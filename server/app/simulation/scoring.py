"""Leaderboard score (plan1.txt 3f). Weights and budgets come from the pack's ScoringConfig."""

from app.models import RunMetrics, ScoringConfig


def score(metrics: RunMetrics, config: ScoringConfig) -> float:
    latency_over = max(0.0, metrics.p95_latency_ms - config.latency_budget_ms)
    cost_over = max(0.0, metrics.cost_per_1k_usd / config.cost_budget_per_1k_usd - 1)
    return (config.w_automation * metrics.automation_rate
            + config.w_quality * metrics.decision_quality
            - config.w_unsafe * metrics.unsafe_release_rate
            - config.latency_penalty_per_10ms * latency_over / 10
            - config.cost_penalty_per_10pct * cost_over * 10)


def with_score(metrics: RunMetrics, config: ScoringConfig) -> RunMetrics:
    return metrics.model_copy(update={"score": score(metrics, config)})
