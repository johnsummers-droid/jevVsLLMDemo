"""Provider protocols. Runners call these; mocks (now) and real adapters (M6) implement them.

JevProvider follows assumption A1: a state plus typed questions in, one answer per question with
a value, probabilities and a confidence out. The adapters keep the real wire format contained.
"""

import random
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


class JevAnswer(CamelModel):
    question_id: str
    value: str
    probabilities: Distribution
    confidence: float = Field(ge=0, le=1)


class JevProvider(Protocol):
    async def ask(self, state: str, questions: list[JevQuestion],
                  call: ProviderCall) -> list[JevAnswer]: ...


@dataclass(frozen=True)
class LLMRequest:
    model: str  # tier: "small" | "large" (A2)
    temperature: float
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


class LLMProvider(Protocol):
    async def generate(self, request: LLMRequest, call: ProviderCall) -> LLMReply: ...
