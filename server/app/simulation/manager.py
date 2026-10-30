"""Runs in progress (T20, decisions Q1 and Q6): at most one per team, held in memory (D8).

A run is computed in full off the event loop, recorded, then paced into the hub. When the
replay ends, or is stopped, its final status and metrics are written back through `finish`.
"""

import asyncio
import logging
import secrets

import anyio
from collections.abc import Callable
from dataclasses import dataclass
from functools import partial

from app.engine.pacer import Pacer
from app.models import Graph, RunConfig, RunMetrics, RunStatus
from app.models.events import RunCompleted
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


async def compute(graph: Graph, config: RunConfig, *, run_id: str, team_id: str, graph_version: int) -> RunResult:
    """The whole run, computed in a worker thread so the event loop keeps serving (Q1)."""
    pack = load_pack(config.pack_id)
    return await asyncio.to_thread(asyncio.run, run_simulation(
        graph, pack, config, run_id=run_id, team_id=team_id, graph_version=graph_version))


@dataclass
class ActiveRun:
    run_id: str
    team_id: str
    pacer: Pacer
    done: asyncio.Task[None]


class RunManager:
    def __init__(self) -> None:
        self._by_team: dict[str, ActiveRun | None] = {}  # None: reserved while the run is set up
        self._official: dict[str, set[str]] = {}  # session id -> its official runs still playing

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
        run = self.find(run_id)
        if run is None:
            return False
        await run.pacer.stop()
        await asyncio.shield(run.done)
        return True

    async def wait(self, run_id: str) -> None:
        """Returns once the run has finished and been recorded (tests, official runs)."""
        run = self.find(run_id)
        if run is not None:
            await asyncio.shield(run.done)

    async def shutdown(self) -> None:
        for run in [r for r in self._by_team.values() if r is not None]:
            await self.stop(run.run_id)

    def reset(self) -> None:
        """Tests only."""
        self._by_team.clear()
        self._official.clear()


runs = RunManager()
