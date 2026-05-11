"""
Tests for the information environment.

Covers:
- Config validation
- Latent factor model determinism
- Cluster correlation structure (within-cluster high, cross-cluster low,
  independent low) — sampled across many seeds for statistical power
- Signal value distribution (mean ≈ logit(p*), std ≈ σ_signal)
- Tail signal distribution (mean ≈ logit(p*), std ≈ σ_tail < σ_signal)
- Aggregate rates and tail fractions match for both tail_modes
- "Separate" and "marked" modes statistically equivalent
- End-to-end determinism: same seed → same observed signal stream
"""
from __future__ import annotations

import math

import numpy as np
import pytest

from sim.information import (
    ClusterSpec,
    InformationConfig,
    InformationEnvironment,
    LatentFactorModel,
    Signal,
)
from sim.simulator import Simulator


# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------

def _run_and_collect(
    cfg: InformationConfig, seed: int, until_ts: int, time_resolution: int = 1000
) -> tuple[InformationEnvironment, list[Signal]]:
    rng = np.random.default_rng(seed)
    env = InformationEnvironment(cfg, rng)
    sim = Simulator(rng=rng, time_resolution=time_resolution)
    signals: list[Signal] = []
    sim.register_handler(
        InformationEnvironment.SIGNAL_EVENT,
        lambda s, ev: signals.append(ev.payload),
    )
    env.schedule_signals(sim, until_ts=until_ts)
    sim.run_until(until_ts)
    return env, signals


# -----------------------------------------------------------------------------
# Config validation
# -----------------------------------------------------------------------------

class TestConfigValidation:
    def test_rejects_zero_markets(self):
        cfg = InformationConfig(k=5)
        with pytest.raises(ValueError, match="zero markets"):
            cfg.validate()

    def test_rejects_cluster_factor_out_of_range(self):
        cfg = InformationConfig(
            k=3,
            clusters=[ClusterSpec(primary_factor=5, market_count=1)],
        )
        with pytest.raises(ValueError, match="primary_factor"):
            cfg.validate()

    def test_rejects_unknown_tail_mode(self):
        cfg = InformationConfig(
            k=5, n_independent_markets=1, tail_mode="bogus",
        )
        with pytest.raises(ValueError, match="tail_mode"):
            cfg.validate()

    def test_n_markets_computed(self):
        cfg = InformationConfig(
            k=5,
            clusters=[
                ClusterSpec(primary_factor=0, market_count=10),
                ClusterSpec(primary_factor=1, market_count=5),
            ],
            n_independent_markets=3,
        )
        assert cfg.n_markets == 18

    def test_rejects_negative_rates(self):
        cfg = InformationConfig(
            k=5, n_independent_markets=1, routine_rate_per_market=-1.0,
        )
        with pytest.raises(ValueError):
            cfg.validate()


# -----------------------------------------------------------------------------
# Latent factor model
# -----------------------------------------------------------------------------

class TestLatentFactorModel:
    def test_deterministic_from_seed(self):
        cfg = InformationConfig(
            k=5,
            clusters=[ClusterSpec(primary_factor=0, market_count=3)],
            n_independent_markets=2,
        )
        m1 = LatentFactorModel(cfg, np.random.default_rng(42))
        m2 = LatentFactorModel(cfg, np.random.default_rng(42))
        assert np.array_equal(m1.f, m2.f)
        for t1, t2 in zip(m1.truths, m2.truths):
            assert t1.market_id == t2.market_id
            assert t1.cluster_id == t2.cluster_id
            assert np.array_equal(t1.loadings, t2.loadings)
            assert t1.logit_p_star == t2.logit_p_star
            assert t1.p_star == t2.p_star

    def test_cluster_assignment(self):
        cfg = InformationConfig(
            k=5,
            clusters=[
                ClusterSpec(primary_factor=0, market_count=3),
                ClusterSpec(primary_factor=2, market_count=2),
            ],
            n_independent_markets=2,
        )
        model = LatentFactorModel(cfg, np.random.default_rng(0))
        assert [t.cluster_id for t in model.truths] == [0, 0, 0, 1, 1, None, None]

    def test_p_star_in_unit_interval(self):
        cfg = InformationConfig(
            k=5,
            clusters=[ClusterSpec(primary_factor=0, market_count=5)],
            n_independent_markets=5,
        )
        model = LatentFactorModel(cfg, np.random.default_rng(7))
        ps = model.p_star_array
        assert np.all((ps > 0) & (ps < 1))
        # And consistent with logit
        np.testing.assert_allclose(
            ps, 1.0 / (1.0 + np.exp(-model.logit_p_star_array)), rtol=1e-12
        )

    def test_loadings_matrix_shape(self):
        cfg = InformationConfig(
            k=5,
            clusters=[ClusterSpec(primary_factor=0, market_count=4)],
            n_independent_markets=3,
        )
        model = LatentFactorModel(cfg, np.random.default_rng(0))
        assert model.loadings_matrix.shape == (7, 5)


# -----------------------------------------------------------------------------
# Cluster correlation structure
# -----------------------------------------------------------------------------

def _logits_across_seeds(cfg, market_indices, n_seeds=300):
    """Return shape (n_seeds, len(market_indices)) of logit_p_star values."""
    out = np.zeros((n_seeds, len(market_indices)))
    for i in range(n_seeds):
        model = LatentFactorModel(cfg, np.random.default_rng(i))
        for j, m in enumerate(market_indices):
            out[i, j] = model.truths[m].logit_p_star
    return out


class TestClusterCorrelation:
    def test_within_cluster_high_correlation(self):
        cfg = InformationConfig(
            k=5,
            clusters=[ClusterSpec(primary_factor=0, market_count=2,
                                   primary_loading_mean=1.5)],
            idiosyncratic_std=0.5,
        )
        logits = _logits_across_seeds(cfg, [0, 1], n_seeds=300)
        corr = float(np.corrcoef(logits[:, 0], logits[:, 1])[0, 1])
        assert corr > 0.5, f"within-cluster correlation {corr:.3f} too low"

    def test_cross_cluster_low_correlation(self):
        cfg = InformationConfig(
            k=5,
            clusters=[
                ClusterSpec(primary_factor=0, market_count=1, primary_loading_mean=1.5),
                ClusterSpec(primary_factor=1, market_count=1, primary_loading_mean=1.5),
            ],
        )
        logits = _logits_across_seeds(cfg, [0, 1], n_seeds=300)
        corr = float(np.corrcoef(logits[:, 0], logits[:, 1])[0, 1])
        assert abs(corr) < 0.25, f"cross-cluster correlation {corr:.3f} too high"

    def test_independent_market_low_correlation_with_cluster(self):
        cfg = InformationConfig(
            k=5,
            clusters=[ClusterSpec(primary_factor=0, market_count=1, primary_loading_mean=1.5)],
            n_independent_markets=1,
        )
        logits = _logits_across_seeds(cfg, [0, 1], n_seeds=300)
        corr = float(np.corrcoef(logits[:, 0], logits[:, 1])[0, 1])
        assert abs(corr) < 0.25, f"cluster-vs-independent correlation {corr:.3f} too high"


# -----------------------------------------------------------------------------
# Signal distribution
# -----------------------------------------------------------------------------

class TestSignalDistribution:
    def test_routine_signal_mean_and_std(self):
        """Signals on a single market should be centered on logit(p*) with σ_signal noise."""
        cfg = InformationConfig(
            k=5,
            clusters=[],
            n_independent_markets=1,
            routine_rate_per_market=10.0,
            tail_rate_per_market=0.0,
            signal_noise_std=1.0,
        )
        env, signals = _run_and_collect(cfg, seed=42, until_ts=200_000)  # ~2000 signals

        values = np.array([s.value for s in signals])
        assert len(values) > 1500  # rate=10, horizon=200 → expect ~2000

        expected_mean = env.world.truths[0].logit_p_star
        # SE = σ / sqrt(N), at N=2000, σ=1 → SE ≈ 0.022; use 5*SE band
        se = 1.0 / math.sqrt(len(values))
        assert abs(values.mean() - expected_mean) < 5 * se, (
            f"sample mean {values.mean():.4f} vs expected {expected_mean:.4f}"
        )
        # Std: with chi-squared distribution, SE on std ≈ σ/sqrt(2N) ≈ 0.016
        assert abs(values.std(ddof=1) - 1.0) < 0.1

    def test_tail_signal_has_lower_noise(self):
        """Tail signals should be tighter around logit(p*) than routine signals."""
        cfg = InformationConfig(
            k=5, clusters=[], n_independent_markets=1,
            routine_rate_per_market=5.0,
            tail_rate_per_market=5.0,  # equal rates so we get plenty of each
            signal_noise_std=1.0,
            tail_noise_std=0.3,
            tail_mode="separate",
        )
        env, signals = _run_and_collect(cfg, seed=7, until_ts=200_000)

        routine = np.array([s.value for s in signals if not s.is_tail])
        tail = np.array([s.value for s in signals if s.is_tail])
        assert len(routine) > 500 and len(tail) > 500

        expected = env.world.truths[0].logit_p_star
        assert abs(routine.std(ddof=1) - 1.0) < 0.15
        assert abs(tail.std(ddof=1) - 0.3) < 0.05
        # Both centered on the true logit
        assert abs(routine.mean() - expected) < 0.1
        assert abs(tail.mean() - expected) < 0.05


# -----------------------------------------------------------------------------
# Tail mode equivalence
# -----------------------------------------------------------------------------

class TestTailModes:
    def _config(self, mode: str) -> InformationConfig:
        return InformationConfig(
            k=5, clusters=[],
            n_independent_markets=10,
            routine_rate_per_market=2.0,
            tail_rate_per_market=0.2,
            signal_noise_std=1.0,
            tail_noise_std=0.4,
            tail_mode=mode,
        )

    def test_separate_mode_aggregate_rates(self):
        cfg = self._config("separate")
        _, signals = _run_and_collect(cfg, seed=11, until_ts=100_000)
        # Expected: 10 markets × (2 + 0.2) per unit × 100 units = 2200 total
        expected_total = 2200
        expected_tail = 200
        sigma_total = math.sqrt(expected_total)
        sigma_tail = math.sqrt(expected_tail)
        n_total = len(signals)
        n_tail = sum(1 for s in signals if s.is_tail)
        assert abs(n_total - expected_total) < 4 * sigma_total, n_total
        assert abs(n_tail - expected_tail) < 4 * sigma_tail, n_tail

    def test_marked_mode_aggregate_rates(self):
        cfg = self._config("marked")
        _, signals = _run_and_collect(cfg, seed=11, until_ts=100_000)
        expected_total = 2200
        expected_tail = 200
        sigma_total = math.sqrt(expected_total)
        sigma_tail = math.sqrt(expected_tail)
        n_total = len(signals)
        n_tail = sum(1 for s in signals if s.is_tail)
        assert abs(n_total - expected_total) < 4 * sigma_total, n_total
        assert abs(n_tail - expected_tail) < 4 * sigma_tail, n_tail

    def test_modes_have_same_expected_tail_fraction(self):
        """Aggregate tail fractions across many runs should match."""
        sep_fractions = []
        mrk_fractions = []
        for seed in range(20):
            _, sep_signals = _run_and_collect(
                self._config("separate"), seed=seed, until_ts=30_000
            )
            _, mrk_signals = _run_and_collect(
                self._config("marked"), seed=seed, until_ts=30_000
            )
            sep_fractions.append(
                sum(1 for s in sep_signals if s.is_tail) / len(sep_signals)
            )
            mrk_fractions.append(
                sum(1 for s in mrk_signals if s.is_tail) / len(mrk_signals)
            )
        # Both should converge to 0.2 / 2.2 ≈ 0.0909
        expected = 0.2 / 2.2
        assert abs(np.mean(sep_fractions) - expected) < 0.02
        assert abs(np.mean(mrk_fractions) - expected) < 0.02
        # And the two modes should agree
        assert abs(np.mean(sep_fractions) - np.mean(mrk_fractions)) < 0.02

    def test_returned_counts_match_observed(self):
        cfg = self._config("separate")
        rng = np.random.default_rng(99)
        env = InformationEnvironment(cfg, rng)
        sim = Simulator(rng=rng, time_resolution=1000)
        observed_routine = [0]
        observed_tail = [0]

        def handler(s, ev):
            if ev.payload.is_tail:
                observed_tail[0] += 1
            else:
                observed_routine[0] += 1

        sim.register_handler(InformationEnvironment.SIGNAL_EVENT, handler)
        counts = env.schedule_signals(sim, until_ts=50_000)
        sim.run_until(50_000)
        assert counts["routine"] == observed_routine[0]
        assert counts["tail"] == observed_tail[0]
        assert counts["total"] == counts["routine"] + counts["tail"]


# -----------------------------------------------------------------------------
# End-to-end determinism
# -----------------------------------------------------------------------------

class TestDeterminism:
    def _trajectory(self, seed: int, mode: str):
        cfg = InformationConfig(
            k=5,
            clusters=[ClusterSpec(primary_factor=0, market_count=3)],
            n_independent_markets=2,
            routine_rate_per_market=2.0,
            tail_rate_per_market=0.2,
            tail_mode=mode,
        )
        _, signals = _run_and_collect(cfg, seed=seed, until_ts=20_000)
        return [(s.market_id, s.is_tail, s.value, s.noise_std) for s in signals]

    def test_same_seed_same_trajectory_separate(self):
        a = self._trajectory(seed=42, mode="separate")
        b = self._trajectory(seed=42, mode="separate")
        assert a == b
        assert len(a) > 0

    def test_same_seed_same_trajectory_marked(self):
        a = self._trajectory(seed=42, mode="marked")
        b = self._trajectory(seed=42, mode="marked")
        assert a == b
        assert len(a) > 0

    def test_different_seeds_diverge(self):
        a = self._trajectory(seed=1, mode="separate")
        b = self._trajectory(seed=2, mode="separate")
        assert a != b

    def test_double_schedule_raises(self):
        cfg = InformationConfig(k=5, n_independent_markets=1)
        rng = np.random.default_rng(0)
        env = InformationEnvironment(cfg, rng)
        sim = Simulator(rng=rng, time_resolution=1000)
        env.schedule_signals(sim, until_ts=1000)
        with pytest.raises(RuntimeError):
            env.schedule_signals(sim, until_ts=2000)
