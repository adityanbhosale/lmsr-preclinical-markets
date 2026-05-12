/**
 * sim_v2 frontend top-level page (Next.js App Router).
 *
 * This is a sketch showing the wiring between the four major UI surfaces.
 * Each component is its own file (omitted from sketch but follows from this).
 *
 * Layout:
 *   ┌──────────────────────────────────────────────────────────────────┐
 *   │  Header — preset selector, "Run" button, status indicator        │
 *   ├──────────────────┬───────────────────────────────────────────────┤
 *   │                  │                                                │
 *   │  SimulatorPanel  │   MarketView (hero seed + CI band)            │
 *   │  (knobs)         │                                                │
 *   │                  ├───────────────────────────────────────────────┤
 *   │                  │   SmallMultiples (16 seeds, sparkline grid)   │
 *   │                  ├───────────────────────────────────────────────┤
 *   │                  │   PnLPanel (rent extraction by class)         │
 *   └──────────────────┴───────────────────────────────────────────────┘
 *
 * Lives at: frontend/app/v2/page.tsx
 */

"use client";

import { useState } from "react";
import { useSimStream } from "@/hooks/useSimStream";
import { DEFAULT_REQUEST, type SimRequest } from "@/lib/protocol";
// import { SimulatorPanel } from "@/components/SimulatorPanel";
// import { MarketView } from "@/components/MarketView";
// import { SmallMultiples } from "@/components/SmallMultiples";
// import { PnLPanel } from "@/components/PnLPanel";

const WS_URL =
  process.env.NEXT_PUBLIC_SIM_V2_WS ??
  "wss://your-workspace--sim-v2-fastapi-app.modal.run/ws/simulate";

export default function V2Page() {
  const [config, setConfig] = useState<SimRequest>(DEFAULT_REQUEST);
  const stream = useSimStream(WS_URL);

  const handleRun = () => stream.start(config);
  const handleStop = () => stream.stop();

  // Hero seed = seed_id 0. Small multiples = seeds 1..N-1.
  const heroFrames = stream.framesBySeed[0] ?? [];
  const heroLatest = stream.latestFrameBySeed[0];
  const heroFinal = stream.finalsBySeed[0];

  return (
    <div className="grid grid-cols-[320px_1fr] gap-4 p-6">
      <aside className="sticky top-6 self-start">
        {/* <SimulatorPanel value={config} onChange={setConfig} /> */}
        <div className="rounded-2xl border p-4 space-y-3">
          <h2 className="font-semibold">Configuration</h2>
          <div className="text-sm text-muted-foreground">
            Knobs: agent mix, capital, trade sizing, correlation, regime,
            disagreement threshold, AMM alpha. Each one maps to a v1 finding
            or recommended next experiment.
          </div>
          <button
            onClick={stream.status === "idle" || stream.status === "done" ? handleRun : handleStop}
            className="w-full rounded-lg bg-foreground text-background py-2"
          >
            {stream.status === "idle" || stream.status === "done"
              ? "Run simulation"
              : stream.status === "pre_compute"
              ? "Pre-computing…"
              : stream.status === "streaming"
              ? "Stop"
              : stream.status}
          </button>
        </div>
      </aside>

      <main className="space-y-4">
        <section className="rounded-2xl border p-4">
          <h2 className="font-semibold mb-2">Hero seed</h2>
          {/* <MarketView frames={heroFrames} latest={heroLatest} ciBand={stream.ciBand} final={heroFinal} /> */}
          <div className="text-sm text-muted-foreground">
            Live price trace with 95% CI band overlay. Frames: {heroFrames.length}.
            Current tick: {heroLatest?.tick ?? "—"}. Aggregate Brier:{" "}
            {heroLatest?.aggregate_brier.toFixed(4) ?? "—"}.
          </div>
        </section>

        <section className="rounded-2xl border p-4">
          <h2 className="font-semibold mb-2">Ensemble (16 seeds)</h2>
          {/* <SmallMultiples framesBySeed={stream.framesBySeed} finalsBySeed={stream.finalsBySeed} /> */}
          <div className="text-sm text-muted-foreground">
            16 sparklines, one per seed. Shows ensemble variance directly —
            the central design fix for v1's ensemble-vs-single-run tension.
          </div>
        </section>

        <section className="rounded-2xl border p-4">
          <h2 className="font-semibold mb-2">Rent extraction</h2>
          {/* <PnLPanel finalsBySeed={stream.finalsBySeed} /> */}
          <div className="text-sm text-muted-foreground">
            PnL by agent class, aggregated across all seeds. Informed PnL,
            noise loss, AMM net, rent efficiency. Updates as each seed
            finishes settling.
          </div>
        </section>
      </main>
    </div>
  );
}
