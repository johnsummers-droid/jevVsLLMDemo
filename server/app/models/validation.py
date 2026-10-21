from enum import StrEnum
from typing import Literal, Self

from pydantic import model_validator

from app.models.base import CamelModel

Severity = Literal["error", "warning"]


class IssueCode(StrEnum):
    # errors: block a run
    UNKNOWN_NODE_TYPE = "UNKNOWN_NODE_TYPE"
    UNKNOWN_PORT = "UNKNOWN_PORT"
    DUPLICATE_ID = "DUPLICATE_ID"
    DUPLICATE_EDGE = "DUPLICATE_EDGE"
    INCOMPATIBLE_PORTS = "INCOMPATIBLE_PORTS"
    ENUM_VALUES_MISMATCH = "ENUM_VALUES_MISMATCH"
    INPUT_FAN_IN_EXCEEDED = "INPUT_FAN_IN_EXCEEDED"
    FAN_OUT_EXCEEDED = "FAN_OUT_EXCEEDED"
    MISSING_REQUIRED_INPUT = "MISSING_REQUIRED_INPUT"
    CYCLE = "CYCLE"
    NO_SOURCE = "NO_SOURCE"
    MULTIPLE_SOURCES = "MULTIPLE_SOURCES"
    NO_SINK = "NO_SINK"
    INVALID_PARAM = "INVALID_PARAM"
    GATE_NEEDS_SIGNAL = "GATE_NEEDS_SIGNAL"
    GRAPH_TOO_LARGE = "GRAPH_TOO_LARGE"
    # warnings: shown on the canvas
    UNREACHABLE_NODE = "UNREACHABLE_NODE"
    DEAD_END = "DEAD_END"
    UNCONNECTED_BRANCH = "UNCONNECTED_BRANCH"
    NO_SAFETY_COVERAGE = "NO_SAFETY_COVERAGE"
    NO_HUMAN_FALLBACK = "NO_HUMAN_FALLBACK"
    ANY_SOURCE = "ANY_SOURCE"
    MULTI_INPUT_RACE = "MULTI_INPUT_RACE"


class ValidationIssue(CamelModel):
    code: IssueCode
    severity: Severity
    message: str
    node_id: str | None = None
    edge_id: str | None = None
    port_id: str | None = None


class ValidationReport(CamelModel):
    ok: bool  # True when there are no errors; warnings are allowed
    issues: list[ValidationIssue]

    @classmethod
    def from_issues(cls, issues: list[ValidationIssue]) -> "ValidationReport":
        return cls(ok=not any(i.severity == "error" for i in issues), issues=issues)

    @model_validator(mode="after")
    def _check_ok(self) -> Self:
        if self.ok == any(i.severity == "error" for i in self.issues):
            raise ValueError("ok must be True exactly when there are no error issues")
        return self
