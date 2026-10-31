"""Graph structure analysis shared by the validator and (T5) the executor.

Pure functions over node ids and edges; they know nothing about the catalog. The caller
says which output ports are branch ports.
"""

from collections import defaultdict
from collections.abc import Callable, Iterable

from app.models import GraphEdge

# Branch conditions map a branching node to the branch ports it may have fired:
# {"router": {"route.billing", "route.bug_report"}} means "router fired one of these".
BranchConditions = dict[str, frozenset[str]]
IsBranch = Callable[[str, str], bool]


class CycleError(ValueError):
    def __init__(self, cycles: list[list[str]]) -> None:
        super().__init__(f"graph has cycles: {cycles}")
        self.cycles = cycles


def _successors(node_ids: Iterable[str], edges: Iterable[GraphEdge]) -> dict[str, list[str]]:
    succ: dict[str, list[str]] = {n: [] for n in node_ids}
    for edge in edges:
        if edge.source in succ and edge.target in succ:
            succ[edge.source].append(edge.target)
    return succ


def find_cycles(node_ids: list[str], edges: list[GraphEdge]) -> list[list[str]]:
    """Strongly connected components that contain a cycle (size > 1, or a self-loop).

    Each component is listed in input order; components are ordered by their first node.
    """
    succ = _successors(node_ids, edges)
    order = {n: i for i, n in enumerate(node_ids)}
    index: dict[str, int] = {}
    low: dict[str, int] = {}
    stack: list[str] = []
    on_stack: set[str] = set()
    components: list[list[str]] = []

    # Iterative Tarjan, so a long chain cannot hit the recursion limit.
    for root in node_ids:
        if root in index:
            continue
        work = [(root, 0)]
        while work:
            node, i = work.pop()
            if i == 0:
                index[node] = low[node] = len(index)
                stack.append(node)
                on_stack.add(node)
            if i < len(succ[node]):
                work.append((node, i + 1))
                nxt = succ[node][i]
                if nxt not in index:
                    work.append((nxt, 0))
                elif nxt in on_stack:
                    low[node] = min(low[node], index[nxt])
                continue
            if low[node] == index[node]:
                component = []
                while True:
                    member = stack.pop()
                    on_stack.discard(member)
                    component.append(member)
                    if member == node:
                        break
                if len(component) > 1 or node in succ[node]:
                    components.append(sorted(component, key=order.__getitem__))
            if work:
                parent = work[-1][0]
                low[parent] = min(low[parent], low[node])
    return sorted(components, key=lambda c: order[c[0]])


def topological_order(node_ids: list[str], edges: list[GraphEdge]) -> list[str]:
    """Kahn's algorithm, ties broken by input order so the result is deterministic."""
    succ = _successors(node_ids, edges)
    indegree = {n: 0 for n in node_ids}
    for targets in succ.values():
        for t in targets:
            indegree[t] += 1
    position = {n: i for i, n in enumerate(node_ids)}
    ready = sorted((n for n, d in indegree.items() if d == 0), key=position.__getitem__)
    order: list[str] = []
    while ready:
        node = ready.pop(0)
        order.append(node)
        for t in succ[node]:
            indegree[t] -= 1
            if indegree[t] == 0:
                ready.append(t)
                ready.sort(key=position.__getitem__)
    if len(order) != len(node_ids):
        raise CycleError(find_cycles(node_ids, edges))
    return order


def reachable(starts: Iterable[str], succ: dict[str, list[str]]) -> set[str]:
    seen = set(starts)
    todo = list(seen)
    while todo:
        for nxt in succ.get(todo.pop(), []):
            if nxt not in seen:
                seen.add(nxt)
                todo.append(nxt)
    return seen


def branch_conditions(
    order: list[str], edges: list[GraphEdge], is_branch: IsBranch
) -> dict[str, BranchConditions]:
    """For each edge id: the branch conditions that hold on every request where it is live.

    A node runs when any incoming edge is live, so it keeps a branching node only when every
    incoming edge names it, with the union of their ports (four router routes merging into
    one node still exclude the router's low-confidence route). The result under-approximates:
    two edges are only reported exclusive when that is certain. Requires an acyclic graph
    (pass a topological order).
    """
    incoming: dict[str, list[GraphEdge]] = defaultdict(list)
    for edge in edges:
        incoming[edge.target].append(edge)
    edge_conds: dict[str, BranchConditions] = {}
    for node in order:
        sets = [edge_conds[e.id] for e in incoming[node] if e.id in edge_conds]
        node_conds: BranchConditions = {}
        if sets:
            for source in set(sets[0]).intersection(*sets[1:]):
                node_conds[source] = frozenset().union(*(c[source] for c in sets))
        for edge in edges:
            if edge.source != node:
                continue
            conds = dict(node_conds)
            if is_branch(edge.source, edge.source_port):
                conds[edge.source] = frozenset({edge.source_port})
            edge_conds[edge.id] = conds
    return edge_conds


def mutually_exclusive(a: BranchConditions, b: BranchConditions) -> bool:
    """True when a and b need disjoint branches of the same node (only one branch fires)."""
    return any(node in a and not a[node] & ports for node, ports in b.items())
