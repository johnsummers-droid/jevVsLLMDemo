"""Queries. Write functions commit; callers pass the request's Session from get_db."""

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.db.base import utcnow
from app.db.tables import GraphRow, SessionRow, TeamRow
from app.models.graph import Graph, StoredGraph


def name_key(name: str) -> str:
    """Team names are unique per session ignoring case and surrounding spaces."""
    return name.strip().casefold()


def _graph_json(graph: Graph) -> dict:
    return graph.model_dump(by_alias=True, mode="json")


def create_session(db: Session, code: str, facilitator_token_hash: str) -> SessionRow:
    row = SessionRow(code=code, facilitator_token_hash=facilitator_token_hash)
    db.add(row)
    db.commit()
    return row


def get_session_by_code(db: Session, code: str) -> SessionRow | None:
    return db.scalar(select(SessionRow).where(SessionRow.code == code))


def create_team(db: Session, session_id: str, name: str, token_hash: str, graph: Graph) -> TeamRow:
    """Adds the team and its graph at version 0."""
    name = name.strip()
    team = TeamRow(session_id=session_id, name=name, name_key=name_key(name), token_hash=token_hash)
    db.add(team)
    db.flush()
    db.add(GraphRow(team_id=team.id, graph=_graph_json(graph)))
    db.commit()
    return team


def get_team_by_name(db: Session, session_id: str, name: str) -> TeamRow | None:
    return db.scalar(
        select(TeamRow).where(TeamRow.session_id == session_id, TeamRow.name_key == name_key(name))
    )


def get_team_by_token_hash(db: Session, token_hash: str) -> TeamRow | None:
    return db.scalar(select(TeamRow).where(TeamRow.token_hash == token_hash))


def list_teams(db: Session, session_id: str) -> list[TeamRow]:
    return list(db.scalars(select(TeamRow).where(TeamRow.session_id == session_id).order_by(TeamRow.joined_at)))


def replace_team_token(db: Session, team: TeamRow, token_hash: str) -> TeamRow:
    """Rejoin (decision P3): the new token replaces, and so revokes, the old one."""
    team.token_hash = token_hash
    team.joined_at = utcnow()
    db.commit()
    return team


def get_session_by_facilitator_hash(db: Session, token_hash: str) -> SessionRow | None:
    return db.scalar(select(SessionRow).where(SessionRow.facilitator_token_hash == token_hash))


def count_teams(db: Session, session_id: str) -> int:
    return db.scalar(select(func.count()).select_from(TeamRow).where(TeamRow.session_id == session_id)) or 0


def list_team_graphs(db: Session, session_id: str) -> list[tuple[TeamRow, int, bool]]:
    """Each team in join order with its graph's version and lock flag."""
    rows = db.execute(
        select(TeamRow, GraphRow.version, GraphRow.locked)
        .join(GraphRow, GraphRow.team_id == TeamRow.id)
        .where(TeamRow.session_id == session_id)
        .order_by(TeamRow.joined_at)
    )
    return [(team, version, locked) for team, version, locked in rows]


def get_graph(db: Session, team_id: str) -> StoredGraph | None:
    row = db.get(GraphRow, team_id)
    if row is None:
        return None
    return StoredGraph(
        team_id=row.team_id,
        version=row.version,
        locked=row.locked,
        graph=Graph.model_validate(row.graph),
        updated_at=row.updated_at,
    )


def save_graph(db: Session, team_id: str, graph: Graph) -> StoredGraph:
    """Stores the graph and bumps its version. Version and lock checks belong to the API (T13)."""
    row = db.get(GraphRow, team_id)
    if row is None:
        raise LookupError(team_id)
    row.graph = _graph_json(graph)
    row.version += 1
    row.updated_at = utcnow()
    db.commit()
    stored = get_graph(db, team_id)
    assert stored is not None
    return stored


def set_session_locked(db: Session, session_id: str, locked: bool) -> int:
    """Locks or unlocks every team graph in the session; returns how many changed."""
    team_ids = select(TeamRow.id).where(TeamRow.session_id == session_id)
    result = db.execute(
        update(GraphRow).where(GraphRow.team_id.in_(team_ids), GraphRow.locked != locked).values(locked=locked)
    )
    db.commit()
    return result.rowcount
