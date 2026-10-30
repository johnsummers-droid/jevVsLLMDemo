import os
from collections.abc import Iterator
from contextlib import ExitStack
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session, sessionmaker

from app.config import Settings, get_settings
from app.db.base import Base
from app.db.session import get_db, make_engine
from app.main import app


# Set to a PostgreSQL URL (postgresql+psycopg://...) to run the database tests against it; CI's
# postgres job does. Its public schema is wiped before every test that uses it.
TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL")


@pytest.fixture
def empty_db_url(tmp_path: Path) -> str:
    """An empty database: TEST_DATABASE_URL wiped clean, or else a fresh SQLite file."""
    if not TEST_DATABASE_URL:
        return f"sqlite:///{tmp_path / 'test.db'}"
    engine = make_engine(TEST_DATABASE_URL)
    with engine.begin() as conn:
        conn.execute(text("DROP SCHEMA public CASCADE"))
        conn.execute(text("CREATE SCHEMA public"))
    engine.dispose()
    return TEST_DATABASE_URL


@pytest.fixture
def db(empty_db_url: str) -> Iterator[Session]:
    """A session on an empty database; the migration test checks the tables match Alembic's."""
    engine = make_engine(empty_db_url)
    Base.metadata.create_all(engine)
    with sessionmaker(bind=engine, expire_on_commit=False)() as session:
        yield session
    engine.dispose()


@pytest.fixture
def settings() -> Settings:
    """Test secrets, independent of the environment and server/.env."""
    return Settings(_env_file=None, facilitator_code="open-sesame", token_secret="test-token-secret")


@pytest.fixture
def db_client(db: Session, settings: Settings) -> Iterator[TestClient]:
    """A TestClient whose endpoints use the `db` session and the `settings` fixture."""
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_settings] = lambda: settings
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.pop(get_db, None)
        app.dependency_overrides.pop(get_settings, None)


@pytest.fixture
def live_client(db_client: TestClient, db: Session) -> Iterator[TestClient]:
    """db_client, entered: websockets, background runs and portal calls share the app's event
    loop. Every request gets its own session on the test database, as in production (sockets
    authenticate and runs finish in worker threads, concurrently). Sockets opened through
    `live_client.sockets` are closed first, or the app would keep waiting for them."""
    from app.realtime.hub import hub
    from app.simulation.manager import runs

    factory = sessionmaker(bind=db.get_bind(), expire_on_commit=False)

    def own_session() -> Iterator[Session]:
        with factory() as session:
            yield session

    app.dependency_overrides[get_db] = own_session
    hub.reset()
    runs.reset()
    with db_client as entered, ExitStack() as sockets:
        entered.sockets = sockets  # type: ignore[attr-defined]
        yield entered
    hub.reset()
    runs.reset()
