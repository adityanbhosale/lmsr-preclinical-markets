/**
 * Minimal ABI for the LSLMSR V3 contract.
 *
 * Includes only the read functions and write functions Phase 2-4 need.
 * Full ABI lives in contracts/out/LSLMSR.sol/LSLMSR.json after `forge build`;
 * we manually transcribe the relevant subset here to keep the bundle small.
 *
 * `as const` is critical — wagmi's type inference requires the literal
 * shape, not a generic Abi type.
 */
export const lslmsrAbi = [
  // ─────────────────────────────────────────────────────────────
  // State reads
  // ─────────────────────────────────────────────────────────────
  {
    type: 'function',
    name: 'qYes',
    inputs: [],
    outputs: [{ type: 'uint256', name: '' }],
    stateMutability: 'view',
  },
  {
    type: 'function',
    name: 'qNo',
    inputs: [],
    outputs: [{ type: 'uint256', name: '' }],
    stateMutability: 'view',
  },
  {
    type: 'function',
    name: 'alpha',
    inputs: [],
    outputs: [{ type: 'uint256', name: '' }],
    stateMutability: 'view',
  },
  {
    type: 'function',
    name: 'resolved',
    inputs: [],
    outputs: [{ type: 'bool', name: '' }],
    stateMutability: 'view',
  },
  {
    type: 'function',
    name: 'outcome',
    inputs: [],
    outputs: [{ type: 'bool', name: '' }],
    stateMutability: 'view',
  },
  {
    type: 'function',
    name: 'resolver',
    inputs: [],
    outputs: [{ type: 'address', name: '' }],
    stateMutability: 'view',
  },
  {
    type: 'function',
    name: 'usdc',
    inputs: [],
    outputs: [{ type: 'address', name: '' }],
    stateMutability: 'view',
  },
  {
    type: 'function',
    name: 'totalWinningShares',
    inputs: [],
    outputs: [{ type: 'uint256', name: '' }],
    stateMutability: 'view',
  },
  {
    type: 'function',
    name: 'resolutionBalance',
    inputs: [],
    outputs: [{ type: 'uint256', name: '' }],
    stateMutability: 'view',
  },

  // ─────────────────────────────────────────────────────────────
  // Computed views
  // ─────────────────────────────────────────────────────────────
  {
    type: 'function',
    name: 'priceYes',
    inputs: [],
    outputs: [{ type: 'uint256', name: '' }],
    stateMutability: 'view',
  },
  {
    type: 'function',
    name: 'b',
    inputs: [],
    outputs: [{ type: 'uint256', name: '' }],
    stateMutability: 'view',
  },
  {
    type: 'function',
    name: 'cost',
    inputs: [],
    outputs: [{ type: 'uint256', name: '' }],
    stateMutability: 'view',
  },
  {
    type: 'function',
    name: 'costOfTrade',
    inputs: [
      { type: 'bool', name: 'isYes' },
      { type: 'uint256', name: 'shares' },
    ],
    outputs: [{ type: 'uint256', name: '' }],
    stateMutability: 'view',
  },

  // ─────────────────────────────────────────────────────────────
  // Per-trader state
  // ─────────────────────────────────────────────────────────────
  {
    type: 'function',
    name: 'positions',
    inputs: [{ type: 'address', name: '' }],
    outputs: [
      { type: 'uint256', name: 'yesShares' },
      { type: 'uint256', name: 'noShares' },
    ],
    stateMutability: 'view',
  },
  {
    type: 'function',
    name: 'claimed',
    inputs: [{ type: 'address', name: '' }],
    outputs: [{ type: 'bool', name: '' }],
    stateMutability: 'view',
  },

  // ─────────────────────────────────────────────────────────────
  // Writes (Phase 4 will use these)
  // ─────────────────────────────────────────────────────────────
  {
    type: 'function',
    name: 'trade',
    inputs: [
      { type: 'bool', name: 'isYes' },
      { type: 'uint256', name: 'shares' },
    ],
    outputs: [],
    stateMutability: 'nonpayable',
  },
  {
    type: 'function',
    name: 'claim',
    inputs: [],
    outputs: [],
    stateMutability: 'nonpayable',
  },
  {
    type: 'function',
    name: 'depositLiquidity',
    inputs: [{ type: 'uint256', name: 'amount' }],
    outputs: [],
    stateMutability: 'nonpayable',
  },
] as const;
