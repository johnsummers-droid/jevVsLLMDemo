from typing import Any

from app.catalog.definitions.human import HUMAN_REVIEW_QUEUE
from app.engine.envelope import RunContext, merged_taint
from app.models import NodeResult, PortValue
from app.runners.base import latency, missing_input, text

CLEAR_RATE = 0.98  # chance the reviewer catches and removes every problem
REVIEW_JITTER = 0.25  # spread of the review time, as a fraction of its median


class HumanReviewRunner:
    """A reviewer approves or fixes the text. Capacity limits arrive in M5."""

    async def run(self, inputs: dict[str, PortValue], params: dict[str, Any],
                  ctx: RunContext) -> NodeResult:
        definition = HUMAN_REVIEW_QUEUE
        if "text" not in inputs:
            return missing_input(definition, "text")
        seed_params: dict[str, Any] = {}  # capacity and review time do not change the verdict
        cleared = ctx.rng(definition.type, seed_params, inputs).random() < CLEAR_RATE
        median = params["reviewer_latency_s"] * 1000
        return NodeResult(
            outputs={"text": text(inputs["text"].value,
                                  set() if cleared else merged_taint(inputs))},
            latency_ms=latency(definition, ctx, params, inputs, median_ms=median,
                               jitter_ms=median * REVIEW_JITTER),
            cost_usd=definition.cost_model.cost_per_call_usd,
            decision={"cleared": cleared},
            escalated=True,
        )
