"""
Unit and property tests for agent classes.
"""

import numpy as np
import pytest
from sim.market import LSLMSRMarket, LSLMSRConfig, ABMMConfig
from sim.agents import (
    NoiseTrader,
    CredentialedTrader,
    MomentumTrader,
    AdversarialTrader,
    TradeAction,
)


def _make_market(price_yes: float = 0.5):
    """Helper: build a market with a target initial YES price."""
    if abs(price_yes - 0.5) < 1e-12:
        cfg = LSLMSRConfig(alpha=0.05, q_abmm_yes=500.0, q_abmm_no=500.0)
    else:
        # asymmetric seeding to skew price
        # higher q_no relative to q_yes → lower yes price
        ratio = (1 - price_yes) / price_yes
        cfg = LSLMSRConfig(alpha=0.05, q_abmm_yes=500.0, q_abmm_no=500.0 * ratio)
    return LSLMSRMarket(config=cfg, abmm=ABMMConfig(enabled=False))


# ---------- NoiseTrader ----------

def test_noise_trader_produces_nonzero_trade():
    rng = np.random.default_rng(seed=0)
    agent = NoiseTrader("noise_0", rng)
    market = _make_market()
    action = agent.decide(market.snapshot())
    assert action.shares > 0


def test_noise_trader_mean_size_calibrated():
    """Average trade size over many calls should be near mean_size."""
    rng = np.random.default_rng(seed=42)
    agent = NoiseTrader("noise_0", rng, mean_size=5.0, size_std=1.0)
    market = _make_market()
    state = market.snapshot()
    sizes = [agent.decide(state).shares for _ in range(10000)]
    # |Normal(5,1)| has mean ≈ 5.07 (folded normal correction tiny here)
    assert 4.9 < np.mean(sizes) < 5.2


# ---------- CredentialedTrader ----------

def test_credentialed_signal_is_drawn_from_correct_distribution():
    """Average signal across many agents should converge to true_prob."""
    rng = np.random.default_rng(seed=42)
    agents = [
        CredentialedTrader(f"c_{i}", rng, true_probability=0.7, sigma=0.1)
        for i in range(1000)
    ]
    mean_signal = np.mean([a.signal for a in agents])
    assert abs(mean_signal - 0.7) < 0.01  # within 1%


def test_credentialed_trades_toward_signal_above_price():
    """If signal > market price, agent should buy YES."""
    rng = np.random.default_rng(seed=0)
    market = _make_market(price_yes=0.3)
    agent = CredentialedTrader(
        "c_0", rng, true_probability=0.7, sigma=0.001
    )  # very informed: signal ≈ 0.7
    action = agent.decide(market.snapshot())
    assert action.is_yes
    assert action.shares > 0


def test_credentialed_trades_against_price_when_signal_below():
    """If signal < market price, agent should buy NO."""
    rng = np.random.default_rng(seed=0)
    market = _make_market(price_yes=0.7)
    agent = CredentialedTrader(
        "c_0", rng, true_probability=0.3, sigma=0.001
    )
    action = agent.decide(market.snapshot())
    assert not action.is_yes
    assert action.shares > 0


def test_credentialed_pool_converges_to_true_probability():
    """
    Property test: a market populated entirely by credentialed traders
    should converge to true_probability over many trades.

    This is the critical test. If this fails, the credentialed agent is
    miscalibrated and H2 results will be meaningless.
    """
    rng = np.random.default_rng(seed=42)
    true_prob = 0.65
    cfg = LSLMSRConfig(alpha=0.05, q_abmm_yes=500.0, q_abmm_no=500.0)
    market = LSLMSRMarket(config=cfg, abmm=ABMMConfig(enabled=False))

    # build 50 credentialed agents
    agents = [
        CredentialedTrader(
            f"c_{i}", rng,
            true_probability=true_prob,
            sigma=0.10,
            aggressiveness=0.5,
        )
        for i in range(50)
    ]

    # run 2000 trades
    for t in range(2000):
        agent = agents[int(rng.integers(0, len(agents)))]
        action = agent.decide(market.snapshot())
        if not action.is_noop:
            market.execute_trade(action.is_yes, action.shares)

    # final price should be within 0.05 of true_prob
    final_price = market.price_yes()
    assert abs(final_price - true_prob) < 0.05, (
        f"credentialed pool did not converge: "
        f"final={final_price:.4f}, target={true_prob}"
    )


# ---------- MomentumTrader ----------

def test_momentum_no_trade_before_lookback_filled():
    """Should produce no-op until lookback observations accumulated."""
    rng = np.random.default_rng(seed=0)
    market = _make_market(price_yes=0.5)
    agent = MomentumTrader("m_0", rng, lookback=10)
    for i in range(10):
        action = agent.decide(market.snapshot())
        assert action.is_noop


def test_momentum_buys_into_uptrend():
    """
    If price rises consistently, momentum trader should buy YES.
    Simulate this by manually building up the price history.
    """
    rng = np.random.default_rng(seed=0)
    market = _make_market(price_yes=0.5)
    agent = MomentumTrader("m_0", rng, lookback=5, threshold=0.01)

    # feed it 5 increasing prices to fill lookback at low values
    for p in [0.40, 0.42, 0.44, 0.46, 0.48]:
        # mock a market state with that price
        mock_state = {"price_yes": p, "b": 50.0}
        agent.decide(mock_state)

    # now feed a higher current price; should trigger YES buy
    current_state = {"price_yes": 0.55, "b": 50.0}
    action = agent.decide(current_state)
    assert action.is_yes
    assert action.shares > 0


# ---------- AdversarialTrader ----------

def test_adversarial_silent_before_attack_tick():
    rng = np.random.default_rng(seed=0)
    agent = AdversarialTrader(
        "adv", rng, attack_tick=100, attack_shares=50.0, attack_is_yes=True
    )
    market = _make_market()
    for t in range(100):
        state = market.snapshot()
        state["tick"] = t
        action = agent.decide(state)
        assert action.is_noop, f"attacked early at t={t}"


def test_adversarial_fires_at_attack_tick():
    rng = np.random.default_rng(seed=0)
    agent = AdversarialTrader(
        "adv", rng, attack_tick=10, attack_shares=50.0, attack_is_yes=True
    )
    market = _make_market()
    # ticks 0-9: silent
    for t in range(10):
        state = market.snapshot(); state["tick"] = t
        action = agent.decide(state)
        assert action.is_noop
    # tick 10: fires
    state = market.snapshot(); state["tick"] = 10
    action = agent.decide(state)
    assert not action.is_noop
    assert action.shares == 50.0
    assert action.is_yes


def test_adversarial_silent_after_attack():
    rng = np.random.default_rng(seed=0)
    agent = AdversarialTrader(
        "adv", rng, attack_tick=5, attack_shares=50.0, attack_is_yes=True
    )
    market = _make_market()
    # advance through and including attack
    for t in range(20):
        state = market.snapshot(); state["tick"] = t
        agent.decide(state)
    # post-attack should be noop
    state = market.snapshot(); state["tick"] = 20
    action = agent.decide(state)
    assert action.is_noop