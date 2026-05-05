"""Noise trader — random direction, normally-distributed size."""

from __future__ import annotations
import numpy as np
from .base import Agent, TradeAction


class NoiseTrader(Agent):
    def __init__(
        self,
        agent_id: str,
        rng: np.random.Generator,
        mean_size: float = 5.0,
        size_std: float = 2.0,
    ):
        super().__init__(agent_id, rng)
        self.mean_size = mean_size
        self.size_std = size_std

    def decide(self, market_state: dict) -> TradeAction:
        is_yes = bool(self.rng.integers(0, 2))
        size = abs(self.rng.normal(self.mean_size, self.size_std))
        return TradeAction(is_yes=is_yes, shares=size)