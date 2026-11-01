"""Provider protocols. Runners call these; mocks (now) and real adapters (M6) implement them.

JevProvider follows assumption A1: a state plus typed questions in, one answer per question with
a value, probabilities and a confidence out. The adapters keep the real wire format contained.
"""

import random
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Literal, Protocol, Self

from pydantic import Field, model_validator

from app.models import Distribution, Docs, Taint, Ticket
from app.models.base import CamelModel


@dataclass(frozen=True)
class ProviderCall:
    """Per-call context. Mocks use the ticket's labels and the rng; real adapters ignore both."""

    ticket: Ticket
    rng: random.Random
    taint: frozenset[Taint] = field(default_factory=frozenset)  # taint on the node's input


class JevQuestion(CamelModel):
    id: str  # "intent" | "safety"
    kind: Literal["choice", "boolean"]
    prompt: str
    options: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _check_options(self) -> Self:
        if self.kind == "choice" and not self.options:
            raise ValueError("a choice question needs options")
        return self


class CallMeasure(CamelModel):
    """A real call's measured numbers (U4). Replays repeat them, so reruns time and cost the same."""

    latency_ms: float = Field(ge=0)
    cost_usd: float = Field(ge=0)
    tokens_in: int = Field(ge=0)
    tokens_out: int = Field(ge=0)
    replayed: bool


class JevAnswer(CamelModel):
    question_id: str
    value: str
    probabilities: Distribution
    confidence: float = Field(ge=0, le=1)
    # None from the mock: the runner then samples latency and cost from the node's cost model.
    # Covers the whole request; every runner asks one question per request.
    measure: CallMeasure | None = None


class ProviderFailure(Exception):
    """A real provider call failed for good (U10). The runner turns it into a failed node."""

    def __init__(self, code: Literal["timeout", "provider_error", "rate_limited", "spend_cap"],
                 message: str, *, retryable: bool, latency_ms: float = 0) -> None:
        super().__init__(message)
        self.code, self.message, self.retryable = code, message, retryable
        self.latency_ms = latency_ms  # time spent before giving up, for the node_failed event


class JevProvider(Protocol):
    async def ask(self, state: str, questions: list[JevQuestion],
                  call: ProviderCall) -> list[JevAnswer]: ...


@dataclass(frozen=True)
class LLMRequest:
    model: str  # tier: "small" | "large" (A2)
    max_tokens: int
    prompt: str
    text: str
    context: Docs | None = None


@dataclass(frozen=True)
class LLMReply:
    text: str
    tokens_in: int
    tokens_out: int
    taint: frozenset[Taint]  # taint of the generated text (replaces the input's taint)
    measure: CallMeasure | None = None  # None from the mock (see JevAnswer)
    verdicts: Mapping[str, float] = field(default_factory=dict)  # judge question -> p(yes), live


class LLMProvider(Protocol):
    # Whose prices the runner bills at: "gemini" or "claude" (config.LLM_PRICES_PER_1K_USD).
    name: str

    async def generate(self, request: LLMRequest, call: ProviderCall) -> LLMReply: ...
