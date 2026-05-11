"""
Tests for sim/runner_agentic.py.

Covers:
  - End-to-end sanity (no crash, RunResults fields populated)
  - Brier score computation
  - Snapshot timing (t=0, multiples of interval, t=horizon)
  - Snapshot record schema
  - Flat-record accessors (trade_records, agent_summary_records,
    summary_record) — these are the parquet-bound interfaces Task 9 calls
  - Determinism: same seed → bit-identical results
  - Different seeds → different results
  - Validation
  - Mixed integration with all four agent classes from Tasks 4-7
"""
from __future__ import annotations

import math
import numpy as np
import pytest

from sim.agentic import (
    AggregationDepthAgent,
    CrossMarketConsistencyAgent,
    NaiveCredentialedAgent,
    NoiseTrader,
    TailEventReasoningAgent,
    base_rates_from_truth,
    cross_weights_from_loadings,
    make_cross_market_agent,
)
from sim.information import ClusterSpec, InformationConfig
from sim.market_env import MarketSpec
from sim.runner_agentic import RunResults, run_sim, SNAPSHOT_EVENT


# =============================================================================
# Helpers
# =============================================================================

def _simple_cfg(n_markets: int = 2, k: int = 2) -> InformationConfig:
    return InformationConfig(
        k=k,
        clusters=[ClusterSpec(primary_factor=0, market_count=n_markets)],
        routine_rate_per_market=3.0,
        tail_rate_per_market=0.0,
    )


def _make_naive(info_env, rng):
    market_ids = tuple(range(info_env.n_markets))
    return [
        NaiveCredentialedAgent(
            agent_id=0, budget=100.0, market_ids=market_ids,
            observation_delay=50, review_interval=1000,
        ),
    ]


# =============================================================================
# Sanity / end-to-end
# =============================================================================

class TestRunSimBasics:
    def test_returns_run_results(self):
        res = run_sim(_simple_cfg(), _make_naive, horizon=5_000, seed=0)
        assert isinstance(res, RunResults)

    def test_fields_populated(self):
        res = run_sim(_simple_cfg(n_markets=3), _make_naive, horizon=5_000, seed=0)
        assert res.seed == 0
        assert res.horizon == 5_000
        assert res.n_markets == 3
        assert res.info_env is not None
        assert res.market_env is not None
        assert len(res.agents) == 1
        assert len(res.snapshots) > 0

    def test_brier_per_market_shape_and_range(self):
        res = run_sim(_simple_cfg(n_markets=4), _make_naive, horizon=5_000, seed=0)
        b = res.brier_per_market()
        assert b.shape == (4,)
        assert np.all(b >= 0)
        assert np.all(b <= 1)

    def test_final_prices_match_market_env(self):
        res = run_sim(_simple_cfg(), _make_naive, horizon=5_000, seed=0)
        np.testing.assert_array_equal(
            res.final_prices_yes, res.market_env.prices_yes()
        )

    def test_p_star_matches_info_env(self):
        res = run_sim(_simple_cfg(), _make_naive, horizon=5_000, seed=0)
        np.testing.assert_array_equal(
            res.p_star, res.info_env.world.p_star_array
        )

    def test_trades_actually_happen(self):
        """With nontrivial config, naive agent should produce trades."""
        res = run_sim(_simple_cfg(), _make_naive, horizon=10_000, seed=0)
        assert len(res.trade_log) > 0


# =============================================================================
# Snapshot timing
# =============================================================================

class TestSnapshotTiming:
    def test_snapshot_at_zero_always_captured(self):
        res = run_sim(_simple_cfg(), _make_naive, horizon=5_000, seed=0,
                      snapshot_interval=5_000)
        timestamps = sorted({s["timestamp"] for s in res.snapshots})
        assert 0 in timestamps

    def test_snapshot_at_horizon_captured(self):
        res = run_sim(_simple_cfg(), _make_naive, horizon=5_000, seed=0,
                      snapshot_interval=5_000)
        timestamps = sorted({s["timestamp"] for s in res.snapshots})
        assert 5_000 in timestamps

    def test_snapshots_at_expected_intervals(self):
        """horizon=10000, interval=2500 → snapshots at 0, 2500, 5000, 7500, 10000."""
        res = run_sim(_simple_cfg(n_markets=2), _make_naive, horizon=10_000,
                      seed=0, snapshot_interval=2_500)
        timestamps = sorted({s["timestamp"] for s in res.snapshots})
        assert timestamps == [0, 2_500, 5_000, 7_500, 10_000]

    def test_snapshots_one_row_per_market_per_time(self):
        """4 markets × 5 snapshot times = 20 records."""
        res = run_sim(_simple_cfg(n_markets=4), _make_naive, horizon=10_000,
                      seed=0, snapshot_interval=2_500)
        assert len(res.snapshots) == 4 * 5

    def test_snapshot_record_schema(self):
        res = run_sim(_simple_cfg(), _make_naive, horizon=5_000, seed=0)
        snap = res.snapshots[0]
        expected_keys = {"seed", "timestamp", "market_id", "price_yes",
                          "p_star", "brier"}
        assert set(snap.keys()) == expected_keys
        assert isinstance(snap["timestamp"], int)
        assert isinstance(snap["market_id"], int)
        assert isinstance(snap["price_yes"], float)
        assert isinstance(snap["p_star"], float)
        assert isinstance(snap["brier"], float)

    def test_snapshot_horizon_not_duplicated_when_aligned(self):
        """horizon is multiple of interval — final state captured exactly once."""
        res = run_sim(_simple_cfg(n_markets=2), _make_naive, horizon=10_000,
                      seed=0, snapshot_interval=5_000)
        horizon_rows = [s for s in res.snapshots if s["timestamp"] == 10_000]
        # Exactly 2 rows (one per market), not 4 (duplicated)
        assert len(horizon_rows) == 2

    def test_snapshot_horizon_captured_when_not_aligned(self):
        """horizon not multiple of interval — extra final snapshot."""
        res = run_sim(_simple_cfg(n_markets=2), _make_naive, horizon=12_345,
                      seed=0, snapshot_interval=5_000)
        timestamps = sorted({s["timestamp"] for s in res.snapshots})
        assert 12_345 in timestamps
        assert 10_000 in timestamps  # last aligned snapshot still captured

    def test_snapshot_interval_zero_disables_periodic(self):
        res = run_sim(_simple_cfg(n_markets=2), _make_naive, horizon=10_000,
                      seed=0, snapshot_interval=0)
        timestamps = sorted({s["timestamp"] for s in res.snapshots})
        # Only t=0 and t=horizon
        assert timestamps == [0, 10_000]

    def test_snapshot_reflects_post_trade_state(self):
        """At t=horizon, snapshot price should equal market_env.price_yes."""
        res = run_sim(_simple_cfg(n_markets=2), _make_naive, horizon=10_000,
                      seed=0, snapshot_interval=5_000)
        final_snaps = {s["market_id"]: s["price_yes"]
                       for s in res.snapshots if s["timestamp"] == 10_000}
        for m_id in range(2):
            assert final_snaps[m_id] == pytest.approx(
                float(res.market_env.price_yes(m_id)), rel=1e-12
            )


# =============================================================================
# Flat-record accessors (parquet-bound interfaces for Task 9)
# =============================================================================

class TestRecordAccessors:
    def test_trade_records_schema(self):
        res = run_sim(_simple_cfg(), _make_naive, horizon=10_000, seed=0)
        records = res.trade_records()
        assert len(records) == len(res.trade_log)
        expected_keys = {"seed", "timestamp", "market_id", "agent_id", "is_yes",
                          "shares", "cost", "price_yes_before", "price_yes_after"}
        for r in records:
            assert set(r.keys()) == expected_keys
            assert isinstance(r["is_yes"], bool)
            assert isinstance(r["shares"], float)
            assert isinstance(r["cost"], float)

    def test_agent_summary_records_schema(self):
        res = run_sim(_simple_cfg(), _make_naive, horizon=10_000, seed=0)
        records = res.agent_summary_records()
        assert len(records) == 1
        r = records[0]
        expected_keys = {"seed", "agent_id", "agent_type", "budget",
                          "deployed", "n_trades"}
        assert set(r.keys()) == expected_keys
        assert r["agent_type"] == "NaiveCredentialedAgent"
        assert r["n_trades"] == len(res.trade_log)
        assert r["deployed"] >= 0

    def test_agent_summary_n_trades_matches_log(self):
        """n_trades in agent_summary should equal count from trade_log."""
        def make_two_agents(info_env, rng):
            return [
                NaiveCredentialedAgent(
                    agent_id=0, budget=100.0, market_ids=(0,),
                    observation_delay=50, review_interval=1000,
                ),
                NaiveCredentialedAgent(
                    agent_id=1, budget=100.0, market_ids=(0,),
                    observation_delay=200, review_interval=1000,
                ),
            ]
        res = run_sim(_simple_cfg(n_markets=1), make_two_agents,
                      horizon=10_000, seed=0)
        records = res.agent_summary_records()
        for r in records:
            actual = sum(1 for t in res.trade_log if t.agent_id == r["agent_id"])
            assert r["n_trades"] == actual

    def test_summary_record_schema(self):
        res = run_sim(_simple_cfg(n_markets=3), _make_naive, horizon=10_000, seed=0)
        summary = res.summary_record()
        expected_keys = {"seed", "horizon", "n_markets", "n_agents", "n_trades",
                          "mean_brier", "max_brier", "mean_final_price"}
        assert set(summary.keys()) == expected_keys
        assert summary["seed"] == 0
        assert summary["horizon"] == 10_000
        assert summary["n_markets"] == 3
        assert summary["n_agents"] == 1
        assert 0 <= summary["mean_brier"] <= 1
        assert 0 <= summary["max_brier"] <= 1
        assert 0 <= summary["mean_final_price"] <= 1

    def test_snapshot_records_passes_through(self):
        res = run_sim(_simple_cfg(), _make_naive, horizon=5_000, seed=0)
        records = res.snapshot_records()
        assert records == res.snapshots


# =============================================================================
# Determinism
# =============================================================================

class TestDeterminism:
    def test_same_seed_identical_results(self):
        r1 = run_sim(_simple_cfg(n_markets=3), _make_naive, horizon=10_000, seed=42)
        r2 = run_sim(_simple_cfg(n_markets=3), _make_naive, horizon=10_000, seed=42)
        np.testing.assert_array_equal(r1.final_prices_yes, r2.final_prices_yes)
        np.testing.assert_array_equal(r1.p_star, r2.p_star)
        assert r1.trade_records() == r2.trade_records()
        assert r1.snapshots == r2.snapshots
        assert r1.summary_record() == r2.summary_record()

    def test_different_seeds_different_results(self):
        r1 = run_sim(_simple_cfg(n_markets=3), _make_naive, horizon=10_000, seed=0)
        r2 = run_sim(_simple_cfg(n_markets=3), _make_naive, horizon=10_000, seed=1)
        # At least one of the result dimensions must differ
        differ = (
            not np.array_equal(r1.final_prices_yes, r2.final_prices_yes)
            or not np.array_equal(r1.p_star, r2.p_star)
            or len(r1.trade_log) != len(r2.trade_log)
        )
        assert differ

    def test_agent_factory_rng_consumption_deterministic(self):
        """Factory using base_rates_from_truth (RNG-consuming) stays deterministic."""
        def make_tail(info_env, rng):
            base = base_rates_from_truth(info_env, (0, 1), rng, noise_std=0.3)
            return [
                TailEventReasoningAgent(
                    agent_id=0, budget=100.0, market_ids=(0, 1),
                    base_rates=base, review_interval=1000,
                ),
            ]
        r1 = run_sim(_simple_cfg(), make_tail, horizon=10_000, seed=7)
        r2 = run_sim(_simple_cfg(), make_tail, horizon=10_000, seed=7)
        assert r1.trade_records() == r2.trade_records()
        assert r1.snapshots == r2.snapshots


# =============================================================================
# Validation
# =============================================================================

class TestValidation:
    def test_horizon_must_be_positive(self):
        with pytest.raises(ValueError, match="horizon must be positive"):
            run_sim(_simple_cfg(), _make_naive, horizon=0, seed=0)
        with pytest.raises(ValueError, match="horizon must be positive"):
            run_sim(_simple_cfg(), _make_naive, horizon=-1, seed=0)

    def test_snapshot_interval_non_negative(self):
        with pytest.raises(ValueError, match="snapshot_interval must be non-negative"):
            run_sim(_simple_cfg(), _make_naive, horizon=1000, seed=0,
                    snapshot_interval=-1)

    def test_time_resolution_at_least_one(self):
        with pytest.raises(ValueError, match="time_resolution must be >= 1"):
            run_sim(_simple_cfg(), _make_naive, horizon=1000, seed=0,
                    time_resolution=0)


# =============================================================================
# Edge cases
# =============================================================================

class TestEdgeCases:
    def test_empty_agent_population(self):
        """No agents → no trades, but sim still runs and snapshots fire."""
        res = run_sim(_simple_cfg(), lambda env, rng: [], horizon=10_000, seed=0)
        assert len(res.agents) == 0
        assert len(res.trade_log) == 0
        # Final prices should still be 0.5 (no trades, no price movement)
        np.testing.assert_allclose(res.final_prices_yes, 0.5, atol=1e-12)
        # Snapshots still captured
        assert len(res.snapshots) > 0

    def test_default_market_spec_uses_polynomial_retreat(self):
        """No market_spec arg → defaults to MarketSpec() with polynomial retreat."""
        res = run_sim(_simple_cfg(), _make_naive, horizon=5_000, seed=0)
        assert res.market_env.spec.retreat_enabled is True
        assert res.market_env.spec.retreat_decay_shape == "polynomial"

    def test_custom_market_spec_respected(self):
        spec = MarketSpec(retreat_enabled=False)
        res = run_sim(_simple_cfg(), _make_naive, horizon=5_000, seed=0,
                      market_spec=spec)
        assert res.market_env.spec.retreat_enabled is False

    def test_noise_trader_alone(self):
        """Pure-noise population: lots of trades, but random direction."""
        def make_noise(info_env, rng):
            return [
                NoiseTrader(
                    agent_id=0, budget=1000.0,
                    market_ids=tuple(range(info_env.n_markets)),
                    arrival_rate_per_unit=5.0,
                ),
            ]
        res = run_sim(_simple_cfg(n_markets=2), make_noise, horizon=10_000, seed=0)
        assert len(res.trade_log) > 0


# =============================================================================
# Full integration: mixed population of all four agent classes
# =============================================================================

class TestMixedPopulationIntegration:
    def test_all_four_agent_classes_together(self):
        """
        Realistic integration test: mixed population with naive credentialed,
        tail-event reasoning, aggregation-depth, and cross-market consistency
        agents all trading concurrently.

        Verifies:
          - No crash with mixed agent types
          - Trade log records trades from multiple agent types
          - Each agent type has expected n_trades > 0
          - Determinism preserved across the full population
        """
        cfg = InformationConfig(
            k=3,
            clusters=[ClusterSpec(primary_factor=0, market_count=5,
                                   primary_loading_mean=1.5,
                                   primary_loading_std=0.1)],
            idiosyncratic_std=0.15,
            routine_rate_per_market=3.0, tail_rate_per_market=0.5,
            signal_noise_std=0.7, tail_noise_std=0.3,
        )

        def make_mixed(info_env, rng):
            # Use rng for any agent-side random construction
            base = base_rates_from_truth(info_env, (0,), rng, noise_std=0.3)
            cw = cross_weights_from_loadings(
                info_env.world.loadings_matrix,
                primary_markets=(0,),
                observed_markets=(0, 1, 2, 3, 4),
            )
            return [
                NaiveCredentialedAgent(
                    agent_id=0, budget=100.0, market_ids=(0,),
                    observation_delay=100, review_interval=1000,
                    prior_precision=2.0, disagreement_threshold=0.03,
                    trade_size=1.0,
                ),
                TailEventReasoningAgent(
                    agent_id=1, budget=100.0, market_ids=(0,),
                    base_rates=base, review_interval=1000,
                    disagreement_threshold=0.03, trade_size=1.0,
                ),
                AggregationDepthAgent(
                    agent_id=2, budget=100.0, market_ids=(0,),
                    observed_markets=(0, 1, 2, 3, 4),
                    cross_weights=cw, review_interval=500,
                    disagreement_threshold=0.03, trade_size=1.0,
                ),
                make_cross_market_agent(
                    agent_id=3, budget=100.0,
                    primary_markets=(0,), observed_markets=(0, 1, 2, 3, 4),
                    info_env=info_env, review_interval=1000,
                    disagreement_threshold=0.03, trade_size=1.0,
                ),
                NoiseTrader(
                    agent_id=4, budget=200.0, market_ids=(0,),
                    arrival_rate_per_unit=2.0,
                ),
            ]

        res = run_sim(cfg, make_mixed, horizon=20_000, seed=3)
        assert len(res.trade_log) > 0
        # All four agent types should appear in the agent summary
        summary = res.agent_summary_records()
        types_seen = {r["agent_type"] for r in summary}
        assert types_seen == {
            "NaiveCredentialedAgent",
            "TailEventReasoningAgent",
            "AggregationDepthAgent",
            "CrossMarketConsistencyAgent",
            "NoiseTrader",
        }
        # No agent over-spent
        for r in summary:
            assert r["deployed"] <= r["budget"] + 1e-9
        # Brier scores in valid range
        b = res.brier_per_market()
        assert np.all((b >= 0) & (b <= 1))

    def test_mixed_population_determinism(self):
        """Same seed across a mixed population → identical trade log."""
        cfg = _simple_cfg(n_markets=3)

        def make_mixed(info_env, rng):
            return [
                NaiveCredentialedAgent(
                    agent_id=0, budget=100.0, market_ids=(0, 1, 2),
                    observation_delay=50, review_interval=1000,
                ),
                NoiseTrader(
                    agent_id=1, budget=200.0, market_ids=(0, 1, 2),
                    arrival_rate_per_unit=3.0,
                ),
            ]
        r1 = run_sim(cfg, make_mixed, horizon=10_000, seed=11)
        r2 = run_sim(cfg, make_mixed, horizon=10_000, seed=11)
        assert r1.trade_records() == r2.trade_records()
