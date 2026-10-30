"""WebSocket fan-out and the live view each (re)connecting client is synced from (Q3, Q4).

Everything here runs on the event loop and never awaits: publishing only queues events, and a
per-socket writer task sends them. One process holds all of it (D8).

Channels follow from the token: a team socket gets its own team's events; a facilitator socket
gets, for its session, the run lifecycle, metrics and leaderboard events of every team but never
the per-node firehose.
"""

import asyncio
from collections.abc import Callable
from dataclasses import dataclass, field

from app.models.events import (
    Closing,
    EventBase,
    GraphLocked,
    MetricsSnapshot,
    RunCompleted,
    RunStarted,
    StateSync,
)
from app.models.metrics import NodeStats, RunMetrics
from app.models.runs import RunSummary

FACILITATOR_EVENTS = frozenset({"run_started", "metrics_snapshot", "run_completed", "leaderboard_updated"})

# More than a whole run (about 1,800 events at spike 3x) plus its replay on reconnect.
QUEUE_LIMIT = 4096

CLOSE_SLOW = 1013  # "try again later": the client reconnects and resyncs
CLOSE_REVOKED = 4403  # the team rejoined elsewhere, so this socket's token is no longer valid
CLOSE_REASONS = {
    CLOSE_SLOW: "too slow to keep up; reconnect",
    CLOSE_REVOKED: "this team joined again with a new token",
}


@dataclass
class TeamView:
    """A team's current or last run, as a newly connected client must see it."""

    run: RunSummary | None = None
    metrics: RunMetrics | None = None
    node_stats: list[NodeStats] = field(default_factory=list)
    events: list[EventBase] = field(default_factory=list)  # while running: every event so far

    def apply(self, event: EventBase) -> None:
        if isinstance(event, RunStarted):
            self.run = RunSummary(run_id=event.run_id or "", team_id=event.team_id, status="running",
                                  config=event.config, graph_version=event.graph_version)
            self.metrics, self.node_stats, self.events = None, [], []
        if self.run is None or event.run_id != self.run.run_id:
            return  # not part of the current run (e.g. graph_locked)
        self.events.append(event)
        if isinstance(event, MetricsSnapshot):
            self.metrics, self.node_stats = event.metrics, event.node_stats
        elif isinstance(event, RunCompleted):
            self.run = self.run.model_copy(update={"status": event.status})
            self.metrics = event.metrics
            self.events = [event]  # a finished run is synced from its totals, not replayed


class Connection:
    """One authenticated socket: its channel and a bounded queue its writer task drains."""

    def __init__(self, session_id: str, team_id: str | None) -> None:
        self.session_id = session_id
        self.team_id = team_id  # None for a facilitator
        self.queue: asyncio.Queue[EventBase | None] = asyncio.Queue(QUEUE_LIMIT)
        self.close_code: int | None = None

    def send(self, event: EventBase) -> None:
        if self.close_code is not None:
            return
        try:
            self.queue.put_nowait(event)
        except asyncio.QueueFull:
            self.close(CLOSE_SLOW)  # never block a run for one slow reader

    def close(self, code: int) -> None:
        """Drops what is queued and ends the writer: it sends `closing` (the close frame itself may
        never reach the client, see models.events.Closing), then closes the socket with `code`."""
        if self.close_code is not None:
            return
        self.close_code = code
        while not self.queue.empty():
            self.queue.get_nowait()
        self.queue.put_nowait(Closing(seq=0, sim_ms=0, team_id=self.team_id, code=code,
                                      reason=CLOSE_REASONS.get(code, "")))
        self.queue.put_nowait(None)


class Hub:
    def __init__(self) -> None:
        self._teams: dict[str, set[Connection]] = {}
        self._facilitators: dict[str, set[Connection]] = {}
        self._views: dict[str, TeamView] = {}

    def view(self, team_id: str) -> TeamView:
        return self._views.setdefault(team_id, TeamView())

    def connect(self, conn: Connection, locked: bool) -> None:
        """Registers the socket and queues its state_sync first (plus, mid-run, the run so far)."""
        if conn.team_id is None:
            self._facilitators.setdefault(conn.session_id, set()).add(conn)
            conn.send(StateSync(seq=0, sim_ms=0, locked=locked))
            return
        self._teams.setdefault(conn.team_id, set()).add(conn)
        for event in self.sync_events(conn.team_id, locked):
            conn.send(event)

    def disconnect(self, conn: Connection) -> None:
        channel = self._facilitators if conn.team_id is None else self._teams
        key = conn.session_id if conn.team_id is None else conn.team_id
        channel.get(key, set()).discard(conn)

    def sync_events(self, team_id: str, locked: bool) -> list[EventBase]:
        """state_sync, then, while a run plays, every event after run_started (Q4). The client drops
        events whose seq is not above the state_sync's, so replaying is safe."""
        view = self._views.get(team_id)
        if view is None or view.run is None:
            return [StateSync(seq=0, sim_ms=0, team_id=team_id, locked=locked)]
        last = view.events[-1] if view.events else None
        running = view.run.status == "running"
        sync = StateSync(
            seq=0 if running or last is None else last.seq,
            sim_ms=0 if running or last is None else last.sim_ms,
            run_id=view.run.run_id, team_id=team_id, run=view.run,
            metrics=view.metrics, node_stats=view.node_stats, locked=locked,
        )
        return [sync, *view.events[1:]] if running else [sync]

    def publish(self, session_id: str, event: EventBase) -> None:
        """Delivers a team's event (event.team_id) to that team, and the run lifecycle and
        metrics to the session's facilitators. Session-wide events have no team_id."""
        if event.team_id is not None:
            self.view(event.team_id).apply(event)
            for conn in list(self._teams.get(event.team_id, ())):
                conn.send(event)
        if event.type in FACILITATOR_EVENTS:
            for conn in list(self._facilitators.get(session_id, ())):
                conn.send(event)

    def announce_lock(self, session_id: str, team_ids: list[str], locked: bool) -> None:
        """Pencils down or unlock (Q5): every team socket learns at once, no polling."""
        for team_id in team_ids:
            self.publish(session_id, GraphLocked(seq=0, sim_ms=0, team_id=team_id, locked=locked))

    def close_team(self, team_id: str, code: int = CLOSE_REVOKED) -> None:
        for conn in list(self._teams.get(team_id, ())):
            conn.close(code)

    def publisher(self, session_id: str) -> Callable[[EventBase], None]:
        """A pacer's deliver function for one session."""
        return lambda event: self.publish(session_id, event)

    def reset(self) -> None:
        """Tests only: forget every connection and view."""
        self.__init__()


hub = Hub()
