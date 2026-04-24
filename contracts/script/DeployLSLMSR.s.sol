// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import { Script, console2 } from "forge-std/Script.sol";
import { LSLMSR } from "../src/LSLMSR.sol";
import { UD60x18, ud } from "@prb/math/UD60x18.sol";

/// @title LSLMSR Deployment Script
/// @notice Deploys a binary LS-LMSR market to Base Sepolia with
///         symmetric ABMM seeding, the deployer as the resolver stub,
///         and Circle's testnet USDC as the settlement token.
contract DeployLSLMSR is Script {
    /// @notice Circle's testnet USDC on Base Sepolia.
    address constant BASE_SEPOLIA_USDC = 0x036CbD53842c5426634e7929541eC2318f3dCF7e;

    function run() external returns (LSLMSR market) {
        uint256 deployerKey = vm.envUint("PRIVATE_KEY");
        address deployer = vm.addr(deployerKey);

        // Constructor params — match the defaults from your test harness
        UD60x18 alpha     = ud(0.05e18);   // α = 0.05 (liquidity scaling)
        UD60x18 qAbmmYes  = ud(100e18);    // 100 YES seed shares
        UD60x18 qAbmmNo   = ud(100e18);    // 100 NO seed shares
        address resolver  = deployer;      // Admin-attested resolver for MVP

        vm.startBroadcast(deployerKey);
        market = new LSLMSR(
            alpha,
            qAbmmYes,
            qAbmmNo,
            resolver,
            BASE_SEPOLIA_USDC
        );
        vm.stopBroadcast();

        console2.log("=== LSLMSR Deployment ===");
        console2.log("Contract:     ", address(market));
        console2.log("Deployer:     ", deployer);
        console2.log("Resolver:     ", resolver);
        console2.log("USDC token:   ", BASE_SEPOLIA_USDC);
        console2.log("alpha (1e18): ", alpha.unwrap());
        console2.log("q_yes (1e18): ", qAbmmYes.unwrap());
        console2.log("q_no  (1e18): ", qAbmmNo.unwrap());
        console2.log("priceYes init:", market.priceYes().unwrap());
    }
}
