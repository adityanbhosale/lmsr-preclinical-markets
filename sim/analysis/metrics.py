"""
Convergence and robustness metrics for H1 and H2.

H1 metrics (retreat robustness under attack):
  - attack_displacement: how far the attack pushed the price
  - recovery_fraction: what fraction of displacement was recovered post-attack
  - retreat_engaged: whether the retreat function activated during the run
  - final_brier: Brier score at end of run

H2 metrics (convergence under mixed populations):
  - converged: did the price reach within epsilon of true_prob for K consecutive ticks
  - convergence_tick: the first tick at which the K-consecutive-ticks criterion was met
  - final_price: price at last tick
  - mean_post_convergence_error: mean |price - true_prob| after convergence
"""

from __future__ import annotations
import numpy as np
import pandas as pd


# ---------- shared helpers ----------

def brier_score(price: float, outcome: int) -> float:
    """Brier score for a single binary forecast."""
    return (price - outcome) ** 2


def mean_brier_trajectory(log: pd.DataFrame) -> float:
    """
    Mean Brier score across the run, treating true_probability as the target.
    Lower = better calibration.
    """
    return float(np.mean((log["price_yes"] - log["true_probability"]) ** 2))


# ---------- H2: convergence ----------

def convergence_tick(
    log: pd.DataFrame,
    epsilon: float = 0.03,
    k: int = 50,
) -> int | None:
    """
    First tick at which |price_yes - true_prob| < epsilon for K consecutive
    ticks. Returns None if convergence is never reached.

    Parameters
    ----------
    epsilon : float
        Tolerance band around true probability.
    k : int
        Number of consecutive ticks the price must stay within the band.
    """
    deviations = np.abs(log["price_yes"].values - log["true_probability"].values)
    within_band = deviations < epsilon

    # rolling sum of length k; if it equals k, all k previous ticks were within
    rolling = pd.Series(within_band).rolling(window=k).sum()
    converged_mask = rolling == k

    if not converged_mask.any():
        return None

    # convergence_tick is the *first* tick of the K-window, not the last
    first_satisfying_tick = int(converged_mask.idxmax())
    return first_satisfying_tick - k + 1


def has_converged(log: pd.DataFrame, epsilon: float = 0.03, k: int = 50) -> bool:
    return convergence_tick(log, epsilon, k) is not None


def mean_post_convergence_error(
    log: pd.DataFrame,
    epsilon: float = 0.03,
    k: int = 50,
) -> float | None:
    """Mean |price - true_prob| from convergence onward. None if never converged."""
    tick = convergence_tick(log, epsilon, k)
    if tick is None:
        return None
    post = log.iloc[tick:]
    return float(np.mean(np.abs(post["price_yes"] - post["true_probability"])))


# ---------- H1: retreat robustness ----------

def find_attack_tick(log: pd.DataFrame) -> int | None:
    """
    Identify the tick at which the adversarial trade fired.
    Heuristic: the adversarial agent has agent_id starting with 'adv_'.
    """
    adv_trades = log[
        log["agent_id"].str.startswith("adv_") & (log["shares"] > 0)
    ]
    if len(adv_trades) == 0:
        return None
    return int(adv_trades["tick"].iloc[0])


def attack_displacement(log: pd.DataFrame) -> float | None:
    """
    Price change caused by the attack trade itself (price after - price before).
    Returns None if no attack occurred.
    """
    attack_tick = find_attack_tick(log)
    if attack_tick is None or attack_tick == 0:
        return None
    price_before = log.iloc[attack_tick - 1]["price_yes"]
    price_after = log.iloc[attack_tick]["price_yes"]
    return float(price_after - price_before)


def recovery_fraction(
    log: pd.DataFrame,
    recovery_window: int = 200,
) -> float | None:
    """
    Fraction of attack displacement recovered within `recovery_window` ticks.

    1.0 = full recovery (price back to pre-attack level)
    0.0 = no recovery (price stays at post-attack level)
    >1.0 = overshoot (price went past pre-attack level in opposite direction)
    """
    attack_tick = find_attack_tick(log)
    if attack_tick is None or attack_tick == 0:
        return None

    price_before = log.iloc[attack_tick - 1]["price_yes"]
    price_after_attack = log.iloc[attack_tick]["price_yes"]
    displacement = price_after_attack - price_before

    if abs(displacement) < 1e-6:
        return None  # no displacement to recover from

    end_tick = min(attack_tick + recovery_window, len(log) - 1)
    price_at_recovery = log.iloc[end_tick]["price_yes"]

    recovered = price_after_attack - price_at_recovery
    return float(recovered / displacement)


def retreat_engaged(log: pd.DataFrame) -> bool:
    """Whether retreat factor dropped below 1.0 at any point."""
    return bool((log["retreat_factor"] < 1.0).any())


def min_retreat_factor(log: pd.DataFrame) -> float:
    """Lowest retreat factor reached during the run."""
    return float(log["retreat_factor"].min())


# ---------- summary builders ----------

def h1_summary(log: pd.DataFrame, recovery_window: int = 200) -> dict:
    """Single-run summary for H1 results."""
    return {
        "attack_tick": find_attack_tick(log),
        "attack_displacement": attack_displacement(log),
        "recovery_fraction": recovery_fraction(log, recovery_window),
        "retreat_engaged": retreat_engaged(log),
        "min_retreat_factor": min_retreat_factor(log),
        "final_price": float(log.iloc[-1]["price_yes"]),
        "true_probability": float(log.iloc[-1]["true_probability"]),
        "final_abs_error": float(
            abs(log.iloc[-1]["price_yes"] - log.iloc[-1]["true_probability"])
        ),
        "mean_brier": mean_brier_trajectory(log),
    }


def h2_summary(log: pd.DataFrame, epsilon: float = 0.03, k: int = 50) -> dict:
    """Single-run summary for H2 results."""
    tick = convergence_tick(log, epsilon, k)
    return {
        "converged": tick is not None,
        "convergence_tick": tick,
        "epsilon": epsilon,
        "k": k,
        "final_price": float(log.iloc[-1]["price_yes"]),
        "true_probability": float(log.iloc[-1]["true_probability"]),
        "final_abs_error": float(
            abs(log.iloc[-1]["price_yes"] - log.iloc[-1]["true_probability"])
        ),
        "mean_post_convergence_error": mean_post_convergence_error(
            log, epsilon, k
        ),
        "mean_brier": mean_brier_trajectory(log),
    }