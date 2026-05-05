// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import "forge-std/Script.sol";
import "forge-std/console.sol";
import {UD60x18, ud, unwrap} from "@prb/math/UD60x18.sol";
import {IERC20} from "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import {LSLMSR} from "../src/LSLMSR.sol";

/**
 * Generate parity fixture by deploying a fresh LSLMSR on the local fork
 * and executing a deterministic trade sequence. Writes JSON to:
 *   sim/tests/fixtures/parity_run.json
 *
 * Run with:
 *   forge script script/GenerateParityFixture.s.sol \
 *     --rpc-url http://localhost:8545 \
 *     --broadcast \
 *     --unlocked \
 *     --sender <USDC_HOLDER_ON_BASE_SEPOLIA>
 *
 * Requires anvil forking Base Sepolia at a block where the sender has USDC.
 * Easiest path: use a known testnet USDC holder address as --sender, or
 * deal USDC to a test account using vm.deal + a USDC mock.
 */
contract GenerateParityFixture is Script {
    // Base Sepolia USDC
    address constant USDC = 0x036CbD53842c5426634e7929541eC2318f3dCF7e;

    // resolver — any address; doesn't matter for parity (we don't resolve)
    address constant RESOLVER = address(0xDEADBEEF);

    // deterministic config (modest values to avoid USDC-balance issues on the fork)
    UD60x18 ALPHA;
    UD60x18 Q_ABMM_YES;
    UD60x18 Q_ABMM_NO;

    // 20 deterministic trades: (isYes, shares as UD60x18)
    struct Trade {
        bool isYes;
        uint256 sharesWei;
    }

    function run() external {
        ALPHA = ud(0.05e18);
        Q_ABMM_YES = ud(500e18);
        Q_ABMM_NO = ud(500e18);

        Trade[20] memory trades = [
            Trade(true, 10e18),
            Trade(false, 5e18),
            Trade(true, 15e18),
            Trade(false, 20e18),
            Trade(true, 3e18),
            Trade(false, 8e18),
            Trade(true, 25e18),
            Trade(false, 12e18),
            Trade(true, 7e18),
            Trade(false, 18e18),
            Trade(true, 4e18),
            Trade(false, 6e18),
            Trade(true, 30e18),
            Trade(false, 9e18),
            Trade(true, 11e18),
            Trade(false, 14e18),
            Trade(true, 2e18),
            Trade(false, 22e18),
            Trade(true, 16e18),
            Trade(false, 5e18)
        ];

        vm.startBroadcast();

        

        // deploy fresh market
        LSLMSR market = new LSLMSR(
            ALPHA,
            Q_ABMM_YES,
            Q_ABMM_NO,
            RESOLVER,
            USDC
        );

        // approve unlimited USDC for the trader (msg.sender from --sender)
        IERC20(USDC).approve(address(market), type(uint256).max);

        // Capture initial price
        uint256 initialPriceYesWei = unwrap(market.priceYes());

        // Build JSON
        string memory json = "{";
        json = string.concat(json, '"config":{');
        json = string.concat(json, '"alpha_wei":"', vm.toString(unwrap(ALPHA)), '",');
        json = string.concat(json, '"q_abmm_yes_wei":"', vm.toString(unwrap(Q_ABMM_YES)), '",');
        json = string.concat(json, '"q_abmm_no_wei":"', vm.toString(unwrap(Q_ABMM_NO)), '"');
        json = string.concat(json, "},");
        json = string.concat(json, '"initial_price_yes_wei":"', vm.toString(initialPriceYesWei), '",');
        json = string.concat(json, '"trades":[');

        for (uint256 i = 0; i < trades.length; i++) {
            market.trade(trades[i].isYes, ud(trades[i].sharesWei));
            uint256 priceWei = unwrap(market.priceYes());

            string memory t = "{";
            t = string.concat(t, '"is_yes":', trades[i].isYes ? "true" : "false", ",");
            t = string.concat(t, '"shares_wei":"', vm.toString(trades[i].sharesWei), '",');
            t = string.concat(t, '"solidity_price_yes_wei":"', vm.toString(priceWei), '"');
            t = string.concat(t, "}");

            json = string.concat(json, t);
            if (i < trades.length - 1) json = string.concat(json, ",");
        }

        json = string.concat(json, "]}");

        vm.stopBroadcast();

        vm.writeFile("../sim/tests/fixtures/parity_run.json", json);
        console.log("fixture written to sim/tests/fixtures/parity_run.json");
    }
}