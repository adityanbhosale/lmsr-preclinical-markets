'use client';

import { MARKETS } from '@/lib/markets';

export interface MarketSelectorProps {
  selectedId: string;
  onSelect: (id: string) => void;
}

export function MarketSelector({ selectedId, onSelect }: MarketSelectorProps) {
  return (
    <div className="flex flex-row flex-wrap gap-2">
      {MARKETS.map((market) => {
        const isActive = market.id === selectedId;
        return (
          <button
            key={market.id}
            type="button"
            onClick={() => onSelect(market.id)}
            className={`px-3 py-2 rounded-lg text-left font-mono transition-colors ${
              isActive
                ? 'bg-zinc-100 dark:bg-zinc-800 ring-1 ring-zinc-300 dark:ring-zinc-700 font-medium'
                : 'bg-transparent border border-zinc-200 dark:border-zinc-700'
            }`}
          >
            <div className="text-sm font-semibold tracking-tight">
              {market.program}
            </div>
            <div className="text-xs text-muted-foreground">{market.milestone}</div>
          </button>
        );
      })}
    </div>
  );
}
