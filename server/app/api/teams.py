"""A team's own graph (T13). Last write wins per version: 409 stale, 423 locked (plan1.txt section 0).

Saving an invalid graph is allowed (P7); only its shape and size are checked, by the Graph model.
"""

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.api.deps import current_team
from app.catalog.default_graph import default_graph
from app.db import repo
from app.db.session import get_db
from app.db.tables import TeamRow
from app.models.graph import SaveGraphRequest, StoredGraph

router = APIRouter(prefix="/api/teams", tags=["teams"])


def own_team(team_id: str, team: TeamRow = Depends(current_team)) -> TeamRow:
    """The token's team, provided it is the team named in the path."""
    if team.id != team_id:
        raise HTTPException(status_code=403, detail="not your team")
    return team


def _current(db: Session, team_id: str) -> StoredGraph:
    stored = repo.get_graph(db, team_id)
    if stored is None:  # every team gets a graph when it is created
        raise HTTPException(status_code=404, detail="team has no graph")
    return stored


def _refused(db: Session, team_id: str) -> JSONResponse:
    """Why a conditional save wrote nothing: 423 when locked, else 409 with the current graph."""
    current = _current(db, team_id)
    if current.locked:
        raise HTTPException(status_code=423, detail="graph is locked")
    return JSONResponse(status_code=409, content=current.model_dump(by_alias=True, mode="json"))


@router.get("/{team_id}/graph")
def get_team_graph(team: TeamRow = Depends(own_team), db: Session = Depends(get_db)) -> StoredGraph:
    return _current(db, team.id)


@router.put("/{team_id}/graph")
def save_team_graph(
    body: SaveGraphRequest,
    team: TeamRow = Depends(own_team),
    db: Session = Depends(get_db),
) -> StoredGraph:
    stored = repo.save_graph(db, team.id, body.graph, expected_version=body.version)
    return stored if stored is not None else _refused(db, team.id)


@router.post("/{team_id}/graph/reset")
def reset_team_graph(team: TeamRow = Depends(own_team), db: Session = Depends(get_db)) -> StoredGraph:
    """Back to the default graph. No version check: resetting is meant to discard."""
    stored = repo.save_graph(db, team.id, default_graph())
    return stored if stored is not None else _refused(db, team.id)
