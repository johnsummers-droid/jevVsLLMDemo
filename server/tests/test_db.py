from datetime import UTC
from pathlib import Path

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from sqlalchemy import inspect
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.catalog.default_graph import default_graph
from app.db import repo
from app.db.base import Base
from app.db.session import make_engine
from app.models.graph import Graph

SERVER = Path(__file__).resolve().parents[1]


def alembic_config(url: str) -> Config:
    config = Config(str(SERVER / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", url)
    return config


def test_upgrade_head_creates_tables_and_matches_models(tmp_path: Path) -> None:
    url = f"sqlite:///{tmp_path / 'migrated.db'}"
    command.upgrade(alembic_config(url), "head")
    engine = make_engine(url)
    try:
        assert {"sessions", "teams", "graphs"} <= set(inspect(engine).get_table_names())
        with engine.connect() as conn:
            assert compare_metadata(MigrationContext.configure(conn), Base.metadata) == []
    finally:
        engine.dispose()


def test_downgrade_base_drops_tables(tmp_path: Path) -> None:
    url = f"sqlite:///{tmp_path / 'migrated.db'}"
    config = alembic_config(url)
    command.upgrade(config, "head")
    command.downgrade(config, "base")
    engine = make_engine(url)
    try:
        assert set(inspect(engine).get_table_names()) == {"alembic_version"}
    finally:
        engine.dispose()


def make_team(db: Session, name: str = "Red Team", token_hash: str = "t1"):
    session = repo.create_session(db, "ABC234", "f" * 64)
    return session, repo.create_team(db, session.id, name, token_hash, default_graph())


def test_session_round_trip(db: Session) -> None:
    created = repo.create_session(db, "ABC234", "f" * 64)
    found = repo.get_session_by_code(db, "ABC234")
    assert found is not None and found.id == created.id
    assert found.facilitator_token_hash == "f" * 64
    assert found.created_at.tzinfo == UTC
    assert repo.get_session_by_code(db, "ZZZ999") is None


def test_session_code_is_unique(db: Session) -> None:
    repo.create_session(db, "ABC234", "a")
    with pytest.raises(IntegrityError):
        repo.create_session(db, "ABC234", "b")


def test_team_starts_with_graph_at_version_0(db: Session) -> None:
    _, team = make_team(db, name="  Red Team ")
    assert team.name == "Red Team" and team.name_key == "red team"
    stored = repo.get_graph(db, team.id)
    assert stored is not None
    assert stored.version == 0 and not stored.locked
    assert stored.graph == default_graph()
    assert stored.updated_at.tzinfo == UTC


def test_team_lookup_by_name_ignores_case_and_by_token(db: Session) -> None:
    session, team = make_team(db)
    assert repo.get_team_by_name(db, session.id, " RED team").id == team.id
    assert repo.get_team_by_name(db, session.id, "Blue") is None
    assert repo.get_team_by_token_hash(db, "t1").id == team.id
    assert repo.list_teams(db, session.id) == [team]


def test_team_name_unique_per_session_ignoring_case(db: Session) -> None:
    session, _ = make_team(db)
    with pytest.raises(IntegrityError):
        repo.create_team(db, session.id, "red TEAM", "t2", default_graph())
    db.rollback()
    other = repo.create_session(db, "XYZ789", "f")
    repo.create_team(db, other.id, "Red Team", "t3", default_graph())  # fine in another session


def test_replace_token_revokes_old_one(db: Session) -> None:
    _, team = make_team(db)
    joined = team.joined_at
    repo.replace_team_token(db, team, "t2")
    assert repo.get_team_by_token_hash(db, "t1") is None
    assert repo.get_team_by_token_hash(db, "t2").id == team.id
    assert team.joined_at >= joined


def test_save_graph_bumps_version_and_round_trips(db: Session) -> None:
    _, team = make_team(db)
    graph = default_graph()
    smaller = Graph(nodes=graph.nodes[:2], edges=[])
    stored = repo.save_graph(db, team.id, smaller)
    assert stored.version == 1 and stored.graph == smaller
    db.expire_all()
    assert repo.get_graph(db, team.id) == stored
    with pytest.raises(LookupError):
        repo.save_graph(db, "missing", smaller)


def test_lock_applies_to_every_team_in_the_session_only(db: Session) -> None:
    session, red = make_team(db)
    blue = repo.create_team(db, session.id, "Blue", "t2", default_graph())
    other = repo.create_session(db, "XYZ789", "f")
    green = repo.create_team(db, other.id, "Green", "t3", default_graph())
    assert repo.set_session_locked(db, session.id, True) == 2
    assert repo.set_session_locked(db, session.id, True) == 0
    db.expire_all()
    assert repo.get_graph(db, red.id).locked and repo.get_graph(db, blue.id).locked
    assert not repo.get_graph(db, green.id).locked
    assert repo.set_session_locked(db, session.id, False) == 2


def test_deleting_a_session_cascades(db: Session) -> None:
    session, team = make_team(db)
    db.delete(session)
    db.commit()
    assert repo.get_graph(db, team.id) is None
