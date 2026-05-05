/**
 * LS-LMSR market with ABMM retreat — TypeScript port of sim/market.py.
 *
 * Binary YES/NO prediction market.
 *   b(q) = alpha * (qYes + qNo)
 *   C(q) = b * ln(exp(qYes/b) + exp(qNo/b))
 *   priceYes(q) = exp(qYes/b) / (exp(qYes/b) + exp(qNo/b))
 *
 * Retreat: ABMM seed inventory is multiplied by w(volume) where w(0) = 1
 * and w decays once human volume exceeds the threshold. Three decay shapes
 * supported; H1 results show polynomial (harmonic) dominates exponential
 * and step.
 *
 * All math uses log-sum-exp to avoid overflow when q/b is large.
 */

export type DecayShape = 'exponential' | 'polynomial' | 'step';

export interface LSLMSRConfig {
  alpha: number;        // LS sensitivity. Typical: 0.05.
  qAbmmYes: number;     // initial ABMM seed on YES
  qAbmmNo: number;      // initial ABMM seed on NO
}

export interface ABMMConfig {
  enabled: boolean;
  tau: number;          // retreat exponent
  threshold: number;    // human volume threshold before retreat begins
  decayShape: DecayShape;
}

export interface MarketSnapshot {
  qYesHuman: number;
  qNoHuman: number;
  qYesAbmmEff: number;  // ABMM contribution after retreat
  qNoAbmmEff: number;
  retreatFactor: number;
  humanVolume: number;
  priceYes: number;
  b: number;
  tick?: number;        // populated by runner
}

export interface TradeAction {
  isYes: boolean;
  shares: number;       // 0 = noop
}

export const NOOP: TradeAction = { isYes: true, shares: 0 };

/** Numerically stable log(exp(a) + exp(b)). */
function logSumExp2(a: number, b: number): number {
  const m = Math.max(a, b);
  return m + Math.log(Math.exp(a - m) + Math.exp(b - m));
}

/** Numerically stable softmax-of-2: exp(a) / (exp(a) + exp(b)). */
function softmax2(a: number, b: number): number {
  const m = Math.max(a, b);
  const ea = Math.exp(a - m);
  const eb = Math.exp(b - m);
  return ea / (ea + eb);
}

export class LSLMSRMarket {
  readonly config: LSLMSRConfig;
  readonly abmm: ABMMConfig;
  private qYesHuman = 0;
  private qNoHuman = 0;
  private humanVolume = 0;

  constructor(config: LSLMSRConfig, abmm: ABMMConfig) {
    if (config.alpha <= 0) throw new Error('alpha must be > 0');
    if (config.qAbmmYes <= 0 || config.qAbmmNo <= 0)
      throw new Error('ABMM seed must be > 0');
    this.config = config;
    this.abmm = abmm;
  }

  /**
   * Retreat factor w in [0, 1]. 1.0 = full ABMM, 0.0 = fully retreated.
   * Mirrors sim/market.py::_retreat_factor exactly:
   *   excess = human_volume - threshold     (raw, not normalized here)
   *   exponential: exp(-tau * excess / threshold)
   *   polynomial:  1 / (1 + tau * (excess / threshold))
   *   step:        0
   */
  retreatFactor(): number {
    if (!this.abmm.enabled) return 1.0;
    if (this.humanVolume <= this.abmm.threshold) return 1.0;
    const excess = this.humanVolume - this.abmm.threshold;
    const normalized = excess / this.abmm.threshold;

    switch (this.abmm.decayShape) {
      case 'exponential':
        return Math.exp(-this.abmm.tau * normalized);
      case 'polynomial':
        return 1 / (1 + this.abmm.tau * normalized);
      case 'step':
        return 0;
    }
  }

  qYesEffective(): number {
    return this.qYesHuman + this.retreatFactor() * this.config.qAbmmYes;
  }

  qNoEffective(): number {
    return this.qNoHuman + this.retreatFactor() * this.config.qAbmmNo;
  }

  b(): number {
    return this.config.alpha * (this.qYesEffective() + this.qNoEffective());
  }

  priceYes(): number {
    const b = this.b();
    if (b === 0) return 0.5;
    return softmax2(this.qYesEffective() / b, this.qNoEffective() / b);
  }

  cost(): number {
    const b = this.b();
    if (b === 0) return 0;
    return b * logSumExp2(this.qYesEffective() / b, this.qNoEffective() / b);
  }

  /**
   * Cost of executing a hypothetical trade, without mutating state.
   * Holds retreat factor constant across the trade — fine for any reasonable
   * single-trade size, since human volume only ticks up by `shares`.
   */
  costOfTrade(isYes: boolean, shares: number): number {
    if (shares <= 0) return 0;
    const before = this.cost();
    const w = this.retreatFactor();
    const qy = this.qYesHuman + (isYes ? shares : 0) + w * this.config.qAbmmYes;
    const qn = this.qNoHuman + (!isYes ? shares : 0) + w * this.config.qAbmmNo;
    const b = this.config.alpha * (qy + qn);
    if (b === 0) return 0;
    const after = b * logSumExp2(qy / b, qn / b);
    return after - before;
  }

  execute(action: TradeAction): { cost: number } {
    if (action.shares <= 0) return { cost: 0 };
    const cost = this.costOfTrade(action.isYes, action.shares);
    if (action.isYes) this.qYesHuman += action.shares;
    else this.qNoHuman += action.shares;
    this.humanVolume += action.shares;
    return { cost };
  }

  snapshot(): MarketSnapshot {
    const w = this.retreatFactor();
    return {
      qYesHuman: this.qYesHuman,
      qNoHuman: this.qNoHuman,
      qYesAbmmEff: w * this.config.qAbmmYes,
      qNoAbmmEff: w * this.config.qAbmmNo,
      retreatFactor: w,
      humanVolume: this.humanVolume,
      priceYes: this.priceYes(),
      b: this.b(),
    };
  }
}

/**
 * Build a market with a specific starting price by adjusting ABMM seed
 * proportions. Holds total seed inventory constant.
 *
 * For starting price p with seed inventory S:
 *   qY = S * p,  qN = S * (1 - p)
 * (Approximate — for p in [0.1, 0.9] the resulting price is within ~0.005
 * of the target, which is fine for v1.)
 */
export function marketWithStartingPrior(
  startingPrior: number,
  totalSeed: number,
  alpha: number,
  abmm: ABMMConfig,
): LSLMSRMarket {
  const p = Math.min(Math.max(startingPrior, 0.01), 0.99);
  return new LSLMSRMarket(
    {
      alpha,
      qAbmmYes: totalSeed * p,
      qAbmmNo: totalSeed * (1 - p),
    },
    abmm,
  );
}