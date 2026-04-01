"""
Binary Liquidity-Sensitive LMSR (Othman et al., 2013).

b(q) = α · (q_yes + q_no)
C(q) = b · log(exp(q_yes / b) + exp(q_no / b))
p_yes, p_no = softmax(q/b)
"""

from __future__ import annotations

import math

__all__ = [
    "lslmsr_price",
    "lslmsr_cost",
    "alpha_from_confidence",
]


def _b_ls(q_yes: float, q_no: float, alpha: float) -> float:
    return max(float(alpha) * (float(q_yes) + float(q_no)), 1e-12)


def lslmsr_cost(q_yes: float, q_no: float, alpha: float) -> float:
    """
    LS-LMSR cost C(q_yes, q_no) with liquidity b = α · (q_yes + q_no).
    Uses log-sum-exp for numerical stability.
    """
    b = _b_ls(q_yes, q_no, alpha)
    sy = float(q_yes) / b
    sn = float(q_no) / b
    m = max(sy, sn)
    return b * (m + math.log(math.exp(sy - m) + math.exp(sn - m)))


def lslmsr_price(q_yes: float, q_no: float, alpha: float) -> tuple[float, float]:
    """
    Marginal prices (implied probabilities) for YES and NO under LS-LMSR.
    Returns (p_yes, p_no); values sum to 1.
    """
    b = _b_ls(q_yes, q_no, alpha)
    sy = float(q_yes) / b
    sn = float(q_no) / b
    m = max(sy, sn)
    ey = math.exp(sy - m)
    en = math.exp(sn - m)
    t = ey + en
    return ey / t, en / t


def alpha_from_confidence(confidence_score: float) -> float:
    """
    Per-asset liquidity sensitivity from oracle confidence in [0, 1].

    α = 0.005 + (1 − confidence_score) × 0.075
    """
    c = float(confidence_score)
    c = min(max(c, 0.0), 1.0)
    return 0.005 + (1.0 - c) * 0.075
