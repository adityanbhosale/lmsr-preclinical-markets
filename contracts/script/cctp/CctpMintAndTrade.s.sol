// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import { Script, console2 } from "forge-std/Script.sol";
import { UD60x18, ud } from "@prb/math/UD60x18.sol";

/// @notice Minimal CCTP MessageTransmitter interface (V1).
interface IMessageTransmitter {
    /// @notice Verifies the attestation signature and, if valid, forwards the
    ///         message to its target handler (which mints fresh USDC for a
    ///         depositForBurn message).
    /// @param message The original cross-chain message (from the burn tx's
    ///                MessageSent event).
    /// @param attestation Circle's signature over the message hash.
    function receiveMessage(bytes calldata message, bytes calldata attestation)
        external
        returns (bool success);
}

interface IERC20 {
    function approve(address spender, uint256 amount) external returns (bool);
    function balanceOf(address account) external view returns (uint256);
}

interface ILSLMSR {
    function trade(bool isYes, UD60x18 shares) external;
    function costOfTrade(bool isYes, UD60x18 shares) external view returns (UD60x18);
}

/// @title CCTP Mint + Trade — Base Sepolia
/// @notice Step 3 of the CCTP round-trip demo. Receives the attested burn
///         message from Sepolia (which mints 10 USDC to the recipient on
///         Base Sepolia), then uses the freshly-minted USDC to execute a
///         trade on the Layer 2 LS-LMSR prediction market.
contract CctpMintAndTrade is Script {
    // CCTP V1 MessageTransmitter on Base Sepolia
    address constant MESSAGE_TRANSMITTER_BASE = 0x7865fAfC2db2093669d92c0F33AeEF291086BEFD;

    // Base Sepolia USDC (Circle testnet)
    address constant USDC_BASE = 0x036CbD53842c5426634e7929541eC2318f3dCF7e;

    // Layer 2 LS-LMSR V3 contract (deployed earlier)
    address constant LSLMSR_BASE = 0xb7Bd56113438961202EcFF985E7Cb2B9F2442475;

    // Trade parameters: buy 5 YES shares at current market price
    UD60x18 constant TRADE_SHARES = UD60x18.wrap(5e18);

    function run() external {
        uint256 deployerKey = vm.envUint("PRIVATE_KEY");
        address deployer = vm.addr(deployerKey);

        // Expected inputs from the poller + burn tx
        bytes memory message = vm.envBytes("CCTP_MESSAGE");
        bytes memory attestation = vm.envBytes("CCTP_ATTESTATION");

        console2.log("=== CCTP Mint + Trade: Base Sepolia ===");
        console2.log("Recipient:       ", deployer);
        console2.log("");

        uint256 usdcBefore = IERC20(USDC_BASE).balanceOf(deployer);
        console2.log("USDC before mint:", usdcBefore / 1e6);

        vm.startBroadcast(deployerKey);

        // 1. Submit attestation to mint USDC on Base Sepolia
        bool ok = IMessageTransmitter(MESSAGE_TRANSMITTER_BASE).receiveMessage(
            message,
            attestation
        );
        require(ok, "CCTP receiveMessage failed");

        uint256 usdcAfter = IERC20(USDC_BASE).balanceOf(deployer);
        console2.log("USDC after mint: ", usdcAfter / 1e6);

        // 2. Compute cost of the intended trade
        UD60x18 cost = ILSLMSR(LSLMSR_BASE).costOfTrade(true, TRADE_SHARES);
        uint256 costUsdc = cost.unwrap() / 1e12;  // UD60x18 -> 6-decimal
        console2.log("Trade cost USDC: ", costUsdc);

        // 3. Approve LSLMSR to spend USDC
        IERC20(USDC_BASE).approve(LSLMSR_BASE, costUsdc + 1);

        // 4. Execute the trade
        ILSLMSR(LSLMSR_BASE).trade(true, TRADE_SHARES);

        vm.stopBroadcast();

        console2.log("");
        console2.log("=== Trade complete ===");
        console2.log("Purchased 5 YES shares at Layer 2 market");
        console2.log("USDC remaining:  ", IERC20(USDC_BASE).balanceOf(deployer) / 1e6);
    }
}
