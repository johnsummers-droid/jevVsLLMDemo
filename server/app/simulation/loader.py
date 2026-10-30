"""Loads the scenario packs bundled in simulation/packs/. Packs are read once and cached."""

import json
from collections import Counter
from functools import cache
from pathlib import Path

from app.catalog.definitions.jev import INTENTS
from app.models import PackSummary, ScenarioPack

PACKS_DIR = Path(__file__).parent / "packs"
PACK_IDS = ("practice", "official")
HIDDEN_PACKS = frozenset({"official"})  # never send ticket details to clients (plan1.txt D9)


@cache
def load_pack(pack_id: str) -> ScenarioPack:
    if pack_id not in PACK_IDS:
        raise KeyError(f"unknown pack {pack_id!r}")
    pack = ScenarioPack.model_validate(json.loads((PACKS_DIR / f"{pack_id}.json").read_text()))
    if pack.id != pack_id:
        raise ValueError(f"{pack_id}.json declares id {pack.id!r}")
    if bad := sorted({t.expected_intent for t in pack.tickets} - set(INTENTS)):
        raise ValueError(f"{pack_id}: unknown expected intents {bad}")
    return pack


def pack_summary(pack_id: str) -> PackSummary:
    pack = load_pack(pack_id)
    counts = None if pack_id in HIDDEN_PACKS else dict(Counter(t.category for t in pack.tickets))
    return PackSummary(id=pack.id, version=pack.version, ticket_count=len(pack.tickets),
                       category_counts=counts, scoring=pack.scoring)
