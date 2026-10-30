from datetime import UTC
from pathlib import Path

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from app.catalog.default_graph import default_graph
from app.db import repo
from app.db.base import Base
from app.db.session import get_db
from app.db.session import make_engine
from app.db.tables import RunRow
from app.models.graph import Graph
from app.models.metrics import RunMetrics
from app.models.runs import RunConfig

SERVER = Path(__file__).resolve().parents[1]


def alembic_config(url: str) -> Config:
    config = Config(str(SERVER / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", url)
    return config


def test_upgrade_head_creates_tables_and_matches_models(empty_db_url: str) -> None:
    url = empty_db_url
    command.upgrade(alembic_config(url), "head")
    engine = make_engine(url)
    try:
        assert {"sessions", "teams", "graphs", "runs"} <= set(inspect(engine).get_table_names())
        with engine.connect() as conn:
            assert compare_metadata(MigrationContext.configure(conn), Base.metadata) == []
    finally:
        engine.dispose()


def test_downgrade_base_drops_tables(empty_db_url: str) -> None:
    url = empty_db_url
    config = alembic_config(url)
    command.upgrade(config, "head")
    command.downgrade(config, "base")
    engine = make_engine(url)
    try:
        assert set(inspect(engine).get_table_names()) == {"alembic_version"}
    finally:
        engine.dispose()


def test_downgrade_to_0001_drops_runs_and_session_lock(empty_db_url: str) -> None:
    config = alembic_config(empty_db_url)
    command.upgrade(config, "head")
    command.downgrade(config, "0001")
    engine = make_engine(empty_db_url)
    try:
        assert "runs" not in inspect(engine).get_table_names()
        assert "locked" not in {c["name"] for c in inspect(engine).get_columns("sessions")}
    finally:
        engine.dispose()


def test_0002_keeps_sessions_in_pencils_down_locked(empty_db_url: str) -> None:
    """A session whose every graph was locked under 0001 is locked as a session after 0002, and
    no rows are lost (SQLite batch mode once cascaded its table rebuild into teams and graphs)."""
    config = alembic_config(empty_db_url)
    command.upgrade(config, "0001")
    engine = make_engine(empty_db_url)
    now = "2026-10-30 12:00:00+00:00"
    try:
        with engine.begin() as conn:
            for sid, code, team_locks in [("s1", "AAA222", [True, True]), ("s2", "BBB333", [True, False]),
                                          ("s3", "CCC444", [])]:
                conn.execute(text("INSERT INTO sessions (id, code, facilitator_token_hash, created_at)"
                                  " VALUES (:sid, :code, 'h', :now)"), {"sid": sid, "code": code, "now": now})
                for i, locked in enumerate(team_locks):
                    params = {"tid": f"{sid}t{i}", "sid": sid, "locked": locked, "now": now}
                    conn.execute(text("INSERT INTO teams (id, session_id, name, name_key, token_hash, joined_at)"
                                      " VALUES (:tid, :sid, :tid, :tid, :tid, :now)"), params)
                    conn.execute(text("INSERT INTO graphs (team_id, version, locked, graph, updated_at)"
                                      " VALUES (:tid, 0, :locked, '{}', :now)"), params)
        command.upgrade(config, "head")
        with engine.connect() as conn:
            locked = dict(conn.exec_driver_sql("SELECT id, locked FROM sessions").all())
            counts = [conn.exec_driver_sql(f"SELECT count(*) FROM {t}").scalar() for t in ("teams", "graphs")]
        assert {k: bool(v) for k, v in locked.items()} == {"s1": True, "s2": False, "s3": False}
        assert counts == [4, 4]
        command.downgrade(config, "0001")
        with engine.connect() as conn:
            assert conn.exec_driver_sql("SELECT count(*) FROM teams").scalar() == 4
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
    assert repo.save_graph(db, "missing", smaller) is None


def test_save_graph_refuses_stale_version_and_locked_graph(db: Session) -> None:
    session, team = make_team(db)
    graph = default_graph()
    assert repo.save_graph(db, team.id, graph, expected_version=0).version == 1
    assert repo.save_graph(db, team.id, graph, expected_version=0) is None
    repo.set_session_locked(db, session.id, True)
    assert repo.save_graph(db, team.id, graph, expected_version=1) is None
    assert repo.save_graph(db, team.id, graph) is None
    assert repo.get_graph(db, team.id).version == 1


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


def test_lock_sets_the_session_flag_and_later_teams_join_locked(db: Session) -> None:
    session, red = make_team(db)
    repo.set_session_locked(db, session.id, True)
    db.refresh(session)
    assert session.locked
    blue = repo.create_team(db, session.id, "Blue", "t2", default_graph())
    assert repo.get_graph(db, blue.id).locked
    assert repo.save_graph(db, blue.id, default_graph()) is None
    repo.set_session_locked(db, session.id, False)
    db.refresh(session)
    assert not session.locked
    assert not repo.get_graph(db, blue.id).locked and not repo.get_graph(db, red.id).locked


def test_lock_works_on_a_session_without_teams(db: Session) -> None:
    session = repo.create_session(db, "ABC234", "f")
    assert repo.set_session_locked(db, session.id, True) == 0
    db.refresh(session)
    assert session.locked
    team = repo.create_team(db, session.id, "Late", "t1", default_graph())
    assert repo.get_graph(db, team.id).locked


def practice_config(seed: int = 7) -> RunConfig:
    return RunConfig(mode="practice", pack_id="practice", seed=seed)


def metrics(score: float = 1.0) -> RunMetrics:
    return RunMetrics(total=15, completed=15, automation_rate=0.5, escalation_rate=0.2, unsafe_release_rate=0.0,
                      dropped_rate=0.0, p50_latency_ms=300, p95_latency_ms=700, cost_per_1k_usd=90,
                      decision_quality=0.9, score=score)


def test_run_round_trip_and_finish_once(db: Session) -> None:
    _, team = make_team(db)
    graph = default_graph()
    run = repo.create_run(db, team, practice_config(), graph, graph_version=3)
    assert run.status == "running" and run.finished_at is None and run.metrics is None
    db.expire_all()
    row = repo.get_run(db, run.id)
    summary = repo.run_summary(row)
    assert summary.run_id == run.id and summary.team_id == team.id and summary.status == "running"
    assert summary.config == practice_config() and summary.graph_version == 3
    assert Graph.model_validate(row.graph) == graph
    assert row.started_at.tzinfo == UTC

    assert repo.finish_run(db, run.id, "completed", metrics())
    assert not repo.finish_run(db, run.id, "stopped", None)  # already finished
    db.expire_all()
    row = repo.get_run(db, run.id)
    assert row.status == "completed" and row.finished_at is not None
    assert repo.run_metrics(row) == metrics()
    assert repo.get_run(db, "missing") is None


def test_latest_run_and_latest_official_run_per_team(db: Session) -> None:
    session, red = make_team(db)
    blue = repo.create_team(db, session.id, "Blue", "t2", default_graph())
    graph = default_graph()
    assert repo.latest_run(db, red.id) is None
    official = RunConfig(mode="official", pack_id="official", seed=1)
    old = repo.create_run(db, red, official, graph, 0)
    practice = repo.create_run(db, red, practice_config(), graph, 0)
    new = repo.create_run(db, red, official, graph, 0)
    blue_run = repo.create_run(db, blue, official, graph, 0)
    for row, minute in [(old, 1), (practice, 2), (new, 3), (blue_run, 3)]:
        row.started_at = row.started_at.replace(year=2026, month=10, day=30, hour=12, minute=minute)
    db.commit()
    assert repo.latest_run(db, red.id).id == new.id
    assert {r.id for r in repo.latest_official_runs(db, session.id)} == {new.id, blue_run.id}
    other = repo.create_session(db, "XYZ789", "f")
    assert repo.latest_official_runs(db, other.id) == []


def test_fail_stale_runs_only_touches_unfinished_runs(db: Session) -> None:
    _, team = make_team(db)
    graph = default_graph()
    running = repo.create_run(db, team, practice_config(), graph, 0)
    done = repo.create_run(db, team, practice_config(), graph, 0)
    repo.finish_run(db, done.id, "completed", metrics())
    assert repo.fail_stale_runs(db) == 1
    db.expire_all()
    assert repo.get_run(db, running.id).status == "failed"
    assert repo.get_run(db, running.id).finished_at is not None
    assert repo.get_run(db, done.id).status == "completed"
    assert repo.fail_stale_runs(db) == 0


def test_deleting_a_session_cascades_to_runs(db: Session) -> None:
    session, team = make_team(db)
    run_id = repo.create_run(db, team, practice_config(), default_graph(), 0).id
    db.delete(session)
    db.commit()
    db.expire_all()
    assert db.get(RunRow, run_id) is None


def test_startup_marks_interrupted_runs_failed(db: Session) -> None:
    from fastapi.testclient import TestClient

    from app.main import app

    _, team = make_team(db)
    run = repo.create_run(db, team, practice_config(), default_graph(), 0)
    app.dependency_overrides[get_db] = lambda: db
    try:
        with TestClient(app):  # entering runs the lifespan
            pass
    finally:
        app.dependency_overrides.pop(get_db, None)
    db.expire_all()
    assert repo.get_run(db, run.id).status == "failed"


def test_startup_survives_an_unmigrated_database(tmp_path: Path) -> None:
    from fastapi.testclient import TestClient

    from app.main import app

    engine = make_engine(f"sqlite:///{tmp_path / 'empty.db'}")
    with sessionmaker(bind=engine)() as empty:
        app.dependency_overrides[get_db] = lambda: empty
        try:
            with TestClient(app) as client:
                assert client.get("/api/health").status_code == 200
        finally:
            app.dependency_overrides.pop(get_db, None)
    engine.dispose()
