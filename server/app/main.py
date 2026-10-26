from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import catalog, graphs, sessions
from app.config import get_settings

settings = get_settings()
app = FastAPI(title="Pipeline Simulator")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_origin_regex=settings.allowed_origin_regex,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(catalog.router)
app.include_router(graphs.router)
app.include_router(sessions.router)


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
