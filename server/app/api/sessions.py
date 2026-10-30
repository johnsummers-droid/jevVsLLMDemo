"""Workshop sessions and teams (T12, decisions P2 and P3)."""

from anyio import from_thread
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import auth
from app.api.deps import session_by_code, session_facilitator, token_secret
from app.catalog.default_graph import default_graph
from app.config import Settings, get_settings
from app.db import repo
from app.db.session import get_db
from app.db.tables import SessionRow, TeamRow
from app.models.sessions import (
    MAX_TEAMS_PER_SESSION,
    CreateSessionRequest,
    CreateSessionResponse,
    JoinTeamRequest,
    JoinTeamResponse,
    LockRequest,
    SessionDetail,
    TeamSummary,
)
from app.realtime.hub import hub

router = APIRouter(prefix="/api/sessions", tags=["sessions"])

_CODE_ATTEMPTS = 10


@router.post("", status_code=201)
def create_session(
    body: CreateSessionRequest,
    settings: Settings = Depends(get_settings),
    secret: str = Depends(token_secret),
    db: Session = Depends(get_db),
) -> CreateSessionResponse:
    if not settings.facilitator_code:
        raise HTTPException(status_code=503, detail="FACILITATOR_CODE is not configured")
    if not auth.same_secret(body.facilitator_code, settings.facilitator_code):
        raise HTTPException(status_code=401, detail="wrong facilitator code")
    token = auth.new_token()
    for _ in range(_CODE_ATTEMPTS):
        code = auth.new_session_code()
        if repo.get_session_by_code(db, code) is not None:
            continue
        try:
            repo.create_session(db, code, auth.hash_token(secret, token))
        except IntegrityError:  # taken by a concurrent request since the check
            db.rollback()
            continue
        return CreateSessionResponse(session_code=code, facilitator_token=token)
    raise HTTPException(status_code=503, detail="could not allocate a session code")


@router.post("/{code}/teams", status_code=201)
def join_team(
    body: JoinTeamRequest,
    session: SessionRow = Depends(session_by_code),
    secret: str = Depends(token_secret),
    db: Session = Depends(get_db),
) -> JoinTeamResponse:
    """Joins as a new team, or rejoins an existing one by name (P3: the old token is revoked)."""
    token = auth.new_token()
    token_hash = auth.hash_token(secret, token)
    team = repo.get_team_by_name(db, session.id, body.team_name)
    if team is None:
        if repo.count_teams(db, session.id) >= MAX_TEAMS_PER_SESSION:
            raise HTTPException(status_code=409, detail=f"session is full ({MAX_TEAMS_PER_SESSION} teams)")
        try:
            team = repo.create_team(db, session.id, body.team_name, token_hash, default_graph())
        except IntegrityError:  # the same name joined concurrently: rejoin it instead
            db.rollback()
            team = repo.get_team_by_name(db, session.id, body.team_name)
            if team is None:
                raise
            repo.replace_team_token(db, team, token_hash)
            from_thread.run_sync(hub.close_team, team.id)
    else:
        repo.replace_team_token(db, team, token_hash)
        from_thread.run_sync(hub.close_team, team.id)  # sockets on the revoked token (4403)
    return JoinTeamResponse(team_id=team.id, team_name=team.name, token=token)


def _detail(db: Session, session: SessionRow) -> SessionDetail:
    return SessionDetail(
        session_code=session.code,
        created_at=session.created_at,
        locked=session.locked,
        teams=[_summary(team, version, locked) for team, version, locked in repo.list_team_graphs(db, session.id)],
    )


def _summary(team: TeamRow, version: int, locked: bool) -> TeamSummary:
    return TeamSummary(team_id=team.id, name=team.name, joined_at=team.joined_at, graph_version=version, locked=locked)


@router.get("/{code}")
def get_session(session: SessionRow = Depends(session_facilitator), db: Session = Depends(get_db)) -> SessionDetail:
    return _detail(db, session)


@router.post("/{code}/lock")
def lock_session(
    body: LockRequest,
    session: SessionRow = Depends(session_facilitator),
    db: Session = Depends(get_db),
) -> SessionDetail:
    """Pencils down: locks (or unlocks) the session and every team graph in it, including the
    graphs of teams that join while it is locked (Q5)."""
    repo.set_session_locked(db, session.id, body.locked)
    detail = _detail(db, session)
    from_thread.run_sync(hub.announce_lock, session.id, [t.team_id for t in detail.teams], body.locked)
    return detail
