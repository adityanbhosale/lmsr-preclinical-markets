/**
 * Display-formatting utilities.
 *
 * The contracts use UD60x18 (18-decimal fixed-point) for share quantities
 * and probability, and USDC's native 6-decimal representation for cost
 * settlement. This module centralizes the conversions so each component
 * doesn't reimplement decimal math.
 */

import { formatUnits } from 'viem';

/**
 * UD60x18 (18 decimals) → human-readable share count, like "5.00"
 * Optionally specify number of decimal places (default 2).
 */
export function formatShares(value: bigint, decimals: number = 2): string {
  return parseFloat(formatUnits(value, 18)).toFixed(decimals);
}

/**
 * UD60x18 probability (18 decimals where 1e18 = 100%) → percentage string
 * with the specified number of decimal places. Default 1 decimal.
 *
 * Example: 500_000_000_000_000_000n → "50.0%"
 */
export function formatProbability(value: bigint, decimals: number = 1): string {
  const asFloat = parseFloat(formatUnits(value, 18));
  return `${(asFloat * 100).toFixed(decimals)}%`;
}

/**
 * USDC raw (6 decimals) → human-readable USD string with $ prefix
 * Example: 5_000_000n → "$5.00"
 */
export function formatUsdc(value: bigint, decimals: number = 2): string {
  return `$${parseFloat(formatUnits(value, 6)).toFixed(decimals)}`;
}

/**
 * USDC raw → just the number, no $ symbol. For places where we want
 * "5.00 USDC" with the unit as a separate label.
 */
export function formatUsdcNumber(value: bigint, decimals: number = 2): string {
  return parseFloat(formatUnits(value, 6)).toFixed(decimals);
}

/**
 * Truncate an Ethereum address for display: 0xeAe8...d07C
 */
export function truncateAddress(address: string): string {
  if (!address || address.length < 10) return address;
  return `${address.slice(0, 6)}...${address.slice(-4)}`;
}

/**
 * Solvency calculation — given current state, returns the ratio of
 * available USDC to maximum liability (1 USDC per winning share).
 *
 * Returns:
 *   1.0  → fully solvent (contract holds ≥ max liability)
 *   0.5  → half-collateralized
 *   0.0  → no USDC
 *
 * If the market is unresolved, max liability is `max(qYes, qNo)` since
 * we don't know which side will win. After resolution, max liability is
 * known precisely (= totalWinningShares).
 */
export function computeSolvencyRatio(args: {
  qYes: bigint;
  qNo: bigint;
  usdcBalance: bigint;
  resolved: boolean;
  outcome: boolean;
  totalWinningShares: bigint;
}): number {
  const { qYes, qNo, usdcBalance, resolved, outcome, totalWinningShares } =
    args;

  // Convert UD60x18 shares to USDC-equivalent (1 share = 1 USDC max liability)
  // UD60x18 has 18 decimals; USDC has 6. So divide by 1e12.
  const SCALE = 10n ** 12n;

  const maxLiability = resolved
    ? totalWinningShares / SCALE
    : (qYes > qNo ? qYes : qNo) / SCALE;

  if (maxLiability === 0n) return 1.0;

  // Compute as float (small loss of precision, fine for display)
  const balanceNum = Number(usdcBalance);
  const liabilityNum = Number(maxLiability);
  return balanceNum / liabilityNum;
}

/**
 * Solvency status from ratio — green/yellow/red bucket.
 */
export type SolvencyStatus = 'solvent' | 'partial' | 'undercollateralized';

export function solvencyStatus(ratio: number): SolvencyStatus {
  if (ratio >= 1.0) return 'solvent';
  if (ratio >= 0.5) return 'partial';
  return 'undercollateralized';
}
