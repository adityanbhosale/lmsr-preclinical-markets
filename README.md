# LS-LMSR Prediction Markets for Pre-Clinical Drug Discovery

A mechanism design research project applying the **Liquidity-Sensitive Logarithmic Market Scoring Rule (LS-LMSR)** to preclinical milestone contracts for AI-generated therapeutics, with an **Automated Bioactivity Market Maker (ABMM)** that solves the cold-start problem for thin credentialed markets with no retail liquidity.

**Live implementation:** [molecula-flame.vercel.app](https://molecula-flame.vercel.app)  
**Expert platform:** [platform-v2-umber.vercel.app/markets](https://platform-v2-umber.vercel.app/markets)

---

## The Problem

Generative drug discovery platforms now produce candidates faster than any evaluation infrastructure can validate them. Each molecule carries a probability distribution over downstream clinical success, but virtually none receives independent analytical infrastructure. Every internal triage decision relies on the same computational models that generated the candidates — there is no adversarial check, no calibration against external judgment, no market mechanism to surface systematic overconfidence.

|  | Value |
|--|--|
| Cost per IND-enabling program | $2–5M committed before independent probability assessment exists |
| AI-generated candidates without external evaluation | ~90% receive no systematic external signal before triage |
| Independent price signals for pre-IND assets | 0 |

---

## The Mechanism

### 1. Liquidity-Sensitive LMSR (Othman et al., 2013)

Standard LMSR uses a fixed liquidity parameter `b`. The LS-LMSR replaces this with a volume-adaptive parameter, so liquidity depth grows automatically with cumulative trading volume:

```
b(q)  = α · Σqᵢ                         # liquidity grows with volume
C(q)  = b(q) · log(Σ exp(qᵢ / b(q)))   # cost function
pᵢ(q) = ∂C/∂qᵢ                          # marginal price = implied probability
```

The `α` parameter is derived per-asset from oracle-attested confidence scores:

```
α = 0.005 + (1 − confidence_score) × 0.075
```

High-confidence molecules get low `α` (tight markets, resistant to large swings). Low-confidence molecules get high `α` (responsive to early expert signal, rewarding early conviction).

### 2. The Cold-Start Problem

Without an initial position, `q = (0, 0)` at market open. Every molecule opens at 50/50 regardless of computational signal:

```
p_yes = exp(0/b) / (exp(0/b) + exp(0/b)) = 0.5
```

This is uninformative. A molecule with `confidence_score = 0.71` opens identically to one with `score = 0.20`.

### 3. Automated Bioactivity Market Maker (ABMM)

The ABMM solves the cold-start problem by placing synthetic initial stakes derived from oracle-attested computational scores (binding affinity, selectivity, IC50, literature signal):

```
effective_confidence = score_comp × 0.6 + score_lit × 0.4
q_abmm_yes(0) = f(effective_confidence, α)
q_abmm_no(0)  = f(1 − effective_confidence, α)
```

The ABMM is not a real trader — it holds no economic position — but its quantities participate in the cost function and determine every subsequent trader's marginal prices.

### 4. ABMM Retreat Function

As credentialed expert volume accumulates, the ABMM retreats. The retreat function is parameterized as **exponential decay** rather than linear, for two structural reasons:

1. Early credentialed trades carry the highest informational value and should drive rapid initial retreat
2. Thin specialty markets may never reach sufficient volume to fully exit ABMM dominance under a threshold design — a residual floor is required for price stability

Retreat is weighted by trader calibration score (Brier-based) rather than raw volume:

```
ldi_calibrated(t) = Σ (volumeᵢ × brier_scoreᵢ)   # over credentialed trades up to t

w(t) = exp(−λ · ldi_calibrated(t))                 # ABMM weight, w(0)=1, w(∞)→0

λ = log(2) / ldi_half                              # decay rate parameter

q_abmm_yes(t) = w(t) · q_abmm_yes(0)              # effective ABMM quantities
q_abmm_no(t)  = w(t) · q_abmm_no(0)
```

This makes retreat responsive to signal quality, not just signal quantity.

---

## Open Theoretical Questions

### Incentive-Compatibility Under ABMM Dominance

A market scoring rule is incentive-compatible if a trader's optimal strategy is to report their true belief. Under standard LMSR this holds by construction. The ABMM introduces a distortion: its large initial synthetic position makes the market expensive to move early, potentially creating incentives for credentialed experts to **underreport** their true belief (partial trade is cheaper than full correction) or **strategically delay** (waiting for ABMM retreat reduces the cost of future trades).

This distortion is structurally analogous to the active block producer setting in transaction fee mechanism design — an algorithmic incumbent with a private valuation whose presence distorts incentive-compatibility for other participants. Bahrani, Garimidi, and Roughgarden (2023) prove that with an active block producer, no non-trivial mechanism can be simultaneously DSIC and BPIC. A parallel result may apply here.

The formal condition for ε-incentive-compatibility requires:

```
w(t) · q_abmm ≤ δ(ε, α, p*)

where:
  ε   = maximum tolerated belief distortion
  α   = per-market liquidity sensitivity
  p*  = expert's true belief
  δ   = tolerance bound (tightest when p* is far from p_abmm)
```

**Open question 1:** Does the exponential retreat function preserve approximate incentive-compatibility in the sense of Theorem 3.4 (Bahrani et al., 2023)?

**Open question 2:** What is the optimal λ as a closed-form function of (α, confidence_score, modality)?

**Open question 3:** Does calibration-weighted `ldi_calibrated` produce strictly better incentive-compatibility properties than volume-weighted `ldi` under all conditions?

**Open question 4:** Should the oracle-attested computational score be treated as a proper scoring rule input (cf. Roughgarden & Neyman, 2023) or as a Bayesian prior updated by a separate mechanism?

---

## Downstream DeFi Primitives

A working price oracle for pre-clinical assets enables three primitives that have not previously existed in drug discovery:

**Milestone-Gated Funding Pools** — capital routes automatically to the next milestone pool upon resolution, replacing the $2–5M IND commitment with a staged, market-priced capital release mechanism.

**Pre-Clinical Asset Derivatives** — once a continuous probability estimate exists on a molecule, options become possible. Floor contracts pay out if a candidate drops below a threshold IND probability — pipeline insurance priced by the market rather than actuarial tables.

**Computational Model Staking** — AI labs stake their models rather than specific molecules. Systematic outperformance of market priors earns calibration-weighted returns; underperformance dilutes stake. This creates a continuous public benchmark for generative drug discovery models — currently unavailable in any form.

---

## Repository Structure

```
lmsr-preclinical-markets/
├── core/
│   ├── lmsr_market.py        # LS-LMSR implementation
│   ├── lmsr_prior.py         # ABMM seeding + calibration-weighted retreat
│   └── retreat_functions.py  # Linear vs exponential retreat comparison
├── notebooks/
│   └── mechanism_demo.ipynb  # Interactive walkthrough with visualizations
├── api/
│   └── main.py               # FastAPI backend (credentials scrubbed)
├── docs/
│   └── mechanism.md          # Extended formal write-up
├── .env.example
├── requirements.txt
└── LICENSE
```

---

## Installation

```bash
git clone https://github.com/adityanb/lmsr-preclinical-markets
cd lmsr-preclinical-markets
pip install -r requirements.txt
cp .env.example .env  # fill in your credentials
```

To run the mechanism demo:

```bash
jupyter notebook notebooks/mechanism_demo.ipynb
```

To start the API:

```bash
uvicorn api.main:app --reload
```

---

## References

1. Othman, A., Sandholm, T., Pennock, D. M., & Reeves, D. M. (2010). A practical liquidity-sensitive automated market maker. *ACM EC '10*, 377–386.
2. Hanson, R. (2003). Combinatorial information market design. *Information Systems Frontiers*, 5(1), 107–119.
3. Bahrani, M., Garimidi, P., & Roughgarden, T. (2023). Transaction fee mechanism design with active block producers. *arXiv:2307.01686*.
4. Roughgarden, T., & Neyman, E. (2023). From proper scoring rules to max-min optimal forecast aggregation. *Operations Research*.
5. Roughgarden, T., & Schrijvers, O. (2017). Online prediction with selfish experts. *NeurIPS 2017*.
6. Brier, G. W. (1950). Verification of forecasts expressed in terms of probability. *Monthly Weather Review*, 78(1), 1–3.
7. Hay, M. et al. (2014). Clinical development success rates for investigational drugs. *Nature Biotechnology*, 32(1), 40–51.

---

## Author

**Aditya N. Bhosale**  
University of Pennsylvania (Biology & Healthcare Finance)  
[adityanb@sas.upenn.edu](mailto:adityanb@sas.upenn.edu)

*Working project — mechanism theory active, implementation ongoing. Feedback welcome.*
