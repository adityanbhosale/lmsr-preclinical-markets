/**
 * Minimal ABI for the Layer 1 MilestoneRegistry contract.
 *
 * Used to read the program name + the four milestone token addresses for
 * read-only display on Base Sepolia (the user's wallet stays on Base).
 */
export const milestoneRegistryAbi = [
  {
    type: 'function',
    name: 'programName',
    inputs: [],
    outputs: [{ type: 'string', name: '' }],
    stateMutability: 'view',
  },
  {
    type: 'function',
    name: 'tokens',
    inputs: [{ type: 'uint8', name: '' }],
    outputs: [{ type: 'address', name: '' }],
    stateMutability: 'view',
  },
  {
    type: 'function',
    name: 'identityRegistry',
    inputs: [],
    outputs: [{ type: 'address', name: '' }],
    stateMutability: 'view',
  },
  {
    type: 'function',
    name: 'agent',
    inputs: [],
    outputs: [{ type: 'address', name: '' }],
    stateMutability: 'view',
  },
] as const;
