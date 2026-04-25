'use client';

import { useReadContract } from 'wagmi';
import { CONTRACTS } from '@/lib/contracts';
import { lslmsrAbi } from '@/lib/abi/lslmsr';
import { erc20Abi } from '@/lib/abi/usdc';
import {
  computeSolvencyRatio,
  solvencyStatus,
  formatUsdcNumber,
} from '@/lib/format';

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
export function SolvencyIndicator() {
  const baseConfig = {
    address: CONTRACTS.lslmsr.address,
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
    args: [CONTRACTS.lslmsr.address],
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
  const status = solvencyStatus(ratio);

  const statusConfig = {
    solvent: {
      color: 'bg-green-500',
      label: 'Solvent',
      description: `Contract holds ${formatUsdcNumber(usdcBalance)} USDC; max liability is covered.`,
    },
    partial: {
      color: 'bg-yellow-500',
      label: 'Partially collateralized',
      description: `Contract holds ${formatUsdcNumber(usdcBalance)} USDC; resolver must top up before resolution.`,
    },
    undercollateralized: {
      color: 'bg-red-500',
      label: 'Undercollateralized',
      description: `Contract holds ${formatUsdcNumber(usdcBalance)} USDC. resolve() will revert until liquidity is added.`,
    },
  } as const;

  const config = statusConfig[status];

  return (
    <section className="border border-border rounded-lg p-4">
      <div className="flex items-start gap-3">
        <div className={`w-3 h-3 rounded-full mt-1.5 ${config.color}`} />
        <div className="flex-1">
          <div className="flex items-baseline justify-between gap-3">
            <span className="text-sm font-semibold">{config.label}</span>
            <span className="text-xs text-muted-foreground tabular-nums">
              {(ratio * 100).toFixed(0)}% coverage
            </span>
          </div>
          <p className="text-xs text-muted-foreground mt-1 leading-relaxed">
            {config.description}
          </p>
        </div>
      </div>
    </section>
  );
}
