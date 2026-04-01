"""
Deterministic ABMM retreat curves vs. liquidity depth index (LDI).
"""

from __future__ import annotations

import math

__all__ = [
    "exponential_retreat",
    "linear_retreat",
    "convex_retreat",
    "compare_retreat_functions",
]


def exponential_retreat(ldi: float, decay_rate: float = 3.0) -> float:
    """Weight exp(−decay_rate · LDI). At LDI=0 weight is 1; decays exponentially."""
    return math.exp(-float(decay_rate) * max(float(ldi), 0.0))


def linear_retreat(ldi: float) -> float:
    """Weight max(0, 1 − LDI). Interpret LDI as normalized expert depth in [0, 1] for full decay."""
    return max(0.0, 1.0 - float(ldi))


def convex_retreat(ldi: float, power: float = 0.5) -> float:
    """
    Weight max(0, 1 − LDI^power) for LDI ≥ 0.

    With power < 1, LDI^power is concave in LDI, giving a slower initial drop
    than linear for small LDI (shape depends on normalization).
    """
    ldi = max(float(ldi), 0.0)
    k = float(power)
    if k <= 0.0:
        raise ValueError("power must be positive")
    return max(0.0, 1.0 - ldi**k)


def compare_retreat_functions() -> None:
    """Print a summary table comparing retreat shapes at sample LDI values."""
    header = f"{'LDI':>8}  {'exp(−3·LDI)':>14}  {'linear':>10}  {'convex':>10}"
    print(header)
    print("-" * len(header))
    for ldi in (0.0, 0.1, 0.25, 0.5, 0.75, 1.0, 1.5, 2.0):
        ex = exponential_retreat(ldi, decay_rate=3.0)
        lin = linear_retreat(ldi)
        conv = convex_retreat(ldi, power=0.5)
        print(f"{ldi:8.2f}  {ex:14.6f}  {lin:10.6f}  {conv:10.6f}")


if __name__ == "__main__":
    compare_retreat_functions()
