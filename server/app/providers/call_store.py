"""The call store: every real provider call is made once and replayed after that (U3, U4, U10).

Live providers (T36, T37) wrap each API call in `CallStore.call`. The key is a hash of the
provider, the model and the exact request fields, so the same request gets the same answer for
every team and every rerun (fair official runs, free practice reruns), and a restart keeps them.
A replay returns the measured latency of the original call, so timing replays too (U4).

Before a real call the day's spend (the sum of stored costs since midnight UTC; replays add
nothing) is checked against the cap, and SpendCapReached is raised at the cap (T38 turns that
into the mock fallback and a warning). Identical calls in flight at the same time share one real
call, across threads too: runs are computed in worker threads, each with its own event loop.
A per-provider limit caps the real calls in flight across all runs (U5). Time spent queueing for
a slot is not part of a call's measured latency: it depends on what else is running.
"""

import asyncio
import concurrent.futures
import hashlib
import json
import threading
import time
from collections import deque
from collections.abc import Awaitable, Callable
from contextlib import AbstractContextManager
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.orm import Session

from app.db import repo
from app.db.tables import ProviderCallRow

SessionScope = Callable[[], AbstractContextManager[Session]]


class SpendCapReached(RuntimeError):
    """The day's real spend has reached LIVE_SPEND_CAP_USD; no new real calls today."""


@dataclass(frozen=True)
class Fetched:
    """What a live provider's API call returns: its parsed response and usage."""

    response: dict[str, Any]
    tokens_in: int
    tokens_out: int
    cost_usd: float


@dataclass(frozen=True)
class StoredCall:
    response: dict[str, Any]
    latency_ms: float  # measured on the original call
    tokens_in: int
    tokens_out: int
    cost_usd: float  # of the original call; a replay itself is free
    replayed: bool  # True when no real call was made for this request


def call_key(provider: str, model: str, request: dict[str, Any]) -> str:
    payload = json.dumps({"provider": provider, "model": model, "request": request},
                         sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(payload.encode()).hexdigest()


def start_of_day(now: datetime) -> datetime:
    return now.astimezone(UTC).replace(hour=0, minute=0, second=0, microsecond=0)


class Limiter:
    """A semaphore across threads and event loops; asyncio's belongs to a single loop."""

    def __init__(self, slots: int) -> None:
        self._free = slots
        self._lock = threading.Lock()
        self._waiting: deque[tuple[asyncio.AbstractEventLoop, asyncio.Future[None]]] = deque()

    async def __aenter__(self) -> None:
        with self._lock:
            if self._free > 0:
                self._free -= 1
                return
            loop = asyncio.get_running_loop()
            turn: asyncio.Future[None] = loop.create_future()
            self._waiting.append((loop, turn))
        try:
            await turn
        except asyncio.CancelledError:
            with self._lock:
                if (loop, turn) in self._waiting:
                    self._waiting.remove((loop, turn))
                    raise
            await self.__aexit__()  # the slot was handed over as we were cancelled
            raise

    async def __aexit__(self, *_: object) -> None:
        with self._lock:
            if not self._waiting:
                self._free += 1
                return
            loop, turn = self._waiting.popleft()
        loop.call_soon_threadsafe(_grant, turn)


def _grant(turn: asyncio.Future[None]) -> None:
    if not turn.done():
        turn.set_result(None)


class CallStore:
    def __init__(self, sessions: SessionScope, spend_cap_usd: float, *,
                 limits: dict[str, int] | None = None,
                 clock: Callable[[], float] = time.perf_counter,
                 now: Callable[[], datetime] = lambda: datetime.now(UTC)) -> None:
        self._limiters = {name: Limiter(slots) for name, slots in (limits or {}).items()}
        self._sessions = sessions
        self._cap = spend_cap_usd
        self._clock = clock
        self._now = now
        self._lock = threading.Lock()
        self._in_flight: dict[str, concurrent.futures.Future[StoredCall]] = {}

    async def call(self, provider: str, model: str, request: dict[str, Any],
                   fetch: Callable[[], Awaitable[Fetched]]) -> StoredCall:
        key = call_key(provider, model, request)
        with self._lock:
            shared = self._in_flight.get(key)
            if shared is None:
                mine: concurrent.futures.Future[StoredCall] = concurrent.futures.Future()
                self._in_flight[key] = mine
        if shared is not None:
            return replace(await asyncio.wrap_future(shared), replayed=True)
        try:
            result = await self._lookup_or_fetch(key, provider, model, fetch)
        except BaseException as error:
            mine.set_exception(error)
            raise
        else:
            mine.set_result(result)
            return result
        finally:
            with self._lock:
                del self._in_flight[key]

    async def _lookup_or_fetch(self, key: str, provider: str, model: str,
                               fetch: Callable[[], Awaitable[Fetched]]) -> StoredCall:
        if (stored := await asyncio.to_thread(self._get, key)) is not None:
            return stored
        if await asyncio.to_thread(self._spent_today) >= self._cap:
            raise SpendCapReached(f"today's live spend has reached ${self._cap:.2f}")
        limiter = self._limiters.get(provider)
        if limiter is None:
            started = self._clock()
            fetched = await fetch()
            latency_ms = (self._clock() - started) * 1000
        else:
            async with limiter:
                started = self._clock()
                fetched = await fetch()
                latency_ms = (self._clock() - started) * 1000
        row = ProviderCallRow(key=key, provider=provider, model=model, response=fetched.response,
                              latency_ms=latency_ms, tokens_in=fetched.tokens_in,
                              tokens_out=fetched.tokens_out, cost_usd=fetched.cost_usd,
                              created_at=self._now())
        await asyncio.to_thread(self._put, row)
        return StoredCall(response=fetched.response, latency_ms=latency_ms,
                          tokens_in=fetched.tokens_in, tokens_out=fetched.tokens_out,
                          cost_usd=fetched.cost_usd, replayed=False)

    def _get(self, key: str) -> StoredCall | None:
        with self._sessions() as db:
            row = repo.get_provider_call(db, key)
            if row is None:
                return None
            return StoredCall(response=row.response, latency_ms=row.latency_ms,
                              tokens_in=row.tokens_in, tokens_out=row.tokens_out,
                              cost_usd=row.cost_usd, replayed=True)

    def _put(self, row: ProviderCallRow) -> None:
        with self._sessions() as db:
            repo.put_provider_call(db, row)  # a duplicate (another process) is fine to drop

    def _spent_today(self) -> float:
        with self._sessions() as db:
            return repo.spend_since(db, start_of_day(self._now()))

