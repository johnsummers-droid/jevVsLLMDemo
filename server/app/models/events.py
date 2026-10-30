"""WebSocket events (plan1.txt 2a). The executor and runner build them; M4's pacer and hub only
deliver them. seq increases strictly within a run; sim_ms is simulated time."""

from typing import Annotated, Any, Literal

from pydantic import Field

from app.models.base import CamelModel
from app.models.metrics import LeaderboardRow, NodeStats, RunMetrics
from app.models.results import NodeError
from app.models.runs import Outcome, RunConfig, RunStatus, RunSummary


class EventBase(CamelModel):
    run_id: str | None = None
    team_id: str | None = None
    seq: int = Field(ge=0)
    sim_ms: float = Field(ge=0)


class RunStarted(EventBase):
    type: Literal["run_started"] = "run_started"
    config: RunConfig
    graph_version: int = 0


class NodeStarted(EventBase):
    type: Literal["node_started"] = "node_started"
    request_id: str
    node_id: str


class NodeCompleted(EventBase):
    type: Literal["node_completed"] = "node_completed"
    request_id: str
    node_id: str
    latency_ms: float
    cost_usd: float
    fired_branch: str | None = None
    decision: dict[str, Any] | None = None
    tokens_out: int = 0
    escalated: bool = False


class NodeFailed(EventBase):
    type: Literal["node_failed"] = "node_failed"
    request_id: str
    node_id: str
    error: NodeError


class EdgeTransferred(EventBase):
    type: Literal["edge_transferred"] = "edge_transferred"
    request_id: str
    edge_id: str


class RequestCompleted(EventBase):
    type: Literal["request_completed"] = "request_completed"
    request_id: str
    outcome: Outcome
    released_unsafe: bool
    total_latency_ms: float


class MetricsSnapshot(EventBase):
    type: Literal["metrics_snapshot"] = "metrics_snapshot"
    metrics: RunMetrics
    node_stats: list[NodeStats]


class RunCompleted(EventBase):
    type: Literal["run_completed"] = "run_completed"
    status: RunStatus
    metrics: RunMetrics


class GraphLocked(EventBase):
    type: Literal["graph_locked"] = "graph_locked"
    locked: bool


class LeaderboardUpdated(EventBase):
    type: Literal["leaderboard_updated"] = "leaderboard_updated"
    rows: list[LeaderboardRow]


class StateSync(EventBase):
    type: Literal["state_sync"] = "state_sync"
    run: RunSummary | None = None
    metrics: RunMetrics | None = None
    node_stats: list[NodeStats] = Field(default_factory=list)
    locked: bool = False


ServerEvent = Annotated[
    RunStarted | NodeStarted | NodeCompleted | NodeFailed | EdgeTransferred | RequestCompleted
    | MetricsSnapshot | RunCompleted | GraphLocked | LeaderboardUpdated | StateSync,
    Field(discriminator="type"),
]


class Subscribe(CamelModel):
    type: Literal["subscribe"] = "subscribe"
    channels: list[str]


class Ping(CamelModel):
    type: Literal["ping"] = "ping"


ClientMessage = Annotated[Subscribe | Ping, Field(discriminator="type")]
