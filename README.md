# On-Chain Liquidity and Price Discovery for Tokenized Life Sciences Milestone Payment Rights

A two-layer system for creating liquid secondary markets in contractual biotech milestone payment rights, combining a **Delaware SPV tokenized under Regulation D 506(c)** with a **Liquidity-Sensitive LMSR prediction market** providing continuous price discovery between clinical catalysts.

**Live implementation:** [molecula-flame.vercel.app](https://molecula-flame.vercel.app)
**Expert platform:** [platform-v2-umber.vercel.app/markets](https://platform-v2-umber.vercel.app/markets)
**Legal architecture:** [Tokenized RWA Legal Whitepaper](docs/legal_whitepaper.pdf)

---

## The Problem

Clinical-stage private biotechs routinely hold contractual rights to substantial milestone payments — cash flows due from pharma partners upon specific clinical events (FDA approval, Phase II success, regulatory filing). A single milestone payment tied to a Phase II completion can represent $20–100M of contingent value. These rights are **economically significant, legally well-defined, and structurally illiquid**.

The existing market is bilateral and opaque. A biotech seeking to monetize a milestone payment before realization negotiates a one-off sale or loan with a royalty fund (Royalty Pharma, HealthCare Royalty Partners, XOMA) or a specialty lender. Valuation is determined by the counterparty's internal model. There is no secondary market, no continuous price discovery, and no way for the biotech to know whether the quoted price reflects the milestone's true risk-adjusted value or the counterparty's bargaining leverage.

|  | Current State |
| --- | --- |
| Clinical-stage private biotechs with out-licensed milestone payments | ~500–800 companies globally |
| Secondary market for individual milestone payment rights | None |
| Continuous price signal on milestone probability between catalysts | None |
| Counterparty set for non-dilutive milestone monetization | <20 specialty funds |

The result is a structural mispricing of the asset class. Biotechs either accept unfavorable bilateral terms or forgo non-dilutive capital entirely. Royalty funds absorb the illiquidity premium. No institutional price discovery mechanism exists between the deal and the milestone event itself.

---

## The Two-Layer Architecture

This model resolves the illiquidity problem by separating the **legal ownership layer** from the **price discovery layer** and allowing each to operate under the regulatory regime best suited to it. The full legal architecture is documented in the [whitepaper](docs/legal_whitepaper.pdf); this section summarizes the design.

```
┌─────────────────────────────────────────────────────────────────┐
│                   LAYER 2: PREDICTION MARKET                    │
│                                                                 │
│   LS-LMSR AMM on Base (Coinbase L2)                             │
│   Outcome shares (YES/NO) referencing milestone event           │
│   USDC settlement, continuous price discovery                   │
│   Candidate jurisdiction: CFTC event contract                   │
└───────────────────────┬─────────────────────────────────────────┘
                        │ references
                        ▼
┌─────────────────────────────────────────────────────────────────┐
│                   LAYER 1: TOKENIZED SPV                        │
│                                                                 │
│   Delaware LLC holding milestone payment right                  │
│   ERC-3643 (T-REX) compliance token on Ethereum mainnet         │
│   Regulation D 506(c) — accredited investors only               │
│   Token as authoritative legal record of ownership              │
└─────────────────────────────────────────────────────────────────┘
```

**Layer 1** is the security. Token holders own membership interests in the SPV, which in turn holds the contractual milestone payment right. The token is the legal record of ownership, not a digital representation of an off-chain claim — the SPV operating agreement designates the on-chain ERC-3643 register as the definitive cap table.

**Layer 2** is the price discovery mechanism. Outcome shares are binary instruments that pay out based on the public milestone event, not on the SPV's economic performance. They are structured as CFTC-style event contracts rather than securities, enabling continuous trading without triggering Reg D transfer restrictions on the underlying SPV token.

The architecture is fully on-chain (**Path B**): compliance is enforced at the token contract level via ERC-3643, not through off-chain middleware. This commits the system to an institutional-grade infrastructure stack (Ethereum mainnet + Base + USDC + Circle CCTP) and leverages the same ERC-3643 standard used by Securitize for BlackRock's BUIDL fund and KKR's tokenized private equity offerings.

The only architectural sub-decision left open is **soulbound vs. composable outcome shares** — whether Layer 2 tokens should be freely transferable (maximizing DeFi composability but risking characterization as an unlawful secondary market in the restricted SPV interest) or soulbound (non-transferable, resolving the Reg D resale question cleanly but eliminating composability). The resolution depends on the SEC vs. CFTC jurisdictional determination discussed in the whitepaper's Section 5.

---

## Layer 1: Tokenized SPV (Security Layer)

The milestone payment right is held by a Delaware limited liability company established as a special purpose vehicle. Token holders own membership interests in the SPV; the SPV holds the contractual right to receive payment from the pharma counterparty upon achievement of the specified clinical milestone.

### Regulatory Structure

The SPV token is a security under Howey. The offering uses **Regulation D Rule 506(c)**, which permits general solicitation of accredited investors and is the near-term structure used by Securitize and comparable institutional tokenization platforms. A parallel Regulation S track is available for non-US participants. Full analysis of the exemption decision and the alternatives (Reg A+, Reg S standalone) is in Section 2 of the whitepaper.

### ERC-3643 (T-REX) Compliance

The SPV membership interest token is implemented using the ERC-3643 standard, which enforces transfer restrictions on-chain through four components:

- **Identity Registry** — maps wallet addresses to verified identity claims (accredited status, jurisdiction, sanctions screening)
- **Compliance Module** — smart contract that checks the identity registry on every transfer and enforces Reg D lock-up periods
- **Token Contract** — the ERC-3643 asset token with transfer hooks calling the compliance module
- **Claims Issuer** — the trusted entity signing identity attestations (SPV administrator or third-party KYC provider)

This architecture satisfies Reg D transfer restrictions without requiring off-chain compliance middleware for every transaction.

### Chain Choice

Layer 1 lives on **Ethereum mainnet** for institutional trust, ERC-3643 ecosystem maturity, and regulatory recognition. Settlement of the underlying milestone payment — when the pharma counterparty pays the SPV upon milestone achievement — is recorded on Ethereum mainnet as a state update to the SPV token contract.

---

## Layer 2: LS-LMSR Prediction Market (Price Discovery Layer)

Between clinical catalysts, the SPV token has no continuous price signal. The prediction market layer solves this by running outcome shares on the milestone event as a separate market on Base, with the price of outcome shares providing a continuous implied probability estimate for the underlying milestone.

### 1. Liquidity-Sensitive LMSR (Othman et al., 2013)

Standard LMSR uses a fixed liquidity parameter `b`. The LS-LMSR replaces this with a volume-adaptive parameter, so liquidity depth grows automatically with cumulative trading volume:

```
b(q)  = α · Σqᵢ                         # liquidity grows with volume
C(q)  = b(q) · log(Σ exp(qᵢ / b(q)))    # cost function
pᵢ(q) = ∂C/∂qᵢ                          # marginal price = implied probability
```

The `α` parameter is derived per-market from a computational prior on milestone probability:

```
α = 0.005 + (1 − prior_confidence) × 0.075
```

High-confidence markets get low `α` (tight markets, resistant to early swings). Low-confidence markets get high `α` (responsive to expert signal, rewarding early conviction).

### 2. The Cold-Start Problem

Without an initial position, `q = (0, 0)` at market open and every market opens at 50/50 regardless of computational signal. A milestone with a well-modeled 75% probability would open identically to one with a 15% probability — uninformative and inviting adverse selection against the first credentialed trader.

### 3. Automated Bioactivity Market Maker (ABMM)

The ABMM solves the cold-start problem by placing synthetic initial stakes derived from an oracle-attested probability model. In the current framing, the prior is a composite signal incorporating the counterparty's proprietary preclinical data, published clinical literature, analyst models where available, and historical base rates for the therapeutic area:

```
effective_prior = p_model · 0.5 + p_literature · 0.3 + p_base_rate · 0.2
q_abmm_yes(0)  = f(effective_prior, α)
q_abmm_no(0)   = f(1 − effective_prior, α)
```

The ABMM is not a real trader — it holds no economic position — but its quantities participate in the cost function and determine every subsequent trader's marginal prices.

The use of counterparty proprietary data in the prior creates a material non-public information (MNPI) exposure addressed in the whitepaper's Section 6. The near-term deployment is restricted to private biotech counterparties, where Rule 10b-5 does not apply; public company onboarding requires a purpose-built information barrier architecture that is an open design question.

### 4. ABMM Retreat Function

As credentialed expert volume accumulates, the ABMM retreats. The retreat function is parameterized as **exponential decay** rather than linear, for two structural reasons:

1. Early credentialed trades carry the highest informational value and should drive rapid initial retreat
2. Thin markets may never reach sufficient volume to fully exit ABMM dominance under a threshold design — a residual floor is required for price stability

Retreat is weighted by trader calibration score (Brier-based) rather than raw volume:

```
ldi_calibrated(t) = Σ (volumeᵢ × brier_scoreᵢ)   # over credentialed trades up to t

w(t) = exp(−λ · ldi_calibrated(t))                # ABMM weight, w(0)=1, w(∞)→0

λ = log(2) / ldi_half                             # decay rate parameter

q_abmm_yes(t) = w(t) · q_abmm_yes(0)             # effective ABMM quantities
q_abmm_no(t)  = w(t) · q_abmm_no(0)
```

This makes retreat responsive to signal quality, not just signal quantity.

### 5. Settlement and Cross-Chain Flow

Layer 2 lives on **Base** for low transaction costs and USDC-native infrastructure. When a prediction market resolves, USDC distributions to outcome share holders execute natively on Base. When the underlying SPV milestone payment is settled, the legal finality is recorded on Ethereum mainnet via the ERC-3643 token contract; USDC moves cross-chain via **Circle's Cross-Chain Transfer Protocol (CCTP)**.

---

## Open Theoretical Questions

### Incentive-Compatibility Under ABMM Dominance

A market scoring rule is incentive-compatible if a trader's optimal strategy is to report their true belief. Under standard LMSR this holds by construction. The ABMM introduces a distortion: its large initial synthetic position makes the market expensive to move early, potentially creating incentives for credentialed experts to **underreport** their true belief (partial trade is cheaper than full correction) or **strategically delay** (waiting for ABMM retreat reduces the cost of future trades).

This distortion is structurally analogous to the active block producer setting in transaction fee mechanism design — an algorithmic incumbent with a private valuation whose presence distorts incentive-compatibility for other participants. Bahrani, Garimidi, and Roughgarden (2023) prove that with an active block producer, no non-trivial mechanism can be simultaneously DSIC and BPIC. A parallel result may apply here, though the ABMM's non-strategic nature (deterministic, publicly known retreat schedule, no preferences) suggests the DSIC-only version of the problem is the correct formulation.

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

**Open question 2:** What is the optimal λ as a closed-form function of (α, prior_confidence, modality)?

**Open question 3:** Does calibration-weighted `ldi_calibrated` produce strictly better incentive-compatibility properties than volume-weighted `ldi` under all conditions?

**Open question 4:** Should the oracle-attested probability model be treated as a proper scoring rule input (cf. Roughgarden & Neyman, 2023) or as a Bayesian prior updated by a separate mechanism?

### Legal and Architectural Open Questions

Summarized from the whitepaper's Section 7:

**(a) SEC vs. CFTC jurisdiction over outcome shares.** Whether binary outcome shares referencing a tokenized security fall under SEC or CFTC jurisdiction, and whether the two-layer structure is legally respected or collapsed by regulators into a single securities offering. This is the most significant unresolved legal question in the architecture.

**(b) Soulbound vs. composability.** Whether Layer 2 outcome shares should be freely transferable (maximizing composability but risking characterization as an unlawful secondary market in the restricted SPV interest) or soulbound (resolving the Reg D resale question at the cost of DeFi composability). Resolution is contingent on (a).

**(c) Oracle resolution and legal finality.** Which oracle architecture provides legally recognized settlement trigger authority, and how dispute resolution integrates with the SPV's contractual payment obligation. Existing solutions (UMA optimistic oracle, Pyth price aggregation) are not directly applicable to bespoke clinical event data; a purpose-built architecture with credentialed DSMB attestation and stake-slashing for bad attestation is the candidate design.

**(d) Rule 144 resale and the prediction market layer.** Whether continuous trading of outcome shares during the Reg D lock-up period constitutes an unlawful secondary market in the restricted SPV interest.

**(e) SPV assignment without counterparty consent.** Whether the pharma counterparty's assignment of a milestone payment right to the SPV requires regulatory consent (FDA, IRB) given that the underlying right is tied to a regulated clinical process.

**Open question 5:** Given the model's docus on developing a tokenized RWA with a overlayed Prediction Market Layer where the underlying is tokenized as a security, what are the key next developemental steps:

**Phase 1:  **

1. Legal Foundation – i.e. what's being tokenized?
          * Royalty Stream: % of future revenues (essentially a revenue participation agreement)
          * Milestone Payment Rights: contractual right to receive payment upon a specific clinical event             (binary, time-bounded, directly maps to prediction market structure)
          * Developement-stage equity – ownership stake in drug candidate or biotech entity. Most
            complex, closest to traditional VC
          * IP license right – tokenized share of licensing revenue from a patent or compound

      Legal Questions:
        1. DO the outcome shares (YES/NO tokens) constitute securities under the Securities Act or
        derivatives under the CEA – and what's the enforcement risk of getting this wrong?
        2. Which exemption is most viable for the underlying asset token – Reg D 506(c) accredited  
        investors, general solicitation allowed) vs. Reg S (non-US persons, sidesteps SEC) vs. Reg A+
        (broader base, slower)
        3. Can the prediction market layer and the RWA layer be legally separated such that information
        market participants are not deemed to hold the underlying security?

2. Legal Wrapper – SPV – Delaware LLC or LP created specifically to hold the underlying asset. Token holders have membership interests in the SPV. This is how Robinhood structured its OpenAI/SpaceX tokenized equity exposure and how most institutional tokenization platforms operate (Securitize, Centrifuge).

**Phase 2:  **

3. ERC-3643 implementation (T-REX) for the underlying asset token (production standard for permissioned security tokens).
   * Identity Registry – maps wallet addresses to verified identity claims (accreditation status,
     jurisdiction, sanctions screening). Integrates with an off-chain KYC provider (Persona, Jumio,
     or Synaps, which is crypto-native).
   * Compliance Module – smart contract which enforces transfer rules. Checks identiy registry on
     every transfer. Enforces lock-up periods, jurisdiction restrictions, maximum holder counts (Reg D
     has a 2,000 investor limit).
   * Token Contract – ERC-3643 asset token itself, with transfer hooks that call the compliance
     module.
   * Claims Issuer – the trusted entity that signs identity claims (i.e. SPV admin or a third-party
     KYC provider).

Our LS-LMSR AMM woould essentially sit on top of this layer, interacting with the ERC-3643 token but maintaining its own contract architecture.

4. Separate the information market layer cleanly – ensure that YES/NO outcome shares are not the underlying ERC-3643 security token – they're a derivative instrument that references it.
   * keeps outcome shares outside securities law
   * allows non-KYC'd participants to trade the information market while only KYC'd participants hold the      underlying asset
   * preserves composability – outcome shares can potentially move freely while the underlying asset           remains permissioned
  

---
## Testnet Reference Implementation

A working Solidity implementation of the Layer 2 LS-LMSR automated market
maker is deployed and live on Base Sepolia at
[`0x4f74e2AFDfc46dd3C072EAC5172eC87BE1F8d29B`](https://sepolia.basescan.org/address/0x4f74e2AFDfc46dd3C072EAC5172eC87BE1F8d29B).
The contract implements the LS-LMSR cost function, marginal pricing, and
trading mechanics described in the whitepaper, using PRBMath's UD60x18
fixed-point type for `exp`/`ln` operations. 14 unit tests pass, covering
core math, input-domain boundaries, and state/access control
(`contracts/test/LSLMSR.t.sol`).

See [`docs/testnet-implementation.md`](docs/testnet-implementation.md) for
deployment coordinates, architecture notes, test coverage detail, and a
walkthrough of implementation decisions and roadblocks.

---

## Downstream Product Implications

A working two-layer market for tokenized milestone payment rights enables three institutional products that do not currently exist in biotech finance:

**Secondary Liquidity for Milestone Payment Rights** — the primary product. Private biotechs gain access to continuous price discovery on their contractual milestone payments and a broader counterparty set than the current <20-fund specialty market. Royalty funds gain access to a liquid secondary market where they can dynamically rebalance exposure rather than holding to realization.

**Target-Class Indices** — once multiple milestone markets exist within a therapeutic area, a confidence-weighted index `I_target(t) = Σ wᵢ(t) · pᵢ(t)` produces a continuous price signal for the target class as a whole. This is the product answer to the thin-market problem: even if individual milestones are sparsely traded, the aggregate index is liquid enough to support structured products, hedging, and institutional benchmarking.

**Computational Model Staking** — AI drug discovery companies (Recursion, Isomorphic Labs, Insilico) stake prediction batches against market priors rather than specific molecules. Systematic outperformance earns calibration-weighted returns; underperformance dilutes stake. This creates a continuous public benchmark for generative drug discovery models, which is currently unavailable in any form.

---

## Repository Structure

```
lmsr-preclinical-markets/
├── core/
│   ├── lmsr_market.py              # LS-LMSR implementation
│   ├── lmsr_prior.py               # ABMM seeding + calibration-weighted retreat
│   └── retreat_functions.py        # Linear vs exponential retreat comparison
├── notebooks/
│   └── mechanism_demo.ipynb        # Interactive walkthrough with visualizations
├── api/
│   └── main.py                     # FastAPI backend (credentials scrubbed)
├── docs/
│   ├── mechanism.md                # Extended formal write-up of Layer 2
│   ├── legal_whitepaper.pdf        # Full two-layer legal and architectural framework
│   └── settlement_architecture.md  # ERC-3643 + CCTP + oracle resolution design
├── .env.example
├── requirements.txt
└── LICENSE
```

---

## Installation

```
git clone https://github.com/adityanb/lmsr-preclinical-markets
cd lmsr-preclinical-markets
pip install -r requirements.txt
cp .env.example .env  # fill in your credentials
```

To run the mechanism demo:

```
jupyter notebook notebooks/mechanism_demo.ipynb
```

To start the API:

```
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
8. ERC-3643 T-REX Standard. *Token for Regulated EXchanges*. [erc3643.org](https://erc3643.org)
9. Circle. Cross-Chain Transfer Protocol (CCTP). [circle.com/cross-chain-transfer-protocol](https://www.circle.com/cross-chain-transfer-protocol)
10. SEC. Regulation D, Rule 506(c). 17 CFR § 230.506(c).

---

## Author

**Aditya N. Bhosale**
University of Pennsylvania (Biology & Healthcare Finance)
[adityanb@sas.upenn.edu](mailto:adityanb@sas.upenn.edu)

*Working project — two-layer architecture committed, Layer 2 mechanism implementation live, Layer 1 SPV tokenization in legal review. Feedback welcome.*
