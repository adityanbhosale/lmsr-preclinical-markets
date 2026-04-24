// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

// STATUS: deferred. Return leg pending sufficient Base Sepolia USDC
// liquidity to satisfy solvency check (>= 105 USDC). See docs/cctp-demo.md
// for resumption instructions. Do not execute in isolation — must follow
// a successful outbound demo run.

import { Script, console2 } from "forge-std/Script.sol";

interface IERC20 {
    function approve(address spender, uint256 amount) external returns (bool);
    function balanceOf(address account) external view returns (uint256);
}

interface ILSLMSR {
    function depositLiquidity(uint256 amount) external;
    function resolve(bool outcome) external;
    function claim() external;
    function qYes() external view returns (uint256);
    function qNo() external view returns (uint256);
    function resolved() external view returns (bool);
}

interface ITokenMessenger {
    function depositForBurn(
        uint256 amount,
        uint32 destinationDomain,
        bytes32 mintRecipient,
        address burnToken
    ) external returns (uint64 nonce);
}

/// @title CCTP Resolve + Claim + Return Burn — Base Sepolia
/// @notice Step 4 of the CCTP round-trip demo. Top-up liquidity on the
///         Layer 2 market, resolve YES, claim the proportional payout, and
///         then burn the payout via CCTP back to Ethereum Sepolia.
/// @dev Note: in production the resolver and the trader are independent
///      parties; here the deployer plays both roles for demo self-containment.
///      The mechanical property demonstrated is the CCTP round-trip with
///      claim payout, not the market dynamics.
contract CctpResolveClaimReturn is Script {
    address constant USDC_BASE     = 0x036CbD53842c5426634e7929541eC2318f3dCF7e;
    address constant LSLMSR_BASE   = 0xb7Bd56113438961202EcFF985E7Cb2B9F2442475;
    address constant TOKEN_MESSENGER_BASE = 0x9f3B8679c73C2Fef8b59B4f3444d4e156fb70AA5;

    // Circle's domain ID for Ethereum Sepolia
    uint32 constant SEPOLIA_DOMAIN = 0;

    function run() external {
        uint256 deployerKey = vm.envUint("PRIVATE_KEY");
        address deployer = vm.addr(deployerKey);

        console2.log("=== CCTP Resolve + Claim + Return Burn ===");
        console2.log("Deployer:        ", deployer);
        console2.log("");

        ILSLMSR market = ILSLMSR(LSLMSR_BASE);

        // Sanity check: make sure we're not already resolved (idempotency safety)
        require(!market.resolved(), "market already resolved");

        vm.startBroadcast(deployerKey);

        // 1. Top up liquidity to cover max liability (qYes * 1 USDC)
        // With the ABMM at 100 and our 5-share trade, qYes = 105 now.
        // Need >= 105 USDC. Deposit 150 for safety.
        uint256 needed = 150 * 1e6;
        IERC20(USDC_BASE).approve(LSLMSR_BASE, needed);
        market.depositLiquidity(needed);
        console2.log("Liquidity deposited:", needed / 1e6, "USDC");

        // 2. Resolve YES
        market.resolve(true);
        console2.log("Market resolved:    YES");

        // 3. Claim winnings
        uint256 usdcBeforeClaim = IERC20(USDC_BASE).balanceOf(deployer);
        market.claim();
        uint256 usdcAfterClaim = IERC20(USDC_BASE).balanceOf(deployer);
        uint256 payout = usdcAfterClaim - usdcBeforeClaim;
        console2.log("Claim payout:      ", payout / 1e6, "USDC (approx)");

        // 4. Burn the payout via CCTP back to Sepolia
        bytes32 mintRecipient = bytes32(uint256(uint160(deployer)));
        IERC20(USDC_BASE).approve(TOKEN_MESSENGER_BASE, payout);
        uint64 nonce = ITokenMessenger(TOKEN_MESSENGER_BASE).depositForBurn(
            payout,
            SEPOLIA_DOMAIN,
            mintRecipient,
            USDC_BASE
        );

        vm.stopBroadcast();

        console2.log("");
        console2.log("=== Return burn initiated ===");
        console2.log("Burned for return: ", payout / 1e6, "USDC");
        console2.log("Nonce:             ", nonce);
        console2.log("");
        console2.log("Next: wait ~15-20 min for attestation, then");
        console2.log("      node scripts/cctp_poll.js <return_tx_hash> base-sepolia");
        console2.log("      forge script script/cctp/CctpFinalMint.s.sol ...");
    }
}
