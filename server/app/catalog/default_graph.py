"""The intentionally imperfect starter graph (plan1.txt 3c).

Weaknesses for teams to discover: router.route.low_confidence and policy.route.block are
unconnected, there is no safety check or knowledge lookup, and the LLM is the large tier
with max_tokens=512.

Regenerate the fixture after changing this file (from server/):
    .venv/bin/python -m app.catalog.default_graph > ../shared/fixtures/graphs/default.json
"""

from typing import Any

from app.catalog.registry import default_params, get_definition
from app.models import Graph, GraphEdge, GraphNode, Position

# (node id, node type, x[, y]) and (source, source port, target, target port)
NodeSpec = tuple[str, str, float] | tuple[str, str, float, float]
EdgeSpec = tuple[str, str, str, str]

_NODES: list[NodeSpec] = [
    ("customer_message", "customer_message", 0),
    ("router", "jev_intent_router", 280),
    ("llm", "llm_answer_generator", 560),
    ("policy", "policy_engine", 840),
    ("response", "customer_response", 1120),
]

_EDGES: list[EdgeSpec] = [
    ("customer_message", "text", "router", "text"),
    ("router", "route.billing", "llm", "text"),
    ("router", "route.technical_support", "llm", "text"),
    ("router", "route.bug_report", "llm", "text"),
    ("router", "route.feature_request", "llm", "text"),
    ("llm", "text", "policy", "text"),
    ("policy", "route.pass", "response", "text"),
]


def build_graph(node_specs: list[NodeSpec], edge_specs: list[EdgeSpec],
                params: dict[str, dict[str, Any]] | None = None) -> Graph:
    """A graph with every node on its default params, overridden per node id by `params`."""
    params = params or {}
    nodes = []
    for node_id, node_type, x, *y in node_specs:
        node_params = default_params(get_definition(node_type)) | params.get(node_id, {})
        nodes.append(GraphNode(id=node_id, type=node_type,
                               position=Position(x=x, y=y[0] if y else 0), params=node_params))
    edges = [
        GraphEdge(id=f"{src}.{src_port}->{dst}.{dst_port}", source=src, source_port=src_port,
                  target=dst, target_port=dst_port)
        for src, src_port, dst, dst_port in edge_specs
    ]
    return Graph(nodes=nodes, edges=edges)


def default_graph() -> Graph:
    return build_graph(_NODES, _EDGES)


if __name__ == "__main__":
    print(default_graph().model_dump_json(by_alias=True, indent=2))
