import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.exc import SQLAlchemyError

from app.api import catalog, graphs, official, packs, runs as runs_api, sessions, teams, ws
from app.config import get_settings
from app.db import repo
from app.db.session import session_scope
from app.simulation.manager import runs

logger = logging.getLogger(__name__)
settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    # Live mode without its key, or before its provider exists, refuses to start (U2).
    if problems := get_settings().live_problems():
        raise RuntimeError("cannot start in live mode: " + "; ".join(problems))
    # Run state lives in memory (D8), so runs a restart cut off can never finish.
    try:
        with session_scope(app) as db:
            if failed := repo.fail_stale_runs(db):
                logger.warning("marked %d interrupted run(s) as failed", failed)
    except SQLAlchemyError:
        logger.exception("could not clean up interrupted runs (database not migrated?)")
    yield
    await runs.shutdown()  # runs still playing are recorded as stopped


app = FastAPI(title="Pipeline Simulator", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_origin_regex=settings.allowed_origin_regex,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(catalog.router)
app.include_router(graphs.router)
app.include_router(packs.router)
app.include_router(sessions.router)
app.include_router(teams.router)
app.include_router(runs_api.router)
app.include_router(official.router)
app.include_router(ws.router)


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
