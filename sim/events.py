"""
Event types and priority queue for the continuous-time simulator.

Determinism guarantees:
- Timestamps are integer ticks. Float math may be used during event scheduling
  (e.g. exponential interarrivals in `schedule_poisson`), but the final
  comparison key in the priority queue is always integer-valued.
- Events at the same (timestamp, priority) are processed in insertion order.
  Re-running with the same seed and the same scheduling sequence produces the
  same trajectory bit-for-bit.

Priority semantics: lower integer fires first. Use the `EventPriority`
constants where they apply, but priority is an open integer space — define
new levels in downstream modules as needed without touching this file.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional
import heapq


class EventPriority:
    """Conventional priority levels. Callers may use any integer."""
    SIGNAL = 0          # information arrivals — process before any reactions
    DECISION = 100      # agent decisions
    TRADE = 200         # trade execution
    BOOKKEEPING = 1000  # retreat updates, logging, periodic review checks


@dataclass(eq=False)
class Event:
    """
    A scheduled event.

    timestamp: integer tick at which to fire.
    priority: ordering within a timestamp (lower fires first).
    insertion_order: monotonic counter assigned at push time; resolves
                     remaining ties so ordering is total and deterministic.
    event_type: string discriminator for handler dispatch.
    payload: arbitrary handler-defined data (NOT part of the comparison key).
    """
    timestamp: int
    priority: int
    insertion_order: int
    event_type: str
    payload: Any = None

    def __lt__(self, other: "Event") -> bool:
        return (
            (self.timestamp, self.priority, self.insertion_order)
            < (other.timestamp, other.priority, other.insertion_order)
        )

    def __repr__(self) -> str:
        return (
            f"Event(t={self.timestamp}, prio={self.priority}, "
            f"seq={self.insertion_order}, type={self.event_type!r})"
        )


class EventQueue:
    """Priority queue of `Event`s. Lower (timestamp, priority, insertion_order) pops first."""

    def __init__(self) -> None:
        self._heap: list[Event] = []
        self._counter: int = 0

    def push(
        self,
        timestamp: int,
        event_type: str,
        payload: Any = None,
        priority: int = EventPriority.DECISION,
    ) -> Event:
        if not isinstance(timestamp, int) or isinstance(timestamp, bool):
            raise TypeError(
                f"timestamp must be int, got {type(timestamp).__name__}={timestamp!r}"
            )
        event = Event(
            timestamp=timestamp,
            priority=priority,
            insertion_order=self._counter,
            event_type=event_type,
            payload=payload,
        )
        self._counter += 1
        heapq.heappush(self._heap, event)
        return event

    def pop(self) -> Event:
        if not self._heap:
            raise IndexError("pop from empty EventQueue")
        return heapq.heappop(self._heap)

    def peek(self) -> Optional[Event]:
        return self._heap[0] if self._heap else None

    def __len__(self) -> int:
        return len(self._heap)

    def __bool__(self) -> bool:
        return bool(self._heap)

    @property
    def total_pushed(self) -> int:
        """Cumulative events ever pushed. Useful for determinism diagnostics."""
        return self._counter
