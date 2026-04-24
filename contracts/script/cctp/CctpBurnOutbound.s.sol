// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import { Script, console2 } from "forge-std/Script.sol";

/// @notice Minimal CCTP TokenMessenger interface (V1).
interface ITokenMessenger {
    /// @notice Burns `amount` of USDC on this chain and emits a cross-chain
    ///         message that will mint the same amount on the destination
    ///         chain after Circle attestation.
    /// @param amount Amount to burn (6-decimal USDC units).
    /// @param destinationDomain Circle's internal chain ID for the target chain.
    /// @param mintRecipient Recipient address, left-padded to bytes32.
    /// @param burnToken Address of the USDC contract on this chain.
    /// @return nonce Unique identifier for the cross-chain message.
    function depositForBurn(
        uint256 amount,
        uint32 destinationDomain,
        bytes32 mintRecipient,
        address burnToken
    ) external returns (uint64 nonce);
}

interface IERC20 {
    function approve(address spender, uint256 amount) external returns (bool);
    function balanceOf(address account) external view returns (uint256);
}

/// @title CCTP Burn Script — Sepolia -> Base Sepolia
/// @notice Step 1 of the CCTP round-trip demo. Burns USDC on Ethereum
///         Sepolia, emitting a cross-chain message that Circle's attestation
///         service will sign. The attestation can then be redeemed on Base
///         Sepolia to mint fresh USDC.
contract CctpBurnOutbound is Script {
    // CCTP V1 contracts on Ethereum Sepolia
    address constant TOKEN_MESSENGER_SEPOLIA = 0x9f3B8679c73C2Fef8b59B4f3444d4e156fb70AA5;
    address constant USDC_SEPOLIA            = 0x1c7D4B196Cb0C7B01d743Fbc6116a902379C7238;

    // Circle's domain ID for Base Sepolia (not the EVM chain ID)
    uint32 constant BASE_SEPOLIA_DOMAIN = 6;

    // Amount to burn: 10 USDC (6 decimals)
    uint256 constant AMOUNT = 10 * 10 ** 6;

    function run() external {
        uint256 deployerKey = vm.envUint("PRIVATE_KEY");
        address deployer = vm.addr(deployerKey);

        // CCTP expects the recipient as bytes32 (left-padded address)
        bytes32 mintRecipient = bytes32(uint256(uint160(deployer)));

        console2.log("=== CCTP Burn: Sepolia -> Base Sepolia ===");
        console2.log("Sender/recipient:", deployer);
        console2.log("Amount (USDC):   ", AMOUNT / 1e6);
        console2.log("Destination:     Base Sepolia (domain 6)");
        console2.log("");

        vm.startBroadcast(deployerKey);

        // 1. Approve TokenMessenger to spend USDC
        IERC20(USDC_SEPOLIA).approve(TOKEN_MESSENGER_SEPOLIA, AMOUNT);

        // 2. Burn and emit cross-chain message
        uint64 nonce = ITokenMessenger(TOKEN_MESSENGER_SEPOLIA).depositForBurn(
            AMOUNT,
            BASE_SEPOLIA_DOMAIN,
            mintRecipient,
            USDC_SEPOLIA
        );

        vm.stopBroadcast();

        console2.log("=== Burn complete ===");
        console2.log("Nonce:           ", nonce);
        console2.log("");
        console2.log("Next: wait ~15-20 min for Circle attestation, then");
        console2.log("      node scripts/cctp_poll.js <tx_hash>");
        console2.log("      (tx hash is visible in the broadcast output above)");
    }
}
