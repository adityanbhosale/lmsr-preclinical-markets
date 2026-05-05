/**
 * Agent classes — TypeScript port of sim/agents/.
 *
 * Four classes:
 *   - CredentialedTrader: informed trader with private Gaussian signal.
 *     Drives H2 convergence behavior.
 *   - NoiseTrader: random direction, random size. Models retail.
 *   - MomentumTrader: trend-follower with lookback window.
 *   - AdversarialTrader: single-shot attack at a runner tick. H1 only.
 */

import { TradeAction, NOOP, MarketSnapshot } from './lslmsr';
import { sampleNormal } from './rng';

export interface Agent {
  readonly id: string;
  decide(state: MarketSnapshot): TradeAction;
}

// ── Credentialed ──────────────────────────────────────────────────────────

export interface CredentialedParams {
  sigma: number;          // std dev of private signal around true_prob
  aggressiveness: number; // size = aggressiveness * |signal - price| * b
  minEdge: number;        // skip trade if |signal - price| < minEdge
  trueProbability: number;
}

export class CredentialedTrader implements Agent {
  readonly id: string;
  private params: CredentialedParams;
  private signal: number;

  constructor(id: string, params: CredentialedParams, rng: () => number) {
    this.id = id;
    this.params = params;
    this.signal = sampleNormal(rng, params.trueProbability, params.sigma);
    this.signal = Math.max(0.001, Math.min(0.999, this.signal));
  }

  decide(state: MarketSnapshot): TradeAction {
    const edge = this.signal - state.priceYes;
    if (Math.abs(edge) < this.params.minEdge) return NOOP;
    const shares = this.params.aggressiveness * Math.abs(edge) * state.b;
    if (shares <= 0) return NOOP;
    return { isYes: edge > 0, shares };
  }
}

// ── Noise ─────────────────────────────────────────────────────────────────

export interface NoiseParams {
  meanSize: number;
  sizeStd: number;
}

export class NoiseTrader implements Agent {
  readonly id: string;
  private params: NoiseParams;
  private rng: () => number;

  constructor(id: string, params: NoiseParams, rng: () => number) {
    this.id = id;
    this.params = params;
    this.rng = rng;
  }

  decide(_state: MarketSnapshot): TradeAction {
    const isYes = this.rng() < 0.5;
    const shares = Math.max(
      0.1,
      sampleNormal(this.rng, this.params.meanSize, this.params.sizeStd),
    );
    return { isYes, shares };
  }
}

// ── Momentum ──────────────────────────────────────────────────────────────

export interface MomentumParams {
  lookback: number;
  threshold: number;
  aggressiveness: number;
}

export class MomentumTrader implements Agent {
  readonly id: string;
  private params: MomentumParams;
  private priceHistory: number[] = [];

  constructor(id: string, params: MomentumParams, _rng: () => number) {
    this.id = id;
    this.params = params;
  }

  decide(state: MarketSnapshot): TradeAction {
    this.priceHistory.push(state.priceYes);
    if (this.priceHistory.length > this.params.lookback * 2) {
      this.priceHistory.shift();
    }
    if (this.priceHistory.length < this.params.lookback) return NOOP;

    const window = this.priceHistory.slice(-this.params.lookback);
    const ma = window.reduce((a, b) => a + b, 0) / window.length;
    const delta = state.priceYes - ma;

    if (Math.abs(delta) < this.params.threshold) return NOOP;
    const shares = this.params.aggressiveness * Math.abs(delta) * state.b;
    if (shares <= 0) return NOOP;
    return { isYes: delta > 0, shares };
  }
}

// ── Adversarial (H1) ──────────────────────────────────────────────────────

export interface AdversarialParams {
  attackTick: number;
  attackShares: number;
  attackIsYes: boolean;
}

export class AdversarialTrader implements Agent {
  readonly id: string;
  private params: AdversarialParams;
  private hasAttacked = false;

  constructor(id: string, params: AdversarialParams) {
    this.id = id;
    this.params = params;
  }

  decide(state: MarketSnapshot): TradeAction {
    if (this.hasAttacked) return NOOP;
    if ((state.tick ?? 0) < this.params.attackTick) return NOOP;
    this.hasAttacked = true;
    return {
      isYes: this.params.attackIsYes,
      shares: this.params.attackShares,
    };
  }
}

// ── Population builder ────────────────────────────────────────────────────

export interface PopulationConfig {
  totalAgents: number;
  mix: [number, number, number]; // [credentialed, noise, momentum] — sums to 1
  trueProbability: number;
  credentialed: Omit<CredentialedParams, 'trueProbability'>;
  noise: NoiseParams;
  momentum: MomentumParams;
}

export function buildPopulation(
  config: PopulationConfig,
  rng: () => number,
): Agent[] {
  const [credShare, noiseShare, momShare] = config.mix;
  const total = credShare + noiseShare + momShare;
  if (Math.abs(total - 1) > 1e-6) {
    throw new Error(`mix must sum to 1.0 (got ${total})`);
  }

  const nCred = Math.round(config.totalAgents * credShare);
  const nNoise = Math.round(config.totalAgents * noiseShare);
  const nMom = config.totalAgents - nCred - nNoise;

  const agents: Agent[] = [];
  for (let i = 0; i < nCred; i++) {
    agents.push(
      new CredentialedTrader(
        `cred_${i}`,
        { ...config.credentialed, trueProbability: config.trueProbability },
        rng,
      ),
    );
  }
  for (let i = 0; i < nNoise; i++) {
    agents.push(new NoiseTrader(`noise_${i}`, config.noise, rng));
  }
  for (let i = 0; i < nMom; i++) {
    agents.push(new MomentumTrader(`mom_${i}`, config.momentum, rng));
  }
  return agents;
}