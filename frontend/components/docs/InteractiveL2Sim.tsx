'use client';

/**
 * Interactive L2 simulation panel.
 *
 * Adjusts agent mix, true probability, retreat config, and an optional
 * adversarial attack. Re-runs the LS-LMSR + agent simulator client-side
 * on every parameter change (~50ms for 1000 ticks) and renders the price
 * trajectory + retreat factor as a dual-line Recharts plot.
 */

import { useDeferredValue, useMemo, useState } from 'react';
import {
  CartesianGrid,
  Label,
  Legend,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';

import { LSLMSRMarket, DecayShape, marketWithStartingPrior } from '@/lib/sim/lslmsr';
import { Agent, AdversarialTrader, buildPopulation } from '@/lib/sim/agents';
import { runSimulation } from '@/lib/sim/runner';
import { mulberry32 } from '@/lib/sim/rng';

// ── Defaults ──────────────────────────────────────────────────────────────

const DEFAULTS = {
  trueProb: 0.65,
  startingPrior: 0.5,
  credSharePct: 60,
  momSharePct: 20,
  nTicks: 1000,
  totalAgents: 50,
  alpha: 0.05,
  totalSeed: 1000,
  tau: 1.5,
  threshold: 100,
  decayShape: 'polynomial' as DecayShape,
  seed: 42,
  attackMagnitudePct: 25,
};

// ── Main component ────────────────────────────────────────────────────────

export function InteractiveL2Sim() {
  // Always-visible state
  const [credSharePct, setCredSharePct] = useState(DEFAULTS.credSharePct);
  const [momSharePct, setMomSharePct] = useState(DEFAULTS.momSharePct);
  const [trueProb, setTrueProb] = useState(DEFAULTS.trueProb);
  const [nTicks, setNTicks] = useState(DEFAULTS.nTicks);
  const [attackEnabled, setAttackEnabled] = useState(false);

  // Advanced state
  const [startingPrior, setStartingPrior] = useState(DEFAULTS.startingPrior);
  const [tau, setTau] = useState(DEFAULTS.tau);
  const [threshold, setThreshold] = useState(DEFAULTS.threshold);
  const [decayShape, setDecayShape] = useState<DecayShape>(DEFAULTS.decayShape);
  const [seed, setSeed] = useState(DEFAULTS.seed);
  const [attackMagnitudePct, setAttackMagnitudePct] = useState(DEFAULTS.attackMagnitudePct);

  // Constrain mom share so cred + mom <= 100
  const maxMomShare = Math.max(0, 100 - credSharePct);
  const safeMomShare = Math.min(momSharePct, maxMomShare);
  const noiseSharePct = Math.max(0, 100 - credSharePct - safeMomShare);

  // Defer expensive simulation until UI is idle (smooths slider drag)
  const params = {
    credSharePct,
    momSharePct: safeMomShare,
    trueProb,
    nTicks,
    attackEnabled,
    startingPrior,
    tau,
    threshold,
    decayShape,
    seed,
    attackMagnitudePct,
  };
  const deferredParams = useDeferredValue(params);

  const log = useMemo(() => {
    const p = deferredParams;
    const rng = mulberry32(p.seed);

    const market = marketWithStartingPrior(
      p.startingPrior,
      DEFAULTS.totalSeed,
      DEFAULTS.alpha,
      { enabled: true, tau: p.tau, threshold: p.threshold, decayShape: p.decayShape },
    );

    const noiseShare = Math.max(0, 100 - p.credSharePct - p.momSharePct);
    const population = buildPopulation(
      {
        totalAgents: DEFAULTS.totalAgents,
        mix: [p.credSharePct / 100, noiseShare / 100, p.momSharePct / 100],
        trueProbability: p.trueProb,
        credentialed: { sigma: 0.1, aggressiveness: 0.5, minEdge: 0.01 },
        noise: { meanSize: 3.0, sizeStd: 1.0 },
        momentum: { lookback: 15, threshold: 0.02, aggressiveness: 0.3 },
      },
      rng,
    );

    const agents: Agent[] = [...population];
    if (p.attackEnabled) {
      agents.push(
        new AdversarialTrader('adv_0', {
          attackTick: Math.floor(p.nTicks / 3),
          attackShares: (p.attackMagnitudePct / 100) * DEFAULTS.totalSeed,
          // Attack against the truth direction — maximally adversarial
          attackIsYes: p.trueProb < 0.5,
        }),
      );
    }

    return runSimulation({ market, agents, nTicks: p.nTicks, rng });
  }, [deferredParams]);

  // Subsample for plotting — Recharts struggles past ~300 points
  const plotData = useMemo(() => {
    const stride = Math.max(1, Math.floor(log.length / 250));
    return log
      .filter((_, i) => i % stride === 0 || i === log.length - 1)
      .map((l) => ({
        tick: l.tick,
        priceYes: Number(l.priceYes.toFixed(4)),
        retreatFactor: Number(l.retreatFactor.toFixed(4)),
      }));
  }, [log]);

  const lastTick = log[log.length - 1];
  const attackTick = attackEnabled ? Math.floor(deferredParams.nTicks / 3) : null;
  const isStale = params !== deferredParams;

  function reset() {
    setCredSharePct(DEFAULTS.credSharePct);
    setMomSharePct(DEFAULTS.momSharePct);
    setTrueProb(DEFAULTS.trueProb);
    setNTicks(DEFAULTS.nTicks);
    setAttackEnabled(false);
    setStartingPrior(DEFAULTS.startingPrior);
    setTau(DEFAULTS.tau);
    setThreshold(DEFAULTS.threshold);
    setDecayShape(DEFAULTS.decayShape);
    setSeed(DEFAULTS.seed);
    setAttackMagnitudePct(DEFAULTS.attackMagnitudePct);
  }

  return (
    <section className="not-prose border border-border rounded-lg bg-background my-8">
      <header className="px-5 py-4 border-b border-border">
        <h3 className="text-sm font-semibold tracking-tight text-foreground">
          Interactive simulation
        </h3>
        <p className="text-xs text-muted-foreground mt-1 leading-relaxed">
          Adjust agent mix, market parameters, and adversarial attacks. The simulator
          runs in your browser — every change re-executes ~{deferredParams.nTicks} trades
          using the same LS-LMSR + agent code as the H1/H2 sweeps below.
        </p>
      </header>

      <div className="grid grid-cols-1 lg:grid-cols-[280px_1fr]">
        {/* ── Controls ──────────────────────────────────────────────── */}
        <div className="p-5 space-y-5 border-b lg:border-b-0 lg:border-r border-border">
          <Section label="Agent population">
            <Slider
              label="Credentialed"
              value={credSharePct}
              onChange={setCredSharePct}
              min={0}
              max={100}
              step={5}
              suffix="%"
            />
            <Slider
              label="Momentum"
              value={safeMomShare}
              onChange={(v) => setMomSharePct(Math.min(v, maxMomShare))}
              min={0}
              max={maxMomShare}
              step={5}
              suffix="%"
            />
            <ReadOnly label="Noise (auto)" value={`${noiseSharePct}%`} />
          </Section>

          <Section label="Market truth">
            <Slider
              label="True probability"
              value={trueProb}
              onChange={setTrueProb}
              min={0.05}
              max={0.95}
              step={0.05}
              format={(v) => v.toFixed(2)}
            />
            <Slider
              label="Trades"
              value={nTicks}
              onChange={setNTicks}
              min={200}
              max={2000}
              step={100}
            />
          </Section>

          <button
            type="button"
            onClick={() => setAttackEnabled((v) => !v)}
            className={`w-full text-xs font-medium py-2 px-3 rounded-md border transition-colors ${
              attackEnabled
                ? 'bg-orange-50 dark:bg-orange-950/40 border-orange-300 dark:border-orange-900 text-orange-900 dark:text-orange-200 hover:bg-orange-100 dark:hover:bg-orange-950/60'
                : 'border-border text-foreground hover:bg-muted/50'
            }`}
          >
            {attackEnabled
              ? `Attack armed: ${attackMagnitudePct}% @ tick ${Math.floor(nTicks / 3)}`
              : 'Fire adversarial attack'}
          </button>

          <details className="group">
            <summary className="text-xs font-medium text-foreground cursor-pointer select-none flex items-center gap-1.5 hover:text-muted-foreground">
              <span className="transition-transform group-open:rotate-90 inline-block">▸</span>
              Advanced
            </summary>
            <div className="mt-3 space-y-4 pl-1.5 border-l border-border ml-1">
              <Section label="Starting state" inset>
                <Slider
                  label="Starting prior"
                  value={startingPrior}
                  onChange={setStartingPrior}
                  min={0.05}
                  max={0.95}
                  step={0.05}
                  format={(v) => v.toFixed(2)}
                />
              </Section>

              <Section label="Retreat function" inset>
                <Slider
                  label="τ (decay)"
                  value={tau}
                  onChange={setTau}
                  min={0.5}
                  max={3.0}
                  step={0.1}
                  format={(v) => v.toFixed(1)}
                />
                <Slider
                  label="Threshold"
                  value={threshold}
                  onChange={setThreshold}
                  min={50}
                  max={500}
                  step={50}
                />
                <RadioGroup
                  label="Decay shape"
                  value={decayShape}
                  onChange={setDecayShape}
                  options={[
                    { value: 'polynomial', label: 'Poly' },
                    { value: 'exponential', label: 'Exp' },
                    { value: 'step', label: 'Step' },
                  ]}
                />
              </Section>

              {attackEnabled && (
                <Section label="Attack" inset>
                  <RadioGroup
                    label="Magnitude"
                    value={attackMagnitudePct}
                    onChange={setAttackMagnitudePct}
                    options={[
                      { value: 10, label: '10%' },
                      { value: 25, label: '25%' },
                      { value: 50, label: '50%' },
                      { value: 75, label: '75%' },
                    ]}
                  />
                </Section>
              )}

              <Section label="Reproducibility" inset>
                <NumberInput label="Seed" value={seed} onChange={setSeed} />
              </Section>
            </div>
          </details>

          <button
            type="button"
            onClick={reset}
            className="w-full text-xs text-muted-foreground hover:text-foreground py-1.5 transition-colors"
          >
            Reset to defaults
          </button>
        </div>

        {/* ── Plot + readouts ───────────────────────────────────────── */}
        <div className="p-5">
          <div
            className={`relative transition-opacity duration-150 ${
              isStale ? 'opacity-60' : 'opacity-100'
            }`}
          >
            <ResponsiveContainer width="100%" height={380}>
              <LineChart
                data={plotData}
                margin={{ top: 12, right: 110, left: 0, bottom: 24 }}
              >
                <CartesianGrid
                  strokeDasharray="2 4"
                  stroke="currentColor"
                  strokeOpacity={0.08}
                  vertical={false}
                />
                <XAxis
                  dataKey="tick"
                  stroke="currentColor"
                  strokeOpacity={0.4}
                  fontSize={10}
                  tickLine={false}
                  axisLine={{ stroke: 'currentColor', strokeOpacity: 0.15 }}
                >
                  <Label
                    value="Tick"
                    offset={-12}
                    position="insideBottom"
                    fontSize={10}
                    fill="currentColor"
                    fillOpacity={0.5}
                  />
                </XAxis>
                <YAxis
                  domain={[0, 1]}
                  stroke="currentColor"
                  strokeOpacity={0.4}
                  fontSize={10}
                  tickLine={false}
                  axisLine={{ stroke: 'currentColor', strokeOpacity: 0.15 }}
                  tickFormatter={(v: number) => v.toFixed(1)}
                  ticks={[0, 0.25, 0.5, 0.75, 1]}
                />
                <Tooltip
                  contentStyle={{
                    background: 'hsl(var(--background))',
                    border: '1px solid hsl(var(--border))',
                    borderRadius: 6,
                    fontSize: 11,
                  }}
                  labelFormatter={(t) => `Tick ${t}`}
                  formatter={(v: number, name: string) => [
                    v.toFixed(3),
                    name === 'priceYes' ? 'Price (YES)' : 'Retreat factor',
                  ]}
                />
                <ReferenceLine
                  y={trueProb}
                  stroke="#dc2626"
                  strokeDasharray="3 3"
                  strokeOpacity={0.7}
                  label={{
                    value: `true_prob = ${trueProb.toFixed(2)}`,
                    fontSize: 10,
                    fill: '#dc2626',
                    position: 'right',
                    offset: 8,
                  }}
                />
                <ReferenceLine
                  y={startingPrior}
                  stroke="currentColor"
                  strokeDasharray="2 4"
                  strokeOpacity={0.25}
                />
                {attackTick !== null && (
                  <ReferenceLine
                    x={attackTick}
                    stroke="#ea580c"
                    strokeDasharray="2 4"
                    strokeOpacity={0.7}
                    label={{
                      value: 'attack',
                      fontSize: 10,
                      fill: '#ea580c',
                      position: 'top',
                    }}
                  />
                )}
                <Line
                  type="monotone"
                  dataKey="priceYes"
                  stroke="#1e40af"
                  strokeWidth={1.6}
                  dot={false}
                  isAnimationActive={false}
                  name="priceYes"
                />
                <Line
                  type="monotone"
                  dataKey="retreatFactor"
                  stroke="currentColor"
                  strokeWidth={1}
                  strokeDasharray="3 3"
                  strokeOpacity={0.5}
                  dot={false}
                  isAnimationActive={false}
                  name="retreatFactor"
                />
                <Legend
                  verticalAlign="top"
                  height={28}
                  iconType="line"
                  wrapperStyle={{ fontSize: 11, paddingBottom: 8 }}
                  formatter={(v) =>
                    v === 'priceYes' ? 'Price (YES)' : 'Retreat factor'
                  }
                />
              </LineChart>
            </ResponsiveContainer>
          </div>

          <div className="grid grid-cols-3 gap-2 mt-4">
            <Stat label="Final price" value={lastTick.priceYes.toFixed(3)} />
            <Stat label="Retreat factor" value={lastTick.retreatFactor.toFixed(3)} />
            <Stat label="Volume" value={lastTick.humanVolume.toFixed(0)} />
          </div>
        </div>
      </div>
    </section>
  );
}

// ── Helper sub-components ─────────────────────────────────────────────────

function Section({
  label,
  children,
  inset = false,
}: {
  label: string;
  children: React.ReactNode;
  inset?: boolean;
}) {
  return (
    <div className={inset ? 'space-y-2.5 pl-2' : 'space-y-2.5'}>
      <div className="text-[10px] uppercase tracking-wider font-semibold text-muted-foreground">
        {label}
      </div>
      <div className="space-y-2.5">{children}</div>
    </div>
  );
}

function Slider({
  label,
  value,
  onChange,
  min,
  max,
  step = 1,
  suffix = '',
  format,
}: {
  label: string;
  value: number;
  onChange: (v: number) => void;
  min: number;
  max: number;
  step?: number;
  suffix?: string;
  format?: (v: number) => string;
}) {
  return (
    <label className="block">
      <div className="flex justify-between items-baseline mb-1">
        <span className="text-xs text-muted-foreground">{label}</span>
        <span className="text-xs font-mono text-foreground tabular-nums">
          {format ? format(value) : `${value}${suffix}`}
        </span>
      </div>
      <input
        type="range"
        min={min}
        max={max}
        step={step}
        value={value}
        onChange={(e) => onChange(Number(e.target.value))}
        className="w-full h-1 accent-foreground cursor-pointer"
      />
    </label>
  );
}

function ReadOnly({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex justify-between items-baseline">
      <span className="text-xs text-muted-foreground">{label}</span>
      <span className="text-xs font-mono text-muted-foreground tabular-nums">{value}</span>
    </div>
  );
}

function RadioGroup<T extends string | number>({
  label,
  value,
  onChange,
  options,
}: {
  label: string;
  value: T;
  onChange: (v: T) => void;
  options: { value: T; label: string }[];
}) {
  return (
    <div>
      <div className="text-xs text-muted-foreground mb-1.5">{label}</div>
      <div className="flex gap-1">
        {options.map((opt) => (
          <button
            key={String(opt.value)}
            type="button"
            onClick={() => onChange(opt.value)}
            className={`flex-1 text-xs py-1 px-1.5 rounded border transition-colors ${
              value === opt.value
                ? 'bg-foreground text-background border-foreground'
                : 'border-border text-muted-foreground hover:text-foreground hover:border-foreground/40'
            }`}
          >
            {opt.label}
          </button>
        ))}
      </div>
    </div>
  );
}

function NumberInput({
  label,
  value,
  onChange,
}: {
  label: string;
  value: number;
  onChange: (v: number) => void;
}) {
  return (
    <label className="flex justify-between items-center gap-2">
      <span className="text-xs text-muted-foreground">{label}</span>
      <input
        type="number"
        value={value}
        onChange={(e) => onChange(Number(e.target.value) || 0)}
        className="w-20 text-xs font-mono bg-transparent border border-border rounded px-2 py-0.5 text-foreground tabular-nums focus:outline-none focus:border-foreground/40"
      />
    </label>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="border border-border rounded-md px-3 py-2">
      <div className="text-[10px] uppercase tracking-wider text-muted-foreground">
        {label}
      </div>
      <div className="text-sm font-mono font-medium text-foreground tabular-nums mt-0.5">
        {value}
      </div>
    </div>
  );
}