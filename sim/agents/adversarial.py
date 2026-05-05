"""
Adversarial trader for H1: coordinated liquidity-withdrawal attack.

Two-phase attack:
  Phase 1 (t < attack_tick): no-op (sit silently).
  Phase 2 (t = attack_tick): execute large trade in attack_direction.
  Phase 3 (t > attack_tick): no-op (let the dust settle, observe whether
                             retreat function reverses the attack).

The interesting metric for H1 is whether the post-attack price returns
toward true probability after the attack — i.e., does the retreat function
restore informed-trader-driven price discovery, or does the attack persist?
"""

from __future__ import annotations
from .base import Agent, TradeAction


class AdversarialTrader(Agent):
    """
    Single-shot attacker. Fires once at attack_tick.

    Parameters
    ----------
    attack_tick : int
        Tick at which to execute the attack.
    attack_shares : float
        Size of the attack trade (in shares, not USDC).
    attack_is_yes : bool
        Direction of attack. True = push YES price up, False = push NO up.
    """

    def __init__(
        self,
        agent_id: str,
        rng,  # unused but required by base class
        attack_tick: int,
        attack_shares: float,
        attack_is_yes: bool = True,
    ):
        super().__init__(agent_id, rng)
        self.attack_tick = attack_tick
        self.attack_shares = attack_shares
        self.attack_is_yes = attack_is_yes
        self.has_attacked = False
        self.current_tick = 0

    def decide(self, market_state: dict) -> TradeAction:
        tick = self.current_tick
        self.current_tick += 1

        if tick < self.attack_tick or self.has_attacked:
            return TradeAction.noop()

        # fire the attack
        self.has_attacked = True
        return TradeAction(
            is_yes=self.attack_is_yes,
            shares=self.attack_shares,
        )