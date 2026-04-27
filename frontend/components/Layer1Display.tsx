'use client';

import { useReadContract, useReadContracts } from 'wagmi';
import { CONTRACTS } from '@/lib/contracts';
import { milestoneRegistryAbi } from '@/lib/abi/milestoneRegistry';
import { identityRegistryAbi } from '@/lib/abi/identityRegistry';
import { truncateAddress } from '@/lib/format';

// Hardcoded test investors registered on Layer 1. These match what was
// committed in the Layer 1 deploy session — alice, bob, carol with
// ACCREDITED_INVESTOR claims.
const TEST_INVESTORS = [
  { name: 'alice', address: '0x00000000000000000000000000000000000A11CE' as `0x${string}` },
  { name: 'bob', address: '0x0000000000000000000000000000000000000B0B' as `0x${string}` },
  { name: 'carol', address: '0x00000000000000000000000000000000000Ca401' as `0x${string}` },
] as const;

const MILESTONES = [
  { index: 0, name: 'IND' },
  { index: 1, name: 'Phase 1' },
  { index: 2, name: 'Phase 2' },
  { index: 3, name: 'Approval' },
] as const;

/**
 * Layer1Display — read-only display of the ERC-3643 MilestoneRegistry on
 * Ethereum Sepolia.
 *
 * Demonstrates that the dual-layer architecture is real: the user's wallet
 * is on Base Sepolia (where Layer 2 lives), but this component reads from
 * a different chain entirely without forcing a network switch. Shows the
 * four-token ladder structure and confirms that the compliance layer has
 * populated state (alice, bob, carol all verified).
 */
export function Layer1Display() {
  const baseRegistry = {
    address: CONTRACTS.milestoneRegistry.address,
    abi: milestoneRegistryAbi,
    chainId: CONTRACTS.milestoneRegistry.chainId,
    query: { refetchInterval: 30_000 }, // less frequent — Layer 1 changes rarely
  } as const;

  const { data: programName } = useReadContract({
    ...baseRegistry,
    functionName: 'programName',
  });

  // Read all 4 milestone token addresses in parallel
  const { data: tokenAddresses } = useReadContracts({
    contracts: MILESTONES.map((m) => ({
      ...baseRegistry,
      functionName: 'tokens',
      args: [m.index],
    })),
    query: { refetchInterval: 30_000 },
  });

  // Verify alice/bob/carol — proves the compliance layer is populated
  const { data: verifications } = useReadContracts({
    contracts: TEST_INVESTORS.map((investor) => ({
      address: CONTRACTS.identityRegistry.address,
      abi: identityRegistryAbi,
      chainId: CONTRACTS.identityRegistry.chainId,
      functionName: 'isVerified',
      args: [investor.address],
    })),
    query: { refetchInterval: 30_000 },
  });

  const verifiedCount = verifications?.filter(
    (v) => v.status === 'success' && Boolean(v.result)
  ).length ?? 0;

  return (
    <section className="border border-border rounded-lg p-6 space-y-4">
      <div className="flex items-baseline justify-between">
        <h3 className="text-sm font-semibold tracking-tight">
          Layer 1 — Tokenized SPV
        </h3>
        <span className="text-xs text-muted-foreground">
          on Ethereum Sepolia
        </span>
      </div>

      {/* Program info */}
      <div className="text-xs space-y-1">
        <div className="flex gap-2">
          <span className="text-muted-foreground w-24">Program:</span>
          <span className="font-mono">{programName ?? '—'}</span>
        </div>
        <div className="flex gap-2">
          <span className="text-muted-foreground w-24">Standard:</span>
          <span>ERC-3643 (T-REX)</span>
        </div>
        <div className="flex gap-2">
          <span className="text-muted-foreground w-24">Registry:</span>
          <a
            href={`${CONTRACTS.milestoneRegistry.explorer}/address/${CONTRACTS.milestoneRegistry.address}`}
            target="_blank"
            rel="noopener noreferrer"
            className="font-mono hover:text-foreground transition-colors underline-offset-2 hover:underline"
          >
            {truncateAddress(CONTRACTS.milestoneRegistry.address)}
          </a>
        </div>
      </div>

      {/* Four-token ladder */}
      <div className="pt-3 border-t border-border">
        <div className="text-xs text-muted-foreground mb-2">
          Four-token ladder
        </div>
        <div className="grid grid-cols-2 gap-2 text-xs">
          {MILESTONES.map((milestone, i) => {
            const tokenResult = tokenAddresses?.[i];
            const tokenAddress =
              tokenResult?.status === 'success'
                ? (tokenResult.result as `0x${string}`)
                : undefined;
            return (
              <div
                key={milestone.index}
                className="flex items-center gap-2 py-1"
              >
                <div className="w-1.5 h-1.5 rounded-full bg-orange-500 shrink-0" />
                <span className="font-semibold w-16">{milestone.name}</span>
                {tokenAddress ? (
                  <a
                    href={`${CONTRACTS.milestoneRegistry.explorer}/address/${tokenAddress}`}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="font-mono text-muted-foreground hover:text-foreground transition-colors underline-offset-2 hover:underline truncate"
                  >
                    {truncateAddress(tokenAddress)}
                  </a>
                ) : (
                  <span className="text-muted-foreground">—</span>
                )}
              </div>
            );
          })}
        </div>
      </div>

      {/* Compliance state */}
      <div className="pt-3 border-t border-border">
        <div className="flex justify-between items-center text-xs">
          <span className="text-muted-foreground">
            Accredited investors verified:
          </span>
          <span className="font-semibold tabular-nums">
            {verifiedCount} / {TEST_INVESTORS.length}
          </span>
        </div>
        <div className="text-xs text-muted-foreground/70 italic mt-1 leading-relaxed">
          Compliance state is populated — synthetic accredited investors
          (alice, bob, carol) registered with active claims. Demonstrates
          the identity registry handles the full lifecycle, not just empty
          infrastructure.
        </div>
      </div>
    </section>
  );
}
