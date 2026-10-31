"""T32: help panel content (plan1.txt S4-S7)."""

import asyncio
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.catalog.registry import REGISTRY, catalog, expand_outputs, resolve_params
from app.engine.envelope import make_context
from app.main import app
from app.models import HelpExample, NodeDefinition, NodeHelp, PortValue
from app.providers.mock_llm import MARKERS
from app.simulation.loader import load_pack

PRACTICE = {t.id: t for t in load_pack("practice").tickets}
OFFICIAL = load_pack("official").tickets
DEFINITIONS = {d.type: d for d in catalog()}


def run_example(definition: NodeDefinition, example: HelpExample) -> Any:
    """Run the example as S5 says: the ticket's customer message (with its taint) as input,
    unless input_text replaces its text; mock providers; run seed 0."""
    ticket = PRACTICE[example.ticket_id]
    ctx = make_context(ticket, run_seed=0)
    entry = REGISTRY[definition.type]
    inputs: dict[str, PortValue] = {}
    if definition.inputs:
        source = REGISTRY["customer_message"]
        emitted = asyncio.run(source.runner.run({}, resolve_params(source.definition, {}), ctx))
        message = emitted.outputs["text"]
        inputs["text"] = PortValue(type="text", value=example.input_text or message.value,
                                   taint=message.taint)
    params = resolve_params(definition, example.params)
    return asyncio.run(entry.runner.run(inputs, params, ctx)), params


def matches(actual: Any, expected: Any) -> bool:
    """Numbers within 0.005 (help rounds to 2 decimals); objects may list a subset of fields."""
    if isinstance(expected, dict):
        return isinstance(actual, dict) and all(
            k in actual and matches(actual[k], v) for k, v in expected.items())
    if isinstance(expected, list):
        return isinstance(actual, list) and len(actual) == len(expected) and all(
            matches(a, e) for a, e in zip(actual, expected, strict=True))
    if isinstance(expected, float) and not isinstance(expected, bool):
        return isinstance(actual, int | float) and abs(actual - expected) <= 0.005
    return actual == expected and type(actual) is type(expected)


def strings(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        return [s for k, v in value.items() for s in strings(k) + strings(v)]
    if isinstance(value, list):
        return [s for v in value for s in strings(v)]
    return []


def test_every_catalog_node_has_help() -> None:
    assert all(d.help is not None for d in DEFINITIONS.values())


@pytest.mark.parametrize("node_type", DEFINITIONS)
def test_every_node_with_outputs_has_an_example(node_type: str) -> None:
    definition = DEFINITIONS[node_type]
    assert definition.help is not None
    assert (definition.help.example is not None) == bool(definition.outputs)


@pytest.mark.parametrize("node_type", [t for t, d in DEFINITIONS.items() if d.outputs])
def test_example_gives_the_stated_output(node_type: str) -> None:
    definition = DEFINITIONS[node_type]
    assert definition.help is not None and definition.help.example is not None
    example = definition.help.example
    result, params = run_example(definition, example)
    assert result.error is None
    assert result.fired_branch == example.fired_branch
    ports = {p.id for p in expand_outputs(definition, params)}
    assert set(example.outputs) <= ports
    for port_id, expected in example.outputs.items():
        assert port_id in result.outputs, port_id
        actual = result.outputs[port_id].value
        assert matches(actual, expected), f"{port_id}: {actual!r} != {expected!r}"


def test_matches_rules() -> None:
    assert matches(0.9149, 0.91) and not matches(0.92, 0.91)
    assert matches({"a": 1, "b": 2}, {"a": 1}) and not matches({"a": 1}, {"a": 1, "b": 2})
    assert not matches([1, 2], [1]) and not matches(1, True) and not matches("x", "y")


def test_help_reveals_no_scenario_answers() -> None:
    """S6: no mock marker phrase and no official ticket text anywhere in the help."""
    text = "\n".join(s for d in DEFINITIONS.values()
                     for s in strings(d.help.model_dump() if d.help else {})).lower()
    for marker in MARKERS.values():
        assert marker.lower().rstrip(".") not in text, marker
    for ticket in OFFICIAL:
        assert ticket.text.lower() not in text, ticket.id


def test_help_must_cover_params_and_outputs_and_name_only_real_ones() -> None:
    definition = DEFINITIONS["knowledge_lookup"]
    assert definition.help is not None
    good = definition.help.model_dump()
    fields = definition.model_dump(exclude={"help"})

    def build(**changes: Any) -> NodeDefinition:
        return NodeDefinition.model_validate({**fields, "help": {**good, **changes}})

    build()  # the real help is valid
    with pytest.raises(ValueError, match="help params: missing"):
        build(params={"source": "x"})
    with pytest.raises(ValueError, match="help params: unknown"):
        build(params={**good["params"], "nope": "x"})
    with pytest.raises(ValueError, match="help outputs: missing"):
        build(outputs={})
    with pytest.raises(ValueError, match="help inputs: unknown"):
        build(inputs={"nope": "x"})
    with pytest.raises(ValueError, match="help example params: unknown"):
        build(example={**good["example"], "params": {"nope": 1}})
    with pytest.raises(ValueError):
        NodeHelp.model_validate({**good, "how_it_works": []})
    with pytest.raises(ValueError):
        HelpExample.model_validate({**good["example"], "ticket_id": "o-01"})


def test_get_catalog_carries_help() -> None:
    body = TestClient(app).get("/api/catalog").json()
    router = next(d for d in body["nodes"] if d["type"] == "jev_intent_router")
    assert set(router["help"]) >= {"summary", "placement", "howItWorks", "params", "outputs",
                                   "example", "tips"}
    assert router["help"]["example"]["firedBranch"] == "route.technical_support"
    assert set(router["help"]["params"]) == {"allowed_intents", "threshold"}  # keys stay as-is
