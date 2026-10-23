import pytest

from app.engine.planner import (
    CycleError,
    branch_conditions,
    find_cycles,
    mutually_exclusive,
    reachable,
    topological_order,
)
from app.models import GraphEdge


def _edges(*links: str) -> list[GraphEdge]:
    """"a.out>b.in" -> an edge from a's port "out" to b's port "in"."""
    edges = []
    for link in links:
        src, dst = link.split(">")
        (s, sp), (t, tp) = src.split(".", 1), dst.split(".", 1)
        edges.append(GraphEdge(id=link, source=s, source_port=sp, target=t, target_port=tp))
    return edges


def test_topological_order_is_deterministic() -> None:
    edges = _edges("a.x>c.x", "b.x>c.x", "c.x>d.x")
    assert topological_order(["d", "c", "b", "a"], edges) == ["b", "a", "c", "d"]
    assert topological_order(["a", "b", "c", "d"], edges) == ["a", "b", "c", "d"]


def test_topological_order_rejects_cycles() -> None:
    with pytest.raises(CycleError) as info:
        topological_order(["a", "b", "c"], _edges("a.x>b.x", "b.x>c.x", "c.x>b.x"))
    assert info.value.cycles == [["b", "c"]]


def test_find_cycles() -> None:
    assert find_cycles(["a", "b"], _edges("a.x>b.x")) == []
    assert find_cycles(["a"], _edges("a.x>a.y")) == [["a"]]
    edges = _edges("a.x>b.x", "b.x>a.x", "b.x>c.x", "c.x>d.x", "d.x>c.x", "d.x>e.x")
    assert find_cycles(["a", "b", "c", "d", "e"], edges) == [["a", "b"], ["c", "d"]]


def test_find_cycles_handles_long_chains() -> None:
    ids = [f"n{i}" for i in range(2000)]
    links = [f"{a}.x>{b}.x" for a, b in zip(ids, ids[1:], strict=False)]
    assert find_cycles(ids, _edges(*links)) == []
    assert find_cycles(ids, _edges(*links, f"{ids[-1]}.x>{ids[0]}.x")) == [ids]


def test_reachable() -> None:
    succ = {"a": ["b"], "b": ["c"], "c": [], "d": ["a"]}
    assert reachable(["a"], succ) == {"a", "b", "c"}


def _is_branch(node: str, port: str) -> bool:
    return port.startswith("route.")


def test_branch_conditions_on_a_router() -> None:
    edges = _edges("src.x>r.in", "r.route.a>x.in", "r.route.b>y.in", "x.out>m.in", "y.out>m.in",
                   "src.x>m.in")
    conds = branch_conditions(["src", "r", "x", "y", "m"], edges, _is_branch)
    assert conds["r.route.a>x.in"] == {("r", "route.a")}
    assert conds["x.out>m.in"] == {("r", "route.a")}
    assert conds["y.out>m.in"] == {("r", "route.b")}
    assert conds["src.x>m.in"] == frozenset()
    assert mutually_exclusive(conds["x.out>m.in"], conds["y.out>m.in"])
    assert not mutually_exclusive(conds["x.out>m.in"], conds["src.x>m.in"])


def test_merge_forgets_branch_conditions() -> None:
    # m runs on either branch, so whatever leaves m carries no condition.
    edges = _edges("r.route.a>m.in", "r.route.b>m.in", "m.out>z.in", "r.route.a>z.in")
    conds = branch_conditions(["r", "m", "z"], edges, _is_branch)
    assert conds["m.out>z.in"] == frozenset()
    assert not mutually_exclusive(conds["m.out>z.in"], conds["r.route.a>z.in"])


def test_nested_branches() -> None:
    edges = _edges("r.route.a>s.in", "s.route.p>x.in", "s.route.q>y.in", "r.route.b>z.in")
    conds = branch_conditions(["r", "s", "x", "y", "z"], edges, _is_branch)
    assert conds["s.route.p>x.in"] == {("r", "route.a"), ("s", "route.p")}
    assert mutually_exclusive(conds["s.route.p>x.in"], conds["s.route.q>y.in"])
    assert mutually_exclusive(conds["s.route.p>x.in"], conds["r.route.b>z.in"])
