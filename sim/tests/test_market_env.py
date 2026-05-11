"""
Tests for the continuous-time multi-market environment.

Three core properties verified:
  1. The event-driven path produces bit-identical state to direct LSLMSRMarket
     calls. Combined with the existing test_market_parity.py (LSLMSRMarket ↔
     Solidity to 1e-9), this gives event-driven path ↔ Solidity transitively.
  2. Trade routing across multiple markets is correct (trades affect only
     their target market).
  3. The trade log captures full context — required for Task 9-10 analysis
     (PnL decomposition, price-impact attribution).

End-to-end determinism is inherited from Task 1's simulator, plus one new
test that exercises the full pipeline.
"""
from __future__ import annotations

import numpy as np
import pytest

from sim.market import ABMMConfig, LSLMSRConfig, LSLMSRMarket
from sim.market_env import (
    MarketEnvironment,
    MarketSpec,
    TradeRecord,
    TradeRequest,
)
from sim.simulator import Simulator


# -----------------------------------------------------------------------------
# MarketSpec validation
# -----------------------------------------------------------------------------

class TestMarketSpecValidation:
    def test_default_uses_polynomial_decay(self):
        """H1 winner — should be the default for the agentic sim."""
        spec = MarketSpec()
        assert spec.retreat_decay_shape == "polynomial"
        assert spec.retreat_enabled is True

    def test_rejects_invalid_decay_shape(self):
        with pytest.raises(ValueError, match="retreat_decay_shape"):
            MarketSpec(retreat_decay_shape="bogus")

    def test_rejects_nonpositive_alpha(self):
        with pytest.raises(ValueError, match="alpha"):
            MarketSpec(alpha=0)
        with pytest.raises(ValueError, match="alpha"):
            MarketSpec(alpha=-1)

    def test_rejects_nonpositive_q_abmm(self):
        with pytest.raises(ValueError):
            MarketSpec(q_abmm_yes=0)
        with pytest.raises(ValueError):
            MarketSpec(q_abmm_no=-5)

    def test_rejects_nonpositive_threshold(self):
        with pytest.raises(ValueError, match="retreat_threshold"):
            MarketSpec(retreat_threshold=0)

    def test_accepts_all_decay_shapes(self):
        for shape in ("polynomial", "exponential", "step"):
            assert MarketSpec(retreat_decay_shape=shape).retreat_decay_shape == shape

    def test_to_market_constructs_lslmsr(self):
        spec = MarketSpec(alpha=2.0, q_abmm_yes=50.0, q_abmm_no=80.0)
        m = spec.to_market()
        assert isinstance(m, LSLMSRMarket)
        assert m.config.alpha == 2.0
        assert m.q_yes == 50.0
        assert m.q_no == 80.0


# -----------------------------------------------------------------------------
# TradeRequest validation
# -----------------------------------------------------------------------------

class TestTradeRequestValidation:
    def test_rejects_negative_market_id(self):
        with pytest.raises(ValueError, match="market_id"):
            TradeRequest(market_id=-1, agent_id=0, is_yes=True, shares=1.0)

    def test_rejects_nonpositive_shares(self):
        with pytest.raises(ValueError, match="shares"):
            TradeRequest(market_id=0, agent_id=0, is_yes=True, shares=0)
        with pytest.raises(ValueError, match="shares"):
            TradeRequest(market_id=0, agent_id=0, is_yes=True, shares=-1.0)


# -----------------------------------------------------------------------------
# MarketEnvironment basics
# -----------------------------------------------------------------------------

class TestMarketEnvironmentBasics:
    def test_n_markets(self):
        env = MarketEnvironment(n_markets=5, spec=MarketSpec())
        assert env.n_markets == 5
        assert len(env.markets) == 5

    def test_rejects_zero_markets(self):
        with pytest.raises(ValueError, match="n_markets"):
            MarketEnvironment(n_markets=0, spec=MarketSpec())

    def test_initial_prices_symmetric(self):
        env = MarketEnvironment(n_markets=3, spec=MarketSpec())
        np.testing.assert_allclose(env.prices_yes(), [0.5, 0.5, 0.5])

    def test_asymmetric_seed_gives_asymmetric_initial_price(self):
        env = MarketEnvironment(n_markets=1, spec=MarketSpec(q_abmm_yes=200.0, q_abmm_no=50.0))
        # More YES seed → YES is more expensive
        assert env.price_yes(0) > 0.5

    def test_double_register_raises(self):
        env = MarketEnvironment(n_markets=1, spec=MarketSpec())
        sim = Simulator(rng=np.random.default_rng(0))
        env.register(sim)
        with pytest.raises(RuntimeError, match="register"):
            env.register(sim)

    def test_initial_human_volumes_zero(self):
        env = MarketEnvironment(n_markets=3, spec=MarketSpec())
        np.testing.assert_allclose(env.human_volumes(), [0.0, 0.0, 0.0])
        np.testing.assert_allclose(env.retreat_factors(), [1.0, 1.0, 1.0])


# -----------------------------------------------------------------------------
# Trade execution via events
# -----------------------------------------------------------------------------

class TestTradeExecution:
    def _setup(self, n_markets=3, spec=None):
        env = MarketEnvironment(n_markets=n_markets, spec=spec or MarketSpec())
        sim = Simulator(rng=np.random.default_rng(0), time_resolution=1000)
        env.register(sim)
        return env, sim

    def test_yes_trade_increases_yes_price(self):
        env, sim = self._setup()
        sim.schedule(delay=100, event_type=env.TRADE_EVENT,
                     payload=TradeRequest(market_id=0, agent_id=1, is_yes=True, shares=10.0))
        sim.run_until(1000)
        assert env.price_yes(0) > 0.5
        # Other markets untouched
        assert env.price_yes(1) == 0.5
        assert env.price_yes(2) == 0.5

    def test_no_trade_decreases_yes_price(self):
        env, sim = self._setup()
        sim.schedule(delay=100, event_type=env.TRADE_EVENT,
                     payload=TradeRequest(market_id=1, agent_id=2, is_yes=False, shares=10.0))
        sim.run_until(1000)
        assert env.price_yes(1) < 0.5
        assert env.price_yes(0) == 0.5
        assert env.price_yes(2) == 0.5

    def test_market_id_out_of_range_raises(self):
        env, sim = self._setup(n_markets=2)
        sim.schedule(delay=100, event_type=env.TRADE_EVENT,
                     payload=TradeRequest(market_id=5, agent_id=0, is_yes=True, shares=1.0))
        with pytest.raises(IndexError, match="market_id"):
            sim.run_until(1000)

    def test_wrong_payload_type_raises(self):
        env, sim = self._setup()
        sim.schedule(delay=100, event_type=env.TRADE_EVENT, payload="not a TradeRequest")
        with pytest.raises(TypeError, match="TradeRequest"):
            sim.run_until(1000)

    def test_human_volume_accumulates(self):
        env, sim = self._setup(n_markets=1)
        for i, shares in enumerate([3.0, 5.0, 2.0]):
            sim.schedule(delay=(i + 1) * 10, event_type=env.TRADE_EVENT,
                         payload=TradeRequest(market_id=0, agent_id=0, is_yes=True, shares=shares))
        sim.run_until(100)
        assert env.markets[0].human_volume == 10.0


# -----------------------------------------------------------------------------
# Trade log
# -----------------------------------------------------------------------------

class TestTradeLog:
    def test_log_captures_full_context(self):
        env = MarketEnvironment(n_markets=1, spec=MarketSpec())
        sim = Simulator(rng=np.random.default_rng(0), time_resolution=1000)
        env.register(sim)
        sim.schedule(delay=500, event_type=env.TRADE_EVENT,
                     payload=TradeRequest(market_id=0, agent_id=42, is_yes=True, shares=5.0))
        sim.run_until(1000)
        assert len(env.trade_log) == 1
        rec = env.trade_log[0]
        assert rec.timestamp == 500
        assert rec.market_id == 0
        assert rec.agent_id == 42
        assert rec.is_yes is True
        assert rec.shares == 5.0
        assert rec.cost > 0
        assert rec.price_yes_before == 0.5
        assert rec.price_yes_after > 0.5

    def test_log_ordered_by_arrival(self):
        env = MarketEnvironment(n_markets=2, spec=MarketSpec())
        sim = Simulator(rng=np.random.default_rng(0), time_resolution=1000)
        env.register(sim)
        for i, (mid, is_yes, shares) in enumerate([
            (0, True, 1.0), (1, False, 2.0), (0, True, 3.0)
        ]):
            sim.schedule(delay=(i + 1) * 100, event_type=env.TRADE_EVENT,
                         payload=TradeRequest(market_id=mid, agent_id=0, is_yes=is_yes, shares=shares))
        sim.run_until(1000)
        assert len(env.trade_log) == 3
        assert [r.timestamp for r in env.trade_log] == [100, 200, 300]
        assert [r.market_id for r in env.trade_log] == [0, 1, 0]


# -----------------------------------------------------------------------------
# Parity: event-driven path matches direct calls
# -----------------------------------------------------------------------------

class TestParityWithDirectCalls:
    """
    Bit-identical state across event-driven wrapper vs direct LSLMSRMarket calls.

    Combined with sim/tests/test_market_parity.py (LSLMSRMarket ↔ Solidity to
    1e-9), this gives event-path ↔ Solidity parity transitively. The wrapper
    introduces no new floating-point operations.
    """

    def test_no_retreat_bit_exact(self):
        spec = MarketSpec(retreat_enabled=False)
        trades = [
            (0, True, 5.0), (1, False, 3.0), (0, True, 2.0),
            (2, True, 10.0), (1, True, 1.0), (2, False, 7.0),
        ]

        # Reference: direct calls
        ref = [spec.to_market() for _ in range(3)]
        ref_costs = [ref[mid].execute_trade(is_yes, shares) for mid, is_yes, shares in trades]

        # Event-driven path
        env = MarketEnvironment(n_markets=3, spec=spec)
        sim = Simulator(rng=np.random.default_rng(0))
        env.register(sim)
        for i, (mid, is_yes, shares) in enumerate(trades):
            sim.schedule(delay=i + 1, event_type=env.TRADE_EVENT,
                         payload=TradeRequest(market_id=mid, agent_id=0, is_yes=is_yes, shares=shares))
        sim.run_until(100)

        # Bit-exact state match
        for i in range(3):
            assert env.markets[i].q_yes == ref[i].q_yes
            assert env.markets[i].q_no == ref[i].q_no
            assert env.markets[i].human_volume == ref[i].human_volume
            assert env.markets[i].price_yes() == ref[i].price_yes()
        # Bit-exact cost match
        for i, rec in enumerate(env.trade_log):
            assert rec.cost == ref_costs[i]

    def test_with_polynomial_retreat_bit_exact(self):
        spec = MarketSpec(
            retreat_enabled=True, retreat_decay_shape="polynomial",
            retreat_tau=1.0, retreat_threshold=20.0,
        )
        trades = [(i % 3, i % 2 == 0, 5.0) for i in range(20)]

        ref = [spec.to_market() for _ in range(3)]
        for mid, is_yes, shares in trades:
            ref[mid].execute_trade(is_yes, shares)

        env = MarketEnvironment(n_markets=3, spec=spec)
        sim = Simulator(rng=np.random.default_rng(0))
        env.register(sim)
        for i, (mid, is_yes, shares) in enumerate(trades):
            sim.schedule(delay=i + 1, event_type=env.TRADE_EVENT,
                         payload=TradeRequest(market_id=mid, agent_id=0, is_yes=is_yes, shares=shares))
        sim.run_until(1000)

        for i in range(3):
            assert env.markets[i].q_yes == ref[i].q_yes
            assert env.markets[i].q_no == ref[i].q_no
            assert env.markets[i].price_yes() == ref[i].price_yes()
            # At least confirm retreat actually activated
            if env.markets[i].human_volume > spec.retreat_threshold:
                assert env.markets[i]._retreat_factor() < 1.0


# -----------------------------------------------------------------------------
# Retreat behavior end-to-end
# -----------------------------------------------------------------------------

class TestRetreat:
    def test_retreat_factor_one_below_threshold(self):
        spec = MarketSpec(retreat_enabled=True, retreat_threshold=100.0)
        env = MarketEnvironment(n_markets=1, spec=spec)
        sim = Simulator(rng=np.random.default_rng(0))
        env.register(sim)
        sim.schedule(delay=1, event_type=env.TRADE_EVENT,
                     payload=TradeRequest(market_id=0, agent_id=0, is_yes=True, shares=10.0))
        sim.run_until(100)
        assert env.markets[0]._retreat_factor() == 1.0
        assert env.markets[0].human_volume == 10.0

    def test_polynomial_retreat_value(self):
        """1 / (1 + tau * excess/threshold); 100 shares, threshold 50, tau 1 → 0.5."""
        spec = MarketSpec(
            retreat_enabled=True, retreat_decay_shape="polynomial",
            retreat_tau=1.0, retreat_threshold=50.0,
        )
        env = MarketEnvironment(n_markets=1, spec=spec)
        sim = Simulator(rng=np.random.default_rng(0))
        env.register(sim)
        sim.schedule(delay=1, event_type=env.TRADE_EVENT,
                     payload=TradeRequest(market_id=0, agent_id=0, is_yes=True, shares=100.0))
        sim.run_until(100)
        assert env.markets[0]._retreat_factor() == pytest.approx(0.5, rel=1e-12)

    def test_retreat_disabled_means_factor_one(self):
        spec = MarketSpec(retreat_enabled=False, retreat_threshold=10.0)
        env = MarketEnvironment(n_markets=1, spec=spec)
        sim = Simulator(rng=np.random.default_rng(0))
        env.register(sim)
        sim.schedule(delay=1, event_type=env.TRADE_EVENT,
                     payload=TradeRequest(market_id=0, agent_id=0, is_yes=True, shares=100.0))
        sim.run_until(100)
        assert env.markets[0]._retreat_factor() == 1.0


# -----------------------------------------------------------------------------
# End-to-end determinism
# -----------------------------------------------------------------------------

class TestDeterminism:
    def _trade_log_from_seed(self, seed: int):
        rng = np.random.default_rng(seed)
        env = MarketEnvironment(n_markets=3, spec=MarketSpec())
        sim = Simulator(rng=rng, time_resolution=1000)
        env.register(sim)
        for _ in range(50):
            t = int(rng.integers(1, 10_000))
            mid = int(rng.integers(0, 3))
            is_yes = bool(rng.integers(0, 2))
            shares = float(rng.uniform(0.1, 10.0))
            sim.schedule_at(t, env.TRADE_EVENT,
                            payload=TradeRequest(market_id=mid, agent_id=0,
                                                 is_yes=is_yes, shares=shares))
        sim.run_until(20_000)
        return [(r.timestamp, r.market_id, r.is_yes, r.shares, r.cost,
                 r.price_yes_before, r.price_yes_after) for r in env.trade_log]

    def test_same_seed_same_trade_log(self):
        a = self._trade_log_from_seed(42)
        b = self._trade_log_from_seed(42)
        assert a == b
        assert len(a) > 0

    def test_different_seeds_diverge(self):
        a = self._trade_log_from_seed(1)
        b = self._trade_log_from_seed(2)
        assert a != b
