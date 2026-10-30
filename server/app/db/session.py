"""Engine and request-scoped sessions. Synchronous SQLAlchemy (decision P5)."""

from collections.abc import Iterator
from contextlib import contextmanager
from functools import lru_cache
from typing import Any

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from app.config import get_settings


def make_engine(url: str) -> Engine:
    if not url.startswith("sqlite"):
        return create_engine(url, pool_pre_ping=True)
    # FastAPI runs sync endpoints in a thread pool, so connections cross threads.
    engine = create_engine(url, connect_args={"check_same_thread": False})

    @event.listens_for(engine, "connect")
    def _foreign_keys(dbapi_conn: Any, _record: Any) -> None:
        dbapi_conn.execute("PRAGMA foreign_keys=ON")

    return engine


@lru_cache
def get_engine() -> Engine:
    return make_engine(get_settings().database_url)


@lru_cache
def _session_factory() -> sessionmaker[Session]:
    return sessionmaker(bind=get_engine(), expire_on_commit=False)


def get_db() -> Iterator[Session]:
    """FastAPI dependency; tests override it with a session on a temporary database."""
    with _session_factory()() as db:
        yield db


@contextmanager
def session_scope(app: Any = None) -> Iterator[Session]:
    """A session outside a request (startup, a run finishing in the background). It goes through
    get_db, or the app's dependency override of it, so tests reach their own database."""
    provider = app.dependency_overrides.get(get_db, get_db) if app is not None else get_db
    provided = provider()
    if not isinstance(provided, Iterator):  # an override that returns a session directly
        yield provided
        return
    try:
        yield next(provided)
    finally:
        provided.close()
