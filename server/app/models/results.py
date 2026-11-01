from typing import Any, Literal, Self

from pydantic import Field, model_validator

from app.models.base import CamelModel
from app.models.values import PortValue


class NodeError(CamelModel):
    code: Literal["timeout", "provider_error", "invalid_input", "rate_limited", "spend_cap"]
    message: str
    retryable: bool


class NodeResult(CamelModel):
    outputs: dict[str, PortValue] = Field(default_factory=dict)  # data outputs + the fired branch
    fired_branch: str | None = None
    latency_ms: float = Field(ge=0)
    cost_usd: float = Field(default=0, ge=0)
    tokens_in: int = Field(default=0, ge=0)
    tokens_out: int = Field(default=0, ge=0)
    decision: dict[str, Any] | None = None  # e.g. {"intent": "billing", "confidence": 0.82}
    escalated: bool = False
    cached: bool = False
    judged: bool = False  # a real reply whose content was checked (U9); see executor._classify
    error: NodeError | None = None

    @model_validator(mode="after")
    def _check_branch(self) -> Self:
        if self.fired_branch is not None and self.fired_branch not in self.outputs:
            raise ValueError(f"fired_branch {self.fired_branch!r} has no output value")
        return self
