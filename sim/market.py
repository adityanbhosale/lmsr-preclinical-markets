"""
LS-LMSR market — pure-Python port of contracts/src/LSLMSR.sol.

Binary YES/NO prediction market with liquidity-sensitive LMSR pricing.
b(q) = alpha * (qYes + qNo)
C(q) = b * ln(exp(qYes/b) + exp(qNo/b))
priceYes = exp(qYes/b) / (exp(qYes/b) + exp(qNo/b))

ABMM retreat function is added as a Python-only extension for H1 stress testing.
The Solidity reference does not implement retreat; parity is validated for the
LS-LMSR core only (retreat_factor = 1.0 always for parity tests).
"""

from __future__ import annotations
from dataclasses import dataclass, field
import numpy as np


@dataclass
class LSLMSRConfig:
    """Liquidity-sensitive LMSR parameters."""
    alpha: float
    q_abmm_yes: float
    q_abmm_no: float

    def __post_init__(self):
        assert self.alpha > 0, "alpha must be positive"
        assert self.q_abmm_yes > 0, "qAbmmYes must be positive"
        assert self.q_abmm_no > 0, "qAbmmNo must be positive"


@dataclass
class ABMMConfig:
    """
    ABMM retreat parameters. Python-only extension; not in Solidity.
    Retreat is OFF by default (multiplier = 1.0) for parity testing.
    """
    enabled: bool = False
    tau: float = 1.0
    threshold: float = 100.0
    decay_shape: str = "exponential"  # "exponential" | "polynomial" | "step"

    def __post_init__(self):
        assert self.decay_shape in ("exponential", "polynomial", "step")


@dataclass
class LSLMSRMarket:
    """
    Binary YES/NO LS-LMSR market.
    q_yes, q_no track total shares outstanding (ABMM seed + human trades).
    """
    config: LSLMSRConfig
    abmm: ABMMConfig = field(default_factory=ABMMConfig)
    q_yes: float = field(init=False)
    q_no: float = field(init=False)
    human_volume: float = 0.0   # cumulative human trade volume (for retreat)

    def __post_init__(self):
        self.q_yes = self.config.q_abmm_yes
        self.q_no = self.config.q_abmm_no

    # ---------- core LS-LMSR (matches Solidity exactly) ----------

    def b(self) -> float:
        """Liquidity parameter. b = alpha * (qYes + qNo)."""
        # apply retreat if enabled (Python extension, off for parity)
        retreat = self._retreat_factor()
        # retreat shrinks the ABMM contribution to total inventory
        abmm_q = (self.config.q_abmm_yes + self.config.q_abmm_no) * retreat
        human_q_yes = self.q_yes - self.config.q_abmm_yes
        human_q_no = self.q_no - self.config.q_abmm_no
        return self.config.alpha * (abmm_q + human_q_yes + human_q_no)

    def cost(self, q_yes: float, q_no: float) -> float:
        """C(q) = b * ln(exp(qYes/b) + exp(qNo/b)) with numerical stability."""
        b = self.b_at(q_yes, q_no)
        scaled_yes = q_yes / b
        scaled_no = q_no / b
        m = max(scaled_yes, scaled_no)
        return b * (m + np.log(np.exp(scaled_yes - m) + np.exp(scaled_no - m)))

    def b_at(self, q_yes: float, q_no: float) -> float:
        """b evaluated at a hypothetical (qYes, qNo). For internal cost calls."""
        retreat = self._retreat_factor()
        abmm_q = (self.config.q_abmm_yes + self.config.q_abmm_no) * retreat
        human_q_yes = q_yes - self.config.q_abmm_yes
        human_q_no = q_no - self.config.q_abmm_no
        return self.config.alpha * (abmm_q + human_q_yes + human_q_no)

    def price_yes(self) -> float:
        """Marginal price of a YES share (= probability of YES)."""
        b = self.b()
        scaled_yes = self.q_yes / b
        scaled_no = self.q_no / b
        m = max(scaled_yes, scaled_no)
        ey = np.exp(scaled_yes - m)
        en = np.exp(scaled_no - m)
        return ey / (ey + en)

    def price_no(self) -> float:
        return 1.0 - self.price_yes()

    # ---------- trading ----------

    def cost_of_trade(self, is_yes: bool, shares: float) -> float:
        """Cost in USDC-equivalent units to buy `shares` of YES or NO."""
        cost_before = self.cost(self.q_yes, self.q_no)
        new_q_yes = self.q_yes + shares if is_yes else self.q_yes
        new_q_no = self.q_no + shares if not is_yes else self.q_no
        cost_after = self.cost(new_q_yes, new_q_no)
        return cost_after - cost_before

    def execute_trade(self, is_yes: bool, shares: float) -> float:
        """Execute trade. Returns cost paid by trader."""
        cost = self.cost_of_trade(is_yes, shares)
        if is_yes:
            self.q_yes += shares
        else:
            self.q_no += shares
        self.human_volume += shares
        return cost

    # ---------- ABMM retreat (Python-only) ----------

    def _retreat_factor(self) -> float:
        if not self.abmm.enabled:
            return 1.0
        if self.human_volume <= self.abmm.threshold:
            return 1.0
        excess = self.human_volume - self.abmm.threshold
        if self.abmm.decay_shape == "exponential":
            return float(np.exp(-self.abmm.tau * excess / self.abmm.threshold))
        elif self.abmm.decay_shape == "polynomial":
            return float(1.0 / (1.0 + self.abmm.tau * (excess / self.abmm.threshold)))
        elif self.abmm.decay_shape == "step":
            return 0.0
        else:
            raise ValueError(f"unknown decay_shape: {self.abmm.decay_shape}")

    def snapshot(self) -> dict:
        return {
            "q_yes": self.q_yes,
            "q_no": self.q_no,
            "price_yes": self.price_yes(),
            "price_no": self.price_no(),
            "b": self.b(),
            "human_volume": self.human_volume,
            "retreat_factor": self._retreat_factor(),
        }