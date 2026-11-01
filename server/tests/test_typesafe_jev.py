"""The live Jev provider, through the real SDK against a fake HTTP transport: no network, no key."""

import asyncio
import json
import random

import httpx2
import pytest
from sqlalchemy.orm import sessionmaker
from typesafe_sdk import RetryPolicy

from app.config import JEV_MODEL, JEV_PRICE_PER_1K_INPUT_USD
from app.db.base import Base
from app.db.session import make_engine
from app.engine.envelope import make_context
from app.models import PortValue
from app.providers.base import JevQuestion, ProviderCall, ProviderFailure
from app.providers.call_store import CallStore
from app.providers.jev_wording import (CRITERIA_BY_QUESTION, INTENT_CRITERIA, INTENT_INSTRUCTIONS,
                                       SAFETY_INSTRUCTIONS)
from app.providers.typesafe_jev import TypeSafeJevProvider, build_request
from app.runners.jev import IntentRouterRunner, SafetyCheckRunner
from app.simulation.loader import load_pack

TICKET = load_pack("practice").tickets[0]  # expected intent: billing
INTENTS = ["billing", "technical_support", "bug_report", "feature_request"]
PROBS = {"billing": 0.91, "technical_support": 0.05, "bug_report": 0.03, "feature_request": 0.01}
NO_WAIT = RetryPolicy(max_retries=1, backoff_initial=0, backoff_max=0)


def question(options: list[str] = INTENTS) -> JevQuestion:
    return JevQuestion(id="intent", kind="choice", prompt=INTENT_INSTRUCTIONS, options=options)


def body(probs: dict[str, float] = PROBS, *, choice: str = "billing", name: str = "intent",
         confidence: float = 0.88) -> dict:
    return {"model": JEV_MODEL, "usage": {"input_tokens": 1000, "output_tokens": 9},
            "answers": {name: {"type": "choice", "choice": choice, "confidence": confidence,
                               "probabilities": probs}}}


class FakeApi:
    """Answers with the queued replies in turn (the last repeats) and records what it was sent."""

    def __init__(self, *replies: dict | int | Exception) -> None:
        self.replies, self.sent = list(replies), []

    def __call__(self, request: httpx2.Request) -> httpx2.Response:
        self.sent.append(json.loads(request.content))
        reply = self.replies.pop(0) if len(self.replies) > 1 else self.replies[0]
        if isinstance(reply, Exception):
            raise reply
        if isinstance(reply, int):
            return httpx2.Response(reply, json={"error": "secret ticket text echoed"})
        return httpx2.Response(200, json=reply)


@pytest.fixture
def store(empty_db_url: str):
    engine = make_engine(empty_db_url)
    Base.metadata.create_all(engine)
    yield CallStore(sessionmaker(bind=engine, expire_on_commit=False), 1.0)
    engine.dispose()


def provider(store: CallStore, api: FakeApi) -> TypeSafeJevProvider:
    return TypeSafeJevProvider(store, "test-key", transport=httpx2.MockTransport(api), retry=NO_WAIT)


def ask(jev: TypeSafeJevProvider, text: str = TICKET.text, options: list[str] = INTENTS):
    async def run():
        try:
            return await jev.ask(text, [question(options)], ProviderCall(TICKET, random.Random(0)))
        finally:
            await jev.aclose()
    return asyncio.run(run())


def test_the_request_on_the_wire(store: CallStore) -> None:
    api = FakeApi(body())
    ask(provider(store, api))
    sent = api.sent[0]
    assert sent["model"] == JEV_MODEL and sent["state"] == TICKET.text
    asked = sent["questions"]["intent"]
    assert asked["type"] == "choice" and asked["instructions"] == INTENT_INSTRUCTIONS
    assert asked["criteria"] == {i: INTENT_CRITERIA[i] for i in INTENTS}


def test_the_answer_and_its_measured_cost(store: CallStore) -> None:
    [answer] = ask(provider(store, FakeApi(body())))
    assert (answer.question_id, answer.value, answer.confidence) == ("intent", "billing", 0.88)
    assert answer.probabilities.probs == pytest.approx(PROBS)
    assert answer.measure.cost_usd == pytest.approx(JEV_PRICE_PER_1K_INPUT_USD)
    assert answer.measure.tokens_in == 1000 and answer.measure.latency_ms >= 0
    assert answer.measure.replayed is False


def test_probabilities_that_only_nearly_sum_to_one_are_accepted(store: CallStore) -> None:
    [answer] = ask(provider(store, FakeApi(body({**PROBS, "billing": 0.9}))))
    assert sum(answer.probabilities.probs.values()) == pytest.approx(1)


def test_a_repeated_question_is_replayed_without_a_call(store: CallStore) -> None:
    api = FakeApi(body())
    [first] = ask(provider(store, api))
    [second] = ask(provider(store, api))
    assert len(api.sent) == 1
    assert second.measure.replayed is True
    assert second.value == first.value and second.measure.latency_ms == first.measure.latency_ms
    assert second.measure.cost_usd == first.measure.cost_usd


def test_the_order_of_allowed_intents_changes_nothing(store: CallStore) -> None:
    assert build_request("x", [question(INTENTS)]) == build_request("x", [question(INTENTS[::-1])])
    api = FakeApi(body())
    ask(provider(store, api))
    ask(provider(store, api), options=INTENTS[::-1])
    assert len(api.sent) == 1


def test_a_different_option_set_is_a_different_call(store: CallStore) -> None:
    api = FakeApi(body(), body({"billing": 0.9, "technical_support": 0.1}))
    ask(provider(store, api))
    ask(provider(store, api), options=INTENTS[:2])
    assert len(api.sent) == 2


def test_every_catalog_option_has_wording() -> None:
    from app.catalog.definitions.jev import INTENTS as ALL_INTENTS, JEV_SAFETY_CHECK
    assert set(ALL_INTENTS) == set(CRITERIA_BY_QUESTION["intent"])
    [categories] = [p for p in JEV_SAFETY_CHECK.params if p.key == "categories"]
    assert {"safe", *categories.options} == set(CRITERIA_BY_QUESTION["safety"])


@pytest.mark.parametrize("reply, code, retryable", [
    (429, "rate_limited", True),
    (500, "provider_error", True),
    (401, "provider_error", False),
    (httpx2.ReadTimeout("slow"), "timeout", True),
    (httpx2.ConnectError("down"), "provider_error", True),
])
def test_failures_are_mapped_and_never_stored(store: CallStore, reply, code, retryable) -> None:
    api = FakeApi(reply)
    with pytest.raises(ProviderFailure) as failure:
        ask(provider(store, api))
    assert (failure.value.code, failure.value.retryable) == (code, retryable)
    assert "secret" not in failure.value.message  # the body may quote the ticket
    good = FakeApi(body())
    assert ask(provider(store, good))[0].value == "billing"  # the failure wasn't replayed
    assert len(good.sent) == 1


def test_a_transient_failure_is_retried_once(store: CallStore) -> None:
    api = FakeApi(500, body())
    assert ask(provider(store, api))[0].value == "billing"
    assert len(api.sent) == 2
    failing = FakeApi(500)
    with pytest.raises(ProviderFailure):
        ask(provider(store, failing), options=INTENTS[:3])
    assert len(failing.sent) == 2


@pytest.mark.parametrize("reply", [
    body(name="other_question"),
    body({"billing": 1.0}),
    body(choice="not_an_option"),
    body(dict.fromkeys(INTENTS, 0.0)),
])
def test_an_answer_that_does_not_fit_fails_and_is_not_stored(store: CallStore, reply: dict) -> None:
    api = FakeApi(reply)
    with pytest.raises(ProviderFailure, match="unusable") as failure:
        ask(provider(store, api))
    assert failure.value.code == "provider_error" and failure.value.retryable is False
    assert ask(provider(store, FakeApi(body())))[0].value == "billing"


def test_the_spend_cap_is_a_node_failure_with_no_call(empty_db_url: str) -> None:
    engine = make_engine(empty_db_url)
    Base.metadata.create_all(engine)
    capped = CallStore(sessionmaker(bind=engine, expire_on_commit=False), 0)
    api = FakeApi(body())
    with pytest.raises(ProviderFailure) as failure:
        ask(provider(capped, api))
    engine.dispose()
    assert failure.value.code == "spend_cap" and api.sent == []


def test_no_client_opens_when_everything_replays(store: CallStore) -> None:
    ask(provider(store, FakeApi(body())))
    jev = provider(store, FakeApi(500))
    assert ask(jev)[0].measure.replayed is True
    assert jev._client is None


def test_questions_without_wording_are_a_programming_error() -> None:
    with pytest.raises(ValueError, match="no wording for options"):
        build_request("x", [question(["billing", "made_up"])])
    with pytest.raises(ValueError, match="no wording for Jev question"):
        build_request("x", [JevQuestion(id="tone", kind="choice", prompt="?", options=["a"])])
    with pytest.raises(ValueError, match="no wording for Jev question"):
        build_request("x", [JevQuestion(id="intent", kind="boolean", prompt="?")])


# The runners on the live provider.

def message() -> dict[str, PortValue]:
    return {"text": PortValue(type="text", value=TICKET.text)}


def run_node(runner, params: dict, jev: TypeSafeJevProvider):
    async def run():
        try:
            ctx = make_context(TICKET, run_seed=1, jev=jev)
            return await runner.run(message(), params, ctx)
        finally:
            await jev.aclose()
    return asyncio.run(run())


def test_the_router_uses_measured_latency_and_cost(store: CallStore) -> None:
    result = run_node(IntentRouterRunner(), {"allowed_intents": INTENTS, "threshold": 0.5},
                      provider(store, FakeApi(body())))
    assert result.fired_branch == "route.billing"
    assert result.cost_usd == pytest.approx(JEV_PRICE_PER_1K_INPUT_USD)
    assert (result.tokens_in, result.tokens_out, result.cached) == (1000, 9, False)


def test_the_threshold_gates_on_jevs_confidence(store: CallStore) -> None:
    result = run_node(IntentRouterRunner(), {"allowed_intents": INTENTS, "threshold": 0.9},
                      provider(store, FakeApi(body())))
    assert result.fired_branch == "route.low_confidence"


def test_a_failed_call_fails_the_node_and_keeps_its_time(store: CallStore) -> None:
    result = run_node(IntentRouterRunner(), {"allowed_intents": INTENTS, "threshold": 0.5},
                      provider(store, FakeApi(500)))
    assert result.error.code == "provider_error" and result.outputs == {}
    assert result.latency_ms > 0 and result.cost_usd == 0


def test_the_safety_check_on_the_live_provider(store: CallStore) -> None:
    probs = {"safe": 0.1, "prompt_injection": 0.8, "abuse": 0.1}
    api = FakeApi(body(probs, choice="prompt_injection", name="safety"))
    result = run_node(SafetyCheckRunner(), {"categories": ["prompt_injection", "abuse"],
                                            "threshold": 0.5}, provider(store, api))
    assert result.fired_branch == "route.unsafe"
    assert result.decision["flagged"] == ["prompt_injection"]
    assert api.sent[0]["questions"]["safety"]["instructions"] == SAFETY_INSTRUCTIONS


# scripts/live_check.py

def load_live_check():
    import importlib.util
    from pathlib import Path
    path = Path(__file__).parents[1] / "scripts" / "live_check.py"
    spec = importlib.util.spec_from_file_location("live_check", path)
    module = importlib.util.module_from_spec(spec)
    import sys
    sys.modules["live_check"] = module  # dataclasses look the module up by name
    spec.loader.exec_module(module)
    return module


def test_live_check_report(store: CallStore) -> None:
    check = load_live_check()
    pack = load_pack("practice").tickets
    right = ask(provider(store, FakeApi(body())))[0]                       # says billing, conf 0.88
    low = right.model_copy(update={"confidence": 0.2})
    lines = check.report([check.Row(pack[0], right), check.Row(pack[1], right),
                          check.Row(pack[2], low)], threshold=0.5)
    text = "\n".join(lines)
    assert "WRONG" in lines[2] and "WRONG" in lines[3]  # technical_support and bug_report tickets
    assert "low_confidence" in lines[3] and "WRONG" not in lines[1]
    [routine] = [line for line in lines if line.startswith("routine")]
    assert routine.split() == ["routine", "3", "1", "0.88", "0.54", "1", "1"]
    assert "3 real calls" in text
    assert TICKET.text not in text  # the report never prints message bodies


def test_live_check_refuses_without_a_key(monkeypatch: pytest.MonkeyPatch, capsys) -> None:
    from app.config import Settings
    check = load_live_check()
    monkeypatch.setattr(check, "get_settings", lambda: Settings(_env_file=None, typesafe_api_key=""))
    monkeypatch.setattr("sys.argv", ["live_check.py", "jev"])
    assert check.main() == 2
    assert "TYPESAFE_API_KEY" in capsys.readouterr().err


# A whole run in live mode, through compute(): worker thread, own event loop, shared store.

def answering_api(calls: list[dict]):
    def handle(request: httpx2.Request) -> httpx2.Response:
        sent = json.loads(request.content)
        calls.append(sent)
        options = list(sent["questions"]["intent"]["criteria"])
        probs = {o: 0.04 / (len(options) - 1) for o in options[1:]} | {options[0]: 0.96}
        return httpx2.Response(200, json=body(probs, choice=options[0]))
    return handle


def test_a_full_live_run_then_a_free_identical_one(empty_db_url: str, monkeypatch) -> None:
    from types import SimpleNamespace

    from app.catalog.default_graph import default_graph
    from app.config import Settings
    from app.db.session import get_db
    from app.models import RunConfig
    from app.providers import factory
    from app.simulation import manager

    engine = make_engine(empty_db_url)
    Base.metadata.create_all(engine)
    make_session = sessionmaker(bind=engine, expire_on_commit=False)

    def override():
        with make_session() as session:
            yield session

    calls: list[dict] = []
    live = Settings(_env_file=None, jev_mode="live", typesafe_api_key="test-key")
    monkeypatch.setattr(manager, "get_settings", lambda: live)
    monkeypatch.setattr(factory, "get_settings", lambda: live)
    real = TypeSafeJevProvider
    monkeypatch.setattr(factory, "TypeSafeJevProvider", lambda store, key: real(
        store, key, transport=httpx2.MockTransport(answering_api(calls)), retry=NO_WAIT))
    app = SimpleNamespace(state=SimpleNamespace(), dependency_overrides={get_db: override})
    config = RunConfig(mode="practice", pack_id="practice", seed=1, speed=1000, duration_s=1)

    def run(run_id: str):
        return asyncio.run(manager.compute(app, default_graph(), config, run_id=run_id,
                                           team_id="t", graph_version=1))

    first = run("r1")
    assert 0 < len(calls) <= len(load_pack("practice").tickets)
    assert all(c["model"] == JEV_MODEL for c in calls)
    made = len(calls)
    second = run("r2")
    assert len(calls) == made  # everything replayed
    assert second.metrics.model_dump() == first.metrics.model_dump()
    engine.dispose()
