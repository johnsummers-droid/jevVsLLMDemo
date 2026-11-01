"""Runs in progress (T20, decisions Q1 and Q6): at most one per team, held in memory (D8).

A run is accepted at once and computed in full off the event loop in the background (U6), then
paced into the hub. When the replay ends, or is stopped, its final status and metrics are written
back through `finish`. Real calls can't be interrupted, so stopping a run that is still computing
ends it at once and throws its result away; the calls it made stay in the call store.
"""

import asyncio
import logging
import secrets

import anyio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from functools import partial
from typing import Any

from app.config import get_settings
from app.engine.pacer import Pacer
from app.models import Graph, RunConfig, RunMetrics, RunStatus
from app.providers.factory import call_store_for, close_provider, jev_provider, llm_provider
from app.models.events import RunCompleted, RunPreparing
from app.realtime.hub import hub
from app.simulation.loader import load_pack
from app.simulation.runner import RunResult, run_simulation, stop_events

logger = logging.getLogger(__name__)

# Wall-clock timing of runs: arrivals over 45 s at 20x simulated speed. Tests shorten them.
PRACTICE_TIMING: dict[str, float] = {"speed": 20.0, "duration_s": 45.0}
OFFICIAL_TIMING: dict[str, float] = {"speed": 20.0, "duration_s": 45.0}

# Blocking; runs in an anyio worker thread, so it may call back into the loop (anyio.from_thread).
Finish = Callable[[str, RunStatus, RunMetrics | None], None]


class RunInProgress(Exception):
    pass


class OfficialRunInProgress(Exception):
    pass


def new_seed() -> int:
    return secrets.randbelow(2**31)


def practice_config() -> RunConfig:
    """Q6: the practice pack with a seed the server picks."""
    return RunConfig(mode="practice", pack_id="practice", seed=new_seed(), **PRACTICE_TIMING)


def official_config() -> RunConfig:
    """Q7: the hidden official pack. Built once per official run: every team gets this config."""
    return RunConfig(mode="official", pack_id="official", seed=new_seed(), **OFFICIAL_TIMING)


async def compute(app: Any, graph: Graph, config: RunConfig, *, run_id: str, team_id: str,
                  graph_version: int) -> RunResult:
    """The whole run, computed in a worker thread so the event loop keeps serving (Q1)."""
    pack = load_pack(config.pack_id)
    settings = get_settings()
    live = "live" in (settings.jev_mode, settings.llm_mode)
    store = call_store_for(app) if live else None

    async def run_on_own_loop() -> RunResult:
        # Built and closed here: a live provider's HTTP connections belong to this event loop.
        jev, llm = jev_provider(settings, store), llm_provider(settings, store)
        try:
            return await run_simulation(
                graph, pack, config, run_id=run_id, team_id=team_id, graph_version=graph_version,
                jev=jev, llm=llm)
        finally:
            await close_provider(jev)
            await close_provider(llm)

    return await asyncio.to_thread(asyncio.run, run_on_own_loop())


@dataclass
class ActiveRun:
    run_id: str
    team_id: str
    pacer: Pacer
    done: asyncio.Task[None]


@dataclass
class PreparingRun:
    """A run accepted and recorded as pending, whose computation is still ahead of it."""

    run_id: str
    team_id: str
    session_id: str
    config: RunConfig
    graph_version: int
    compute: Callable[[], Awaitable[RunResult]]
    finish: Finish
    cancelled: bool = False
    task: asyncio.Task[None] | None = field(default=None, repr=False)


class RunManager:
    def __init__(self) -> None:
        self._by_team: dict[str, ActiveRun | None] = {}  # None: reserved while the run is set up
        self._official: dict[str, set[str]] = {}  # session id -> its official runs still playing
        self._preparing: dict[str, PreparingRun] = {}  # run id -> run

    def reserve(self, team_id: str) -> None:
        """Claims the team's single run slot; raises RunInProgress if it is taken."""
        if team_id in self._by_team:
            raise RunInProgress(team_id)
        self._by_team[team_id] = None

    def release(self, team_id: str) -> None:
        """Gives back a reservation that never became a run (setup failed)."""
        if team_id in self._by_team and self._by_team[team_id] is None:
            del self._by_team[team_id]

    def active(self, team_id: str) -> ActiveRun | None:
        return self._by_team.get(team_id)

    def begin_official(self, session_id: str) -> None:
        """Claims the session's official run; raises OfficialRunInProgress if one is playing."""
        if session_id in self._official:
            raise OfficialRunInProgress(session_id)
        self._official[session_id] = set()

    def end_official_if_idle(self, session_id: str) -> None:
        if not self._official.get(session_id, {""}):
            del self._official[session_id]

    def official_in_progress(self, session_id: str) -> bool:
        return session_id in self._official

    def prepare(self, prepared: list[PreparingRun], mark_running: Callable[[str], None],
                on_done: Callable[[], Awaitable[None]] | None = None) -> None:
        """Announces the runs and computes them in the background; they start playing together,
        once all are ready, so an official run stays a race. A run whose computation fails ends
        alone. The team slots are already reserved. `mark_running` blocks; it runs in a thread."""
        for run in prepared:
            self._preparing[run.run_id] = run
            hub.publish(run.session_id, RunPreparing(
                seq=0, sim_ms=0, run_id=run.run_id, team_id=run.team_id, config=run.config,
                graph_version=run.graph_version))
        task = asyncio.create_task(self._prepare_all(prepared, mark_running, on_done))
        for run in prepared:
            run.task = task

    async def _prepare_all(self, prepared: list[PreparingRun], mark_running: Callable[[str], None],
                           on_done: Callable[[], Awaitable[None]] | None) -> None:
        try:
            results = await asyncio.gather(*(run.compute() for run in prepared),
                                           return_exceptions=True)
            for run, result in zip(prepared, results, strict=True):
                if run.cancelled:
                    continue
                if isinstance(result, BaseException):
                    logger.error("run %s could not be computed", run.run_id, exc_info=result)
                    await self._end_unplayed(run, "failed")
                    continue
                await anyio.to_thread.run_sync(mark_running, run.run_id)
                if not run.cancelled:  # stopped while that was being written
                    self.launch(run.team_id, run.session_id, result, run.config, run.finish)
                    # It plays now, so stop() must find the pacer even while the others get ready.
                    self._preparing.pop(run.run_id, None)
        finally:
            for run in prepared:
                self._preparing.pop(run.run_id, None)
            if on_done is not None:
                await on_done()

    async def _end_unplayed(self, run: PreparingRun, status: RunStatus) -> None:
        run.cancelled = True
        hub.publish(run.session_id, RunCompleted(seq=1, sim_ms=0, run_id=run.run_id,
                                                 team_id=run.team_id, status=status))
        self.release(run.team_id)
        try:
            await anyio.to_thread.run_sync(run.finish, run.run_id, status, None)
        except Exception:
            logger.exception("could not record the end of run %s", run.run_id)

    def preparing_for(self, team_id: str) -> PreparingRun | None:
        return next((r for r in self._preparing.values()
                     if r.team_id == team_id and not r.cancelled), None)

    def launch(self, team_id: str, session_id: str, result: RunResult, config: RunConfig, finish: Finish) -> ActiveRun:
        pack = load_pack(config.pack_id)
        pacer = Pacer(result.events, config.speed, hub.publisher(session_id),
                      stop_events=partial(stop_events, result, pack))
        pacer.start()
        done = asyncio.create_task(self._finish_when_played(team_id, result.run_id, pacer, finish))
        run = ActiveRun(result.run_id, team_id, pacer, done)
        self._by_team[team_id] = run
        if config.mode == "official" and session_id in self._official:
            self._official[session_id].add(result.run_id)
        return run

    async def _finish_when_played(self, team_id: str, run_id: str, pacer: Pacer, finish: Finish) -> None:
        status: RunStatus = "failed"
        metrics: RunMetrics | None = None
        try:
            await pacer.wait()
            last = pacer.delivered[-1] if pacer.delivered else None
            if isinstance(last, RunCompleted):
                status, metrics = last.status, last.metrics
        except Exception:
            logger.exception("run %s failed while playing", run_id)
        finally:
            try:
                await anyio.to_thread.run_sync(finish, run_id, status, metrics)
            except Exception:
                logger.exception("could not record the end of run %s", run_id)
            self._by_team.pop(team_id, None)
            for session_id, playing in list(self._official.items()):
                if run_id in playing:
                    playing.discard(run_id)
                    self.end_official_if_idle(session_id)

    def find(self, run_id: str) -> ActiveRun | None:
        return next((r for r in self._by_team.values() if r is not None and r.run_id == run_id), None)

    async def stop(self, run_id: str) -> bool:
        """Stops a run that is playing and waits until its end is recorded; False if not playing."""
        preparing = self._preparing.get(run_id)
        if preparing is not None and not preparing.cancelled:
            await self._end_unplayed(preparing, "stopped")
            return True
        run = self.find(run_id)
        if run is None:
            return False
        await run.pacer.stop()
        await asyncio.shield(run.done)
        return True

    async def wait(self, run_id: str) -> None:
        """Returns once the run has finished and been recorded (tests, official runs)."""
        preparing = self._preparing.get(run_id)
        if preparing is not None and preparing.task is not None:
            await asyncio.shield(preparing.task)
        run = self.find(run_id)
        if run is not None:
            await asyncio.shield(run.done)

    async def shutdown(self) -> None:
        for preparing in list(self._preparing.values()):
            await self.stop(preparing.run_id)
            if preparing.task is not None:
                preparing.task.cancel()
        for run in [r for r in self._by_team.values() if r is not None]:
            await self.stop(run.run_id)

    def reset(self) -> None:
        """Tests only."""
        self._by_team.clear()
        self._official.clear()
        self._preparing.clear()


runs = RunManager()
