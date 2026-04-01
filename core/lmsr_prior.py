"""
ABMM seeding and calibration-weighted retreat weight.
"""

from __future__ import annotations

import math

__all__ = [
    "abmm_seed",
    "abmm_weight",
]


def abmm_seed(
    confidence_score: float,
    alpha: float,
    seed_scale: float = 3.0,
) -> tuple[float, float]:
    """
    Synthetic YES/NO quantities for cold-start such that total outstanding
    is ``seed_scale`` and implied LS-LMSR price matches ``confidence_score``
    (target p_yes), assuming interior solution.

    With q_yes + q_no = S fixed, b = α·S is fixed, and
    q_yes = (S + b·logit(p)) / 2, q_no = (S − b·logit(p)) / 2.
    """
    p = float(confidence_score)
    p = min(max(p, 1e-9), 1.0 - 1e-9)
    S = max(float(seed_scale), 1e-12)
    alpha_f = float(alpha)
    b = alpha_f * S
    logit_p = math.log(p / (1.0 - p))
    q_yes = 0.5 * (S + b * logit_p)
    q_no = 0.5 * (S - b * logit_p)
    q_yes = max(q_yes, 0.0)
    q_no = max(q_no, 0.0)
    return q_yes, q_no


def abmm_weight(ldi_calibrated: float, ldi_half: float = 0.35) -> float:
    """
    ABMM influence weight after calibrated expert depth index LDI.

    w(LDI) = exp(−λ · LDI) with λ = log(2) / ldi_half so w(ldi_half) = 0.5.
    """
    ldi = max(float(ldi_calibrated), 0.0)
    half = max(float(ldi_half), 1e-12)
    lam = math.log(2.0) / half
    return math.exp(-lam * ldi)
