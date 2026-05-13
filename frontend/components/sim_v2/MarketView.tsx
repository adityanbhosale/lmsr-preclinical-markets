/**
 * MarketView — hero-seed chart with two stacked recharts panels.
 *
 * Top panel: per-market YES price traces over time. Each market gets its
 * own line, plus a horizontal dashed reference line at its p_star (true
 * probability). The convergence story plays out visually as the lines
 * pull toward their dashed targets.
 *
 * Bottom panel: aggregate Brier of the hero seed plotted against the
 * 95% CI band derived from the pre-computed ensemble. Shows where this
 * particular run sits within the population of possible runs — directly
 * addresses the "ensemble vs single seed" tension v1's findings created.
 *
 * Performance: at default 8fps × 7min that's ~3,360 frames. We downsample
 * to ~400 points for the chart layer (every ~9th frame). Recharts handles
 * 400-point line charts without breaking a sweat.no
 */

"use client";

import { useMemo } from "react";
import {
  ResponsiveContainer,
  LineChart,
  Line,
  AreaChart,
  Area,
  XAxis,
  YAxis,
  Tooltip,
  ReferenceLine,
  CartesianGrid,
  Legend,
} from "recharts";
import type { FrameMessage, CIBandFrame } from "@/lib/sim_v2/protocol";



interface MarketViewProps {
  frames: FrameMessage[];
  ciBand: CIBandFrame | null;
  /** Optional: render this many points max for performance. Default 400. */
  maxPoints?: number;
}

// Paul Tol palette — same colors used in v1's analysis figures
const MARKET_COLORS = ["#4477AA", "#EE6677", "#228833", "#CCBB44", "#66CCEE", "#AA3377", "#BBBBBB"];

export function MarketView({ frames, ciBand, maxPoints = 400 }: MarketViewProps) {
  // Build the price-trace data: one row per (downsampled) tick.
  // Each row: { tick, market_0: price, market_1: price, ..., brier: aggregate }
  const traceData = useMemo(() => {
    if (frames.length === 0) return [];

    const stride = Math.max(1, Math.floor(frames.length / maxPoints));
    const sampled = frames.filter((_, i) => i % stride === 0 || i === frames.length - 1);

    return sampled.map((f) => {
      const row: Record<string, number> = { tick: f.tick, brier: f.aggregate_brier };
      for (const m of f.markets) {
        row[`market_${m.market_id}`] = m.price_yes;
      }
      return row;
    });
  }, [frames, maxPoints]);

  // p_star per market from the latest frame (constant across the run, but we
  // need to pluck it from somewhere)
  const pStarByMarket = useMemo(() => {
    if (frames.length === 0) return {};
    const last = frames[frames.length - 1];
    const out: Record<number, number> = {};
    for (const m of last.markets) {
      out[m.market_id] = m.p_star;
    }
    return out;
  }, [frames]);

  // CI band data, downsampled to align with our trace stride
  const bandData = useMemo(() => {
    if (!ciBand || !ciBand.ticks.length) return [];
    const stride = Math.max(1, Math.floor(ciBand.ticks.length / maxPoints));
    const out: Array<{ tick: number; p025: number; p975: number; mean: number }> = [];
    for (let i = 0; i < ciBand.ticks.length; i += stride) {
      out.push({
        tick: ciBand.ticks[i],
        p025: ciBand.brier_p025[i],
        p975: ciBand.brier_p975[i],
        mean: ciBand.brier_mean[i],
      });
    }
    return out;
  }, [ciBand, maxPoints]);

  // Merge band into trace so the bottom chart can read both from same data
  type BrierChartRow = {
    tick: number;
    brier: number;
    p025?: number;
    p975?: number;
    mean?: number;
  };
  const brierChartData = useMemo<BrierChartRow[]>(() => {
    if (bandData.length === 0) return traceData.map((t) => ({ tick: t.tick, brier: t.brier }));

    // Index band by tick for fast lookup
    const bandByTick = new Map<number, { p025: number; p975: number; mean: number }>();
    for (const b of bandData) {
      bandByTick.set(b.tick, { p025: b.p025, p975: b.p975, mean: b.mean });
    }

    // For each trace row, find nearest band row by tick
    return traceData.map((t) => {
      // Round-down to nearest band tick (band ticks come from horizon, evenly spaced)
      const bandTicks = bandData.map((b) => b.tick);
      const nearest = bandTicks.reduce((prev, curr) =>
        Math.abs(curr - t.tick) < Math.abs(prev - t.tick) ? curr : prev
      );
      const b = bandByTick.get(nearest);
      return {
        tick: t.tick,
        brier: t.brier,
        p025: b?.p025,
        p975: b?.p975,
        mean: b?.mean,
      };
    });
  }, [traceData, bandData]);

  if (frames.length === 0) {
    return (
      <div className="flex h-72 items-center justify-center text-sm text-neutral-400 dark:text-neutral-500">
        Waiting for first frame…
      </div>
    );
  }

  const marketIds = frames[0].markets.map((m) => m.market_id);

  return (
    <div className="space-y-6">
      {/* Top: per-market price traces */}
      <div className="h-64">
        <div className="mb-1 flex items-center justify-between">
          <h3 className="text-xs font-medium uppercase tracking-wider text-neutral-500 dark:text-neutral-400">
            Per-market YES price
          </h3>
          <span className="text-[11px] text-neutral-400 dark:text-neutral-500">
            dashed lines = true p*
          </span>
        </div>
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={traceData} margin={{ top: 8, right: 12, bottom: 8, left: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="rgb(229 229 229)" className="dark:[stroke:rgb(38_38_38)]" />
            <XAxis
              dataKey="tick"
              type="number"
              domain={["dataMin", "dataMax"]}
              tick={{ fontSize: 10, fill: "rgb(115 115 115)" }}
              tickLine={false}
            />
            <YAxis
              domain={[0, 1]}
              ticks={[0, 0.25, 0.5, 0.75, 1.0]}
              tick={{ fontSize: 10, fill: "rgb(115 115 115)" }}
              tickLine={false}
              tickFormatter={(v) => v.toFixed(2)}
            />
            <Tooltip
              contentStyle={{
                fontSize: 11,
                background: "rgb(255 255 255 / 0.95)",
                border: "1px solid rgb(229 229 229)",
                borderRadius: 6,
              }}
              labelFormatter={(t) => `tick ${t}`}
              formatter={(value: unknown, name: unknown) =>
                [Number(value).toFixed(4), name as string]
              }            />
            {marketIds.map((mid, i) => (
              <Line
                key={`line-${mid}`}
                type="monotone"
                dataKey={`market_${mid}`}
                stroke={MARKET_COLORS[i % MARKET_COLORS.length]}
                strokeWidth={1.5}
                dot={false}
                isAnimationActive={false}
                name={`Market ${mid}`}
              />
            ))}
            {marketIds.map((mid, i) => (
              <ReferenceLine
                key={`ref-${mid}`}
                y={pStarByMarket[mid]}
                stroke={MARKET_COLORS[i % MARKET_COLORS.length]}
                strokeDasharray="4 4"
                strokeOpacity={0.4}
              />
            ))}
          </LineChart>
        </ResponsiveContainer>
      </div>

      {/* Bottom: aggregate Brier with CI band */}
      <div className="h-44">
        <div className="mb-1 flex items-center justify-between">
          <h3 className="text-xs font-medium uppercase tracking-wider text-neutral-500 dark:text-neutral-400">
            Aggregate Brier
          </h3>
          <span className="text-[11px] text-neutral-400 dark:text-neutral-500">
            shaded = 95% CI from ensemble pre-pass
          </span>
        </div>
        <ResponsiveContainer width="100%" height="100%">
          <AreaChart data={brierChartData} margin={{ top: 8, right: 12, bottom: 8, left: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="rgb(229 229 229)" className="dark:[stroke:rgb(38_38_38)]" />
            <XAxis
              dataKey="tick"
              type="number"
              domain={["dataMin", "dataMax"]}
              tick={{ fontSize: 10, fill: "rgb(115 115 115)" }}
              tickLine={false}
            />
            <YAxis
              tick={{ fontSize: 10, fill: "rgb(115 115 115)" }}
              tickLine={false}
              tickFormatter={(v) => v.toFixed(3)}
            />
            <Tooltip
              contentStyle={{
                fontSize: 11,
                background: "rgb(255 255 255 / 0.95)",
                border: "1px solid rgb(229 229 229)",
                borderRadius: 6,
              }}
              labelFormatter={(t) => `tick ${t}`}
              formatter={(value: unknown, name: unknown) => {
                const nameStr = String(name);
                if (typeof value !== "number") return ["—", nameStr];
                return [value.toFixed(4), nameStr];
              }}
            />
            {/* CI band as filled area between p025 and p975.
                Recharts technique: stack two areas. First p025 is invisible,
                then a delta is layered on top of it with fill. */}
            {brierChartData.some((d) => d.p025 !== undefined) && (
              <>
                <Area
                  type="monotone"
                  dataKey="p025"
                  stroke="none"
                  fill="none"
                  isAnimationActive={false}
                  legendType="none"
                />
                <Area
                  type="monotone"
                  dataKey={(d: { p025?: number; p975?: number }) =>
                    d.p975 !== undefined && d.p025 !== undefined ? d.p975 - d.p025 : undefined
                  }
                  stroke="none"
                  fill="rgb(148 163 184)"
                  fillOpacity={0.2}
                  stackId="band"
                  isAnimationActive={false}
                  name="95% CI"
                />
              </>
            )}
            {/* Ensemble mean as dashed reference */}
            <Line
              type="monotone"
              dataKey="mean"
              stroke="rgb(100 116 139)"
              strokeWidth={1}
              strokeDasharray="3 3"
              dot={false}
              isAnimationActive={false}
              name="Ensemble mean"
            />
            {/* Hero seed Brier — the actual live line */}
            <Line
              type="monotone"
              dataKey="brier"
              stroke="rgb(15 23 42)"
              className="dark:[stroke:rgb(241_245_249)]"
              strokeWidth={1.75}
              dot={false}
              isAnimationActive={false}
              name="This seed"
            />
            <Legend
              wrapperStyle={{ fontSize: 10, paddingTop: 4 }}
              iconType="line"
              iconSize={10}
            />
          </AreaChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
