"""Deterministic, scenario-aware mock of the Jev decision API (plan1.txt 3b).

Answers depend only on the ticket's labels, the input taint and call.rng, so they are
reproducible. Three questions are understood: "intent" (choice over the allowed intents),
"safety" (choice over "safe" plus the enabled categories) and "urgency" (choice over the rubric's
levels, as strings).
"""

import random

from app.models import Distribution
from app.providers.base import JevAnswer, JevQuestion, ProviderCall

# Chance the router picks the expected intent (when it is allowed), by ticket category.
INTENT_ACCURACY = {"routine": 0.95, "complex": 0.85, "ambiguous": 0.55,
                   "policy_violation": 0.85, "prompt_injection": 0.85}
# Chance the urgency scorer gives the ticket's level (else one level off), by category.
URGENCY_ACCURACY = {"routine": 0.9, "complex": 0.8, "ambiguous": 0.6,
                    "policy_violation": 0.8, "prompt_injection": 0.8}
SAFETY_RECALL = 0.92
SAFETY_FALSE_POSITIVE = 0.03
# Which safety category a risky ticket belongs to. Injection is detected through the input's
# "injection" taint, so a message already cleared by a human is no longer a threat.
POLICY_VIOLATION_THREAT = "abuse"


def _confidence(rng: random.Random, correct: bool, ambiguous: bool) -> float:
    # Calibrated: right answers tend to be confident, wrong ones less so.
    if not correct:
        return rng.betavariate(3, 4)  # mean ~0.43
    return rng.betavariate(4, 3) if ambiguous else rng.betavariate(8, 2)  # ~0.57 / ~0.8


def _distribution(rng: random.Random, options: list[str], chosen: str,
                  confidence: float) -> Distribution:
    """Probabilities with `chosen` as the strict maximum at roughly `confidence`."""
    if len(options) == 1:
        return Distribution(probs={chosen: 1.0})
    others = [o for o in options if o != chosen]
    floor = 1 / len(options)
    top = max(confidence, floor + (1 - floor) * 0.05)  # keep the chosen option on top
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
            elif question.id == "urgency":
                answers.append(self._urgency(question, call))
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
                         confidence=probs.probs[value])

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
                         probabilities=Distribution(probs=probs),
                         confidence=max(p_unsafe, 1 - p_unsafe))

    def _urgency(self, question: JevQuestion, call: ProviderCall) -> JevAnswer:
        rng, ticket = call.rng, call.ticket
        levels = sorted(int(o) for o in question.options)
        # The rubric's level closest to the truth, rounding up (2 -> 3 on a 1/3/5 rubric).
        truth = min(levels, key=lambda level: (abs(level - ticket.urgency), -level))
        correct = rng.random() < URGENCY_ACCURACY[ticket.category]
        index = levels.index(truth)
        if not correct:
            neighbours = [i for i in (index - 1, index + 1) if 0 <= i < len(levels)]
            index = rng.choice(neighbours)
        value = str(levels[index])
        confidence = _confidence(rng, correct, ticket.category == "ambiguous")
        probs = _distribution(rng, question.options, value, confidence)
        return JevAnswer(question_id=question.id, value=value, probabilities=probs,
                         confidence=probs.probs[value])
