// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import { Test, console2 } from "forge-std/Test.sol";
import { LSLMSR } from "../src/LSLMSR.sol";
import { UD60x18, ud } from "@prb/math/UD60x18.sol";

contract LSLMSRTest is Test {
    LSLMSR market;

    // Set up a market with alpha=0.05, symmetric ABMM seeding (q_yes=q_no=100)
    function setUp() public {
        market = new LSLMSR(
            ud(0.05e18),   // alpha = 0.05
            ud(100e18),    // q_abmm_yes = 100
            ud(100e18),    // q_abmm_no = 100
            address(this)  // resolver
        );
    }

    function test_initialPriceIsFifty() public view {
        // Symmetric seeding -> price should be exactly 0.5
        UD60x18 price = market.priceYes();
        assertApproxEqAbs(price.unwrap(), 0.5e18, 1e15); // within 0.001
    }

    function test_buyYesIncreasesPrice() public {
        UD60x18 priceBefore = market.priceYes();
        market.trade(true, ud(10e18)); // buy 10 YES shares
        UD60x18 priceAfter = market.priceYes();

        assertGt(priceAfter.unwrap(), priceBefore.unwrap());
        console2.log("price before:", priceBefore.unwrap());
        console2.log("price after:", priceAfter.unwrap());
    }

    function test_costFunctionMonotonic() public {
        UD60x18 costBefore = market.cost();
        market.trade(true, ud(10e18));
        UD60x18 costAfter = market.cost();

        assertGt(costAfter.unwrap(), costBefore.unwrap());
    }

    function test_tradeCostMatchesCostDelta() public {
        UD60x18 costBefore = market.cost();
        UD60x18 tradeCost = market.costOfTrade(true, ud(10e18));
        market.trade(true, ud(10e18));
        UD60x18 costAfter = market.cost();

        UD60x18 expectedDelta = costAfter.sub(costBefore);
        assertApproxEqAbs(tradeCost.unwrap(), expectedDelta.unwrap(), 1e12);
    }

    function test_asymmetricSeedingPriceMatches() public {
        // Deploy a market with asymmetric ABMM seeding (q_yes=150, q_no=50)
        LSLMSR asymMarket = new LSLMSR(
            ud(0.05e18),
            ud(150e18),
            ud(50e18),
            address(this)
        );

        UD60x18 price = asymMarket.priceYes();
        // Price should be > 0.5 because YES is seeded more heavily
        assertGt(price.unwrap(), 0.5e18);

        // Compute expected price in Python: exp(150/10) / (exp(150/10) + exp(50/10))
        // = exp(15) / (exp(15) + exp(5))
        // ≈ 0.99995...
        console2.log("asymmetric price:", price.unwrap());
    }
}