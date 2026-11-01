"""Reference graphs for the debrief (T40).

The session's facilitator can view them at any time. A team can from the moment the session is
locked and every official run has ended, until it is unlocked; before that the list is empty and
a graph answers 403, whatever its name, so the answer doesn't reveal which names exist.
The web app's ?ref viewer is separate and bundles the same graphs (user decision 2026-11-01).
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import session_facilitator
from app.api.teams import own_team
from app.db import repo
from app.db.session import get_db
from app.db.tables import SessionRow, TeamRow
from app.models import Graph, ReferenceGraphInfo, ReferenceGraphList
from app.simulation.reference_graphs import REFERENCE_GRAPHS, REFERENCE_LABELS

router = APIRouter(tags=["reference"])

_UNFINISHED = ("pending", "running")


def _all_graphs() -> ReferenceGraphList:
    return ReferenceGraphList(available=True, graphs=[
        ReferenceGraphInfo(name=name, label=REFERENCE_LABELS[name]) for name in REFERENCE_GRAPHS
    ])


def _graph(name: str) -> Graph:
    builder = REFERENCE_GRAPHS.get(name)
    if builder is None:
        raise HTTPException(status_code=404, detail="no reference graph with that name")
    return builder()


def _revealed(db: Session, team: TeamRow) -> bool:
    session = db.get(SessionRow, team.session_id)
    if session is None or not session.locked:
        return False
    official = repo.latest_official_runs(db, team.session_id)
    return bool(official) and all(run.status not in _UNFINISHED for run in official)


@router.get("/api/sessions/{code}/reference-graphs")
def session_reference_graphs(_: SessionRow = Depends(session_facilitator)) -> ReferenceGraphList:
    return _all_graphs()


@router.get("/api/sessions/{code}/reference-graphs/{name}")
def session_reference_graph(name: str, _: SessionRow = Depends(session_facilitator)) -> Graph:
    return _graph(name)


@router.get("/api/teams/{team_id}/reference-graphs")
def team_reference_graphs(team: TeamRow = Depends(own_team), db: Session = Depends(get_db)) -> ReferenceGraphList:
    return _all_graphs() if _revealed(db, team) else ReferenceGraphList(available=False, graphs=[])


@router.get("/api/teams/{team_id}/reference-graphs/{name}")
def team_reference_graph(name: str, team: TeamRow = Depends(own_team), db: Session = Depends(get_db)) -> Graph:
    if not _revealed(db, team):
        raise HTTPException(status_code=403, detail="available after the official run")
    return _graph(name)
