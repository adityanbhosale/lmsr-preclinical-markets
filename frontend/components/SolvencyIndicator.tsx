'use client';

import { useReadContract } from 'wagmi';
import { CONTRACTS } from '@/lib/contracts';
import { lslmsrAbi } from '@/lib/abi/lslmsr';
import { erc20Abi } from '@/lib/abi/usdc';
import { computeSolvencyRatio, formatUsdcNumber } from '@/lib/format';

export interface SolvencyIndicatorProps {
  marketAddress: `0x${string}`;
}

type CoverageTier = 'full' | 'partial' | 'limited' | 'none';

/** Buckets match the displayed "(ratio * 100).toFixed(0)% coverage" rounding. */
function coverageTier(ratio: number): CoverageTier {
  const pct = Math.round(ratio * 100);
  if (pct >= 100) return 'full';
  if (pct >= 50) return 'partial';
  if (pct >= 1) return 'limited';
  return 'none';
}

/**
 * SolvencyIndicator — visible-product-property version of the
 * "structural solvency guarantee" architectural claim.
 *
 * Computes whether the contract holds enough USDC to cover its maximum
 * liability (1 USDC per winning share) and renders a colored status badge.
 *
 * Pre-resolution: max liability = max(qYes, qNo)
 * Post-resolution: max liability = totalWinningShares
 */
export function SolvencyIndicator({ marketAddress }: SolvencyIndicatorProps) {
  const baseConfig = {
    address: marketAddress,
    abi: lslmsrAbi,
    chainId: CONTRACTS.lslmsr.chainId,
    query: { refetchInterval: 12_000 },
  } as const;

  const { data: qYes } = useReadContract({
    ...baseConfig,
    functionName: 'qYes',
  });
  const { data: qNo } = useReadContract({
    ...baseConfig,
    functionName: 'qNo',
  });
  const { data: resolved } = useReadContract({
    ...baseConfig,
    functionName: 'resolved',
  });
  const { data: outcome } = useReadContract({
    ...baseConfig,
    functionName: 'outcome',
  });
  const { data: totalWinningShares } = useReadContract({
    ...baseConfig,
    functionName: 'totalWinningShares',
  });

  // The market's USDC balance — read from the USDC contract
  const { data: usdcBalance } = useReadContract({
    address: CONTRACTS.usdc.address,
    abi: erc20Abi,
    chainId: CONTRACTS.usdc.chainId,
    functionName: 'balanceOf',
    args: [marketAddress],
    query: { refetchInterval: 12_000 },
  });

  // If any required value is undefined, render placeholder
  const dataReady =
    qYes !== undefined &&
    qNo !== undefined &&
    resolved !== undefined &&
    outcome !== undefined &&
    totalWinningShares !== undefined &&
    usdcBalance !== undefined;

  if (!dataReady) {
    return (
      <section className="border border-border rounded-lg p-4">
        <div className="flex items-center gap-3">
          <div className="w-3 h-3 rounded-full bg-gray-300 animate-pulse" />
          <div className="text-sm text-muted-foreground">
            Loading solvency status...
          </div>
        </div>
      </section>
    );
  }

  const ratio = computeSolvencyRatio({
    qYes,
    qNo,
    usdcBalance,
    resolved,
    outcome,
    totalWinningShares,
  });
  const tier = coverageTier(ratio);

  const tierConfig = {
    full: {
      dot: 'bg-green-500',
      label: 'Fully collateralized',
      labelText: 'text-green-800 dark:text-green-400',
    },
    partial: {
      dot: 'bg-yellow-500',
      label: 'Partially collateralized',
      labelText: 'text-yellow-800 dark:text-yellow-400',
    },
    limited: {
      dot: 'bg-orange-500',
      label: 'Limited liquidity',
      labelText: 'text-orange-800 dark:text-orange-400',
    },
    none: {
      dot: 'bg-red-500',
      label: 'Uncollateralized',
      labelText: 'text-red-800 dark:text-red-400',
    },
  } as const;

  const { dot, label, labelText } = tierConfig[tier];

  const usdcStr = formatUsdcNumber(usdcBalance);
  const description =
    Math.round(ratio * 100) >= 100
      ? `Contract holds ${usdcStr} USDC; max liability is covered.`
      : `Contract holds ${usdcStr} USDC; max liability is not fully covered. resolve() will revert until liquidity is added.`;

  return (
    <section className="border border-border rounded-lg p-4">
      <div className="flex items-start gap-3">
        <div className={`w-3 h-3 rounded-full mt-1.5 ${dot}`} />
        <div className="flex-1">
          <div className="flex items-baseline justify-between gap-3">
            <span className={`text-sm font-semibold ${labelText}`}>
              {label}
            </span>
            <span className="text-xs text-muted-foreground tabular-nums">
              {(ratio * 100).toFixed(0)}% coverage
            </span>
          </div>
          <p className="text-xs text-muted-foreground mt-1 leading-relaxed">
            {description}
          </p>
        </div>
      </div>
    </section>
  );
}
