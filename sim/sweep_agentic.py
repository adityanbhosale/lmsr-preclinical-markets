"""
Cartesian sweep over (agent_mix × info_regime × seed).

For the agentic information-edge experiments. Default config = 6 mixes × 4
regimes × 100 seeds = 2400 runs, fitting the handoff's 2000-4000 target.

Outputs four parquet files in sim/results/:
  - runs.parquet:          one row per run, with summary metrics
  - trades.parquet:        one row per trade
  - agent_summary.parquet: one row per (run, agent)
  - snapshots.parquet:     one row per (run, snapshot_time, market)

`run_id` is the join key across tables. Every record is tagged with
(run_id, mix_name, regime_name) so the analysis pipeline (Task 10) can
group, filter, and aggregate without re-running anything.

Multiprocessing
---------------
The sweep parallelizes over runs via ProcessPoolExecutor. Each worker
calls execute_run(spec), which looks up the agent factory and info config
by name in module-level dicts (AGENT_MIXES, INFO_REGIMES). Module-level
dispatch keeps everything picklable.

Pass parallel=False to run serially — useful for debugging or when one
process is enough.
"""
from __future__ import annotations

import os
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass
from typing import Optional

import numpy as np
import pandas as pd

from sim.agentic import (
    AggregationDepthAgent,
    NaiveCredentialedAgent,
    NoiseTrader,
    TailEventReasoningAgent,
    base_rates_from_truth,
    cross_weights_from_loadings,
    make_cross_market_agent,
)
from sim.information import ClusterSpec, InformationConfig
from sim.market_env import MarketSpec
from sim.runner_agentic import RunResults, run_sim


# =============================================================================
# Agent mixes
# =============================================================================
# Each mix is a module-level callable that takes (info_env, rng) and returns
# a list of agents. Module-level (no closures) so workers can pickle them.

def _market_ids(info_env) -> tuple:
    return tuple(range(info_env.n_markets))


def make_noise_only(info_env, rng):
    """Pure noise traders — baseline for 'no information' market."""
    market_ids = _market_ids(info_env)
    return [
        NoiseTrader(
            agent_id=i, budget=300.0, market_ids=market_ids,
            arrival_rate_per_unit=3.0,
        )
        for i in range(3)
    ]


def make_naive_only(info_env, rng):
    """Naive credentialed agents only (modal-anchor baseline)."""
    market_ids = _market_ids(info_env)
    agents = [
        NaiveCredentialedAgent(
            agent_id=i, budget=100.0, market_ids=market_ids,
            observation_delay=100, review_interval=1000,
            prior_precision=2.0, signal_precision_assumed=1.0,
            disagreement_threshold=0.03, trade_size=1.0,
        )
        for i in range(3)
    ]
    agents.append(NoiseTrader(
        agent_id=3, budget=200.0, market_ids=market_ids,
        arrival_rate_per_unit=2.0,
    ))
    return agents


def make_plus_tail(info_env, rng):
    """Two naive credentialed + one tail-event reasoning + noise."""
    market_ids = _market_ids(info_env)
    base = base_rates_from_truth(info_env, market_ids, rng, noise_std=0.3)
    return [
        NaiveCredentialedAgent(
            agent_id=0, budget=100.0, market_ids=market_ids,
            observation_delay=100, review_interval=1000,
            prior_precision=2.0, disagreement_threshold=0.03, trade_size=1.0,
        ),
        NaiveCredentialedAgent(
            agent_id=1, budget=100.0, market_ids=market_ids,
            observation_delay=100, review_interval=1000,
            prior_precision=2.0, disagreement_threshold=0.03, trade_size=1.0,
        ),
        TailEventReasoningAgent(
            agent_id=2, budget=100.0, market_ids=market_ids,
            base_rates=base, review_interval=1000,
            prior_precision=1.0, disagreement_threshold=0.03, trade_size=1.0,
        ),
        NoiseTrader(
            agent_id=3, budget=200.0, market_ids=market_ids,
            arrival_rate_per_unit=2.0,
        ),
    ]


def make_plus_aggregation(info_env, rng):
    """Two naive credentialed + one aggregation-depth + noise."""
    market_ids = _market_ids(info_env)
    cw = cross_weights_from_loadings(
        info_env.world.loadings_matrix,
        primary_markets=market_ids, observed_markets=market_ids,
    )
    return [
        NaiveCredentialedAgent(
            agent_id=0, budget=100.0, market_ids=market_ids,
            observation_delay=100, review_interval=1000,
            prior_precision=2.0, disagreement_threshold=0.03, trade_size=1.0,
        ),
        NaiveCredentialedAgent(
            agent_id=1, budget=100.0, market_ids=market_ids,
            observation_delay=100, review_interval=1000,
            prior_precision=2.0, disagreement_threshold=0.03, trade_size=1.0,
        ),
        AggregationDepthAgent(
            agent_id=2, budget=100.0, market_ids=market_ids,
            observed_markets=market_ids, cross_weights=cw,
            review_interval=500, prior_precision=1.0,
            disagreement_threshold=0.03, trade_size=1.0,
        ),
        NoiseTrader(
            agent_id=3, budget=200.0, market_ids=market_ids,
            arrival_rate_per_unit=2.0,
        ),
    ]


def make_plus_cross(info_env, rng):
    """Two naive credentialed + one cross-market consistency + noise."""
    market_ids = _market_ids(info_env)
    return [
        NaiveCredentialedAgent(
            agent_id=0, budget=100.0, market_ids=market_ids,
            observation_delay=100, review_interval=1000,
            prior_precision=2.0, disagreement_threshold=0.03, trade_size=1.0,
        ),
        NaiveCredentialedAgent(
            agent_id=1, budget=100.0, market_ids=market_ids,
            observation_delay=100, review_interval=1000,
            prior_precision=2.0, disagreement_threshold=0.03, trade_size=1.0,
        ),
        make_cross_market_agent(
            agent_id=2, budget=100.0,
            primary_markets=market_ids, observed_markets=market_ids,
            info_env=info_env, review_interval=1000,
            disagreement_threshold=0.03, trade_size=1.0,
        ),
        NoiseTrader(
            agent_id=3, budget=200.0, market_ids=market_ids,
            arrival_rate_per_unit=2.0,
        ),
    ]


def make_all_four(info_env, rng):
    """One of each sophisticated agent type + noise."""
    market_ids = _market_ids(info_env)
    base = base_rates_from_truth(info_env, market_ids, rng, noise_std=0.3)
    cw = cross_weights_from_loadings(
        info_env.world.loadings_matrix,
        primary_markets=market_ids, observed_markets=market_ids,
    )
    return [
        NaiveCredentialedAgent(
            agent_id=0, budget=100.0, market_ids=market_ids,
            observation_delay=100, review_interval=1000,
            prior_precision=2.0, disagreement_threshold=0.03, trade_size=1.0,
        ),
        TailEventReasoningAgent(
            agent_id=1, budget=100.0, market_ids=market_ids,
            base_rates=base, review_interval=1000,
            prior_precision=1.0, disagreement_threshold=0.03, trade_size=1.0,
        ),
        AggregationDepthAgent(
            agent_id=2, budget=100.0, market_ids=market_ids,
            observed_markets=market_ids, cross_weights=cw,
            review_interval=500, prior_precision=1.0,
            disagreement_threshold=0.03, trade_size=1.0,
        ),
        make_cross_market_agent(
            agent_id=3, budget=100.0,
            primary_markets=market_ids, observed_markets=market_ids,
            info_env=info_env, review_interval=1000,
            disagreement_threshold=0.03, trade_size=1.0,
        ),
        NoiseTrader(
            agent_id=4, budget=200.0, market_ids=market_ids,
            arrival_rate_per_unit=2.0,
        ),
    ]


AGENT_MIXES: dict = {
    "noise_only": make_noise_only,
    "naive_only": make_naive_only,
    "plus_tail": make_plus_tail,
    "plus_aggregation": make_plus_aggregation,
    "plus_cross": make_plus_cross,
    "all_four": make_all_four,
}


# =============================================================================
# Information regimes
# =============================================================================
# Each regime is a static InformationConfig. 2×2 grid:
#   (routine | tail) × (low_corr | high_corr)
#
# Correlation is set via primary_loading_std:
#   low_corr  → high std (β_m vary a lot within cluster, weakly aligned)
#   high_corr → low std  (β_m similar within cluster, strongly aligned)

def _make_info_config(
    *, tail_rate: float, primary_loading_mean: float, primary_loading_std: float,
) -> InformationConfig:
    return InformationConfig(
        k=3,
        clusters=[ClusterSpec(
            primary_factor=0, market_count=5,
            primary_loading_mean=primary_loading_mean,
            primary_loading_std=primary_loading_std,
        )],
        idiosyncratic_std=0.15,
        routine_rate_per_market=3.0,
        tail_rate_per_market=tail_rate,
        signal_noise_std=0.7,
        tail_noise_std=0.3,
    )


INFO_REGIMES: dict = {
    "routine_low_corr":  _make_info_config(
        tail_rate=0.1, primary_loading_mean=1.0, primary_loading_std=0.6,
    ),
    "routine_high_corr": _make_info_config(
        tail_rate=0.1, primary_loading_mean=2.0, primary_loading_std=0.1,
    ),
    "tail_low_corr":     _make_info_config(
        tail_rate=0.8, primary_loading_mean=1.0, primary_loading_std=0.6,
    ),
    "tail_high_corr":    _make_info_config(
        tail_rate=0.8, primary_loading_mean=2.0, primary_loading_std=0.1,
    ),
}


# =============================================================================
# Sweep types
# =============================================================================

@dataclass(frozen=True)
class RunSpec:
    """Identifies one run in the sweep grid."""
    run_id: int
    mix_name: str
    regime_name: str
    seed: int
    horizon: int
    snapshot_interval: int


@dataclass
class SweepConfig:
    """Sweep grid configuration."""
    mix_names: tuple
    regime_names: tuple
    n_seeds_per_cell: int = 100
    horizon: int = 30_000
    snapshot_interval: int = 5_000

    def __post_init__(self) -> None:
        for m in self.mix_names:
            if m not in AGENT_MIXES:
                raise ValueError(
                    f"unknown mix {m!r}; known: {sorted(AGENT_MIXES)}"
                )
        for r in self.regime_names:
            if r not in INFO_REGIMES:
                raise ValueError(
                    f"unknown regime {r!r}; known: {sorted(INFO_REGIMES)}"
                )
        if self.n_seeds_per_cell <= 0:
            raise ValueError("n_seeds_per_cell must be positive")
        if self.horizon <= 0:
            raise ValueError("horizon must be positive")
        if self.snapshot_interval < 0:
            raise ValueError("snapshot_interval must be non-negative")

    @property
    def total_runs(self) -> int:
        return len(self.mix_names) * len(self.regime_names) * self.n_seeds_per_cell


DEFAULT_SWEEP: SweepConfig = SweepConfig(
    mix_names=(
        "noise_only", "naive_only", "plus_tail",
        "plus_aggregation", "plus_cross", "all_four",
    ),
    regime_names=(
        "routine_low_corr", "routine_high_corr",
        "tail_low_corr", "tail_high_corr",
    ),
    n_seeds_per_cell=100,
    horizon=30_000,
    snapshot_interval=5_000,
)


def enumerate_runs(cfg: SweepConfig) -> list[RunSpec]:
    """Cartesian enumeration in (mix, regime, seed) order."""
    runs: list[RunSpec] = []
    run_id = 0
    for mix in cfg.mix_names:
        for regime in cfg.regime_names:
            for seed in range(cfg.n_seeds_per_cell):
                runs.append(RunSpec(
                    run_id=run_id, mix_name=mix, regime_name=regime,
                    seed=seed, horizon=cfg.horizon,
                    snapshot_interval=cfg.snapshot_interval,
                ))
                run_id += 1
    return runs


# =============================================================================
# Execution
# =============================================================================

@dataclass
class RunRecords:
    """Flat records from one run, tagged with sweep metadata."""
    summary: dict
    trades: list
    agent_summary: list
    snapshots: list


def _tag(d: dict, spec: RunSpec) -> dict:
    """Add (run_id, mix_name, regime_name) to a flat record."""
    d = dict(d)
    d["run_id"] = spec.run_id
    d["mix_name"] = spec.mix_name
    d["regime_name"] = spec.regime_name
    return d


def execute_run(spec: RunSpec) -> RunRecords:
    """
    Execute one run and return tagged flat records.

    Module-level so it's picklable for multiprocessing workers.
    """
    info_config = INFO_REGIMES[spec.regime_name]
    make_agents = AGENT_MIXES[spec.mix_name]
    res = run_sim(
        info_config=info_config,
        make_agents=make_agents,
        horizon=spec.horizon,
        seed=spec.seed,
        snapshot_interval=spec.snapshot_interval,
    )
    summary = _tag(res.summary_record(), spec)
    trades = [_tag(r, spec) for r in res.trade_records()]
    agents_ = [_tag(r, spec) for r in res.agent_summary_records()]
    snaps = [_tag(r, spec) for r in res.snapshot_records()]
    return RunRecords(
        summary=summary, trades=trades,
        agent_summary=agents_, snapshots=snaps,
    )


def run_sweep(
    cfg: SweepConfig,
    *,
    parallel: bool = True,
    n_workers: Optional[int] = None,
    progress_every: int = 0,
) -> dict:
    """
    Execute every run in the sweep grid.

    Returns a dict with four lists of flat-record dicts: "summary", "trades",
    "agent_summary", "snapshots". Pass to `write_sweep` to persist to parquet.

    Parameters
    ----------
    cfg : SweepConfig
        Sweep grid.
    parallel : bool
        If True (default), use ProcessPoolExecutor. If False, run serially.
    n_workers : int, optional
        Number of worker processes when parallel=True. Default: os.cpu_count().
    progress_every : int
        Print progress every K runs (serial only); 0 disables.
    """
    runs = enumerate_runs(cfg)
    summary_records: list = []
    trade_records: list = []
    agent_records: list = []
    snapshot_records: list = []

    def _accumulate(rec: RunRecords) -> None:
        summary_records.append(rec.summary)
        trade_records.extend(rec.trades)
        agent_records.extend(rec.agent_summary)
        snapshot_records.extend(rec.snapshots)

    if parallel:
        with ProcessPoolExecutor(max_workers=n_workers) as pool:
            for rec in pool.map(execute_run, runs):
                _accumulate(rec)
    else:
        for i, spec in enumerate(runs):
            rec = execute_run(spec)
            _accumulate(rec)
            if progress_every > 0 and ((i + 1) % progress_every == 0):
                print(f"  ... {i + 1}/{len(runs)} runs complete")

    return {
        "summary": summary_records,
        "trades": trade_records,
        "agent_summary": agent_records,
        "snapshots": snapshot_records,
    }


# =============================================================================
# Parquet I/O
# =============================================================================

def write_sweep(results: dict, output_dir: str) -> dict:
    """
    Write each table in `results` to its own parquet file in `output_dir`.

    Returns a dict mapping table name -> output path. Tables with zero rows
    are skipped silently.
    """
    os.makedirs(output_dir, exist_ok=True)
    paths: dict = {}
    for table_name, records in results.items():
        if not records:
            continue
        df = pd.DataFrame(records)
        path = os.path.join(output_dir, f"{table_name}.parquet")
        df.to_parquet(path, engine="pyarrow", index=False)
        paths[table_name] = path
    return paths


def read_sweep(output_dir: str) -> dict:
    """
    Read sweep parquet files back into a dict of DataFrames.

    Missing tables map to empty DataFrames (so callers can use .empty checks).
    """
    out: dict = {}
    for table_name in ("summary", "trades", "agent_summary", "snapshots"):
        path = os.path.join(output_dir, f"{table_name}.parquet")
        if os.path.exists(path):
            out[table_name] = pd.read_parquet(path, engine="pyarrow")
        else:
            out[table_name] = pd.DataFrame()
    return out
