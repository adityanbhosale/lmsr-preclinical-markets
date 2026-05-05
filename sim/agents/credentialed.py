"""
Credentialed (informed) trader.

Each agent gets a private signal s ~ Normal(true_prob, sigma^2). The agent
trades toward its signal using edge-proportional sizing. Higher conviction
(smaller sigma) → larger trades.

Design notes:
- The agent never directly observes true_prob; it observes its signal s_i.
- A market populated by credentialed traders converges to the *mean of
  their signals*, which converges to true_prob as N → ∞ (LLN).
- This is the agent class that drives H2 convergence behavior.
"""

from __future__ import annotations
import numpy as np
from .base import Agent, TradeAction


class CredentialedTrader(Agent):
    """
    Informed trader with a private signal.

    Parameters
    ----------
    sigma : float
        Standard deviation of the agent's private signal around true_prob.
        Smaller = more informed. Typical range: 0.05 (highly informed)
        to 0.20 (weakly informed).
    aggressiveness : float
        Trade size scaling. Trade size = aggressiveness * |signal - price| * b.
        Multiplying by b ensures trade sizes scale with market liquidity.
    min_edge : float
        Don't trade if |signal - price| < min_edge. Prevents constant
        small noise trades. Typical: 0.01.
    true_probability : float
        Required at construction. The agent's signal is drawn around this.
        The agent itself never accesses this attribute after init —
        signal is sampled once and stored.
    """

    def __init__(
        self,
        agent_id: str,
        rng: np.random.Generator,
        true_probability: float,
        sigma: float = 0.10,
        aggressiveness: float = 0.5,
        min_edge: float = 0.01,
    ):
        super().__init__(agent_id, rng)
        self.sigma = sigma
        self.aggressiveness = aggressiveness
        self.min_edge = min_edge

        # sample private signal once at init, store it
        # truncate to (0.001, 0.999) to avoid edge cases
        raw_signal = rng.normal(true_probability, sigma)
        self.signal = float(np.clip(raw_signal, 0.001, 0.999))

    def decide(self, market_state: dict) -> TradeAction:
        price_yes = market_state["price_yes"]
        b = market_state["b"]

        edge = self.signal - price_yes  # positive → buy YES, negative → buy NO

        if abs(edge) < self.min_edge:
            return TradeAction.noop()

        size = self.aggressiveness * abs(edge) * b
        is_yes = edge > 0

        return TradeAction(is_yes=is_yes, shares=size)