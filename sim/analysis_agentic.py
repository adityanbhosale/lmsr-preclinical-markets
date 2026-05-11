"""
Analysis pipeline for the agentic information-edge sweep.

Loads parquet artifacts produced by sim.sweep_agentic.run_sweep, computes the
four metrics from the project plan, generates headline figures (matplotlib
PNGs), and dumps a metrics.json bundle for the Task 11 writeup to cite.

The four metrics
----------------
1. **Marginal informational contribution** of each specialist class.
   For each plus_X mix, compute the paired Brier delta vs naive_only across
   seed-matched runs. Statistical significance via paired t-test.

2. **Diversity vs efficiency**: all_four (most diverse) vs naive_only
   (homogeneous). Paired comparison per regime.

3. **Tail-regime behavior**: in markets where p_star is in tail (|p* − 0.5|
   > 0.35), how close does the final market price get to truth? Per mix.
   LS-LMSR has a price ceiling of sigmoid(1) ≈ 0.731 with alpha=1.0; we plot
   this explicitly so reviewers see that hitting "the ceiling" is success.

4. **Correlation regime impact**: low_corr vs high_corr stratification.
   Quantifies how much within-cluster correlation hurts price discovery.

Usage
-----
    from sim.analysis_agentic import run_analysis
    results = run_analysis(sweep_dir="sim/results", output_dir="sim/results")

Or as a CLI:
    python -m sim.analysis_agentic

Figures are written to {output_dir}/figures/, metrics.json to {output_dir}/.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Optional

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy import stats

from sim.sweep_agentic import read_sweep


# =============================================================================
# Consistent styling (Paul Tol high-contrast, colorblind-friendly)
# =============================================================================

AGENT_COLORS: dict = {
    "noise_only":       "#BBBBBB",
    "naive_only":       "#4477AA",
    "plus_tail":        "#EE6677",
    "plus_aggregation": "#228833",
    "plus_cross":       "#CCBB44",
    "all_four":         "#AA3377",
}

MIX_ORDER: list = list(AGENT_COLORS.keys())

REGIME_ORDER: list = [
    "routine_low_corr", "routine_high_corr",
    "tail_low_corr", "tail_high_corr",
]

LSLMSR_CEILING: float = 1.0 / (1.0 + np.exp(-1.0))  # sigmoid(1) ≈ 0.7311


# =============================================================================
# Metric 1: marginal informational contribution
# =============================================================================

def compute_metric_1(summary: pd.DataFrame) -> pd.DataFrame:
    """
    Paired Brier delta vs naive_only for each specialist mix.

    Returns one row per (mix_name, regime_name) with mean delta, 95% CI on
    the mean, and paired-t-test p-value. Positive mean_delta means the mix
    beat the naive_only baseline (lower brier).
    """
    rows: list = []
    target_mixes = ["plus_tail", "plus_aggregation", "plus_cross", "all_four"]
    for regime in REGIME_ORDER:
        if regime not in summary["regime_name"].values:
            continue
        base = (
            summary[(summary["mix_name"] == "naive_only") &
                    (summary["regime_name"] == regime)]
            .set_index("seed")["mean_brier"]
        )
        for mix in target_mixes:
            target = (
                summary[(summary["mix_name"] == mix) &
                        (summary["regime_name"] == regime)]
                .set_index("seed")["mean_brier"]
            )
            joined = pd.concat([base, target], axis=1, join="inner",
                                keys=["baseline", "mix"]).dropna()
            if len(joined) < 2:
                continue
            deltas = joined["baseline"] - joined["mix"]
            mean = float(deltas.mean())
            sem = float(deltas.sem())
            ci_low, ci_high = stats.t.interval(
                0.95, df=len(deltas) - 1, loc=mean, scale=sem if sem > 0 else 1e-12
            )
            _, p_value = stats.ttest_rel(joined["baseline"], joined["mix"])
            rows.append({
                "mix_name": mix,
                "regime_name": regime,
                "mean_brier_baseline": float(joined["baseline"].mean()),
                "mean_brier_mix": float(joined["mix"].mean()),
                "mean_delta": mean,
                "ci_low": float(ci_low),
                "ci_high": float(ci_high),
                "p_value": float(p_value),
                "n_seeds": int(len(deltas)),
                "significant_05": bool(p_value < 0.05),
            })
    return pd.DataFrame(rows)


# =============================================================================
# Metric 2: diversity vs efficiency
# =============================================================================

def compute_metric_2(summary: pd.DataFrame) -> pd.DataFrame:
    """
    Compare all_four (heterogeneous, 1 of each specialist + 1 naive + noise)
    vs naive_only (homogeneous, 3 naives + noise) per regime.
    """
    rows: list = []
    for regime in REGIME_ORDER:
        if regime not in summary["regime_name"].values:
            continue
        naive = (
            summary[(summary["mix_name"] == "naive_only") &
                    (summary["regime_name"] == regime)]
            .set_index("seed")["mean_brier"]
        )
        diverse = (
            summary[(summary["mix_name"] == "all_four") &
                    (summary["regime_name"] == regime)]
            .set_index("seed")["mean_brier"]
        )
        joined = pd.concat([naive, diverse], axis=1, join="inner",
                            keys=["naive", "diverse"]).dropna()
        if len(joined) < 2:
            continue
        deltas = joined["naive"] - joined["diverse"]
        _, p_value = stats.ttest_rel(joined["naive"], joined["diverse"])
        rows.append({
            "regime_name": regime,
            "mean_brier_naive": float(joined["naive"].mean()),
            "mean_brier_all_four": float(joined["diverse"].mean()),
            "diversity_gain": float(deltas.mean()),
            "diversity_gain_pct": float(deltas.mean() / joined["naive"].mean() * 100),
            "p_value": float(p_value),
            "n_seeds": int(len(deltas)),
            "significant_05": bool(p_value < 0.05),
        })
    return pd.DataFrame(rows)


# =============================================================================
# Metric 3: tail-regime behavior
# =============================================================================

def compute_metric_3(
    snapshots: pd.DataFrame,
    tail_threshold: float = 0.35,
) -> pd.DataFrame:
    """
    For markets with |p_star − 0.5| > tail_threshold, measure how close the
    final market price gets to truth per (mix, regime).

    Returns one row per (mix_name, regime_name) with:
      - n_tail_markets: tail markets observed
      - mean_gap: |price_yes − p_star| at end of run
      - mean_gap_normalized: gap relative to "best possible" given LS-LMSR ceiling
    """
    final = snapshots.groupby("run_id")["timestamp"].transform("max")
    final_snaps = snapshots[snapshots["timestamp"] == final].copy()
    tail = final_snaps[
        (final_snaps["p_star"] > 0.5 + tail_threshold) |
        (final_snaps["p_star"] < 0.5 - tail_threshold)
    ].copy()
    if tail.empty:
        return pd.DataFrame()
    tail["gap"] = (tail["price_yes"] - tail["p_star"]).abs()
    # Best achievable price given LS-LMSR ceiling
    # For p* > 0.5: can reach at most LSLMSR_CEILING; for p* < 0.5: at most 1 - LSLMSR_CEILING
    tail["max_achievable_price"] = np.where(
        tail["p_star"] > 0.5, LSLMSR_CEILING, 1.0 - LSLMSR_CEILING
    )
    tail["min_achievable_gap"] = (tail["p_star"] - tail["max_achievable_price"]).abs()
    tail["excess_gap"] = tail["gap"] - tail["min_achievable_gap"]
    grouped = tail.groupby(["mix_name", "regime_name"]).agg(
        n_tail_markets=("gap", "size"),
        mean_p_star=("p_star", "mean"),
        mean_final_price=("price_yes", "mean"),
        mean_gap=("gap", "mean"),
        mean_excess_gap=("excess_gap", "mean"),
    ).reset_index()
    return grouped


# =============================================================================
# Metric 4: correlation regime impact
# =============================================================================

def compute_metric_4(summary: pd.DataFrame) -> pd.DataFrame:
    """
    Compare low_corr vs high_corr aggregate brier per mix.

    Returns one row per mix_name with mean brier in each correlation regime
    plus the high/low ratio. Ratio >> 1 means high-correlation regimes hurt
    that mix's price discovery more.
    """
    df = summary.copy()
    df["corr_level"] = df["regime_name"].map({
        "routine_low_corr": "low",
        "tail_low_corr": "low",
        "routine_high_corr": "high",
        "tail_high_corr": "high",
    })
    grouped = df.groupby(["mix_name", "corr_level"])["mean_brier"].mean().reset_index()
    pivot = grouped.pivot(index="mix_name", columns="corr_level", values="mean_brier")
    if "low" in pivot.columns and "high" in pivot.columns:
        pivot["high_low_ratio"] = pivot["high"] / pivot["low"]
    pivot = pivot.reset_index()
    # Reorder by canonical mix order if all mixes present
    if set(pivot["mix_name"]) >= set(MIX_ORDER):
        pivot = pivot.set_index("mix_name").loc[MIX_ORDER].reset_index()
    return pivot


# =============================================================================
# Figures
# =============================================================================

def _ensure_dir_for(path: str) -> None:
    d = os.path.dirname(path)
    if d:
        os.makedirs(d, exist_ok=True)


def figure_brier_heatmap(summary: pd.DataFrame, output_path: str) -> None:
    """Heatmap of mean Brier by (mix, regime) with cell annotations."""
    pivot = summary.pivot_table(
        index="mix_name", columns="regime_name",
        values="mean_brier", aggfunc="mean",
    )
    present_mixes = [m for m in MIX_ORDER if m in pivot.index]
    present_regimes = [r for r in REGIME_ORDER if r in pivot.columns]
    pivot = pivot.loc[present_mixes, present_regimes]

    fig, ax = plt.subplots(figsize=(8.5, 5.5))
    im = ax.imshow(pivot.values, aspect="auto", cmap="RdYlGn_r")
    ax.set_xticks(range(len(present_regimes)))
    ax.set_xticklabels(present_regimes, rotation=20, ha="right")
    ax.set_yticks(range(len(present_mixes)))
    ax.set_yticklabels(present_mixes)
    for i in range(len(present_mixes)):
        for j in range(len(present_regimes)):
            val = pivot.values[i, j]
            ax.text(j, i, f"{val:.4f}", ha="center", va="center",
                     color="black", fontsize=10)
    plt.colorbar(im, ax=ax, label="Mean Brier (lower = better)")
    ax.set_title("Population Brier by Agent Mix × Information Regime\n"
                  "(mean across seeds)")
    ax.set_xlabel("Information Regime")
    ax.set_ylabel("Agent Mix")
    plt.tight_layout()
    _ensure_dir_for(output_path)
    plt.savefig(output_path, dpi=150, bbox_inches="tight")
    plt.close()


def figure_marginal_contribution(metric_1: pd.DataFrame, output_path: str) -> None:
    """Bar chart of Brier reduction vs naive_only per (mix, regime)."""
    target_mixes = ["plus_tail", "plus_aggregation", "plus_cross", "all_four"]
    regimes = [r for r in REGIME_ORDER if r in metric_1["regime_name"].values]
    fig, axes = plt.subplots(1, len(regimes), figsize=(4 * len(regimes), 4.5),
                              sharey=True, squeeze=False)
    axes = axes[0]
    for ax, regime in zip(axes, regimes):
        regime_data = metric_1[metric_1["regime_name"] == regime]
        regime_data = regime_data.set_index("mix_name").reindex(target_mixes).dropna()
        x = np.arange(len(regime_data))
        ax.bar(x, regime_data["mean_delta"],
                color=[AGENT_COLORS[m] for m in regime_data.index],
                edgecolor="black", linewidth=0.5)
        ax.errorbar(
            x, regime_data["mean_delta"],
            yerr=[regime_data["mean_delta"] - regime_data["ci_low"],
                  regime_data["ci_high"] - regime_data["mean_delta"]],
            fmt="none", color="black", capsize=4, linewidth=1,
        )
        ax.axhline(0, color="black", linewidth=0.6)
        ax.set_xticks(x)
        ax.set_xticklabels(regime_data.index, rotation=30, ha="right", fontsize=8)
        ax.set_title(regime, fontsize=10)
        ax.grid(True, alpha=0.3, axis="y")
    axes[0].set_ylabel("Brier reduction vs naive_only\n(positive = mix beats baseline)")
    fig.suptitle(
        "Metric 1: Marginal Informational Contribution by Mix × Regime\n"
        "(paired comparison, error bars = 95% CI)",
        fontsize=11,
    )
    plt.tight_layout()
    _ensure_dir_for(output_path)
    plt.savefig(output_path, dpi=150, bbox_inches="tight")
    plt.close()


def figure_convergence_trajectories(snapshots: pd.DataFrame, output_path: str) -> None:
    """Mean Brier over simulation time, faceted by regime, lines = mixes."""
    grouped = (
        snapshots.groupby(["mix_name", "regime_name", "timestamp"])["brier"]
        .mean().reset_index()
    )
    regimes = [r for r in REGIME_ORDER if r in grouped["regime_name"].values]
    nrows, ncols = (2, 2) if len(regimes) == 4 else (1, len(regimes))
    fig, axes = plt.subplots(nrows, ncols, figsize=(11, 7),
                              sharex=True, sharey=True, squeeze=False)
    for ax, regime in zip(axes.flat, regimes):
        for mix in MIX_ORDER:
            data = grouped[(grouped["mix_name"] == mix) &
                            (grouped["regime_name"] == regime)]
            if data.empty:
                continue
            ax.plot(data["timestamp"], data["brier"],
                     label=mix, color=AGENT_COLORS[mix], linewidth=1.6)
        ax.set_title(regime, fontsize=10)
        ax.grid(True, alpha=0.3)
        ax.set_xlabel("Timestamp")
        ax.set_ylabel("Mean Brier")
    # Single legend in the first axes
    axes.flat[0].legend(loc="upper right", fontsize=8, framealpha=0.9)
    fig.suptitle(
        "Brier Convergence Trajectories by Mix × Regime\n"
        "(mean across markets and seeds)",
        fontsize=11,
    )
    plt.tight_layout()
    _ensure_dir_for(output_path)
    plt.savefig(output_path, dpi=150, bbox_inches="tight")
    plt.close()


def figure_tail_regime_scatter(
    snapshots: pd.DataFrame,
    output_path: str,
    tail_threshold: float = 0.35,
) -> None:
    """Final price vs p_star for tail markets, faceted by mix."""
    final = snapshots.groupby("run_id")["timestamp"].transform("max")
    final_snaps = snapshots[snapshots["timestamp"] == final]
    tail = final_snaps[
        (final_snaps["p_star"] > 0.5 + tail_threshold) |
        (final_snaps["p_star"] < 0.5 - tail_threshold)
    ]
    mixes_to_show = [m for m in
                     ["noise_only", "naive_only", "plus_tail", "all_four"]
                     if m in tail["mix_name"].values]
    if not mixes_to_show:
        return
    fig, axes = plt.subplots(1, len(mixes_to_show),
                              figsize=(3.5 * len(mixes_to_show), 4),
                              sharex=True, sharey=True, squeeze=False)
    axes = axes[0]
    for ax, mix in zip(axes, mixes_to_show):
        data = tail[tail["mix_name"] == mix]
        ax.scatter(data["p_star"], data["price_yes"],
                    alpha=0.25, s=10, color=AGENT_COLORS[mix])
        ax.plot([0, 1], [0, 1], "k--", alpha=0.5, linewidth=0.8, label="y=x")
        ax.axhline(LSLMSR_CEILING, color="red", linestyle=":",
                    linewidth=0.8, label=f"LS-LMSR ceiling ({LSLMSR_CEILING:.3f})")
        ax.axhline(1.0 - LSLMSR_CEILING, color="red", linestyle=":", linewidth=0.8)
        ax.set_title(mix, fontsize=10)
        ax.set_xlim(-0.05, 1.05)
        ax.set_ylim(-0.05, 1.05)
        ax.grid(True, alpha=0.3)
        ax.set_xlabel("p* (true probability)")
        if ax is axes[0]:
            ax.legend(loc="upper left", fontsize=7)
            ax.set_ylabel("Final market price")
    fig.suptitle(
        f"Metric 3: Final Price vs Truth in Tail Markets "
        f"(|p* − 0.5| > {tail_threshold})",
        fontsize=11,
    )
    plt.tight_layout()
    _ensure_dir_for(output_path)
    plt.savefig(output_path, dpi=150, bbox_inches="tight")
    plt.close()


def figure_correlation_regime(summary: pd.DataFrame, output_path: str) -> None:
    """Grouped bar chart: low_corr vs high_corr mean Brier per mix."""
    df = summary.copy()
    df["corr_level"] = df["regime_name"].map({
        "routine_low_corr": "low", "tail_low_corr": "low",
        "routine_high_corr": "high", "tail_high_corr": "high",
    })
    grouped = df.groupby(["mix_name", "corr_level"])["mean_brier"].mean().reset_index()
    pivot = grouped.pivot(index="mix_name", columns="corr_level", values="mean_brier")
    present_mixes = [m for m in MIX_ORDER if m in pivot.index]
    pivot = pivot.loc[present_mixes]
    x = np.arange(len(present_mixes))
    width = 0.35
    fig, ax = plt.subplots(figsize=(9.5, 5))
    ax.bar(x - width / 2, pivot["low"], width, label="low correlation",
            color=[AGENT_COLORS[m] for m in present_mixes], alpha=0.55,
            edgecolor="black", linewidth=0.5)
    ax.bar(x + width / 2, pivot["high"], width, label="high correlation",
            color=[AGENT_COLORS[m] for m in present_mixes],
            edgecolor="black", linewidth=0.5)
    ax.set_xticks(x)
    ax.set_xticklabels(present_mixes, rotation=30, ha="right")
    ax.set_ylabel("Mean Brier (averaged over tail/routine)")
    ax.set_title("Metric 4: Correlation Regime Impact by Mix\n"
                  "Higher within-cluster correlation → harder price discovery")
    ax.legend()
    ax.grid(True, alpha=0.3, axis="y")
    plt.tight_layout()
    _ensure_dir_for(output_path)
    plt.savefig(output_path, dpi=150, bbox_inches="tight")
    plt.close()


# =============================================================================
# Orchestration
# =============================================================================

@dataclass
class AnalysisResults:
    metric_1: pd.DataFrame
    metric_2: pd.DataFrame
    metric_3: pd.DataFrame
    metric_4: pd.DataFrame
    figures_dir: str
    metrics_json_path: str


def run_analysis(
    sweep_dir: str = "sim/results",
    output_dir: str = "sim/results",
) -> AnalysisResults:
    """Top-level orchestrator: load, compute, plot, dump."""
    data = read_sweep(sweep_dir)
    summary = data["summary"]
    snapshots = data["snapshots"]
    if summary.empty:
        raise FileNotFoundError(
            f"No summary.parquet found in {sweep_dir!r}. "
            f"Run sim.sweep_agentic.run_sweep first."
        )

    m1 = compute_metric_1(summary)
    m2 = compute_metric_2(summary)
    m3 = compute_metric_3(snapshots) if not snapshots.empty else pd.DataFrame()
    m4 = compute_metric_4(summary)

    figures_dir = os.path.join(output_dir, "figures")
    os.makedirs(figures_dir, exist_ok=True)
    figure_brier_heatmap(
        summary, os.path.join(figures_dir, "01_brier_heatmap.png")
    )
    figure_marginal_contribution(
        m1, os.path.join(figures_dir, "02_metric_1_marginal_contribution.png")
    )
    if not snapshots.empty:
        figure_convergence_trajectories(
            snapshots, os.path.join(figures_dir, "03_convergence_trajectories.png")
        )
        figure_tail_regime_scatter(
            snapshots, os.path.join(figures_dir, "04_metric_3_tail_regime.png")
        )
    figure_correlation_regime(
        summary, os.path.join(figures_dir, "05_metric_4_correlation.png")
    )

    # JSON bundle for the writeup to cite
    metrics_dict = {
        "metric_1_marginal_contribution": m1.to_dict(orient="records"),
        "metric_2_diversity": m2.to_dict(orient="records"),
        "metric_3_tail_regime": m3.to_dict(orient="records"),
        "metric_4_correlation": m4.to_dict(orient="records"),
        "config": {
            "tail_threshold": 0.35,
            "lslmsr_ceiling": float(LSLMSR_CEILING),
            "mix_order": MIX_ORDER,
            "regime_order": REGIME_ORDER,
        },
    }
    metrics_json_path = os.path.join(output_dir, "metrics.json")
    with open(metrics_json_path, "w") as f:
        json.dump(metrics_dict, f, indent=2)

    return AnalysisResults(
        metric_1=m1, metric_2=m2, metric_3=m3, metric_4=m4,
        figures_dir=figures_dir,
        metrics_json_path=metrics_json_path,
    )


if __name__ == "__main__":
    results = run_analysis()
    print("Analysis complete.")
    print(f"  Figures: {results.figures_dir}")
    print(f"  Metrics JSON: {results.metrics_json_path}")
    print("\n=== Metric 1: Marginal Contribution ===")
    print(results.metric_1.to_string(index=False))
    print("\n=== Metric 2: Diversity ===")
    print(results.metric_2.to_string(index=False))
    print("\n=== Metric 3: Tail Regime ===")
    if results.metric_3.empty:
        print("  (no tail markets at threshold)")
    else:
        print(results.metric_3.to_string(index=False))
    print("\n=== Metric 4: Correlation ===")
    print(results.metric_4.to_string(index=False))
