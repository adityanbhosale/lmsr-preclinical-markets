"""
sim_v2.backend.streaming — Frame batching and pacing for the WebSocket.

Maps the pre-computed SeedResult (which has tick-resolution price traces and
a flat trade log) into a paced stream of FrameMessages, plus one CIBandFrame
at the start and one FinalFrame at the end.

Pacing model:
  - The user picks duration_seconds (3-15 min) and target_fps (2-30).
  - Total frames = duration_seconds * target_fps. Default 420s * 8fps = 3,360 frames.
  - The simulation horizon is horizon_ticks (default 10,000).
  - Frame n samples the simulation at tick = round(n / total_frames * horizon_ticks).
  - Trades and agent state are bucketed into the inter-frame window.

Event-aligned pacing (optional): the streamer can detect "important" frames
(large price moves, signal arrivals, threshold crossings) and dwell briefly,
borrowing time from quiescent stretches. Skipped in this sketch for clarity;
the hooks are noted.
"""

from __future__ import annotations

import asyncio
import math
from collections import defaultdict
from dataclasses import dataclass
from typing import AsyncIterator, Iterable

from .compute import SeedResult, compute_ci_band
from .models import (
    SimRequest,
    FrameMessage,
    CIBandFrame,
    FinalFrame,
    MarketSnapshot,
    AgentSnapshot,
    TradeEvent,
    ErrorFrame,
)
from .pnl import settle_and_summarize


# ---------------------------------------------------------------------------
# Per-seed framing
# ---------------------------------------------------------------------------


@dataclass
class FramePlan:
    """Pre-computed schedule of (frame_index, simulation_tick) pairs."""

    total_frames: int
    frame_to_tick: list[int]
    seconds_per_frame: float


def build_frame_plan(req: SimRequest) -> FramePlan:
    total_frames = req.stream.duration_seconds * req.stream.target_fps
    horizon = req.horizon_ticks
    frame_to_tick = [
        int(round((i + 1) / total_frames * horizon)) for i in range(total_frames)
    ]
    # Ensure final frame hits the horizon exactly
    frame_to_tick[-1] = horizon
    return FramePlan(
        total_frames=total_frames,
        frame_to_tick=frame_to_tick,
        seconds_per_frame=1.0 / req.stream.target_fps,
    )


def _bucket_trades_by_frame(
    seed: SeedResult, plan: FramePlan
) -> list[list[dict]]:
    """Distribute the flat trade log into per-frame buckets."""
    buckets: list[list[dict]] = [[] for _ in range(plan.total_frames)]
    if not seed.trades:
        return buckets

    sorted_trades = sorted(seed.trades, key=lambda t: t["tick"])
    frame_idx = 0
    for trade in sorted_trades:
        while (
            frame_idx < plan.total_frames - 1
            and trade["tick"] > plan.frame_to_tick[frame_idx]
        ):
            frame_idx += 1
        buckets[frame_idx].append(trade)
    return buckets


def _agent_snapshots_at_frame(
    seed: SeedResult, up_to_tick: int
) -> list[AgentSnapshot]:
    """Reconstruct agent positions and capital at a given tick by replaying
    the trade log up to that point. O(n_trades) per frame — fine at the
    frame counts and trade counts v2 deals with."""
    yes_by_agent_market: dict[tuple[str, int], float] = defaultdict(float)
    no_by_agent_market: dict[tuple[str, int], float] = defaultdict(float)
    cost_by_agent: dict[str, float] = defaultdict(float)
    trades_by_agent: dict[str, int] = defaultdict(int)
    classes: dict[str, str] = {}

    for trade in seed.trades:
        if trade["tick"] > up_to_tick:
            break
        aid = trade["agent_id"]
        m = trade["market_id"]
        key = (aid, m)
        if trade["is_yes"]:
            yes_by_agent_market[key] += trade["shares"]
        else:
            no_by_agent_market[key] += trade["shares"]
        cost_by_agent[aid] += trade["cost"]
        trades_by_agent[aid] += 1
        # Recover class from agent summary
        classes.setdefault(aid, _class_from_id(aid))

    # Need budget info — pull from agent_summary
    budget_by_agent: dict[str, float] = {
        rec["agent_id"]: rec.get("budget", 100.0) for rec in seed.agent_summary
    }

    snapshots: list[AgentSnapshot] = []
    for aid in sorted(classes):
        yes_pos: dict[int, float] = {}
        no_pos: dict[int, float] = {}
        for (a2, m), shares in yes_by_agent_market.items():
            if a2 == aid and shares != 0:
                yes_pos[int(m)] = float(shares)
        for (a2, m), shares in no_by_agent_market.items():
            if a2 == aid and shares != 0:
                no_pos[int(m)] = float(shares)
        deployed = cost_by_agent[aid]
        budget = budget_by_agent.get(aid, 100.0)
        snapshots.append(
            AgentSnapshot(
                agent_id=aid,
                agent_class=classes[aid],
                capital_deployed=float(deployed),
                capital_remaining=float(max(0.0, budget - deployed)),
                n_trades=trades_by_agent[aid],
                yes_shares_by_market=yes_pos,
                no_shares_by_market=no_pos,
            )
        )
    return snapshots


def _class_from_id(agent_id: str) -> str:
    for cls in ("naive", "agg", "tail", "cross", "noise"):
        if agent_id.startswith(cls):
            return "aggregation" if cls == "agg" else cls
    return "unknown"


def build_frames(
    seed: SeedResult, plan: FramePlan, seed_id: int = 0
) -> Iterable[FrameMessage]:
    """Yield FrameMessage objects on the schedule defined by plan."""
    buckets = _bucket_trades_by_frame(seed, plan)
    market_ids = seed.market_ids

    # Track cumulative volume per market for the snapshot field
    cum_volume: dict[int, float] = {m: 0.0 for m in market_ids}
    cum_trades: dict[int, int] = {m: 0 for m in market_ids}

    for frame_idx, tick in enumerate(plan.frame_to_tick):
        # Update cumulative volume from this frame's bucket
        for t in buckets[frame_idx]:
            m = t["market_id"]
            cum_volume[m] = cum_volume.get(m, 0.0) + abs(t["shares"])
            cum_trades[m] = cum_trades.get(m, 0) + 1

        markets = []
        for m in market_ids:
            price = float(seed.price_trace[m][min(tick, len(seed.price_trace[m]) - 1)])
            p_star = seed.p_star_by_market[m]
            markets.append(
                MarketSnapshot(
                    market_id=int(m),
                    price_yes=price,
                    p_star=float(p_star),
                    instantaneous_brier=float((price - p_star) ** 2),
                    cumulative_volume=cum_volume[m],
                    n_trades=cum_trades[m],
                )
            )

        trades_delta = [
            TradeEvent(
                tick=t["timestamp"],
                market_id=int(t["market_id"]),
                agent_id=t["agent_id"],
                agent_class=_class_from_id(t["agent_id"]),
                is_yes=bool(t["is_yes"]),
                shares=float(t["shares"]),
                cost=float(t["cost"]),
                price_before=float(t["price_yes_before"]),
                price_after=float(t["price_yes_after"]),
            )
            for t in buckets[frame_idx]
        ]

        agents = _agent_snapshots_at_frame(seed, tick)
        aggregate_brier = (
            sum((s.price_yes - s.p_star) ** 2 for s in markets) / len(markets)
            if markets
            else 0.0
        )

        yield FrameMessage(
            seed_id=seed_id,
            tick=tick,
            wall_t=(frame_idx + 1) * plan.seconds_per_frame,
            markets=markets,
            trades_delta=trades_delta,
            agents=agents,
            aggregate_brier=float(aggregate_brier),
        )


# ---------------------------------------------------------------------------
# Async stream orchestration
# ---------------------------------------------------------------------------


async def stream_seed(
    seed: SeedResult,
    plan: FramePlan,
    seed_id: int = 0,
    amm_subsidy: float = 0.0,
) -> AsyncIterator:
    """Yield CIBandFrame? No — CI band is computed across seeds, handled by caller.
    This yields FrameMessages paced at plan.seconds_per_frame, then one FinalFrame."""
    for frame in build_frames(seed, plan, seed_id=seed_id):
        yield frame
        await asyncio.sleep(plan.seconds_per_frame)

    class_pnls, rent, tail_ids, excess_gaps = settle_and_summarize(
        seed, amm_subsidy=amm_subsidy
    )
    yield FinalFrame(
        seed_id=seed_id,
        final_aggregate_brier=float(
            sum(
                (seed.price_trace[m][-1] - seed.p_star_by_market[m]) ** 2
                for m in seed.market_ids
            )
            / len(seed.market_ids)
        ),
        pnl_by_class=class_pnls,
        rent_extraction=rent,
        tail_market_ids=tail_ids,
        tail_market_excess_gaps={int(k): float(v) for k, v in excess_gaps.items()},
    )


def build_ci_band_message(ci_results: list[SeedResult]) -> CIBandFrame:
    """Wrap compute.compute_ci_band output into a CIBandFrame."""
    band = compute_ci_band(ci_results, ci_results[0].market_ids)
    return CIBandFrame(
        ticks=band["ticks"],
        brier_p025=band["brier_p025"],
        brier_p975=band["brier_p975"],
        brier_mean=band["brier_mean"],
        price_yes_mean_by_market={
            str(k): v for k, v in band["price_yes_mean_by_market"].items()
        },
    )
