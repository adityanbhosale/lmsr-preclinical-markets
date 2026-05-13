/**
 * SimulatorPanel — user-facing controls for v2.
 *
 * Renders the eight v2 knobs grouped by v1 finding mapping:
 *   - Population composition (Finding 1, 2): agent class counts
 *   - Capital constraint (Finding 3 / Exp #1): capital per agent
 *   - Trade-size mechanism (Exp #2): fixed vs confidence-weighted
 *   - Information structure (Findings 2, 4): regime, correlation, signal rate
 *   - Market design: alpha (LS-LMSR ceiling), retreat mode
 *   - Stream pacing (UX only): duration, fps, ensemble size
 *
 * Plus a preset selector for quick demos of v1 finding reproductions.
 *
 * No backend required to develop — this component only emits SimRequest
 * shapes via onChange and triggers onRun.
 */

"use client";

import { useState } from "react";
import { type SimRequest, DEFAULT_REQUEST } from "@/lib/sim_v2/protocol";
import { PRESETS, getPresetById } from "@/lib/sim_v2/presets";

interface SimulatorPanelProps {
  value: SimRequest;
  onChange: (next: SimRequest) => void;
  onRun: () => void;
  onStop: () => void;
  status: string; // "idle" | "connecting" | "pre_compute" | "streaming" | "done" | "error"
  disabled?: boolean;
}

const isBusy = (status: string) =>
  status === "connecting" || status === "pre_compute" || status === "streaming";

export function SimulatorPanel({
  value,
  onChange,
  onRun,
  onStop,
  status,
  disabled = false,
}: SimulatorPanelProps) {
  const [activePreset, setActivePreset] = useState<string>("v1_all_four_diversity");

  const update = <K extends keyof SimRequest>(key: K, patch: Partial<SimRequest[K]>) => {
    onChange({
      ...value,
      [key]: { ...(value[key] as object), ...patch },
    });
  };

  const handlePresetSelect = (id: string) => {
    const preset = getPresetById(id);
    if (preset) {
      setActivePreset(id);
      onChange(preset.config);
    }
  };

  const busy = isBusy(status);

  return (
    <aside className="w-80 shrink-0 border-r border-neutral-200 bg-neutral-50/50 p-5 dark:border-neutral-800 dark:bg-neutral-900/50">
      <div className="space-y-6">
        {/* Header + Run button */}
        <div className="space-y-3">
          <h2 className="text-sm font-semibold uppercase tracking-wider text-neutral-500 dark:text-neutral-400">
            Configuration
          </h2>
          <button
            type="button"
            disabled={disabled}
            onClick={busy ? onStop : onRun}
            className={`w-full rounded-lg px-4 py-2.5 text-sm font-medium shadow-sm transition-colors ${
              busy
                ? "bg-red-600 text-white hover:bg-red-700"
                : "bg-neutral-900 text-white hover:bg-neutral-800 dark:bg-neutral-100 dark:text-neutral-900 dark:hover:bg-white"
            } disabled:cursor-not-allowed disabled:opacity-50`}
          >
            {busy ? "Stop" : "Run simulation"}
          </button>
        </div>

        {/* Preset selector */}
        <Section title="Preset">
          <select
            value={activePreset}
            onChange={(e) => handlePresetSelect(e.target.value)}
            disabled={busy}
            className="w-full rounded-md border border-neutral-300 bg-white px-3 py-2 text-sm dark:border-neutral-700 dark:bg-neutral-800"
          >
            {PRESETS.map((p) => (
              <option key={p.id} value={p.id}>
                {p.name}
              </option>
            ))}
          </select>
          <p className="mt-2 text-xs leading-relaxed text-neutral-500 dark:text-neutral-400">
            {getPresetById(activePreset)?.description}
          </p>
        </Section>

        {/* Agent composition */}
        <Section title="Agent population">
          <Stepper
            label="Naive credentialed"
            value={value.agent_mix.n_naive}
            min={0}
            max={10}
            onChange={(v) => update("agent_mix", { n_naive: v })}
            disabled={busy}
          />
          <Stepper
            label="Aggregation depth"
            value={value.agent_mix.n_aggregation}
            min={0}
            max={10}
            onChange={(v) => update("agent_mix", { n_aggregation: v })}
            disabled={busy}
          />
          <Stepper
            label="Tail event"
            value={value.agent_mix.n_tail}
            min={0}
            max={10}
            onChange={(v) => update("agent_mix", { n_tail: v })}
            disabled={busy}
          />
          <Stepper
            label="Cross-market"
            value={value.agent_mix.n_cross}
            min={0}
            max={10}
            onChange={(v) => update("agent_mix", { n_cross: v })}
            disabled={busy}
          />
          <Stepper
            label="Noise"
            value={value.agent_mix.n_noise}
            min={0}
            max={10}
            onChange={(v) => update("agent_mix", { n_noise: v })}
            disabled={busy}
          />
        </Section>

        {/* Capital & decision threshold */}
        <Section title="Capital & decisions">
          <Slider
            label="Capital per agent"
            value={value.agent.capital_per_agent}
            min={50}
            max={2000}
            step={50}
            format={(v) => `$${v}`}
            onChange={(v) => update("agent", { capital_per_agent: v })}
            disabled={busy}
            helpText="Finding 3: binding constraint for tail markets"
          />
          <Slider
            label="Disagreement threshold"
            value={value.agent.disagreement_threshold}
            min={0.01}
            max={0.10}
            step={0.005}
            format={(v) => v.toFixed(3)}
            onChange={(v) => update("agent", { disagreement_threshold: v })}
            disabled={busy}
            helpText="Trade trigger: |p_post − p_market|"
          />
        </Section>

        {/* Trade sizing */}
        <Section title="Trade sizing">
          <Toggle
            label="Mode"
            options={[
              { value: "fixed", label: "Fixed" },
              { value: "confidence_weighted", label: "Confidence-weighted" },
            ]}
            value={value.trade_sizing.mode}
            onChange={(v) =>
              update("trade_sizing", { mode: v as "fixed" | "confidence_weighted" })
            }
            disabled={busy}
            helpText="Experiment #2: dynamic sizing by posterior precision"
          />
        </Section>

        {/* Information environment */}
        <Section title="Information environment">
          <Toggle
            label="Regime"
            options={[
              { value: "routine", label: "Routine" },
              { value: "tail", label: "Tail" },
              { value: "mixed", label: "Mixed" },
            ]}
            value={value.information.regime}
            onChange={(v) =>
              update("information", { regime: v as "routine" | "tail" | "mixed" })
            }
            disabled={busy}
          />
          <Slider
            label="Within-cluster correlation"
            value={value.information.within_cluster_correlation}
            min={0.0}
            max={0.95}
            step={0.05}
            format={(v) => v.toFixed(2)}
            onChange={(v) =>
              update("information", { within_cluster_correlation: v })
            }
            disabled={busy}
            helpText="Finding 4: 2.55× penalty at high corr"
          />
          <Slider
            label="Signal rate"
            value={value.information.signal_rate}
            min={0.001}
            max={0.10}
            step={0.001}
            format={(v) => v.toFixed(3)}
            onChange={(v) => update("information", { signal_rate: v })}
            disabled={busy}
          />
          <Stepper
            label="Number of markets"
            value={value.information.n_markets}
            min={1}
            max={12}
            onChange={(v) => update("information", { n_markets: v })}
            disabled={busy}
          />
        </Section>

        {/* Market design */}
        <Section title="Market mechanism">
          <Slider
            label="LS-LMSR alpha"
            value={value.market.alpha}
            min={0.1}
            max={3.0}
            step={0.1}
            format={(v) => v.toFixed(1)}
            onChange={(v) => update("market", { alpha: v })}
            disabled={busy}
            helpText="Finding 3 ceiling: σ(1/α) at α=1.0 ≈ 0.731"
          />
        </Section>

        {/* Stream pacing */}
        <Section title="Stream pacing">
          <Slider
            label="Duration"
            value={value.stream.duration_seconds}
            min={10}
            max={900}
            step={10}
            format={(v) => `${v}s`}
            onChange={(v) => update("stream", { duration_seconds: v })}
            disabled={busy}
          />
          <Slider
            label="Frames/sec"
            value={value.stream.target_fps}
            min={2}
            max={30}
            step={1}
            format={(v) => `${v} fps`}
            onChange={(v) => update("stream", { target_fps: v })}
            disabled={busy}
          />
          <Stepper
            label="Ensemble seeds"
            value={value.stream.n_ensemble_seeds}
            min={1}
            max={64}
            onChange={(v) => update("stream", { n_ensemble_seeds: v })}
            disabled={busy}
          />
        </Section>

        {/* Reset to defaults */}
        <button
          type="button"
          onClick={() => {
            setActivePreset("");
            onChange(DEFAULT_REQUEST);
          }}
          disabled={busy}
          className="text-xs text-neutral-500 underline-offset-4 hover:text-neutral-700 hover:underline disabled:opacity-50 dark:text-neutral-400 dark:hover:text-neutral-200"
        >
          Reset to defaults
        </button>
      </div>
    </aside>
  );
}

// ────────────────────────────────────────────────────────────────────
// Primitives — minimal inline components, no external UI lib needed
// ────────────────────────────────────────────────────────────────────

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="space-y-3">
      <h3 className="text-xs font-semibold uppercase tracking-wider text-neutral-500 dark:text-neutral-400">
        {title}
      </h3>
      <div className="space-y-3">{children}</div>
    </div>
  );
}

function Stepper({
  label,
  value,
  min,
  max,
  onChange,
  disabled,
}: {
  label: string;
  value: number;
  min: number;
  max: number;
  onChange: (v: number) => void;
  disabled?: boolean;
}) {
  const dec = () => onChange(Math.max(min, value - 1));
  const inc = () => onChange(Math.min(max, value + 1));
  return (
    <div className="flex items-center justify-between gap-2">
      <span className="text-sm text-neutral-700 dark:text-neutral-300">{label}</span>
      <div className="flex items-center gap-1">
        <button
          type="button"
          onClick={dec}
          disabled={disabled || value <= min}
          className="h-7 w-7 rounded border border-neutral-300 bg-white text-neutral-700 hover:bg-neutral-100 disabled:opacity-30 dark:border-neutral-700 dark:bg-neutral-800 dark:text-neutral-200 dark:hover:bg-neutral-700"
          aria-label={`decrease ${label}`}
        >
          −
        </button>
        <span className="w-8 text-center text-sm font-medium tabular-nums">{value}</span>
        <button
          type="button"
          onClick={inc}
          disabled={disabled || value >= max}
          className="h-7 w-7 rounded border border-neutral-300 bg-white text-neutral-700 hover:bg-neutral-100 disabled:opacity-30 dark:border-neutral-700 dark:bg-neutral-800 dark:text-neutral-200 dark:hover:bg-neutral-700"
          aria-label={`increase ${label}`}
        >
          +
        </button>
      </div>
    </div>
  );
}

function Slider({
  label,
  value,
  min,
  max,
  step,
  format,
  onChange,
  disabled,
  helpText,
}: {
  label: string;
  value: number;
  min: number;
  max: number;
  step: number;
  format: (v: number) => string;
  onChange: (v: number) => void;
  disabled?: boolean;
  helpText?: string;
}) {
  return (
    <div className="space-y-1">
      <div className="flex items-baseline justify-between gap-2">
        <span className="text-sm text-neutral-700 dark:text-neutral-300">{label}</span>
        <span className="text-sm font-medium tabular-nums text-neutral-900 dark:text-neutral-100">
          {format(value)}
        </span>
      </div>
      <input
        type="range"
        min={min}
        max={max}
        step={step}
        value={value}
        onChange={(e) => onChange(Number(e.target.value))}
        disabled={disabled}
        className="block w-full accent-neutral-900 disabled:opacity-50 dark:accent-neutral-100"
      />
      {helpText && (
        <p className="text-[11px] leading-snug text-neutral-500 dark:text-neutral-400">{helpText}</p>
      )}
    </div>
  );
}

function Toggle({
  label,
  options,
  value,
  onChange,
  disabled,
  helpText,
}: {
  label: string;
  options: { value: string; label: string }[];
  value: string;
  onChange: (v: string) => void;
  disabled?: boolean;
  helpText?: string;
}) {
  return (
    <div className="space-y-1">
      <span className="block text-sm text-neutral-700 dark:text-neutral-300">{label}</span>
      <div className="flex rounded-md border border-neutral-300 bg-white p-0.5 dark:border-neutral-700 dark:bg-neutral-800">
        {options.map((opt) => (
          <button
            key={opt.value}
            type="button"
            onClick={() => onChange(opt.value)}
            disabled={disabled}
            className={`flex-1 rounded px-2 py-1 text-xs transition-colors ${
              value === opt.value
                ? "bg-neutral-900 text-white dark:bg-neutral-100 dark:text-neutral-900"
                : "text-neutral-600 hover:bg-neutral-100 dark:text-neutral-300 dark:hover:bg-neutral-700"
            } disabled:cursor-not-allowed disabled:opacity-50`}
          >
            {opt.label}
          </button>
        ))}
      </div>
      {helpText && (
        <p className="text-[11px] leading-snug text-neutral-500 dark:text-neutral-400">{helpText}</p>
      )}
    </div>
  );
}
