from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from app.db.base import Base
from app.db.session import get_db, make_engine
from app.main import app


@pytest.fixture
def db(tmp_path: Path) -> Iterator[Session]:
    """A session on a fresh SQLite file; the migration test checks the tables match Alembic's."""
    engine = make_engine(f"sqlite:///{tmp_path / 'test.db'}")
    Base.metadata.create_all(engine)
    with sessionmaker(bind=engine, expire_on_commit=False)() as session:
        yield session
    engine.dispose()


@pytest.fixture
def db_client(db: Session) -> Iterator[TestClient]:
    """A TestClient whose endpoints use the `db` session."""
    app.dependency_overrides[get_db] = lambda: db
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.pop(get_db, None)
