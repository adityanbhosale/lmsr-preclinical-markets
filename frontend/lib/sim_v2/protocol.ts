/**
 * Protocol types — mirror of sim_v2/backend/models.py.
 *
 * Keep in sync with the backend Pydantic models. The shape here is the
 * WebSocket contract; any drift between this file and models.py is the
 * source of runtime validation errors.
 *
 * agent_id is intentionally `number`, not `string`: v2 uses non-overlapping
 * integer ID ranges per agent class (0-99 naive, 100-199 aggregation,
 * 200-299 tail, 300-399 cross, 400+ noise).
 */

// ────────────────────────────────────────────────────────────────────
// Request types
// ────────────────────────────────────────────────────────────────────

export interface AgentMixConfig {
  n_naive: number;
  n_aggregation: number;
  n_tail: number;
  n_cross: number;
  n_noise: number;
}

export interface TradeSizingConfig {
  mode: "fixed" | "confidence_weighted";
  base_size: number;
  confidence_floor: number;
  confidence_ceiling: number;
}

export interface InformationConfig {
  regime: "routine" | "tail" | "mixed";
  signal_rate: number;
  within_cluster_correlation: number;
  n_markets: number;
}

export interface MarketConfig {
  alpha: number;
  initial_liquidity: number;
  retreat_mode: "polynomial" | "exponential" | "step";
}

export interface AgentConfig {
  capital_per_agent: number;
  disagreement_threshold: number;
}

export interface StreamConfig {
  duration_seconds: number;
  target_fps: number;
  n_ensemble_seeds: number;
  ci_band_seeds: number;
}

export interface SimRequest {
  agent_mix: AgentMixConfig;
  trade_sizing: TradeSizingConfig;
  information: InformationConfig;
  market: MarketConfig;
  agent: AgentConfig;
  stream: StreamConfig;
  horizon_ticks: number;
  base_seed: number;
}

// ────────────────────────────────────────────────────────────────────
// Frame types
// ────────────────────────────────────────────────────────────────────

export type AgentClass =
  | "naive"
  | "aggregation"
  | "tail"
  | "cross"
  | "noise"
  | "unknown";

export interface TradeEvent {
  tick: number;
  market_id: number;
  agent_id: number;
  agent_class: AgentClass;
  is_yes: boolean;
  shares: number;
  cost: number;
  price_before: number;
  price_after: number;
}

export interface MarketSnapshot {
  market_id: number;
  price_yes: number;
  p_star: number;
  instantaneous_brier: number;
  cumulative_volume: number;
  n_trades: number;
}

export interface AgentSnapshot {
  agent_id: number;
  agent_class: string;
  capital_deployed: number;
  capital_remaining: number;
  n_trades: number;
  yes_shares_by_market: Record<number, number>;
  no_shares_by_market: Record<number, number>;
}

export interface FrameMessage {
  type: "frame";
  seed_id: number;
  tick: number;
  wall_t: number;
  markets: MarketSnapshot[];
  trades_delta: TradeEvent[];
  agents: AgentSnapshot[];
  aggregate_brier: number;
}

export interface CIBandFrame {
  type: "ci_band";
  ticks: number[];
  brier_p025: number[];
  brier_p975: number[];
  brier_mean: number[];
  price_yes_mean_by_market: Record<string, number[]>;
}

// ────────────────────────────────────────────────────────────────────
// Final settlement types
// ────────────────────────────────────────────────────────────────────

export interface AgentClassPnL {
  agent_class: string;
  n_agents: number;
  mean_pnl: number;
  median_pnl: number;
  pnl_std: number;
  pnl_per_trade: number;
  total_volume: number;
  win_rate: number;
}

export interface RentExtractionSummary {
  total_informed_pnl: number;
  noise_trader_loss: number;
  amm_net: number;
  rent_efficiency: number;
}

export interface FinalFrame {
  type: "final";
  seed_id: number;
  final_aggregate_brier: number;
  pnl_by_class: AgentClassPnL[];
  rent_extraction: RentExtractionSummary;
  tail_market_ids: number[];
  tail_market_excess_gaps: Record<string, number>;
}

export interface ErrorFrame {
  type: "error";
  code: string;
  message: string;
  recoverable: boolean;
}

export type OutgoingMessage =
  | FrameMessage
  | CIBandFrame
  | FinalFrame
  | ErrorFrame;

// ────────────────────────────────────────────────────────────────────
// Defaults — mirror of presets.PRESETS["v1_all_four_diversity"]
// ────────────────────────────────────────────────────────────────────

export const DEFAULT_REQUEST: SimRequest = {
  agent_mix: { n_naive: 1, n_aggregation: 1, n_tail: 1, n_cross: 1, n_noise: 2 },
  trade_sizing: {
    mode: "fixed",
    base_size: 1.0,
    confidence_floor: 0.25,
    confidence_ceiling: 4.0,
  },
  information: {
    regime: "routine",
    signal_rate: 0.02,
    within_cluster_correlation: 0.6,
    n_markets: 3,
  },
  market: {
    alpha: 1.0,
    initial_liquidity: 100.0,
    retreat_mode: "polynomial",
  },
  agent: {
    capital_per_agent: 100.0,
    disagreement_threshold: 0.03,
  },
  stream: {
    duration_seconds: 180,
    target_fps: 4,
    n_ensemble_seeds: 4,
    ci_band_seeds: 20,
  },
  horizon_ticks: 1000,
  base_seed: 42,
};

// ────────────────────────────────────────────────────────────────────
// Visual constants — class palette for charts
// ────────────────────────────────────────────────────────────────────

/** Paul Tol high-contrast colorblind-friendly palette, matching v1's analysis figures. */
export const CLASS_COLOR: Record<string, string> = {
  naive: "#4477AA",
  aggregation: "#EE6677",
  tail: "#228833",
  cross: "#CCBB44",
  noise: "#BBBBBB",
  unknown: "#666666",
};

export const CLASS_LABEL: Record<string, string> = {
  naive: "Naive credentialed",
  aggregation: "Aggregation depth",
  tail: "Tail event",
  cross: "Cross-market",
  noise: "Noise",
};
