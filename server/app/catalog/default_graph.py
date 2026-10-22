"""The intentionally imperfect starter graph (plan1.txt 3c).

Weaknesses for teams to discover: router.route.low_confidence and policy.route.block are
unconnected, there is no safety check or knowledge lookup, and the LLM is the large tier
with max_tokens=512.

Regenerate the fixture after changing this file (from server/):
    .venv/bin/python -m app.catalog.default_graph > ../shared/fixtures/graphs/default.json
"""

from app.catalog.registry import default_params, get_definition
from app.models import Graph, GraphEdge, GraphNode, Position

_NODES = [
    ("customer_message", "customer_message", 0),
    ("router", "jev_intent_router", 280),
    ("llm", "llm_answer_generator", 560),
    ("policy", "policy_engine", 840),
    ("response", "customer_response", 1120),
]

_EDGES = [
    ("customer_message", "text", "router", "text"),
    ("router", "route.billing", "llm", "text"),
    ("router", "route.technical_support", "llm", "text"),
    ("router", "route.bug_report", "llm", "text"),
    ("router", "route.feature_request", "llm", "text"),
    ("llm", "text", "policy", "text"),
    ("policy", "route.pass", "response", "text"),
]


def default_graph() -> Graph:
    nodes = [
        GraphNode(id=node_id, type=node_type, position=Position(x=x, y=0),
                  params=default_params(get_definition(node_type)))
        for node_id, node_type, x in _NODES
    ]
    edges = [
        GraphEdge(id=f"{src}.{src_port}->{dst}.{dst_port}", source=src, source_port=src_port,
                  target=dst, target_port=dst_port)
        for src, src_port, dst, dst_port in _EDGES
    ]
    return Graph(nodes=nodes, edges=edges)


if __name__ == "__main__":
    print(default_graph().model_dump_json(by_alias=True, indent=2))
