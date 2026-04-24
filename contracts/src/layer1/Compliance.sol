// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import { IdentityRegistry } from "./IdentityRegistry.sol";

/// @title Compliance
/// @notice Pluggable module that the MilestoneToken consults on every
///         transfer. Decides whether a transfer is permitted based on the
///         compliance state of sender and recipient.
/// @dev Simplified from full T-REX — implements only the "both parties must
///      hold valid claims" rule. Real compliance modules also enforce daily
///      transfer limits, country restrictions, investor caps, etc.
contract Compliance {
    IdentityRegistry public immutable identityRegistry;

    constructor(IdentityRegistry _identityRegistry) {
        require(
            address(_identityRegistry) != address(0),
            "identity registry zero"
        );
        identityRegistry = _identityRegistry;
    }

    /// @notice Returns true if `from` can send `amount` to `to`.
    /// @dev For MVP: both addresses must be verified in the identity registry.
    ///      The zero address is permitted on one side (mint from zero / burn to zero).
    function canTransfer(address from, address to, uint256 /* amount */)
        external
        view
        returns (bool)
    {
        // Minting: from == address(0), to must be verified
        if (from == address(0)) {
            return identityRegistry.isVerified(to);
        }
        // Burning: to == address(0), from must be verified
        if (to == address(0)) {
            return identityRegistry.isVerified(from);
        }
        // Regular transfer: both must be verified
        return identityRegistry.isVerified(from) && identityRegistry.isVerified(to);
    }
}
