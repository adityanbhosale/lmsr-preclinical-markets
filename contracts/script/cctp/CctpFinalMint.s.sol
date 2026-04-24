// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

// STATUS: deferred. Return leg pending sufficient Base Sepolia USDC
// liquidity to satisfy solvency check (>= 105 USDC). See docs/cctp-demo.md
// for resumption instructions. Do not execute in isolation — must follow
// a successful outbound demo run.

import { Script, console2 } from "forge-std/Script.sol";

interface IMessageTransmitter {
    function receiveMessage(bytes calldata message, bytes calldata attestation)
        external
        returns (bool success);
}

interface IERC20 {
    function balanceOf(address account) external view returns (uint256);
}

/// @title CCTP Final Mint — closes the round-trip on Sepolia
/// @notice Step 6 (final) of the CCTP round-trip demo. Redeems the return
///         attestation on Ethereum Sepolia, minting the claim-payout USDC
///         back on the chain where it started.
contract CctpFinalMint is Script {
    address constant MESSAGE_TRANSMITTER_SEPOLIA = 0x7865fAfC2db2093669d92c0F33AeEF291086BEFD;
    address constant USDC_SEPOLIA                = 0x1c7D4B196Cb0C7B01d743Fbc6116a902379C7238;

    function run() external {
        uint256 deployerKey = vm.envUint("PRIVATE_KEY");
        address deployer = vm.addr(deployerKey);

        bytes memory message = vm.envBytes("CCTP_MESSAGE");
        bytes memory attestation = vm.envBytes("CCTP_ATTESTATION");

        console2.log("=== CCTP Final Mint: Base Sepolia -> Sepolia ===");
        console2.log("Recipient:       ", deployer);
        console2.log("");

        uint256 before = IERC20(USDC_SEPOLIA).balanceOf(deployer);
        console2.log("USDC before mint:", before / 1e6);

        vm.startBroadcast(deployerKey);
        bool ok = IMessageTransmitter(MESSAGE_TRANSMITTER_SEPOLIA)
            .receiveMessage(message, attestation);
        require(ok, "CCTP receiveMessage failed");
        vm.stopBroadcast();

        uint256 afterAmt = IERC20(USDC_SEPOLIA).balanceOf(deployer);
        console2.log("USDC after mint: ", afterAmt / 1e6);
        console2.log("Net received:    ", (afterAmt - before) / 1e6, "USDC");
        console2.log("");
        console2.log("=== Round-trip complete ===");
    }
}
