"""Pedagogy guardrails (plan1.txt section 5, t5-plan.txt decision 7).

On the official pack, the reference graphs must separate the way the workshop needs. Orderings
and latency budgets are checked on every seed; the strong graph's unsafe and automation rates
are checked as means, because a mock safety miss can make a single seed release one ticket.
"""

import asyncio
import statistics

import pytest

from app.models import RunConfig, RunMetrics
from app.simulation.loader import load_pack
from app.simulation.reference_graphs import REFERENCE_GRAPHS
from app.simulation.runner import run_simulation

SEEDS = range(10)
OFFICIAL = load_pack("official")
BUDGET_MS = OFFICIAL.scoring.latency_budget_ms


def _metrics(name: str, seed: int) -> RunMetrics:
    config = RunConfig(mode="official", pack_id="official", seed=seed)
    return asyncio.run(run_simulation(REFERENCE_GRAPHS[name](), OFFICIAL, config)).metrics


RESULTS = {name: [_metrics(name, seed) for seed in SEEDS] for name in REFERENCE_GRAPHS}


@pytest.mark.parametrize("seed", SEEDS)
def test_default_is_slow_and_unsafe(seed: int) -> None:
    m = RESULTS["default"][seed]
    assert m.p95_latency_ms > BUDGET_MS
    assert m.unsafe_release_rate > 0


def test_weak_scores_below_default() -> None:
    # On the mean and nearly every seed: since T39 both escalate a lot on the mock's dice, so one
    # seed can swap them. Real AI is the real check (plan1.txt T39: -25 against +22).
    weak, default = RESULTS["weak"], RESULTS["default"]
    assert statistics.mean(m.score for m in weak) + 20 < statistics.mean(m.score for m in default)
    assert sum(w.score < d.score for w, d in zip(weak, default, strict=True)) >= 8


@pytest.mark.parametrize("seed", SEEDS)
def test_strong_is_fast_and_scores_highest(seed: int) -> None:
    strong = RESULTS["strong"][seed]
    assert strong.p95_latency_ms <= BUDGET_MS
    assert strong.dropped_rate == 0
    for name in ("default", "weak", "escalate_all"):
        assert strong.score > RESULTS[name][seed].score, name


@pytest.mark.parametrize("seed", SEEDS)
def test_escalating_everything_is_safe_but_too_expensive(seed: int) -> None:
    m = RESULTS["escalate_all"][seed]
    assert m.escalation_rate == 1
    assert m.cost_per_1k_usd > OFFICIAL.scoring.cost_budget_per_1k_usd


def test_default_loses_more_to_safety_than_to_speed() -> None:
    # Safety outweighs speed: the starter graph's unsafe releases cost it more than its p95.
    cfg = OFFICIAL.scoring
    for m in RESULTS["default"]:
        unsafe = cfg.w_unsafe * m.unsafe_release_rate
        latency = min(cfg.latency_penalty_max,
                      cfg.latency_penalty_per_10ms * max(0, m.p95_latency_ms - BUDGET_MS) / 10)
        assert unsafe > latency


def test_strong_is_mostly_automated_and_rarely_unsafe() -> None:
    strong = RESULTS["strong"]
    # About 0.57 on real AI too (T39): at the 0.70 threshold it escalates what it isn't sure about.
    assert statistics.mean(m.automation_rate for m in strong) >= 0.55
    assert statistics.mean(m.unsafe_release_rate for m in strong) <= 0.03
    assert statistics.mean(m.unsafe_release_rate for m in RESULTS["default"]) >= 0.1
