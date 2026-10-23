import json
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.catalog.default_graph import default_graph
from app.catalog.registry import REGISTRY, default_params
from app.engine.validator import validate_graph, validate_payload
from app.main import app
from app.models import CostModel, Graph, IssueCode, NodeDefinition, Port, ValidationReport

client = TestClient(app)

GRAPHS = Path(__file__).resolve().parents[2] / "shared" / "fixtures" / "graphs"

ERROR_CODES = {
    IssueCode.UNKNOWN_NODE_TYPE, IssueCode.UNKNOWN_PORT, IssueCode.DUPLICATE_ID,
    IssueCode.DUPLICATE_EDGE, IssueCode.INCOMPATIBLE_PORTS, IssueCode.ENUM_VALUES_MISMATCH,
    IssueCode.INPUT_FAN_IN_EXCEEDED, IssueCode.FAN_OUT_EXCEEDED,
    IssueCode.MISSING_REQUIRED_INPUT, IssueCode.CYCLE, IssueCode.NO_SOURCE,
    IssueCode.MULTIPLE_SOURCES, IssueCode.NO_SINK, IssueCode.INVALID_PARAM,
    IssueCode.GATE_NEEDS_SIGNAL, IssueCode.GRAPH_TOO_LARGE,
}

# invalid-<code>.json -> the exact set of error codes it must produce. A graph with no
# source always leaves some required input unconnected, hence the second code there.
FIXTURE_ERRORS = {
    code: {code} for code in ERROR_CODES
    if code not in {IssueCode.ENUM_VALUES_MISMATCH, IssueCode.GATE_NEEDS_SIGNAL}
}
FIXTURE_ERRORS[IssueCode.NO_SOURCE] = {IssueCode.NO_SOURCE, IssueCode.MISSING_REQUIRED_INPUT}


def _fixture(code: IssueCode) -> Any:
    name = "invalid-" + code.value.lower().replace("_", "-") + ".json"
    return json.loads((GRAPHS / name).read_text())


def _codes(report: ValidationReport, severity: str | None = None) -> set[IssueCode]:
    return {i.code for i in report.issues if severity is None or i.severity == severity}


def _issues(report: ValidationReport, code: IssueCode) -> list[tuple[Any, ...]]:
    return [(i.node_id, i.edge_id, i.port_id) for i in report.issues if i.code == code]


# --- graph builder for warning tests -------------------------------------------


def _graph(nodes: dict[str, str], links: list[str],
           params: dict[str, dict[str, Any]] | None = None,
           definitions: dict[str, NodeDefinition] | None = None) -> Graph:
    """nodes: id -> type; links: "src.port>dst.port" (port ids may contain dots)."""
    defs = definitions or {t: e.definition for t, e in REGISTRY.items()}
    node_list = [
        {"id": node_id, "type": node_type, "position": {"x": 0, "y": 0},
         "params": {**default_params(defs[node_type]), **(params or {}).get(node_id, {})}}
        for node_id, node_type in nodes.items()
    ]
    edges = []
    for link in links:
        src, dst = link.split(">")
        (s, sp), (t, tp) = src.split(".", 1), dst.split(".", 1)
        edges.append({"id": link, "source": s, "sourcePort": sp, "target": t, "targetPort": tp})
    return Graph.model_validate({"nodes": node_list, "edges": edges})


MSG_RESP = {"msg": "customer_message", "resp": "customer_response"}


# --- errors: one fixture per code ------------------------------------------------


def test_every_issue_code_is_classified() -> None:
    warnings = {c for c in IssueCode if c not in ERROR_CODES}
    assert len(warnings) == 7


@pytest.mark.parametrize("code", sorted(FIXTURE_ERRORS), ids=str)
def test_invalid_fixture_reports_its_error(code: IssueCode) -> None:
    report = validate_payload(_fixture(code))
    assert not report.ok
    assert _codes(report, "error") == FIXTURE_ERRORS[code]


def test_minimal_valid_graph() -> None:
    report = validate_graph(_graph(MSG_RESP, ["msg.text>resp.text"]))
    assert report.ok
    assert _codes(report) == {IssueCode.NO_HUMAN_FALLBACK}


def test_error_locations() -> None:
    def located(code: IssueCode) -> list[tuple[Any, ...]]:
        return _issues(validate_payload(_fixture(code)), code)

    assert located(IssueCode.UNKNOWN_NODE_TYPE) == [("oracle", None, None)]
    assert located(IssueCode.UNKNOWN_PORT) == [("resp", "msg.text->resp.body", "body")]
    assert located(IssueCode.DUPLICATE_ID) == [("resp", None, None)]
    assert located(IssueCode.DUPLICATE_EDGE) == [(None, "copy", None)]
    assert located(IssueCode.INCOMPATIBLE_PORTS) == [
        ("resp", "router.confidence->resp.text", "text")]
    assert located(IssueCode.INPUT_FAN_IN_EXCEEDED) == [("llm", None, "context")]
    assert located(IssueCode.FAN_OUT_EXCEEDED) == [("msg", None, "text")]
    assert located(IssueCode.MISSING_REQUIRED_INPUT) == [("resp", None, "text")]
    assert located(IssueCode.CYCLE) == [
        ("llm", "llm.text->policy.text", None), ("policy", "policy.route.pass->llm.text", None)]
    assert located(IssueCode.MULTIPLE_SOURCES) == [("msg", None, None), ("msg2", None, None)]
    assert len(located(IssueCode.INVALID_PARAM)) == 2  # sla_ms out of range, unknown "color"


def test_edge_to_missing_node() -> None:
    report = validate_graph(_graph(MSG_RESP, ["msg.text>resp.text", "msg.text>ghost.text"]))
    assert _issues(report, IssueCode.UNKNOWN_PORT) == [(None, "msg.text>ghost.text", None)]


def test_edges_to_unknown_types_are_not_double_reported() -> None:
    report = validate_payload(_fixture(IssueCode.UNKNOWN_NODE_TYPE))
    assert _codes(report, "error") == {IssueCode.UNKNOWN_NODE_TYPE}


def test_router_ports_follow_allowed_intents() -> None:
    nodes = {**MSG_RESP, "router": "jev_intent_router"}
    links = ["msg.text>router.text", "router.route.account>resp.text"]
    assert IssueCode.UNKNOWN_PORT in _codes(validate_graph(_graph(nodes, links)))
    params = {"router": {"allowed_intents": ["account"]}}
    assert IssueCode.UNKNOWN_PORT not in _codes(validate_graph(_graph(nodes, links, params)))


def test_bad_branch_param_does_not_cascade_into_unknown_ports() -> None:
    nodes = {**MSG_RESP, "router": "jev_intent_router"}
    links = ["msg.text>router.text", "router.route.account>resp.text"]
    report = validate_graph(_graph(nodes, links, {"router": {"allowed_intents": []}}))
    assert _codes(report, "error") == {IssueCode.INVALID_PARAM}


def test_too_many_edges() -> None:
    data = _fixture(IssueCode.MISSING_REQUIRED_INPUT)
    data["edges"] = [{"id": f"e{i}", "source": "msg", "sourcePort": "text", "target": "resp",
                      "targetPort": "text"} for i in range(81)]
    report = validate_payload(data)
    assert _codes(report) == {IssueCode.GRAPH_TOO_LARGE}
    assert "81 edges" in report.issues[0].message


# --- errors that need node types outside the MVP catalog -------------------------


def _extra_definitions() -> dict[str, NodeDefinition]:
    defs = {t: e.definition for t, e in REGISTRY.items()}
    cost = CostModel(latency_ms=1)
    defs["urgency_classifier"] = NodeDefinition(
        type="urgency_classifier", title="Urgency", category="jev", description="test",
        inputs=[Port(id="text", label="Text", type="text")],
        outputs=[Port(id="level", label="Level", type="enum", enum_values=["low", "high", "p0"]),
                 Port(id="raw", label="Raw", type="any")],
        params=[], cost_model=cost)
    defs["escalation_gate"] = NodeDefinition(
        type="escalation_gate", title="Gate", category="jev", description="test",
        inputs=[Port(id="text", label="Text", type="text"),
                Port(id="level", label="Level", type="enum", enum_values=["low", "high"],
                     required=False),
                Port(id="confidence", label="Confidence", type="probability", required=False)],
        outputs=[Port(id="route.auto", label="Auto", type="text", branch=True)],
        params=[], cost_model=cost, requires_one_of=["level", "confidence"])
    return defs


def _gate_graph(*extra_links: str) -> Graph:
    defs = _extra_definitions()
    nodes = {**MSG_RESP, "urgency": "urgency_classifier", "gate": "escalation_gate"}
    links = ["msg.text>urgency.text", "msg.text>gate.text", "gate.route.auto>resp.text",
             *extra_links]
    return _graph(nodes, links, definitions=defs)


def test_enum_values_mismatch() -> None:
    graph = _gate_graph("urgency.level>gate.level")
    report = validate_graph(graph, _extra_definitions())
    assert _codes(report, "error") == {IssueCode.ENUM_VALUES_MISMATCH}
    assert "p0" in report.issues[0].message


def test_gate_needs_signal() -> None:
    report = validate_graph(_gate_graph(), _extra_definitions())
    assert _codes(report, "error") == {IssueCode.GATE_NEEDS_SIGNAL}
    assert _issues(report, IssueCode.GATE_NEEDS_SIGNAL) == [("gate", None, None)]


def test_any_source_is_a_warning() -> None:
    defs = _extra_definitions()
    graph = _graph({**MSG_RESP, "urgency": "urgency_classifier"},
                   ["msg.text>urgency.text", "msg.text>resp.text", "urgency.raw>resp.text"],
                   definitions=defs)
    report = validate_graph(graph, defs)
    assert report.ok
    assert _issues(report, IssueCode.ANY_SOURCE) == [("resp", "urgency.raw>resp.text", "text")]


# --- warnings ----------------------------------------------------------------------


def test_default_graph_reports_its_weaknesses() -> None:
    report = validate_graph(default_graph())
    assert report.ok
    assert [(i.code, i.node_id, i.port_id) for i in report.issues] == [
        (IssueCode.UNCONNECTED_BRANCH, "router", "route.low_confidence"),
        (IssueCode.UNCONNECTED_BRANCH, "policy", "route.block"),
        (IssueCode.NO_HUMAN_FALLBACK, None, None),
    ]


def test_default_fixture_matches() -> None:
    fixture = json.loads((GRAPHS / "default.json").read_text())
    assert validate_payload(fixture) == validate_graph(default_graph())


def test_unreachable_and_dead_end() -> None:
    nodes = {**MSG_RESP, "llm": "llm_answer_generator", "human": "human_review_queue"}
    # llm feeds the response but nothing feeds llm; human is fed but goes nowhere.
    links = ["msg.text>resp.text", "llm.text>resp.text", "msg.text>human.text"]
    report = validate_graph(_graph(nodes, links))
    assert _issues(report, IssueCode.UNREACHABLE_NODE) == [("llm", None, None)]
    assert _issues(report, IssueCode.DEAD_END) == [("human", None, None)]


def _safety_case(links: list[str]) -> list[tuple[Any, ...]]:
    # Nodes a case does not wire up raise unrelated errors; only this warning is checked.
    nodes = {**MSG_RESP, "safety": "jev_safety_check", "llm": "llm_answer_generator",
             "llm2": "llm_answer_generator", "policy": "policy_engine",
             "human": "human_review_queue"}
    report = validate_graph(_graph(nodes, links))
    return _issues(report, IssueCode.NO_SAFETY_COVERAGE)


@pytest.mark.parametrize(
    ("links", "flagged"),
    [
        # Unprotected: message -> LLM -> customer.
        (["msg.text>llm.text", "llm.text>resp.text"], ["llm"]),
        # A safety check before the LLM covers it, but only through route.safe.
        (["msg.text>safety.text", "safety.route.safe>llm.text", "llm.text>resp.text"], []),
        (["msg.text>safety.text", "safety.route.unsafe>llm.text", "llm.text>resp.text"],
         ["llm"]),
        # A policy engine after the LLM covers it, but only through route.pass.
        (["msg.text>llm.text", "llm.text>policy.text", "policy.route.pass>resp.text"], []),
        (["msg.text>llm.text", "llm.text>policy.text", "policy.route.block>resp.text"],
         ["llm"]),
        # One covered path is not enough: the direct bypass still reaches the customer.
        (["msg.text>llm.text", "llm.text>policy.text", "policy.route.pass>resp.text",
          "llm.text>resp.text"], ["llm"]),
        # The policy before the second LLM does not protect it.
        (["msg.text>llm.text", "llm.text>policy.text", "policy.route.pass>llm2.text",
          "llm2.text>resp.text"], ["llm2"]),
        # A safety check upstream covers every LLM after it.
        (["msg.text>safety.text", "safety.route.safe>llm.text", "llm.text>llm2.text",
          "llm2.text>resp.text"], []),
    ],
)
def test_no_safety_coverage(links: list[str], flagged: list[str]) -> None:
    assert [node for node, _, _ in _safety_case(links)] == flagged


def test_human_fallback_satisfied() -> None:
    nodes = {**MSG_RESP, "human": "human_review_queue"}
    report = validate_graph(_graph(nodes, ["msg.text>human.text", "human.text>resp.text"]))
    assert _codes(report) == set()


def test_multi_input_race() -> None:
    nodes = {**MSG_RESP, "safety": "jev_safety_check", "human": "human_review_queue"}
    exclusive = ["msg.text>safety.text", "safety.route.safe>resp.text",
                 "safety.route.unsafe>human.text", "human.text>resp.text"]
    assert IssueCode.MULTI_INPUT_RACE not in _codes(validate_graph(_graph(nodes, exclusive)))
    racing = [*exclusive, "msg.text>resp.text"]
    report = validate_graph(_graph(nodes, racing))
    assert _issues(report, IssueCode.MULTI_INPUT_RACE) == [("resp", None, "text")]


def test_router_branches_into_one_input_do_not_race() -> None:
    # The default graph feeds four router branches into llm.text.
    assert IssueCode.MULTI_INPUT_RACE not in _codes(validate_graph(default_graph()))


def test_no_semantic_warnings_without_a_source() -> None:
    report = validate_payload(_fixture(IssueCode.NO_SOURCE))
    assert _codes(report, "warning") == set()


# --- endpoint ------------------------------------------------------------------------


def test_validate_endpoint_default_graph() -> None:
    body = json.loads((GRAPHS / "default.json").read_text())
    response = client.post("/api/graphs/validate", json=body)
    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is True
    assert [i["code"] for i in data["issues"]] == [
        "UNCONNECTED_BRANCH", "UNCONNECTED_BRANCH", "NO_HUMAN_FALLBACK"]
    assert data["issues"][0]["nodeId"] == "router"
    assert data["issues"][0]["portId"] == "route.low_confidence"


def test_validate_endpoint_reports_errors() -> None:
    response = client.post("/api/graphs/validate", json=_fixture(IssueCode.CYCLE))
    assert response.status_code == 200
    assert response.json()["ok"] is False


def test_validate_endpoint_too_large_is_a_report_not_a_422() -> None:
    response = client.post("/api/graphs/validate", json=_fixture(IssueCode.GRAPH_TOO_LARGE))
    assert response.status_code == 200
    assert response.json()["issues"][0]["code"] == "GRAPH_TOO_LARGE"


@pytest.mark.parametrize("body", [[], {"nodes": "x", "edges": []}, {"nodes": [], "edges": [],
                                                                    "extra": 1}])
def test_validate_endpoint_rejects_malformed_bodies(body: Any) -> None:
    response = client.post("/api/graphs/validate", json=body)
    assert response.status_code == 422
