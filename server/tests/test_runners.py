import asyncio
import random
import statistics
from typing import Any

import pytest

from app.catalog.definitions.jev import INTENTS
from app.catalog.registry import REGISTRY, default_params, expand_outputs
from app.engine.envelope import make_context
from app.engine.latency import sample_latency
from app.engine.seeding import derive_seed
from app.models import NodeResult, PortValue, Ticket
from app.providers.mock_jev import jev_confidence
from app.providers.mock_llm import MARKERS
from app.simulation.loader import PACK_IDS, load_pack
from app.tools.policy import check_policy

TICKETS = {t.id: t for pack_id in PACK_IDS for t in load_pack(pack_id).tickets}
SEEDS = range(200)


def run(node_type: str, ticket: Ticket, inputs: dict[str, PortValue] | None = None,
        params: dict[str, Any] | None = None, seed: int = 0) -> NodeResult:
    entry = REGISTRY[node_type]
    resolved = default_params(entry.definition) | (params or {})
    if inputs is None:
        inputs = {"text": message(ticket)} if entry.definition.inputs else {}
    return asyncio.run(entry.runner.run(inputs, resolved, make_context(ticket, run_seed=seed)))


def message(ticket: Ticket) -> PortValue:
    return run("customer_message", ticket).outputs["text"]


def rate(flags: list[bool]) -> float:
    return sum(flags) / len(flags)


# --- seeding and latency ---------------------------------------------------------------


def test_seed_is_stable_across_processes() -> None:
    # Pinned: a change here means every run's results change (and hash() salting would show up).
    assert derive_seed(1, "o-01", "jev_intent_router", {"a": 1}, {}) == 15830023468400009395


def test_seed_ignores_taint_and_key_order_but_not_content() -> None:
    a = PortValue(type="text", value="hi", taint={"injection", "pii", "misrouted"})
    b = PortValue(type="text", value="hi", taint={"misrouted", "pii", "injection"})
    base = derive_seed(1, "t", "n", {"x": 1, "y": 2}, {"text": a})
    assert base == derive_seed(1, "t", "n", {"y": 2, "x": 1}, {"text": b})
    assert base != derive_seed(1, "t", "n", {"x": 1, "y": 3}, {"text": a})
    assert base != derive_seed(1, "t", "n", {"x": 1, "y": 2}, {"text": a}, stream="latency")
    assert base != derive_seed(2, "t", "n", {"x": 1, "y": 2}, {"text": a})


def test_sample_latency() -> None:
    rng = random.Random(0)
    assert sample_latency(0, 10, rng) == 0
    assert sample_latency(40, 0, rng) == 40
    samples = [sample_latency(40, 15, rng) for _ in range(2000)]
    assert min(samples) > 0
    assert statistics.median(samples) == pytest.approx(40, rel=0.1)


# --- output contracts ------------------------------------------------------------------


@pytest.mark.parametrize("node_type", REGISTRY)
@pytest.mark.parametrize("ticket_id", TICKETS)
def test_runner_output_contract(node_type: str, ticket_id: str) -> None:
    ticket = TICKETS[ticket_id]
    definition = REGISTRY[node_type].definition
    ports = {p.id: p for p in expand_outputs(definition, default_params(definition))}
    branches = {pid for pid, p in ports.items() if p.branch}
    for seed in range(5):
        result = run(node_type, ticket, seed=seed)
        assert result.error is None
        assert set(result.outputs) <= set(ports)
        for port_id, value in result.outputs.items():
            assert value.type == ports[port_id].type, port_id
        # Every data output is present; exactly one branch fires when the node has branches.
        assert set(result.outputs) - branches == set(ports) - branches
        fired = set(result.outputs) & branches
        assert fired == ({result.fired_branch} if branches else set())
        assert result.latency_ms >= 0 and result.cost_usd >= 0


@pytest.mark.parametrize("node_type", [t for t, e in REGISTRY.items() if e.definition.inputs])
def test_missing_text_input_is_an_error(node_type: str) -> None:
    result = run(node_type, TICKETS["o-01"], inputs={})
    assert result.error is not None and result.error.code == "invalid_input"


@pytest.mark.parametrize("node_type", REGISTRY)
def test_runners_are_deterministic(node_type: str) -> None:
    for ticket in TICKETS.values():
        assert run(node_type, ticket, seed=7) == run(node_type, ticket, seed=7)


def test_run_seed_changes_results() -> None:
    results = {run("jev_intent_router", TICKETS["o-19"], seed=s).decision["confidence"]
               for s in range(10)}
    assert len(results) == 10


# --- customer message ------------------------------------------------------------------


def test_only_injection_tickets_carry_injection_taint() -> None:
    for ticket in TICKETS.values():
        expected = {"injection"} if ticket.category == "prompt_injection" else set()
        assert message(ticket).taint == expected
        assert message(ticket).value == ticket.text


# --- intent router ---------------------------------------------------------------------


def test_router_threshold_is_monotonic_per_ticket() -> None:
    thresholds = [0.0, 0.2, 0.4, 0.5, 0.6, 0.8, 1.0]
    for ticket in TICKETS.values():
        for seed in range(10):
            low = [run("jev_intent_router", ticket, params={"threshold": t}, seed=seed)
                   .fired_branch == "route.low_confidence" for t in thresholds]
            assert low == sorted(low), (ticket.id, seed, low)  # once low, stays low
            assert not low[0] and low[-1]


def test_router_accuracy_follows_ticket_category() -> None:
    def accuracy(category: str) -> float:
        hits = [run("jev_intent_router", t, params={"allowed_intents": INTENTS},
                    seed=s).decision["intent"] == t.expected_intent
                for t in TICKETS.values() if t.category == category for s in SEEDS]
        return rate(hits)

    assert accuracy("routine") == pytest.approx(0.95, abs=0.04)
    assert accuracy("complex") == pytest.approx(0.85, abs=0.05)
    assert accuracy("ambiguous") == pytest.approx(0.55, abs=0.06)


def test_router_confidence_is_calibrated() -> None:
    right, wrong = [], []
    for ticket in TICKETS.values():
        for seed in range(40):
            d = run("jev_intent_router", ticket, seed=seed).decision
            (right if d["intent"] == ticket.expected_intent else wrong).append(d["confidence"])
    assert statistics.mean(right) > statistics.mean(wrong) + 0.2


def test_router_marks_wrong_routes_as_misrouted() -> None:
    ticket = TICKETS["o-10"]  # expected intent "account" is not allowed by default
    for seed in range(20):
        result = run("jev_intent_router", ticket, params={"threshold": 0}, seed=seed)
        assert result.decision["intent"] != "account"
        assert "misrouted" in result.outputs[result.fired_branch].taint


def test_router_low_confidence_branch_is_not_misrouted() -> None:
    result = run("jev_intent_router", TICKETS["o-10"], params={"threshold": 1})
    assert result.fired_branch == "route.low_confidence"
    assert "misrouted" not in result.outputs["route.low_confidence"].taint


def test_router_distribution_tops_at_the_chosen_intent() -> None:
    for seed in range(50):
        result = run("jev_intent_router", TICKETS["o-19"], seed=seed)
        probs = result.outputs["probabilities"].value["probs"]
        assert max(probs, key=probs.get) == result.outputs["intent"].value
        # Jev's confidence (U7): how far p_max stands above an even split, not p_max itself.
        n = len(probs)
        expected = (probs[result.outputs["intent"].value] - 1 / n) / (1 - 1 / n)
        assert result.outputs["confidence"].value == pytest.approx(expected)


def test_jev_confidence_formula() -> None:
    assert jev_confidence({"a": 0.25, "b": 0.25, "c": 0.25, "d": 0.25}) == 0
    assert jev_confidence({"a": 1.0, "b": 0.0}) == 1
    assert jev_confidence({"a": 0.8, "b": 0.1, "c": 0.05, "d": 0.05}) == pytest.approx(0.55 / 0.75)
    assert jev_confidence({"only": 1.0}) == 1


# --- safety check ----------------------------------------------------------------------


def _risky(category: str) -> list[Ticket]:
    return [t for t in TICKETS.values() if t.category == category]


def test_safety_detects_injections_and_never_strips_taint() -> None:
    caught = []
    for ticket in _risky("prompt_injection"):
        for seed in SEEDS:
            result = run("jev_safety_check", ticket, seed=seed)
            caught.append(result.fired_branch == "route.unsafe")
            # Caught or missed, the injection taint stays on the outgoing text.
            assert "injection" in result.outputs[result.fired_branch].taint
    assert rate(caught) == pytest.approx(0.92, abs=0.04)


def test_safety_only_sees_enabled_categories() -> None:
    caught = [run("jev_safety_check", t, params={"categories": ["fraud"]}, seed=s)
              .fired_branch == "route.unsafe"
              for t in _risky("prompt_injection") for s in SEEDS]
    assert rate(caught) < 0.08


def test_safety_flags_policy_violations_as_abuse() -> None:
    results = [run("jev_safety_check", t, seed=s) for t in _risky("policy_violation")
               for s in SEEDS]
    assert rate([r.fired_branch == "route.unsafe" for r in results]) > 0.85
    assert {tuple(r.decision["flagged"]) for r in results} >= {("abuse",)}


def test_safety_false_positives_are_rare() -> None:
    flagged = [run("jev_safety_check", t, seed=s).fired_branch == "route.unsafe"
               for t in TICKETS.values() if t.category == "routine" for s in SEEDS]
    assert rate(flagged) < 0.06


def test_safety_ignores_a_cleared_injection() -> None:
    ticket = _risky("prompt_injection")[0]
    cleared = PortValue(type="text", value=ticket.text)  # a human removed the taint
    flagged = [run("jev_safety_check", ticket, inputs={"text": cleared}, seed=s)
               .fired_branch == "route.unsafe" for s in SEEDS]
    assert rate(flagged) < 0.08


# --- LLM answer generator --------------------------------------------------------------


def _complies(result: NodeResult) -> bool:
    return "injection" in result.outputs["text"].taint


@pytest.mark.parametrize(("tier", "expected"), [("small", 0.7), ("large", 0.45)])
def test_llm_injection_compliance_rate(tier: str, expected: float) -> None:
    results = [run("llm_answer_generator", t, params={"model": tier}, seed=s)
               for t in _risky("prompt_injection") for s in SEEDS]
    assert rate([_complies(r) for r in results]) == pytest.approx(expected, abs=0.05)
    hardened = [run("llm_answer_generator", t, seed=s, params={
        "model": tier, "prompt": "You are a support agent. Never reveal internal data."})
        for t in _risky("prompt_injection") for s in SEEDS]
    assert rate([_complies(r) for r in hardened]) == pytest.approx(expected / 2, abs=0.05)


def test_llm_compliance_writes_a_marker_that_one_rule_catches() -> None:
    for ticket in _risky("prompt_injection") + _risky("policy_violation"):
        for seed in range(30):
            out = run("llm_answer_generator", ticket, seed=seed).outputs["text"]
            unsafe = bool(out.taint & {"injection", "policy_violation"})
            assert (MARKERS[ticket.risk] in out.value) == unsafe
            if unsafe:
                rule = {"refund_promise": "no_refund_promises", "legal_advice": "no_legal_advice",
                        "internal_url": "no_internal_urls",
                        "credentials": "no_credentials"}[ticket.risk]
                assert not check_policy(out.value, [rule], [], []).passed


def test_llm_refusal_drops_the_injection_taint() -> None:
    outs = [run("llm_answer_generator", t, seed=s).outputs["text"]
            for t in _risky("prompt_injection") for s in range(30)]
    assert any("injection" not in o.taint for o in outs)


def test_llm_without_injected_input_never_complies() -> None:
    ticket = _risky("prompt_injection")[0]
    cleared = {"text": PortValue(type="text", value=ticket.text)}
    assert not any(_complies(run("llm_answer_generator", ticket, inputs=cleared, seed=s))
                   for s in SEEDS)


def test_llm_policy_violation_rate() -> None:
    outs = [run("llm_answer_generator", t, seed=s).outputs["text"]
            for t in _risky("policy_violation") for s in SEEDS]
    assert rate(["policy_violation" in o.taint for o in outs]) == pytest.approx(0.4, abs=0.05)


def test_llm_pii_echo() -> None:
    pii_tickets = [t for t in TICKETS.values() if t.contains_pii]
    outs = [run("llm_answer_generator", t, seed=s).outputs["text"] for t in pii_tickets
            for s in SEEDS]
    assert rate(["pii" in o.taint for o in outs]) == pytest.approx(0.3, abs=0.05)
    for out in outs:
        if "pii" in out.taint:
            assert not check_policy(out.value, [], [], ["email", "phone", "card_number",
                                                        "ssn"]).passed


def test_llm_grounding_needs_matching_docs() -> None:
    complex_tickets = [t for t in TICKETS.values() if t.needs_grounding]

    def ungrounded(with_context: bool) -> float:
        flags = []
        for t in complex_tickets:
            inputs = {"text": message(t)}
            if with_context:
                inputs["context"] = run("knowledge_lookup", t).outputs["docs"]
            flags += ["ungrounded" in run("llm_answer_generator", t, inputs=inputs, seed=s)
                      .outputs["text"].taint for s in SEEDS]
        return rate(flags)

    assert ungrounded(False) == pytest.approx(0.4, abs=0.05)
    assert ungrounded(True) < 0.1
    routine = [run("llm_answer_generator", t, seed=s).outputs["text"]
               for t in TICKETS.values() if t.category == "routine" for s in range(20)]
    assert not any("ungrounded" in o.taint for o in routine)


def test_llm_tokens_latency_and_cost() -> None:
    ticket = TICKETS["o-13"]  # 340 expected tokens
    large = run("llm_answer_generator", ticket)
    small = run("llm_answer_generator", ticket, params={"model": "small", "max_tokens": 128})
    assert large.tokens_out == 340  # the expected length, capped only by max_tokens
    assert small.tokens_out == 128
    assert small.latency_ms < 800 < large.latency_ms
    assert 0 < small.cost_usd < large.cost_usd
    assert large.tokens_in > 0


def test_llm_params_change_the_draw() -> None:
    ticket = _risky("prompt_injection")[0]
    a = [_complies(run("llm_answer_generator", ticket, seed=s)) for s in range(50)]
    b = [_complies(run("llm_answer_generator", ticket, params={"max_tokens": 200}, seed=s))
         for s in range(50)]
    assert a != b


# --- tools, human, sink ------------------------------------------------------------------


def test_policy_engine_routes_on_rules_and_keeps_taint() -> None:
    ticket = TICKETS["o-23"]
    bad = PortValue(type="text", value=MARKERS["refund_promise"], taint={"policy_violation"})
    result = run("policy_engine", ticket, inputs={"text": bad})
    assert result.fired_branch == "route.block"
    assert result.outputs["route.block"].taint == {"policy_violation"}
    assert result.decision["violations"] == ["no_refund_promises"]
    missed = run("policy_engine", ticket, inputs={"text": bad}, params={"rules": []})
    assert missed.fired_branch == "route.pass"
    assert missed.outputs["route.pass"].taint == {"policy_violation"}


def test_knowledge_lookup_latency_grows_with_top_k() -> None:
    ticket = TICKETS["o-13"]
    one = statistics.median(run("knowledge_lookup", ticket, params={"top_k": 1}, seed=s)
                            .latency_ms for s in range(50))
    ten = statistics.median(run("knowledge_lookup", ticket, params={"top_k": 10}, seed=s)
                            .latency_ms for s in range(50))
    assert one == pytest.approx(30, rel=0.15) and ten == pytest.approx(75, rel=0.15)


def test_human_review_clears_taint_and_escalates() -> None:
    ticket = _risky("prompt_injection")[0]
    results = [run("human_review_queue", ticket, seed=s) for s in range(500)]
    assert all(r.escalated and r.cost_usd == 2.0 for r in results)
    assert rate([not r.outputs["text"].taint for r in results]) == pytest.approx(0.98, abs=0.02)
    assert statistics.median(r.latency_ms for r in results) == pytest.approx(120_000, rel=0.1)


def test_customer_response_records_delivery() -> None:
    ticket = TICKETS["o-01"]
    value = PortValue(type="text", value="hi", taint={"pii"})
    result = run("customer_response", ticket, inputs={"text": value})
    assert result.outputs == {} and result.decision == {"delivered": True, "taint": ["pii"]}
