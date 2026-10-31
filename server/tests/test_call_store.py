"""The call store (U3, U4, U10): replays, measured latency, the daily spend cap, shared calls."""

import asyncio
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.db.session import make_engine
from app.providers.call_store import CallStore, Fetched, SpendCapReached, call_key, start_of_day

NOON = datetime(2026, 10, 31, 12, 0, tzinfo=UTC)


class FakeClock:
    """perf_counter stand-in; the fake API advances it by its call time."""

    def __init__(self) -> None:
        self.t = 0.0

    def __call__(self) -> float:
        return self.t


class Api:
    """A fake provider API that counts its calls."""

    def __init__(self, clock: FakeClock, seconds: float = 0.25, cost: float = 1.0) -> None:
        self.clock, self.seconds, self.cost, self.calls = clock, seconds, cost, 0

    def fetch(self, answer: str = "ok", fail: bool = False):
        async def _fetch() -> Fetched:
            self.calls += 1
            await asyncio.sleep(0.01)
            self.clock.t += self.seconds
            if fail:
                raise TimeoutError("provider timed out")
            return Fetched(response={"answer": answer}, tokens_in=100, tokens_out=20,
                           cost_usd=self.cost)
        return _fetch


@pytest.fixture
def sessions(empty_db_url: str):
    engine = make_engine(empty_db_url)
    Base.metadata.create_all(engine)
    yield sessionmaker(bind=engine, expire_on_commit=False)
    engine.dispose()


def store(sessions, cap: float = 10.0, now: datetime = NOON, clock: FakeClock | None = None):
    clock = clock or FakeClock()
    return CallStore(sessions, cap, clock=clock, now=lambda: now), clock


def test_call_key_is_stable_and_specific() -> None:
    a = call_key("gemini", "m", {"prompt": "p", "text": "t"})
    assert a == call_key("gemini", "m", {"text": "t", "prompt": "p"})  # field order is irrelevant
    assert len({a, call_key("claude", "m", {"prompt": "p", "text": "t"}),
                call_key("gemini", "m2", {"prompt": "p", "text": "t"}),
                call_key("gemini", "m", {"prompt": "p", "text": "u"})}) == 4


def test_a_real_call_is_made_once_then_replayed_with_its_latency(sessions) -> None:
    calls, clock = store(sessions)
    api = Api(clock)
    first = asyncio.run(calls.call("gemini", "m", {"text": "hi"}, api.fetch()))
    again = asyncio.run(calls.call("gemini", "m", {"text": "hi"}, api.fetch()))
    assert api.calls == 1
    assert not first.replayed and again.replayed
    assert first.latency_ms == again.latency_ms == pytest.approx(250)
    assert again.response == {"answer": "ok"} and (again.tokens_in, again.tokens_out) == (100, 20)


def test_replays_survive_a_new_store(sessions) -> None:
    calls, clock = store(sessions)
    asyncio.run(calls.call("jev", "jev-1.14.0", {"state": "x"}, Api(clock).fetch()))
    restarted, clock2 = store(sessions)
    api = Api(clock2)
    assert asyncio.run(restarted.call("jev", "jev-1.14.0", {"state": "x"}, api.fetch())).replayed
    assert api.calls == 0


def test_a_different_request_is_a_new_call(sessions) -> None:
    calls, clock = store(sessions)
    api = Api(clock)
    asyncio.run(calls.call("gemini", "m", {"text": "a"}, api.fetch("A")))
    second = asyncio.run(calls.call("gemini", "m", {"text": "b"}, api.fetch("B")))
    assert api.calls == 2 and second.response == {"answer": "B"}


def test_the_daily_cap_stops_new_calls_but_not_replays(sessions) -> None:
    calls, clock = store(sessions, cap=10.0)
    api = Api(clock, cost=6.0)
    asyncio.run(calls.call("gemini", "m", {"n": 1}, api.fetch()))  # spent 0 before
    asyncio.run(calls.call("gemini", "m", {"n": 2}, api.fetch()))  # spent 6 before
    with pytest.raises(SpendCapReached):
        asyncio.run(calls.call("gemini", "m", {"n": 3}, api.fetch()))  # spent 12
    assert api.calls == 2
    assert asyncio.run(calls.call("gemini", "m", {"n": 1}, api.fetch())).replayed

    tomorrow, clock2 = store(sessions, cap=10.0, now=NOON + timedelta(days=1))
    assert not asyncio.run(tomorrow.call("gemini", "m", {"n": 3}, Api(clock2, cost=6.0).fetch())).replayed


def test_a_zero_cap_allows_no_real_calls(sessions) -> None:
    calls, clock = store(sessions, cap=0)
    with pytest.raises(SpendCapReached):
        asyncio.run(calls.call("gemini", "m", {"n": 1}, Api(clock).fetch()))


def test_identical_calls_in_flight_share_one_real_call(sessions) -> None:
    calls, clock = store(sessions)
    api = Api(clock)

    async def both():
        return await asyncio.gather(*(calls.call("gemini", "m", {"text": "hi"}, api.fetch())
                                      for _ in range(3)))

    results = asyncio.run(both())
    assert api.calls == 1
    assert [r.replayed for r in results] == [False, True, True]
    assert len({r.latency_ms for r in results}) == 1


def test_a_failed_call_is_not_stored(sessions) -> None:
    calls, clock = store(sessions)
    api = Api(clock)
    with pytest.raises(TimeoutError):
        asyncio.run(calls.call("gemini", "m", {"text": "hi"}, api.fetch(fail=True)))
    assert not asyncio.run(calls.call("gemini", "m", {"text": "hi"}, api.fetch())).replayed
    assert api.calls == 2


def test_start_of_day_is_utc_midnight() -> None:
    warsaw = datetime(2026, 11, 1, 0, 30, tzinfo=UTC) + timedelta(hours=1)
    assert start_of_day(warsaw) == datetime(2026, 11, 1, 0, 0, tzinfo=UTC)
