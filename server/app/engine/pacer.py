"""Replays a computed run's events on a wall-clock schedule (decision Q1, refining D5).

The run is computed in full first; the pacer only delivers its numbered events, each at
sim_ms / speed after the start, so edge animations are watchable. Stopping cancels the replay
and delivers the closing events the caller builds from what was delivered so far.
"""

import asyncio
import time
from collections.abc import Awaitable, Callable, Sequence

from app.models.events import EventBase

Deliver = Callable[[EventBase], None]  # synchronous, so a stop never splits a delivery
StopEvents = Callable[[list[EventBase]], list[EventBase]]


class Pacer:
    def __init__(
        self,
        events: Sequence[EventBase],
        speed: float,
        deliver: Deliver,
        *,
        stop_events: StopEvents | None = None,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self.events = events
        self._speed = speed
        self._deliver = deliver
        self._stop_events = stop_events
        self._clock = clock
        self._sleep = sleep
        self._task: asyncio.Task[None] | None = None
        self._ended = asyncio.Event()  # set once the last event, or the stop's closing ones, went out
        self.delivered: list[EventBase] = []
        self.stopped = False

    def start(self) -> asyncio.Task[None]:
        self._task = asyncio.create_task(self._play())
        return self._task

    async def wait(self) -> None:
        """Returns when every event has been delivered, or a stop has delivered its closing events.
        Re-raises an error the replay hit."""
        if self._task is None:
            return
        await self._ended.wait()
        if self._task.done() and not self._task.cancelled() and self._task.exception() is not None:
            raise self._task.exception()

    @property
    def finished(self) -> bool:
        return self.stopped or len(self.delivered) == len(self.events)

    async def stop(self) -> bool:
        """Stops a replay still playing and delivers its closing events; False if it had finished."""
        if self.finished:
            return False
        self.stopped = True
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        try:
            for event in self._stop_events(self.delivered) if self._stop_events else []:
                self._deliver(event)
                self.delivered.append(event)
        finally:
            self._ended.set()
        return True

    async def _play(self) -> None:
        try:
            start = self._clock()
            for event in self.events:
                delay = start + event.sim_ms / self._speed / 1000 - self._clock()
                if delay > 0:
                    await self._sleep(delay)
                self._deliver(event)
                self.delivered.append(event)
        finally:
            if not self.stopped:  # a stop sets it after its closing events
                self._ended.set()
