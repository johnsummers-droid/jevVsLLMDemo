from typing import Any

from fastapi import APIRouter, Body, HTTPException
from pydantic import ValidationError

from app.catalog.default_graph import default_graph
from app.engine.validator import validate_payload
from app.models import Graph, ValidationReport

router = APIRouter(prefix="/api/graphs", tags=["graphs"])


@router.get("/default")
def get_default_graph() -> Graph:
    return default_graph()


@router.post("/validate")
def validate(payload: Any = Body(...)) -> ValidationReport:
    """Stateless: validate a graph without storing it.

    The body is taken as raw JSON so an oversized graph comes back as a GRAPH_TOO_LARGE
    report instead of a 422. A body that is not graph-shaped at all is still a 422.
    """
    try:
        return validate_payload(payload)
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=exc.errors(include_url=False, include_context=False)) from None
