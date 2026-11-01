"""Official runs and the leaderboard (T21, decision Q7). Facilitator only.

POST /api/sessions/{code}/runs locks the session, stops any practice run, snapshots every team
graph and runs them all on the hidden official pack with one seed and one config. A graph with
validation errors gets a run recorded as failed, ranked last. 409 while an official run plays.
The leaderboard is pushed to the session's facilitator sockets as each team's run ends.
"""

import asyncio

import anyio
from functools import partial

from anyio import from_thread
from fastapi import APIRouter, Depends, FastAPI, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from sqlalchemy.orm import Session

from app.api.deps import session_facilitator
from app.db import repo
from app.db.base import new_id
from app.db.session import get_db, session_scope
from app.db.tables import SessionRow, TeamRow
from app.engine.validator import validate_graph
from app.models import (
    LeaderboardRow,
    OfficialRunResponse,
    RunMetrics,
    RunRecord,
    RunStatus,
    StoredGraph,
)
from app.models.events import LeaderboardUpdated
from app.realtime.hub import hub
from app.api.runs import _mark_running
from app.simulation.manager import (OfficialRunInProgress, PreparingRun, RunInProgress, compute,
                                    official_config, runs)
from app.simulation.scoring import Standing, rank

router = APIRouter(prefix="/api/sessions", tags=["official"])


def leaderboard(db: Session, session_id: str) -> list[LeaderboardRow]:
    names = {team.id: team.name for team in repo.list_teams(db, session_id)}
    return rank([
        Standing(row.team_id, names.get(row.team_id, "?"), row.id, row.status, repo.run_metrics(row))
        for row in repo.latest_official_runs(db, session_id)
    ])


def _publish_leaderboard(db: Session, session_id: str) -> None:
    """From a worker thread: compute the leaderboard and push it to the session's facilitators."""
    rows = leaderboard(db, session_id)
    from_thread.run_sync(hub.publish, session_id, LeaderboardUpdated(seq=0, sim_ms=0, rows=rows))


def _finish_official(app: FastAPI, session_id: str, run_id: str, status: RunStatus,
                     metrics: RunMetrics | None) -> None:
    with session_scope(app) as db:
        repo.finish_run(db, run_id, status, metrics)
        _publish_leaderboard(db, session_id)


def _publish_prepared(app: FastAPI, session_id: str) -> None:
    with session_scope(app) as db:
        _publish_leaderboard(db, session_id)


def _lock_and_snapshot(db: Session, session_id: str) -> list[tuple[TeamRow, StoredGraph]]:
    repo.set_session_locked(db, session_id, True)
    snapshot = []
    for team in repo.list_teams(db, session_id):
        stored = repo.get_graph(db, team.id)
        if stored is not None:
            snapshot.append((team, stored))
    return snapshot


def _record_failed(db: Session, team: TeamRow, stored: StoredGraph, config, run_id: str) -> RunRecord:
    repo.create_run(db, team, config, stored.graph, stored.version, run_id)
    repo.finish_run(db, run_id, "failed", None)
    db.expire_all()
    return repo.run_record(repo.get_run(db, run_id))


@router.post("/{code}/runs", status_code=201)
async def start_official_run(
    request: Request,
    session: SessionRow = Depends(session_facilitator),
    db: Session = Depends(get_db),
) -> OfficialRunResponse:
    try:
        runs.begin_official(session.id)
    except OfficialRunInProgress:
        raise HTTPException(status_code=409, detail="an official run is already in progress") from None
    reserved: list[str] = []
    try:
        snapshot = await run_in_threadpool(_lock_and_snapshot, db, session.id)
        hub.announce_lock(session.id, [team.id for team, _ in snapshot], True)

        # Free every team's slot: practice runs are stopped (they cannot restart: the session is locked).
        for team, _ in snapshot:
            while True:
                if (preparing := runs.preparing_for(team.id)) is not None:
                    await runs.stop(preparing.run_id)
                    continue
                if (active := runs.active(team.id)) is not None:
                    await runs.stop(active.run_id)
                    continue
                try:
                    runs.reserve(team.id)
                    break
                except RunInProgress:  # a practice run still being set up; let it start, then stop it
                    await asyncio.sleep(0.01)
            reserved.append(team.id)

        config = official_config()
        records: dict[str, RunRecord] = {}
        playable: list[tuple[TeamRow, StoredGraph, str]] = []
        for team, stored in snapshot:
            run_id = new_id()
            if validate_graph(stored.graph).ok:
                playable.append((team, stored, run_id))
            else:
                records[team.id] = await run_in_threadpool(_record_failed, db, team, stored, config, run_id)
                runs.release(team.id)
                reserved.remove(team.id)

        prepared = []
        for team, stored, run_id in playable:
            row = await run_in_threadpool(repo.create_run, db, team, config, stored.graph,
                                          stored.version, run_id, "pending")
            records[team.id] = repo.run_record(row)
            prepared.append(PreparingRun(
                run_id=run_id, team_id=team.id, session_id=session.id, config=config,
                graph_version=stored.version,
                finish=partial(_finish_official, request.app, session.id),
                compute=partial(compute, request.app, stored.graph, config, run_id=run_id,
                                team_id=team.id, graph_version=stored.version)))
    except BaseException:
        for team_id in reserved:  # setup failed before these runs were handed over
            runs.release(team_id)
        runs.end_official_if_idle(session.id)
        raise

    async def prepared_all() -> None:
        runs.end_official_if_idle(session.id)  # stays claimed while any run plays
        await anyio.to_thread.run_sync(_publish_prepared, request.app, session.id)

    if prepared:
        runs.prepare(prepared, partial(_mark_running, request.app), prepared_all)
    else:
        runs.end_official_if_idle(session.id)
    await run_in_threadpool(_publish_leaderboard, db, session.id)
    return OfficialRunResponse(seed=config.seed, runs=[records[team.id] for team, _ in snapshot])


@router.get("/{code}/leaderboard")
def get_leaderboard(session: SessionRow = Depends(session_facilitator),
                    db: Session = Depends(get_db)) -> list[LeaderboardRow]:
    return leaderboard(db, session.id)
