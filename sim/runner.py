"""
Simulation runner. Instantiates a market, populates with agents,
steps through trades, logs to a list (and optionally Parquet).
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import Sequence
import numpy as np
import pandas as pd

from .market import LSLMSRMarket, LSLMSRConfig, ABMMConfig
from .agents.base import Agent


@dataclass
class RunResult:
    config: dict
    log: pd.DataFrame


def run_simulation(
    market_config: LSLMSRConfig,
    abmm_config: ABMMConfig,
    agents: Sequence[Agent],
    n_trades: int,
    rng: np.random.Generator,
    true_probability: float = 0.5,
) -> RunResult:
    """
    Run a single simulation.

    At each tick: sample one agent uniformly, call its decide(), execute the
    trade, record the resulting state.
    """
    market = LSLMSRMarket(config=market_config, abmm=abmm_config)
    log_rows = []

    for t in range(n_trades):
        agent = agents[int(rng.integers(0, len(agents)))]
        state = market.snapshot()
        state["tick"] = t
        action = agent.decide(state)

        if not action.is_noop:
            cost = market.execute_trade(
                is_yes=action.is_yes,
                shares=action.shares,
            )
        else:
            cost = 0.0

        post_state = market.snapshot()
        log_rows.append({
            "tick": t,
            "agent_id": agent.agent_id,
            "is_yes": action.is_yes,
            "shares": action.shares,
            "cost": cost,
            "price_yes": post_state["price_yes"],
            "price_no": post_state["price_no"],
            "b": post_state["b"],
            "human_volume": post_state["human_volume"],
            "retreat_factor": post_state["retreat_factor"],
            "true_probability": true_probability,
        })

    return RunResult(
        config={
            "market": market_config.__dict__,
            "abmm": abmm_config.__dict__,
            "n_trades": n_trades,
            "n_agents": len(agents),
            "true_probability": true_probability,
        },
        log=pd.DataFrame(log_rows),
    )


if __name__ == "__main__":
    # End-of-Day-4 milestone: all four agent classes running together.
    from .agents import NoiseTrader, CredentialedTrader, MomentumTrader

    rng = np.random.default_rng(seed=42)
    true_prob = 0.65

    # 60% credentialed, 30% noise, 10% momentum
    agents = (
        [
            CredentialedTrader(
                f"cred_{i}", rng,
                true_probability=true_prob,
                sigma=0.10,
                aggressiveness=0.5,
            )
            for i in range(30)
        ]
        + [NoiseTrader(f"noise_{i}", rng, mean_size=3.0, size_std=1.0)
           for i in range(15)]
        + [MomentumTrader(f"mom_{i}", rng, lookback=15)
           for i in range(5)]
    )

    result = run_simulation(
        market_config=LSLMSRConfig(
            alpha=0.05, q_abmm_yes=500.0, q_abmm_no=500.0
        ),
        abmm_config=ABMMConfig(enabled=False),
        agents=agents,
        n_trades=1000,
        rng=rng,
        true_probability=true_prob,
    )

    print(f"Final price_yes: {result.log.iloc[-1]['price_yes']:.4f}")
    print(f"True probability: {true_prob}")
    print(f"Final b: {result.log.iloc[-1]['b']:.2f}")
    print(f"Trade count by agent class:")
    agent_class_counts = (
        result.log.assign(
            agent_class=result.log["agent_id"].str.split("_").str[0]
        )
        .groupby("agent_class")
        .size()
    )
    print(agent_class_counts)

    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(figsize=(10, 4))
    ax.plot(result.log["tick"], result.log["price_yes"],
            label="price (yes)", linewidth=1)
    ax.axhline(true_prob, color="red", linestyle="--",
               label=f"true probability ({true_prob})")
    ax.set_xlabel("tick")
    ax.set_ylabel("price")
    ax.set_ylim(0, 1)
    ax.legend()
    ax.set_title(
        "End-of-Day-4 milestone: 60% credentialed, 30% noise, 10% momentum"
    )
    fig.tight_layout()
    fig.savefig("sim/notebooks/day4_milestone.png", dpi=120)
    print("\nplot saved to sim/notebooks/day4_milestone.png")