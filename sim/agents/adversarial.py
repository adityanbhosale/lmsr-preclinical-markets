"""
Adversarial trader for H1: single-shot attack at a specific runner tick.
"""

from __future__ import annotations
from .base import Agent, TradeAction


class AdversarialTrader(Agent):
    def __init__(
        self,
        agent_id: str,
        rng,
        attack_tick: int,
        attack_shares: float,
        attack_is_yes: bool = True,
    ):
        super().__init__(agent_id, rng)
        self.attack_tick = attack_tick
        self.attack_shares = attack_shares
        self.attack_is_yes = attack_is_yes
        self.has_attacked = False

    def decide(self, market_state: dict) -> TradeAction:
        if self.has_attacked:
            return TradeAction.noop()

        # read the actual runner tick from state
        tick = market_state.get("tick", 0)
        if tick < self.attack_tick:
            return TradeAction.noop()

        # fire
        self.has_attacked = True
        return TradeAction(
            is_yes=self.attack_is_yes,
            shares=self.attack_shares,
        )