"""Auth dependencies: "Authorization: Bearer <token>" resolved to a team or a session's facilitator.

401 when the token is missing or matches nothing; 403 when it is a real token for something
else (another session's facilitator, or a team). 503 while TOKEN_SECRET is unset.
"""

from fastapi import Depends, Header, HTTPException
from sqlalchemy.orm import Session

from app import auth
from app.config import Settings, get_settings
from app.db import repo
from app.db.session import get_db
from app.db.tables import SessionRow, TeamRow

_UNAUTHORIZED = {"WWW-Authenticate": "Bearer"}


def token_secret(settings: Settings = Depends(get_settings)) -> str:
    if not settings.token_secret:
        raise HTTPException(status_code=503, detail="TOKEN_SECRET is not configured")
    return settings.token_secret


def bearer_token(authorization: str | None = Header(default=None)) -> str:
    scheme, _, token = (authorization or "").partition(" ")
    token = token.strip()
    if scheme.lower() != "bearer" or not token:
        raise HTTPException(status_code=401, detail="missing bearer token", headers=_UNAUTHORIZED)
    return token


def current_team(
    token: str = Depends(bearer_token),
    secret: str = Depends(token_secret),
    db: Session = Depends(get_db),
) -> TeamRow:
    token_hash = auth.hash_token(secret, token)
    team = repo.get_team_by_token_hash(db, token_hash)
    if team is not None:
        return team
    if repo.get_session_by_facilitator_hash(db, token_hash) is not None:
        raise HTTPException(status_code=403, detail="not a team token")
    raise HTTPException(status_code=401, detail="invalid or revoked token", headers=_UNAUTHORIZED)


def session_by_code(code: str, db: Session = Depends(get_db)) -> SessionRow:
    session = repo.get_session_by_code(db, auth.normalize_code(code))
    if session is None:
        raise HTTPException(status_code=404, detail="no session with that code")
    return session


def session_facilitator(
    session: SessionRow = Depends(session_by_code),
    token: str = Depends(bearer_token),
    secret: str = Depends(token_secret),
    db: Session = Depends(get_db),
) -> SessionRow:
    """The session named by the path's {code}, provided the token is its facilitator token."""
    token_hash = auth.hash_token(secret, token)
    if auth.same_secret(token_hash, session.facilitator_token_hash):
        return session
    if (
        repo.get_session_by_facilitator_hash(db, token_hash) is not None
        or repo.get_team_by_token_hash(db, token_hash) is not None
    ):
        raise HTTPException(status_code=403, detail="not this session's facilitator")
    raise HTTPException(status_code=401, detail="invalid token", headers=_UNAUTHORIZED)
