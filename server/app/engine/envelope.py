"""Request envelope (plan1.txt D4) and the context every node runner receives.

Taint rides on text values: a runner's pass-through or generated text carries the taint, and
data outputs (enums, scores, reports) carry none. By default a node's text output keeps the
union of its inputs' taint; runners that know better (LLM, human review, router) adjust it.
"""

import random
from dataclasses import dataclass, field
from typing import Any

from app.engine.seeding import seeded_rng
from app.models import PortValue, Taint, Ticket
from app.providers.base import JevProvider, LLMProvider, ProviderCall


@dataclass
class RequestEnvelope:
    request_id: str
    ticket: Ticket
    decisions: dict[str, dict[str, Any]] = field(default_factory=dict)  # node id -> decision (T5)


@dataclass
class RunContext:
    run_seed: int
    envelope: RequestEnvelope
    jev: JevProvider
    llm: LLMProvider

    @property
    def ticket(self) -> Ticket:
        return self.envelope.ticket

    def rng(self, node_type: str, seed_params: dict[str, Any], inputs: dict[str, PortValue],
            stream: str = "decision") -> random.Random:
        return seeded_rng(self.run_seed, self.ticket.id, node_type, seed_params, inputs, stream)

    def provider_call(self, node_type: str, seed_params: dict[str, Any],
                      inputs: dict[str, PortValue]) -> ProviderCall:
        return ProviderCall(ticket=self.ticket, rng=self.rng(node_type, seed_params, inputs),
                            taint=frozenset(merged_taint(inputs)))


def merged_taint(inputs: dict[str, PortValue]) -> set[Taint]:
    taint: set[Taint] = set()
    for value in inputs.values():
        taint |= value.taint
    return taint


def make_context(ticket: Ticket, run_seed: int = 0, request_id: str | None = None,
                 jev: JevProvider | None = None, llm: LLMProvider | None = None) -> RunContext:
    """A context with the mock providers unless others are given (tests, headless runs)."""
    from app.providers.mock_jev import MockJevProvider
    from app.providers.mock_llm import MockLLMProvider

    return RunContext(run_seed=run_seed,
                      envelope=RequestEnvelope(request_id=request_id or ticket.id, ticket=ticket),
                      jev=jev or MockJevProvider(), llm=llm or MockLLMProvider())
