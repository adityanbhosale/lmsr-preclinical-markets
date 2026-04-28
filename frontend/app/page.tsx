'use client';

import { ConnectButton } from '@rainbow-me/rainbowkit';
import { useAccount, useChainId } from 'wagmi';
import { useEffect, useState } from 'react';
import { MarketHeader } from '@/components/MarketHeader';
import { MarketSelector } from '@/components/MarketSelector';
import { SolvencyIndicator } from '@/components/SolvencyIndicator';
import { PositionCard } from '@/components/PositionCard';
import { TradeForm } from '@/components/TradeForm';
import { Layer1Display } from '@/components/Layer1Display';
import { FaucetPrompt } from '@/components/FaucetPrompt';
import { ArchitectureSidebar } from '@/components/ArchitectureSidebar';
import { CONTRACTS } from '@/lib/contracts';
import { MARKETS, type Market } from '@/lib/markets';
import { truncateAddress } from '@/lib/format';

export default function HomePage() {
  const [mounted, setMounted] = useState(false);
  useEffect(() => setMounted(true), []);

  const [selectedMarketId, setSelectedMarketId] = useState<string>(
    MARKETS[0].id
  );

  const currentMarket: Market =
    MARKETS.find((m) => m.id === selectedMarketId) ?? MARKETS[0];

  const { address, isConnected } = useAccount();
  const chainId = useChainId();

  return (
    <main className="min-h-screen bg-background text-foreground font-mono">
      {/* Top header */}
      <div className="border-b border-border">
        <div className="container flex items-center justify-between py-4">
          <div>
            <h1 className="text-lg font-semibold tracking-tight">
              LMSR Preclinical Markets
            </h1>
            <p className="text-xs text-muted-foreground">
              Dual-layer testnet demo · Base Sepolia + Ethereum Sepolia
            </p>
          </div>
          {mounted && <ConnectButton />}
        </div>
      </div>

      {/* Main content */}
      <div className="container py-8">
        <div className="max-w-2xl mx-auto space-y-5">
          {/* Inline explainer for visitors */}
          <ArchitectureSidebar />

          <MarketSelector
            selectedId={selectedMarketId}
            onSelect={setSelectedMarketId}
          />

          {/* Layer 2 market */}
          <MarketHeader
            marketAddress={currentMarket.address}
            market={currentMarket}
          />
          <SolvencyIndicator marketAddress={currentMarket.address} />

          {/* Trading section — connected wallet only */}
          {mounted && isConnected && <FaucetPrompt />}
          {mounted && (
            <TradeForm
              key={currentMarket.address}
              marketAddress={currentMarket.address}
            />
          )}
          {mounted && (
            <PositionCard marketAddress={currentMarket.address} />
          )}

          {/* Layer 1 read-only display — always visible */}
          <Layer1Display />

          {/* Wallet diagnostic (subtle, only when connected) */}
          {mounted && isConnected && (
            <section className="border border-border rounded-lg p-4 text-xs space-y-1 bg-muted/30">
              <div className="text-muted-foreground font-semibold uppercase tracking-wide">
                Wallet
              </div>
              <div className="flex gap-2">
                <span className="text-muted-foreground w-20">Address:</span>
                <span className="font-mono">
                  {address ? truncateAddress(address) : '—'}
                </span>
              </div>
              <div className="flex gap-2">
                <span className="text-muted-foreground w-20">Chain:</span>
                <span>
                  {chainId === 84532
                    ? 'Base Sepolia ✓'
                    : chainId === 11155111
                      ? 'Ethereum Sepolia (switch to Base Sepolia for trades)'
                      : `${chainId} (unexpected)`}
                </span>
              </div>
            </section>
          )}

          {/* Footer */}
          <footer className="pt-4 text-xs text-muted-foreground space-y-1">
            <div>
              Layer 2 contract:{' '}
              <a
                href={`${CONTRACTS.lslmsr.explorer}/address/${currentMarket.address}`}
                target="_blank"
                rel="noopener noreferrer"
                className="font-mono hover:text-foreground transition-colors underline-offset-2 hover:underline"
              >
                {truncateAddress(currentMarket.address)}
              </a>{' '}
              on Base Sepolia
            </div>
            <div>
              Settlement:{' '}
              <span className="font-mono">
                {truncateAddress(CONTRACTS.usdc.address)}
              </span>{' '}
              (Circle USDC)
            </div>
          </footer>
        </div>
      </div>
    </main>
  );
}
