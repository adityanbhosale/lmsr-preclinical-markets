"""
retreat_functions.py
--------------------
Comparison of ABMM retreat function parameterizations.

Explores the tradeoffs between linear, exponential, and threshold-based
retreat functions in terms of:
    - Early signal capture
    - Price stability in thin markets
    - Approximate incentive-compatibility properties

See README §Open Theoretical Questions for the formal treatment.
"""

import math
from typing import Callable


def linear_retreat(ldi: float, threshold: float = 1000.0) -> float:
    """
    w(ldi) = max(0, 1 - ldi/threshold)

    Failure modes:
        - Slow early retreat suppresses most valuable expert corrections
        - Abrupt exit at threshold destabilizes thin markets
        - No residual floor for perpetually thin specialty markets
    """
    return max(0.0, 1.0 - ldi / threshold)


def exponential_retreat(ldi: float, ldi_half: float = 500.0) -> float:
    """
    w(ldi) = exp(-lambda * ldi),  lambda = log(2) / ldi_half

    Properties:
        - w(0) = 1.0          : full ABMM dominance at open
        - w(ldi_half) = 0.5   : ABMM influence halved at ldi_half
        - w(inf) -> 0         : asymptotic retreat, never fully zero
        - Concave: fast early retreat, asymptotic residual floor

    This is the proposed retreat function. See lmsr_prior.py for
    calibration-weighted LDI extension.
    """
    lambda_ = math.log(2) / max(ldi_half, 1e-9)
    return math.exp(-lambda_ * ldi)


def threshold_retreat(ldi: float, threshold: float = 1000.0) -> float:
    """
    w(ldi) = 1 if ldi < threshold else 0

    Simple but creates a discontinuity in the price surface at
    the threshold crossing. Not recommended for production use.
    """
    return 1.0 if ldi < threshold else 0.0


def convex_retreat(ldi: float, threshold: float = 1000.0) -> float:
    """
    w(ldi) = (1 - ldi/threshold)^2  for ldi < threshold, else 0

    Slow early, fast late — the opposite of what structural analysis
    recommends. Included for comparison only.
    """
    if ldi >= threshold:
        return 0.0
    return (1.0 - ldi / threshold) ** 2


# ── Incentive-compatibility distortion bound ─────────────────────────────────

def ic_distortion_bound(
    weight: float,
    q_abmm_total: float,
    alpha: float,
    p_star: float,
    p_abmm: float,
) -> float:
    """
    Approximate upper bound on incentive-compatibility distortion δ.

    From the ε-IC condition: w(t) · q_abmm ≤ δ(ε, α, p*)

    This is a heuristic approximation — the formal derivation is an
    open question (see README). The bound is tightest when p* is far
    from p_abmm (i.e., when expert correction is most valuable).

    Parameters
    ----------
    weight : float
        Current ABMM weight w(t).
    q_abmm_total : float
        Total ABMM stake magnitude.
    alpha : float
        Per-market liquidity sensitivity.
    p_star : float
        Expert's true belief.
    p_abmm : float
        Current ABMM-seeded market price.

    Returns
    -------
    float
        Approximate distortion bound (higher = more distortion).
    """
    disagreement = abs(p_star - p_abmm)
    abmm_pressure = weight * q_abmm_total * alpha
    return abmm_pressure * disagreement


# ── Comparative analysis ─────────────────────────────────────────────────────

def compare_all(
    ldi_range: list[float],
    ldi_half: float = 500.0,
    threshold: float = 1000.0,
) -> list[dict]:
    """
    Compare all retreat functions across a range of LDI values.

    Returns a list of dicts suitable for plotting or DataFrame conversion.
    """
    return [
        {
            "ldi": ldi,
            "exponential": round(exponential_retreat(ldi, ldi_half), 6),
            "linear": round(linear_retreat(ldi, threshold), 6),
            "convex": round(convex_retreat(ldi, threshold), 6),
            "threshold": round(threshold_retreat(ldi, threshold), 6),
        }
        for ldi in ldi_range
    ]


def ldi_at_weight(target_weight: float, ldi_half: float = 500.0) -> float:
    """
    Compute the LDI value at which exponential retreat reaches target_weight.

    ldi = -log(target_weight) / lambda
    """
    if not 0 < target_weight < 1:
        raise ValueError("target_weight must be in (0, 1)")
    lambda_ = math.log(2) / ldi_half
    return -math.log(target_weight) / lambda_


# ── CLI demo ──────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("Retreat Function Comparison")
    print(f"{'LDI':>8} {'Exponential':>14} {'Linear':>10} {'Convex':>10}")
    print("-" * 46)

    ldi_range = [0, 100, 250, 500, 750, 1000, 1500, 2000]
    for row in compare_all(ldi_range, ldi_half=500.0, threshold=1000.0):
        print(
            f"{row['ldi']:>8.0f} "
            f"{row['exponential']:>14.4f} "
            f"{row['linear']:>10.4f} "
            f"{row['convex']:>10.4f}"
        )

    print(f"\nExponential reaches w=0.1 at LDI = "
          f"{ldi_at_weight(0.1):.1f}")
    print(f"Exponential reaches w=0.5 at LDI = "
          f"{ldi_at_weight(0.5):.1f}  (= ldi_half by construction)")
