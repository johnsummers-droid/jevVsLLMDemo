"""Payloads carried by json ports, named by Port.json_schema_ref (Distribution is in values.py)."""

from pydantic import Field

from app.models.base import CamelModel


class TicketMeta(CamelModel):
    channel: str
    language: str


class Doc(CamelModel):
    id: str
    title: str
    snippet: str
    intent: str  # the support intent the doc answers; the mock LLM uses it for grounding
    score: int = Field(ge=0)


class Docs(CamelModel):
    docs: list[Doc] = Field(default_factory=list)


class PolicyViolation(CamelModel):
    rule: str  # a rule name, "blocked_phrase" or "data_class:<kind>"
    match: str


class PolicyReport(CamelModel):
    passed: bool
    violations: list[PolicyViolation] = Field(default_factory=list)
