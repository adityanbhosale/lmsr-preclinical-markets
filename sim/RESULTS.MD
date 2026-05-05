Sweep results for H1 & H2:

**Does H1 Hold?**
Conditionally. The ABMM retreat function reverses ~80-90% of attack displacement when the attack is ≤ 10% of seeded liquidity, ~50-80% at 25%, ~25-50% at 50%, and fails (<20%) at 75%. The polynomial decay shape is dominant across every magnitude tested – at 25% attack it recovers 81% versus exponential's 71% and step's 62%. The architectural implication then is that the retreat mechanism is robust against small-to-moderate attacks but cannot defend against attacks exceeding ~50% of liquidity. Polynomial decay should hereafter be the default model for ABMM retreat in the Layer 2 LM-LMSR markets.

**Does H2 Hold?**
Yes, with clean threshold. Convergence to true_prob within ε = 0.03 for K = 50 consecutive ticks is ≥97% reliable when credentialed agents constitute ≥40% of the population. Below 30% credentialed share, convergence rate drops to ~65-86%. In the dominant regime, median convergence is 312 ticks (IQR 193–482) – fast enough that typical clinical-trial-window simulations (1000+ ticks of pre-resolution trading), convergence is achieved with substantial steady-state runway.

**Interesting Findings**
(a) Polynomial decay non-trivially outperformed exponential decay at every mangnitude of liquidity shock. Exponential is the conventional default for retreat-style mechanisms in market-making literature; the empirical superiority of polynomial isn't theoretically obvious and warrants a closer look in the next iteration of this agentic stress testing model for the Layer 2 LS-LMSR markets. However, I now have a strong hypothesis that polynomial's slower-decaying tail keeps a small amount of ABMM inventory available longer, which provides residual liquidity to absorb post-attack human trades that try to revert price.

(b) Convergence to true_prob = 0.8 is sytematically less reliable than to 0.5 or 0.2 (in the H2 cross-tab from earlier). The pattern is asymmetric in the way symmetric Bayesian agents shouldn't produce according to literature. I'll investigate this further in the next iteration as well.

**Limitations**
The single-shot attack model is the greatest limitation of this simulation. Real adversarial behavior in prediction markets would be sustained, not single-shot liquidity shocks. An attacker would push the market over many trades, possibly with intermediate small trades to "cover" the attack signature. The current H1 sweep design tests one-shot displacement & recovery. It doesn't really characterize ABMM response to sustained pressure. I'll address this in the next iteration.

Additionally, credentialed agents in this simulation are calibrated against true_prob – i.e., they collectively know the truth, just with noise. Real informed traders disagree about true_prob. The 'credentialed disagreement' regime is not yet modeled, but will be in the next iteration.