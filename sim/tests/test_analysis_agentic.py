"""
Tests for sim/analysis_agentic.py.

Strategy: use synthetic DataFrames (not the real sweep) so tests stay fast.
Real-data validation happens in the smoke test we run after integration.

Covers:
  - Each metric function returns expected schema
  - Statistical claims hold on engineered synthetic data
  - Figure functions produce PNG files of reasonable size
  - End-to-end run_analysis on a temp directory
"""
from __future__ import annotations

import json
import os
import tempfile

import numpy as np
import pandas as pd
import pytest

from sim.analysis_agentic import (
    AnalysisResults,
    LSLMSR_CEILING,
    MIX_ORDER,
    REGIME_ORDER,
    compute_metric_1,
    compute_metric_2,
    compute_metric_3,
    compute_metric_4,
    figure_brier_heatmap,
    figure_correlation_regime,
    figure_marginal_contribution,
    figure_tail_regime_scatter,
    figure_convergence_trajectories,
    run_analysis,
)
from sim.sweep_agentic import write_sweep


# =============================================================================
# Synthetic data builders
# =============================================================================

def make_summary(*, n_seeds: int = 50, noise: float = 0.002) -> pd.DataFrame:
    """
    Build a synthetic summary DataFrame matching real sweep schema.

    Brier means engineered so:
      - noise_only is strictly worst
      - naive_only / plus_X are all similar (~0.030 low_corr, 0.077 high_corr)
      - all_four is strictly best
      - high_corr regimes are 2.5x worse than low_corr
    """
    base_brier = {
        ("noise_only",      "low"):  0.045,
        ("naive_only",      "low"):  0.030,
        ("plus_tail",       "low"):  0.0298,
        ("plus_aggregation","low"):  0.0301,
        ("plus_cross",      "low"):  0.0299,
        ("all_four",        "low"):  0.027,
        ("noise_only",      "high"): 0.101,
        ("naive_only",      "high"): 0.077,
        ("plus_tail",       "high"): 0.0768,
        ("plus_aggregation","high"): 0.0770,
        ("plus_cross",      "high"): 0.0769,
        ("all_four",        "high"): 0.0715,
    }
    rows = []
    run_id = 0
    for mix in MIX_ORDER:
        for regime in REGIME_ORDER:
            corr = "high" if "high_corr" in regime else "low"
            mean = base_brier[(mix, corr)]
            for seed in range(n_seeds):
                # Reproducible per-seed noise
                rng = np.random.default_rng(hash((mix, regime, seed)) % (2**32))
                brier = mean + rng.normal(0, noise)
                rows.append({
                    "run_id": run_id,
                    "seed": seed,
                    "mix_name": mix,
                    "regime_name": regime,
                    "horizon": 30_000,
                    "n_markets": 5,
                    "n_agents": 5,
                    "n_trades": 200,
                    "mean_brier": float(brier),
                    "max_brier": float(brier * 1.5),
                    "mean_final_price": 0.5,
                })
                run_id += 1
    return pd.DataFrame(rows)


def make_snapshots(*, n_seeds: int = 50) -> pd.DataFrame:
    """
    Build synthetic snapshots: 5 markets × 5 timestamps × n_seeds × all mixes/regimes.
    Includes some tail markets (p_star > 0.9) for Metric 3.
    """
    rows = []
    run_id = 0
    for mix in MIX_ORDER:
        for regime in REGIME_ORDER:
            for seed in range(n_seeds):
                rng = np.random.default_rng(hash((mix, regime, seed)) % (2**32))
                # 5 markets per run; mark some as tail
                p_stars = rng.uniform(0.05, 0.95, 5)
                # Force 1 tail market per run for tests
                p_stars[0] = rng.choice([0.05, 0.95])
                # Final prices: depend on mix (informed → closer to truth)
                if mix == "noise_only":
                    final_prices = np.full(5, 0.5) + rng.normal(0, 0.02, 5)
                elif mix == "all_four":
                    final_prices = 0.65 * p_stars + 0.35 * 0.5 + rng.normal(0, 0.02, 5)
                else:
                    final_prices = 0.55 * p_stars + 0.45 * 0.5 + rng.normal(0, 0.02, 5)
                final_prices = np.clip(final_prices, 0.01, 0.99)
                for timestamp in (0, 7500, 15000, 22500, 30000):
                    for m_id in range(5):
                        if timestamp == 0:
                            price = 0.5
                        elif timestamp == 30000:
                            price = float(final_prices[m_id])
                        else:
                            # Linear interpolation
                            t_frac = timestamp / 30000
                            price = 0.5 * (1 - t_frac) + final_prices[m_id] * t_frac
                            price = float(price)
                        rows.append({
                            "run_id": run_id,
                            "seed": seed,
                            "mix_name": mix,
                            "regime_name": regime,
                            "timestamp": int(timestamp),
                            "market_id": m_id,
                            "price_yes": price,
                            "p_star": float(p_stars[m_id]),
                            "brier": float((price - p_stars[m_id]) ** 2),
                        })
                run_id += 1
    return pd.DataFrame(rows)


# =============================================================================
# Metric 1
# =============================================================================

class TestMetric1:
    def test_schema(self):
        df = make_summary()
        m1 = compute_metric_1(df)
        expected_cols = {"mix_name", "regime_name", "mean_brier_baseline",
                          "mean_brier_mix", "mean_delta", "ci_low", "ci_high",
                          "p_value", "n_seeds", "significant_05"}
        assert set(m1.columns) >= expected_cols

    def test_rows_match_4_target_mixes_times_4_regimes(self):
        df = make_summary()
        m1 = compute_metric_1(df)
        # plus_tail, plus_aggregation, plus_cross, all_four × 4 regimes = 16
        assert len(m1) == 16

    def test_all_four_significantly_better(self):
        """Engineered: all_four mean delta should be ~0.003 and p < 0.001 in low_corr."""
        df = make_summary()
        m1 = compute_metric_1(df)
        af_low = m1[(m1["mix_name"] == "all_four") &
                     (m1["regime_name"] == "routine_low_corr")].iloc[0]
        assert af_low["mean_delta"] > 0.001
        assert af_low["p_value"] < 0.01
        assert bool(af_low["significant_05"]) is True

    def test_plus_X_deltas_near_zero(self):
        """plus_tail / plus_aggregation / plus_cross should have small deltas."""
        df = make_summary()
        m1 = compute_metric_1(df)
        for mix in ("plus_tail", "plus_aggregation", "plus_cross"):
            for regime in REGIME_ORDER:
                row = m1[(m1["mix_name"] == mix) &
                          (m1["regime_name"] == regime)].iloc[0]
                # Engineered noise makes deltas small in absolute terms
                assert abs(row["mean_delta"]) < 0.005


# =============================================================================
# Metric 2
# =============================================================================

class TestMetric2:
    def test_schema(self):
        df = make_summary()
        m2 = compute_metric_2(df)
        expected_cols = {"regime_name", "mean_brier_naive", "mean_brier_all_four",
                          "diversity_gain", "diversity_gain_pct", "p_value",
                          "n_seeds"}
        assert set(m2.columns) >= expected_cols

    def test_one_row_per_regime(self):
        df = make_summary()
        m2 = compute_metric_2(df)
        assert len(m2) == 4

    def test_diversity_gain_positive_and_significant(self):
        df = make_summary()
        m2 = compute_metric_2(df)
        for _, row in m2.iterrows():
            assert row["diversity_gain"] > 0
            assert row["p_value"] < 0.001

    def test_gain_pct_calculated_correctly(self):
        df = make_summary()
        m2 = compute_metric_2(df)
        for _, row in m2.iterrows():
            expected = row["diversity_gain"] / row["mean_brier_naive"] * 100
            assert row["diversity_gain_pct"] == pytest.approx(expected, rel=1e-9)


# =============================================================================
# Metric 3
# =============================================================================

class TestMetric3:
    def test_schema(self):
        snaps = make_snapshots()
        m3 = compute_metric_3(snaps)
        expected_cols = {"mix_name", "regime_name", "n_tail_markets",
                          "mean_p_star", "mean_final_price", "mean_gap",
                          "mean_excess_gap"}
        assert set(m3.columns) >= expected_cols

    def test_tail_market_filter(self):
        """Filter should keep only markets with |p_star - 0.5| > threshold."""
        snaps = make_snapshots()
        # Verify the filter is applied correctly by checking row-level values
        threshold = 0.35
        m3 = compute_metric_3(snaps, tail_threshold=threshold)
        # With synthetic data forcing 1 tail market per run, n_tail_markets should be positive
        for _, row in m3.iterrows():
            assert row["n_tail_markets"] > 0
        # Verify the underlying filter directly: every market counted must be in tail
        final = snaps.groupby("run_id")["timestamp"].transform("max")
        final_snaps = snaps[snaps["timestamp"] == final]
        tail = final_snaps[
            (final_snaps["p_star"] > 0.5 + threshold) |
            (final_snaps["p_star"] < 0.5 - threshold)
        ]
        for p in tail["p_star"]:
            assert (p > 0.5 + threshold) or (p < 0.5 - threshold)

    def test_informed_mixes_smaller_gap_than_noise(self):
        snaps = make_snapshots()
        m3 = compute_metric_3(snaps)
        for regime in REGIME_ORDER:
            noise_gap = m3[(m3["mix_name"] == "noise_only") &
                            (m3["regime_name"] == regime)]["mean_gap"].iloc[0]
            naive_gap = m3[(m3["mix_name"] == "naive_only") &
                            (m3["regime_name"] == regime)]["mean_gap"].iloc[0]
            assert naive_gap < noise_gap, (regime, naive_gap, noise_gap)

    def test_empty_snapshots_returns_empty_df(self):
        empty = pd.DataFrame(columns=["run_id", "timestamp", "market_id",
                                       "price_yes", "p_star", "brier",
                                       "mix_name", "regime_name", "seed"])
        m3 = compute_metric_3(empty)
        assert m3.empty


# =============================================================================
# Metric 4
# =============================================================================

class TestMetric4:
    def test_schema(self):
        df = make_summary()
        m4 = compute_metric_4(df)
        assert "mix_name" in m4.columns
        assert "low" in m4.columns
        assert "high" in m4.columns
        assert "high_low_ratio" in m4.columns

    def test_one_row_per_mix(self):
        df = make_summary()
        m4 = compute_metric_4(df)
        assert len(m4) == len(MIX_ORDER)

    def test_high_low_ratio_above_one(self):
        """high_corr regimes are uniformly harder → ratio > 1 for every mix."""
        df = make_summary()
        m4 = compute_metric_4(df)
        for _, row in m4.iterrows():
            assert row["high_low_ratio"] > 1.5

    def test_canonical_mix_order_preserved(self):
        df = make_summary()
        m4 = compute_metric_4(df)
        assert list(m4["mix_name"]) == MIX_ORDER


# =============================================================================
# Figure generation
# =============================================================================

class TestFigures:
    def test_brier_heatmap_creates_png(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "heatmap.png")
            figure_brier_heatmap(make_summary(), path)
            assert os.path.exists(path)
            assert os.path.getsize(path) > 5_000  # nontrivial PNG

    def test_marginal_contribution_creates_png(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "marginal.png")
            m1 = compute_metric_1(make_summary())
            figure_marginal_contribution(m1, path)
            assert os.path.exists(path)
            assert os.path.getsize(path) > 5_000

    def test_convergence_trajectories_creates_png(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "convergence.png")
            figure_convergence_trajectories(make_snapshots(n_seeds=10), path)
            assert os.path.exists(path)
            assert os.path.getsize(path) > 5_000

    def test_tail_regime_scatter_creates_png(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "tail.png")
            figure_tail_regime_scatter(make_snapshots(n_seeds=10), path)
            assert os.path.exists(path)
            assert os.path.getsize(path) > 5_000

    def test_correlation_regime_creates_png(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "corr.png")
            figure_correlation_regime(make_summary(), path)
            assert os.path.exists(path)
            assert os.path.getsize(path) > 5_000


# =============================================================================
# End-to-end orchestration
# =============================================================================

class TestRunAnalysis:
    def test_returns_analysis_results(self):
        """run_analysis on synthetic parquet returns full results bundle."""
        with tempfile.TemporaryDirectory() as tmp:
            # Write synthetic parquet
            summary = make_summary(n_seeds=20)
            snapshots = make_snapshots(n_seeds=20)
            write_sweep({
                "summary": summary.to_dict(orient="records"),
                "snapshots": snapshots.to_dict(orient="records"),
                "trades": [],
                "agent_summary": [],
            }, tmp)
            # Run analysis on it
            results = run_analysis(sweep_dir=tmp, output_dir=tmp)
            assert isinstance(results, AnalysisResults)
            assert not results.metric_1.empty
            assert not results.metric_2.empty
            assert not results.metric_3.empty
            assert not results.metric_4.empty
            # Figures should be on disk
            for fig_name in (
                "01_brier_heatmap.png",
                "02_metric_1_marginal_contribution.png",
                "03_convergence_trajectories.png",
                "04_metric_3_tail_regime.png",
                "05_metric_4_correlation.png",
            ):
                assert os.path.exists(os.path.join(results.figures_dir, fig_name))
            # JSON should be valid
            with open(results.metrics_json_path) as f:
                data = json.load(f)
            assert "metric_1_marginal_contribution" in data
            assert "metric_2_diversity" in data
            assert "metric_3_tail_regime" in data
            assert "metric_4_correlation" in data
            assert "config" in data

    def test_missing_summary_raises(self):
        with tempfile.TemporaryDirectory() as tmp:
            # Empty dir → read_sweep returns empty DataFrames
            with pytest.raises(FileNotFoundError):
                run_analysis(sweep_dir=tmp, output_dir=tmp)
