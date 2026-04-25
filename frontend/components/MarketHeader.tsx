'use client';

import { useReadContract } from 'wagmi';
import { CONTRACTS, MARKET_METADATA } from '@/lib/contracts';
import { lslmsrAbi } from '@/lib/abi/lslmsr';
import { formatProbability, formatShares } from '@/lib/format';

/**
 * Hero component — displays the current YES probability prominently,
 * along with market metadata (program, milestone, target date) and the
 * raw `qYes` / `qNo` / `α` state for transparency.
 *
 * Polls every 12 seconds (matching Base Sepolia's typical block time).
 */
export function MarketHeader() {
  const baseConfig = {
    address: CONTRACTS.lslmsr.address,
    abi: lslmsrAbi,
    chainId: CONTRACTS.lslmsr.chainId,
    query: { refetchInterval: 12_000 },
  } as const;

  const { data: priceYes, isLoading: priceLoading } = useReadContract({
    ...baseConfig,
    functionName: 'priceYes',
  });
  const { data: qYes } = useReadContract({
    ...baseConfig,
    functionName: 'qYes',
  });
  const { data: qNo } = useReadContract({
    ...baseConfig,
    functionName: 'qNo',
  });
  const { data: alpha } = useReadContract({
    ...baseConfig,
    functionName: 'alpha',
  });
  const { data: resolved } = useReadContract({
    ...baseConfig,
    functionName: 'resolved',
  });
  const { data: outcome } = useReadContract({
    ...baseConfig,
    functionName: 'outcome',
  });

  return (
    <section className="border border-border rounded-lg p-6 space-y-6">
      {/* Market metadata */}
      <div>
        <div className="flex items-baseline gap-3 mb-1">
          <h2 className="text-base font-semibold tracking-tight">
            {MARKET_METADATA.program}
          </h2>
          <span className="text-xs text-muted-foreground">
            · {MARKET_METADATA.milestone}
          </span>
          {resolved && (
            <span className={`text-xs px-2 py-0.5 rounded ${
              outcome
                ? 'bg-green-100 text-green-800'
                : 'bg-red-100 text-red-800'
            }`}>
              RESOLVED {outcome ? 'YES' : 'NO'}
            </span>
          )}
        </div>
        <p className="text-xs text-muted-foreground leading-relaxed">
          {MARKET_METADATA.description}
        </p>
      </div>

      {/* Hero probability */}
      <div className="flex items-baseline gap-4 pt-2 border-t border-border">
        <div>
          <div className="text-xs text-muted-foreground mb-1">
            implied YES probability
          </div>
          <div className="text-5xl font-bold tabular-nums tracking-tight">
            {priceLoading || priceYes === undefined
              ? '—'
              : formatProbability(priceYes, 1)}
          </div>
        </div>
        <div className="ml-auto text-xs text-muted-foreground text-right">
          <div>Resolution target</div>
          <div className="font-semibold text-foreground">
            {MARKET_METADATA.resolutionTarget}
          </div>
        </div>
      </div>

      {/* Raw state readout */}
      <div className="grid grid-cols-3 gap-4 pt-4 border-t border-border text-xs">
        <div>
          <div className="text-muted-foreground mb-1">qYes</div>
          <div className="font-mono tabular-nums">
            {qYes !== undefined ? formatShares(qYes, 2) : '—'}
          </div>
        </div>
        <div>
          <div className="text-muted-foreground mb-1">qNo</div>
          <div className="font-mono tabular-nums">
            {qNo !== undefined ? formatShares(qNo, 2) : '—'}
          </div>
        </div>
        <div>
          <div className="text-muted-foreground mb-1">α (alpha)</div>
          <div className="font-mono tabular-nums">
            {alpha !== undefined ? formatShares(alpha, 4) : '—'}
          </div>
        </div>
      </div>
    </section>
  );
}
