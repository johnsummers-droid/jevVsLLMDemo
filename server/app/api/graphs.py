from fastapi import APIRouter

from app.catalog.default_graph import default_graph
from app.models import Graph

router = APIRouter(prefix="/api/graphs", tags=["graphs"])


@router.get("/default")
def get_default_graph() -> Graph:
    return default_graph()
