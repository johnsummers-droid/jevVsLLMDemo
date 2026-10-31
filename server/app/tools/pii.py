"""PII detection by regex. Shared by the policy engine's data classes and the mock LLM."""

import re

from app.models import PiiKind

PII_PATTERNS: dict[PiiKind, re.Pattern[str]] = {
    "email": re.compile(r"\b[\w.+-]+@[\w-]+(?:\.[\w-]+)+\b"),
    "phone": re.compile(r"(?<!\d)\(?\d{3}\)?[ .-]\d{3}[ .-]\d{4}(?!\d)"),
    "card_number": re.compile(r"(?<!\d)(?:\d[ -]?){12,15}\d(?!\d)"),
    "ssn": re.compile(r"(?<!\d)\d{3}-\d{2}-\d{4}(?!\d)"),
}


def find_pii(text: str, kinds: list[PiiKind] | None = None) -> dict[PiiKind, list[str]]:
    """Matches per PII kind, in text order. Kinds with no match are left out."""
    found: dict[PiiKind, list[str]] = {}
    for kind in kinds if kinds is not None else list(PII_PATTERNS):
        if matches := PII_PATTERNS[kind].findall(text):
            found[kind] = matches
    return found


# Most specific first, so an SSN is not taken for part of a card or phone number.
REDACTION_ORDER: tuple[PiiKind, ...] = ("ssn", "card_number", "phone", "email")


def redact_pii(text: str, kinds: list[PiiKind]) -> str:
    """Replaces every match of the given kinds with a placeholder such as "[email]"."""
    for kind in REDACTION_ORDER:
        if kind in kinds:
            text = PII_PATTERNS[kind].sub(f"[{kind}]", text)
    return text
