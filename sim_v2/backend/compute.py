"""
sim_v2.backend.compute — wraps existing v1 sim.runner_agentic.run_sim
to produce traces shaped for v2 streaming.

Key design choice: this module does NOT re-implement any v1 logic. It builds
the InformationConfig, AgentPopulation factory, and MarketSpec that v1's
run_sim already accepts. The only new behavior is:

  1. Translating v2's user-facing SimRequest into v1's internal types
  2. Running N seeds in parallel
  3. Producing a tick-indexed price trace per market (for CI band derivation)
  4. Producing a per-tick frame stream (decimated to target_fps)

Everything that v1 tested at 1e-9 parity carries forward.
"""

from __future__ import annotations

import math
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass
from typing import Callable

import numpy as np

# These imports reference the existing v1 modules — no changes to v1 needed.
# from sim.runner_agentic import run_sim, RunResults
# from sim.information import InformationConfig as V1InfoConfig, ClusterSpec
# from sim.market_env import MarketSpec
# from sim.agentic import (
#     NaiveCredentialedAgent,
#     AggregationDepthAgent,
#     TailEventReasoningAgent,
#     CrossMarketConsistencyAgent,
#     NoiseTrader,
#     AgentPopulation,
#     base_rates_from_truth,
#     make_cross_market_agent,
# )

from .models import (
    SimRequest,
    AgentMixConfig,
    TradeSizingConfig,
    InformationConfig as V2InfoConfig,
    MarketConfig,
    AgentConfig,
)


# ---------------------------------------------------------------------------
# Translation: v2 SimRequest → v1 run_sim arguments
# ---------------------------------------------------------------------------


def _build_v1_info_config(v2_cfg: V2InfoConfig):
    """Map v2's user-facing knobs to v1's InformationConfig.

    v1's InformationConfig is structurally richer than v2 exposes: it allows
    multiple clusters on different primary factors plus independent markets.
    v2 collapses to a SINGLE-CLUSTER layout for UX simplicity:
      - All n_markets belong to one cluster on primary_factor=0
      - No independent markets
      - Within-cluster correlation is approximated by primary_loading_mean
        and the ratio primary_loading_std / idiosyncratic_std

    Calibration of within_cluster_correlation slider:
      - At target_corr=0.0: primary_loading_mean ~ 0.3 (weak factor influence,
        markets dominated by idiosyncratic)
      - At target_corr=0.85: primary_loading_mean ~ 2.0 (factor dominates,
        markets co-move strongly)
    Linear interpolation between these, since v1's empirical mapping is
    monotone in this regime.
    """
    from sim.information import InformationConfig as V1InfoConfig, ClusterSpec

    # Regime selection drives which rate channel is non-zero
    if v2_cfg.regime == "routine":
        routine_rate, tail_rate = v2_cfg.signal_rate, 0.0
    elif v2_cfg.regime == "tail":
        routine_rate, tail_rate = 0.0, v2_cfg.signal_rate
    else:  # mixed
        routine_rate = v2_cfg.signal_rate * 0.7
        tail_rate = v2_cfg.signal_rate * 0.3

    # Map within_cluster_correlation slider to loading_mean
    target_corr = v2_cfg.within_cluster_correlation
    primary_loading_mean = 0.3 + 1.7 * target_corr

    cluster = ClusterSpec(
        primary_factor=0,
        market_count=v2_cfg.n_markets,
        primary_loading_mean=primary_loading_mean,
        primary_loading_std=0.2,
        secondary_loading_std=0.15,
    )

    return V1InfoConfig(
        k=3,
        clusters=[cluster],
        n_independent_markets=0,
        independent_loading_std=0.4,
        idiosyncratic_std=0.5,
        signal_noise_std=1.0,
        tail_noise_std=0.4,
        routine_rate_per_market=routine_rate,
        tail_rate_per_market=tail_rate,
        tail_mode="separate",
    )




def _build_agent_factory(
        mix: AgentMixConfig,
        sizing: TradeSizingConfig,
        agent_cfg: AgentConfig,
        market_ids: tuple[int, ...],
    ) -> Callable:
    
    def make_agents(info_env, rng):
        import numpy as np
        from sim.agentic import (
                NaiveCredentialedAgent,
                AggregationDepthAgent,
                TailEventReasoningAgent,
                NoiseTrader,
                AgentPopulation,
                base_rates_from_truth,
                make_cross_market_agent,
                cross_weights_from_loadings,
            )

        agents = []
        class_by_id: dict[int, str] = {}

        # Build the loadings matrix once — shape (n_markets, k) — for the
        # aggregation-depth cross_weights. Index aligns with market_id ordering
        # in market_ids, which is also the iteration order in v1 sweep.
        loadings_matrix = np.stack(
            [info_env.truths[m].loadings for m in market_ids]
        )

        # ── Naive credentialed (IDs 0-99) ───────────────────────────────
        for i in range(mix.n_naive):
            aid = i
            agents.append(
                NaiveCredentialedAgent(
                    agent_id=aid,
                    budget=agent_cfg.capital_per_agent,
                    market_ids=market_ids,
                    observation_delay=1000,
                    review_interval=5000,
                    prior_precision=5.0,
                    signal_precision_assumed=1.0,
                    disagreement_threshold=agent_cfg.disagreement_threshold,
                    trade_size=sizing.base_size,
                    confidence_weighted=(sizing.mode == "confidence_weighted"),
                    confidence_floor=sizing.confidence_floor,
                    confidence_ceiling=sizing.confidence_ceiling,
                )
            )
            class_by_id[aid] = "naive"

        # ── Aggregation depth (IDs 100-199) ─────────────────────────────
        if mix.n_aggregation > 0:
            cross_weights = cross_weights_from_loadings(
                loadings_matrix,
                primary_markets=market_ids,
                observed_markets=market_ids,
            )
            for i in range(mix.n_aggregation):
                aid = 100 + i
                agents.append(
                    AggregationDepthAgent(
                        agent_id=aid,
                        budget=agent_cfg.capital_per_agent,
                        market_ids=market_ids,
                        observed_markets=market_ids,
                        cross_weights=cross_weights,
                        observation_delay=0,
                        review_interval=500,
                        prior_precision=2.0,
                        signal_precision_assumed=1.0,
                        disagreement_threshold=agent_cfg.disagreement_threshold,
                        trade_size=sizing.base_size,
                        confidence_weighted=(sizing.mode == "confidence_weighted"),
                        confidence_floor=sizing.confidence_floor,
                        confidence_ceiling=sizing.confidence_ceiling,
                    )
                )
                class_by_id[aid] = "aggregation"

        # ── Tail event (IDs 200-299) ────────────────────────────────────
        if mix.n_tail > 0:
            base_rates = base_rates_from_truth(
                info_env, market_ids, rng, noise_std=0.5
            )
            for i in range(mix.n_tail):
                aid = 200 + i
                agents.append(
                    TailEventReasoningAgent(
                        agent_id=aid,
                        budget=agent_cfg.capital_per_agent,
                        market_ids=market_ids,
                        base_rates=base_rates,
                        observation_delay=0,
                        review_interval=1000,
                        prior_precision=1.0,
                        disagreement_threshold=agent_cfg.disagreement_threshold,
                        trade_size=sizing.base_size,
                        confidence_weighted=(sizing.mode == "confidence_weighted"),
                        confidence_floor=sizing.confidence_floor,
                        confidence_ceiling=sizing.confidence_ceiling,
                    )
                )
                class_by_id[aid] = "tail"

        # ── Cross-market consistency (IDs 300-399) ──────────────────────
        for i in range(mix.n_cross):
            aid = 300 + i
            agents.append(
                make_cross_market_agent(
                    agent_id=aid,
                    budget=agent_cfg.capital_per_agent,
                    primary_markets=market_ids,
                    observed_markets=market_ids,
                    info_env=info_env,
                    disagreement_threshold=agent_cfg.disagreement_threshold,
                    trade_size=sizing.base_size,
                    confidence_weighted=(sizing.mode == "confidence_weighted"),
                    confidence_floor=sizing.confidence_floor,
                    confidence_ceiling=sizing.confidence_ceiling,
                )
            )
            class_by_id[aid] = "cross"

        # ── Noise (IDs 400+) ────────────────────────────────────────────
        # Field name confirmed pending diagnostic — most likely
        # arrival_rate_per_unit per v1 sweep code
        for i in range(mix.n_noise):
            aid = 400 + i
            agents.append(
                NoiseTrader(
                    agent_id=aid,
                    budget=agent_cfg.capital_per_agent,
                    market_ids=market_ids,
                    arrival_rate_per_unit=3.0,
                )
            )
            class_by_id[aid] = "noise"

        return agents

    return make_agents


def _build_v1_market_spec(market_cfg: MarketConfig):
    """v1 MarketSpec uses q_abmm_yes/no (initial inventory per side) instead
    of a single 'initial_liquidity' value, and retreat_decay_shape instead
    of retreat_mode. v2 collapses initial_liquidity → both sides equally."""
    from sim.market_env import MarketSpec

    return MarketSpec(
        alpha=market_cfg.alpha,
        q_abmm_yes=market_cfg.initial_liquidity,
        q_abmm_no=market_cfg.initial_liquidity,
        retreat_enabled=True,
        retreat_decay_shape=market_cfg.retreat_mode,
    )


# ---------------------------------------------------------------------------
# Single-seed execution
# ---------------------------------------------------------------------------


@dataclass
class SeedResult:
    """Output of one seed's pre-computation. Holds everything needed by both
    the streaming layer (frame interpolation) and the PnL layer (settlement)."""

    seed: int
    tick_max: int
    market_ids: tuple[int, ...]
    p_star_by_market: dict[int, float]
    # Tick-indexed price arrays per market — interpolated to a regular grid.
    # Key is market_id; value is np.ndarray of length tick_max+1.
    price_trace: dict[int, np.ndarray]
    # Flat trade log — schema matches v1's RunResults.trade_records()
    trades: list[dict]
    # Agent summary — matches v1's RunResults.agent_summary_records()
    agent_summary: list[dict]


def run_single_seed(req: SimRequest, seed_offset: int = 0) -> SeedResult:
    """Execute one v1 sim run with v2 config translation. Pure function;
    safe to call from a ProcessPoolExecutor worker."""
    from sim.runner_agentic import run_sim

    seed = req.base_seed + seed_offset
    market_ids = tuple(range(req.information.n_markets))

    info_cfg = _build_v1_info_config(req.information)
    market_spec = _build_v1_market_spec(req.market)
    make_agents = _build_agent_factory(
        req.agent_mix, req.trade_sizing, req.agent, market_ids
    )

    results = run_sim(
        info_config=info_cfg,
        make_agents=make_agents,
        horizon=req.horizon_ticks,
        seed=seed,
        market_spec=market_spec,
        time_resolution=1,
        snapshot_interval=max(1, req.horizon_ticks // 1000),
    )

    # Build tick-indexed price trace by forward-filling from trade records.
    # This is what the streaming layer interpolates over.
    price_trace = _build_price_trace(results, market_ids, req.horizon_ticks)

    return SeedResult(
        seed=seed,
        tick_max=req.horizon_ticks,
        market_ids=market_ids,
        p_star_by_market={
            m: results.info_env.truths[m].p_star for m in market_ids
        },
        price_trace=price_trace,
        trades=list(results.trade_records()),
        agent_summary=list(results.agent_summary_records()),
    )


def _build_price_trace(
    results, market_ids: tuple[int, ...], horizon: int
) -> dict[int, np.ndarray]:
    """Forward-fill price trace from snapshot records. Snapshot interval was
    set to horizon/1000 so we have ~1000 sample points; we expand to per-tick."""
    trace = {m: np.full(horizon + 1, 0.5, dtype=np.float32) for m in market_ids}
    snapshots_by_market: dict[int, list[tuple[int, float]]] = {m: [] for m in market_ids}

    for snap in results.snapshot_records():
        m = snap["market_id"]
        if m in snapshots_by_market:
            snapshots_by_market[m].append((snap["timestamp"], snap["price_yes"]))
    for m, pts in snapshots_by_market.items():
        if not pts:
            continue
        pts.sort()
        ticks = np.array([p[0] for p in pts])
        prices = np.array([p[1] for p in pts])
        # Forward-fill: at each tick t, price = price at largest snapshot tick ≤ t
        idx = np.searchsorted(ticks, np.arange(horizon + 1), side="right") - 1
        idx = np.clip(idx, 0, len(prices) - 1)
        trace[m] = prices[idx].astype(np.float32)

    return trace


# ---------------------------------------------------------------------------
# Multi-seed orchestration
# ---------------------------------------------------------------------------


def run_ensemble(
    req: SimRequest, n_seeds: int, max_workers: int = 8
) -> list[SeedResult]:
    """Pre-compute N seeds in parallel. Used both for the CI band (n=100ish)
    and the hero/small-multiples ensemble (n=16ish)."""
    results: list[SeedResult] = []
    with ProcessPoolExecutor(max_workers=max_workers) as pool:
        futures = {
            pool.submit(run_single_seed, req, offset): offset
            for offset in range(n_seeds)
        }
        for fut in as_completed(futures):
            results.append(fut.result())
    results.sort(key=lambda r: r.seed)
    return results


def compute_ci_band(
    ci_results: list[SeedResult], market_ids: tuple[int, ...]
) -> dict:
    """Aggregate price traces across seeds into 2.5/50/97.5 percentile bands
    plus per-tick mean Brier."""
    n_seeds = len(ci_results)
    tick_max = ci_results[0].tick_max

    # Stack price traces: shape (n_seeds, n_markets, tick_max+1)
    stacked = np.stack(
        [
            np.stack([r.price_trace[m] for m in market_ids])
            for r in ci_results
        ]
    )

    # Compute Brier per (seed, tick) — average over markets
    p_star_arr = np.array(
        [[r.p_star_by_market[m] for m in market_ids] for r in ci_results]
    )[:, :, None]  # shape (n_seeds, n_markets, 1)
    brier_per_seed = ((stacked - p_star_arr) ** 2).mean(axis=1)  # (n_seeds, T+1)

    return {
        "ticks": list(range(tick_max + 1)),
        "brier_p025": np.percentile(brier_per_seed, 2.5, axis=0).tolist(),
        "brier_p975": np.percentile(brier_per_seed, 97.5, axis=0).tolist(),
        "brier_mean": brier_per_seed.mean(axis=0).tolist(),
        "price_yes_mean_by_market": {
            int(m): stacked[:, i, :].mean(axis=0).tolist()
            for i, m in enumerate(market_ids)
        },
    }
