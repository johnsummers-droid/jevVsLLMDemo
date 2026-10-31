from datetime import datetime
from typing import Any, Literal, Self

from pydantic import Field, model_validator

from app.models.base import CamelModel

MAX_NODES = 40
MAX_EDGES = 80


class Position(CamelModel):
    x: float
    y: float


# Params removed from the catalog, per node type. They are dropped whenever a graph is parsed, so
# graphs saved before the removal (database rows, stale browser tabs, old fixtures) still load and
# validate. U11 (MVP step 2): temperature, which Gemini 3+ and Claude 5.5 should not get.
RETIRED_PARAMS: dict[str, frozenset[str]] = {
    "llm_answer_generator": frozenset({"temperature"}),
}


class GraphNode(CamelModel):
    id: str = Field(min_length=1)
    type: str
    position: Position
    params: dict[str, Any] = Field(default_factory=dict)  # checked against the definition's ParamSpecs
    label: str | None = None

    @model_validator(mode="after")
    def _drop_retired_params(self) -> Self:
        if retired := RETIRED_PARAMS.get(self.type):
            self.params = {k: v for k, v in self.params.items() if k not in retired}
        return self


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


class SaveGraphRequest(CamelModel):
    """PUT /api/teams/{id}/graph: `version` is the version the client last loaded."""

    version: int = Field(ge=0)
    graph: Graph
