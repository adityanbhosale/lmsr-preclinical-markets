/**
 * Minimal ABI for the Layer 1 IdentityRegistry contract.
 *
 * Used to verify that registered investors hold valid accreditation claims
 * — demonstrates that the compliance layer has populated state, not just
 * empty infrastructure.
 */
export const identityRegistryAbi = [
  {
    type: 'function',
    name: 'isVerified',
    inputs: [{ type: 'address', name: 'investor' }],
    outputs: [{ type: 'bool', name: '' }],
    stateMutability: 'view',
  },
  {
    type: 'function',
    name: 'isRegistered',
    inputs: [{ type: 'address', name: '' }],
    outputs: [{ type: 'bool', name: '' }],
    stateMutability: 'view',
  },
  {
    type: 'function',
    name: 'trustedIssuer',
    inputs: [],
    outputs: [{ type: 'address', name: '' }],
    stateMutability: 'view',
  },
] as const;
