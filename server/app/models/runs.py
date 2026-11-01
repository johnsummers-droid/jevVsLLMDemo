from datetime import datetime
from typing import Any, Literal

from pydantic import Field

from app.models.base import CamelModel
from app.models.metrics import RunMetrics
from app.models.results import NodeError

RunMode = Literal["practice", "official"]
# pending: computing ahead of the replay (U6). A reply from real providers can take seconds.
RunStatus = Literal["pending", "running", "completed", "stopped", "failed"]
Outcome = Literal["automated", "escalated", "blocked", "dropped", "failed"]


class RunConfig(CamelModel):
    mode: RunMode
    pack_id: str
    seed: int
    speed: float = Field(default=20.0, gt=0)  # simulated ms per wall-clock ms
    duration_s: float = Field(default=45, gt=0)  # wall-clock length of the arrival window
    traffic_spike: float = Field(default=1.0, ge=1, le=3)  # multiplies the ticket count
    injection_wave: bool = False  # appends another copy of every injection ticket
    max_concurrency: int = Field(default=32, ge=1)  # accepted; unused until M5


class NodeExecution(CamelModel):
    node_id: str
    node_type: str
    start_ms: float
    latency_ms: float = Field(ge=0)
    cost_usd: float = Field(default=0, ge=0)
    fired_branch: str | None = None
    decision: dict[str, Any] | None = None
    error: NodeError | None = None
    skipped: bool = False
    tokens_out: int = Field(default=0, ge=0)  # for NodeStats
    escalated: bool = False  # for NodeStats


class RequestTrace(CamelModel):
    request_id: str
    ticket_id: str
    arrival_ms: float
    steps: list[NodeExecution]
    outcome: Outcome
    released_unsafe: bool
    decision_correct: bool
    total_latency_ms: float = Field(ge=0)
    total_cost_usd: float = Field(ge=0)


class RunSummary(CamelModel):
    run_id: str
    team_id: str | None = None
    status: RunStatus
    config: RunConfig
    graph_version: int = 0
    warnings: list[str] = Field(default_factory=list)


class RunRecord(RunSummary):
    """A stored run (T20): what POST /api/teams/{id}/runs, POST /api/runs/{id}/stop and
    GET /api/teams/{id}/runs/latest return. metrics are set once the run has finished."""

    metrics: RunMetrics | None = None
    started_at: datetime
    finished_at: datetime | None = None


class LeaderboardRow(CamelModel):
    """One team's latest official run (T21). Finished runs rank first by score (ties: lower
    unsafe-release rate, then lower p95); stopped, still running and failed runs follow."""

    team_id: str
    team_name: str
    run_id: str
    status: RunStatus
    metrics: RunMetrics | None = None  # None until the run has finished, and for a failed run
    rank: int = Field(ge=1)


class OfficialRunResponse(CamelModel):
    """POST /api/sessions/{code}/runs: one seed and config for every team (decision Q7)."""

    seed: int
    runs: list[RunRecord]
