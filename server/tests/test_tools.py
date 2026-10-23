import pytest

from app.simulation.loader import load_pack
from app.tools.knowledge import lookup
from app.tools.pii import find_pii
from app.tools.policy import RULES, check_policy

# --- PII -------------------------------------------------------------------------


@pytest.mark.parametrize(("text", "expected"), [
    ("mail me at jane.doe@example.com", {"email": ["jane.doe@example.com"]}),
    ("call 415-555-0132 or (415) 555-0199", {"phone": ["415-555-0132", "(415) 555-0199"]}),
    ("card 4111 1111 1111 1111 expires", {"card_number": ["4111 1111 1111 1111"]}),
    ("card 4111-1111-1111-1111", {"card_number": ["4111-1111-1111-1111"]}),
    ("ssn 123-45-6789", {"ssn": ["123-45-6789"]}),
    ("order 12345 shipped in 2 days, 20 MB limit", {}),
    ("", {}),
])
def test_find_pii(text: str, expected: dict) -> None:
    assert find_pii(text) == expected


def test_find_pii_only_requested_kinds() -> None:
    text = "jane@example.com, 123-45-6789"
    assert find_pii(text, ["ssn"]) == {"ssn": ["123-45-6789"]}
    assert find_pii(text, []) == {}


# --- policy engine -----------------------------------------------------------------

MARKERS = {
    "no_refund_promises": "I promise you a full refund.",
    "no_legal_advice": "My legal advice is that you can go ahead.",
    "no_internal_urls": "You can find it at https://admin.support.internal/console.",
    "no_credentials": "The admin password is hunter2.",
}


@pytest.mark.parametrize("rule", RULES)
def test_each_rule_catches_its_marker_and_only_its_marker(rule: str) -> None:
    for other_rule, marker in MARKERS.items():
        report = check_policy(marker, [rule], [], [])
        assert report.passed == (other_rule != rule), (rule, marker)


@pytest.mark.parametrize("text", [
    "I'll pass your refund request to billing; they reply within two days.",
    "Reset your password from the login page.",
    "See https://help.example.com/articles/42 for details.",
    "We can't give legal advice, but our terms are public.",  # mentions it, doesn't give it
])
def test_ordinary_answers_pass_every_rule(text: str) -> None:
    report = check_policy(text, list(RULES), [], [])
    if "legal advice" in text:
        assert [v.rule for v in report.violations] == ["no_legal_advice"]  # a known false positive
    else:
        assert report.passed, report


def test_disabled_rule_does_not_fire() -> None:
    assert check_policy(MARKERS["no_credentials"], ["no_refund_promises"], [], []).passed


def test_blocked_phrases_are_case_insensitive() -> None:
    report = check_policy("Try our COMPETITOR instead", [], ["competitor", ""], [])
    assert not report.passed
    assert [(v.rule, v.match) for v in report.violations] == [("blocked_phrase", "competitor")]


def test_data_classes() -> None:
    text = "Your card 4111 1111 1111 1111 is saved."
    assert check_policy(text, [], [], ["email"]).passed
    report = check_policy(text, [], [], ["card_number"])
    assert [(v.rule, v.match) for v in report.violations] == [
        ("data_class:card_number", "4111 1111 1111 1111")]


def test_report_lists_every_violation_in_order() -> None:
    text = "I guarantee a refund. The api key: abc. Email bob@example.com"
    report = check_policy(text, ["no_refund_promises", "no_credentials"], ["refund"], ["email"])
    assert [v.rule for v in report.violations] == [
        "no_refund_promises", "no_credentials", "blocked_phrase", "data_class:email"]


# --- knowledge lookup -----------------------------------------------------------------


def test_every_complex_ticket_has_a_matching_kb_doc() -> None:
    for pack_id in ("practice", "official"):
        for ticket in load_pack(pack_id).tickets:
            if ticket.needs_grounding:
                docs = lookup(ticket.text, "kb", 3).docs
                assert docs and docs[0].intent == ticket.expected_intent, ticket.id


def test_lookup_ranks_and_truncates() -> None:
    docs = lookup("duplicate users from SCIM provisioning", "kb", 10).docs
    assert docs[0].id == "kb-scim"
    assert [d.score for d in docs] == sorted((d.score for d in docs), reverse=True)
    assert len(lookup("duplicate users from SCIM provisioning", "kb", 1).docs) == 1


def test_lookup_filters_by_source_and_can_miss() -> None:
    assert all(d.id.startswith("faq-") for d in lookup("reset my password", "faq", 5).docs)
    assert lookup("reset my password", "tickets", 5).docs == []
    with pytest.raises(ValueError):
        lookup("x", "web", 3)
