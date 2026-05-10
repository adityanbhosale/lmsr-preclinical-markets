"""
Discrete-event simulator core.

The simulator owns a clock, an event queue, and a handler registry. Handlers
are functions of (simulator, event) and are responsible for any new events
they need to schedule. Randomness flows through a single injected
`np.random.Generator` so runs are reproducible from the seed alone.

Time model: integer "ticks". The `time_resolution` parameter defines how many
ticks make up one "unit time" of the user's choosing (e.g. seconds). Rate
parameters passed to helpers like `schedule_poisson` are interpreted in those
unit-time terms.
"""
from __future__ import annotations

from typing import Any, Callable, Optional

import numpy as np

from sim.events import Event, EventQueue, EventPriority


# A handler takes the simulator (to schedule follow-ups, access RNG, read clock)
# and the event being processed. Return value is ignored.
EventHandler = Callable[["Simulator", Event], None]


class Simulator:
    """
    Discrete-event simulator with integer-tick time and deterministic ordering.

    Usage:
        rng = np.random.default_rng(seed)
        sim = Simulator(rng=rng, time_resolution=1000)  # 1000 ticks per unit time
        sim.register_handler("signal", on_signal)
        sim.schedule(delay=500, event_type="signal", payload={...})
        sim.run_until(60_000)
    """

    def __init__(self, rng: np.random.Generator, time_resolution: int = 1) -> None:
        if not isinstance(time_resolution, int) or time_resolution < 1:
            raise ValueError("time_resolution must be a positive integer")
        self.rng = rng
        self.time_resolution = time_resolution
        self.queue = EventQueue()
        self._now: int = 0
        self._handlers: dict[str, EventHandler] = {}
        self._processed: int = 0

    # ----- clock -----

    @property
    def now(self) -> int:
        """Current simulated time in integer ticks."""
        return self._now

    @property
    def now_time(self) -> float:
        """Current simulated time in unit-time (ticks / time_resolution)."""
        return self._now / self.time_resolution

    # ----- scheduling -----

    def register_handler(self, event_type: str, handler: EventHandler) -> None:
        if event_type in self._handlers:
            raise ValueError(f"handler already registered for {event_type!r}")
        self._handlers[event_type] = handler

    def schedule(
        self,
        delay: int,
        event_type: str,
        payload: Any = None,
        priority: int = EventPriority.DECISION,
    ) -> Event:
        """Schedule `delay` ticks from now."""
        if delay < 0:
            raise ValueError(f"cannot schedule in the past (delay={delay})")
        return self.queue.push(self._now + delay, event_type, payload, priority)

    def schedule_at(
        self,
        timestamp: int,
        event_type: str,
        payload: Any = None,
        priority: int = EventPriority.DECISION,
    ) -> Event:
        """Schedule at absolute tick `timestamp`."""
        if timestamp < self._now:
            raise ValueError(
                f"cannot schedule in the past (timestamp={timestamp} < now={self._now})"
            )
        return self.queue.push(timestamp, event_type, payload, priority)

    # ----- main loop -----

    def run_until(self, until_ts: int) -> int:
        """
        Process all events with timestamp <= until_ts. Returns count processed.
        Advances clock to until_ts even if the queue empties first.
        """
        n = 0
        while self.queue and self.queue.peek().timestamp <= until_ts:
            event = self.queue.pop()
            self._dispatch(event)
            n += 1
        if until_ts > self._now:
            self._now = until_ts
        return n

    def run_count(self, max_events: int) -> int:
        """Process up to `max_events` events. Returns count processed."""
        if max_events < 0:
            raise ValueError("max_events must be >= 0")
        n = 0
        while n < max_events and self.queue:
            event = self.queue.pop()
            self._dispatch(event)
            n += 1
        return n

    def _dispatch(self, event: Event) -> None:
        # Advance clock first so handlers see correct `now`.
        self._now = event.timestamp
        handler = self._handlers.get(event.event_type)
        if handler is None:
            raise KeyError(f"no handler registered for event_type {event.event_type!r}")
        handler(self, event)
        self._processed += 1

    @property
    def events_processed(self) -> int:
        return self._processed


# -----------------------------------------------------------------------------
# Poisson scheduling helper
# -----------------------------------------------------------------------------

def schedule_poisson(
    sim: Simulator,
    rate_per_unit_time: float,
    event_type: str,
    until_ts: int,
    payload_fn: Optional[Callable[["Simulator"], Any]] = None,
    priority: int = EventPriority.SIGNAL,
) -> int:
    """
    Pre-schedule a homogeneous Poisson process of arrivals into the queue,
    from `sim.now` to `until_ts` inclusive. Returns count scheduled.

    Interarrivals are sampled as float exponentials, accumulated in continuous
    time, then rounded to the nearest integer tick at insertion. Multiple
    arrivals may collide on the same tick; `insertion_order` makes the order
    deterministic.

    Notes:
    - `rate_per_unit_time` is in unit-time terms. If `sim.time_resolution =
      1000` and you pass `rate=2.0`, expect 2 arrivals per 1000 ticks on
      average.
    - For `rate * (until_ts - sim.now) / time_resolution >> 1`, discretization
      error from rounding is statistically negligible.
    - For non-homogeneous or state-dependent rates, use a renewal pattern
      instead: each handler schedules its successor.
    """
    if rate_per_unit_time <= 0:
        return 0

    start_tick = sim.now
    if until_ts <= start_tick:
        return 0

    rate_per_tick = rate_per_unit_time / sim.time_resolution
    if rate_per_tick <= 0:
        return 0

    n_scheduled = 0
    t_cont = float(start_tick)
    while True:
        gap = sim.rng.exponential(1.0 / rate_per_tick)
        t_cont += gap
        if t_cont > until_ts:
            break
        t_tick = int(round(t_cont))
        if t_tick < sim.now:
            t_tick = sim.now
        if t_tick > until_ts:
            break
        payload = payload_fn(sim) if payload_fn is not None else None
        sim.schedule_at(t_tick, event_type, payload, priority)
        n_scheduled += 1

    return n_scheduled
