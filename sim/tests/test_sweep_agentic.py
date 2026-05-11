"""
Tests for sim/sweep_agentic.py.

Covers:
  - Sweep config validation
  - Enumeration produces correct run count and IDs
  - Single-run execute_run returns tagged records
  - Serial sweep produces expected aggregate records
  - Parallel sweep produces IDENTICAL records to serial (determinism)
  - Parquet round-trip preserves data
  - Statistical sanity: regimes produce distinguishable results
"""
from __future__ import annotations

import os
import tempfile

import numpy as np
import pandas as pd
import pytest

from sim.sweep_agentic import (
    AGENT_MIXES,
    DEFAULT_SWEEP,
    INFO_REGIMES,
    RunRecords,
    RunSpec,
    SweepConfig,
    enumerate_runs,
    execute_run,
    read_sweep,
    run_sweep,
    write_sweep,
)


# =============================================================================
# Config validation
# =============================================================================

class TestSweepConfig:
    def test_unknown_mix_rejected(self):
        with pytest.raises(ValueError, match="unknown mix"):
            SweepConfig(mix_names=("not_a_mix",), regime_names=("tail_high_corr",))

    def test_unknown_regime_rejected(self):
        with pytest.raises(ValueError, match="unknown regime"):
            SweepConfig(mix_names=("naive_only",), regime_names=("not_a_regime",))

    def test_n_seeds_must_be_positive(self):
        with pytest.raises(ValueError, match="n_seeds_per_cell"):
            SweepConfig(
                mix_names=("naive_only",), regime_names=("tail_high_corr",),
                n_seeds_per_cell=0,
            )

    def test_horizon_must_be_positive(self):
        with pytest.raises(ValueError, match="horizon"):
            SweepConfig(
                mix_names=("naive_only",), regime_names=("tail_high_corr",),
                horizon=0,
            )

    def test_total_runs_property(self):
        cfg = SweepConfig(
            mix_names=("naive_only", "plus_tail"),
            regime_names=("routine_low_corr", "tail_high_corr"),
            n_seeds_per_cell=10,
        )
        assert cfg.total_runs == 2 * 2 * 10

    def test_default_sweep_2400_runs(self):
        assert DEFAULT_SWEEP.total_runs == 2400


# =============================================================================
# Enumerate
# =============================================================================

class TestEnumerateRuns:
    def test_total_run_count_matches_total_runs(self):
        cfg = SweepConfig(
            mix_names=("naive_only", "plus_tail"),
            regime_names=("tail_high_corr", "routine_low_corr"),
            n_seeds_per_cell=5,
        )
        runs = enumerate_runs(cfg)
        assert len(runs) == cfg.total_runs

    def test_run_ids_unique_and_sequential(self):
        cfg = SweepConfig(
            mix_names=("naive_only", "plus_tail"),
            regime_names=("tail_high_corr",),
            n_seeds_per_cell=3,
        )
        runs = enumerate_runs(cfg)
        ids = [r.run_id for r in runs]
        assert ids == list(range(len(runs)))

    def test_iteration_order_is_mix_then_regime_then_seed(self):
        cfg = SweepConfig(
            mix_names=("naive_only", "plus_tail"),
            regime_names=("routine_low_corr", "tail_high_corr"),
            n_seeds_per_cell=2,
        )
        runs = enumerate_runs(cfg)
        # First 2 runs: mix=naive_only, regime=routine_low_corr, seeds 0,1
        assert (runs[0].mix_name, runs[0].regime_name, runs[0].seed) == \
               ("naive_only", "routine_low_corr", 0)
        assert (runs[1].mix_name, runs[1].regime_name, runs[1].seed) == \
               ("naive_only", "routine_low_corr", 1)
        # Next 2: same mix, next regime
        assert (runs[2].mix_name, runs[2].regime_name, runs[2].seed) == \
               ("naive_only", "tail_high_corr", 0)
        # After all regimes for naive_only: switch to plus_tail
        assert runs[4].mix_name == "plus_tail"

    def test_every_cell_has_n_seeds(self):
        cfg = SweepConfig(
            mix_names=tuple(AGENT_MIXES.keys()),
            regime_names=tuple(INFO_REGIMES.keys()),
            n_seeds_per_cell=5,
        )
        runs = enumerate_runs(cfg)
        cells: dict = {}
        for r in runs:
            cells.setdefault((r.mix_name, r.regime_name), []).append(r.seed)
        for (mix, regime), seeds in cells.items():
            assert sorted(seeds) == list(range(5))


# =============================================================================
# Single-run execute_run
# =============================================================================

class TestExecuteRun:
    def test_returns_run_records(self):
        spec = RunSpec(
            run_id=0, mix_name="naive_only", regime_name="tail_high_corr",
            seed=0, horizon=5_000, snapshot_interval=2_500,
        )
        rec = execute_run(spec)
        assert isinstance(rec, RunRecords)
        assert isinstance(rec.summary, dict)
        assert isinstance(rec.trades, list)
        assert isinstance(rec.agent_summary, list)
        assert isinstance(rec.snapshots, list)

    def test_every_record_tagged_with_run_metadata(self):
        spec = RunSpec(
            run_id=42, mix_name="plus_tail", regime_name="tail_high_corr",
            seed=7, horizon=5_000, snapshot_interval=2_500,
        )
        rec = execute_run(spec)
        for r in [rec.summary] + rec.trades + rec.agent_summary + rec.snapshots:
            assert r["run_id"] == 42
            assert r["mix_name"] == "plus_tail"
            assert r["regime_name"] == "tail_high_corr"

    def test_every_mix_runs_without_crashing(self):
        """Smoke: each defined mix produces records."""
        for mix in AGENT_MIXES:
            spec = RunSpec(
                run_id=0, mix_name=mix, regime_name="tail_high_corr",
                seed=0, horizon=5_000, snapshot_interval=2_500,
            )
            rec = execute_run(spec)
            assert len(rec.agent_summary) >= 1  # at least one agent

    def test_every_regime_runs_without_crashing(self):
        for regime in INFO_REGIMES:
            spec = RunSpec(
                run_id=0, mix_name="naive_only", regime_name=regime,
                seed=0, horizon=5_000, snapshot_interval=2_500,
            )
            rec = execute_run(spec)
            assert rec.summary["n_markets"] == 5  # all regimes have 5 markets


# =============================================================================
# Sweep execution
# =============================================================================

class TestRunSweep:
    def test_serial_sweep_returns_all_four_tables(self):
        cfg = SweepConfig(
            mix_names=("naive_only",), regime_names=("tail_high_corr",),
            n_seeds_per_cell=3, horizon=5_000, snapshot_interval=2_500,
        )
        results = run_sweep(cfg, parallel=False)
        assert set(results.keys()) == {"summary", "trades", "agent_summary", "snapshots"}
        # One summary row per run
        assert len(results["summary"]) == 3

    def test_serial_sweep_record_counts(self):
        """Total records should be sum across runs."""
        cfg = SweepConfig(
            mix_names=("noise_only",), regime_names=("tail_high_corr",),
            n_seeds_per_cell=3, horizon=5_000, snapshot_interval=2_500,
        )
        results = run_sweep(cfg, parallel=False)
        # noise_only has 3 agents → 3 agent_summary rows per run × 3 runs = 9
        assert len(results["agent_summary"]) == 9
        # snapshots: 5 markets × 3 timestamps (t=0, 2500, 5000) × 3 runs = 45
        assert len(results["snapshots"]) == 45

    def test_parallel_matches_serial(self):
        """Parallel and serial sweeps must produce IDENTICAL records."""
        cfg = SweepConfig(
            mix_names=("naive_only", "plus_tail"),
            regime_names=("routine_low_corr", "tail_high_corr"),
            n_seeds_per_cell=2, horizon=5_000, snapshot_interval=2_500,
        )
        serial = run_sweep(cfg, parallel=False)
        parallel = run_sweep(cfg, parallel=True, n_workers=2)
        # Sort by run_id to defeat ordering differences from workers
        for table in ("summary", "trades", "agent_summary", "snapshots"):
            s = sorted(serial[table], key=lambda r: (r["run_id"],
                       r.get("timestamp", -1), r.get("market_id", -1),
                       r.get("agent_id", -1)))
            p = sorted(parallel[table], key=lambda r: (r["run_id"],
                       r.get("timestamp", -1), r.get("market_id", -1),
                       r.get("agent_id", -1)))
            assert s == p, f"table {table!r} differs between serial and parallel"


# =============================================================================
# Parquet I/O
# =============================================================================

class TestParquetIO:
    def test_write_creates_files(self):
        cfg = SweepConfig(
            mix_names=("naive_only",), regime_names=("tail_high_corr",),
            n_seeds_per_cell=2, horizon=5_000, snapshot_interval=2_500,
        )
        results = run_sweep(cfg, parallel=False)
        with tempfile.TemporaryDirectory() as tmp:
            paths = write_sweep(results, tmp)
            assert set(paths.keys()) == {"summary", "trades", "agent_summary", "snapshots"}
            for p in paths.values():
                assert os.path.exists(p)
                assert p.endswith(".parquet")

    def test_round_trip_preserves_columns(self):
        cfg = SweepConfig(
            mix_names=("naive_only",), regime_names=("tail_high_corr",),
            n_seeds_per_cell=2, horizon=5_000, snapshot_interval=2_500,
        )
        results = run_sweep(cfg, parallel=False)
        with tempfile.TemporaryDirectory() as tmp:
            write_sweep(results, tmp)
            loaded = read_sweep(tmp)
            assert set(loaded.keys()) == {"summary", "trades", "agent_summary", "snapshots"}
            # Schema preserved
            assert set(loaded["summary"].columns) >= {"run_id", "mix_name",
                                                       "regime_name", "seed",
                                                       "mean_brier"}
            assert len(loaded["summary"]) == len(results["summary"])

    def test_read_missing_dir_returns_empty_frames(self):
        with tempfile.TemporaryDirectory() as tmp:
            # Empty dir — no parquet files
            loaded = read_sweep(tmp)
            for t in ("summary", "trades", "agent_summary", "snapshots"):
                assert loaded[t].empty

    def test_round_trip_join_via_run_id(self):
        """Verify run_id is a valid join key across tables."""
        cfg = SweepConfig(
            mix_names=("naive_only",), regime_names=("tail_high_corr",),
            n_seeds_per_cell=3, horizon=5_000, snapshot_interval=2_500,
        )
        results = run_sweep(cfg, parallel=False)
        with tempfile.TemporaryDirectory() as tmp:
            write_sweep(results, tmp)
            loaded = read_sweep(tmp)
            # Join summary and agent_summary on run_id; every agent row
            # should match a summary row
            joined = loaded["agent_summary"].merge(
                loaded["summary"][["run_id", "mix_name"]],
                on="run_id", suffixes=("", "_summary"),
            )
            assert len(joined) == len(loaded["agent_summary"])
            # mix_name should agree across tables for each run
            assert (joined["mix_name"] == joined["mix_name_summary"]).all()


# =============================================================================
# Statistical sanity (small subsweep is enough to verify direction)
# =============================================================================

class TestStatisticalSanity:
    def test_naive_vs_noise_naive_better(self):
        """
        Across multiple seeds in the same regime, the naive_only mix should
        produce strictly better (lower mean brier) than noise_only.
        """
        cfg = SweepConfig(
            mix_names=("noise_only", "naive_only"),
            regime_names=("routine_high_corr",),
            n_seeds_per_cell=10, horizon=10_000, snapshot_interval=5_000,
        )
        results = run_sweep(cfg, parallel=False)
        df = pd.DataFrame(results["summary"])
        by_mix = df.groupby("mix_name")["mean_brier"].mean()
        # Informed agents (any type) should beat pure noise
        assert by_mix["naive_only"] < by_mix["noise_only"], by_mix.to_dict()
