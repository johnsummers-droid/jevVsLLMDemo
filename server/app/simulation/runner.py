"""Runs a graph against a pack in memory: schedule, execute, aggregate, emit (no DB or WS yet).

Each request is simulated on its own; the events of all requests are then merged by simulated
time (t5-plan.txt decision 1), metrics snapshots are inserted at most every SNAPSHOT_WALL_MS of
wall-clock time at the run's speed, and every event is numbered.
"""

from dataclasses import dataclass

from app.engine.envelope import RequestEnvelope, RunContext
from app.engine.events import EventSink, InMemorySink
from app.engine.executor import ExecutionPlan, execute_request
from app.metrics.aggregator import compute_metrics, compute_node_stats
from app.models import (
    Graph,
    NodeStats,
    RequestTrace,
    RunConfig,
    RunMetrics,
    RunStatus,
    ScenarioPack,
)
from app.models.events import (
    EventBase,
    MetricsSnapshot,
    RequestCompleted,
    RunCompleted,
    RunStarted,
)
from app.providers.base import JevProvider, LLMProvider
from app.providers.mock_jev import MockJevProvider
from app.providers.mock_llm import MockLLMProvider
from app.simulation.scoring import with_score
from app.simulation.traffic import schedule

SNAPSHOT_WALL_MS = 250  # metrics_snapshot at most 4 times per wall-clock second


@dataclass
class RunResult:
    run_id: str
    status: RunStatus
    traces: list[RequestTrace]
    metrics: RunMetrics
    node_stats: list[NodeStats]
    events: list[EventBase]


async def run_simulation(graph: Graph, pack: ScenarioPack, config: RunConfig, *,
                         run_id: str = "headless", team_id: str | None = None,
                         graph_version: int = 0, sink: EventSink | None = None,
                         jev: JevProvider | None = None,
                         llm: LLMProvider | None = None) -> RunResult:
    """Raises InvalidGraphError (from ExecutionPlan.build) if the graph has validation errors."""
    plan = ExecutionPlan.build(graph)
    jev = jev or MockJevProvider()
    llm = llm or MockLLMProvider()
    node_ids = [pn.id for pn in plan.nodes]

    traces: list[RequestTrace] = []
    timed: list[tuple[float, int, int, EventBase]] = []
    for index, arrival in enumerate(schedule(pack, config)):
        ctx = RunContext(run_seed=config.seed, jev=jev, llm=llm,
                         envelope=RequestEnvelope(request_id=arrival.request_id,
                                                  ticket=arrival.ticket))
        trace, events = await execute_request(plan, ctx, arrival.arrival_ms)
        traces.append(trace)
        timed += [(e.sim_ms, index, order, e) for order, e in enumerate(events)]
    timed.sort(key=lambda item: item[:3])

    metrics = with_score(compute_metrics(traces), pack.scoring)
    stream: list[EventBase] = [RunStarted(seq=0, sim_ms=0, config=config,
                                          graph_version=graph_version)]
    by_request = {t.request_id: t for t in traces}
    done: list[RequestTrace] = []
    interval = SNAPSHOT_WALL_MS * config.speed
    next_snapshot = interval
    unreported = False
    for sim_ms, _, _, event in timed:
        if sim_ms >= next_snapshot:
            if unreported:
                stream.append(_snapshot(done, len(traces), node_ids, pack, next_snapshot))
                unreported = False
            next_snapshot = (sim_ms // interval + 1) * interval
        stream.append(event)
        if isinstance(event, RequestCompleted):
            done.append(by_request[event.request_id])
            unreported = True
    end_ms = timed[-1][0] if timed else 0.0
    if unreported:
        stream.append(_snapshot(done, len(traces), node_ids, pack, end_ms))
    stream.append(RunCompleted(seq=0, sim_ms=end_ms, status="completed", metrics=metrics))

    numbered = [e.model_copy(update={"seq": seq, "run_id": run_id, "team_id": team_id})
                for seq, e in enumerate(stream)]
    sink = sink or InMemorySink()
    for event in numbered:
        sink.emit(event)
    return RunResult(run_id=run_id, status="completed", traces=traces, metrics=metrics,
                     node_stats=compute_node_stats(traces, node_ids), events=numbered)


def _snapshot(done: list[RequestTrace], total: int, node_ids: list[str], pack: ScenarioPack,
              sim_ms: float) -> MetricsSnapshot:
    return MetricsSnapshot(seq=0, sim_ms=sim_ms,
                           metrics=with_score(compute_metrics(done, total), pack.scoring),
                           node_stats=compute_node_stats(done, node_ids))


def stop_events(result: RunResult, pack: ScenarioPack, delivered: list[EventBase]) -> list[EventBase]:
    """The closing events of a run stopped after `delivered` (decision Q1): a metrics_snapshot over
    the requests that completed, then run_completed(status="stopped"), numbered on from there."""
    head = [] if delivered else result.events[:1]  # stopped before run_started went out
    last = delivered[-1] if delivered else result.events[0]
    done_ids = {e.request_id for e in delivered if isinstance(e, RequestCompleted)}
    done = [t for t in result.traces if t.request_id in done_ids]
    node_ids = [s.node_id for s in result.node_stats]
    snapshot = _snapshot(done, len(result.traces), node_ids, pack, last.sim_ms)
    completed = RunCompleted(seq=0, sim_ms=last.sim_ms, status="stopped", metrics=snapshot.metrics)
    ids = {"run_id": last.run_id, "team_id": last.team_id}
    first = last.seq + 1 if delivered else 1
    return [*head, *(e.model_copy(update={"seq": first + i, **ids}) for i, e in enumerate((snapshot, completed)))]
