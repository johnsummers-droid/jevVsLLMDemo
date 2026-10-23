from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import catalog, graphs

app = FastAPI(title="Pipeline Simulator")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(catalog.router)
app.include_router(graphs.router)


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
