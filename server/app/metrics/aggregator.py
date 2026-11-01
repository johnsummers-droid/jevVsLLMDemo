"""Run metrics and per-node stats from request traces (plan1.txt 3f).

All rates are over the total number of requests. Latency percentiles are nearest-rank over
automated requests, in simulated ms. The score is filled in by simulation/scoring.py.
"""

import math
from collections import Counter

from app.models import NodeStats, RequestTrace, RunMetrics


def percentile(values: list[float], p: float) -> float:
    """Nearest-rank percentile; 0.0 for an empty list."""
    if not values:
        return 0.0
    ordered = sorted(values)
    rank = max(1, math.ceil(p / 100 * len(ordered)))
    return ordered[rank - 1]


def _rate(count: int, total: int) -> float:
    return count / total if total else 0.0


def compute_metrics(traces: list[RequestTrace], total: int | None = None) -> RunMetrics:
    """Metrics over the completed traces. total defaults to len(traces) (a finished run)."""
    total = len(traces) if total is None else total
    outcomes = Counter(t.outcome for t in traces)
    automated = [t.total_latency_ms for t in traces if t.outcome == "automated"]
    return RunMetrics(
        total=total,
        completed=len(traces),
        automation_rate=_rate(outcomes["automated"], total),
        escalation_rate=_rate(outcomes["escalated"], total),
        unsafe_release_rate=_rate(sum(t.released_unsafe for t in traces), total),
        dropped_rate=_rate(outcomes["dropped"], total),
        p50_latency_ms=percentile(automated, 50),
        p95_latency_ms=percentile(automated, 95),
        cost_per_1k_usd=_rate(1000 * sum(t.total_cost_usd for t in traces), total),
        decision_quality=_rate(sum(t.decision_correct for t in traces), total),
    )


def compute_node_stats(traces: list[RequestTrace], node_ids: list[str]) -> list[NodeStats]:
    stats = []
    for node_id in node_ids:
        steps = [s for t in traces for s in t.steps if s.node_id == node_id]
        ran = [s for s in steps if not s.skipped]
        stats.append(NodeStats(
            node_id=node_id,
            requests=len(ran),
            skipped=len(steps) - len(ran),
            errors=sum(s.error is not None and s.error.code != "provider_blocked" for s in ran),
            provider_blocks=sum(s.error is not None and s.error.code == "provider_blocked"
                                for s in ran),
            escalations=sum(s.escalated for s in ran),
            avg_latency_ms=sum(s.latency_ms for s in ran) / len(ran) if ran else 0.0,
            total_cost_usd=sum(s.cost_usd for s in ran),
            tokens_out=sum(s.tokens_out for s in ran),
            decisions=dict(Counter(s.fired_branch for s in ran if s.fired_branch)),
        ))
    return stats
