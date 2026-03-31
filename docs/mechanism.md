# Mechanism: Formal Notes

Extended notes on the LS-LMSR + ABMM architecture.
For the accessible version see the main README.

---

## 1. LS-LMSR Formal Properties

The cost function C(q) = b(q) · log(Σ exp(qᵢ/b(q))) is:

- **Convex** in q — marginal cost of moving the market increases with position size
- **Differentiable** everywhere — marginal prices always well-defined
- **Volume-adaptive** — b(q) = α·Σqᵢ grows with total stake, so early trades have high price impact and late trades have low impact relative to total volume

The marginal price property (pᵢ = ∂C/∂qᵢ) means prices integrate to 1 and each equals the log-odds-weighted implied probability of outcome i.

## 2. ABMM as Liquidity Provider

The ABMM functions as a liquidity provider in the AMM sense: it holds positions and faces adverse selection when credentialed experts with better information trade against it.

This maps directly onto the Loss-Versus-Rebalancing (LVR) framework of Milionis, Moallemi, Roughgarden & Zhang (2022). The ABMM's "loss" as expert signal accumulates is not a flaw — it is the intended mechanism by which information transfers from the oracle layer to the market price. The retreat function controls the rate of this transfer.

## 3. Incentive-Compatibility: The Formal Problem

Let p* denote a credentialed expert's true belief and p_abmm the current ABMM-seeded market price. The cost of moving the market from p_abmm to p* is:

    cost(p_abmm → p*) = C(q_after) - C(q_before)

Because C is evaluated at high total volume (due to ABMM's large initial q), the cost of full truthful correction is elevated. This creates two strategic distortions:

**Underreporting:** Expert moves market partway toward p* but stops before full correction because marginal cost exceeds expected profit. Market reflects belief between p_abmm and p*, not p*.

**Strategic delay:** Expert places small initial position, waits for other experts to accumulate LDI and drive ABMM retreat, then trades more aggressively at lower cost. Free-rider problem.

Both distortions are structurally analogous to the active block producer problem in Bahrani, Garimidi & Roughgarden (2023), Theorem 3.1: with an algorithmic incumbent holding a large initial position with private valuation, no non-trivial mechanism can be simultaneously DSIC and BPIC.

The ε-IC condition requires:

    w(t) · q_abmm ≤ δ(ε, α, p*)

where δ is tightest when |p* - p_abmm| is large — precisely when expert correction is most valuable. The exponential retreat function addresses this by reducing w(t) rapidly in the early high-disagreement phase.

**Open question:** Whether exponential retreat satisfies Theorem 3.4 of Bahrani et al. (the approximate DSIC result for the BPIC tipless mechanism) remains unproven. The calibration-weighting extension (using ldi_calibrated rather than raw ldi) aligns incentives with signal quality but requires a formal treatment.

## 4. Oracle Layer Architecture

Resolution currently relies on admin attestation. The correct long-run architecture is:

1. **Quorum attestation** — a panel of credentialed experts (tier ≥ CREDENTIALED) must collectively attest to milestone outcomes. Quorum threshold is modality-specific.

2. **Stake-slashing for bad attestation** — attestors who report outcomes inconsistent with the eventual ground truth have their stake slashed proportional to the error.

3. **Credential-gated position staking** — on-chain, only wallets holding a valid soulbound credential token can submit positions. This prevents speculation from diluting the expert signal.

The soulbound token / composability tradeoff is the primary engineering constraint: soulbound tokens enforce credential gating but break DeFi composability (milestone-gated funding pools require freely transferable position tokens). Semi-soulbound tokens transferable only to whitelisted protocol contracts are the candidate resolution.

## 5. References

See README for full reference list.
