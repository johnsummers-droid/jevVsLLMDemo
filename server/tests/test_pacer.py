"""T19: the pacer replays a computed run on a wall-clock schedule (decision Q1). Fake clocks only."""

import asyncio
from functools import partial

from app.engine.pacer import Pacer
from app.metrics.aggregator import compute_metrics
from app.models import RunConfig
from app.models.events import EventBase, MetricsSnapshot, RequestCompleted, RunCompleted, RunStarted
from app.simulation.loader import load_pack
from app.simulation.reference_graphs import strong_graph
from app.simulation.runner import RunResult, run_simulation, stop_events
from app.simulation.scoring import with_score

PACK = load_pack("practice")
CONFIG = RunConfig(mode="practice", pack_id="practice", seed=3)
RESULT: RunResult = asyncio.run(run_simulation(strong_graph(), PACK, CONFIG, run_id="r1", team_id="t1"))


class FakeClock:
    """time.monotonic and asyncio.sleep stand-ins: sleeping moves the clock, instantly."""

    def __init__(self) -> None:
        self.now = 100.0
        self.sleeps: list[float] = []

    def __call__(self) -> float:
        return self.now

    async def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds
        await asyncio.sleep(0)


class GatedClock:
    """A clock that never moves: each event after time 0 waits for one released token."""

    def __init__(self) -> None:
        self.gate = asyncio.Semaphore(0)

    def __call__(self) -> float:
        return 0.0

    async def sleep(self, _seconds: float) -> None:
        await self.gate.acquire()


async def settle() -> None:
    for _ in range(20):
        await asyncio.sleep(0)


def pacer_for(delivered: list[EventBase], clock: FakeClock | GatedClock) -> Pacer:
    return Pacer(RESULT.events, CONFIG.speed, delivered.append,
                 stop_events=partial(stop_events, RESULT, PACK), clock=clock, sleep=clock.sleep)


def test_replays_every_event_in_order_on_the_simulated_schedule() -> None:
    async def scenario() -> tuple[list[EventBase], FakeClock]:
        delivered: list[EventBase] = []
        clock = FakeClock()
        pacer = pacer_for(delivered, clock)
        pacer.start()
        await pacer.wait()
        assert pacer.finished and not pacer.stopped
        assert not await pacer.stop()  # nothing left to stop
        return delivered, clock

    delivered, clock = asyncio.run(scenario())
    assert delivered == RESULT.events
    wall_s = RESULT.events[-1].sim_ms / CONFIG.speed / 1000
    assert abs(sum(clock.sleeps) - wall_s) < 1e-6
    distinct_times = len({e.sim_ms for e in RESULT.events if e.sim_ms > 0})
    assert len(clock.sleeps) == distinct_times  # events due together share one sleep


def test_stop_mid_run_closes_with_metrics_over_completed_requests() -> None:
    async def scenario() -> tuple[list[EventBase], Pacer]:
        delivered: list[EventBase] = []
        clock = GatedClock()
        pacer = pacer_for(delivered, clock)
        pacer.start()
        for _ in range(60):
            clock.gate.release()
        await settle()
        assert await pacer.stop()
        await pacer.wait()  # returns after a stop
        for _ in range(1000):
            clock.gate.release()
        await settle()
        return delivered, pacer

    delivered, pacer = asyncio.run(scenario())
    played, (snapshot, completed) = delivered[:-2], delivered[-2:]
    assert 0 < len(played) < len(RESULT.events) - 1
    assert played == RESULT.events[: len(played)]
    assert [e.seq for e in delivered] == list(range(len(delivered)))
    assert isinstance(snapshot, MetricsSnapshot) and isinstance(completed, RunCompleted)
    assert completed.status == "stopped" and completed.sim_ms == played[-1].sim_ms
    assert {e.run_id for e in delivered} == {"r1"} and {e.team_id for e in delivered} == {"t1"}
    done = {e.request_id for e in played if isinstance(e, RequestCompleted)}
    expected = with_score(compute_metrics([t for t in RESULT.traces if t.request_id in done],
                                          len(RESULT.traces)), PACK.scoring)
    assert completed.metrics == expected == snapshot.metrics
    assert pacer.delivered == delivered and pacer.finished


def test_stop_before_the_first_event_still_announces_the_run() -> None:
    async def scenario() -> list[EventBase]:
        delivered: list[EventBase] = []
        pacer = pacer_for(delivered, GatedClock())
        pacer.start()
        await pacer.stop()  # the task has not run a single step yet
        return delivered

    delivered = asyncio.run(scenario())
    assert [type(e) for e in delivered] == [RunStarted, MetricsSnapshot, RunCompleted]
    assert [e.seq for e in delivered] == [0, 1, 2]
    assert delivered[-1].status == "stopped" and delivered[-1].metrics.completed == 0


def test_a_waiter_sees_the_closing_events_of_a_stop() -> None:
    """Whoever waits for the replay (the run manager) must find run_completed(stopped) last."""
    async def scenario() -> EventBase:
        delivered: list[EventBase] = []
        clock = GatedClock()
        pacer = pacer_for(delivered, clock)
        pacer.start()
        clock.gate.release()
        await settle()

        async def waiter() -> EventBase:
            await pacer.wait()
            return pacer.delivered[-1]

        waiting = asyncio.create_task(waiter())
        await settle()
        await pacer.stop()
        return await waiting

    last = asyncio.run(scenario())
    assert isinstance(last, RunCompleted) and last.status == "stopped"
