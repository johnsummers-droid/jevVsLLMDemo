from datetime import UTC, datetime
from typing import Any

import pytest
from pydantic import TypeAdapter, ValidationError

from app.models import (
    BoolParam,
    CostModel,
    Distribution,
    EnumParam,
    Graph,
    GraphEdge,
    GraphNode,
    IntParam,
    IssueCode,
    MultiEnumParam,
    NodeDefinition,
    NodeResult,
    NumberParam,
    ParamSpec,
    Port,
    PortValue,
    StoredGraph,
    StringListParam,
    TextParam,
    ValidationIssue,
    ValidationReport,
)
from app.models.graph import MAX_EDGES, MAX_NODES

# --- wire format -------------------------------------------------------------


def test_camel_case_round_trip() -> None:
    port = Port(id="route.billing", label="Billing", type="text", branch=True)
    wire = port.model_dump(by_alias=True, exclude_defaults=True)
    assert wire == {"id": "route.billing", "label": "Billing", "type": "text", "branch": True}

    edge = GraphEdge.model_validate(
        {"id": "e1", "source": "a", "sourcePort": "text", "target": "b", "targetPort": "text"}
    )
    assert edge.source_port == "text"
    assert GraphEdge.model_validate(edge.model_dump(by_alias=True)) == edge


def test_snake_case_also_accepted() -> None:
    edge = GraphEdge(id="e1", source="a", source_port="text", target="b", target_port="text")
    assert edge.model_dump(by_alias=True)["sourcePort"] == "text"


def test_unknown_fields_rejected() -> None:
    with pytest.raises(ValidationError):
        Port.model_validate({"id": "p", "label": "p", "type": "text", "colour": "red"})


# --- ports -------------------------------------------------------------------


def test_unknown_port_type_rejected() -> None:
    with pytest.raises(ValidationError):
        Port(id="p", label="p", type="video")


@pytest.mark.parametrize(
    "kwargs",
    [
        {"type": "text", "enum_values": ["a"]},
        {"type": "enum", "enum_values": ["a", "a"]},
        {"type": "probability", "score_range": (1, 5)},
        {"type": "score", "score_range": (5, 1)},
        {"type": "text", "json_schema_ref": "Docs"},
        {"type": "boolean", "branch": True},
        {"type": "text", "id": ""},
    ],
)
def test_invalid_port_fields(kwargs: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        Port(**{"id": "p", "label": "p", **kwargs})


def test_valid_typed_ports() -> None:
    Port(id="intent", label="Intent", type="enum", enum_values=["billing", "bug_report"])
    Port(id="score", label="Score", type="score", score_range=(1, 5))
    Port(id="probs", label="Probabilities", type="json", json_schema_ref="Distribution")


# --- params ------------------------------------------------------------------

PARAM_CASES: list[tuple[Any, list[Any], list[Any]]] = [
    (
        NumberParam(key="threshold", label="Threshold", default=0.5, min=0, max=1),
        [0, 0.5, 1, 1.0],
        [-0.1, 1.01, "0.5", True, None],
    ),
    (
        IntParam(key="top_k", label="Top k", default=3, min=1, max=10),
        [1, 10],
        [0, 11, 2.5, True, "3"],
    ),
    (
        EnumParam(key="model", label="Model", default="large", options=["small", "large"]),
        ["small", "large"],
        ["medium", "", None],
    ),
    (
        MultiEnumParam(
            key="intents", label="Intents", default=["a"], options=["a", "b", "c"], min_selected=1
        ),
        [["a"], ["a", "c"]],
        [[], ["d"], ["a", "a"], "a", [1]],
    ),
    (
        StringListParam(key="phrases", label="Phrases", default=[], max_items=2, max_len=5),
        [[], ["ok"], ["12345", "x"]],
        [["a", "b", "c"], ["123456"], "abc", [1]],
    ),
    (
        TextParam(key="prompt", label="Prompt", default="hi", max_len=10),
        ["", "0123456789"],
        ["01234567890", 3, None],
    ),
    (
        BoolParam(key="flag", label="Flag", default=False),
        [True, False],
        [0, 1, "true", None],
    ),
]


@pytest.mark.parametrize(
    ("spec", "good", "bad"), PARAM_CASES, ids=[c[0].kind for c in PARAM_CASES]
)
def test_param_check(spec: Any, good: list[Any], bad: list[Any]) -> None:
    for value in good:
        assert spec.check(value) == value
    for value in bad:
        with pytest.raises(ValueError):
            spec.check(value)


@pytest.mark.parametrize(
    "data",
    [
        {"kind": "number", "key": "t", "label": "t", "default": 2, "min": 0, "max": 1},
        {"kind": "int", "key": "k", "label": "k", "default": 0, "min": 1, "max": 5},
        {"kind": "enum", "key": "m", "label": "m", "default": "x", "options": ["a"]},
        {"kind": "multi_enum", "key": "i", "label": "i", "default": [], "options": ["a"]},
        {"kind": "text", "key": "p", "label": "p", "default": "too long", "maxLen": 3},
    ],
)
def test_invalid_param_default_rejected(data: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        TypeAdapter(ParamSpec).validate_python(data)


def test_param_spec_discriminated_by_kind() -> None:
    spec = TypeAdapter(ParamSpec).validate_python(
        {"kind": "multi_enum", "key": "i", "label": "i", "default": ["a"], "options": ["a"],
         "minSelected": 1}
    )
    assert isinstance(spec, MultiEnumParam)
    with pytest.raises(ValidationError):
        TypeAdapter(ParamSpec).validate_python({"kind": "slider", "key": "s", "label": "s"})


# --- node definitions ----------------------------------------------------------


def _router(**overrides: Any) -> NodeDefinition:
    data: dict[str, Any] = {
        "type": "jev_intent_router",
        "title": "Jev intent router",
        "category": "jev",
        "description": "Routes a message to an intent.",
        "inputs": [Port(id="text", label="Text", type="text", multi=True)],
        "outputs": [
            Port(id="intent", label="Intent", type="enum"),
            Port(id="confidence", label="Confidence", type="probability"),
            Port(id="route.<intent>", label="Route", type="text", branch=True,
                 dynamic_from_param="allowed_intents"),
            Port(id="route.low_confidence", label="Low confidence", type="text", branch=True),
        ],
        "params": [
            MultiEnumParam(key="allowed_intents", label="Intents", default=["billing"],
                           options=["billing", "bug_report"]),
            NumberParam(key="threshold", label="Threshold", default=0.5, min=0, max=1),
        ],
        "cost_model": CostModel(latency_ms=40, latency_jitter_ms=15, cost_per_call_usd=0.0002),
    }
    data.update(overrides)
    return NodeDefinition(**data)


def test_valid_node_definition_round_trip() -> None:
    node = _router()
    wire = node.model_dump(by_alias=True)
    assert wire["costModel"]["latencyMs"] == 40
    assert wire["params"][0]["kind"] == "multi_enum"
    assert NodeDefinition.model_validate(wire) == node


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"inputs": [Port(id="t", label="t", type="text")] * 2}, "duplicate input"),
        ({"outputs": [Port(id="o", label="o", type="text")] * 2}, "duplicate output"),
        ({"params": [BoolParam(key="k", label="k", default=False)] * 2}, "duplicate param"),
        ({"inputs": [Port(id="t", label="t", type="text", branch=True)]}, "outputs only"),
        ({"outputs": [Port(id="o", label="o", type="text", multi=True)]}, "inputs only"),
        (
            {"outputs": [Port(id="o", label="o", type="text", branch=True,
                              dynamic_from_param="threshold")]},
            "multi_enum",
        ),
        (
            {"outputs": [Port(id="o", label="o", type="text", dynamic_from_param="allowed_intents")]},
            "must be branch",
        ),
        ({"is_source": True}, "source nodes have no inputs"),
        ({"is_sink": True}, "sink nodes have no outputs"),
        ({"category": "human_review"}, "category"),
    ],
)
def test_inconsistent_node_definition_rejected(overrides: dict[str, Any], message: str) -> None:
    with pytest.raises(ValidationError, match=message):
        _router(**overrides)


def test_source_and_sink_shapes() -> None:
    _router(inputs=[], is_source=True)
    _router(outputs=[], is_sink=True)
    with pytest.raises(ValidationError, match="both source and sink"):
        _router(inputs=[], outputs=[], is_source=True, is_sink=True)


# --- graphs ------------------------------------------------------------------


def _node(i: int) -> GraphNode:
    return GraphNode(id=f"n{i}", type="customer_message", position={"x": i, "y": 0})


def _edge(i: int) -> GraphEdge:
    return GraphEdge(id=f"e{i}", source="a", source_port="text", target="b", target_port="text")


def test_graph_round_trip() -> None:
    graph = Graph(nodes=[_node(0), _node(1)], edges=[_edge(0)])
    wire = graph.model_dump(by_alias=True)
    assert wire["schemaVersion"] == 1
    assert Graph.model_validate(wire) == graph

    stored = StoredGraph(team_id="t1", version=3, graph=graph, updated_at=datetime.now(UTC))
    assert StoredGraph.model_validate_json(stored.model_dump_json(by_alias=True)) == stored


def test_graph_size_limits() -> None:
    Graph(nodes=[_node(i) for i in range(MAX_NODES)], edges=[_edge(i) for i in range(MAX_EDGES)])
    with pytest.raises(ValidationError):
        Graph(nodes=[_node(i) for i in range(MAX_NODES + 1)], edges=[])
    with pytest.raises(ValidationError):
        Graph(nodes=[], edges=[_edge(i) for i in range(MAX_EDGES + 1)])


def test_graph_rejects_unknown_schema_version() -> None:
    with pytest.raises(ValidationError):
        Graph.model_validate({"schemaVersion": 2, "nodes": [], "edges": []})


# --- runtime values and results ------------------------------------------------


def test_distribution_must_sum_to_one() -> None:
    Distribution(probs={"billing": 0.7, "bug_report": 0.3})
    Distribution(probs={"a": 1 / 3, "b": 1 / 3, "c": 1 / 3})
    for probs in ({"a": 0.5, "b": 0.4}, {"a": 1.2, "b": -0.2}, {}):
        with pytest.raises(ValidationError):
            Distribution(probs=probs)


def test_port_value_taint() -> None:
    value = PortValue(type="text", value="hi", taint={"injection"})
    assert PortValue.model_validate_json(value.model_dump_json(by_alias=True)) == value
    with pytest.raises(ValidationError):
        PortValue(type="text", value="hi", taint={"spicy"})


def test_node_result_fired_branch_needs_output() -> None:
    out = {"route.billing": PortValue(type="text", value="hi")}
    result = NodeResult(outputs=out, fired_branch="route.billing", latency_ms=40)
    assert result.model_dump(by_alias=True)["firedBranch"] == "route.billing"
    with pytest.raises(ValidationError, match="fired_branch"):
        NodeResult(outputs={}, fired_branch="route.billing", latency_ms=40)
    with pytest.raises(ValidationError):
        NodeResult(latency_ms=-1)


# --- validation report ---------------------------------------------------------


def test_validation_report_ok_flag() -> None:
    warning = ValidationIssue(code=IssueCode.DEAD_END, severity="warning", message="w")
    error = ValidationIssue(code=IssueCode.CYCLE, severity="error", message="e", node_id="n1")

    assert ValidationReport.from_issues([]).ok
    assert ValidationReport.from_issues([warning]).ok
    assert not ValidationReport.from_issues([warning, error]).ok
    with pytest.raises(ValidationError):
        ValidationReport(ok=True, issues=[error])

    wire = ValidationReport.from_issues([error]).model_dump(by_alias=True)
    assert wire["issues"][0] == {
        "code": "CYCLE", "severity": "error", "message": "e",
        "nodeId": "n1", "edgeId": None, "portId": None,
    }
