/**
 * Named SimRequest presets — TypeScript mirror of sim_v2/backend/presets.py.
 *
 * Each preset is a story. Users pick one to jump into a config that
 * reproduces a v1 finding or sets up a v1-recommended next experiment.
 * Knobs are mutable from there.
 *
 * Keep in sync with presets.py — backend is the source of truth, but
 * we mirror here so SimulatorPanel can read presets without an extra
 * fetch on every page load.
 */

import type { SimRequest } from "./protocol";

export interface PresetDef {
  id: string;
  name: string;
  description: string;
  config: SimRequest;
}

const baseStream = {
  duration_seconds: 420,
  target_fps: 8,
  n_ensemble_seeds: 16,
  ci_band_seeds: 100,
};

const baseAgent = {
  capital_per_agent: 100.0,
  disagreement_threshold: 0.03,
};

const baseSizing = {
  mode: "fixed" as const,
  base_size: 1.0,
  confidence_floor: 0.25,
  confidence_ceiling: 4.0,
};

const baseMarket = {
  alpha: 1.0,
  initial_liquidity: 100.0,
  retreat_mode: "polynomial" as const,
};

export const PRESETS: PresetDef[] = [
  {
    id: "v1_naive_baseline",
    name: "v1 baseline — 4 naive agents",
    description: "v1 Finding 1 baseline. No specialists. The diversity-comparison anchor.",
    config: {
      agent_mix: { n_naive: 4, n_aggregation: 0, n_tail: 0, n_cross: 0, n_noise: 2 },
      trade_sizing: baseSizing,
      information: { regime: "routine", signal_rate: 0.02, within_cluster_correlation: 0.6, n_markets: 3 },
      market: baseMarket,
      agent: baseAgent,
      stream: baseStream,
      horizon_ticks: 10_000,
      base_seed: 42,
    },
  },
  {
    id: "v1_all_four_diversity",
    name: "v1 all-four diversity",
    description: "v1 Finding 2 — diversity wins (7-9% Brier improvement). The headline.",
    config: {
      agent_mix: { n_naive: 1, n_aggregation: 1, n_tail: 1, n_cross: 1, n_noise: 2 },
      trade_sizing: baseSizing,
      information: { regime: "routine", signal_rate: 0.02, within_cluster_correlation: 0.6, n_markets: 3 },
      market: baseMarket,
      agent: baseAgent,
      stream: baseStream,
      horizon_ticks: 10_000,
      base_seed: 42,
    },
  },
  {
    id: "v1_high_correlation_penalty",
    name: "v1 high-correlation penalty",
    description: "v1 Finding 4 — the 2.55× correlation penalty. Same mix, high within-cluster corr.",
    config: {
      agent_mix: { n_naive: 1, n_aggregation: 1, n_tail: 1, n_cross: 1, n_noise: 2 },
      trade_sizing: baseSizing,
      information: { regime: "routine", signal_rate: 0.02, within_cluster_correlation: 0.85, n_markets: 3 },
      market: baseMarket,
      agent: baseAgent,
      stream: baseStream,
      horizon_ticks: 10_000,
      base_seed: 42,
    },
  },
  {
    id: "v1_tail_regime",
    name: "v1 tail regime",
    description: "v1 Finding 3 — capital binds in tail markets. Watch tail probabilities stay un-priced.",
    config: {
      agent_mix: { n_naive: 1, n_aggregation: 1, n_tail: 1, n_cross: 1, n_noise: 2 },
      trade_sizing: baseSizing,
      information: { regime: "tail", signal_rate: 0.005, within_cluster_correlation: 0.6, n_markets: 3 },
      market: baseMarket,
      agent: baseAgent,
      stream: baseStream,
      horizon_ticks: 10_000,
      base_seed: 42,
    },
  },
  {
    id: "exp1_capital_rich",
    name: "Experiment #1 — capital-rich ($1000)",
    description: "v1's recommended next experiment: 10× capital, watch tail markets close (or not).",
    config: {
      agent_mix: { n_naive: 1, n_aggregation: 1, n_tail: 1, n_cross: 1, n_noise: 2 },
      trade_sizing: baseSizing,
      information: { regime: "tail", signal_rate: 0.005, within_cluster_correlation: 0.6, n_markets: 3 },
      market: baseMarket,
      agent: { capital_per_agent: 1000.0, disagreement_threshold: 0.03 },
      stream: baseStream,
      horizon_ticks: 10_000,
      base_seed: 42,
    },
  },
  {
    id: "exp2_confidence_sizing",
    name: "Experiment #2 — confidence-weighted sizing",
    description: "Tests whether dynamic sizing reverses Finding 1's negative deltas.",
    config: {
      agent_mix: { n_naive: 2, n_aggregation: 0, n_tail: 1, n_cross: 0, n_noise: 2 },
      trade_sizing: { mode: "confidence_weighted", base_size: 1.0, confidence_floor: 0.25, confidence_ceiling: 4.0 },
      information: { regime: "routine", signal_rate: 0.02, within_cluster_correlation: 0.6, n_markets: 3 },
      market: baseMarket,
      agent: baseAgent,
      stream: baseStream,
      horizon_ticks: 10_000,
      base_seed: 42,
    },
  },
  {
    id: "exp3_loose_threshold",
    name: "Experiment #3 — loose disagreement threshold",
    description: "Lower threshold (0.01) → sustained convergence in tail markets.",
    config: {
      agent_mix: { n_naive: 1, n_aggregation: 1, n_tail: 1, n_cross: 1, n_noise: 2 },
      trade_sizing: baseSizing,
      information: { regime: "tail", signal_rate: 0.005, within_cluster_correlation: 0.6, n_markets: 3 },
      market: baseMarket,
      agent: { capital_per_agent: 100.0, disagreement_threshold: 0.01 },
      stream: baseStream,
      horizon_ticks: 10_000,
      base_seed: 42,
    },
  },
  {
    id: "high_capital_diversity_low_corr",
    name: "Best-case protocol design",
    description: "Synthesizes v1's findings: high capital, diversity, low correlation, confidence-weighted.",
    config: {
      agent_mix: { n_naive: 1, n_aggregation: 1, n_tail: 1, n_cross: 1, n_noise: 3 },
      trade_sizing: { mode: "confidence_weighted", base_size: 1.0, confidence_floor: 0.25, confidence_ceiling: 4.0 },
      information: { regime: "mixed", signal_rate: 0.02, within_cluster_correlation: 0.3, n_markets: 3 },
      market: baseMarket,
      agent: { capital_per_agent: 500.0, disagreement_threshold: 0.02 },
      stream: baseStream,
      horizon_ticks: 10_000,
      base_seed: 42,
    },
  },
];

export function getPresetById(id: string): PresetDef | undefined {
  return PRESETS.find((p) => p.id === id);
}
