"""
sim_v2.backend.pnl — Settlement, PnL, and rent extraction by agent class.

This is the new analytical surface area in v2. v1 measured Brier and gap-to-truth;
v2 adds the protocol-design framing of *who pays whom* once positions are
settled at the true probability.

Why this matters for a Metalayer-style audience: Brier improvements are
academic. PnL distributions tell you whether the protocol is extracting
informational rent cleanly (informed flow profits, noise flow pays, AMM
runs at a sustainable subsidy level) or whether subsidies are leaking to
unintended classes.

Settlement model:
  At horizon, each YES share pays p* (true probability), each NO share pays 1-p*.
  Agent realized PnL = settlement_value - total_cost_paid.
  AMM net = -(sum of agent PnLs) modulo subsidy.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Iterable
from .agent_classes import class_from_agent_id

import numpy as np

from .compute import SeedResult
from .models import AgentClassPnL, RentExtractionSummary


# ---------------------------------------------------------------------------
# Per-agent settlement
# ---------------------------------------------------------------------------


@dataclass
class AgentPnL:
    agent_id: str
    agent_class: str
    realized_pnl: float
    total_cost: float
    total_volume: float  # sum of |shares| traded
    n_trades: int
    yes_position_value: float
    no_position_value: float




def settle_agents(seed_result: SeedResult) -> list[AgentPnL]:
    """Walk the trade log, accumulate positions per (agent, market),
    settle at p_star at horizon, return per-agent PnL records."""

    # positions[agent_id][market_id] = (yes_shares, no_shares, total_cost)
    positions: dict[str, dict[int, tuple[float, float, float]]] = defaultdict(
        lambda: defaultdict(lambda: (0.0, 0.0, 0.0))
    )
    n_trades_by_agent: dict[str, int] = defaultdict(int)
    volume_by_agent: dict[str, float] = defaultdict(float)

    for trade in seed_result.trades:
        aid = trade["agent_id"]
        m = trade["market_id"]
        y, n, c = positions[aid][m]
        if trade["is_yes"]:
            y += trade["shares"]
        else:
            n += trade["shares"]
        c += trade["cost"]
        positions[aid][m] = (y, n, c)
        n_trades_by_agent[aid] += 1
        volume_by_agent[aid] += abs(trade["shares"])

    pnls: list[AgentPnL] = []
    # Iterate ALL agents (including non-traders), not just those with positions.
    # An agent with no trades has empty by_market, yielding realized_pnl=0,
    # which still surfaces the class in aggregate output. This matters for naive
    # credentialed agents whose posterior never crosses the disagreement threshold —
    # without this, their entire class disappears from the PnL panel (Finding 1).
    all_agent_ids = [a["agent_id"] for a in seed_result.agent_summary]
    for aid in all_agent_ids:
        by_market = positions.get(aid, {})
        yes_value = 0.0
        no_value = 0.0
        cost = 0.0
        for m, (y, n, c) in by_market.items():
            # Mark-to-market at horizon: positions valued at final market price,
            # not at the true probability. Reflects what traders could realize
            # by closing positions. p_star reachability isn't guaranteed (see
            # v1 Finding 3 LS-LMSR ceiling).
            final_price = float(seed_result.price_trace[m][-1])
            yes_value += y * final_price
            no_value += n * (1.0 - final_price)
            cost += c
        pnls.append(
            AgentPnL(
                agent_id=aid,
                agent_class=class_from_agent_id(aid),
                realized_pnl=(yes_value + no_value) - cost,
                total_cost=cost,
                total_volume=volume_by_agent[aid],
                n_trades=n_trades_by_agent[aid],
                yes_position_value=yes_value,
                no_position_value=no_value,
            )
        )
    return pnls


# ---------------------------------------------------------------------------
# Class-level aggregation
# ---------------------------------------------------------------------------


def aggregate_pnl_by_class(pnls: Iterable[AgentPnL]) -> list[AgentClassPnL]:
    """Bucket per-agent PnL into class-level statistics."""
    by_class: dict[str, list[AgentPnL]] = defaultdict(list)
    for p in pnls:
        by_class[p.agent_class].append(p)

    summaries: list[AgentClassPnL] = []
    for cls, items in by_class.items():
        pnl_arr = np.array([i.realized_pnl for i in items])
        vol_arr = np.array([i.total_volume for i in items])
        trades = sum(i.n_trades for i in items)
        volume = float(vol_arr.sum())
        pnl_per_trade = float(pnl_arr.sum() / trades) if trades > 0 else 0.0
        summaries.append(
            AgentClassPnL(
                agent_class=cls,
                n_agents=len(items),
                mean_pnl=float(pnl_arr.mean()),
                median_pnl=float(np.median(pnl_arr)),
                pnl_std=float(pnl_arr.std(ddof=1)) if len(pnl_arr) > 1 else 0.0,
                pnl_per_trade=pnl_per_trade,
                total_volume=volume,
                win_rate=float((pnl_arr > 0).mean()),
            )
        )

    summaries.sort(
        key=lambda s: {"naive": 0, "aggregation": 1, "tail": 2, "cross": 3, "noise": 4}.get(
            s.agent_class, 99
        )
    )
    return summaries


# ---------------------------------------------------------------------------
# Rent extraction summary
# ---------------------------------------------------------------------------


def compute_rent_extraction(
    class_pnls: list[AgentClassPnL], amm_subsidy: float = 0.0
) -> RentExtractionSummary:
    """The headline metric.

    informed_pnl: total profit to informational specialists (everyone except noise)
    noise_loss: absolute value of noise traders' aggregate loss (positive = they lose)
    amm_net: signed flow to/from the AMM (LS-LMSR's worst-case loss is its subsidy)
    rent_efficiency: how much of noise's loss flows to informed agents vs AMM

    For a well-designed protocol we'd expect:
      - noise_loss > 0 (uninformed flow funds rent)
      - informed_pnl > 0 (sophistication is rewarded)
      - amm_net ≈ -subsidy_budgeted (AMM pays expected subsidy, no surprises)
      - rent_efficiency near 1 (rent goes to informed traders, not lost to AMM)
    """
    by_class = {c.agent_class: c for c in class_pnls}

    informed_classes = ("naive", "aggregation", "tail", "cross")
    informed_pnl = sum(
        by_class[c].mean_pnl * by_class[c].n_agents
        for c in informed_classes
        if c in by_class
    )

    noise_pnl = (
        by_class["noise"].mean_pnl * by_class["noise"].n_agents
        if "noise" in by_class
        else 0.0
    )
    noise_loss = -noise_pnl  # positive when noise loses money

    # Conservation: informed + noise + amm_net = 0 (modulo subsidy)
    amm_net = -(informed_pnl + noise_pnl) + amm_subsidy

    if noise_loss > 1e-9:
        rent_efficiency = informed_pnl / noise_loss
    else:
        rent_efficiency = 0.0

    return RentExtractionSummary(
        total_informed_pnl=float(informed_pnl),
        noise_trader_loss=float(noise_loss),
        amm_net=float(amm_net),
        rent_efficiency=float(rent_efficiency),
    )


# ---------------------------------------------------------------------------
# Tail-market diagnostics (Finding 3 reproduction in v2)
# ---------------------------------------------------------------------------


def compute_tail_diagnostics(
    seed_result: SeedResult, tail_threshold: float = 0.35
) -> tuple[list[int], dict[int, float]]:
    """Identify tail markets (|p* - 0.5| > tail_threshold) and compute the
    excess gap (actual final price gap minus minimum gap given LS-LMSR ceiling).

    Returns (tail_market_ids, excess_gap_by_market)."""

    LS_LMSR_CEILING_OFFSET_FROM_HALF = 0.231  # sigmoid(1) - 0.5

    tail_ids: list[int] = []
    excess_gaps: dict[int, float] = {}

    for m, p_star in seed_result.p_star_by_market.items():
        if abs(p_star - 0.5) <= tail_threshold:
            continue
        tail_ids.append(int(m))
        final_price = float(seed_result.price_trace[m][-1])
        actual_gap = abs(final_price - p_star)

        # LS-LMSR with alpha=1 can express probabilities in
        # [0.5 - 0.231, 0.5 + 0.231]. Past that, structural ceiling.
        if p_star > 0.5 + LS_LMSR_CEILING_OFFSET_FROM_HALF:
            min_gap = p_star - (0.5 + LS_LMSR_CEILING_OFFSET_FROM_HALF)
        elif p_star < 0.5 - LS_LMSR_CEILING_OFFSET_FROM_HALF:
            min_gap = (0.5 - LS_LMSR_CEILING_OFFSET_FROM_HALF) - p_star
        else:
            min_gap = 0.0

        excess_gaps[int(m)] = max(0.0, actual_gap - min_gap)

    return tail_ids, excess_gaps


def settle_and_summarize(
    seed_result: SeedResult, amm_subsidy: float = 0.0
) -> tuple[list[AgentClassPnL], RentExtractionSummary, list[int], dict[int, float]]:
    """One-call settlement + summary, used by streaming.py to build FinalFrame."""
    per_agent = settle_agents(seed_result)
    by_class = aggregate_pnl_by_class(per_agent)
    rent = compute_rent_extraction(by_class, amm_subsidy=amm_subsidy)
    tail_ids, excess_gaps = compute_tail_diagnostics(seed_result)
    return by_class, rent, tail_ids, excess_gaps
