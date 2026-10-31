import asyncio
from dataclasses import replace
from typing import Any

import pytest

from app.catalog.default_graph import build_graph, default_graph
from app.engine.envelope import make_context
from app.engine.executor import (
    ExecutionPlan,
    InvalidGraphError,
    _classify,
    _Live,
    _RequestState,
    execute_request,
)
from app.models import NodeError, NodeResult, PortValue, RequestTrace, Ticket
from app.models.events import EventBase, NodeStarted
from app.simulation.loader import load_pack
from app.simulation.reference_graphs import escalate_all_graph, strong_graph

TICKETS = {t.id: t for t in load_pack("official").tickets}
ROUTINE = TICKETS["o-01"]  # billing, no PII
INJECTION = TICKETS["o-27"]
AMBIGUOUS = TICKETS["o-19"]


def execute(graph_or_plan: Any, ticket: Ticket, seed: int = 0,
            arrival_ms: float = 100.0) -> tuple[RequestTrace, list[EventBase]]:
    plan = graph_or_plan if isinstance(graph_or_plan, ExecutionPlan) \
        else ExecutionPlan.build(graph_or_plan)
    return asyncio.run(execute_request(plan, make_context(ticket, run_seed=seed), arrival_ms))


def with_params(graph: Any, node_id: str, **params: Any) -> Any:
    for node in graph.nodes:
        if node.id == node_id:
            node.params |= params
    return graph


def step(trace: RequestTrace, node_id: str) -> Any:
    return next(s for s in trace.steps if s.node_id == node_id)


def bare_graph() -> Any:
    """The MVP graph without human review: low-confidence requests are dropped."""
    graph = default_graph()
    graph.nodes = [n for n in graph.nodes if n.id != "human"]
    graph.edges = [e for e in graph.edges if "human" not in (e.source, e.target)]
    return graph


def direct_graph() -> Any:
    return build_graph([("customer_message", "customer_message", 0),
                        ("response", "customer_response", 280)],
                       [("customer_message", "text", "response", "text")])


# --- plan ---------------------------------------------------------------------------------


def test_plan_refuses_graphs_with_errors() -> None:
    graph = default_graph()
    graph.edges.pop(0)  # router loses its required input
    with pytest.raises(InvalidGraphError) as exc:
        ExecutionPlan.build(graph)
    assert not exc.value.report.ok


def test_plan_is_topological_with_resolved_params() -> None:
    plan = ExecutionPlan.build(default_graph())
    assert [pn.id for pn in plan.nodes] == ["customer_message", "router", "llm", "human",
                                            "response"]
    assert plan.nodes[1].params["threshold"] == 0.5


# --- dead paths, inputs, timing --------------------------------------------------------------


def test_unfired_branch_skips_downstream_nodes_without_events() -> None:
    graph = with_params(bare_graph(), "router", threshold=1.0)  # always low confidence
    trace, events = execute(graph, ROUTINE)
    assert trace.outcome == "dropped" and not trace.decision_correct
    skipped = {s.node_id for s in trace.steps if s.skipped}
    assert skipped == {"llm", "response"}
    assert not [e for e in events if getattr(e, "node_id", None) in skipped]
    assert all(s.latency_ms == 0 and s.cost_usd == 0 for s in trace.steps if s.skipped)


def test_multi_input_takes_the_earliest_live_arrival() -> None:
    graph = build_graph(
        [("customer_message", "customer_message", 0), ("fast", "llm_answer_generator", 280),
         ("slow", "llm_answer_generator", 280, 200), ("response", "customer_response", 560)],
        [("customer_message", "text", "fast", "text"), ("customer_message", "text", "slow", "text"),
         ("slow", "text", "response", "text"), ("fast", "text", "response", "text")],
        {"fast": {"model": "small", "max_tokens": 64}, "slow": {"model": "large"}})
    trace, _ = execute(graph, ROUTINE)
    fast, slow, response = step(trace, "fast"), step(trace, "slow"), step(trace, "response")
    assert fast.start_ms + fast.latency_ms < slow.start_ms + slow.latency_ms
    assert response.start_ms == fast.start_ms + fast.latency_ms
    assert trace.total_latency_ms == pytest.approx(response.start_ms - 100.0)


def test_node_waits_for_its_slowest_used_input() -> None:
    # Diamond: message -> knowledge -> llm.context and message -> llm.text.
    graph = build_graph(
        [("customer_message", "customer_message", 0), ("knowledge", "knowledge_lookup", 200),
         ("llm", "llm_answer_generator", 400), ("response", "customer_response", 600)],
        [("customer_message", "text", "knowledge", "text"),
         ("customer_message", "text", "llm", "text"), ("knowledge", "docs", "llm", "context"),
         ("llm", "text", "response", "text")])
    trace, _ = execute(graph, TICKETS["o-13"])
    knowledge, llm = step(trace, "knowledge"), step(trace, "llm")
    assert knowledge.start_ms == 100.0
    assert llm.start_ms == pytest.approx(knowledge.start_ms + knowledge.latency_ms)
    assert trace.total_latency_ms == pytest.approx(llm.start_ms + llm.latency_ms - 100.0)
    assert trace.total_cost_usd == pytest.approx(sum(s.cost_usd for s in trace.steps))


def test_optional_input_without_a_value_is_left_out() -> None:
    # The knowledge branch of a router never fires for this ticket's intent, so llm runs
    # without context.
    graph = build_graph(
        [("customer_message", "customer_message", 0), ("router", "jev_intent_router", 200),
         ("knowledge", "knowledge_lookup", 400), ("llm", "llm_answer_generator", 600),
         ("response", "customer_response", 800)],
        [("customer_message", "text", "router", "text"),
         ("router", "route.feature_request", "knowledge", "text"),
         ("customer_message", "text", "llm", "text"), ("knowledge", "docs", "llm", "context"),
         ("llm", "text", "response", "text")],
        {"router": {"threshold": 0}})
    trace, _ = execute(graph, ROUTINE)
    assert step(trace, "router").fired_branch == "route.billing"
    assert step(trace, "knowledge").skipped and not step(trace, "llm").skipped
    assert trace.outcome == "automated"


# --- outcomes ----------------------------------------------------------------------------


def test_automated() -> None:
    trace, _ = execute(direct_graph(), ROUTINE)
    assert (trace.outcome, trace.released_unsafe, trace.decision_correct) == \
        ("automated", False, True)


def test_escalated() -> None:
    trace, _ = execute(escalate_all_graph(), ROUTINE)
    assert trace.outcome == "escalated"
    assert step(trace, "human").escalated
    assert not trace.decision_correct  # a routine ticket did not need a human
    assert trace.total_latency_ms > 60_000


def test_blocked() -> None:
    graph = build_graph(
        [("customer_message", "customer_message", 0), ("policy", "policy_engine", 280),
         ("response", "customer_response", 560)],
        [("customer_message", "text", "policy", "text"), ("policy", "route.pass", "response", "text")],
        {"policy": {"blocked_phrases": ["refund"]}})
    trace, _ = execute(graph, TICKETS["o-23"])
    assert (trace.outcome, trace.released_unsafe, trace.decision_correct) == \
        ("blocked", False, True)
    assert execute(graph, ROUTINE)[0].outcome == "automated"


def test_dropped_branch_is_not_blocked() -> None:
    graph = with_params(bare_graph(), "router", threshold=1.0)
    assert execute(graph, INJECTION)[0].outcome == "dropped"


def test_low_confidence_goes_to_human_review() -> None:
    graph = with_params(default_graph(), "router", threshold=1.0)
    trace, _ = execute(graph, ROUTINE)
    assert trace.outcome == "escalated"
    assert step(trace, "llm").skipped and not step(trace, "human").skipped


class FailingRunner:
    async def run(self, inputs: dict, params: dict, ctx: Any) -> NodeResult:
        return NodeResult(latency_ms=5, error=NodeError(code="timeout", message="slow",
                                                        retryable=True))


def test_failed_node_fails_the_request() -> None:
    plan = ExecutionPlan.build(default_graph())
    plan.nodes[2] = replace(plan.nodes[2], runner=FailingRunner())  # the LLM
    trace, events = execute(plan, ROUTINE)
    assert trace.outcome == "failed" and not trace.released_unsafe
    assert step(trace, "llm").error is not None
    assert step(trace, "human").skipped and step(trace, "response").skipped
    assert [e.type for e in events if getattr(e, "node_id", None) == "llm"] == \
        ["node_started", "node_failed"]


# --- released_unsafe and decision_correct truth table -------------------------------------------


def _state(delivered_taint: set | None = None, reviewed: bool = False, blocked: bool = False,
           failed: bool = False) -> _RequestState:
    state = _RequestState(end_ms=200, blocked=blocked, failed=failed)
    if delivered_taint is not None:
        state.delivered = _Live(value=PortValue(type="text", value="answer",
                                                taint=delivered_taint),
                                ready_ms=150, reviewed=reviewed)
    return state


@pytest.mark.parametrize(("ticket_id", "state", "expected"), [
    ("o-01", _state(set()), ("automated", False, True)),
    ("o-02", _state({"pii"}), ("automated", True, False)),
    ("o-27", _state(set()), ("automated", True, False)),  # must_block released automatically
    ("o-01", _state({"misrouted"}), ("automated", False, False)),
    ("o-13", _state({"ungrounded"}), ("automated", False, False)),
    ("o-19", _state(set()), ("automated", False, False)),  # must_escalate answered by a bot
    ("o-27", _state(set(), reviewed=True), ("escalated", False, True)),
    ("o-27", _state({"injection"}, reviewed=True), ("escalated", True, True)),  # reviewer missed
    ("o-01", _state(set(), reviewed=True), ("escalated", False, False)),
    ("o-23", _state(None, blocked=True), ("blocked", False, True)),
    ("o-01", _state(None, blocked=True), ("blocked", False, False)),
    ("o-27", _state(None), ("dropped", False, False)),
    ("o-27", _state({"injection"}, failed=True), ("failed", False, False)),
])
def test_outcome_truth_table(ticket_id: str, state: _RequestState, expected: tuple) -> None:
    trace = _classify("r", make_context(TICKETS[ticket_id]), 100.0, state)
    assert (trace.outcome, trace.released_unsafe, trace.decision_correct) == expected


def test_latency_counts_to_delivery_or_last_node() -> None:
    ctx = make_context(ROUTINE)
    assert _classify("r", ctx, 100.0, _state(set())).total_latency_ms == 50
    assert _classify("r", ctx, 100.0, _state(None)).total_latency_ms == 100


# --- determinism ----------------------------------------------------------------------------


def test_same_seed_same_trace() -> None:
    for ticket in TICKETS.values():
        assert execute(strong_graph(), ticket, seed=3) == execute(strong_graph(), ticket, seed=3)


def test_node_ids_do_not_change_results() -> None:
    original = strong_graph()
    renamed = original.model_copy(deep=True)
    mapping = {n.id: f"team7-{n.id}" for n in renamed.nodes}
    for node in renamed.nodes:
        node.id = mapping[node.id]
    for edge in renamed.edges:
        edge.source, edge.target = mapping[edge.source], mapping[edge.target]
    for ticket in TICKETS.values():
        a, b = execute(original, ticket)[0], execute(renamed, ticket)[0]
        assert (a.outcome, a.released_unsafe, a.total_latency_ms, a.total_cost_usd) == \
            (b.outcome, b.released_unsafe, b.total_latency_ms, b.total_cost_usd)


def test_params_change_results() -> None:
    hot = with_params(strong_graph(), "llm", max_tokens=300)
    latencies = [execute(strong_graph(), t)[0].total_latency_ms for t in TICKETS.values()]
    hot_latencies = [execute(hot, t)[0].total_latency_ms for t in TICKETS.values()]
    assert latencies != hot_latencies


def test_events_carry_request_and_sim_time() -> None:
    _, events = execute(direct_graph(), ROUTINE, arrival_ms=250.0)
    assert [e.type for e in events] == ["node_started", "node_completed", "edge_transferred",
                                        "node_started", "node_completed", "request_completed"]
    assert all(e.seq == 0 and e.sim_ms == 250.0 for e in events)
    assert isinstance(events[0], NodeStarted) and events[0].request_id == "o-01"
