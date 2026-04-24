// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import { Script, console2 } from "forge-std/Script.sol";
import { ClaimTopicsRegistry } from "../src/layer1/ClaimTopicsRegistry.sol";
import { IdentityRegistry } from "../src/layer1/IdentityRegistry.sol";
import { Compliance } from "../src/layer1/Compliance.sol";
import { MilestoneRegistry } from "../src/layer1/MilestoneRegistry.sol";

/// @title Layer 1 Deployment Script
/// @notice Deploys the full ERC-3643-style permissioned token suite to
///         Ethereum Sepolia: ClaimTopicsRegistry, IdentityRegistry,
///         Compliance, and a MilestoneRegistry that spawns four
///         MilestoneTokens (IND / Phase 1 / Phase 2 / Approval).
contract DeployLayer1 is Script {
    /// @notice The biotech program this Layer 1 instance represents.
    /// @dev Using one of your four backtested candidates. Change per deploy.
    string constant PROGRAM_NAME = "sotorasib";

    function run() external {
        uint256 deployerKey = vm.envUint("PRIVATE_KEY");
        address deployer = vm.addr(deployerKey);

        vm.startBroadcast(deployerKey);

        // Step 1: Deploy ClaimTopicsRegistry
        // Registers ACCREDITED_INVESTOR (topic ID 1) as the single required claim.
        ClaimTopicsRegistry claimTopics = new ClaimTopicsRegistry();

        // Step 2: Deploy IdentityRegistry, wiring the topics registry in.
        // Deployer becomes the trusted issuer (can register/issue/revoke).
        IdentityRegistry identityRegistry = new IdentityRegistry(
            deployer,
            claimTopics
        );

        // Step 3: Deploy Compliance, which consults the identity registry.
        Compliance compliance = new Compliance(identityRegistry);

        // Step 4: Deploy MilestoneRegistry. Its constructor spawns the four
        // MilestoneTokens under the shared identity + compliance infrastructure.
        MilestoneRegistry milestoneRegistry = new MilestoneRegistry(
            PROGRAM_NAME,
            deployer,
            identityRegistry,
            compliance
        );

        vm.stopBroadcast();

        console2.log("=== Layer 1 Deployment (Ethereum Sepolia) ===");
        console2.log("Program:            ", PROGRAM_NAME);
        console2.log("Deployer:           ", deployer);
        console2.log("");
        console2.log("ClaimTopicsRegistry:", address(claimTopics));
        console2.log("IdentityRegistry:   ", address(identityRegistry));
        console2.log("Compliance:         ", address(compliance));
        console2.log("MilestoneRegistry:  ", address(milestoneRegistry));
        console2.log("");
        console2.log("Milestone tokens (spawned by MilestoneRegistry):");
        console2.log("  IND:             ", address(milestoneRegistry.tokens(MilestoneRegistry.Milestone.IND)));
        console2.log("  Phase 1:         ", address(milestoneRegistry.tokens(MilestoneRegistry.Milestone.Phase1)));
        console2.log("  Phase 2:         ", address(milestoneRegistry.tokens(MilestoneRegistry.Milestone.Phase2)));
        console2.log("  Approval:        ", address(milestoneRegistry.tokens(MilestoneRegistry.Milestone.Approval)));
    }
}
