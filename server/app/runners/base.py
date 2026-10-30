"""Shared helpers for node runners.

Runners receive params already resolved (registry.resolve_params) and one value per connected
input port (the executor picks the first live value of a multi input). They return only declared
output ports and fire exactly one branch when the node has branches.
"""

from typing import Any, Protocol

from app.engine.envelope import RunContext
from app.engine.latency import sample_latency
from app.models import NodeDefinition, NodeError, NodeResult, PortValue, Taint


class NodeRunner(Protocol):
    async def run(self, inputs: dict[str, PortValue], params: dict[str, Any],
                  ctx: RunContext) -> NodeResult: ...


def text(value: str, taint: set[Taint] | frozenset[Taint] = frozenset()) -> PortValue:
    return PortValue(type="text", value=value, taint=set(taint))


def latency(definition: NodeDefinition, ctx: RunContext, seed_params: dict[str, Any],
            inputs: dict[str, PortValue], median_ms: float | None = None,
            jitter_ms: float | None = None) -> float:
    """Sampled from the definition's cost model unless a median/jitter is given."""
    cost = definition.cost_model
    rng = ctx.rng(definition.type, seed_params, inputs, stream="latency")
    return sample_latency(cost.latency_ms if median_ms is None else median_ms,
                          cost.latency_jitter_ms if jitter_ms is None else jitter_ms, rng)


def missing_input(definition: NodeDefinition, port: str) -> NodeResult:
    return NodeResult(latency_ms=0, error=NodeError(
        code="invalid_input", message=f"{definition.type}: no value on input {port!r}",
        retryable=False))
