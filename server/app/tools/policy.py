"""Policy engine rules: regexes and phrase lists over the outgoing text.

Each rule catches exactly one of the mock LLM's marker phrases (providers/mock_llm.py), so the
default policy (only no_refund_promises) catches some unsafe answers but not all of them.

Widened from real replies (T38): a commitment to refund counts as a promise, and a match right
after a refusal ("I can't give legal advice") doesn't count. These rules stay deliberately simple:
this is the deterministic tool teams can place in a graph, and real replies are scored by
providers/reply_checks.py instead.
"""

import re

from app.models import PiiKind, PolicyReport, PolicyViolation
from app.tools.pii import find_pii

RULES: dict[str, re.Pattern[str]] = {
    "no_refund_promises": re.compile(
        r"\b(?:promise|guarantee)\w*\b[^.]{0,40}\brefund"
        r"|\b(?:will|I'll|we'll)\s+(?:\w+\s+){0,6}?(?:process|issue|give|send)\w*\s+(?:you\s+)?(?:a|an|your)\s+"
        r"(?:\w+\s+)?refund",
        re.IGNORECASE),
    "no_legal_advice": re.compile(r"\blegal (?:advice|opinion)\b", re.IGNORECASE),
    "no_internal_urls": re.compile(r"https?://[^\s]*\.internal\b|https?://(?:intranet|admin)\.",
                                   re.IGNORECASE),
    "no_credentials": re.compile(r"\b(?:password|api[ _-]?key|secret|token)\b\s*(?:is\b|:)",
                                 re.IGNORECASE),
}


# Ends right before a match when the sentence is declining: "I can't", "I am unable to provide".
_REFUSAL = re.compile(r"\b(?:can't|cannot|can not|unable to|won't|not able to|don't|do not|not)\b"
                      r"[^.!?]{0,40}$", re.IGNORECASE)


def _violates(rule: re.Pattern[str], text: str) -> re.Match[str] | None:
    """The first match that isn't declining."""
    for match in rule.finditer(text):
        if not _REFUSAL.search(text[:match.start()]):
            return match
    return None


def check_policy(text: str, rules: list[str], blocked_phrases: list[str],
                 data_classes: list[PiiKind]) -> PolicyReport:
    violations: list[PolicyViolation] = []
    for rule in rules:
        if match := _violates(RULES[rule], text):
            violations.append(PolicyViolation(rule=rule, match=match.group(0)))
    lowered = text.lower()
    for phrase in blocked_phrases:
        if phrase and phrase.lower() in lowered:
            violations.append(PolicyViolation(rule="blocked_phrase", match=phrase))
    for kind, matches in find_pii(text, data_classes).items():
        violations.append(PolicyViolation(rule=f"data_class:{kind}", match=matches[0]))
    return PolicyReport(passed=not violations, violations=violations)
