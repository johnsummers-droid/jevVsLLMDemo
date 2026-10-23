from typing import Any

from app.catalog.definitions.io import CUSTOMER_MESSAGE, CUSTOMER_RESPONSE
from app.engine.envelope import RunContext, merged_taint
from app.models import NodeResult, PortValue, TicketMeta
from app.runners.base import missing_input, text


class CustomerMessageRunner:
    """Emits the envelope's ticket. Injection tickets carry the "injection" taint (D4).

    traffic_mix and attack_rate choose which tickets arrive; that is the traffic generator's job
    (T5), so the runner ignores them.
    """

    async def run(self, inputs: dict[str, PortValue], params: dict[str, Any],
                  ctx: RunContext) -> NodeResult:
        ticket = ctx.ticket
        taint = {"injection"} if ticket.category == "prompt_injection" else set()
        meta = TicketMeta(channel="chat", language=params["language"])
        return NodeResult(
            outputs={
                "text": text(ticket.text, taint),
                "meta": PortValue(type="json", value=meta.model_dump(by_alias=True)),
            },
            latency_ms=CUSTOMER_MESSAGE.cost_model.latency_ms,
        )


class CustomerResponseRunner:
    """The sink. It has no outputs; the executor reads what arrived on its input."""

    async def run(self, inputs: dict[str, PortValue], params: dict[str, Any],
                  ctx: RunContext) -> NodeResult:
        if "text" not in inputs:
            return missing_input(CUSTOMER_RESPONSE, "text")
        return NodeResult(latency_ms=CUSTOMER_RESPONSE.cost_model.latency_ms,
                          decision={"delivered": True, "taint": sorted(merged_taint(inputs))})
