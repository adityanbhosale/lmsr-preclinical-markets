import { marketWithStartingPrior } from '../lib/sim/lslmsr';
import { buildPopulation } from '../lib/sim/agents';
import { runSimulation } from '../lib/sim/runner';
import { mulberry32 } from '../lib/sim/rng';

const rng = mulberry32(123);
const market = marketWithStartingPrior(0.5, 1000, 0.05, {
  enabled: true, tau: 1.5, threshold: 100, decayShape: 'polynomial',
});
const agents = buildPopulation({
  totalAgents: 50,
  mix: [0.6, 0.2, 0.2],
  trueProbability: 0.65,
  credentialed: { sigma: 0.10, aggressiveness: 0.5, minEdge: 0.01 },
  noise: { meanSize: 3.0, sizeStd: 1.0 },
  momentum: { lookback: 15, threshold: 0.02, aggressiveness: 0.3 },
}, rng);

const log = runSimulation({ market, agents, nTicks: 1000, rng });
console.log('Final price:', log[log.length - 1].priceYes.toFixed(4));
console.log('Final retreat:', log[log.length - 1].retreatFactor.toFixed(4));
console.log('Final volume:', log[log.length - 1].humanVolume.toFixed(1));