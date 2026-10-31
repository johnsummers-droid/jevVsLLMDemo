"""Leaderboard score (plan1.txt 3f). Weights and budgets come from the pack's ScoringConfig."""

from dataclasses import dataclass

from app.models import LeaderboardRow, RunMetrics, RunStatus, ScoringConfig


def score(metrics: RunMetrics, config: ScoringConfig) -> float:
    latency_over = max(0.0, metrics.p95_latency_ms - config.latency_budget_ms)
    cost_over = max(0.0, metrics.cost_per_1k_usd / config.cost_budget_per_1k_usd - 1)
    return (config.w_automation * metrics.automation_rate
            + config.w_quality * metrics.decision_quality
            - config.w_unsafe * metrics.unsafe_release_rate
            - min(config.latency_penalty_max, config.latency_penalty_per_10ms * latency_over / 10)
            - config.cost_penalty_per_10pct * cost_over * 10)


def with_score(metrics: RunMetrics, config: ScoringConfig) -> RunMetrics:
    return metrics.model_copy(update={"score": score(metrics, config)})


@dataclass
class Standing:
    """A team's latest official run, before ranking."""

    team_id: str
    team_name: str
    run_id: str
    status: RunStatus
    metrics: RunMetrics | None


# Finished runs first, then stopped (scored on what completed), still running, failed.
_STATUS_ORDER: dict[str, int] = {"completed": 0, "stopped": 1, "running": 2, "pending": 2, "failed": 3}


def rank(standings: list[Standing]) -> list[LeaderboardRow]:
    """Leaderboard order (T21): by status group, then higher score, lower unsafe-release rate,
    lower p95, then name. Ranks are positions, so they are unique."""
    def key(s: Standing) -> tuple:
        m = s.metrics
        scored = (-m.score, m.unsafe_release_rate, m.p95_latency_ms) if m is not None else (0.0, 0.0, 0.0)
        return (_STATUS_ORDER.get(s.status, 3), *scored, s.team_name.casefold())

    return [LeaderboardRow(team_id=s.team_id, team_name=s.team_name, run_id=s.run_id, status=s.status,
                           metrics=s.metrics, rank=i)
            for i, s in enumerate(sorted(standings, key=key), start=1)]
