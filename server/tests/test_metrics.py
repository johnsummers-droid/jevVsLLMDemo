import pytest

from app.metrics.aggregator import compute_metrics, compute_node_stats, percentile
from app.models import NodeExecution, RequestTrace, RunMetrics, ScoringConfig
from app.simulation.scoring import score, with_score


def trace(outcome: str, latency: float = 100, cost: float = 0.0, unsafe: bool = False,
          correct: bool = True, steps: list[NodeExecution] | None = None) -> RequestTrace:
    return RequestTrace(request_id="r", ticket_id="t", arrival_ms=0, steps=steps or [],
                        outcome=outcome, released_unsafe=unsafe, decision_correct=correct,
                        total_latency_ms=latency, total_cost_usd=cost)


@pytest.mark.parametrize(("values", "p", "expected"), [
    ([], 95, 0.0),
    ([42], 50, 42),
    ([42], 95, 42),
    ([5, 1, 4, 2, 3], 50, 3),
    (list(range(1, 21)), 95, 19),  # ceil(0.95 * 20) = 19th value
    (list(range(1, 101)), 95, 95),
    ([10, 20], 0, 10),
])
def test_nearest_rank_percentile(values: list[float], p: float, expected: float) -> None:
    assert percentile(values, p) == expected


def test_empty_run_has_zero_rates() -> None:
    metrics = compute_metrics([])
    assert metrics.total == 0 and metrics.automation_rate == 0 and metrics.p95_latency_ms == 0
    assert metrics.cost_per_1k_usd == 0 and metrics.decision_quality == 0


def test_rates_are_over_all_requests_and_latency_over_automated_only() -> None:
    traces = [
        trace("automated", latency=100),
        trace("automated", latency=300, unsafe=True, correct=False),
        trace("escalated", latency=120_000, cost=2.0),  # human time stays out of percentiles
        trace("blocked", latency=50),
        trace("dropped", latency=10, correct=False),
    ]
    m = compute_metrics(traces)
    assert (m.total, m.completed) == (5, 5)
    assert m.automation_rate == 0.4 and m.escalation_rate == 0.2
    assert m.unsafe_release_rate == 0.2 and m.dropped_rate == 0.2
    assert (m.p50_latency_ms, m.p95_latency_ms) == (100, 300)
    assert m.cost_per_1k_usd == pytest.approx(400)  # $2 over 5 requests, x1000
    assert m.decision_quality == 0.6


def test_partial_run_uses_the_given_total() -> None:
    m = compute_metrics([trace("automated")], total=4)
    assert (m.total, m.completed, m.automation_rate) == (4, 1, 0.25)


def test_node_stats() -> None:
    def run_step(**kw: object) -> NodeExecution:
        return NodeExecution(node_id="router", node_type="jev_intent_router", start_ms=0, **kw)

    traces = [
        trace("automated", steps=[run_step(latency_ms=40, cost_usd=0.0002,
                                           fired_branch="route.billing")]),
        trace("dropped", steps=[run_step(latency_ms=60, cost_usd=0.0002,
                                         fired_branch="route.low_confidence")]),
        trace("dropped", steps=[run_step(latency_ms=0, skipped=True)]),
    ]
    [stats] = compute_node_stats(traces, ["router"])
    assert (stats.requests, stats.skipped, stats.errors) == (2, 1, 0)
    assert stats.avg_latency_ms == 50 and stats.total_cost_usd == pytest.approx(0.0004)
    assert stats.decisions == {"route.billing": 1, "route.low_confidence": 1}
    assert compute_node_stats([], ["router"])[0].avg_latency_ms == 0


def test_score_by_hand() -> None:
    config = ScoringConfig(cost_budget_per_1k_usd=1000)
    metrics = RunMetrics(total=10, completed=10, automation_rate=0.6, escalation_rate=0.3,
                         unsafe_release_rate=0.1, dropped_rate=0.1, p50_latency_ms=500,
                         p95_latency_ms=1000, cost_per_1k_usd=1500, decision_quality=0.8)
    # 100*0.6 + 50*0.8 - 400*0.1 - 1*(1000-800)/10 - 5*(1500/1000-1)*10
    assert score(metrics, config) == pytest.approx(60 + 40 - 40 - 20 - 25)
    within = metrics.model_copy(update={"p95_latency_ms": 700, "cost_per_1k_usd": 900})
    assert score(within, config) == pytest.approx(60 + 40 - 40)
    assert with_score(within, config).score == pytest.approx(60)
