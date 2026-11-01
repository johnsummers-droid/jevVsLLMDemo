"""WebSocket events (plan1.txt 2a). The executor and runner build them; M4's pacer and hub only
deliver them. seq increases strictly within a run; sim_ms is simulated time."""

from typing import Annotated, Any, Literal

from pydantic import Field

from app.models.base import CamelModel
from app.models.metrics import NodeStats, RunMetrics
from app.models.results import NodeError
from app.models.runs import LeaderboardRow, Outcome, RunConfig, RunStatus, RunSummary


class EventBase(CamelModel):
    run_id: str | None = None
    team_id: str | None = None
    seq: int = Field(ge=0)
    sim_ms: float = Field(ge=0)


class RunPreparing(EventBase):
    """The run was accepted and is computing; run_started follows, or run_completed if it fails
    or is stopped first (U6)."""

    type: Literal["run_preparing"] = "run_preparing"
    config: RunConfig
    graph_version: int = 0


class RunStarted(EventBase):
    type: Literal["run_started"] = "run_started"
    config: RunConfig
    graph_version: int = 0
    warnings: list[str] = Field(default_factory=list)  # e.g. the spend cap fell back to mocks (U10)


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
    # A failed call still took time and may have cost money (NodeStats counts both), so clients
    # can rebuild the per-node numbers from events alone.
    latency_ms: float = 0.0
    cost_usd: float = 0.0


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
    metrics: RunMetrics | None = None  # None: the run ended before it played (U6)


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


class Closing(EventBase):
    """Sent right before the server closes a socket, with the same code and reason. Render's
    proxy swallows WebSocket close frames (it answers them itself and keeps the client's
    connection open), so the client closes on this message instead of waiting for the frame."""

    type: Literal["closing"] = "closing"
    code: int
    reason: str = ""


class Pong(EventBase):
    """The answer to a client's ping. Browsers cannot see protocol-level pings, and Render's proxy
    keeps a connection open after the server has gone (see Closing), so the client sends a ping
    every 25 s and reconnects when no pong (or other event) arrives for about 40 s."""

    type: Literal["pong"] = "pong"


ServerEvent = Annotated[
    RunPreparing | RunStarted | NodeStarted | NodeCompleted | NodeFailed | EdgeTransferred | RequestCompleted
    | MetricsSnapshot | RunCompleted | GraphLocked | LeaderboardUpdated | StateSync | Closing | Pong,
    Field(discriminator="type"),
]


class Auth(CamelModel):
    """The first message on /api/ws (decision Q2): a team or facilitator token, never in the URL."""

    type: Literal["auth"] = "auth"
    token: str


class Subscribe(CamelModel):
    """Unused in M4: the channels follow from the token (Q3)."""

    type: Literal["subscribe"] = "subscribe"
    channels: list[str]


class Ping(CamelModel):
    """The client's heartbeat; answered with Pong."""

    type: Literal["ping"] = "ping"


ClientMessage = Annotated[Auth | Subscribe | Ping, Field(discriminator="type")]
