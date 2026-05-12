"""
sim_v2.backend.models — Pydantic schemas for the v2 WebSocket contract.

These are the ONLY types crossing the network boundary. The frontend mirrors
them in TS in `frontend/lib/protocol.ts`. Keep these two files in sync; a small
codegen pass (datamodel-code-generator or hand-mirror) is fine.

Design principle: every field that affects a finding from v1 must be settable
here, and every metric we want to display must come back through a Frame or
FinalFrame. No side-channels.
"""

from __future__ import annotations

from typing import Literal, Optional
from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Configuration — what the user sets in the SimulatorPanel
# ---------------------------------------------------------------------------


class AgentMixConfig(BaseModel):
    """Counts per agent class. v1 always used (1, 1, 1, 1) for `all_four`.
    v2 lets the user vary these to test population-composition hypotheses."""

    n_naive: int = Field(default=2, ge=0, le=10)
    n_aggregation: int = Field(default=1, ge=0, le=10)
    n_tail: int = Field(default=1, ge=0, le=10)
    n_cross: int = Field(default=1, ge=0, le=10)
    n_noise: int = Field(default=2, ge=0, le=10)

    @property
    def total(self) -> int:
        return self.n_naive + self.n_aggregation + self.n_tail + self.n_cross + self.n_noise


class TradeSizingConfig(BaseModel):
    """v1 used fixed trade_size=1.0 throughout — Finding 1 noted this masked
    specialist differentiation. v2 exposes the toggle as Experiment #2."""

    mode: Literal["fixed", "confidence_weighted"] = "fixed"
    base_size: float = Field(default=1.0, gt=0, le=10.0)
    # When confidence_weighted: size = base_size * f(posterior_precision)
    # f is bounded so size ∈ [base_size * 0.25, base_size * 4.0]
    confidence_floor: float = Field(default=0.25, gt=0, le=1.0)
    confidence_ceiling: float = Field(default=4.0, ge=1.0, le=10.0)


class InformationConfig(BaseModel):
    """The v1 information environment, exposed as user-settable parameters."""

    regime: Literal["routine", "tail", "mixed"] = "routine"
    signal_rate: float = Field(default=0.02, gt=0, le=1.0)
    within_cluster_correlation: float = Field(default=0.6, ge=0.0, le=0.95)
    n_markets: int = Field(default=3, ge=1, le=12)
    # noise_std is regime-driven: 0.7 for routine, 0.3 for tail (v1 values)


class MarketConfig(BaseModel):
    """LS-LMSR parameters. alpha=1.0 is v1 default; lowering alpha lifts the
    sigmoid(1)≈0.731 price ceiling identified in Finding 3."""

    alpha: float = Field(default=1.0, gt=0, le=5.0)
    initial_liquidity: float = Field(default=100.0, gt=0)
    retreat_mode: Literal["polynomial", "exponential", "step"] = "polynomial"
    # v1's H1 hypothesis test confirmed polynomial as winner — keep as default


class AgentConfig(BaseModel):
    """Per-agent constraints. Capital is the v1 Finding 3 binding constraint."""

    capital_per_agent: float = Field(default=100.0, gt=0, le=10000.0)
    disagreement_threshold: float = Field(default=0.03, gt=0, le=0.20)


class StreamConfig(BaseModel):
    """UX-only — controls wall-clock duration, not simulation outcomes."""

    duration_seconds: int = Field(default=420, ge=10, le=900)    # was ge=180
    target_fps: int = Field(default=8, ge=2, le=30)               # unchanged
    n_ensemble_seeds: int = Field(default=16, ge=1, le=64)        # was ge=4
    ci_band_seeds: int = Field(default=100, ge=2, le=500)         # was ge=20


class SimRequest(BaseModel):
    """Top-level config sent by the client. Single object so the WebSocket
    handshake is one message; everything else is server→client frames."""

    agent_mix: AgentMixConfig = Field(default_factory=AgentMixConfig)
    trade_sizing: TradeSizingConfig = Field(default_factory=TradeSizingConfig)
    information: InformationConfig = Field(default_factory=InformationConfig)
    market: MarketConfig = Field(default_factory=MarketConfig)
    agent: AgentConfig = Field(default_factory=AgentConfig)
    stream: StreamConfig = Field(default_factory=StreamConfig)
    horizon_ticks: int = Field(default=10_000, ge=1_000, le=100_000)
    base_seed: int = Field(default=42, ge=0)


# ---------------------------------------------------------------------------
# Frames — what flows back over the WebSocket
# ---------------------------------------------------------------------------


class TradeEvent(BaseModel):
    """Single trade since previous frame."""

    tick: int
    market_id: int
    agent_id: str
    agent_class: Literal["naive", "aggregation", "tail", "cross", "noise"]
    is_yes: bool
    shares: float
    cost: float
    price_before: float
    price_after: float


class MarketSnapshot(BaseModel):
    """Per-market state at this frame."""

    market_id: int
    price_yes: float
    p_star: float  # the true probability (revealed to client for display)
    instantaneous_brier: float  # (price - p*)^2 — frame-level diagnostic
    cumulative_volume: float
    n_trades: int


class AgentSnapshot(BaseModel):
    """Per-agent state at this frame."""

    agent_id: str
    agent_class: str
    capital_deployed: float
    capital_remaining: float
    n_trades: int
    # Position counts per market
    yes_shares_by_market: dict[int, float]
    no_shares_by_market: dict[int, float]


class FrameMessage(BaseModel):
    """Streaming update. Sent at target_fps."""

    type: Literal["frame"] = "frame"
    seed_id: int  # which seed this frame belongs to (for small multiples)
    tick: int
    wall_t: float  # seconds since stream started, for client-side debug
    markets: list[MarketSnapshot]
    trades_delta: list[TradeEvent]
    agents: list[AgentSnapshot]
    aggregate_brier: float  # mean across markets


class CIBandFrame(BaseModel):
    """Pre-computed 95% CI band for the hero seed, sent once before frames."""

    type: Literal["ci_band"] = "ci_band"
    ticks: list[int]
    brier_p025: list[float]
    brier_p975: list[float]
    brier_mean: list[float]
    price_yes_mean_by_market: dict[int, list[float]]  # str-keyed in JSON


# ---------------------------------------------------------------------------
# Final settlement — sent once at end of stream
# ---------------------------------------------------------------------------


class AgentClassPnL(BaseModel):
    """Aggregated rent extraction for one agent class."""

    agent_class: str
    n_agents: int
    mean_pnl: float
    median_pnl: float
    pnl_std: float
    pnl_per_trade: float
    total_volume: float
    win_rate: float  # fraction of agents with positive PnL


class RentExtractionSummary(BaseModel):
    """The headline metric for Metalayer-style conversations.

    Total PnL across all classes sums to (subsidy contributed by AMM −
    settlement payout to AMM). When the AMM net-pays, that's the LS-LMSR
    subsidy. When it net-receives, that's the protocol fee surface."""

    total_informed_pnl: float  # sum of (aggregation + tail + cross + naive)
    noise_trader_loss: float  # what noise pays in (positive number = they lose)
    amm_net: float  # what the AMM gives or takes from the pool
    rent_efficiency: float  # informed_pnl / |noise_loss| — how cleanly rent flows


class FinalFrame(BaseModel):
    """Sent once when the stream completes."""

    type: Literal["final"] = "final"
    seed_id: int
    final_aggregate_brier: float
    pnl_by_class: list[AgentClassPnL]
    rent_extraction: RentExtractionSummary
    # For tail-market detail (Finding 3 reproduction):
    tail_market_ids: list[int]
    tail_market_excess_gaps: dict[int, float]  # str-keyed in JSON


class ErrorFrame(BaseModel):
    """Sent if pre-compute fails or stream is interrupted."""

    type: Literal["error"] = "error"
    code: str
    message: str
    recoverable: bool = False





__all__ = [
    "AgentMixConfig",
    "TradeSizingConfig",
    "InformationConfig",
    "MarketConfig",
    "AgentConfig",
    "StreamConfig",
    "SimRequest",
    "TradeEvent",
    "MarketSnapshot",
    "AgentSnapshot",
    "FrameMessage",
    "CIBandFrame",
    "AgentClassPnL",
    "RentExtractionSummary",
    "FinalFrame",
    "ErrorFrame",
]
