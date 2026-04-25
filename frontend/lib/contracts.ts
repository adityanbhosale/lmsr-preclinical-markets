/**
 * On-chain deployment coordinates for the testnet reference implementation.
 *
 * These addresses are the canonical demo target. If you redeploy any layer,
 * update the address here and restart the dev server (env vars + module
 * imports are evaluated once at startup).
 */

import { baseSepolia, sepolia } from 'wagmi/chains';

export const CONTRACTS = {
  // Layer 2 — LS-LMSR market with USDC settlement (Base Sepolia)
  lslmsr: {
    address: '0xb7Bd56113438961202EcFF985E7Cb2B9F2442475' as const,
    chainId: baseSepolia.id,
    explorer: 'https://sepolia.basescan.org',
  },

  // Circle USDC on Base Sepolia (the asset the LSLMSR market settles in)
  usdc: {
    address: '0x036CbD53842c5426634e7929541eC2318f3dCF7e' as const,
    chainId: baseSepolia.id,
    decimals: 6,
  },

  // Layer 1 — ERC-3643 MilestoneRegistry (Ethereum Sepolia)
  milestoneRegistry: {
    address: '0x1488cB83Dc15E677FFd2b5C1010a56a0C7cCa14D' as const,
    chainId: sepolia.id,
    explorer: 'https://sepolia.etherscan.io',
  },

  // Layer 1 — IdentityRegistry (Ethereum Sepolia)
  identityRegistry: {
    address: '0x4f74e2AFDfc46dd3C072EAC5172eC87BE1F8d29B' as const,
    chainId: sepolia.id,
  },
} as const;

/**
 * Static market metadata. The contracts don't store program/milestone
 * names on-chain (only abstract state), so we display them from this map.
 */
export const MARKET_METADATA = {
  program: 'sotorasib',
  milestone: 'IND filing',
  description:
    'Will the Investigational New Drug (IND) application for sotorasib be filed by the target date?',
  resolutionTarget: 'Q4 2026',
  asset: 'KRAS G12C inhibitor (Phase 1 backtest candidate)',
} as const;
