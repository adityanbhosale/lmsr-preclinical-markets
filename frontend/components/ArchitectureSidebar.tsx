'use client';

import { useState } from 'react';

/**
 * ArchitectureSidebar — collapsible "What's this?" panel for visitors who
 * land on the page without context. Provides 3 short paragraphs that
 * explain the dual-layer architecture without requiring them to read the
 * README.
 *
 * Defaults to expanded so the explanation is visible on first load.
 * Visitors who already know can collapse it.
 */
export function ArchitectureSidebar() {
  const [expanded, setExpanded] = useState(true);

  return (
    <section className="border border-border rounded-lg p-4 bg-muted/30">
      <button
        type="button"
        onClick={() => setExpanded(!expanded)}
        className="flex items-center justify-between w-full text-left"
      >
        <div className="text-xs font-semibold tracking-tight">
          {expanded ? 'About this demo' : "What's this?"}
        </div>
        <span className="text-xs text-muted-foreground">
          {expanded ? '−' : '+'}
        </span>
      </button>

      {expanded && (
        <div className="text-xs text-muted-foreground space-y-2 mt-3 leading-relaxed">
          <p>
            This is a working testnet implementation of a{' '}
            <span className="font-semibold text-foreground">
              dual-layer prediction market
            </span>{' '}
            for tokenized biotech milestone payment rights. The architecture
            separates legal ownership of the underlying security (Layer 1, an
            ERC-3643 token on Ethereum Sepolia) from price discovery on the
            milestone outcome (Layer 2, an LS-LMSR AMM on Base Sepolia).
          </p>
          <p>
            Outcome shares on Layer 2 reference a public event (FDA approval,
            clinical trial milestone) rather than the security itself, which
            keeps Layer 2 permissionless even though Layer 1 is gated to
            accredited investors. Cross-chain settlement uses Circle's CCTP,
            so USDC remains native on both chains — no wrapped derivative,
            no bridge risk.
          </p>
          <p>
            Trade against the live market below. Every transaction is on
            public testnet infrastructure and verifiable on Basescan and
            Etherscan. Source code:{' '}
            <a
              href="https://github.com/adityanbhosale/lmsr-preclinical-markets"
              target="_blank"
              rel="noopener noreferrer"
              className="font-mono hover:text-foreground underline-offset-2 hover:underline"
            >
              github.com/adityanbhosale/lmsr-preclinical-markets
            </a>
          </p>
        </div>
      )}
    </section>
  );
}
