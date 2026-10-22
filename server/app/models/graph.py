from datetime import datetime
from typing import Any, Literal

from pydantic import Field

from app.models.base import CamelModel

MAX_NODES = 40
MAX_EDGES = 80


class Position(CamelModel):
    x: float
    y: float


class GraphNode(CamelModel):
    id: str = Field(min_length=1)
    type: str
    position: Position
    params: dict[str, Any] = Field(default_factory=dict)  # checked against the definition's ParamSpecs
    label: str | None = None


class GraphEdge(CamelModel):
    id: str = Field(min_length=1)
    source: str
    source_port: str
    target: str
    target_port: str


class Graph(CamelModel):
    """Structural shape only; semantic rules (ids, ports, cycles) belong to the validator."""

    schema_version: Literal[1] = 1
    nodes: list[GraphNode] = Field(max_length=MAX_NODES)
    edges: list[GraphEdge] = Field(max_length=MAX_EDGES)


class StoredGraph(CamelModel):
    team_id: str
    version: int = Field(ge=0)
    locked: bool = False
    graph: Graph
    updated_at: datetime
