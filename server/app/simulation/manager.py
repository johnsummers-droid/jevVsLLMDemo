"""Runs in progress (T20, decisions Q1 and Q6): at most one per team, held in memory (D8).

A run is computed in full off the event loop, recorded, then paced into the hub. When the
replay ends, or is stopped, its final status and metrics are written back through `finish`.
"""

import asyncio
import logging
import secrets
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

# Wall-clock timing of a practice run: arrivals over 45 s at 20x simulated speed. Tests shorten it.
PRACTICE_TIMING: dict[str, float] = {"speed": 20.0, "duration_s": 45.0}

Finish = Callable[[str, RunStatus, RunMetrics | None], None]  # blocking; runs in a worker thread


class RunInProgress(Exception):
    pass


def practice_config() -> RunConfig:
    """Q6: the practice pack with a seed the server picks."""
    return RunConfig(mode="practice", pack_id="practice", seed=secrets.randbelow(2**31), **PRACTICE_TIMING)


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

    def reserve(self, team_id: str) -> None:
        """Claims the team's single run slot; raises RunInProgress if it is taken."""
        if team_id in self._by_team:
            raise RunInProgress(team_id)
        self._by_team[team_id] = None

    def release(self, team_id: str) -> None:
        """Gives back a reservation that never became a run (setup failed)."""
        if team_id in self._by_team and self._by_team[team_id] is None:
            del self._by_team[team_id]

    def launch(self, team_id: str, session_id: str, result: RunResult, config: RunConfig, finish: Finish) -> ActiveRun:
        pack = load_pack(config.pack_id)
        pacer = Pacer(result.events, config.speed, hub.publisher(session_id),
                      stop_events=partial(stop_events, result, pack))
        pacer.start()
        done = asyncio.create_task(self._finish_when_played(team_id, result.run_id, pacer, finish))
        run = ActiveRun(result.run_id, team_id, pacer, done)
        self._by_team[team_id] = run
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
                await asyncio.to_thread(finish, run_id, status, metrics)
            except Exception:
                logger.exception("could not record the end of run %s", run_id)
            self._by_team.pop(team_id, None)

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


runs = RunManager()
