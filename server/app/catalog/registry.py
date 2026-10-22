"""Maps node type -> (NodeDefinition, NodeRunner) and expands dynamic branch ports."""

from dataclasses import dataclass
from typing import Any, Protocol

from app.catalog.definitions import ALL_DEFINITIONS
from app.models import NodeDefinition, NodeResult, Port, PortValue


class NodeRunner(Protocol):
    # ctx becomes a typed RunContext when the executor lands (T5).
    async def run(
        self, inputs: dict[str, PortValue], params: dict[str, Any], ctx: Any
    ) -> NodeResult: ...


class StubRunner:
    """Placeholder until the real runners land (T4)."""

    def __init__(self, node_type: str) -> None:
        self.node_type = node_type

    async def run(
        self, inputs: dict[str, PortValue], params: dict[str, Any], ctx: Any
    ) -> NodeResult:
        raise NotImplementedError(f"no runner for {self.node_type!r} yet")


@dataclass(frozen=True)
class RegistryEntry:
    definition: NodeDefinition
    runner: NodeRunner


REGISTRY: dict[str, RegistryEntry] = {
    d.type: RegistryEntry(definition=d, runner=StubRunner(d.type)) for d in ALL_DEFINITIONS
}
if len(REGISTRY) != len(ALL_DEFINITIONS):
    raise RuntimeError("duplicate node types in the catalog")


def catalog() -> list[NodeDefinition]:
    return [entry.definition for entry in REGISTRY.values()]


def get_definition(node_type: str) -> NodeDefinition:
    try:
        return REGISTRY[node_type].definition
    except KeyError:
        raise KeyError(f"unknown node type {node_type!r}") from None


def default_params(definition: NodeDefinition) -> dict[str, Any]:
    return {spec.key: spec.default for spec in definition.params}


def resolve_params(definition: NodeDefinition, params: dict[str, Any]) -> dict[str, Any]:
    """Fill in defaults and check every value. Raises ValueError on unknown keys or bad values."""
    specs = {spec.key: spec for spec in definition.params}
    if unknown := sorted(set(params) - set(specs)):
        raise ValueError(f"{definition.type}: unknown params {unknown}")
    return {key: spec.check(params.get(key, spec.default)) for key, spec in specs.items()}


def expand_outputs(definition: NodeDefinition, params: dict[str, Any]) -> list[Port]:
    """Output ports for a node with these params.

    Each dynamic template port ("route.*", dynamic_from_param="allowed_intents") becomes one
    branch port per selected value, in the order selected, at the template's position.
    """
    resolved = resolve_params(definition, params)
    ports: list[Port] = []
    for port in definition.outputs:
        if port.dynamic_from_param is None:
            ports.append(port)
            continue
        prefix = port.id.removesuffix("*")
        for value in resolved[port.dynamic_from_param]:
            ports.append(port.model_copy(update={
                "id": prefix + value,
                "label": value.replace("_", " ").capitalize(),
                "dynamic_from_param": None,
            }))
    ids = [p.id for p in ports]
    if len(set(ids)) != len(ids):
        raise ValueError(f"{definition.type}: expanded output ids collide: {ids}")
    return ports
