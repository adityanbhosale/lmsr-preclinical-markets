'use client';

/**
 * <ContractAddress /> — copy-to-clipboard address with explorer link.
 *
 * Usage in MDX:
 *   <ContractAddress
 *     label="LSLMSR V3"
 *     chain="base-sepolia"
 *     address="0xb7Bd56113438961202EcFF985E7Cb2B9F2442475"
 *   />
 */

import { useState } from 'react';

type Chain = 'sepolia' | 'base-sepolia';

const EXPLORERS: Record<Chain, { name: string; base: string }> = {
  sepolia: { name: 'Etherscan', base: 'https://sepolia.etherscan.io/address/' },
  'base-sepolia': { name: 'Basescan', base: 'https://sepolia.basescan.org/address/' },
};

export function ContractAddress({
  label,
  chain,
  address,
}: {
  label: string;
  chain: Chain;
  address: string;
}) {
  const [copied, setCopied] = useState(false);
  const explorer = EXPLORERS[chain];

  const onCopy = async () => {
    await navigator.clipboard.writeText(address);
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  };

  return (
    <div className="not-prose my-3 flex items-center gap-3 rounded-md border border-neutral-200 bg-white px-4 py-3 font-mono text-sm">
      <span className="text-xs font-semibold uppercase tracking-wider text-neutral-500">
        {label}
      </span>
      <code className="flex-1 overflow-hidden text-ellipsis text-neutral-900">
        {address}
      </code>
      <button
        onClick={onCopy}
        className="rounded border border-neutral-300 px-2 py-0.5 text-xs text-neutral-600 transition-colors hover:border-neutral-500 hover:text-black"
      >
        {copied ? '✓ copied' : 'copy'}
      </button>
      <a
        href={`${explorer.base}${address}`}
        target="_blank"
        rel="noopener noreferrer"
        className="text-xs text-neutral-500 hover:text-black transition-colors"
      >
        {explorer.name} ↗
      </a>
    </div>
  );
}
