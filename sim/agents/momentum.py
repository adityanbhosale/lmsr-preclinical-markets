"""
Momentum (trend-following) trader.

Looks at the last N price observations and trades in the direction of the
recent move. Amplifies trends; can delay or accelerate convergence depending
on the dominant counterparty class.

Design notes:
- Pure trend-follower: no view on true probability. Just rides the move.
- Lookback determines responsiveness vs. noise filtering.
- This agent class makes H1 attacks more dangerous (it amplifies the
  attacker's push) and H2 convergence noisier (it overshoots informed
  signals).
"""

from __future__ import annotations
from collections import deque
import numpy as np
from .base import Agent, TradeAction


class MomentumTrader(Agent):
    """
    Trend-following trader.

    Parameters
    ----------
    lookback : int
        Number of recent prices to track. Trade decision based on
        delta = current_price - mean(lookback prices).
    threshold : float
        Don't trade if |delta| < threshold. Prevents noise-trading.
    aggressiveness : float
        Trade size = aggressiveness * |delta| * b.
    """

    def __init__(
        self,
        agent_id: str,
        rng: np.random.Generator,
        lookback: int = 15,
        threshold: float = 0.02,
        aggressiveness: float = 0.3,
    ):
        super().__init__(agent_id, rng)
        self.lookback = lookback
        self.threshold = threshold
        self.aggressiveness = aggressiveness
        self.price_history: deque = deque(maxlen=lookback)

    def decide(self, market_state: dict) -> TradeAction:
        price_yes = market_state["price_yes"]
        b = market_state["b"]

        # need at least lookback observations before trading
        if len(self.price_history) < self.lookback:
            self.price_history.append(price_yes)
            return TradeAction.noop()

        # compute momentum signal
        mean_recent = np.mean(self.price_history)
        delta = price_yes - mean_recent

        # update history *after* computing signal
        self.price_history.append(price_yes)

        if abs(delta) < self.threshold:
            return TradeAction.noop()

        # trade in the direction of the move
        size = self.aggressiveness * abs(delta) * b
        is_yes = delta > 0

        return TradeAction(is_yes=is_yes, shares=size)