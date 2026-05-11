"""
Tests for the continuous-time agent population.

Coverage layers:
  1. Agent unit tests — validation + math (posterior update, modal bias,
     trade-decision direction, capital constraint).
  2. AgentPopulation unit tests — dispatch correctness, observation delay,
     review scheduling, noise rate calibration, end-to-end determinism.
  3. Integration tests — agents wired into the full information + market
     pipeline; convergence properties.
"""
from __future__ import annotations

import math

import numpy as np
import pytest

from sim.agentic import (
    AgentPopulation,
    NaiveCredentialedAgent,
    NoiseTrader,
    _sigmoid,
)
from sim.information import ClusterSpec, InformationConfig, InformationEnvironment, Signal
from sim.market_env import MarketEnvironment, MarketSpec, TradeRequest
from sim.simulator import Simulator


# -----------------------------------------------------------------------------
# NaiveCredentialedAgent — validation
# -----------------------------------------------------------------------------

class TestNaiveCredentialedValidation:
    def test_requires_market_ids(self):
        with pytest.raises(ValueError, match="market_ids"):
            NaiveCredentialedAgent(agent_id=0, budget=100.0, market_ids=())

    def test_rejects_negative_observation_delay(self):
        with pytest.raises(ValueError, match="observation_delay"):
            NaiveCredentialedAgent(
                agent_id=0, budget=100.0, market_ids=(0,), observation_delay=-1
            )

    def test_rejects_nonpositive_prior_precision(self):
        with pytest.raises(ValueError, match="prior_precision"):
            NaiveCredentialedAgent(
                agent_id=0, budget=100.0, market_ids=(0,), prior_precision=0
            )

    def test_rejects_safety_margin_below_one(self):
        with pytest.raises(ValueError, match="safety_margin"):
            NaiveCredentialedAgent(
                agent_id=0, budget=100.0, market_ids=(0,), safety_margin=0.9
            )

    def test_initial_posterior_at_prior(self):
        a = NaiveCredentialedAgent(
            agent_id=0, budget=100.0, market_ids=(0, 1, 2), prior_precision=7.0
        )
        for m in (0, 1, 2):
            mu, tau = a.posterior(m)
            assert mu == 0.0
            assert tau == 7.0


# -----------------------------------------------------------------------------
# NaiveCredentialedAgent — posterior math
# -----------------------------------------------------------------------------

class TestNaiveCredentialedPosterior:
    def test_single_signal_update(self):
        """One signal: μ_new = (τ_0·0 + τ_s·s) / (τ_0 + τ_s)."""
        a = NaiveCredentialedAgent(
            agent_id=0, budget=100.0, market_ids=(0,),
            prior_precision=5.0, signal_precision_assumed=1.0,
        )
        a.update_posterior(Signal(market_id=0, value=2.0, is_tail=False, noise_std=1.0))
        mu, tau = a.posterior(0)
        # Expected: (5*0 + 1*2.0) / (5 + 1) = 2/6 = 0.333...
        assert mu == pytest.approx(2.0 / 6.0, rel=1e-12)
        assert tau == pytest.approx(6.0)

    def test_many_signals_converge_to_mean(self):
        """Many signals with mean μ_s: posterior → μ_s asymptotically."""
        a = NaiveCredentialedAgent(
            agent_id=0, budget=100.0, market_ids=(0,),
            prior_precision=1.0, signal_precision_assumed=1.0,
        )
        rng = np.random.default_rng(0)
        true_logit = 2.5
        for _ in range(500):
            s = float(rng.normal(true_logit, 1.0))
            a.update_posterior(Signal(market_id=0, value=s, is_tail=False, noise_std=1.0))
        mu, _ = a.posterior(0)
        # After 500 signals with sample mean ≈ true_logit and SE ≈ 1/sqrt(500) ≈ 0.045,
        # posterior should be within a few SE of true_logit.
        assert abs(mu - true_logit) < 0.2

    def test_modal_bias_with_strong_prior(self):
        """Strong prior + few signals → posterior stays near 0."""
        a = NaiveCredentialedAgent(
            agent_id=0, budget=100.0, market_ids=(0,),
            prior_precision=50.0, signal_precision_assumed=1.0,
        )
        # 10 signals strongly toward logit=3
        for _ in range(10):
            a.update_posterior(Signal(market_id=0, value=3.0, is_tail=False, noise_std=1.0))
        mu, _ = a.posterior(0)
        # Expected: (50*0 + 10*3) / (50 + 10) = 30/60 = 0.5
        # Sigmoid(0.5) ≈ 0.62 — still anchored near modal 0.5 despite 10 strong signals
        assert mu == pytest.approx(0.5, rel=1e-12)
        assert _sigmoid(mu) < 0.65


# -----------------------------------------------------------------------------
# NaiveCredentialedAgent — trade decisions
# -----------------------------------------------------------------------------

class _StubMarket:
    """Stub market with configurable price and cost. Default cost = shares * 1.0."""
    def __init__(self, price: float):
        self._price = price
    def price_yes(self) -> float:
        return self._price
    def cost_of_trade(self, is_yes: bool, shares: float) -> float:
        avg_price = self._price if is_yes else (1.0 - self._price)
        return shares * avg_price


class _StubMarketEnv:
    """Minimal market env stub. Exposes `.markets[i]` for cost_of_trade lookup."""
    def __init__(self, prices: dict[int, float]):
        max_id = max(prices.keys()) + 1
        self.markets: list = [_StubMarket(0.5) for _ in range(max_id)]
        for mid, p in prices.items():
            self.markets[mid] = _StubMarket(p)
    def price_yes(self, market_id: int) -> float:
        return self.markets[market_id].price_yes()


class TestNaiveCredentialedTrade:
    def _agent(self, **kwargs):
        defaults = dict(
            agent_id=0, budget=100.0, market_ids=(0,),
            prior_precision=1.0, signal_precision_assumed=1.0,
            disagreement_threshold=0.05, trade_size=2.0,
        )
        defaults.update(kwargs)
        return NaiveCredentialedAgent(**defaults)

    def test_trades_yes_when_posterior_above_market(self):
        a = self._agent()
        # Push posterior above sigmoid^-1(0.5) = 0
        for _ in range(20):
            a.update_posterior(Signal(market_id=0, value=2.0, is_tail=False, noise_std=1.0))
        env = _StubMarketEnv({0: 0.5})  # market still at 0.5
        req = a._consider_trade(0, env)
        assert req is not None
        assert req.is_yes is True
        assert req.market_id == 0
        assert req.agent_id == 0

    def test_trades_no_when_posterior_below_market(self):
        a = self._agent()
        for _ in range(20):
            a.update_posterior(Signal(market_id=0, value=-2.0, is_tail=False, noise_std=1.0))
        env = _StubMarketEnv({0: 0.5})
        req = a._consider_trade(0, env)
        assert req is not None
        assert req.is_yes is False

    def test_no_trade_within_threshold(self):
        a = self._agent(disagreement_threshold=0.20)
        a.update_posterior(Signal(market_id=0, value=0.5, is_tail=False, noise_std=1.0))
        # Posterior μ small → p_post ≈ 0.56; market = 0.5 → diff ≈ 0.06 < 0.20
        env = _StubMarketEnv({0: 0.5})
        assert a._consider_trade(0, env) is None

    def test_capital_constraint_shrinks_trade(self):
        """Real LS-LMSR cost makes 10 shares unaffordable on a 1.0 budget; agent shrinks."""
        a = self._agent(budget=1.0, trade_size=10.0)
        for _ in range(20):
            a.update_posterior(Signal(market_id=0, value=3.0, is_tail=False, noise_std=1.0))
        env = MarketEnvironment(n_markets=1, spec=MarketSpec(retreat_enabled=False))
        req = a._consider_trade(0, env)
        assert req is not None
        assert req.shares < 10.0
        assert req.shares > 0.1
        # Actual cost should fit within budget (with safety_margin slack)
        cost = env.markets[0].cost_of_trade(True, req.shares)
        assert cost * a.safety_margin <= a.budget + 1e-9

    def test_capital_exhausted_returns_none(self):
        a = self._agent(budget=0.01)  # below the cost of 0.1 shares in LS-LMSR
        for _ in range(20):
            a.update_posterior(Signal(market_id=0, value=3.0, is_tail=False, noise_std=1.0))
        env = MarketEnvironment(n_markets=1, spec=MarketSpec(retreat_enabled=False))
        assert a._consider_trade(0, env) is None


# -----------------------------------------------------------------------------
# NoiseTrader — validation + fire
# -----------------------------------------------------------------------------

class TestNoiseTrader:
    def test_requires_market_ids(self):
        with pytest.raises(ValueError, match="market_ids"):
            NoiseTrader(agent_id=0, budget=100.0, market_ids=(), arrival_rate_per_unit=1.0)

    def test_rejects_negative_rate(self):
        with pytest.raises(ValueError, match="arrival_rate"):
            NoiseTrader(
                agent_id=0, budget=100.0, market_ids=(0,), arrival_rate_per_unit=-1.0
            )

    def test_does_not_observe_signals(self):
        nt = NoiseTrader(agent_id=0, budget=100.0, market_ids=(0, 1), arrival_rate_per_unit=1.0)
        assert nt.observes(0) is False
        assert nt.observes(1) is False

    def test_fire_produces_trade_request(self):
        nt = NoiseTrader(agent_id=9, budget=100.0, market_ids=(0, 1, 2), arrival_rate_per_unit=1.0)
        env = MarketEnvironment(n_markets=3, spec=MarketSpec(retreat_enabled=False))
        sim = Simulator(rng=np.random.default_rng(0))
        req = nt.fire_noise(sim, env)
        assert req is not None
        assert req.market_id in (0, 1, 2)
        assert req.agent_id == 9
        assert req.shares > 0

    def test_fire_respects_capital(self):
        nt = NoiseTrader(agent_id=0, budget=0.001, market_ids=(0,), arrival_rate_per_unit=1.0)
        env = MarketEnvironment(n_markets=1, spec=MarketSpec(retreat_enabled=False))
        sim = Simulator(rng=np.random.default_rng(0))
        assert nt.fire_noise(sim, env) is None


# -----------------------------------------------------------------------------
# AgentPopulation
# -----------------------------------------------------------------------------

class TestAgentPopulation:
    def test_rejects_duplicate_agent_ids(self):
        with pytest.raises(ValueError, match="agent_ids must be unique"):
            AgentPopulation([
                NaiveCredentialedAgent(agent_id=0, budget=100.0, market_ids=(0,)),
                NaiveCredentialedAgent(agent_id=0, budget=100.0, market_ids=(1,)),
            ])

    def test_double_register_raises(self):
        pop = AgentPopulation([NoiseTrader(
            agent_id=0, budget=100.0, market_ids=(0,), arrival_rate_per_unit=1.0
        )])
        sim = Simulator(rng=np.random.default_rng(0), time_resolution=1000)
        env = MarketEnvironment(n_markets=1, spec=MarketSpec())
        env.register(sim)
        pop.register(sim, env, until_ts=1000)
        with pytest.raises(RuntimeError, match="register"):
            pop.register(sim, env, until_ts=1000)

    def test_signal_dispatched_only_to_observers(self):
        """Agent A observes market 0, agent B observes market 1.
        Signal on market 0 → only A schedules a decision."""
        a = NaiveCredentialedAgent(agent_id=0, budget=100.0, market_ids=(0,),
                                    observation_delay=100, review_interval=0)
        b = NaiveCredentialedAgent(agent_id=1, budget=100.0, market_ids=(1,),
                                    observation_delay=100, review_interval=0)
        pop = AgentPopulation([a, b])
        sim = Simulator(rng=np.random.default_rng(0), time_resolution=1000)
        env = MarketEnvironment(n_markets=2, spec=MarketSpec())
        env.register(sim)
        pop.register(sim, env, until_ts=10_000)
        # Inject one signal on market 0
        sim.schedule(delay=10, event_type=pop.SIGNAL_EVENT,
                     payload=Signal(market_id=0, value=2.0, is_tail=False, noise_std=1.0))
        sim.run_until(10_000)
        # a's posterior should have updated (was 0, now positive); b's should still be 0
        assert a.posterior(0)[0] > 0
        assert b.posterior(1)[0] == 0.0

    def test_observation_delay_respected(self):
        """Decision fires exactly at signal_t + δ."""
        a = NaiveCredentialedAgent(agent_id=0, budget=100.0, market_ids=(0,),
                                    observation_delay=500, review_interval=0)
        pop = AgentPopulation([a])
        sim = Simulator(rng=np.random.default_rng(0), time_resolution=1000)
        env = MarketEnvironment(n_markets=1, spec=MarketSpec())
        env.register(sim)
        pop.register(sim, env, until_ts=10_000)
        sim.schedule_at(timestamp=200, event_type=pop.SIGNAL_EVENT,
                        payload=Signal(market_id=0, value=3.0, is_tail=False, noise_std=1.0))
        # At t=600 (still pre-δ), agent hasn't updated yet
        sim.run_until(699)
        assert a.posterior(0)[0] == 0.0
        # At t=700 (signal_t=200 + δ=500), decision fires, posterior updates
        sim.run_until(700)
        assert a.posterior(0)[0] > 0

    def test_review_fires_periodically(self):
        """Review schedules itself for as long as until_ts allows."""
        a = NaiveCredentialedAgent(
            agent_id=0, budget=100.0, market_ids=(0,),
            observation_delay=0, review_interval=1000, disagreement_threshold=1.0,
            # threshold = 1.0 → no actual trades, but reviews still fire
        )
        pop = AgentPopulation([a])
        sim = Simulator(rng=np.random.default_rng(0), time_resolution=1000)
        env = MarketEnvironment(n_markets=1, spec=MarketSpec())
        env.register(sim)
        pop.register(sim, env, until_ts=10_000)
        # Count review events processed
        review_count = [0]
        original = pop._on_review
        def counting(sim, event):
            review_count[0] += 1
            original(sim, event)
        sim._handlers[pop.REVIEW_EVENT] = counting
        sim.run_until(10_000)
        # Expect reviews at t = 1000, 2000, ..., 10000 → 10 reviews
        assert review_count[0] == 10


class TestNoiseRateCalibration:
    """The noise trader's empirical rate should match its configured rate."""

    def test_empirical_arrival_rate(self):
        rate = 3.0  # per unit time
        time_resolution = 1000
        horizon_units = 1000.0
        horizon_ticks = int(horizon_units * time_resolution)
        expected = rate * horizon_units  # 3000

        nt = NoiseTrader(
            agent_id=0, budget=1e9, market_ids=(0,),  # huge budget → never capital-blocked
            arrival_rate_per_unit=rate, mean_trade_size=0.1,
        )
        pop = AgentPopulation([nt])
        sim = Simulator(rng=np.random.default_rng(42), time_resolution=time_resolution)
        env = MarketEnvironment(n_markets=1, spec=MarketSpec(retreat_enabled=False))
        env.register(sim)
        pop.register(sim, env, until_ts=horizon_ticks)
        sim.run_until(horizon_ticks)

        # Count actual trades (matches count of noise-event firings since budget is huge)
        actual = sum(1 for r in env.trade_log if r.agent_id == 0)
        sigma = math.sqrt(expected)
        assert abs(actual - expected) < 4 * sigma, (
            f"got {actual} trades, expected ~{expected:.0f} (±{4*sigma:.0f})"
        )


# -----------------------------------------------------------------------------
# End-to-end determinism
# -----------------------------------------------------------------------------

class TestDeterminism:
    def _run(self, seed: int) -> list:
        rng = np.random.default_rng(seed)
        cfg = InformationConfig(
            k=2,
            clusters=[ClusterSpec(primary_factor=0, market_count=2)],
            n_independent_markets=1,
            routine_rate_per_market=2.0, tail_rate_per_market=0.2,
        )
        info_env = InformationEnvironment(cfg, rng)
        market_env = MarketEnvironment(n_markets=info_env.n_markets, spec=MarketSpec())
        agents = [
            NaiveCredentialedAgent(agent_id=0, budget=100.0, market_ids=(0, 1),
                                    observation_delay=500, review_interval=2000),
            NaiveCredentialedAgent(agent_id=1, budget=100.0, market_ids=(2,),
                                    observation_delay=500, review_interval=2000),
            NoiseTrader(agent_id=10, budget=100.0, market_ids=(0, 1, 2),
                         arrival_rate_per_unit=1.0),
        ]
        pop = AgentPopulation(agents)
        sim = Simulator(rng=rng, time_resolution=1000)
        market_env.register(sim)
        pop.register(sim, market_env, until_ts=30_000)
        info_env.schedule_signals(sim, until_ts=30_000)
        sim.run_until(30_000)
        return [(r.timestamp, r.market_id, r.agent_id, r.is_yes, r.shares, r.cost)
                for r in market_env.trade_log]

    def test_same_seed_same_trade_log(self):
        a = self._run(seed=42)
        b = self._run(seed=42)
        assert a == b
        assert len(a) > 0

    def test_different_seeds_diverge(self):
        a = self._run(seed=1)
        b = self._run(seed=2)
        assert a != b


# -----------------------------------------------------------------------------
# Integration tests
# -----------------------------------------------------------------------------

class TestIntegration:
    def test_credentialed_pool_pushes_price_toward_p_star(self):
        """
        Many credentialed agents + many signals → market price moves toward p*.

        The latent factor draw is random, so we don't pin p* to a direction;
        we check the price moved AT LEAST halfway from 0.5 toward whatever p*
        the seed produced, AND that the move is non-trivial (>0.05).
        """
        cfg = InformationConfig(
            k=2,
            clusters=[ClusterSpec(primary_factor=0, market_count=1,
                                   primary_loading_mean=2.0, primary_loading_std=0.1,
                                   secondary_loading_std=0.05)],
            idiosyncratic_std=0.3,
            routine_rate_per_market=10.0,
            tail_rate_per_market=0.0,
            signal_noise_std=0.5,
        )
        rng = np.random.default_rng(7)
        info_env = InformationEnvironment(cfg, rng)
        p_star = info_env.truths[0].p_star
        # Require a meaningfully biased p* — the test only makes sense when
        # there's somewhere for the price to go.
        assert abs(p_star - 0.5) > 0.05, f"seed produced p* = {p_star}, too central"

        market_env = MarketEnvironment(n_markets=1, spec=MarketSpec())
        agents = [
            NaiveCredentialedAgent(
                agent_id=i, budget=200.0, market_ids=(0,),
                observation_delay=100, review_interval=1000,
                prior_precision=1.0, signal_precision_assumed=1.0,
                disagreement_threshold=0.02, trade_size=2.0,
            )
            for i in range(5)
        ]
        pop = AgentPopulation(agents)
        sim = Simulator(rng=rng, time_resolution=1000)
        market_env.register(sim)
        pop.register(sim, market_env, until_ts=60_000)
        info_env.schedule_signals(sim, until_ts=60_000)
        sim.run_until(60_000)

        final_price = market_env.price_yes(0)
        # Price moved in the same direction as p_star (sign check)
        same_direction = (final_price - 0.5) * (p_star - 0.5) > 0
        assert same_direction, (
            f"price moved wrong direction: 0.5 -> {final_price:.3f}, p*={p_star:.3f}"
        )
        # Price moved at least halfway toward p_star
        halfway = 0.5 + 0.5 * (p_star - 0.5)
        moved_far_enough = (
            final_price > halfway if p_star > 0.5 else final_price < halfway
        )
        assert moved_far_enough, (
            f"price {final_price:.3f} didn't reach halfway {halfway:.3f} toward p*={p_star:.3f}"
        )

    def test_capital_exhaustion_stops_agent_trading(self):
        """An agent with tiny budget makes a few trades then stops."""
        cfg = InformationConfig(
            k=2,
            clusters=[ClusterSpec(primary_factor=0, market_count=1,
                                   primary_loading_mean=3.0, primary_loading_std=0.1)],
            idiosyncratic_std=0.2,
            routine_rate_per_market=20.0,
            tail_rate_per_market=0.0,
        )
        rng = np.random.default_rng(11)
        info_env = InformationEnvironment(cfg, rng)
        market_env = MarketEnvironment(n_markets=1, spec=MarketSpec())
        # Budget = 5.0 — only enough for a handful of trades.
        a = NaiveCredentialedAgent(
            agent_id=0, budget=5.0, market_ids=(0,),
            observation_delay=10, review_interval=500,
            prior_precision=1.0, disagreement_threshold=0.02, trade_size=1.0,
        )
        pop = AgentPopulation([a])
        sim = Simulator(rng=rng, time_resolution=1000)
        market_env.register(sim)
        pop.register(sim, market_env, until_ts=30_000)
        info_env.schedule_signals(sim, until_ts=30_000)
        sim.run_until(30_000)

        # Agent should have spent close to budget but not exceeded it
        assert a.deployed <= a.budget + 1e-9
        # Last trade by this agent should be well before the end (it ran out)
        agent_trades = [r for r in market_env.trade_log if r.agent_id == 0]
        assert len(agent_trades) > 0
        assert agent_trades[-1].timestamp < 25_000
