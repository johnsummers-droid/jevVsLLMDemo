"""Simulated latency sampling (pulled forward from T5; t4-plan.txt decision 2)."""

import math
import random


def sample_latency(median_ms: float, jitter_ms: float, rng: random.Random) -> float:
    """Lognormal latency with the given median; jitter_ms sets the spread (sigma = jitter/median).

    Always >= 0. No jitter returns the median exactly; a zero median returns 0.
    """
    if median_ms <= 0:
        return 0.0
    if jitter_ms <= 0:
        return float(median_ms)
    return rng.lognormvariate(math.log(median_ms), jitter_ms / median_ms)
