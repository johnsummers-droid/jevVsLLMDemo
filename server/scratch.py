"""Manual T1 checks. Run from server/: python scratch.py"""

from typing import get_args

from pydantic import ValidationError

from app.catalog.compat import type_compat
from app.models.graph import Graph
from app.models.ports import PortType

# camelCase in, camelCase out (sourcePort, schemaVersion)
g = Graph.model_validate({
    "nodes": [{"id": "n1", "type": "input", "position": {"x": 0, "y": 0}}],
    "edges": [{"id": "e1", "source": "n1", "sourcePort": "text",
               "target": "n2", "targetPort": "text"}]})
print(g.model_dump(by_alias=True))
print(g.edges[0].source_port)  # snake_case in Python

# unknown fields are rejected
try:
    Graph.model_validate({"nodes": [], "edges": [], "bogus": 1})
except ValidationError as e:
    print("rejected unknown field:", e.errors()[0]["loc"])

# graph size limit (max 40 nodes)
try:
    Graph.model_validate({
        "nodes": [{"id": f"n{i}", "type": "input", "position": {"x": 0, "y": 0}}
                  for i in range(41)],
        "edges": []})
except ValidationError as e:
    print("rejected 41 nodes:", e.errors()[0]["type"])

# port compatibility rules (plan1.txt section 3a)
print(get_args(PortType))
for source, target in [("text", "text"), ("text", "any"), ("any", "text"),
                       ("enum", "text"), ("score", "probability")]:
    print(f"{source} -> {target}: {type_compat(source, target)}")
