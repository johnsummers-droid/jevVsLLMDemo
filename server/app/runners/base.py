"""Shared helpers for node runners.

Runners receive params already resolved (registry.resolve_params) and one value per connected
input port (the executor picks the first live value of a multi input). They return only declared
output ports and fire exactly one branch when the node has branches.
"""

from typing import Any, Protocol

from app.engine.envelope import RunContext
from app.engine.latency import sample_latency
from app.models import NodeDefinition, NodeError, NodeResult, PortValue, Taint
from app.providers.base import CallMeasure, ProviderFailure


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


def provider_failed(failure: ProviderFailure) -> NodeResult:
    return NodeResult(latency_ms=failure.latency_ms, error=NodeError(
        code=failure.code, message=failure.message, retryable=failure.retryable))


def measured(measure: CallMeasure | None, definition: NodeDefinition, ctx: RunContext,
             seed_params: dict[str, Any], inputs: dict[str, PortValue]) -> dict[str, Any]:
    """A provider node's latency, cost, tokens and cached flag: measured on a real call (U4),
    else sampled from the node's cost model (the mocks)."""
    if measure is None:
        return {"latency_ms": latency(definition, ctx, seed_params, inputs),
                "cost_usd": definition.cost_model.cost_per_call_usd}
    return {"latency_ms": measure.latency_ms, "cost_usd": measure.cost_usd,
            "tokens_in": measure.tokens_in, "tokens_out": measure.tokens_out,
            "cached": measure.replayed}
