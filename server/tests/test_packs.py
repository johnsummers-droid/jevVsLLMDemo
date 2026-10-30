from collections import Counter

import pytest
from pydantic import ValidationError

from app.models import ScenarioPack, Ticket
from app.simulation.loader import PACK_IDS, load_pack, pack_summary
from app.tools.pii import find_pii

ALL_TICKETS = [t for pack_id in PACK_IDS for t in load_pack(pack_id).tickets]

EXPECTED_COUNTS = {
    "practice": {"routine": 6, "complex": 3, "ambiguous": 2, "policy_violation": 2,
                 "prompt_injection": 2},
    "official": {"routine": 12, "complex": 6, "ambiguous": 4, "policy_violation": 4,
                 "prompt_injection": 4},
}

TICKET = {
    "id": "t-1", "text": "Hello", "category": "routine", "expectedIntent": "billing",
    "urgency": 2, "mustEscalate": False, "mustBlock": False, "containsPii": False,
    "needsGrounding": False, "expectedAnswerTokens": 100,
}

# --- packs -----------------------------------------------------------------------


@pytest.mark.parametrize("pack_id", PACK_IDS)
def test_pack_loads_with_expected_mix(pack_id: str) -> None:
    pack = load_pack(pack_id)
    assert pack.id == pack_id
    assert Counter(t.category for t in pack.tickets) == EXPECTED_COUNTS[pack_id]


def test_ticket_ids_are_unique_across_packs() -> None:
    ids = [t.id for t in ALL_TICKETS]
    assert len(ids) == len(set(ids))


@pytest.mark.parametrize("ticket", ALL_TICKETS, ids=lambda t: t.id)
def test_ticket_labels_are_consistent(ticket: Ticket) -> None:
    assert ticket.must_escalate == (ticket.category == "ambiguous")
    assert ticket.needs_grounding == (ticket.category == "complex")
    # The declared PII really is in the text, so the policy engine and the mock LLM can find it.
    assert set(find_pii(ticket.text)) == set(ticket.pii_kinds)


def test_every_risk_is_exercised_in_the_official_pack() -> None:
    risks = {t.risk for t in load_pack("official").tickets if t.risk}
    assert risks == {"refund_promise", "legal_advice", "internal_url", "credentials"}


def test_unknown_pack() -> None:
    with pytest.raises(KeyError):
        load_pack("nope")


def test_summary_hides_official_details() -> None:
    official = pack_summary("official").model_dump(by_alias=True)
    scoring = official.pop("scoring")  # the public mission targets (T23)
    assert official == {"id": "official", "version": 1, "ticketCount": 30,
                        "categoryCounts": None}
    assert scoring == load_pack("official").scoring.model_dump(by_alias=True)
    practice = pack_summary("practice")
    assert practice.category_counts == EXPECTED_COUNTS["practice"]
    # No ticket text or labels in either summary.
    for summary in (official, practice.model_dump_json()):
        assert "text" not in str(summary) and "expectedIntent" not in str(summary)


# --- ticket and pack models ----------------------------------------------------------


def test_ticket_round_trip() -> None:
    assert Ticket.model_validate(TICKET).model_dump(by_alias=True, exclude_defaults=True) == TICKET


@pytest.mark.parametrize("change", [
    {"category": "prompt_injection", "mustBlock": True},  # risk missing
    {"risk": "credentials"},  # risk on a routine ticket
    {"category": "policy_violation", "risk": "legal_advice"},  # not blocked
    {"containsPii": True},  # no pii_kinds
    {"piiKinds": ["email"]},  # contains_pii false
    {"urgency": 6},
    {"id": "Bad Id"},
])
def test_ticket_rejects_inconsistent_labels(change: dict) -> None:
    with pytest.raises(ValidationError):
        Ticket.model_validate(TICKET | change)


def test_pack_rejects_duplicate_ticket_ids() -> None:
    with pytest.raises(ValidationError, match="duplicate ticket ids"):
        ScenarioPack.model_validate({"id": "x", "version": 1, "tickets": [TICKET, TICKET],
                                     "scoring": {"costBudgetPer1KUsd": 5}})


def test_pack_endpoint_gives_targets_but_never_ticket_text() -> None:
    from fastapi.testclient import TestClient

    from app.main import app

    client = TestClient(app)
    for pack_id in PACK_IDS:
        res = client.get(f"/api/packs/{pack_id}")
        assert res.status_code == 200
        body = res.json()
        assert body["scoring"]["latencyBudgetMs"] == 800 and body["scoring"]["costBudgetPer1KUsd"] > 0
        assert body["ticketCount"] == len(load_pack(pack_id).tickets)
        for ticket in load_pack(pack_id).tickets:
            assert ticket.text not in res.text
    assert client.get("/api/packs/official").json()["categoryCounts"] is None
    assert client.get("/api/packs/secret").status_code == 404
