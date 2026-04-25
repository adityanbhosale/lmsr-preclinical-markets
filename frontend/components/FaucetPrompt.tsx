'use client';

import { useAccount, useReadContract } from 'wagmi';
import { CONTRACTS } from '@/lib/contracts';
import { erc20Abi } from '@/lib/abi/usdc';

/**
 * FaucetPrompt — appears when a connected wallet has insufficient USDC
 * on Base Sepolia to make even a minimal trade. Provides one-click
 * deep-links to the Circle faucet and Base Sepolia ETH faucet.
 */
export function FaucetPrompt() {
  const { address, isConnected, chain } = useAccount();
  const onCorrectChain = chain?.id === CONTRACTS.lslmsr.chainId;

  const { data: usdcBalance } = useReadContract({
    address: CONTRACTS.usdc.address,
    abi: erc20Abi,
    chainId: CONTRACTS.usdc.chainId,
    functionName: 'balanceOf',
    args: address ? [address] : undefined,
    query: {
      enabled: !!address,
      refetchInterval: 12_000,
    },
  });

  if (!isConnected || !onCorrectChain) return null;

  // Threshold: less than 0.5 USDC = effectively no funds
  // (a single share trade costs ~0.5 USDC at default state)
  const lowBalance =
    usdcBalance !== undefined && usdcBalance < 500_000n;

  if (!lowBalance) return null;

  return (
    <section className="border border-blue-200 bg-blue-50 rounded-lg p-4 text-xs">
      <div className="font-semibold text-blue-900 mb-2">
        Need testnet funds to trade?
      </div>
      <p className="text-blue-700 leading-relaxed mb-3">
        Trades on Base Sepolia require testnet USDC (for the trade) and
        testnet ETH (for gas). Both are free from Circle and Coinbase.
      </p>
      <div className="space-y-1.5">
        <a
          href="https://faucet.circle.com/"
          target="_blank"
          rel="noopener noreferrer"
          className="block text-blue-700 hover:text-blue-900 underline-offset-2 hover:underline"
        >
          → Circle USDC faucet (select "Base Sepolia")
        </a>
        <a
          href="https://www.coinbase.com/faucets/base-ethereum-sepolia-faucet"
          target="_blank"
          rel="noopener noreferrer"
          className="block text-blue-700 hover:text-blue-900 underline-offset-2 hover:underline"
        >
          → Base Sepolia ETH faucet (Coinbase Developer Platform)
        </a>
      </div>
    </section>
  );
}
