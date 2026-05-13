/**
 * PnLPanel — rent extraction display.
 *
 * Aggregates FinalFrame results across all settled seeds and shows:
 *   1. Summary line: AMM net / informed PnL / noise loss / rent efficiency
 *   2. Bar chart: mean PnL per agent class, with error bars from cross-seed std
 *   3. Tooltip-able detail per class (n_agents, win_rate, pnl_per_trade)
 *
 * The summary line is the Metalayer headline — "who pays whom" is the
 * protocol-design question, and these four numbers answer it.
 *
 * Empty state: shows a placeholder until at least one seed has settled,
 * then progressively reveals as more seeds complete. The aggregation
 * recomputes on each new final frame.
 */

"use client";

import { useMemo } from "react";
import {
  ResponsiveContainer,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  ReferenceLine,
  Tooltip,
  CartesianGrid,
  Cell,
} from "recharts";
import type { FinalFrame } from "@/lib/sim_v2/protocol";
import { CLASS_COLOR, CLASS_LABEL } from "@/lib/sim_v2/protocol";

interface PnLPanelProps {
  finalsBySeed: Record<number, FinalFrame>;
  totalEnsembleSeeds: number;
}

interface ClassAggregate {
  agent_class: string;
  mean_pnl: number;
  pnl_std: number;
  pnl_per_trade: number;
  n_agents: number;
  win_rate: number;
  total_volume: number;
  n_seeds: number;
}

interface RentAggregate {
  total_informed_pnl: number;
  noise_trader_loss: number;
  amm_net: number;
  rent_efficiency: number;
  n_seeds: number;
}

const CLASS_ORDER = ["naive", "aggregation", "tail", "cross", "noise"];

function aggregateClasses(finals: FinalFrame[]): ClassAggregate[] {
  if (finals.length === 0) return [];

  const accum: Record<
    string,
    {
      pnls: number[];
      stds: number[];
      per_trade: number[];
      n_agents: number[];
      win_rates: number[];
      volumes: number[];
    }
  > = {};

  for (const f of finals) {
    for (const c of f.pnl_by_class) {
      if (!accum[c.agent_class]) {
        accum[c.agent_class] = {
          pnls: [], stds: [], per_trade: [], n_agents: [], win_rates: [], volumes: [],
        };
      }
      accum[c.agent_class].pnls.push(c.mean_pnl);
      accum[c.agent_class].stds.push(c.pnl_std);
      accum[c.agent_class].per_trade.push(c.pnl_per_trade);
      accum[c.agent_class].n_agents.push(c.n_agents);
      accum[c.agent_class].win_rates.push(c.win_rate);
      accum[c.agent_class].volumes.push(c.total_volume);
    }
  }

  const mean = (xs: number[]) => (xs.length ? xs.reduce((a, b) => a + b, 0) / xs.length : 0);
  const std = (xs: number[]) => {
    if (xs.length < 2) return 0;
    const m = mean(xs);
    const v = xs.reduce((s, x) => s + (x - m) ** 2, 0) / (xs.length - 1);
    return Math.sqrt(v);
  };

  return Object.entries(accum)
    .map(([cls, vals]) => ({
      agent_class: cls,
      mean_pnl: mean(vals.pnls),
      pnl_std: std(vals.pnls),
      pnl_per_trade: mean(vals.per_trade),
      n_agents: Math.round(mean(vals.n_agents)),
      win_rate: mean(vals.win_rates),
      total_volume: mean(vals.volumes),
      n_seeds: vals.pnls.length,
    }))
    .sort((a, b) => CLASS_ORDER.indexOf(a.agent_class) - CLASS_ORDER.indexOf(b.agent_class));
}

function aggregateRent(finals: FinalFrame[]): RentAggregate | null {
  if (finals.length === 0) return null;
  const sum = { informed: 0, noise: 0, amm: 0, eff: 0 };
  for (const f of finals) {
    sum.informed += f.rent_extraction.total_informed_pnl;
    sum.noise += f.rent_extraction.noise_trader_loss;
    sum.amm += f.rent_extraction.amm_net;
    sum.eff += f.rent_extraction.rent_efficiency;
  }
  const n = finals.length;
  return {
    total_informed_pnl: sum.informed / n,
    noise_trader_loss: sum.noise / n,
    amm_net: sum.amm / n,
    rent_efficiency: sum.eff / n,
    n_seeds: n,
  };
}

export function PnLPanel({ finalsBySeed, totalEnsembleSeeds }: PnLPanelProps) {
  const finals = useMemo(() => Object.values(finalsBySeed), [finalsBySeed]);
  const classAgg = useMemo(() => aggregateClasses(finals), [finals]);
  const rent = useMemo(() => aggregateRent(finals), [finals]);

  if (finals.length === 0) {
    return (
      <div className="flex h-40 items-center justify-center text-sm text-neutral-400 dark:text-neutral-500">
        Waiting for first seed to settle…
      </div>
    );
  }

  const formatUsd = (v: number) => {
    const sign = v >= 0 ? "+" : "−";
    return `${sign}$${Math.abs(v).toFixed(2)}`;
  };

  return (
    <div className="space-y-5">
      {/* Rent extraction summary line */}
      {rent && (
        <div className="grid grid-cols-2 gap-4 rounded-md bg-neutral-50 p-4 sm:grid-cols-4 dark:bg-neutral-800/50">
          <SummaryCell
            label="AMM net"
            value={formatUsd(rent.amm_net)}
            valueColor={rent.amm_net > 0 ? "text-emerald-700 dark:text-emerald-400" : "text-neutral-900 dark:text-neutral-100"}
            sublabel="AMM extraction across population"
          />
          <SummaryCell
            label="Informed PnL"
            value={formatUsd(rent.total_informed_pnl)}
            valueColor={rent.total_informed_pnl > 0 ? "text-emerald-700 dark:text-emerald-400" : "text-amber-700 dark:text-amber-400"}
            sublabel="net to non-noise classes"
          />
          <SummaryCell
            label="Noise loss"
            value={formatUsd(rent.noise_trader_loss)}
            valueColor="text-neutral-900 dark:text-neutral-100"
            sublabel="positive = noise pays in"
          />
          <SummaryCell
            label="Rent efficiency"
            value={rent.rent_efficiency.toFixed(2)}
            valueColor={
              rent.rent_efficiency > 0.5
                ? "text-emerald-700 dark:text-emerald-400"
                : rent.rent_efficiency > 0
                ? "text-amber-700 dark:text-amber-400"
                : "text-red-700 dark:text-red-400"
            }
            sublabel="informed PnL / noise loss"
          />
        </div>
      )}

      <div className="text-xs text-neutral-500 dark:text-neutral-400">
        Averaged across {finals.length} settled seeds (of {totalEnsembleSeeds} ensemble).
        {finals.length < totalEnsembleSeeds && " Updates as remaining seeds finish."}
      </div>

      {/* Bar chart of mean PnL by class */}
      <div className="h-56">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={classAgg} margin={{ top: 8, right: 12, bottom: 8, left: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="rgb(229 229 229)" vertical={false} className="dark:[stroke:rgb(38_38_38)]" />
            <XAxis
              dataKey="agent_class"
              tickFormatter={(v: string) => CLASS_LABEL[v] ?? v}
              tick={{ fontSize: 11, fill: "rgb(115 115 115)" }}
              tickLine={false}
            />
            <YAxis
              tick={{ fontSize: 10, fill: "rgb(115 115 115)" }}
              tickLine={false}
              tickFormatter={(v) => formatUsd(v)}
            />
            <ReferenceLine y={0} stroke="rgb(115 115 115)" strokeWidth={1} />
            <Tooltip
              contentStyle={{
                fontSize: 11,
                background: "rgb(255 255 255 / 0.95)",
                border: "1px solid rgb(229 229 229)",
                borderRadius: 6,
              }}
              formatter={(value: unknown, _name: unknown, entry: unknown) => {
                const v = typeof value === "number" ? value : 0;
                const cls = (entry as { payload: ClassAggregate }).payload;
                return [
                  `${formatUsd(v)} (±${formatUsd(cls.pnl_std)})`,
                  `Mean PnL — ${CLASS_LABEL[cls.agent_class] ?? cls.agent_class}`,
                ];
              }}
              labelFormatter={() => ""}
            />
            <Bar dataKey="mean_pnl" radius={[2, 2, 0, 0]} isAnimationActive={false}>
              {classAgg.map((cls) => (
                <Cell key={cls.agent_class} fill={CLASS_COLOR[cls.agent_class] ?? "#999"} />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>

      {/* Per-class detail table */}
      <div className="overflow-x-auto">
        <table className="w-full text-xs">
          <thead>
            <tr className="border-b border-neutral-200 text-left text-neutral-500 dark:border-neutral-800 dark:text-neutral-400">
              <th className="py-1.5 pr-3 font-medium">Class</th>
              <th className="py-1.5 pr-3 font-medium tabular-nums">Mean PnL</th>
              <th className="py-1.5 pr-3 font-medium tabular-nums">σ across seeds</th>
              <th className="py-1.5 pr-3 font-medium tabular-nums">PnL / trade</th>
              <th className="py-1.5 pr-3 font-medium tabular-nums">Win rate</th>
              <th className="py-1.5 pr-3 font-medium tabular-nums">Agents</th>
            </tr>
          </thead>
          <tbody>
            {classAgg.map((cls) => (
              <tr
                key={cls.agent_class}
                className="border-b border-neutral-100 last:border-b-0 dark:border-neutral-800"
              >
                <td className="py-1.5 pr-3">
                  <span
                    className="mr-2 inline-block h-2 w-2 rounded-full"
                    style={{ background: CLASS_COLOR[cls.agent_class] }}
                  />
                  {CLASS_LABEL[cls.agent_class] ?? cls.agent_class}
                </td>
                <td className={`py-1.5 pr-3 tabular-nums ${cls.mean_pnl >= 0 ? "text-emerald-700 dark:text-emerald-400" : "text-amber-700 dark:text-amber-400"}`}>
                  {formatUsd(cls.mean_pnl)}
                </td>
                <td className="py-1.5 pr-3 tabular-nums text-neutral-600 dark:text-neutral-400">
                  ±${cls.pnl_std.toFixed(2)}
                </td>
                <td className="py-1.5 pr-3 tabular-nums text-neutral-600 dark:text-neutral-400">
                  {formatUsd(cls.pnl_per_trade)}
                </td>
                <td className="py-1.5 pr-3 tabular-nums text-neutral-600 dark:text-neutral-400">
                  {(cls.win_rate * 100).toFixed(0)}%
                </td>
                <td className="py-1.5 pr-3 tabular-nums text-neutral-600 dark:text-neutral-400">
                  {cls.n_agents}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function SummaryCell({
  label,
  value,
  valueColor,
  sublabel,
}: {
  label: string;
  value: string;
  valueColor: string;
  sublabel: string;
}) {
  return (
    <div>
      <div className="text-[11px] uppercase tracking-wider text-neutral-500 dark:text-neutral-400">
        {label}
      </div>
      <div className={`mt-0.5 text-lg font-semibold tabular-nums ${valueColor}`}>{value}</div>
      <div className="mt-0.5 text-[10px] leading-tight text-neutral-500 dark:text-neutral-400">
        {sublabel}
      </div>
    </div>
  );
}
