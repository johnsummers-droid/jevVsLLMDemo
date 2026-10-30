"""Event-order invariants on the recorded stream (plan1.txt section 5) and the event models."""

import asyncio
from collections import Counter

import pytest
from pydantic import TypeAdapter

from app.engine.events import InMemorySink
from app.models import Graph, RunConfig
from app.models.events import (
    ClientMessage,
    EdgeTransferred,
    EventBase,
    MetricsSnapshot,
    NodeCompleted,
    NodeStarted,
    RequestCompleted,
    RunCompleted,
    RunStarted,
    ServerEvent,
)
from app.simulation.loader import load_pack
from app.simulation.reference_graphs import REFERENCE_GRAPHS
from app.simulation.runner import SNAPSHOT_WALL_MS, RunResult, run_simulation


def simulate(graph: Graph, seed: int = 0, **config: object) -> tuple[RunResult, InMemorySink]:
    sink = InMemorySink()
    result = asyncio.run(run_simulation(
        graph, load_pack("official"),
        RunConfig(mode="practice", pack_id="official", seed=seed, **config),
        run_id="run-1", team_id="team-a", sink=sink))
    return result, sink


RUNS = {name: simulate(build())[0] for name, build in REFERENCE_GRAPHS.items()}


@pytest.fixture(params=list(RUNS))
def events(request: pytest.FixtureRequest) -> list[EventBase]:
    return RUNS[request.param].events


def test_sink_receives_the_returned_stream() -> None:
    result, sink = simulate(REFERENCE_GRAPHS["strong"]())
    assert sink.events == result.events


def test_seq_strictly_increases_and_time_never_goes_back(events: list[EventBase]) -> None:
    assert [e.seq for e in events] == list(range(len(events)))
    times = [e.sim_ms for e in events]
    assert times == sorted(times)
    assert all(e.run_id == "run-1" and e.team_id == "team-a" for e in events)


def test_run_started_first_and_run_completed_last(events: list[EventBase]) -> None:
    assert isinstance(events[0], RunStarted)
    assert isinstance(events[-1], RunCompleted) and events[-1].status == "completed"
    assert sum(isinstance(e, (RunStarted, RunCompleted)) for e in events) == 2


def test_node_started_before_it_finishes(events: list[EventBase]) -> None:
    started: set[tuple[str, str]] = set()
    finished: set[tuple[str, str]] = set()
    for e in events:
        key = (getattr(e, "request_id", ""), getattr(e, "node_id", ""))
        if isinstance(e, NodeStarted):
            assert key not in started
            started.add(key)
        elif e.type in ("node_completed", "node_failed"):
            assert key in started and key not in finished
            finished.add(key)
    assert started == finished


def test_edges_transfer_only_after_their_source_completed(events: list[EventBase]) -> None:
    completed: set[tuple[str, str]] = set()
    for e in events:
        if isinstance(e, NodeCompleted):
            completed.add((e.request_id, e.node_id))
        elif isinstance(e, EdgeTransferred):
            source = e.edge_id.split(".", 1)[0]
            assert (e.request_id, source) in completed, e


def test_one_request_completed_per_request_after_its_other_events(
        events: list[EventBase]) -> None:
    counts = Counter(e.request_id for e in events if isinstance(e, RequestCompleted))
    assert len(counts) == 30 and set(counts.values()) == {1}
    done: set[str] = set()
    for e in events:
        request_id = getattr(e, "request_id", None)
        if request_id is not None:
            assert request_id not in done, f"{e.type} after request_completed"
        if isinstance(e, RequestCompleted):
            done.add(e.request_id)


def test_skipped_nodes_emit_nothing() -> None:
    result = RUNS["default"]
    for trace in result.traces:
        skipped = {s.node_id for s in trace.steps if s.skipped}
        emitted = {getattr(e, "node_id", None) for e in result.events
                   if getattr(e, "request_id", None) == trace.request_id}
        assert not skipped & emitted


def test_metrics_snapshots_are_throttled_and_end_with_the_final_metrics() -> None:
    result = RUNS["strong"]
    snapshots = [e for e in result.events if isinstance(e, MetricsSnapshot)]
    assert snapshots
    interval = SNAPSHOT_WALL_MS * 20.0  # default speed
    gaps = [b.sim_ms - a.sim_ms for a, b in zip(snapshots, snapshots[1:], strict=False)]
    assert all(gap >= interval - 1e-6 for gap in gaps[:-1])  # the last one closes the run
    assert snapshots[-1].metrics == result.metrics
    assert result.events[-1].metrics == result.metrics


def test_event_union_round_trips() -> None:
    adapter = TypeAdapter(ServerEvent)
    for event in RUNS["strong"].events:
        wire = event.model_dump(by_alias=True)
        assert adapter.validate_python(wire) == event
    assert TypeAdapter(ClientMessage).validate_python({"type": "ping"}).type == "ping"
    sub = TypeAdapter(ClientMessage).validate_python({"type": "subscribe", "channels": ["t"]})
    assert sub.channels == ["t"]  # type: ignore[union-attr]
