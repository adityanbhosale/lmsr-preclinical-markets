'use client';

import { useAccount, useReadContract } from 'wagmi';
import { CONTRACTS } from '@/lib/contracts';
import { lslmsrAbi } from '@/lib/abi/lslmsr';
import { erc20Abi } from '@/lib/abi/usdc';
import {
  formatShares,
  formatUsdc,
  formatUsdcNumber,
} from '@/lib/format';

export interface PositionCardProps {
  marketAddress: `0x${string}`;
}

/**
 * PositionCard — shows the connected wallet's Layer 2 position and an
 * implied-payout calculation.
 *
 * The implied payout is computed from current market state, not the
 * resolution snapshot — so it shifts as `qYes` or the contract's USDC
 * pool change. This is the right framing for an unresolved market: it's
 * "what would I claim if this resolved RIGHT NOW," not a guarantee.
 */
export function PositionCard({ marketAddress }: PositionCardProps) {
  const { address, isConnected } = useAccount();

  const baseConfig = {
    address: marketAddress,
    abi: lslmsrAbi,
    chainId: CONTRACTS.lslmsr.chainId,
    query: {
      refetchInterval: 12_000,
      enabled: isConnected && !!address,
    },
  } as const;

  // Read user's position from the LSLMSR contract
  const { data: position } = useReadContract({
    ...baseConfig,
    functionName: 'positions',
    args: address ? [address] : undefined,
  });

  // Read user's USDC balance on Base Sepolia
  const { data: usdcBalance } = useReadContract({
    address: CONTRACTS.usdc.address,
    abi: erc20Abi,
    chainId: CONTRACTS.usdc.chainId,
    functionName: 'balanceOf',
    args: address ? [address] : undefined,
    query: {
      refetchInterval: 12_000,
      enabled: isConnected && !!address,
    },
  });

  // Read state for implied payout calculation
  const { data: qYes } = useReadContract({
    ...baseConfig,
    functionName: 'qYes',
  });
  const { data: marketUsdcBalance } = useReadContract({
    address: CONTRACTS.usdc.address,
    abi: erc20Abi,
    chainId: CONTRACTS.usdc.chainId,
    functionName: 'balanceOf',
    args: [marketAddress],
    query: { refetchInterval: 12_000 },
  });

  if (!isConnected) {
    return null;
  }

  const yesShares = position?.[0] ?? 0n;
  const noShares = position?.[1] ?? 0n;
  const hasPosition = yesShares > 0n || noShares > 0n;

  // Implied payout: if YES resolves with current state, this wallet receives
  // (yesShares / qYes) × marketUsdcBalance. UD60x18 division → multiply →
  // convert to USDC 6-decimal.
  let impliedPayoutIfYes: bigint = 0n;
  if (
    yesShares > 0n &&
    qYes !== undefined &&
    qYes > 0n &&
    marketUsdcBalance !== undefined
  ) {
    // (yesShares * marketUsdcBalance * 1e6) / (qYes * 1e6) → simplifies to
    // (yesShares * marketUsdcBalance) / qYes, with USDC already at 6 decimals
    impliedPayoutIfYes = (yesShares * marketUsdcBalance) / qYes;
  }

  return (
    <section className="border border-border rounded-lg p-6 space-y-4">
      <div className="flex items-baseline justify-between">
        <h3 className="text-sm font-semibold tracking-tight">Your position</h3>
        <span className="text-xs text-muted-foreground">
          on Base Sepolia
        </span>
      </div>

      {!hasPosition ? (
        <div className="text-xs text-muted-foreground py-2">
          No position yet. Buy YES or NO shares below to take a position
          on the market.
        </div>
      ) : (
        <div className="grid grid-cols-2 gap-4 text-xs">
          <div className="space-y-1">
            <div className="text-muted-foreground">YES shares</div>
            <div className="text-base font-semibold tabular-nums">
              {formatShares(yesShares, 2)}
            </div>
          </div>
          <div className="space-y-1">
            <div className="text-muted-foreground">NO shares</div>
            <div className="text-base font-semibold tabular-nums">
              {formatShares(noShares, 2)}
            </div>
          </div>
        </div>
      )}

      <div className="pt-3 border-t border-border space-y-2 text-xs">
        <div className="flex justify-between">
          <span className="text-muted-foreground">USDC balance:</span>
          <span className="font-mono tabular-nums">
            {usdcBalance !== undefined
              ? `${formatUsdcNumber(usdcBalance)} USDC`
              : '—'}
          </span>
        </div>
        {hasPosition && (
          <div className="flex justify-between">
            <span className="text-muted-foreground">
              Implied payout if YES wins:
            </span>
            <span className="font-mono tabular-nums text-green-700">
              {formatUsdc(impliedPayoutIfYes)}
            </span>
          </div>
        )}
        {hasPosition && (
          <div className="text-muted-foreground/70 italic pt-1 leading-relaxed">
            Calculated as (your YES shares ÷ qYes) × contract USDC pool.
            Updates as the market state shifts.
          </div>
        )}
      </div>
    </section>
  );
}
