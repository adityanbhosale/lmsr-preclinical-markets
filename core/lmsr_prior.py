"""
lmsr_prior.py
-------------
Automated Bioactivity Market Maker (ABMM) — seeding and retreat.

The ABMM solves the cold-start problem for preclinical prediction markets:
without an initial position, a naive LMSR opens at 50/50 regardless of
oracle signal. The ABMM places synthetic initial stakes derived from
oracle-attested computational scores, then retreats as credentialed expert
volume accumulates.

Retreat function theory
-----------------------
The retreat function w(t) ∈ [0,1] scales the ABMM's position over time.
We parameterize as exponential decay (concave) rather than linear:

    ldi_calibrated(t) = Σ (volume_i × brier_score_i)
    w(t) = exp(−λ · ldi_calibrated(t))
    λ = log(2) / ldi_half

Concave retreat is correct for two structural reasons:
    1. Early credentialed trades carry the highest informational value
       and should drive rapid initial retreat.
    2. Thin specialty markets (e.g. HDAC6 PROTACs) may never accumulate
       sufficient volume to exit ABMM dominance under a threshold design —
       an asymptotic floor provides price stability.

Open theoretical question: does the exponential retreat function preserve
approximate incentive-compatibility in the sense of Theorem 3.4 of
Bahrani, Garimidi & Roughgarden (2023)? See README for full discussion.
"""

import math
from dataclasses import dataclass, field
from typing import Optional

from core.lmsr_market import LSLMSRMarket, alpha_from_confidence


# ── ABMM configuration ────────────────────────────────────────────────────────

SEED_PARTICIPATION = 100.0   # Base synthetic stake magnitude

# Fraction of total stake placed on YES (vs NO) at market open, given
# effective_confidence. Stake magnitude scales with SEED_PARTICIPATION.

OUTCOMES = ["ind_submission", "phase1_success", "phase2_success", "approval"]

# Milestone-specific confidence discount factors: later milestones are
# structurally harder, so ABMM prior is discounted progressively.
MILESTONE_DISCOUNT = {
    "ind_submission":   1.00,
    "phase1_success":   0.65,
    "phase2_success":   0.38,
    "approval":         0.12,
}


# ── Effective confidence ──────────────────────────────────────────────────────

def effective_confidence(
    score_comp: float,
    score_lit: Optional[float] = None,
) -> float:
    """
    Blend computational and literature scores into a single effective prior.

        effective_confidence = score_comp × 0.6 + score_lit × 0.4

    If score_lit is None, falls back to score_comp only.

    Parameters
    ----------
    score_comp : float in [0, 1]
        Computational confidence (docking, ADMET, generative model output).
    score_lit : float in [0, 1] or None
        Literature signal score (NLP pipeline or manual annotation).
    """
    if score_lit is None:
        return float(score_comp)
    return float(score_comp) * 0.6 + float(score_lit) * 0.4


# ── ABMM seeding ──────────────────────────────────────────────────────────────

def seed_quantities(
    eff_confidence: float,
    alpha: float,
    seed_magnitude: float = SEED_PARTICIPATION,
) -> list[float]:
    """
    Compute initial ABMM quantity vector from effective confidence.

    Quantities are distributed across the four outcome stages using
    milestone-specific discount factors, reflecting the structural
    difficulty of each preclinical gate.

    Parameters
    ----------
    eff_confidence : float in [0, 1]
    alpha : float
        LS-LMSR liquidity sensitivity parameter.
    seed_magnitude : float
        Total stake magnitude for ABMM position.

    Returns
    -------
    list[float]
        Quantity vector [q_ind, q_ph1, q_ph2, q_approval].
    """
    quantities = []
    for outcome in OUTCOMES:
        discount = MILESTONE_DISCOUNT[outcome]
        # YES stake scales with discounted effective confidence
        adjusted_conf = eff_confidence * discount
        q_yes = seed_magnitude * adjusted_conf
        # Base quantity includes both YES-weighted and NO-weighted components
        q = seed_magnitude * 0.5 + (q_yes - seed_magnitude * 0.5)
        quantities.append(max(q, 1.0))
    return quantities


def initialize_market(
    target: str,
    confidence_score: float,
    literature_score: Optional[float] = None,
) -> LSLMSRMarket:
    """
    Initialize an LS-LMSR market with ABMM seeding.

    Parameters
    ----------
    target : str
        Target identifier.
    confidence_score : float in [0, 1]
        Oracle-attested computational confidence score.
    literature_score : float or None
        Optional literature signal score.

    Returns
    -------
    LSLMSRMarket
        Seeded market ready for expert trading.
    """
    alpha = alpha_from_confidence(confidence_score)
    eff_conf = effective_confidence(confidence_score, literature_score)
    q_init = seed_quantities(eff_conf, alpha)
    return LSLMSRMarket(target=target, q=q_init, alpha=alpha)


# ── Retreat function ──────────────────────────────────────────────────────────

@dataclass
class ABMMState:
    """
    Tracks ABMM position and retreat over time for a single market.

    Attributes
    ----------
    q_abmm_init : list[float]
        Initial ABMM quantity vector at market open.
    ldi_calibrated : float
        Cumulative calibration-weighted expert volume.
    ldi_half : float
        Expected credentialed volume at which ABMM influence halves.
        λ = log(2) / ldi_half
    trades : list[dict]
        Record of credentialed trades that drove retreat.
    """
    q_abmm_init: list[float]
    ldi_half: float = 500.0
    ldi_calibrated: float = 0.0
    trades: list = field(default_factory=list)

    @property
    def lambda_(self) -> float:
        """Exponential decay rate λ = log(2) / ldi_half."""
        return math.log(2) / max(self.ldi_half, 1e-9)

    @property
    def weight(self) -> float:
        """
        Current ABMM weight w(t) = exp(−λ · ldi_calibrated(t)).

        w(0) = 1.0  → full ABMM dominance at market open
        w(∞) → 0.0  → ABMM fully retreated in mature market
        """
        return math.exp(-self.lambda_ * self.ldi_calibrated)

    @property
    def q_abmm_current(self) -> list[float]:
        """Effective ABMM quantities at current time: w(t) · q_abmm_init."""
        w = self.weight
        return [w * q for q in self.q_abmm_init]

    def record_trade(
        self,
        volume: float,
        brier_score: float,
        credential_tier: str = "CREDENTIALED",
    ) -> None:
        """
        Record a credentialed expert trade and update calibrated LDI.

        Only CREDENTIALED and EXPERT trades drive ABMM retreat.

        Parameters
        ----------
        volume : float
            Trade volume in stake units.
        brier_score : float in [0, 1]
            Trader's rolling Brier score (lower = better calibrated).
            Converted to calibration weight: 1 - brier_score.
        credential_tier : str
            One of: RETAIL, VERIFIED, CREDENTIALED, EXPERT.
        """
        if credential_tier not in ("CREDENTIALED", "EXPERT"):
            return  # Retail and Verified trades do not drive retreat

        calibration_weight = 1.0 - min(max(brier_score, 0.0), 1.0)
        contribution = volume * calibration_weight
        self.ldi_calibrated += contribution

        self.trades.append({
            "volume": volume,
            "brier_score": brier_score,
            "calibration_weight": round(calibration_weight, 4),
            "contribution": round(contribution, 4),
            "ldi_after": round(self.ldi_calibrated, 4),
            "weight_after": round(self.weight, 4),
        })

    def influence_pct(self) -> float:
        """ABMM influence as a percentage (0–100)."""
        return round(self.weight * 100, 2)

    def summary(self) -> dict:
        return {
            "ldi_calibrated": round(self.ldi_calibrated, 4),
            "ldi_half": self.ldi_half,
            "lambda": round(self.lambda_, 6),
            "weight": round(self.weight, 4),
            "abmm_influence_pct": self.influence_pct(),
            "q_abmm_current": [round(q, 4) for q in self.q_abmm_current],
            "n_trades": len(self.trades),
        }


# ── Retreat function comparison ───────────────────────────────────────────────

def linear_retreat(ldi: float, threshold: float = 1000.0) -> float:
    """Linear retreat: w = max(0, 1 - ldi/threshold)."""
    return max(0.0, 1.0 - ldi / threshold)


def exponential_retreat(ldi: float, ldi_half: float = 500.0) -> float:
    """Exponential retreat: w = exp(-lambda * ldi)."""
    lambda_ = math.log(2) / max(ldi_half, 1e-9)
    return math.exp(-lambda_ * ldi)


def compare_retreat_functions(
    ldi_values: list[float],
    threshold: float = 1000.0,
    ldi_half: float = 500.0,
) -> list[dict]:
    """
    Compare linear vs exponential retreat across a range of LDI values.

    Returns a list of dicts for plotting or analysis.
    """
    return [
        {
            "ldi": ldi,
            "linear": round(linear_retreat(ldi, threshold), 4),
            "exponential": round(exponential_retreat(ldi, ldi_half), 4),
        }
        for ldi in ldi_values
    ]


# ── Demo ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 60)
    print("ABMM Seeding & Retreat Demo")
    print("=" * 60)

    molecules = [
        {"target": "GNF-4471",     "confidence": 0.71, "lit": 0.68},
        {"target": "ARV-771",      "confidence": 0.64, "lit": 0.72},
        {"target": "PROTACore-12", "confidence": 0.48, "lit": None},
    ]

    for mol in molecules:
        market = initialize_market(
            target=mol["target"],
            confidence_score=mol["confidence"],
            literature_score=mol["lit"],
        )
        eff = effective_confidence(mol["confidence"], mol["lit"])
        abmm = ABMMState(
            q_abmm_init=market.q.copy(),
            ldi_half=500.0,
        )

        print(f"\n{mol['target']}")
        print(f"  effective_confidence = {eff:.3f}")
        print(f"  alpha = {market.alpha:.4f}")
        print(f"  b = {market.b:.4f}")
        print(f"  opening prices:")
        for outcome, prob in market.prices().items():
            print(f"    {outcome:25s}: {prob:.3f}")
        print(f"  ABMM influence: {abmm.influence_pct():.1f}%")

        # Simulate three credentialed trades
        print(f"  Simulating 3 credentialed trades...")
        for i, (vol, brier) in enumerate([(50, 0.25), (80, 0.18), (60, 0.31)]):
            abmm.record_trade(volume=vol, brier_score=brier)
            print(f"    Trade {i+1}: vol={vol}, brier={brier} → "
                  f"ABMM influence={abmm.influence_pct():.1f}%")
