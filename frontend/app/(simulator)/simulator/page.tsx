/**
 * /simulator — top-level page for the v2 interactive market design sandbox.
 *
 * Layout:
 *   ┌──────────────────────────────────────────────────────────────────┐
 *   │  Top bar: title + ConnectionStatus + frames counter              │
 *   ├──────────────────┬───────────────────────────────────────────────┤
 *   │  SimulatorPanel  │  MarketView (hero seed + CI band)             │
 *   │  (controls)      ├───────────────────────────────────────────────┤
 *   │                  │  SmallMultiples (N seed sparklines)           │
 *   │                  ├───────────────────────────────────────────────┤
 *   │                  │  PnLPanel (rent extraction)                   │
 *   └──────────────────┴───────────────────────────────────────────────┘
 */

"use client";

import { useState } from "react";
import { useSimStream } from "@/hooks/useSimStream";
import { DEFAULT_REQUEST, type SimRequest } from "@/lib/sim_v2/protocol";
import { SimulatorPanel } from "@/components/sim_v2/SimulatorPanel";
import { ConnectionStatus } from "@/components/sim_v2/ConnectionStatus";
import { MarketView } from "@/components/sim_v2/MarketView";
import { SmallMultiples } from "@/components/sim_v2/SmallMultiples";
import { PnLPanel } from "@/components/sim_v2/PnLPanel";

const WS_URL =
  process.env.NEXT_PUBLIC_SIM_V2_WS ?? "ws://localhost:8000/ws/simulate";

export default function SimulatorPage() {
  const [config, setConfig] = useState<SimRequest>(DEFAULT_REQUEST);
  const stream = useSimStream(WS_URL);

  const heroSeedId = 0;
  const heroFrames = stream.framesBySeed[heroSeedId] ?? [];
  const heroLatest = stream.latestFrameBySeed[heroSeedId] ?? null;

  return (
    <div className="flex h-screen flex-col bg-white dark:bg-neutral-950">
      {/* Top bar */}
      <header className="flex items-center justify-between border-b border-neutral-200 bg-white px-6 py-3 dark:border-neutral-800 dark:bg-neutral-950">
        <div className="flex items-center gap-4">
          <h1 className="text-lg font-semibold text-neutral-900 dark:text-neutral-100">
            market design sim
          </h1>
          <span className="text-xs text-neutral-500 dark:text-neutral-400">
            v2 — interactive
          </span>
        </div>
        <ConnectionStatus
          status={stream.status}
          totalFrames={stream.totalFrames}
          errorMessage={stream.error?.message}
        />
      </header>

      {/* Main layout */}
      <div className="flex flex-1 overflow-hidden">
        <SimulatorPanel
          value={config}
          onChange={setConfig}
          onRun={() => stream.start(config)}
          onStop={stream.stop}
          status={stream.status}
        />

        <main className="flex-1 overflow-y-auto p-6">
          <div className="mx-auto max-w-5xl space-y-6">
            {/* Hero MarketView */}
            <section className="rounded-2xl border border-neutral-200 bg-white p-5 dark:border-neutral-800 dark:bg-neutral-900">
              <div className="mb-3 flex items-baseline justify-between">
                <h2 className="text-base font-semibold text-neutral-900 dark:text-neutral-100">
                  Hero seed
                </h2>
                {heroLatest && (
                  <span className="text-xs tabular-nums text-neutral-500 dark:text-neutral-400">
                    tick {heroLatest.tick.toLocaleString()} · Brier {heroLatest.aggregate_brier.toFixed(4)}
                  </span>
                )}
              </div>
              
              <MarketView frames={heroFrames} ciBand={stream.ciBand} />
            </section>

            {/* Small multiples */}
            <section className="rounded-2xl border border-neutral-200 bg-white p-5 dark:border-neutral-800 dark:bg-neutral-900">
              <div className="mb-3 flex items-baseline justify-between">
                <h2 className="text-base font-semibold text-neutral-900 dark:text-neutral-100">
                  Ensemble ({config.stream.n_ensemble_seeds} seeds)
                </h2>
                <span className="text-xs text-neutral-500 dark:text-neutral-400">
                  one sparkline per seed · dashed = ensemble mean
                </span>
              </div>
              <SmallMultiples
                framesBySeed={stream.framesBySeed}
                finalsBySeed={stream.finalsBySeed}
              />
            </section>

            {/* PnL & rent extraction */}
            <section className="rounded-2xl border border-neutral-200 bg-white p-5 dark:border-neutral-800 dark:bg-neutral-900">
              <div className="mb-3 flex items-baseline justify-between">
                <h2 className="text-base font-semibold text-neutral-900 dark:text-neutral-100">
                  Rent extraction by class
                </h2>
                <span className="text-xs text-neutral-500 dark:text-neutral-400">
                  who pays whom — protocol design lens
                </span>
              </div>
              <PnLPanel
                finalsBySeed={stream.finalsBySeed}
                totalEnsembleSeeds={config.stream.n_ensemble_seeds}
              />
            </section>
          </div>
        </main>
      </div>
    </div>
  );
}
