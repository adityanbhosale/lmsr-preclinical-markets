// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import { Script } from "forge-std/Script.sol";
import { console } from "forge-std/console.sol";
import { LSLMSR } from "../src/LSLMSR.sol";
import { UD60x18, ud } from "@prb/math/UD60x18.sol";

/// @notice Deploys three LSLMSR markets to Base Sepolia (adagrasib, vepdegestrant, BI-1701963).
contract DeployMultiMarket is Script {
    address constant RESOLVER = 0xeAe842a316c5e96EC02824C4B5A7D030faEFd07C;
    address constant USDC = 0x036CbD53842c5426634e7929541eC2318f3dCF7e;

    function run() external {
        vm.startBroadcast();

        LSLMSR adagrasib = new LSLMSR(
            ud(0.05e18),
            ud(99e18),
            ud(101e18),
            RESOLVER,
            USDC
        );
        console.log("adagrasib Phase 2 deployed at:", address(adagrasib));

        LSLMSR vepdegestrant = new LSLMSR(
            ud(0.05e18),
            ud(97e18),
            ud(103e18),
            RESOLVER,
            USDC
        );
        console.log("vepdegestrant Phase 3 deployed at:", address(vepdegestrant));

        LSLMSR bi1701963 = new LSLMSR(
            ud(0.05e18),
            ud(91e18),
            ud(109e18),
            RESOLVER,
            USDC
        );
        console.log("BI-1701963 approval deployed at:", address(bi1701963));

        vm.stopBroadcast();
    }
}
