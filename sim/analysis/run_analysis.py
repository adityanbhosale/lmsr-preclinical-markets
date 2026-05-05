"""End-to-end H1+H2 analysis. Runs from sim/ directory."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns

sns.set_style("whitegrid")
plt.rcParams["figure.dpi"] = 110

# --- load data ---
h1 = pd.read_parquet("sim/results/h1_baseline.parquet")
h2 = pd.read_parquet("sim/results/h2_baseline.parquet")
print(f"H1: {len(h1)} runs")
print(f"H2: {len(h2)} runs")
print()

# --- H2 Cell 2: by mix ---
print("=" * 60)
print("H2 — convergence by agent mix:")
mix_summary = (
    h2.groupby(["mix_cred", "mix_noise", "mix_mom"])
    .agg(
        convergence_rate=("converged", "mean"),
        median_conv_tick=("convergence_tick", "median"),
        mean_post_error=("mean_post_convergence_error", "mean"),
        n_runs=("converged", "count"),
    )
    .round(3)
)
print(mix_summary)
print()

# --- H2 Cell 3: speed in dominant regime ---
print("=" * 60)
fast_mix = h2[(h2["mix_cred"] >= 0.4) & (h2["converged"])]
print(f"Convergence ticks (cred ≥ 40%, converged only): {len(fast_mix)} runs")
print(fast_mix["convergence_tick"].describe().round(0))
print()

# --- H2 Cell 4: heatmap ---
fig, axes = plt.subplots(1, 3, figsize=(18, 5))
for ax, true_p in zip(axes, [0.2, 0.5, 0.8]):
    sub = h2[h2["true_probability_grid"] == true_p]
    pivot = sub.pivot_table(
        values="converged", index="mix_cred",
        columns="starting_prior", aggfunc="mean",
    )
    sns.heatmap(pivot, annot=True, fmt=".2f", cmap="RdYlGn",
                vmin=0, vmax=1, ax=ax, cbar=(true_p == 0.8))
    ax.set_title(f"true_prob = {true_p}")
    ax.set_xlabel("starting prior")
    ax.set_ylabel("credentialed share" if true_p == 0.2 else "")
fig.suptitle("H2: convergence rate, faceted by true probability",
             fontsize=13, y=1.02)
plt.tight_layout()
plt.savefig("sim/notebooks/h2_heatmap_mix_prior.png", dpi=120, bbox_inches="tight")
plt.close()
print("saved h2_heatmap_mix_prior.png")

# --- H2 Cell 5: trajectory ---
from sim.sweep import market_with_starting_prior, build_agents, _run_inline
from sim.market import ABMMConfig

rng = np.random.default_rng(seed=7)
agents = build_agents(
    mix=(0.4, 0.4, 0.2), total=50, true_prob=0.65, rng=rng,
    cred_params={"sigma": 0.10, "aggressiveness": 0.1, "min_edge": 0.01},
    noise_params={"mean_size": 3.0, "size_std": 1.0},
    mom_params={"lookback": 15, "threshold": 0.02, "aggressiveness": 0.06},
)
market = market_with_starting_prior(
    {"alpha": 0.05, "q_abmm_yes": 500.0, "q_abmm_no": 500.0},
    ABMMConfig(enabled=False), starting_prior=0.30,
)
log = _run_inline(market, agents, n_trades=1500, rng=rng, true_probability=0.65)

fig, ax = plt.subplots(figsize=(10, 4))
ax.plot(log["tick"], log["price_yes"], linewidth=1, color="steelblue")
ax.axhline(0.65, color="red", linestyle="--", alpha=0.6, label="true_prob = 0.65")
ax.fill_between(log["tick"], 0.62, 0.68, alpha=0.15, color="red", label="ε-band")
ax.set_xlabel("tick")
ax.set_ylabel("price (YES)")
ax.set_ylim(0, 1)
ax.set_title("H2 trajectory: 40/40/20 mix, prior 0.30 → true 0.65")
ax.legend(loc="lower right")
plt.tight_layout()
plt.savefig("sim/notebooks/h2_trajectory_example.png", dpi=120)
plt.close()
print("saved h2_trajectory_example.png")
print()

# --- H1 Cell 6: sanity ---
print("=" * 60)
print(f"H1 sanity:")
print(f"  Total runs: {len(h1)}")
print(f"  Retreat engaged on: {h1['retreat_engaged'].mean()*100:.1f}% of runs")
print(f"  Recovery fraction stats:")
print(h1["recovery_fraction"].describe().round(3))
print(f"  Sample sizes by decay shape:")
print(h1["decay_shape"].value_counts())
print()

# --- H1 Cell 7: pivot table ---
print("=" * 60)
print("Median recovery fraction by decay shape × attack magnitude:")
print(h1.pivot_table(
    values="recovery_fraction",
    index="decay_shape", columns="attack_magnitude_pct",
    aggfunc="median",
).round(3))
print()

# --- H1 Cell 8: heatmap ---
fig, axes = plt.subplots(1, 3, figsize=(18, 5), sharey=True)
for ax, shape in zip(axes, ["exponential", "polynomial", "step"]):
    sub = h1[h1["decay_shape"] == shape]
    pivot = sub.pivot_table(
        values="recovery_fraction",
        index="abmm_tau", columns="attack_magnitude_pct",
        aggfunc="median",
    )
    sns.heatmap(pivot, annot=True, fmt=".2f", cmap="RdYlGn",
                vmin=-0.5, vmax=1.5, center=1.0, ax=ax,
                cbar=(shape == "step"))
    ax.set_title(f"{shape} decay")
    ax.set_xlabel("attack magnitude (% of seeded liquidity)")
    ax.set_ylabel("retreat τ" if shape == "exponential" else "")
fig.suptitle("H1: median recovery fraction across (τ × attack magnitude × decay shape)",
             fontsize=13, y=1.02)
plt.tight_layout()
plt.savefig("sim/notebooks/h1_recovery_by_shape.png", dpi=120, bbox_inches="tight")
plt.close()
print("saved h1_recovery_by_shape.png")
print()

# --- H1 Cell 9: direction asymmetry ---
print("=" * 60)
print("Recovery by attack direction:")
print(h1.groupby("attack_direction")["recovery_fraction"].describe().round(3))
print()
print("Direction × magnitude:")
print(h1.pivot_table(
    values="recovery_fraction",
    index="attack_direction", columns="attack_magnitude_pct",
    aggfunc="median",
).round(3))
print()

# --- H1 Cell 10: trajectory ---
from sim.agents import AdversarialTrader

rng = np.random.default_rng(seed=1)
agents = build_agents(
    mix=(0.6, 0.2, 0.2), total=50, true_prob=0.65, rng=rng,
    cred_params={"sigma": 0.10, "aggressiveness": 0.1, "min_edge": 0.01},
    noise_params={"mean_size": 3.0, "size_std": 1.0},
    mom_params={"lookback": 15, "threshold": 0.02, "aggressiveness": 0.06},
)
agents.append(AdversarialTrader(
    agent_id="adv_0", rng=rng,
    attack_tick=300, attack_shares=0.25 * 1000.0, attack_is_yes=True,
))
abmm = ABMMConfig(enabled=True, tau=1.5, threshold=100.0, decay_shape="exponential")
market = market_with_starting_prior(
    {"alpha": 0.05, "q_abmm_yes": 500.0, "q_abmm_no": 500.0},
    abmm, starting_prior=0.50,
)
log = _run_inline(market, agents, n_trades=1000, rng=rng, true_probability=0.65)

fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(10, 6), sharex=True,
                                gridspec_kw={"height_ratios": [2, 1]})
ax1.plot(log["tick"], log["price_yes"], linewidth=1, color="steelblue")
ax1.axvline(300, color="orange", linestyle=":", linewidth=2, label="attack tick (300)")
ax1.axhline(0.65, color="red", linestyle="--", alpha=0.6, label="true_prob = 0.65")
ax1.set_ylabel("price (YES)")
ax1.set_ylim(0, 1)
ax1.legend(loc="lower right")
ax1.set_title("H1 trajectory: 25%-liquidity YES-attack at tick 300, exponential τ=1.5")

ax2.plot(log["tick"], log["retreat_factor"], linewidth=1, color="purple")
ax2.axvline(300, color="orange", linestyle=":", linewidth=2)
ax2.set_xlabel("tick")
ax2.set_ylabel("retreat factor")
ax2.set_ylim(-0.05, 1.1)
plt.tight_layout()
plt.savefig("sim/notebooks/h1_trajectory_example.png", dpi=120)
plt.close()
print("saved h1_trajectory_example.png")
print()
print("=" * 60)
print("done.")