import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.catalog.compat import port_compat
from app.catalog.default_graph import default_graph
from app.catalog.registry import (
    REGISTRY,
    RUNNERS,
    catalog,
    default_params,
    expand_outputs,
    get_definition,
    resolve_params,
)
from app.main import app
from app.models import Graph, NodeDefinition

client = TestClient(app)

DEFAULT_GRAPH_FIXTURE = (
    Path(__file__).resolve().parents[2] / "shared" / "fixtures" / "graphs" / "default.json"
)

MVP_TYPES = {
    "customer_message",
    "jev_intent_router",
    "jev_safety_check",
    "llm_answer_generator",
    "policy_engine",
    "knowledge_lookup",
    "human_review_queue",
    "customer_response",
}
M5_TYPES = {"jev_urgency_scorer", "jev_escalation_gate", "llm_summarizer", "pii_redactor"}
ALL_TYPES = MVP_TYPES | M5_TYPES

# --- catalog self-consistency --------------------------------------------------


def test_catalog_has_the_mvp_and_m5_nodes() -> None:
    assert {d.type for d in catalog()} == ALL_TYPES
    assert {d.type for d in catalog() if d.mvp} == MVP_TYPES


@pytest.mark.parametrize("definition", catalog(), ids=lambda d: d.type)
def test_definition_is_self_consistent(definition: NodeDefinition) -> None:
    # Re-validating the wire form re-runs every model check (ports, params, defaults).
    wire = definition.model_dump(by_alias=True)
    assert NodeDefinition.model_validate(wire) == definition
    for spec in definition.params:
        spec.check(spec.default)
    # Expanding with every option selected must not collide with static port ids.
    specs = {spec.key: spec for spec in definition.params}
    dynamic_keys = [p.dynamic_from_param for p in definition.outputs if p.dynamic_from_param]
    expand_outputs(definition, {key: specs[key].options for key in dynamic_keys})  # type: ignore[union-attr]


def test_exactly_one_source_and_one_sink() -> None:
    assert [d.type for d in catalog() if d.is_source] == ["customer_message"]
    assert [d.type for d in catalog() if d.is_sink] == ["customer_response"]


def test_decision_nodes_have_branches() -> None:
    for node_type in ("jev_intent_router", "jev_safety_check", "policy_engine"):
        assert any(p.branch for p in get_definition(node_type).outputs), node_type


def test_every_node_type_has_a_runner() -> None:
    assert set(REGISTRY) == set(RUNNERS) == ALL_TYPES
    for node_type, entry in REGISTRY.items():
        assert entry.runner is RUNNERS[node_type]


def test_unknown_type() -> None:
    with pytest.raises(KeyError, match="unknown node type"):
        get_definition("nope")


# --- params --------------------------------------------------------------------


def test_resolve_params_fills_defaults() -> None:
    router = get_definition("jev_intent_router")
    resolved = resolve_params(router, {"threshold": 0.8})
    assert resolved == {**default_params(router), "threshold": 0.8}


@pytest.mark.parametrize(
    ("params", "message"),
    [
        ({"bogus": 1}, "unknown params"),
        ({"threshold": 2}, "outside"),
        ({"allowed_intents": ["billing", "refunds"]}, "unknown options"),
        ({"allowed_intents": []}, "at least 1"),
    ],
)
def test_resolve_params_rejects_bad_values(params: dict, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        resolve_params(get_definition("jev_intent_router"), params)


# --- branch expansion ----------------------------------------------------------


def _ids(node_type: str, params: dict) -> list[str]:
    return [p.id for p in expand_outputs(get_definition(node_type), params)]


def test_router_expansion_uses_default_intents() -> None:
    assert _ids("jev_intent_router", {}) == [
        "intent", "probabilities", "confidence",
        "route.billing", "route.technical_support", "route.bug_report", "route.feature_request",
        "route.low_confidence",
    ]


def test_router_expansion_follows_allowed_intents() -> None:
    ports = expand_outputs(get_definition("jev_intent_router"),
                           {"allowed_intents": ["account", "billing"]})
    branches = [p for p in ports if p.branch]
    assert [p.id for p in branches] == ["route.account", "route.billing", "route.low_confidence"]
    assert branches[0].label == "Account"
    assert all(p.type == "text" and p.dynamic_from_param is None for p in branches)


def test_expansion_leaves_static_nodes_alone() -> None:
    for node_type in ("jev_safety_check", "policy_engine", "llm_answer_generator"):
        definition = get_definition(node_type)
        assert expand_outputs(definition, {}) == definition.outputs


# --- default graph -------------------------------------------------------------


def test_default_graph_matches_fixture() -> None:
    fixture = Graph.model_validate_json(DEFAULT_GRAPH_FIXTURE.read_text())
    assert fixture == default_graph(), (
        "shared/fixtures/graphs/default.json is stale; regenerate it with "
        "`.venv/bin/python -m app.catalog.default_graph > ../shared/fixtures/graphs/default.json`"
    )


def test_default_graph_edges_are_wired_to_real_ports() -> None:
    graph = default_graph()
    nodes = {n.id: n for n in graph.nodes}
    for edge in graph.edges:
        src, dst = nodes[edge.source], nodes[edge.target]
        outputs = {p.id: p for p in expand_outputs(get_definition(src.type), src.params)}
        inputs = {p.id: p for p in get_definition(dst.type).inputs}
        compat, _ = port_compat(outputs[edge.source_port], inputs[edge.target_port])
        assert compat == "ok", edge.id


def test_default_graph_keeps_its_weaknesses() -> None:
    graph = default_graph()
    wired = {(e.source, e.source_port) for e in graph.edges}
    assert ("router", "route.low_confidence") not in wired
    assert ("policy", "route.block") not in wired
    types = {n.type for n in graph.nodes}
    assert "jev_safety_check" not in types
    llm = next(n for n in graph.nodes if n.type == "llm_answer_generator")
    assert llm.params["model"] == "large" and llm.params["max_tokens"] == 512


# --- endpoints -----------------------------------------------------------------


def test_get_catalog() -> None:
    response = client.get("/api/catalog")
    assert response.status_code == 200
    body = response.json()
    assert list(body) == ["nodes"]
    assert len(body["nodes"]) == len(ALL_TYPES)
    definitions = [NodeDefinition.model_validate(d) for d in body["nodes"]]
    assert definitions == catalog()
    router = next(d for d in body["nodes"] if d["type"] == "jev_intent_router")
    assert "costModel" in router
    template = next(p for p in router["outputs"] if p["id"] == "route.*")
    assert template["dynamicFromParam"] == "allowed_intents"


def test_get_default_graph() -> None:
    response = client.get("/api/graphs/default")
    assert response.status_code == 200
    assert response.json() == json.loads(DEFAULT_GRAPH_FIXTURE.read_text())
