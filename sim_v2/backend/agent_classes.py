"""Shared agent class identification.

v2 uses non-overlapping integer ID ranges per agent class. This module
is the single source of truth for that mapping, used by both pnl.py
(for class-level rent aggregation) and streaming.py (for per-trade
class labels on the wire).
"""

from __future__ import annotations


# Range constants — change here if expanding agent population sizes
NAIVE_RANGE = (0, 100)
AGGREGATION_RANGE = (100, 200)
TAIL_RANGE = (200, 300)
CROSS_RANGE = (300, 400)
NOISE_RANGE = (400, 10_000)


def class_from_agent_id(agent_id) -> str:
    """Map integer agent_id to its class name string.

    Ranges:
      0-99    naive
      100-199 aggregation
      200-299 tail
      300-399 cross
      400+    noise
    """
    aid = int(agent_id)
    if NAIVE_RANGE[0] <= aid < NAIVE_RANGE[1]:
        return "naive"
    if AGGREGATION_RANGE[0] <= aid < AGGREGATION_RANGE[1]:
        return "aggregation"
    if TAIL_RANGE[0] <= aid < TAIL_RANGE[1]:
      return "tail"
    if CROSS_RANGE[0] <= aid < CROSS_RANGE[1]:
        return "cross"
    return "noise"


__all__ = ["class_from_agent_id"]
