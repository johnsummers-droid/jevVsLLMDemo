from pydantic import Field

from app.models.base import CamelModel


class NodeStats(CamelModel):
    node_id: str
    requests: int = Field(ge=0)  # times the node ran
    skipped: int = Field(ge=0)
    errors: int = Field(ge=0)
    provider_blocks: int = Field(default=0, ge=0)  # refused by the provider's safety filter
    escalations: int = Field(ge=0)
    avg_latency_ms: float = Field(ge=0)
    total_cost_usd: float = Field(ge=0)
    tokens_out: int = Field(ge=0)
    decisions: dict[str, int] = Field(default_factory=dict)  # fired-branch histogram


class RunMetrics(CamelModel):
    total: int = Field(ge=0)
    completed: int = Field(ge=0)
    automation_rate: float
    escalation_rate: float
    unsafe_release_rate: float
    dropped_rate: float
    p50_latency_ms: float
    p95_latency_ms: float
    cost_per_1k_usd: float
    decision_quality: float
    score: float = 0.0
