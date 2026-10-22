import math
from typing import Any, Literal, Self

from pydantic import Field, model_validator

from app.models.base import CamelModel
from app.models.ports import PortType

Taint = Literal["injection", "pii", "policy_violation", "ungrounded", "misrouted"]


class PortValue(CamelModel):
    type: PortType
    value: Any
    taint: set[Taint] = Field(default_factory=set)


class Distribution(CamelModel):
    probs: dict[str, float] = Field(min_length=1)

    @model_validator(mode="after")
    def _check_probs(self) -> Self:
        if any(p < 0 for p in self.probs.values()):
            raise ValueError("probabilities must be non-negative")
        if not math.isclose(sum(self.probs.values()), 1.0, abs_tol=1e-6):
            raise ValueError("probabilities must sum to 1")
        return self
