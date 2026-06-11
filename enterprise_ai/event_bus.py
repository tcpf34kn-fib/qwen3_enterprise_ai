from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import Any

from .domain import utc_now_iso


@dataclass
class Event:
    event_type: str
    task_id: str
    payload: dict[str, Any]
    created_at: str = field(default_factory=utc_now_iso)


class InMemoryEventBus:
    """Small event bus for local development.

    Replace this with Kafka, RabbitMQ, NATS, Redis Streams, or cloud queues in production.
    """

    def __init__(self) -> None:
        self._events: deque[Event] = deque()

    def publish(self, event_type: str, task_id: str, payload: dict[str, Any]) -> Event:
        event = Event(event_type=event_type, task_id=task_id, payload=payload)
        self._events.append(event)
        return event

    def consume(self) -> Event | None:
        if not self._events:
            return None
        return self._events.popleft()

    def snapshot(self) -> list[dict[str, Any]]:
        return [event.__dict__ for event in self._events]

