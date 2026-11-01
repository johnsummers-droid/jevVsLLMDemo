"""Deterministic, scenario-aware mock of the Jev decision API (plan1.txt 3b).

Answers depend only on the ticket's labels, the input taint and call.rng, so they are
reproducible. Two questions are understood: "intent" (choice over the allowed intents) and
"safety" (choice over "safe" plus the enabled categories).
"""

import random

from app.models import Distribution
from app.providers.base import JevAnswer, JevQuestion, ProviderCall

# Chance the router picks the expected intent (when it is allowed), by ticket category.
INTENT_ACCURACY = {"routine": 0.95, "complex": 0.85, "ambiguous": 0.55,
                   "policy_violation": 0.85, "prompt_injection": 0.85}
SAFETY_RECALL = 0.92
SAFETY_FALSE_POSITIVE = 0.03
# Which safety category a risky ticket belongs to. Injection is detected through the input's
# "injection" taint, so a message already cleared by a human is no longer a threat.
POLICY_VIOLATION_THREAT = "abuse"


def jev_confidence(probs: dict[str, float]) -> float:
    """Jev's confidence for a choice (U7): (p_max - 1/n) / (1 - 1/n), 0 for an even split and 1
    for certainty. Not p_max, so a router threshold means the same for the mock and real Jev."""
    n = len(probs)
    if n < 2:
        return 1.0
    floor = 1 / n
    return min(1.0, max(0.0, (max(probs.values()) - floor) / (1 - floor)))


def _top_probability(n: int, confidence: float) -> float:
    """The p_max for which jev_confidence returns `confidence` (the inverse of the formula)."""
    floor = 1 / n
    return floor + confidence * (1 - floor)


def _confidence(rng: random.Random, correct: bool, ambiguous: bool) -> float:
    # Calibrated: right answers tend to be confident, wrong ones less so.
    if not correct:
        return rng.betavariate(3, 4)  # mean ~0.43
    # Clear right answers sit well above the 0.70 default threshold, as real Jev's do (T39).
    return rng.betavariate(4, 3) if ambiguous else rng.betavariate(16, 2)  # ~0.57 / ~0.89


def _distribution(rng: random.Random, options: list[str], chosen: str,
                  confidence: float) -> Distribution:
    """Probabilities with `chosen` as the strict maximum, whose Jev confidence is `confidence`."""
    if len(options) == 1:
        return Distribution(probs={chosen: 1.0})
    others = [o for o in options if o != chosen]
    top = _top_probability(len(options), max(confidence, 0.05))  # keep the chosen option on top
    weights = [rng.random() + 1e-9 for _ in others]
    rest = [(1 - top) * w / sum(weights) for w in weights]
    if max(rest) >= top:
        rest = [(1 - top) / len(others)] * len(others)
    probs = {chosen: top, **dict(zip(others, rest, strict=True))}
    probs[chosen] += 1 - sum(probs.values())  # absorb float error
    return Distribution(probs=probs)


class MockJevProvider:
    async def ask(self, state: str, questions: list[JevQuestion],
                  call: ProviderCall) -> list[JevAnswer]:
        answers = []
        for question in questions:
            if question.id == "intent":
                answers.append(self._intent(question, call))
            elif question.id == "safety":
                answers.append(self._safety(question, call))
            else:
                raise ValueError(f"mock Jev does not understand question {question.id!r}")
        return answers

    def _intent(self, question: JevQuestion, call: ProviderCall) -> JevAnswer:
        rng, ticket, options = call.rng, call.ticket, question.options
        truth = ticket.expected_intent
        correct = truth in options and rng.random() < INTENT_ACCURACY[ticket.category]
        wrong = [o for o in options if o != truth]
        value = truth if correct or not wrong else rng.choice(wrong)
        confidence = _confidence(rng, value == truth, ticket.category == "ambiguous")
        probs = _distribution(rng, options, value, confidence)
        return JevAnswer(question_id=question.id, value=value, probabilities=probs,
                         confidence=jev_confidence(probs.probs))

    def _safety(self, question: JevQuestion, call: ProviderCall) -> JevAnswer:
        rng, ticket = call.rng, call.ticket
        categories = [o for o in question.options if o != "safe"]
        threat = None
        if "injection" in call.taint:
            threat = "prompt_injection"
        elif ticket.category == "policy_violation":
            threat = POLICY_VIOLATION_THREAT
        if threat in categories:
            flagged = threat if rng.random() < SAFETY_RECALL else None
        else:
            flagged = rng.choice(categories) if rng.random() < SAFETY_FALSE_POSITIVE else None
        # p_unsafe: high when flagged, low otherwise; the runner compares it to its threshold.
        p_unsafe = rng.betavariate(12, 2) if flagged else rng.betavariate(1.5, 12)
        category = flagged or rng.choice(categories)
        probs = {"safe": 1 - p_unsafe, **{c: 0.0 for c in categories}}
        probs[category] = p_unsafe
        value = "safe" if p_unsafe < 0.5 else category
        return JevAnswer(question_id=question.id, value=value,
                         probabilities=Distribution(probs=probs), confidence=jev_confidence(probs))
