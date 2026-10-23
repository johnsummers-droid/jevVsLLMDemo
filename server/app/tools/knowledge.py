"""Knowledge lookup: deterministic keyword match against the bundled kb.json fixture."""

import json
import re
from functools import cache
from pathlib import Path

from app.models import Doc, Docs

KB_PATH = Path(__file__).parent / "kb.json"
SOURCES = ("faq", "kb", "tickets")


@cache
def _kb() -> list[dict]:
    return json.loads(KB_PATH.read_text())


def lookup(text: str, source: str, top_k: int) -> Docs:
    """Docs from one source ranked by how many of their keywords occur in the text."""
    if source not in SOURCES:
        raise ValueError(f"unknown source {source!r}")
    words = set(re.findall(r"[a-z0-9]+", text.lower()))
    hits = []
    for entry in _kb():
        if entry["source"] != source:
            continue
        if score := len(words & set(entry["keywords"])):
            hits.append(Doc(id=entry["id"], title=entry["title"], snippet=entry["snippet"],
                            intent=entry["intent"], score=score))
    hits.sort(key=lambda d: (-d.score, d.id))
    return Docs(docs=hits[:top_k])
