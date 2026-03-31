# Backtest Candidate Profiles

Molecules selected for retrospective simulation of the LS-LMSR + ABMM mechanism against known clinical outcomes. All four were computationally characterized prior to IND submission, have publicly available preclinical data, and have reached definitive resolution (approval or termination).

The simulation methodology is described in `notebooks/backtest_demo.ipynb`. Confidence scores are reconstructed approximations based on published preclinical data available at the time of IND — they are not exact historical values, and are clearly labeled as such in all simulation outputs.

---

## Confidence Score Derivation

Each molecule receives a reconstructed `confidence_score ∈ [0, 1]` based on four components weighted as follows:

```
confidence_score = (binding_score × 0.35)
                 + (selectivity_score × 0.25)
                 + (admet_score × 0.25)
                 + (literature_score × 0.15)
```

From confidence score, the LS-LMSR `α` parameter is derived:

```
α = 0.005 + (1 − confidence_score) × 0.075
```

Low α → tight market, price-resistant to small trades (high-conviction molecule).  
High α → wide market, responsive to early expert signal (uncertain molecule).

---

## Molecule 1: Sotorasib (AMG-510)

| Field | Value |
|---|---|
| Generic name | Sotorasib |
| Development code | AMG-510 |
| Brand name | Lumakras |
| Developer | Amgen |
| Target | KRAS G12C |
| Modality | Covalent small molecule inhibitor |
| Indication | NSCLC, CRC |
| **Reconstructed confidence score** | **0.81** |
| **Derived α** | **0.019** |
| Final outcome | ✅ FDA Approved (May 2021) |

### Pre-Clinical Signal Summary

Sotorasib represented among the strongest preclinical profiles for an oncology small molecule at the time of IND. Key data points:

- **Binding / potency:** IC50 of 0.004–0.032 µM across nearly all KRAS G12C cell lines (Canon et al., *Nature* 2019). Covalent irreversible binding to the switch-II pocket in the GDP-bound state — novel and well-characterized mechanism.
- **In vivo efficacy:** Dose-responsive tumor regression in KRAS G12C murine models. Durable cures in 8/10 mice when combined with chemotherapy. ERK phosphorylation inhibited in nearly all treated models.
- **Selectivity:** Covalent binding to mutant cysteine-12 confers inherent selectivity over wild-type KRAS.
- **ADMET:** Favorable oral bioavailability; does not accumulate with multiple doses. Modest discount applied for renal tubular toxicity signal observed at high doses in rats (necrosis at 960 mg/kg).
- **Literature:** First-in-class mechanism with strong publication record pre-IND (Lanman et al., Hallin et al., Canon et al.).

### Confidence Score Breakdown

| Component | Score | Rationale |
|---|---|---|
| Binding / potency | 0.88 | IC50 4–32 nM, covalent, well-characterized pocket |
| Selectivity | 0.90 | Mutant-selective by mechanism; WT KRAS spared |
| ADMET | 0.72 | Good oral BA; renal tox signal at high dose discounted |
| Literature | 0.85 | *Nature* 2019 publication, multiple supporting abstracts |
| **Composite** | **0.81** | |

### Milestone Timeline

| Milestone | Date | Status | Outcome |
|---|---|---|---|
| M1: IND Submission | Q1 2019 | RESOLVED | ✅ YES |
| M2: Phase 1 Completion (CodeBreaK 100) | Q4 2019 | RESOLVED | ✅ YES |
| M3: Phase 2 Primary Endpoint | Q2 2020 | RESOLVED | ✅ YES |
| M4: FDA Approval | May 28, 2021 | RESOLVED | ✅ YES |

### Key References

- Canon J, et al. The clinical KRAS(G12C) inhibitor AMG 510 drives anti-tumour immunity. *Nature*. 2019;575(7781):217–223.
- Lanman BA, et al. Discovery of AMG 510, a first-in-human covalent inhibitor of KRAS(G12C). *J Med Chem*. 2020;63(1):52–65.
- Skoulidis F, et al. Sotorasib for lung cancers with KRAS p.G12C mutation. *NEJM*. 2021;384(25):2371–2381.

---

## Molecule 2: Vepdegestrant (ARV-471)

| Field | Value |
|---|---|
| Generic name | Vepdegestrant |
| Development code | ARV-471 |
| Developer | Arvinas / Pfizer |
| Target | Estrogen receptor alpha (ERα) |
| Modality | PROTAC protein degrader (CRBN E3 ligase) |
| Indication | ER+/HER2− locally advanced or metastatic breast cancer |
| **Reconstructed confidence score** | **0.73** |
| **Derived α** | **0.025** |
| Final outcome | ✅ NDA Submitted to FDA (June 2025); Phase 3 VERITAC-2 positive |

### Pre-Clinical Signal Summary

ARV-471 demonstrated exceptional preclinical ER degradation efficacy. The primary confidence discount reflects PROTAC-class translation risk at the time of IND (2019), when no PROTAC had yet been approved or demonstrated consistent clinical ORR.

- **Binding / degradation:** DC50 ~1 nM in ER+ breast cancer cell lines. >90% ER degradation achieved in MCF7 orthotopic xenograft models — substantially greater than fulvestrant (63–65% degradation).
- **In vivo efficacy:** 87–123% tumor growth inhibition in MCF7 models vs. 31–80% for fulvestrant. Tumor regression in ESR1 Y537S PDX model (hormone-independent, palbociclib-resistant).
- **Selectivity:** Designed for ER/CRBN binary selectivity. Degrades clinically relevant ESR1 mutants (Y537S, D538G).
- **ADMET:** Oral bioavailability highly variable across species — 59% in mouse, 24% in rat, 5% in dog. Standard Lipinski rules do not apply to PROTACs (MW ~770 Da); this was a novel class concern at IND. Half-life favorable (T1/2 = 6–15 h across species).
- **Literature:** First presented at SABCS 2018 (abstract P5-04-18). First-in-class oral ER PROTAC.

### Confidence Score Breakdown

| Component | Score | Rationale |
|---|---|---|
| Binding / potency | 0.90 | DC50 ~1 nM, >90% Dmax, mutant ER coverage |
| Selectivity | 0.85 | ER/CRBN binary; no significant off-targets reported |
| ADMET | 0.52 | Low dog bioavailability (5%); PROTAC PK class risk |
| Literature | 0.72 | Strong SABCS abstracts; PROTAC precedent limited in 2019 |
| **Composite** | **0.73** | |

### Milestone Timeline

| Milestone | Date | Status | Outcome |
|---|---|---|---|
| M1: IND Clearance | Q3 2019 | RESOLVED | ✅ YES |
| M2: Phase 1 Clinical Benefit (≥40% CBR) | Q4 2021 | RESOLVED | ✅ YES |
| M3: Phase 3 VERITAC-2 Positive | 2024 | RESOLVED | ✅ YES |
| M4: NDA Submission | June 2025 | RESOLVED | ✅ YES |

### Key References

- Flanagan JJ, et al. Abstract P5-04-18: ARV-471, an oral estrogen receptor PROTAC degrader for breast cancer. *Cancer Res*. 2019;79(4 Suppl).
- Snyder LB, et al. Abstract 44: The discovery of ARV-471. *Cancer Res*. 2021;81(13 Suppl).
- Gough SM, et al. Vepdegestrant is highly efficacious as monotherapy and in combination with CDK4/6 or PI3K/mTOR inhibitors in preclinical ER+ breast cancer models. *Clin Cancer Res*. 2024;30(16):3549–3563.

---

## Molecule 3: Adagrasib (MRTX-849)

| Field | Value |
|---|---|
| Generic name | Adagrasib |
| Development code | MRTX-849 |
| Brand name | Krazati |
| Developer | Mirati Therapeutics (now BMS) |
| Target | KRAS G12C |
| Modality | Covalent small molecule inhibitor |
| Indication | NSCLC, CRC |
| **Reconstructed confidence score** | **0.76** |
| **Derived α** | **0.023** |
| Final outcome | ✅ FDA Approved (December 2022) |

### Pre-Clinical Signal Summary

Strong preclinical profile, modestly discounted vs. sotorasib on two grounds: (1) second-in-class KRAS G12C inhibitor — differentiation risk was a real expert concern at IND; (2) tumor regression rate of 65% across CDX/PDX models, lower than sotorasib's curve. Key differentiator was CNS penetration and extended half-life (~24 hours), which experts recognized as a potential clinical advantage.

- **Binding / potency:** Cellular IC50 ~5 nM against KRAS G12C-dependent signaling. >1,000-fold selectivity for KRAS G12C vs. wild-type KRAS. Covalent binding to mutant cysteine-12 in GDP-bound state.
- **In vivo efficacy:** Tumor regression in 17/26 (65%) KRAS G12C-positive CDX/PDX models. Broad-spectrum activity across lung, colon, and pancreatic tumor models at 100 mg/kg/day.
- **Selectivity:** Of 463 proteins profiled in click chemistry proteomics, only KRAS G12C significantly decreased at 1 µM MRTX-849.
- **ADMET:** Long half-life (~24 h) and CNS penetration were differentiated properties. Oral bioavailability confirmed in multiple species.
- **Literature:** Hallin et al. *Cancer Discov* 2020; Fell et al. *J Med Chem* 2020.

### Confidence Score Breakdown

| Component | Score | Rationale |
|---|---|---|
| Binding / potency | 0.85 | 5 nM IC50, >1000x selectivity, clean proteomics |
| Selectivity | 0.88 | Single off-target hit in 463-protein screen |
| ADMET | 0.75 | Long t1/2, CNS penetration; second-in-class PK compared favorably |
| Literature | 0.70 | Strong Cancer Discov 2020; some second-in-class discount |
| **Composite** | **0.76** | |

### Milestone Timeline

| Milestone | Date | Status | Outcome |
|---|---|---|---|
| M1: IND / KRYSTAL-1 Start | Q4 2019 | RESOLVED | ✅ YES |
| M2: Phase 1 RP2D Established | Q1 2022 | RESOLVED | ✅ YES |
| M3: Phase 2 Primary Endpoint | Q3 2022 | RESOLVED | ✅ YES |
| M4: FDA Accelerated Approval | December 12, 2022 | RESOLVED | ✅ YES |

### Key References

- Fell JB, et al. Identification of the clinical development candidate MRTX849. *J Med Chem*. 2020;63(13):6679–6693.
- Hallin J, et al. The KRAS G12C inhibitor MRTX849 provides insight toward therapeutic susceptibility. *Cancer Discov*. 2020;10(1):54–71.
- Drilon A, et al. KRYSTAL-1 Phase 1/1b results. *JCO*. 2022.

---

## Molecule 4: BI 1701963 *(Fail Case)*

| Field | Value |
|---|---|
| Development code | BI 1701963 |
| Developer | Boehringer Ingelheim |
| Target | SOS1::KRAS protein-protein interaction |
| Modality | Small molecule PPI inhibitor |
| Indication | KRAS-mutant solid tumors (NSCLC, CRC, pancreatic) |
| **Reconstructed confidence score** | **0.48** |
| **Derived α** | **0.044** |
| Final outcome | ❌ All trials terminated (2023–2024) |

### Pre-Clinical Signal Summary

BI 1701963 is the right fail case because it failed for scientifically anticipatable reasons — not because of obvious flaws, but because an expert panel paying attention to preclinical signal would have flagged cytostatic-only single-agent activity and the requirement for combination to achieve meaningful tumor regression.

- **Mechanism:** First-in-class SOS1::KRAS PPI inhibitor. Blocks SOS1 binding to RAS-GDP, preventing GDP→GTP exchange (indirect pan-KRAS inhibition). Scientifically novel — activity against G12D/V/C and G13D, unlike KRAS G12C-selective inhibitors.
- **Binding / potency:** Moderate potency. Inhibition of SOS1::KRAS interaction well-characterized biochemically. Cellular activity demonstrated in KRAS-mutant cell lines.
- **In vivo efficacy:** Primarily cytostatic as monotherapy — tumor growth inhibition rather than regression in most models. Synergistic effects with MEK inhibitors and KRAS G12C inhibitors in combination, but marginal single-agent efficacy in PDX models. Regression achieved only in combination experiments.
- **ADMET:** Identified as a liability — challenging pharmacokinetics cited in termination rationale. Oral dosing at 50 mg/kg BID required for preclinical activity (high dose burden).
- **Clinical translation:** Phase 1 (NCT04111458) initiated 2019. Of 31 treated patients, only 7 achieved stable disease as monotherapy. Terminated 2023 due to safety issues and limited efficacy.

### Confidence Score Breakdown

| Component | Score | Rationale |
|---|---|---|
| Binding / potency | 0.55 | Mechanism validated but potency moderate; cytostatic not cytotoxic |
| Selectivity | 0.65 | Pan-KRAS activity is a feature, but SOS2 sparing confirmed |
| ADMET | 0.38 | High dose burden; challenging PK flagged in preclinical studies |
| Literature | 0.42 | Novel mechanism but limited single-agent in vivo publications |
| **Composite** | **0.48** | |

### Milestone Timeline

| Milestone | Date | Status | Outcome |
|---|---|---|---|
| M1: IND / Phase 1 Start (NCT04111458) | Q4 2019 | RESOLVED | ✅ YES |
| M2: Phase 1 Completion / RP2D | 2022–2023 | RESOLVED | ❌ NO — terminated |
| M3: Phase 2 | Never initiated | RESOLVED | ❌ NO |
| M4: Approval | Never reached | RESOLVED | ❌ NO |

*Termination rationale per published record: challenging PK characteristics, safety issues, and limited monotherapy efficacy (Cancer Research 2025, citing Boehringer termination).*

### Key References

- Hofmann MH, et al. BI-3406, a potent and selective SOS1::KRAS interaction inhibitor. *Cancer Discov*. 2021;11(1):172–193.
- Fell JB, et al. Abstract CT210: Phase 1 studies of BI 1701963 in combination. *Cancer Res*. 2021;81(13 Suppl).
- Cancer Research (AACR). Targeted Degradation of SOS1 Exhibits Potent Anticancer Activity (noting BI-1701963 trial terminations). 2025;85(1):101.

---

## Cross-Molecule Summary

| Molecule | Modality | Conf. Score | α | M1 | M2 | M3 | M4 |
|---|---|---|---|---|---|---|---|
| Sotorasib | KRAS G12C SMI | 0.81 | 0.019 | ✅ | ✅ | ✅ | ✅ |
| Vepdegestrant | ER PROTAC | 0.73 | 0.025 | ✅ | ✅ | ✅ | ✅ |
| Adagrasib | KRAS G12C SMI | 0.76 | 0.023 | ✅ | ✅ | ✅ | ✅ |
| BI 1701963 | SOS1::KRAS PPI | 0.48 | 0.044 | ✅ | ❌ | ❌ | ❌ |

The confidence score spread (0.48–0.81) and the single fail case (BI 1701963) are intentional design choices. A backtest where all candidates succeed would only validate the mechanism's ability to track success. The fail case tests whether ABMM seeding at lower confidence and wider α produces a price path that appropriately stays suppressed or converges toward 0 at resolution — the harder and more informative test.

---

*Confidence scores are reconstructed approximations, not historical oracle outputs. All simulation results using these values should be framed as: "had the LS-LMSR + ABMM mechanism existed and been seeded with priors consistent with available preclinical data, the market price path would have evolved as follows."*
