"""
Base agent class. All agent classes implement decide(market_state, rng).
"""

from __future__ import annotations
from abc import ABC, abstractmethod
from dataclasses import dataclass
import numpy as np


@dataclass
class TradeAction:
    """
    An agent's decision for one tick.
    is_yes=True means buy YES shares, False means buy NO shares.
    shares=0 means no-op.
    """
    is_yes: bool = True
    shares: float = 0.0

    @classmethod
    def noop(cls) -> "TradeAction":
        return cls(is_yes=True, shares=0.0)

    @property
    def is_noop(self) -> bool:
        return self.shares <= 0


class Agent(ABC):
    """Abstract base for all simulated traders."""

    def __init__(self, agent_id: str, rng: np.random.Generator):
        self.agent_id = agent_id
        self.rng = rng

    @abstractmethod
    def decide(self, market_state: dict) -> TradeAction:
        """
        Given a market snapshot, return a trade action.
        market_state shape matches LSLMSRMarket.snapshot().
        """
        ...