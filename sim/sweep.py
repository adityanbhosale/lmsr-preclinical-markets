"""
Sweep orchestration. Reads a YAML config, generates the parameter grid,
runs each cell across multiple seeds, persists results to Parquet.
"""

from __future__ import annotations
import itertools
import pathlib
import time
from typing import Any
import numpy as np
import pandas as pd
import yaml

from .market import LSLMSRMarket, LSLMSRConfig, ABMMConfig
from .runner import run_simulation
from .agents import (
    NoiseTrader,
    CredentialedTrader,
    MomentumTrader,
    AdversarialTrader,
)
from .analysis.metrics import h1_summary, h2_summary


# ---------- agent population builder ----------

def build_agents(
    mix: tuple[float, float, float],
    total: int,
    true_prob: float,
    rng: np.random.Generator,
    cred_params: dict,
    noise_params: dict,
    mom_params: dict,
) -> list:
    """
    Build an agent population given a (credentialed, noise, momentum) mix.
    """
    n_cred = int(round(mix[0] * total))
    n_noise = int(round(mix[1] * total))
    n_mom = total - n_cred - n_noise   # remainder to ensure total exact

    agents = []
    agents.extend([
        CredentialedTrader(
            agent_id=f"cred_{i}",
            rng=rng,
            true_probability=true_prob,
            **cred_params,
        )
        for i in range(n_cred)
    ])
    agents.extend([
        NoiseTrader(agent_id=f"noise_{i}", rng=rng, **noise_params)
        for i in range(n_noise)
    ])
    agents.extend([
        MomentumTrader(agent_id=f"mom_{i}", rng=rng, **mom_params)
        for i in range(n_mom)
    ])
    return agents


def market_with_starting_prior(
    market_cfg: dict,
    abmm_cfg: ABMMConfig,
    starting_prior: float,
) -> LSLMSRMarket:
    """
    Construct a market with q_abmm seeding chosen to produce the requested
    initial price_yes.

    Math: with b = alpha*(q_yes + q_no),
          price_yes = exp(q_yes/b) / (exp(q_yes/b) + exp(q_no/b))
                    = 1 / (1 + exp((q_no - q_yes)/b))
    Let d = q_no - q_yes. Then price_yes = sigmoid(-d/b) = 1/(1+exp(d/b)).
    Setting price_yes = p, we get d/b = ln((1-p)/p) =: r.
    Choose q_yes = base, then q_no = base + r*b. But b = alpha*(2*base + r*b),
    so b*(1 - alpha*r) = 2*alpha*base, i.e. b = 2*alpha*base / (1 - alpha*r).
    Then q_no = base + r*b.

    Stability: requires alpha*r < 1, i.e. for alpha=0.05 we can handle
    |r| < 20, which corresponds to priors in (~5e-10, 1 - 5e-10). Fine.
    """
    base = market_cfg["q_abmm_yes"]
    alpha = market_cfg["alpha"]

    if abs(starting_prior - 0.5) < 1e-9:
        q_yes = base
        q_no = base
    else:
        r = float(np.log((1 - starting_prior) / starting_prior))
        denom = 1 - alpha * r
        if denom <= 0:
            raise ValueError(f"unstable seeding for prior={starting_prior}")
        b = 2 * alpha * base / denom
        q_yes = base
        q_no = base + r * b

        if q_no <= 0:
            raise ValueError(
                f"negative q_no for prior={starting_prior}: q_no={q_no}"
            )

    cfg = LSLMSRConfig(alpha=alpha, q_abmm_yes=q_yes, q_abmm_no=q_no)
    return LSLMSRMarket(config=cfg, abmm=abmm_cfg)


# ---------- H2 sweep ----------

def run_h2_sweep(config_path: str, output_dir: str = "sim/results") -> pd.DataFrame:
    with open(config_path) as f:
        cfg = yaml.safe_load(f)

    out_dir = pathlib.Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    cells = list(itertools.product(
        cfg["sweep"]["agent_mix"],
        cfg["sweep"]["starting_prior"],
        cfg["sweep"]["true_probability"],
        range(cfg["n_seeds"]),
    ))

    print(f"H2 sweep: {len(cells)} runs total")
    summaries = []
    start = time.time()

    for idx, (mix, prior, true_prob, seed) in enumerate(cells):
        rng = np.random.default_rng(seed=seed * 10000 + idx)

        agents = build_agents(
            mix=mix,
            total=cfg["agents"]["total_agents"],
            true_prob=true_prob,
            rng=rng,
            cred_params=cfg["agents"]["credentialed"],
            noise_params=cfg["agents"]["noise"],
            mom_params=cfg["agents"]["momentum"],
        )

        abmm = ABMMConfig(enabled=cfg["abmm"]["enabled"])

        market = market_with_starting_prior(
            cfg["market"], abmm, prior
        )

        # since runner instantiates its own market, we need a small inline run
        log = _run_inline(
            market=market,
            agents=agents,
            n_trades=cfg["n_trades"],
            rng=rng,
            true_probability=true_prob,
        )

        summary = h2_summary(
            log,
            epsilon=cfg["convergence"]["epsilon"],
            k=cfg["convergence"]["k"],
        )
        summary.update({
            "mix_cred": mix[0],
            "mix_noise": mix[1],
            "mix_mom": mix[2],
            "starting_prior": prior,
            "true_probability_grid": true_prob,
            "seed": seed,
            "cell_idx": idx,
        })
        summaries.append(summary)

        if (idx + 1) % 50 == 0:
            elapsed = time.time() - start
            rate = (idx + 1) / elapsed
            remaining = (len(cells) - idx - 1) / rate
            print(
                f"  [{idx+1}/{len(cells)}] {rate:.1f} runs/s, "
                f"~{remaining/60:.1f} min remaining"
            )

    df = pd.DataFrame(summaries)
    out_path = out_dir / f"{cfg['name']}.parquet"
    df.to_parquet(out_path)
    print(f"Wrote {len(df)} rows to {out_path}")
    print(f"Total elapsed: {(time.time()-start)/60:.1f} min")
    return df


# ---------- H1 sweep ----------

def run_h1_sweep(config_path: str, output_dir: str = "sim/results") -> pd.DataFrame:
    with open(config_path) as f:
        cfg = yaml.safe_load(f)

    out_dir = pathlib.Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    cells = list(itertools.product(
        cfg["sweep"]["abmm_tau"],
        cfg["sweep"]["abmm_threshold"],
        cfg["sweep"]["decay_shape"],
        cfg["sweep"]["attack_magnitude_pct"],
        cfg["sweep"]["attack_direction"],
        range(cfg["n_seeds"]),
    ))

    print(f"H1 sweep: {len(cells)} runs total")
    summaries = []
    start = time.time()

    for idx, (tau, thresh, shape, mag, direction, seed) in enumerate(cells):
        rng = np.random.default_rng(seed=seed * 10000 + idx)

        true_prob = cfg["true_probability"]
        agents = build_agents(
            mix=tuple(cfg["agents"]["mix"]),
            total=cfg["agents"]["total_agents"],
            true_prob=true_prob,
            rng=rng,
            cred_params=cfg["agents"]["credentialed"],
            noise_params=cfg["agents"]["noise"],
            mom_params=cfg["agents"]["momentum"],
        )

        # add the adversarial agent
        attack_shares = mag * (
            cfg["market"]["q_abmm_yes"] + cfg["market"]["q_abmm_no"]
        )
        agents.append(AdversarialTrader(
            agent_id="adv_0",
            rng=rng,
            attack_tick=cfg["attack_tick"],
            attack_shares=attack_shares,
            attack_is_yes=(direction == "yes"),
        ))

        abmm = ABMMConfig(
            enabled=True,
            tau=tau,
            threshold=thresh,
            decay_shape=shape,
        )

        market = market_with_starting_prior(
            cfg["market"], abmm, cfg["starting_prior"]
        )

        log = _run_inline(
            market=market,
            agents=agents,
            n_trades=cfg["n_trades"],
            rng=rng,
            true_probability=true_prob,
        )

        summary = h1_summary(log, recovery_window=cfg["recovery_window"])
        summary.update({
            "abmm_tau": tau,
            "abmm_threshold": thresh,
            "decay_shape": shape,
            "attack_magnitude_pct": mag,
            "attack_direction": direction,
            "seed": seed,
            "cell_idx": idx,
        })
        summaries.append(summary)

        if (idx + 1) % 50 == 0:
            elapsed = time.time() - start
            rate = (idx + 1) / elapsed
            remaining = (len(cells) - idx - 1) / rate
            print(
                f"  [{idx+1}/{len(cells)}] {rate:.1f} runs/s, "
                f"~{remaining/60:.1f} min remaining"
            )

    df = pd.DataFrame(summaries)
    out_path = out_dir / f"{cfg['name']}.parquet"
    df.to_parquet(out_path)
    print(f"Wrote {len(df)} rows to {out_path}")
    print(f"Total elapsed: {(time.time()-start)/60:.1f} min")
    return df


# ---------- internal helper ----------

def _run_inline(
    market: LSLMSRMarket,
    agents: list,
    n_trades: int,
    rng: np.random.Generator,
    true_probability: float,
) -> pd.DataFrame:
    """
    Inline simulation loop. Same as runner.run_simulation but takes a
    pre-constructed market (so we can control starting prior).
    """
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
    return pd.DataFrame(log_rows)


# ---------- entry point ----------

if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: python -m sim.sweep <config.yaml>")
        sys.exit(1)
    cfg_path = sys.argv[1]
    with open(cfg_path) as f:
        hyp = yaml.safe_load(f)["hypothesis"]
    if hyp == "H1":
        run_h1_sweep(cfg_path)
    elif hyp == "H2":
        run_h2_sweep(cfg_path)
    else:
        raise ValueError(f"unknown hypothesis: {hyp}")