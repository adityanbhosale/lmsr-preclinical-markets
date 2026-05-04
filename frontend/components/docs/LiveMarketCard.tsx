'use client';

/**
 * <LiveMarketCard /> — embeddable multi-market live-data widget.
 *
 * Reads on-chain state for each market in lib/markets.ts via wagmi
 * useReadContracts (multicall) and renders a compact grid summary.
 *
 * Compatible with the project's actual Market type:
 *   { id, address, program, milestone, description, resolutionTarget }
 *
 * All Layer 2 markets live on Base Sepolia, so chainId is hardcoded
 * here rather than read off each market entry.
 *
 * Usage in MDX:
 *   <LiveMarketCard />
 *   <LiveMarketCard programs={['sotorasib', 'adagrasib']} />
 */

import Link from 'next/link';
import { useReadContracts } from 'wagmi';
import { baseSepolia } from 'wagmi/chains';
import { MARKETS, type Market } from '@/lib/markets';
import { lslmsrAbi } from '@/lib/abi/lslmsr';

const REFETCH_INTERVAL_MS = 12_000;
const ALPHA = 0.05;
const CHAIN_ID = baseSepolia.id;

function computePriceYes(qYes: bigint, qNo: bigint): number {
  const yes = Number(qYes) / 1e18;
  const no = Number(qNo) / 1e18;
  const b = ALPHA * (yes + no);
  if (b === 0) return 0.5;
  const expYes = Math.exp(yes / b);
  const expNo = Math.exp(no / b);
  const sumExp = expYes + expNo;
  const sYes = expYes / sumExp;
  const sNo = expNo / sumExp;
  const H = -(sYes * Math.log(sYes + 1e-12) + sNo * Math.log(sNo + 1e-12));
  return Math.min(Math.max(sYes + ALPHA * H, 0), 1);
}

function probabilityClass(p: number): string {
  if (p >= 0.5) return 'text-green-600';
  if (p >= 0.25) return 'text-amber-600';
  return 'text-red-600';
}

function formatProgramName(program: string): string {
  // sotorasib -> Sotorasib, BI-1701963 stays uppercase
  if (program === program.toUpperCase()) return program;
  return program.charAt(0).toUpperCase() + program.slice(1);
}

export function LiveMarketCard({ programs }: { programs?: string[] }) {
  const marketsToShow: readonly Market[] = programs
    ? MARKETS.filter((m) => programs.includes(m.program))
    : MARKETS;

  // Filter to deployed markets (those with a non-null/non-empty address)
  const deployed = marketsToShow.filter(
    (m): m is Market & { address: `0x${string}` } =>
      typeof m.address === 'string' && m.address.startsWith('0x'),
  );

  const contracts = deployed.flatMap((m) => [
    {
      address: m.address,
      abi: lslmsrAbi,
      chainId: CHAIN_ID,
      functionName: 'qYes' as const,
    },
    {
      address: m.address,
      abi: lslmsrAbi,
      chainId: CHAIN_ID,
      functionName: 'qNo' as const,
    },
  ]);

  const { data, isLoading, isError } = useReadContracts({
    contracts,
    query: {
      refetchInterval: REFETCH_INTERVAL_MS,
      enabled: deployed.length > 0,
    },
  });

  return (
    <div className="not-prose my-5 grid grid-cols-1 sm:grid-cols-2 gap-3">
      {marketsToShow.map((market) => {
        const deployedIdx = deployed.findIndex((d) => d.id === market.id);
        const isDeployed = deployedIdx !== -1;

        let priceYes: number | null = null;
        if (isDeployed && data && !isError) {
          const qYesResult = data[deployedIdx * 2];
          const qNoResult = data[deployedIdx * 2 + 1];
          if (
            qYesResult?.status === 'success' &&
            qNoResult?.status === 'success'
          ) {
            priceYes = computePriceYes(
              qYesResult.result as bigint,
              qNoResult.result as bigint,
            );
          }
        }

        return (
          <div
            key={market.id}
            className="flex flex-col gap-2 rounded-lg border border-neutral-200 bg-white p-4"
          >
            <div className="flex items-baseline justify-between">
              <span className="text-sm font-semibold text-neutral-900">
                {formatProgramName(market.program)}
              </span>
              <span className="text-xs uppercase tracking-wider text-neutral-500">
                {market.resolutionTarget}
              </span>
            </div>
            <span className="text-sm text-neutral-600">{market.milestone}</span>
            <div className="mt-1 flex items-baseline gap-2">
              {!isDeployed ? (
                <span className="text-sm italic text-neutral-400">
                  Pending deployment
                </span>
              ) : isLoading || priceYes === null ? (
                <span className="text-sm text-neutral-400">Loading…</span>
              ) : (
                <>
                  <span
                    className={`font-mono text-2xl font-semibold ${probabilityClass(priceYes)}`}
                  >
                    {(priceYes * 100).toFixed(1)}%
                  </span>
                  <span className="text-xs text-neutral-500">YES implied</span>
                </>
              )}
            </div>
            {isDeployed && (
              <Link
                href="/markets"
                className="mt-1 text-xs text-neutral-600 underline hover:text-black"
              >
                Trade on Base Sepolia →
              </Link>
            )}
          </div>
        );
      })}
    </div>
  );
}
