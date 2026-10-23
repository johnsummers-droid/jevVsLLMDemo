"""Server settings.

Plain constants until env-driven settings arrive with pydantic-settings in M3 (t4-plan.txt
decision 3). Prices are placeholders, tuned in T5 so the default graph misses the cost budget.
"""

# USD per 1k tokens, per LLM tier.
LLM_PRICES_PER_1K_USD: dict[str, dict[str, float]] = {
    "small": {"in": 0.001, "out": 0.005},
    "large": {"in": 0.003, "out": 0.015},
}
