from fastapi import APIRouter

from app.catalog.registry import catalog
from app.models import NodeDefinition
from app.models.base import CamelModel

router = APIRouter(prefix="/api", tags=["catalog"])


class CatalogResponse(CamelModel):
    nodes: list[NodeDefinition]


@router.get("/catalog")
def get_catalog() -> CatalogResponse:
    return CatalogResponse(nodes=catalog())
