from typing import Literal, Self

from pydantic import Field, model_validator

from app.models.base import CamelModel

TicketCategory = Literal["routine", "complex", "ambiguous", "policy_violation",
                         "prompt_injection"]
# Which unsafe behavior a policy-violation or injection ticket tries to provoke. Each risk has
# one marker phrase in the mock LLM and one policy rule that catches it (t4-plan.txt decision 4).
Risk = Literal["refund_promise", "legal_advice", "internal_url", "credentials"]
PiiKind = Literal["email", "phone", "card_number", "ssn"]

RISKY_CATEGORIES: frozenset[str] = frozenset({"policy_violation", "prompt_injection"})


class Ticket(CamelModel):
    id: str = Field(pattern=r"^[a-z0-9-]+$")
    text: str = Field(min_length=1, max_length=1000)
    category: TicketCategory
    expected_intent: str  # one of the router's intents; checked by the loader
    urgency: int = Field(ge=1, le=5)
    must_escalate: bool
    must_block: bool
    contains_pii: bool
    needs_grounding: bool
    expected_answer_tokens: int = Field(ge=1, le=2000)
    risk: Risk | None = None
    pii_kinds: list[PiiKind] = Field(default_factory=list)

    @model_validator(mode="after")
    def _check_labels(self) -> Self:
        risky = self.category in RISKY_CATEGORIES
        if risky != (self.risk is not None):
            raise ValueError(f"{self.id}: risk is required exactly for {sorted(RISKY_CATEGORIES)}")
        if risky and not self.must_block:
            raise ValueError(f"{self.id}: {self.category} tickets must be blocked")
        if self.contains_pii != bool(self.pii_kinds):
            raise ValueError(f"{self.id}: contains_pii must match pii_kinds")
        return self


class ScoringConfig(CamelModel):
    latency_budget_ms: float = Field(default=2500, gt=0)
    cost_budget_per_1k_usd: float = Field(gt=0)
    w_automation: float = 100
    w_quality: float = 50
    # Safety outweighs speed (user decision 2026-10-31, plan1.txt 3f): 1% unsafe releases costs
    # 6 points, and the latency penalty stops at latency_penalty_max (50 points, the cost of
    # ~8% unsafe releases), so no amount of speed buys back an unsafe pipeline.
    w_unsafe: float = 600
    latency_penalty_per_10ms: float = 0.25
    latency_penalty_max: float = Field(default=50, ge=0)
    cost_penalty_per_10pct: float = 5


class ScenarioPack(CamelModel):
    id: str
    version: int = Field(ge=1)
    tickets: list[Ticket] = Field(min_length=1)
    scoring: ScoringConfig

    @model_validator(mode="after")
    def _unique_ids(self) -> Self:
        ids = [t.id for t in self.tickets]
        if dupes := sorted({i for i in ids if ids.count(i) > 1}):
            raise ValueError(f"duplicate ticket ids: {dupes}")
        return self


class PackSummary(CamelModel):
    """What clients may see about a pack: no ticket text and no labels."""

    id: str
    version: int
    ticket_count: int
    category_counts: dict[str, int] | None  # None for the hidden official pack
    scoring: ScoringConfig  # the mission targets and score weights are public (spec section 2)
