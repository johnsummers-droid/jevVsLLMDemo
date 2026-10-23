"""Structural and semantic graph validation (plan1.txt 3d).

Errors block a run; warnings are shown on the canvas. Checks keep going after an error so
the canvas can badge everything at once; later checks only look at the nodes and edges
that resolved cleanly, so one mistake does not cascade into many issues.
"""

from collections import defaultdict
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from app.catalog.compat import Compat, port_compat
from app.catalog.registry import REGISTRY, expand_outputs
from app.engine.planner import (
    branch_conditions,
    find_cycles,
    mutually_exclusive,
    reachable,
    topological_order,
)
from app.models import (
    Graph,
    GraphEdge,
    GraphNode,
    IssueCode,
    MultiEnumParam,
    NodeDefinition,
    Port,
    ValidationIssue,
    ValidationReport,
)
from app.models.graph import MAX_EDGES, MAX_NODES

# Node types with a special role in the semantic warnings.
LLM_CATEGORY = "llm"
SAFETY_CHECK = ("jev_safety_check", "route.safe")  # screened only when it exits here
POLICY_ENGINE = ("policy_engine", "route.pass")  # protects only when it exits here
HUMAN_REVIEW = "human_review_queue"

_ERRORS = {
    IssueCode.UNKNOWN_NODE_TYPE, IssueCode.UNKNOWN_PORT, IssueCode.DUPLICATE_ID,
    IssueCode.DUPLICATE_EDGE, IssueCode.INCOMPATIBLE_PORTS, IssueCode.ENUM_VALUES_MISMATCH,
    IssueCode.INPUT_FAN_IN_EXCEEDED, IssueCode.FAN_OUT_EXCEEDED,
    IssueCode.MISSING_REQUIRED_INPUT, IssueCode.CYCLE, IssueCode.NO_SOURCE,
    IssueCode.MULTIPLE_SOURCES, IssueCode.NO_SINK, IssueCode.INVALID_PARAM,
    IssueCode.GATE_NEEDS_SIGNAL, IssueCode.GRAPH_TOO_LARGE,
}


def _default_definitions() -> dict[str, NodeDefinition]:
    return {node_type: entry.definition for node_type, entry in REGISTRY.items()}


@dataclass
class _Resolved:
    """A node whose type is known, with its outputs expanded for its params."""

    node: GraphNode
    definition: NodeDefinition
    inputs: dict[str, Port]
    outputs: dict[str, Port]


@dataclass
class _Validator:
    graph: Graph
    definitions: Mapping[str, NodeDefinition]
    issues: list[ValidationIssue] = field(default_factory=list)
    nodes: dict[str, _Resolved] = field(default_factory=dict)
    wired: list[GraphEdge] = field(default_factory=list)  # both ports resolve
    edges: list[GraphEdge] = field(default_factory=list)  # wired and type-compatible
    unknown_type_ids: set[str] = field(default_factory=set)  # their edges are not checked

    def add(self, code: IssueCode, message: str, *, node_id: str | None = None,
            edge_id: str | None = None, port_id: str | None = None) -> None:
        self.issues.append(ValidationIssue(
            code=code, severity="error" if code in _ERRORS else "warning", message=message,
            node_id=node_id, edge_id=edge_id, port_id=port_id,
        ))

    def run(self) -> ValidationReport:
        self.check_nodes()
        self.check_edges()
        self.check_connections()
        self.check_sources_and_sinks()
        acyclic = self.check_cycles()
        self.check_reachability()
        self.check_safety_coverage()
        self.check_human_fallback()
        if acyclic:
            self.check_multi_input_races()
        return ValidationReport.from_issues(self.issues)

    # --- errors ----------------------------------------------------------------

    def check_nodes(self) -> None:
        seen: set[str] = set()
        for node in self.graph.nodes:
            if node.id in seen:
                self.add(IssueCode.DUPLICATE_ID, f"Another node already uses id {node.id!r}.",
                         node_id=node.id)
                continue
            seen.add(node.id)
            definition = self.definitions.get(node.type)
            if definition is None:
                self.unknown_type_ids.add(node.id)
                self.add(IssueCode.UNKNOWN_NODE_TYPE, f"Unknown node type {node.type!r}.",
                         node_id=node.id)
                continue
            params = self.check_params(node, definition)
            self.nodes[node.id] = _Resolved(
                node=node, definition=definition,
                inputs={p.id: p for p in definition.inputs},
                outputs={p.id: p for p in expand_outputs(definition, params)},
            )

    def check_params(self, node: GraphNode, definition: NodeDefinition) -> dict[str, Any]:
        """Report every bad param; return params that are safe to expand outputs with."""
        specs = {spec.key: spec for spec in definition.params}
        for key in node.params:
            if key not in specs:
                self.add(IssueCode.INVALID_PARAM, f"Unknown parameter {key!r}.",
                         node_id=node.id)
        params: dict[str, Any] = {}
        for key, spec in specs.items():
            if key not in node.params:
                continue
            try:
                params[key] = spec.check(node.params[key])
            except ValueError as exc:
                self.add(IssueCode.INVALID_PARAM, f"Invalid parameter: {exc}", node_id=node.id)
                # A broken branch selection still lets every option's port resolve, so the
                # edges on it are not reported as unknown ports on top of this error.
                if isinstance(spec, MultiEnumParam):
                    params[key] = spec.options
        return params

    def check_edges(self) -> None:
        seen_ids: set[str] = set()
        seen_links: dict[tuple[str, str, str, str], str] = {}
        for edge in self.graph.edges:
            if edge.id in seen_ids:
                self.add(IssueCode.DUPLICATE_ID, f"Another edge already uses id {edge.id!r}.",
                         edge_id=edge.id)
                continue
            seen_ids.add(edge.id)
            link = (edge.source, edge.source_port, edge.target, edge.target_port)
            if link in seen_links:
                self.add(IssueCode.DUPLICATE_EDGE,
                         f"Same connection as edge {seen_links[link]!r}.", edge_id=edge.id)
                continue
            seen_links[link] = edge.id
            if {edge.source, edge.target} & self.unknown_type_ids:
                continue
            source, target = self.nodes.get(edge.source), self.nodes.get(edge.target)
            if source is None or target is None:
                missing = edge.source if source is None else edge.target
                self.add(IssueCode.UNKNOWN_PORT, f"Edge refers to missing node {missing!r}.",
                         edge_id=edge.id)
                continue
            out_port = source.outputs.get(edge.source_port)
            in_port = target.inputs.get(edge.target_port)
            if out_port is None:
                self.add(IssueCode.UNKNOWN_PORT,
                         f"{source.definition.title} has no output {edge.source_port!r}.",
                         node_id=edge.source, edge_id=edge.id, port_id=edge.source_port)
            if in_port is None:
                self.add(IssueCode.UNKNOWN_PORT,
                         f"{target.definition.title} has no input {edge.target_port!r}.",
                         node_id=edge.target, edge_id=edge.id, port_id=edge.target_port)
            if out_port is None or in_port is None:
                continue
            self.wired.append(edge)
            compat, code = port_compat(out_port, in_port)
            if code is not None:
                self.add(code, _compat_message(code, out_port, in_port), node_id=edge.target,
                         edge_id=edge.id, port_id=edge.target_port)
            if compat is not Compat.BLOCKED:
                self.edges.append(edge)

    def check_connections(self) -> None:
        # Counts include incompatible edges: they are drawn, and already reported once.
        incoming: dict[tuple[str, str], list[GraphEdge]] = defaultdict(list)
        outgoing: dict[tuple[str, str], list[GraphEdge]] = defaultdict(list)
        for edge in self.wired:
            incoming[(edge.target, edge.target_port)].append(edge)
            outgoing[(edge.source, edge.source_port)].append(edge)
        for node_id, resolved in self.nodes.items():
            for port in resolved.inputs.values():
                count = len(incoming[(node_id, port.id)])
                if count > 1 and not port.multi:
                    self.add(IssueCode.INPUT_FAN_IN_EXCEEDED,
                             f"Input {port.label!r} accepts one connection, has {count}.",
                             node_id=node_id, port_id=port.id)
                if count == 0 and port.required:
                    self.add(IssueCode.MISSING_REQUIRED_INPUT,
                             f"Required input {port.label!r} is not connected.",
                             node_id=node_id, port_id=port.id)
            limit = resolved.definition.max_fan_out
            for port in resolved.outputs.values():
                count = len(outgoing[(node_id, port.id)])
                if count > limit:
                    self.add(IssueCode.FAN_OUT_EXCEEDED,
                             f"Output {port.label!r} has {count} connections; the limit is "
                             f"{limit}.", node_id=node_id, port_id=port.id)
            signals = resolved.definition.requires_one_of
            if signals and not any(incoming[(node_id, s)] for s in signals):
                labels = ", ".join(resolved.inputs[s].label for s in signals)
                self.add(IssueCode.GATE_NEEDS_SIGNAL,
                         f"Connect at least one of: {labels}.", node_id=node_id)

    def check_sources_and_sinks(self) -> None:
        sources = [n for n, r in self.nodes.items() if r.definition.is_source]
        if not sources:
            self.add(IssueCode.NO_SOURCE, "Add a customer message node: the pipeline has no "
                     "entry point.")
        elif len(sources) > 1:
            for node_id in sources:
                self.add(IssueCode.MULTIPLE_SOURCES, "Only one entry point is allowed.",
                         node_id=node_id)
        if not any(r.definition.is_sink for r in self.nodes.values()):
            self.add(IssueCode.NO_SINK, "Add a customer response node: nothing reaches the "
                     "customer.")

    def check_cycles(self) -> bool:
        cycles = find_cycles(list(self.nodes), self.edges)
        cycle_of = {node: cycle for cycle in cycles for node in cycle}
        for edge in self.edges:
            if edge.target in cycle_of.get(edge.source, ()):
                path = ", ".join(cycle_of[edge.source])
                self.add(IssueCode.CYCLE, f"This connection is part of a loop between: {path}.",
                         node_id=edge.source, edge_id=edge.id)
        return not cycles

    # --- warnings --------------------------------------------------------------

    def _successors(self) -> dict[str, list[str]]:
        succ: dict[str, list[str]] = {n: [] for n in self.nodes}
        for edge in self.edges:
            succ[edge.source].append(edge.target)
        return succ

    def _sources(self) -> list[str]:
        return [n for n, r in self.nodes.items() if r.definition.is_source]

    def check_reachability(self) -> None:
        succ = self._successors()
        sources = self._sources()
        if sources:
            live = reachable(sources, succ)
            for node_id in self.nodes:
                if node_id not in live:
                    self.add(IssueCode.UNREACHABLE_NODE,
                             "No request can reach this node from the customer message.",
                             node_id=node_id)
        sinks = [n for n, r in self.nodes.items() if r.definition.is_sink]
        if sinks:
            pred: dict[str, list[str]] = {n: [] for n in self.nodes}
            for edge in self.edges:
                pred[edge.target].append(edge.source)
            delivers = reachable(sinks, pred)
            for node_id in self.nodes:
                if node_id not in delivers:
                    self.add(IssueCode.DEAD_END,
                             "Nothing from this node can reach a customer response.",
                             node_id=node_id)
        wired = {(e.source, e.source_port) for e in self.edges}
        for node_id, resolved in self.nodes.items():
            for port in resolved.outputs.values():
                if port.branch and (node_id, port.id) not in wired:
                    self.add(IssueCode.UNCONNECTED_BRANCH,
                             f"Requests on branch {port.label!r} will be dropped.",
                             node_id=node_id, port_id=port.id)

    def check_safety_coverage(self) -> None:
        """Warn per LLM that some source->sink path reaches unprotected.

        Search state: (node, screened, unprotected_llm). "screened" means the path left a
        safety check through route.safe; "unprotected_llm" is the first LLM passed while not
        screened that no policy engine (via route.pass) has covered yet.
        """
        out_edges: dict[str, list[GraphEdge]] = defaultdict(list)
        for edge in self.edges:
            out_edges[edge.source].append(edge)
        flagged: list[str] = []
        start = [(s, False, None) for s in self._sources()]
        seen = set(start)
        todo = list(start)
        while todo:
            node_id, screened, pending = todo.pop()
            definition = self.nodes[node_id].definition
            if definition.category == LLM_CATEGORY and not screened and pending is None:
                pending = node_id
            if definition.is_sink and pending is not None and pending not in flagged:
                flagged.append(pending)
            for edge in out_edges[node_id]:
                port = (definition.type, edge.source_port)
                state = (
                    edge.target,
                    screened or port == SAFETY_CHECK,
                    None if port == POLICY_ENGINE else pending,
                )
                if state not in seen:
                    seen.add(state)
                    todo.append(state)
        order = list(self.nodes)
        for node_id in sorted(flagged, key=order.index):
            self.add(IssueCode.NO_SAFETY_COVERAGE,
                     "Some requests reach the customer through this LLM with no safety check "
                     "before it and no policy engine after it.", node_id=node_id)

    def check_human_fallback(self) -> None:
        sources = self._sources()
        if not sources:
            return
        live = reachable(sources, self._successors())
        if not any(self.nodes[n].definition.type == HUMAN_REVIEW for n in live):
            self.add(IssueCode.NO_HUMAN_FALLBACK,
                     "No request can reach human review; risky or uncertain cases have "
                     "nowhere to go.")

    def check_multi_input_races(self) -> None:
        order = topological_order(list(self.nodes), self.edges)
        conds = branch_conditions(
            order, self.edges,
            lambda node_id, port_id: self.nodes[node_id].outputs[port_id].branch,
        )
        incoming: dict[tuple[str, str], list[GraphEdge]] = defaultdict(list)
        for edge in self.edges:
            incoming[(edge.target, edge.target_port)].append(edge)
        for (node_id, port_id), edges in incoming.items():
            if len(edges) < 2 or not self.nodes[node_id].inputs[port_id].multi:
                continue
            racing = next(
                ((a, b) for i, a in enumerate(edges) for b in edges[i + 1:]
                 if not mutually_exclusive(conds[a.id], conds[b.id])),
                None,
            )
            if racing is not None:
                a, b = racing
                self.add(IssueCode.MULTI_INPUT_RACE,
                         f"Edges {a.id!r} and {b.id!r} can both deliver on the same request; "
                         "the first to arrive wins.", node_id=node_id, port_id=port_id)


def _compat_message(code: IssueCode, source: Port, target: Port) -> str:
    if code == IssueCode.ENUM_VALUES_MISMATCH:
        extra = sorted(set(source.enum_values or []) - set(target.enum_values or []))
        return f"{source.label!r} can produce values {target.label!r} does not accept: {extra}."
    if code == IssueCode.ANY_SOURCE:
        return f"{source.label!r} is untyped; check that {target.label!r} can use it."
    return f"Cannot connect {source.type} output {source.label!r} to {target.type} input " \
           f"{target.label!r}."


def validate_graph(
    graph: Graph, definitions: Mapping[str, NodeDefinition] | None = None
) -> ValidationReport:
    """Validate a parsed graph against the catalog (or the given definitions, for tests)."""
    if definitions is None:
        definitions = _default_definitions()
    return _Validator(graph, definitions).run()


def validate_payload(
    data: Any, definitions: Mapping[str, NodeDefinition] | None = None
) -> ValidationReport:
    """Validate untrusted JSON. Oversized graphs are reported before they are parsed.

    Raises pydantic.ValidationError when the payload is not graph-shaped at all.
    """
    if isinstance(data, dict):
        nodes, edges = data.get("nodes"), data.get("edges")
        too_large = []
        if isinstance(nodes, list) and len(nodes) > MAX_NODES:
            too_large.append(f"{len(nodes)} nodes (max {MAX_NODES})")
        if isinstance(edges, list) and len(edges) > MAX_EDGES:
            too_large.append(f"{len(edges)} edges (max {MAX_EDGES})")
        if too_large:
            return ValidationReport.from_issues([ValidationIssue(
                code=IssueCode.GRAPH_TOO_LARGE, severity="error",
                message=f"The graph is too large: {', '.join(too_large)}.",
            )])
    return validate_graph(Graph.model_validate(data), definitions)
