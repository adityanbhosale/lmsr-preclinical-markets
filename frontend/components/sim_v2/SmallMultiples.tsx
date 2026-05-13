/**
 * SmallMultiples — grid of mini sparklines, one per ensemble seed.
 *
 * Each cell shows aggregate Brier over time for one seed. The grid lets
 * the user see ensemble variance at a glance — some seeds wander, some
 * converge tightly, all average to the headline finding. This is the
 * structural answer to "single-run results are misleading" — the variance
 * is on screen.
 *
 * Layout: responsive grid, 4 columns at md+ width, 2 at small. Each
 * sparkline is ~150x60px.
 *
 * Performance: each sparkline downsamples to ~80 points. With 16 seeds
 * that's 1,280 datapoints rendering, well below recharts' breaking point.
 */

"use client";

import { useMemo } from "react";
import { LineChart, Line, YAxis, ResponsiveContainer, ReferenceLine } from "recharts";
import type { FrameMessage, FinalFrame } from "@/lib/sim_v2/protocol";

interface SmallMultiplesProps {
  framesBySeed: Record<number, FrameMessage[]>;
  finalsBySeed: Record<number, FinalFrame>;
  /** Max sparkline data points per seed. Default 80. */
  maxPoints?: number;
}

export function SmallMultiples({
  framesBySeed,
  finalsBySeed,
  maxPoints = 80,
}: SmallMultiplesProps) {
  const seedIds = useMemo(
    () =>
      Object.keys(framesBySeed)
        .map(Number)
        .sort((a, b) => a - b),
    [framesBySeed],
  );

  const data = useMemo(() => {
    return seedIds.map((sid) => {
      const frames = framesBySeed[sid] ?? [];
      const stride = Math.max(1, Math.floor(frames.length / maxPoints));
      const sampled = frames.filter((_, i) => i % stride === 0 || i === frames.length - 1);
      return {
        seedId: sid,
        points: sampled.map((f) => ({ tick: f.tick, brier: f.aggregate_brier })),
        final: finalsBySeed[sid],
        n_frames: frames.length,
        last_brier: frames.length > 0 ? frames[frames.length - 1].aggregate_brier : null,
      };
    });
  }, [seedIds, framesBySeed, finalsBySeed, maxPoints]);

  // Global Y-axis domain for consistent visual comparison across cells
  const yDomain = useMemo<[number, number]>(() => {
    let max = 0;
    for (const cell of data) {
      for (const p of cell.points) {
        if (p.brier > max) max = p.brier;
      }
    }
    return [0, Math.max(max * 1.1, 0.01)];
  }, [data]);

  if (seedIds.length === 0) {
    return (
      <div className="flex h-40 items-center justify-center text-sm text-neutral-400 dark:text-neutral-500">
        Waiting for ensemble frames…
      </div>
    );
  }

  // Mean across all seeds' last_brier — quick aggregate read for the header
  const completedSeeds = data.filter((d) => d.final !== undefined);
  const meanFinalBrier =
    completedSeeds.length > 0
      ? completedSeeds.reduce((s, d) => s + (d.final?.final_aggregate_brier ?? 0), 0) /
        completedSeeds.length
      : null;

  return (
    <div className="space-y-3">
      {/* Summary bar */}
      <div className="flex items-center justify-between text-xs text-neutral-500 dark:text-neutral-400">
        <span>{seedIds.length} seeds rendering</span>
        {meanFinalBrier !== null && (
          <span className="tabular-nums">
            mean final Brier:{" "}
            <span className="font-medium text-neutral-900 dark:text-neutral-100">
              {meanFinalBrier.toFixed(4)}
            </span>{" "}
            ({completedSeeds.length}/{seedIds.length} settled)
          </span>
        )}
      </div>

      {/* Grid */}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-4 xl:grid-cols-4">
        {data.map((cell) => (
          <SparklineCell
            key={cell.seedId}
            seedId={cell.seedId}
            points={cell.points}
            yDomain={yDomain}
            finalBrier={cell.final?.final_aggregate_brier}
            meanBrier={meanFinalBrier}
          />
        ))}
      </div>
    </div>
  );
}

function SparklineCell({
  seedId,
  points,
  yDomain,
  finalBrier,
  meanBrier,
}: {
  seedId: number;
  points: { tick: number; brier: number }[];
  yDomain: [number, number];
  finalBrier?: number;
  meanBrier: number | null;
}) {
  // Color: settled seeds get fuller saturation; in-progress are dimmer
  const isSettled = finalBrier !== undefined;
  const lineColor = isSettled ? "rgb(15 23 42)" : "rgb(100 116 139)";

  // Optional: if settled and we know the mean, color the cell by whether
  // this seed is above or below the ensemble mean (above = worse than mean)
  let badgeColor = "text-neutral-500 dark:text-neutral-400";
  if (isSettled && meanBrier !== null && finalBrier !== undefined) {
    badgeColor =
      finalBrier <= meanBrier
        ? "text-emerald-600 dark:text-emerald-400"
        : "text-amber-600 dark:text-amber-400";
  }

  return (
    <div className="rounded-md border border-neutral-200 bg-white px-2 py-1.5 dark:border-neutral-800 dark:bg-neutral-900">
      <div className="mb-0.5 flex items-baseline justify-between">
        <span className="text-[10px] font-medium text-neutral-600 dark:text-neutral-400">
          seed {seedId}
        </span>
        {finalBrier !== undefined && (
          <span className={`text-[10px] font-medium tabular-nums ${badgeColor}`}>
            {finalBrier.toFixed(4)}
          </span>
        )}
      </div>
      <div className="h-12">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={points} margin={{ top: 2, right: 0, bottom: 2, left: 0 }}>
            <YAxis hide domain={yDomain} />
            {meanBrier !== null && (
              <ReferenceLine
                y={meanBrier}
                stroke="rgb(148 163 184)"
                strokeDasharray="2 2"
                strokeOpacity={0.5}
              />
            )}
            <Line
              type="monotone"
              dataKey="brier"
              stroke={lineColor}
              className={isSettled ? "" : "dark:[stroke:rgb(148_163_184)]"}
              strokeWidth={1.2}
              dot={false}
              isAnimationActive={false}
            />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
