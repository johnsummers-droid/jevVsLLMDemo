"""Practice runs (T20, decision Q6) and stopping a run.

POST /api/teams/{id}/runs runs the team's stored graph on the practice pack: 423 while the graph
is locked, 422 with the ValidationReport when it has errors, 409 while the team has a run in
progress, else 201 with the run, whose events then arrive over /api/ws.
"""

from functools import partial

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app import auth
from app.api.deps import bearer_token, token_secret
from app.api.teams import own_team
from app.db import repo
from app.db.base import new_id
from app.db.session import get_db, session_scope
from app.db.tables import RunRow, TeamRow
from app.engine.validator import validate_graph
from app.models import RunMetrics, RunRecord, RunStatus
from app.simulation.manager import RunInProgress, compute, practice_config, runs

router = APIRouter(tags=["runs"])

_UNAUTHORIZED = {"WWW-Authenticate": "Bearer"}


def _finish(app: FastAPI, run_id: str, status: RunStatus, metrics: RunMetrics | None) -> None:
    with session_scope(app) as db:
        repo.finish_run(db, run_id, status, metrics)


@router.post("/api/teams/{team_id}/runs", status_code=201, response_model=RunRecord)
async def start_practice_run(
    request: Request,
    team: TeamRow = Depends(own_team),
    db: Session = Depends(get_db),
) -> RunRecord | JSONResponse:
    stored = await run_in_threadpool(repo.get_graph, db, team.id)
    if stored is None:
        raise HTTPException(status_code=404, detail="team has no graph")
    if stored.locked:
        raise HTTPException(status_code=423, detail="graphs are locked")
    report = validate_graph(stored.graph)
    if not report.ok:
        return JSONResponse(status_code=422, content=report.model_dump(by_alias=True, mode="json"))
    try:
        runs.reserve(team.id)
    except RunInProgress:
        raise HTTPException(status_code=409, detail="a run is already in progress") from None
    try:
        config, run_id = practice_config(), new_id()
        result = await compute(stored.graph, config, run_id=run_id, team_id=team.id, graph_version=stored.version)
        row = await run_in_threadpool(repo.create_run, db, team, config, stored.graph, stored.version, run_id)
        record = repo.run_record(row)
    except BaseException:
        runs.release(team.id)
        raise
    runs.launch(team.id, team.session_id, result, config, partial(_finish, request.app))
    return record


@router.get("/api/teams/{team_id}/runs/latest")
def latest_run(team: TeamRow = Depends(own_team), db: Session = Depends(get_db)) -> RunRecord | None:
    """The team's most recent run, or null; live progress comes over /api/ws."""
    row = repo.latest_run(db, team.id)
    return repo.run_record(row) if row is not None else None


def _run_for_actor(db: Session, secret: str, token: str, run_id: str) -> RunRow:
    """The run, if the token is its team's or its session facilitator's: 401 for an unknown
    token, 404 for an unknown run, 403 for anyone else's run."""
    token_hash = auth.hash_token(secret, token)
    team = repo.get_team_by_token_hash(db, token_hash)
    session = None if team is not None else repo.get_session_by_facilitator_hash(db, token_hash)
    if team is None and session is None:
        raise HTTPException(status_code=401, detail="invalid or revoked token", headers=_UNAUTHORIZED)
    row = repo.get_run(db, run_id)
    if row is None:
        raise HTTPException(status_code=404, detail="no such run")
    if (team is not None and team.id != row.team_id) or (session is not None and session.id != row.session_id):
        raise HTTPException(status_code=403, detail="not your run")
    return row


def _current_record(db: Session, run_id: str) -> RunRecord:
    db.expire_all()  # the run's end was written through another session
    return repo.run_record(repo.get_run(db, run_id))


@router.post("/api/runs/{run_id}/stop")
async def stop_run(
    run_id: str,
    token: str = Depends(bearer_token),
    secret: str = Depends(token_secret),
    db: Session = Depends(get_db),
) -> RunRecord:
    """Stops the run (its team or the session's facilitator). A run that already ended is
    returned unchanged."""
    await run_in_threadpool(_run_for_actor, db, secret, token, run_id)
    await runs.stop(run_id)
    return await run_in_threadpool(_current_record, db, run_id)
