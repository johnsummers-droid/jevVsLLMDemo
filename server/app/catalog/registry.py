"""Maps node type -> (NodeDefinition, NodeRunner) and expands dynamic branch ports."""

from dataclasses import dataclass
from typing import Any

from app.catalog.definitions import ALL_DEFINITIONS
from app.models import NodeDefinition, Port
from app.runners.base import NodeRunner
from app.runners.human import HumanReviewRunner
from app.runners.io import CustomerMessageRunner, CustomerResponseRunner
from app.runners.jev import (
    EscalationGateRunner,
    IntentRouterRunner,
    SafetyCheckRunner,
    UrgencyScorerRunner,
)
from app.runners.llm import AnswerGeneratorRunner, SummarizerRunner
from app.runners.tool import KnowledgeLookupRunner, PiiRedactorRunner, PolicyEngineRunner

RUNNERS: dict[str, NodeRunner] = {
    "customer_message": CustomerMessageRunner(),
    "jev_intent_router": IntentRouterRunner(),
    "jev_safety_check": SafetyCheckRunner(),
    "jev_urgency_scorer": UrgencyScorerRunner(),
    "jev_escalation_gate": EscalationGateRunner(),
    "llm_answer_generator": AnswerGeneratorRunner(),
    "llm_summarizer": SummarizerRunner(),
    "policy_engine": PolicyEngineRunner(),
    "knowledge_lookup": KnowledgeLookupRunner(),
    "pii_redactor": PiiRedactorRunner(),
    "human_review_queue": HumanReviewRunner(),
    "customer_response": CustomerResponseRunner(),
}


@dataclass(frozen=True)
class RegistryEntry:
    definition: NodeDefinition
    runner: NodeRunner


REGISTRY: dict[str, RegistryEntry] = {
    d.type: RegistryEntry(definition=d, runner=RUNNERS[d.type]) for d in ALL_DEFINITIONS
}
if len(REGISTRY) != len(ALL_DEFINITIONS):
    raise RuntimeError("duplicate node types in the catalog")
if set(RUNNERS) != set(REGISTRY):
    raise RuntimeError(f"runners and definitions differ: {sorted(set(RUNNERS) ^ set(REGISTRY))}")


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
