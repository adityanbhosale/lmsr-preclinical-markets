"""
Unit tests for the discrete-event simulator.

Includes the Task 1 validation requirement: scheduling a Poisson process into
the queue and confirming the empirical arrival rate matches theoretical
within reasonable statistical bounds. Three Poisson properties are checked
(count, interarrival mean, variance/mean ratio) so any of {rounding bias,
RNG misuse, off-by-one in scheduling} fails at least one test.
"""
from __future__ import annotations

import math

import numpy as np
import pytest

from sim.events import EventPriority
from sim.simulator import Simulator, schedule_poisson


# -----------------------------------------------------------------------------
# Basic scheduling / handler dispatch
# -----------------------------------------------------------------------------

class TestSimulatorBasics:
    def test_clock_starts_at_zero(self):
        sim = Simulator(rng=np.random.default_rng(0))
        assert sim.now == 0
        assert sim.now_time == 0.0

    def test_run_with_no_events_advances_clock(self):
        sim = Simulator(rng=np.random.default_rng(0))
        n = sim.run_until(100)
        assert n == 0
        assert sim.now == 100

    def test_handler_fires_and_advances_clock(self):
        sim = Simulator(rng=np.random.default_rng(0))
        seen = []
        sim.register_handler("x", lambda s, ev: seen.append((s.now, ev.payload)))
        sim.schedule(delay=10, event_type="x", payload="hello")
        sim.run_until(100)
        assert seen == [(10, "hello")]
        assert sim.now == 100
        assert sim.events_processed == 1

    def test_handler_can_schedule_followups(self):
        """Renewal pattern: each handler schedules the next event."""
        sim = Simulator(rng=np.random.default_rng(0))
        timestamps = []

        def on_tick(s, ev):
            timestamps.append(s.now)
            if s.now < 50:
                s.schedule(delay=10, event_type="tick")

        sim.register_handler("tick", on_tick)
        sim.schedule(delay=10, event_type="tick")
        sim.run_until(100)
        assert timestamps == [10, 20, 30, 40, 50]

    def test_unregistered_handler_raises(self):
        sim = Simulator(rng=np.random.default_rng(0))
        sim.schedule(delay=1, event_type="ghost")
        with pytest.raises(KeyError):
            sim.run_until(10)

    def test_duplicate_handler_registration_raises(self):
        sim = Simulator(rng=np.random.default_rng(0))
        sim.register_handler("x", lambda s, e: None)
        with pytest.raises(ValueError):
            sim.register_handler("x", lambda s, e: None)

    def test_cannot_schedule_in_past(self):
        sim = Simulator(rng=np.random.default_rng(0))
        sim.register_handler("x", lambda s, e: None)
        sim.schedule(delay=10, event_type="x")
        sim.run_until(20)
        with pytest.raises(ValueError):
            sim.schedule_at(10, "x")
        with pytest.raises(ValueError):
            sim.schedule(delay=-1, event_type="x")

    def test_run_count_bounds(self):
        sim = Simulator(rng=np.random.default_rng(0))
        fired = [0]
        sim.register_handler("x", lambda s, ev: fired.__setitem__(0, fired[0] + 1))
        for i in range(10):
            sim.schedule(delay=i + 1, event_type="x")
        n = sim.run_count(5)
        assert n == 5
        assert fired[0] == 5
        assert len(sim.queue) == 5

    def test_handler_observes_correct_now(self):
        """Clock must advance to event timestamp BEFORE the handler runs."""
        sim = Simulator(rng=np.random.default_rng(0))
        observed = []
        sim.register_handler("x", lambda s, ev: observed.append(s.now))
        sim.schedule_at(timestamp=42, event_type="x")
        sim.run_until(100)
        assert observed == [42]

    def test_now_time_scaling(self):
        sim = Simulator(rng=np.random.default_rng(0), time_resolution=1000)
        sim.register_handler("x", lambda s, ev: None)
        sim.schedule_at(timestamp=2500, event_type="x")
        sim.run_until(2500)
        assert sim.now == 2500
        assert sim.now_time == 2.5


# -----------------------------------------------------------------------------
# Determinism — engineering risk #2
# -----------------------------------------------------------------------------

class TestDeterminism:
    def _run_trajectory(self, seed: int) -> list[tuple[int, str, int]]:
        sim = Simulator(rng=np.random.default_rng(seed), time_resolution=1000)
        observed: list[tuple[int, str, int]] = []

        def on_signal(s, ev):
            observed.append((s.now, ev.event_type, ev.insertion_order))
            delay = int(s.rng.integers(1, 100))
            s.schedule(delay=delay, event_type="decision", priority=EventPriority.DECISION)

        def on_decision(s, ev):
            observed.append((s.now, ev.event_type, ev.insertion_order))

        sim.register_handler("signal", on_signal)
        sim.register_handler("decision", on_decision)
        schedule_poisson(sim, rate_per_unit_time=5.0, event_type="signal", until_ts=10_000)
        sim.run_until(20_000)
        return observed

    def test_same_seed_same_trajectory(self):
        a = self._run_trajectory(seed=42)
        b = self._run_trajectory(seed=42)
        assert a == b
        assert len(a) > 0  # sanity: something actually happened

    def test_different_seeds_diverge(self):
        a = self._run_trajectory(seed=1)
        b = self._run_trajectory(seed=2)
        assert a != b


# -----------------------------------------------------------------------------
# Priority within same timestamp
# -----------------------------------------------------------------------------

class TestPrioritySemantics:
    def test_signal_processed_before_decision_at_same_tick(self):
        sim = Simulator(rng=np.random.default_rng(0))
        order: list[str] = []
        sim.register_handler("signal", lambda s, ev: order.append("signal"))
        sim.register_handler("decision", lambda s, ev: order.append("decision"))
        # Schedule decision FIRST in insertion order, but signal has lower priority
        # number, so signal should still fire first.
        sim.schedule_at(50, "decision", priority=EventPriority.DECISION)
        sim.schedule_at(50, "signal", priority=EventPriority.SIGNAL)
        sim.run_until(100)
        assert order == ["signal", "decision"]


# -----------------------------------------------------------------------------
# Poisson validation — Task 1 spec requirement
# -----------------------------------------------------------------------------

class TestPoissonArrivals:
    """
    Validate `schedule_poisson` produces arrivals consistent with a homogeneous
    Poisson process: correct rate, exponential interarrivals, Poisson-distributed
    counts in fixed windows.
    """

    def test_empirical_rate_matches_theoretical(self):
        rate = 2.0  # 2 arrivals per unit time
        time_resolution = 1000  # 1000 ticks per unit time
        horizon_units = 1000.0
        horizon_ticks = int(horizon_units * time_resolution)
        expected = rate * horizon_units  # 2000 expected

        sim = Simulator(rng=np.random.default_rng(12345), time_resolution=time_resolution)
        arrivals: list[int] = []
        sim.register_handler("a", lambda s, ev: arrivals.append(s.now))
        n = schedule_poisson(sim, rate_per_unit_time=rate, event_type="a", until_ts=horizon_ticks)
        sim.run_until(horizon_ticks)
        assert n == len(arrivals)

        # Poisson(λ) std = sqrt(λ). At λ=2000, σ≈45. 4σ band → ~1-in-16k flake.
        sigma = math.sqrt(expected)
        assert abs(len(arrivals) - expected) < 4 * sigma, (
            f"got {len(arrivals)} arrivals, expected ~{expected:.0f} (±{4*sigma:.0f})"
        )

    def test_interarrival_mean_matches_theoretical(self):
        rate = 1.0
        time_resolution = 10_000  # high res so rounding bias is small
        horizon_units = 5000.0
        horizon_ticks = int(horizon_units * time_resolution)

        sim = Simulator(rng=np.random.default_rng(7), time_resolution=time_resolution)
        arrivals: list[int] = []
        sim.register_handler("a", lambda s, ev: arrivals.append(s.now))
        schedule_poisson(sim, rate_per_unit_time=rate, event_type="a", until_ts=horizon_ticks)
        sim.run_until(horizon_ticks)

        ts = np.array(arrivals, dtype=np.int64)
        gaps_units = np.diff(ts) / time_resolution
        # Exponential(rate=1): mean=1, std=1. SE of mean at N≈5000 is ~0.014.
        mean_gap = float(gaps_units.mean())
        assert abs(mean_gap - 1.0 / rate) < 0.05, (
            f"mean interarrival {mean_gap:.4f}, expected ~{1.0/rate:.4f}"
        )

    def test_window_counts_have_poisson_variance(self):
        """For Poisson, variance ≈ mean. Catches non-Poisson bugs the count test misses."""
        rate = 5.0
        time_resolution = 1000
        n_windows = 200
        window_units = 10.0
        window_ticks = int(window_units * time_resolution)
        horizon_ticks = n_windows * window_ticks

        sim = Simulator(rng=np.random.default_rng(2024), time_resolution=time_resolution)
        arrivals: list[int] = []
        sim.register_handler("a", lambda s, ev: arrivals.append(s.now))
        schedule_poisson(sim, rate_per_unit_time=rate, event_type="a", until_ts=horizon_ticks)
        sim.run_until(horizon_ticks)

        ts = np.array(arrivals, dtype=np.int64)
        bins = np.arange(0, horizon_ticks + 1, window_ticks)
        counts, _ = np.histogram(ts, bins=bins)

        expected_lambda = rate * window_units  # 50 per window
        mean = float(counts.mean())
        var = float(counts.var())
        assert abs(mean - expected_lambda) < 3.0, f"mean {mean} far from {expected_lambda}"
        ratio = var / mean
        assert 0.5 < ratio < 2.0, f"variance/mean ratio {ratio:.3f} inconsistent with Poisson"

    def test_zero_rate_schedules_nothing(self):
        sim = Simulator(rng=np.random.default_rng(0), time_resolution=1000)
        n = schedule_poisson(sim, rate_per_unit_time=0.0, event_type="a", until_ts=10_000)
        assert n == 0
        assert len(sim.queue) == 0

    def test_payload_fn_called_per_arrival(self):
        sim = Simulator(rng=np.random.default_rng(99), time_resolution=1000)
        payloads: list = []
        sim.register_handler("a", lambda s, ev: payloads.append(ev.payload))
        schedule_poisson(
            sim,
            rate_per_unit_time=10.0,
            event_type="a",
            until_ts=10_000,
            payload_fn=lambda s: int(s.rng.integers(0, 100)),
        )
        sim.run_until(10_000)
        assert len(payloads) > 50
        assert all(isinstance(p, int) and 0 <= p < 100 for p in payloads)
