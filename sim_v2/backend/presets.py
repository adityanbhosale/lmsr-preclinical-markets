"""
sim_v2.backend.presets — Named SimRequest configurations.

Each preset is a story. The user can pick a preset to jump into a config
that reproduces a v1 finding or sets up one of the v1-recommended follow-on
experiments. Knobs are still mutable from that starting point.
"""

from __future__ import annotations

from .models import (
    SimRequest,
    AgentMixConfig,
    TradeSizingConfig,
    InformationConfig,
    MarketConfig,
    AgentConfig,
    StreamConfig,
)


PRESETS: dict[str, SimRequest] = {
    # ─── v1 finding reproductions ──────────────────────────────────────────
    "v1_naive_baseline": SimRequest(
        agent_mix=AgentMixConfig(
            n_naive=4, n_aggregation=0, n_tail=0, n_cross=0, n_noise=2
        ),
        information=InformationConfig(
            regime="routine", signal_rate=0.02, within_cluster_correlation=0.6
        ),
        market=MarketConfig(alpha=1.0),
        agent=AgentConfig(capital_per_agent=100.0, disagreement_threshold=0.03),
        trade_sizing=TradeSizingConfig(mode="fixed", base_size=1.0),
        stream=StreamConfig(duration_seconds=420, target_fps=8, n_ensemble_seeds=16),
        horizon_ticks=10_000,
        base_seed=42,
    ),
    "v1_all_four_diversity": SimRequest(
        agent_mix=AgentMixConfig(
            n_naive=1, n_aggregation=1, n_tail=1, n_cross=1, n_noise=2
        ),
        information=InformationConfig(
            regime="routine", signal_rate=0.02, within_cluster_correlation=0.6
        ),
        market=MarketConfig(alpha=1.0),
        agent=AgentConfig(capital_per_agent=100.0, disagreement_threshold=0.03),
        trade_sizing=TradeSizingConfig(mode="fixed", base_size=1.0),
        stream=StreamConfig(duration_seconds=420, target_fps=8, n_ensemble_seeds=16),
        horizon_ticks=10_000,
        base_seed=42,
    ),
    "v1_high_correlation_penalty": SimRequest(
        # Finding 4 reproduction: same all_four mix, but high within-cluster corr
        agent_mix=AgentMixConfig(
            n_naive=1, n_aggregation=1, n_tail=1, n_cross=1, n_noise=2
        ),
        information=InformationConfig(
            regime="routine", signal_rate=0.02, within_cluster_correlation=0.85
        ),
        agent=AgentConfig(capital_per_agent=100.0, disagreement_threshold=0.03),
    ),
    "v1_tail_regime": SimRequest(
        # Finding 3 reproduction: tail signals, see the capital constraint bite
        agent_mix=AgentMixConfig(
            n_naive=1, n_aggregation=1, n_tail=1, n_cross=1, n_noise=2
        ),
        information=InformationConfig(
            regime="tail", signal_rate=0.005, within_cluster_correlation=0.6
        ),
        agent=AgentConfig(capital_per_agent=100.0, disagreement_threshold=0.03),
    ),
    # ─── v1-recommended next experiments ───────────────────────────────────
    "exp1_capital_rich": SimRequest(
        # Experiment #1: bump capital to $1000, see whether tail markets close
        agent_mix=AgentMixConfig(
            n_naive=1, n_aggregation=1, n_tail=1, n_cross=1, n_noise=2
        ),
        information=InformationConfig(
            regime="tail", signal_rate=0.005, within_cluster_correlation=0.6
        ),
        agent=AgentConfig(capital_per_agent=1000.0, disagreement_threshold=0.03),
    ),
    "exp2_confidence_sizing": SimRequest(
        # Experiment #2: confidence-weighted trade sizing — the headline test
        # for whether specialist agents start contributing visibly
        agent_mix=AgentMixConfig(
            n_naive=2, n_aggregation=0, n_tail=1, n_cross=0, n_noise=2
        ),
        information=InformationConfig(
            regime="routine", signal_rate=0.02, within_cluster_correlation=0.6
        ),
        trade_sizing=TradeSizingConfig(
            mode="confidence_weighted",
            base_size=1.0,
            confidence_floor=0.25,
            confidence_ceiling=4.0,
        ),
        agent=AgentConfig(capital_per_agent=100.0, disagreement_threshold=0.03),
    ),
    "exp3_loose_threshold": SimRequest(
        # Experiment #3: lower disagreement threshold, sustained convergence
        agent_mix=AgentMixConfig(
            n_naive=1, n_aggregation=1, n_tail=1, n_cross=1, n_noise=2
        ),
        information=InformationConfig(
            regime="tail", signal_rate=0.005, within_cluster_correlation=0.6
        ),
        agent=AgentConfig(capital_per_agent=100.0, disagreement_threshold=0.01),
    ),
    # ─── Comparison helpers ────────────────────────────────────────────────
    "high_capital_diversity_low_corr": SimRequest(
        # The "best-case protocol design" config — what you'd recommend if
        # you could pick everything from v1's findings
        agent_mix=AgentMixConfig(
            n_naive=1, n_aggregation=1, n_tail=1, n_cross=1, n_noise=3
        ),
        information=InformationConfig(
            regime="mixed", signal_rate=0.02, within_cluster_correlation=0.3
        ),
        agent=AgentConfig(capital_per_agent=500.0, disagreement_threshold=0.02),
        trade_sizing=TradeSizingConfig(mode="confidence_weighted"),
    ),
}


PRESET_DESCRIPTIONS: dict[str, str] = {
    "v1_naive_baseline": "v1 Finding 1 baseline — 4 naive agents, no specialists",
    "v1_all_four_diversity": "v1 Finding 2 — diversity wins (7-9% Brier improvement)",
    "v1_high_correlation_penalty": "v1 Finding 4 — the 2.55x correlation penalty",
    "v1_tail_regime": "v1 Finding 3 — capital binds in tail markets",
    "exp1_capital_rich": "Next experiment #1 — $1000 capital, watch tail markets close",
    "exp2_confidence_sizing": "Next experiment #2 — confidence-weighted sizing",
    "exp3_loose_threshold": "Next experiment #3 — looser disagreement threshold",
    "high_capital_diversity_low_corr": "Best-case protocol design from v1 findings",
}
