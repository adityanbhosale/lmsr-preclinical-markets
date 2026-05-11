"""
Single-run orchestrator for the agentic sim.

Wires InformationEnvironment, MarketEnvironment, AgentPopulation, and the
discrete-event simulator into one `run_sim` call. Returns a RunResults
object holding both the rich post-run state (for in-memory analysis) and
flat-record accessor methods (for parquet serialization in Task 9-10).

Determinism contract
--------------------
A single `seed` produces a single `np.random.Generator` that flows through:
  1. InformationEnvironment construction (latent factors, loadings, ε_m)
  2. The user's `make_agents(info_env, rng)` factory (any agent-side
     randomness, e.g. noisy base rates for TailEventReasoningAgent)
  3. AgentPopulation.register (initial noise-trade scheduling)
  4. InformationEnvironment.schedule_signals (all signal arrivals)
  5. Simulator.run_until (noise-trader RNG consumption during fire_noise)

Same seed → bit-identical RunResults across runs in the same environment.
Verified by `test_runner_determinism`.

Snapshot mechanism
------------------
A new "_snapshot" event type fires at multiples of `snapshot_interval` ticks.
Priority BOOKKEEPING (1000) > all trade/decision priorities, so snapshots
record POST-trade state at each tick. One snapshot per (timestamp, market_id),
flat-record format suitable for parquet.

What's NOT in Task 8
--------------------
- Agent-level posterior trajectories — different agent classes have different
  posterior shapes. Easy to add per agent type in Task 9-10 if needed.
- Parquet serialization itself — RunResults provides the records; the sweep
  layer (Task 9) writes them.
- Parallel runs — sweep layer's concern, not the single-run runner.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional

import numpy as np

from sim.agentic import AgentPopulation
from sim.events import EventPriority
from sim.information import InformationConfig, InformationEnvironment
from sim.market_env import MarketEnvironment, MarketSpec, TradeRecord
from sim.simulator import Simulator


SNAPSHOT_EVENT: str = "_snapshot"


# Type alias for the agent factory: takes (info_env, rng), returns list of agents.
MakeAgentsFn = Callable[[InformationEnvironment, np.random.Generator], list]


@dataclass
class RunResults:
    """
    Output of a single `run_sim` call.

    Holds the rich post-run state for in-memory analysis plus accessor methods
    that produce flat-record (dict) representations of the trade log, agent
    summaries, snapshots, and a single summary row. Flat records compose
    naturally into pandas DataFrames and parquet writes downstream.
    """
    seed: int
    horizon: int
    n_markets: int

    info_env: InformationEnvironment
    market_env: MarketEnvironment
    agents: list

    snapshots: list  # list[dict] — one row per (timestamp, market_id)

    # ---- convenience views ----

    @property
    def trade_log(self) -> list[TradeRecord]:
        return self.market_env.trade_log

    @property
    def final_prices_yes(self) -> np.ndarray:
        return self.market_env.prices_yes()

    @property
    def p_star(self) -> np.ndarray:
        return self.info_env.world.p_star_array

    def brier_per_market(self) -> np.ndarray:
        """(p_market - p_star)² at end of run, one entry per market."""
        return (self.final_prices_yes - self.p_star) ** 2

    # ---- flat records for parquet ----

    def trade_records(self) -> list[dict]:
        return [
            {
                "seed": self.seed,
                "timestamp": r.timestamp,
                "market_id": r.market_id,
                "agent_id": r.agent_id,
                "is_yes": bool(r.is_yes),
                "shares": float(r.shares),
                "cost": float(r.cost),
                "price_yes_before": float(r.price_yes_before),
                "price_yes_after": float(r.price_yes_after),
            }
            for r in self.trade_log
        ]

    def agent_summary_records(self) -> list[dict]:
        """One row per agent: identity + budget consumption + trade count."""
        records: list[dict] = []
        trades_by_agent: dict = {}
        for r in self.trade_log:
            trades_by_agent[r.agent_id] = trades_by_agent.get(r.agent_id, 0) + 1
        for agent in self.agents:
            records.append({
                "seed": self.seed,
                "agent_id": agent.agent_id,
                "agent_type": type(agent).__name__,
                "budget": float(agent.budget),
                "deployed": float(agent.deployed),
                "n_trades": trades_by_agent.get(agent.agent_id, 0),
            })
        return records

    def snapshot_records(self) -> list[dict]:
        """Pass-through; snapshots are already in flat-record form."""
        return list(self.snapshots)

    def summary_record(self) -> dict:
        """Single-row summary of the entire run."""
        brier = self.brier_per_market()
        return {
            "seed": self.seed,
            "horizon": self.horizon,
            "n_markets": self.n_markets,
            "n_agents": len(self.agents),
            "n_trades": len(self.trade_log),
            "mean_brier": float(np.mean(brier)),
            "max_brier": float(np.max(brier)),
            "mean_final_price": float(np.mean(self.final_prices_yes)),
        }


def run_sim(
    info_config: InformationConfig,
    make_agents: MakeAgentsFn,
    *,
    horizon: int = 60_000,
    seed: int = 0,
    market_spec: Optional[MarketSpec] = None,
    time_resolution: int = 1000,
    snapshot_interval: int = 5_000,
) -> RunResults:
    """
    Run one simulation; return a RunResults bundle.

    Parameters
    ----------
    info_config : InformationConfig
        Latent factor world + signal-generation config.
    make_agents : (info_env, rng) -> list[Agent]
        Factory that builds the agent population given the constructed
        info_env and the shared RNG. Required to be a callable (not a
        pre-built list) so that any agent-side randomness participates in
        the single-seed determinism contract.
    horizon : int
        Run length in ticks.
    seed : int
        Single RNG seed.
    market_spec : MarketSpec, optional
        Defaults to MarketSpec() — polynomial-decay retreat (H1 winner).
    time_resolution : int
        Ticks per unit time.
    snapshot_interval : int
        Ticks between price snapshots. 0 disables periodic snapshots
        (only t=0 and t=horizon are captured).
    """
    if horizon <= 0:
        raise ValueError(f"horizon must be positive, got {horizon}")
    if snapshot_interval < 0:
        raise ValueError(f"snapshot_interval must be non-negative, got {snapshot_interval}")
    if time_resolution < 1:
        raise ValueError(f"time_resolution must be >= 1, got {time_resolution}")
    if market_spec is None:
        market_spec = MarketSpec()

    rng = np.random.default_rng(seed)
    info_env = InformationEnvironment(info_config, rng)
    market_env = MarketEnvironment(
        n_markets=info_env.n_markets,
        spec=market_spec,
    )
    agents = list(make_agents(info_env, rng))
    pop = AgentPopulation(agents) if agents else None

    sim = Simulator(rng=rng, time_resolution=time_resolution)
    market_env.register(sim)
    if pop is not None:
        pop.register(sim, market_env, until_ts=horizon)
    else:
        # No agents → register a no-op signal handler so info_env's signal
        # events can still dispatch (otherwise KeyError on first signal).
        sim.register_handler("signal", lambda s, event: None)

    snapshots: list[dict] = []
    p_star_cached = info_env.world.p_star_array
    last_snapshot_t: list[int] = [-1]  # mutable cell for closure

    def _record_snapshot(t: int) -> None:
        prices = market_env.prices_yes()
        for m_id in range(info_env.n_markets):
            snapshots.append({
                "seed": seed,
                "timestamp": t,
                "market_id": m_id,
                "price_yes": float(prices[m_id]),
                "p_star": float(p_star_cached[m_id]),
                "brier": float((prices[m_id] - p_star_cached[m_id]) ** 2),
            })
        last_snapshot_t[0] = t

    def _snapshot_handler(s: Simulator, event) -> None:
        _record_snapshot(s.now)
        next_t = s.now + snapshot_interval
        if next_t <= horizon:
            s.schedule_at(
                timestamp=next_t,
                event_type=SNAPSHOT_EVENT,
                priority=EventPriority.BOOKKEEPING,
            )

    # Always capture t=0 (pre-run state)
    _record_snapshot(0)

    if snapshot_interval > 0:
        sim.register_handler(SNAPSHOT_EVENT, _snapshot_handler)
        if snapshot_interval <= horizon:
            sim.schedule_at(
                timestamp=snapshot_interval,
                event_type=SNAPSHOT_EVENT,
                priority=EventPriority.BOOKKEEPING,
            )

    info_env.schedule_signals(sim, until_ts=horizon)
    sim.run_until(horizon)

    # Capture final state at horizon if the handler didn't already
    if last_snapshot_t[0] < horizon:
        _record_snapshot(horizon)

    return RunResults(
        seed=seed,
        horizon=horizon,
        n_markets=info_env.n_markets,
        info_env=info_env,
        market_env=market_env,
        agents=agents,
        snapshots=snapshots,
    )
