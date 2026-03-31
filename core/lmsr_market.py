"""
lmsr_market.py
--------------
Liquidity-Sensitive Logarithmic Market Scoring Rule (LS-LMSR)
implementation for pre-clinical milestone prediction markets.

Reference:
    Othman, A., Sandholm, T., Pennock, D. M., & Reeves, D. M. (2010).
    A practical liquidity-sensitive automated market maker. ACM EC '10.
"""

import math
import json
import sys
from pathlib import Path
from typing import Dict, List

from scipy.optimize import brentq


class LSLMSRMarket:
    """
    Liquidity-Sensitive LMSR market for a single preclinical asset milestone.

    The LS-LMSR replaces the fixed liquidity parameter b of standard LMSR
    with a volume-adaptive parameter b(q) = alpha * sum(q_i), so market
    depth grows automatically with cumulative trading volume.

    Outcomes correspond to preclinical milestone stages:
        ["ind_submission", "phase1_success", "phase2_success", "approval"]

    Parameters
    ----------
    target : str
        Target identifier (e.g. "KRAS_G12C", "EGFR").
    q : list[float]
        Initial quantity vector over outcomes. Typically set by ABMM seeding.
    alpha : float
        Liquidity sensitivity parameter. Derived from confidence_score:
            alpha = 0.005 + (1 - confidence_score) * 0.075
        Higher alpha → market more responsive to early trades.
    """

    OUTCOMES = ["ind_submission", "phase1_success", "phase2_success", "approval"]

    def __init__(self, target: str, q: list[float], alpha: float = 0.5):
        self.target = target
        self.q = list(map(float, q))
        if len(self.q) != len(self.OUTCOMES):
            raise ValueError(
                f"Expected q length {len(self.OUTCOMES)} for outcomes "
                f"{self.OUTCOMES}, got {len(self.q)}"
            )
        self.alpha = float(alpha)

    # ── Core LS-LMSR primitives ──────────────────────────────────────────────

    @property
    def b(self) -> float:
        """
        Liquidity parameter b(q) = alpha * sum(q_i).

        Grows with cumulative volume — early markets are price-sensitive,
        mature markets develop institutional depth.
        """
        return max(self.alpha * sum(self.q), 1e-12)

    def cost(self) -> float:
        """
        Cost function C(q) = b(q) * log(sum(exp(q_i / b(q)))).

        The cost of the current quantity vector — used to compute the
        price of moving from one state to another.
        """
        b = self.b
        scaled = [qi / b for qi in self.q]
        m = max(scaled)
        return b * (m + math.log(sum(math.exp(s - m) for s in scaled)))

    def prices(self) -> Dict[str, float]:
        """
        Marginal prices p_i(q) = exp(q_i/b) / sum(exp(q_j/b)).

        Each marginal price equals the implied probability of the
        corresponding outcome under the current quantity vector.
        """
        b = self.b
        scaled = [qi / b for qi in self.q]
        m = max(scaled)
        exps = [math.exp(s - m) for s in scaled]
        total = sum(exps)
        return {
            outcome: e / total
            for outcome, e in zip(self.OUTCOMES, exps)
        }

    def prices_from_q(self, q: List[float]) -> List[float]:
        """Compute marginal prices for an arbitrary quantity vector."""
        b = max(self.alpha * sum(q), 1e-12)
        scaled = [qi / b for qi in q]
        m = max(scaled)
        exps = [math.exp(s - m) for s in scaled]
        total = sum(exps)
        return [e / total for e in exps]

    # ── Trading ──────────────────────────────────────────────────────────────

    def cost_to_move(self, outcome: str, target_prob: float) -> float:
        """
        Compute the cost of moving the price of `outcome` to `target_prob`.

        Uses binary search to find the quantity delta required, then
        returns the change in cost function value.

        Parameters
        ----------
        outcome : str
            The outcome to trade on.
        target_prob : float
            The desired marginal price (probability) after the trade.

        Returns
        -------
        float
            Cost of the trade (positive = buy, negative = sell).
        """
        if outcome not in self.OUTCOMES:
            raise ValueError(f"Unknown outcome: {outcome}")
        idx = self.OUTCOMES.index(outcome)

        cost_before = self.cost()

        def price_gap(delta: float) -> float:
            q_new = self.q.copy()
            q_new[idx] += delta
            return self.prices_from_q(q_new)[idx] - target_prob

        # Find the quantity delta that achieves target_prob
        try:
            delta = brentq(price_gap, -1e6, 1e6, xtol=1e-9)
        except ValueError:
            raise ValueError(
                f"Cannot move {outcome} to {target_prob:.4f} — "
                f"target probability may be out of range."
            )

        q_new = self.q.copy()
        q_new[idx] += delta

        # Temporarily apply to compute new cost
        q_orig = self.q
        self.q = q_new
        cost_after = self.cost()
        self.q = q_orig

        return cost_after - cost_before

    def trade(self, outcome: str, target_prob: float) -> dict:
        """
        Execute a trade moving `outcome` price to `target_prob`.

        Updates the internal quantity vector and returns a trade receipt.

        Returns
        -------
        dict with keys: outcome, old_prob, new_prob, cost, delta_q
        """
        if outcome not in self.OUTCOMES:
            raise ValueError(f"Unknown outcome: {outcome}")
        idx = self.OUTCOMES.index(outcome)

        old_prices = self.prices()
        old_prob = old_prices[outcome]

        def price_gap(delta: float) -> float:
            q_new = self.q.copy()
            q_new[idx] += delta
            return self.prices_from_q(q_new)[idx] - target_prob

        try:
            delta = brentq(price_gap, -1e6, 1e6, xtol=1e-9)
        except ValueError:
            raise ValueError(
                f"Cannot move {outcome} to {target_prob:.4f}."
            )

        cost_before = self.cost()
        self.q[idx] += delta
        cost_after = self.cost()

        new_prices = self.prices()

        return {
            "outcome": outcome,
            "old_prob": round(old_prob, 6),
            "new_prob": round(new_prices[outcome], 6),
            "cost": round(cost_after - cost_before, 6),
            "delta_q": round(delta, 6),
            "all_prices": {k: round(v, 6) for k, v in new_prices.items()},
        }

    # ── Utilities ────────────────────────────────────────────────────────────

    def state_dict(self) -> dict:
        """Serializable market state."""
        return {
            "target": self.target,
            "q": self.q,
            "alpha": self.alpha,
            "b": round(self.b, 6),
            "prices": {k: round(v, 6) for k, v in self.prices().items()},
        }

    def __repr__(self) -> str:
        p = self.prices()
        return (
            f"LSLMSRMarket(target={self.target}, alpha={self.alpha:.4f}, "
            f"b={self.b:.4f}, "
            f"ind={p['ind_submission']:.3f}, "
            f"ph1={p['phase1_success']:.3f})"
        )


# ── Alpha derivation ─────────────────────────────────────────────────────────

def alpha_from_confidence(confidence_score: float) -> float:
    """
    Derive LS-LMSR alpha from oracle-attested confidence score.

    alpha = 0.005 + (1 - confidence_score) * 0.075

    High confidence → low alpha → tight market, resistant to large swings.
    Low confidence  → high alpha → responsive to early expert signal.

    Parameters
    ----------
    confidence_score : float in [0, 1]
        Oracle-attested computational confidence (e.g. from docking + ADMET).
    """
    if not 0.0 <= confidence_score <= 1.0:
        raise ValueError("confidence_score must be in [0, 1]")
    return 0.005 + (1 - confidence_score) * 0.075


# ── CLI entrypoint ────────────────────────────────────────────────────────────

if __name__ == "__main__":
    # Quick demo: three oncology targets from live implementation
    targets = [
        {"target": "GNF-4471",    "confidence": 0.71, "lit_score": 0.68},
        {"target": "ARV-771",     "confidence": 0.64, "lit_score": 0.72},
        {"target": "PROTACore-12","confidence": 0.48, "lit_score": None},
    ]

    print("=" * 60)
    print("LS-LMSR Market Initialization Demo")
    print("=" * 60)

    for t in targets:
        alpha = alpha_from_confidence(t["confidence"])
        # Neutral initial quantities before ABMM seeding
        q_init = [100.0, 100.0, 100.0, 100.0]
        market = LSLMSRMarket(target=t["target"], q=q_init, alpha=alpha)
        print(f"\n{market}")
        print(f"  Initial prices: {market.prices()}")
