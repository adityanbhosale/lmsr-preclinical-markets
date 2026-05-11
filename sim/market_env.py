"""
Continuous-time multi-market environment.

Wraps the validated LSLMSRMarket (parity-tested to 1e-9 against Solidity in
sim/tests/test_market_parity.py) for use in event-driven simulations. The
market math is unchanged — this module adds three things:

  1. A multi-market substrate: N independent LSLMSRMarket instances indexed
     by `market_id`, matching the information environment's market_id space.
  2. A "trade" event handler consuming TradeRequest payloads and dispatching
     to the right market.
  3. A trade log capturing (timestamp, market_id, agent_id, is_yes, shares,
     cost, price_yes_before, price_yes_after) per executed trade — feeds the
     analysis pipeline in Task 9-10.

Retreat is automatic. LSLMSRMarket._retreat_factor() recomputes from
accumulated human_volume on every price/cost call, so "continuous-time
retreat" needs no additional machinery in this layer. The default
decay_shape is "polynomial" (H1 winner), overriding ABMMConfig's default
of "exponential".

Parity strategy
---------------
This wrapper introduces no new floating-point operations beyond what
LSLMSRMarket performs internally. The test `test_event_path_matches_direct`
confirms that a sequence of trades executed via the event-driven path
produces bit-identical state to the same sequence executed via direct
LSLMSRMarket method calls. Combined with the existing test_market_parity.py
(LSLMSRMarket ↔ Solidity), this gives event-driven path ↔ Solidity parity
transitively. No drift.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from sim.events import Event
from sim.market import ABMMConfig, LSLMSRConfig, LSLMSRMarket
from sim.simulator import Simulator


# -----------------------------------------------------------------------------
# Configuration
# -----------------------------------------------------------------------------

@dataclass(frozen=True)
class MarketSpec:
    """
    Parameters applied uniformly to every market in the environment.

    LS-LMSR params:
        alpha            — liquidity coefficient (b = alpha * (q_yes + q_no))
        q_abmm_yes / no  — AMM seed liquidity per side

    Retreat params (polynomial decay is the H1 winner; default here):
        retreat_enabled     — gate the retreat function entirely
        retreat_decay_shape — "polynomial" | "exponential" | "step"
        retreat_tau         — decay rate (higher = faster retreat)
        retreat_threshold   — human volume threshold before retreat activates

    Note: defaults intentionally differ from ABMMConfig's defaults. ABMMConfig
    defaults retreat OFF with exponential shape for Solidity parity testing.
    For the agentic sim, we want retreat ON with polynomial (H1 winner).
    """
    alpha: float = 1.0
    q_abmm_yes: float = 100.0
    q_abmm_no: float = 100.0
    retreat_enabled: bool = True
    retreat_decay_shape: str = "polynomial"
    retreat_tau: float = 1.0
    retreat_threshold: float = 100.0

    def __post_init__(self) -> None:
        if self.alpha <= 0:
            raise ValueError(f"alpha must be positive, got {self.alpha}")
        if self.q_abmm_yes <= 0 or self.q_abmm_no <= 0:
            raise ValueError("q_abmm_yes and q_abmm_no must be positive")
        if self.retreat_decay_shape not in ("polynomial", "exponential", "step"):
            raise ValueError(
                f"retreat_decay_shape must be polynomial/exponential/step, "
                f"got {self.retreat_decay_shape!r}"
            )
        if self.retreat_threshold <= 0:
            raise ValueError("retreat_threshold must be positive")
        if self.retreat_tau < 0:
            raise ValueError("retreat_tau must be non-negative")

    def to_market(self) -> LSLMSRMarket:
        """Construct a single LSLMSRMarket from this spec."""
        return LSLMSRMarket(
            config=LSLMSRConfig(
                alpha=self.alpha,
                q_abmm_yes=self.q_abmm_yes,
                q_abmm_no=self.q_abmm_no,
            ),
            abmm=ABMMConfig(
                enabled=self.retreat_enabled,
                tau=self.retreat_tau,
                threshold=self.retreat_threshold,
                decay_shape=self.retreat_decay_shape,
            ),
        )


@dataclass(frozen=True)
class TradeRequest:
    """Payload for a 'trade' event scheduled by an agent."""
    market_id: int
    agent_id: int
    is_yes: bool
    shares: float

    def __post_init__(self) -> None:
        if self.market_id < 0:
            raise ValueError(f"market_id must be non-negative, got {self.market_id}")
        if self.shares <= 0:
            raise ValueError(f"shares must be positive, got {self.shares}")


@dataclass(frozen=True)
class TradeRecord:
    """Logged trade with full price-impact context."""
    timestamp: int
    market_id: int
    agent_id: int
    is_yes: bool
    shares: float
    cost: float
    price_yes_before: float
    price_yes_after: float


# -----------------------------------------------------------------------------
# Multi-market environment
# -----------------------------------------------------------------------------

class MarketEnvironment:
    """
    Multi-market continuous-time environment.

    Usage:
        env = MarketEnvironment(n_markets=15, spec=MarketSpec())
        env.register(sim)
        # ...agents schedule TradeRequest events via sim.schedule(...)...
        sim.run_until(horizon)
        # env.trade_log holds every executed trade in arrival order
    """

    TRADE_EVENT: str = "trade"

    def __init__(self, n_markets: int, spec: MarketSpec):
        if n_markets <= 0:
            raise ValueError(f"n_markets must be positive, got {n_markets}")
        self.spec = spec
        self.markets: list[LSLMSRMarket] = [spec.to_market() for _ in range(n_markets)]
        self.trade_log: list[TradeRecord] = []
        self._registered = False

    @property
    def n_markets(self) -> int:
        return len(self.markets)

    # ----- simulator integration -----

    def register(self, sim: Simulator) -> None:
        """Register the trade handler with the simulator."""
        if self._registered:
            raise RuntimeError("MarketEnvironment.register called twice")
        sim.register_handler(self.TRADE_EVENT, self._on_trade)
        self._registered = True

    def _on_trade(self, sim: Simulator, event: Event) -> None:
        req = event.payload
        if not isinstance(req, TradeRequest):
            raise TypeError(
                f"trade event payload must be TradeRequest, got {type(req).__name__}"
            )
        if req.market_id >= len(self.markets):
            raise IndexError(
                f"market_id {req.market_id} out of range (n_markets={len(self.markets)})"
            )
        m = self.markets[req.market_id]
        price_before = m.price_yes()
        cost = m.execute_trade(req.is_yes, req.shares)
        price_after = m.price_yes()
        self.trade_log.append(TradeRecord(
            timestamp=sim.now,
            market_id=req.market_id,
            agent_id=req.agent_id,
            is_yes=req.is_yes,
            shares=req.shares,
            cost=cost,
            price_yes_before=price_before,
            price_yes_after=price_after,
        ))

    # ----- batched read API for agents/analysis -----

    def price_yes(self, market_id: int) -> float:
        return self.markets[market_id].price_yes()

    def prices_yes(self) -> np.ndarray:
        """All YES prices, indexed by market_id."""
        return np.array([m.price_yes() for m in self.markets])

    def human_volumes(self) -> np.ndarray:
        return np.array([m.human_volume for m in self.markets])

    def retreat_factors(self) -> np.ndarray:
        return np.array([m._retreat_factor() for m in self.markets])

    def snapshot(self) -> list[dict]:
        return [m.snapshot() for m in self.markets]
