/**
 * Simulation runner — uniform-sample agents, execute trades, log snapshots.
 * Mirrors sim/runner.py. Pure function: same inputs → same outputs.
 */

import { LSLMSRMarket, MarketSnapshot } from './lslmsr';
import { Agent } from './agents';

export interface RunConfig {
  market: LSLMSRMarket;
  agents: Agent[];
  nTicks: number;
  rng: () => number;
}

export interface TickLog {
  tick: number;
  priceYes: number;
  retreatFactor: number;
  humanVolume: number;
  b: number;
  agentId: string;
  isYes: boolean;
  shares: number;
  cost: number;
}

export function runSimulation(config: RunConfig): TickLog[] {
  const { market, agents, nTicks, rng } = config;
  const log: TickLog[] = [];

  for (let t = 0; t < nTicks; t++) {
    const agent = agents[Math.floor(rng() * agents.length)];
    const state: MarketSnapshot = { ...market.snapshot(), tick: t };
    const action = agent.decide(state);
    const { cost } = market.execute(action);
    const after = market.snapshot();
    log.push({
      tick: t,
      priceYes: after.priceYes,
      retreatFactor: after.retreatFactor,
      humanVolume: after.humanVolume,
      b: after.b,
      agentId: agent.id,
      isYes: action.isYes,
      shares: action.shares,
      cost,
    });
  }

  return log;
}