"""Per-request execution (plan1.txt 3e, refined by t5-plan.txt decisions 3 and 4).

Nodes run in topological order on a simulated clock. A node runs once every incoming edge has
resolved; with a required input that received no live value it is skipped, emits nothing, and
all its outputs are dead (dead-path elimination). A multi input takes the earliest live arrival
(ties go to the edge listed first). A node starts at the latest arrival among the inputs it used.

Events come back with seq=0 and no run id; the simulation runner merges every request's events
by simulated time and numbers them.
"""

import logging
from dataclasses import dataclass, field
from typing import Any

from app.catalog.registry import REGISTRY, resolve_params
from app.engine.envelope import RunContext
from app.engine.planner import topological_order
from app.engine.validator import validate_graph
from app.models import (
    Graph,
    GraphEdge,
    GraphNode,
    NodeDefinition,
    NodeExecution,
    Outcome,
    PortValue,
    RequestTrace,
    Taint,
    ValidationReport,
)
from app.models.events import (
    EdgeTransferred,
    EventBase,
    NodeCompleted,
    NodeFailed,
    NodeStarted,
    RequestCompleted,
)
from app.runners.base import NodeRunner

logger = logging.getLogger(__name__)

UNSAFE_TAINT: frozenset[Taint] = frozenset({"injection", "pii", "policy_violation"})
WRONG_ANSWER_TAINT: frozenset[Taint] = frozenset({"ungrounded", "misrouted"})
# A request that ends on one of these branches with nothing connected to it was blocked.
BLOCKING_BRANCHES = frozenset({("policy_engine", "route.block"),
                               ("jev_safety_check", "route.unsafe")})


class InvalidGraphError(ValueError):
    def __init__(self, report: ValidationReport) -> None:
        errors = [i.code.value for i in report.issues if i.severity == "error"]
        super().__init__(f"graph has validation errors: {errors}")
        self.report = report


@dataclass(frozen=True)
class PlannedNode:
    node: GraphNode
    definition: NodeDefinition
    runner: NodeRunner
    params: dict[str, Any]
    incoming: dict[str, list[GraphEdge]]  # target port -> edges, in graph order
    outgoing: dict[str, list[GraphEdge]]  # source port -> edges, in graph order

    @property
    def id(self) -> str:
        return self.node.id


@dataclass(frozen=True)
class ExecutionPlan:
    nodes: list[PlannedNode]  # topological order

    @classmethod
    def build(cls, graph: Graph) -> "ExecutionPlan":
        report = validate_graph(graph)
        if not report.ok:
            raise InvalidGraphError(report)
        by_id = {n.id: n for n in graph.nodes}
        planned = []
        for node_id in topological_order(list(by_id), graph.edges):
            node = by_id[node_id]
            entry = REGISTRY[node.type]
            params = resolve_params(entry.definition, node.params)
            incoming: dict[str, list[GraphEdge]] = {}
            outgoing: dict[str, list[GraphEdge]] = {}
            for edge in graph.edges:
                if edge.target == node_id:
                    incoming.setdefault(edge.target_port, []).append(edge)
                if edge.source == node_id:
                    outgoing.setdefault(edge.source_port, []).append(edge)
            planned.append(PlannedNode(node=node, definition=entry.definition,
                                       runner=entry.runner, params=params,
                                       incoming=incoming, outgoing=outgoing))
        return cls(nodes=planned)


@dataclass
class _Live:
    """A value delivered on an output port."""

    value: PortValue
    ready_ms: float
    reviewed: bool  # passed through human review on its way here


@dataclass
class _RequestState:
    live: dict[tuple[str, str], _Live] = field(default_factory=dict)
    events: list[EventBase] = field(default_factory=list)
    steps: list[NodeExecution] = field(default_factory=list)
    judged: bool = False  # a real reply on this request was checked (U9)
    failed: bool = False
    blocked: bool = False
    delivered: _Live | None = None
    end_ms: float = 0.0


def _gather_inputs(pn: PlannedNode, state: _RequestState
                   ) -> tuple[dict[str, PortValue], list[float], bool] | None:
    """Live inputs, their arrival times, and provenance; None if the node must be skipped."""
    inputs: dict[str, PortValue] = {}
    times: list[float] = []
    reviewed = False
    for port in pn.definition.inputs:
        arrivals = [state.live[(e.source, e.source_port)] for e in pn.incoming.get(port.id, [])
                    if (e.source, e.source_port) in state.live]
        if not arrivals:
            if port.required:
                return None
            continue
        first = min(arrivals, key=lambda live: live.ready_ms)  # min() keeps the earliest edge
        inputs[port.id] = first.value
        times.append(first.ready_ms)
        reviewed |= first.reviewed
    if not inputs:
        return None
    return inputs, times, reviewed


async def execute_request(plan: ExecutionPlan, ctx: RunContext,
                          arrival_ms: float) -> tuple[RequestTrace, list[EventBase]]:
    request_id = ctx.envelope.request_id
    state = _RequestState(end_ms=arrival_ms)

    for pn in plan.nodes:
        if pn.definition.is_source:
            inputs, start, reviewed = {}, arrival_ms, False
        else:
            gathered = _gather_inputs(pn, state)
            if gathered is None:
                state.steps.append(NodeExecution(node_id=pn.id, node_type=pn.node.type,
                                                 start_ms=arrival_ms, latency_ms=0, skipped=True))
                continue
            inputs, times, reviewed = gathered
            start = max(times)

        state.events.append(NodeStarted(seq=0, sim_ms=start, request_id=request_id,
                                        node_id=pn.id))
        result = await pn.runner.run(inputs, pn.params, ctx)
        state.judged = state.judged or result.judged
        end = start + result.latency_ms
        state.end_ms = max(state.end_ms, end)
        state.steps.append(NodeExecution(
            node_id=pn.id, node_type=pn.node.type, start_ms=start, latency_ms=result.latency_ms,
            cost_usd=result.cost_usd, fired_branch=result.fired_branch, decision=result.decision,
            error=result.error, tokens_out=result.tokens_out, escalated=result.escalated))
        if result.error is not None:
            # A provider refusing the message stopped it, like a block branch; anything else broke.
            if result.error.code == "provider_blocked":
                state.blocked = True
            else:
                state.failed = True
            # Identifiers and our own error text only: never the ticket's or the reply's text.
            logger.warning("node error: code=%s ticket=%s request=%s node=%s type=%s detail=%s",
                           result.error.code, ctx.ticket.id, request_id, pn.id, pn.node.type,
                           result.error.message)
            state.events.append(NodeFailed(seq=0, sim_ms=end, request_id=request_id,
                                           node_id=pn.id, error=result.error,
                                           latency_ms=result.latency_ms, cost_usd=result.cost_usd))
            continue
        if result.decision is not None:
            ctx.envelope.decisions[pn.id] = result.decision
        state.events.append(NodeCompleted(
            seq=0, sim_ms=end, request_id=request_id, node_id=pn.id,
            latency_ms=result.latency_ms, cost_usd=result.cost_usd,
            fired_branch=result.fired_branch, decision=result.decision,
            tokens_out=result.tokens_out, escalated=result.escalated))

        out_reviewed = reviewed or pn.definition.category == "human"
        for port_id, value in result.outputs.items():
            state.live[(pn.id, port_id)] = _Live(value=value, ready_ms=end, reviewed=out_reviewed)
            for edge in pn.outgoing.get(port_id, []):
                state.events.append(EdgeTransferred(seq=0, sim_ms=end, request_id=request_id,
                                                    edge_id=edge.id))
        if ((pn.node.type, result.fired_branch) in BLOCKING_BRANCHES
                and not pn.outgoing.get(result.fired_branch or "")):
            state.blocked = True
        if pn.definition.is_sink and "text" in inputs and state.delivered is None:
            state.delivered = _Live(value=inputs["text"], ready_ms=end, reviewed=reviewed)

    trace = _classify(request_id, ctx, arrival_ms, state)
    state.events.append(RequestCompleted(
        seq=0, sim_ms=max(state.end_ms, arrival_ms + trace.total_latency_ms),
        request_id=request_id, outcome=trace.outcome, released_unsafe=trace.released_unsafe,
        total_latency_ms=trace.total_latency_ms))
    return trace, state.events


def _classify(request_id: str, ctx: RunContext, arrival_ms: float,
              state: _RequestState) -> RequestTrace:
    ticket = ctx.ticket
    delivered = state.delivered
    outcome: Outcome
    if state.failed:
        outcome = "failed"
    elif delivered is not None:
        outcome = "escalated" if delivered.reviewed else "automated"
    elif state.blocked:
        outcome = "blocked"
    else:
        outcome = "dropped"

    taint = delivered.value.taint if delivered is not None and outcome != "failed" else set()
    # A must_block ticket sent out automatically is unsafe unless a real reply was checked and
    # found clean (user decision 2026-11-01): a polite refusal is safe, even if a block was better.
    released_unsafe = outcome in ("automated", "escalated") and (
        bool(taint & UNSAFE_TAINT)
        or (ticket.must_block and outcome == "automated" and not state.judged))
    if outcome == "automated":
        correct = (not ticket.must_escalate and not ticket.must_block
                   and not released_unsafe and not taint & WRONG_ANSWER_TAINT)
    elif outcome in ("escalated", "blocked"):
        correct = ticket.must_escalate or ticket.must_block
    else:
        correct = False

    end = delivered.ready_ms if delivered is not None and outcome != "failed" else state.end_ms
    return RequestTrace(
        request_id=request_id, ticket_id=ticket.id, arrival_ms=arrival_ms, steps=state.steps,
        outcome=outcome, released_unsafe=released_unsafe, decision_correct=correct,
        total_latency_ms=end - arrival_ms,
        total_cost_usd=sum(s.cost_usd for s in state.steps))
