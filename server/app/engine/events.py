"""Where the runner sends events. T5 records them in memory; M4 adds the pacer and WebSocket hub."""

from typing import Protocol

from app.models.events import EventBase


class EventSink(Protocol):
    def emit(self, event: EventBase) -> None: ...


class InMemorySink:
    def __init__(self) -> None:
        self.events: list[EventBase] = []

    def emit(self, event: EventBase) -> None:
        self.events.append(event)
