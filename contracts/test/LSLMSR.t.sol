// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import { Test, console2 } from "forge-std/Test.sol";
import { LSLMSR } from "../src/LSLMSR.sol";
import { UD60x18, ud } from "@prb/math/UD60x18.sol";

contract LSLMSRTest is Test {
    LSLMSR market;

    // Events to test for emission
    event Trade(address indexed trader, bool isYes, UD60x18 shares, UD60x18 cost);
    event Resolved(bool outcome);

    function setUp() public {
        market = new LSLMSR(
            ud(0.05e18),   // alpha = 0.05
            ud(100e18),    // q_abmm_yes = 100
            ud(100e18),    // q_abmm_no = 100
            address(this)  // resolver
        );
    }

    // ─────────────────────────────────────────────────────────────
    // Original happy-path tests
    // ─────────────────────────────────────────────────────────────

    function test_initialPriceIsFifty() public view {
        UD60x18 price = market.priceYes();
        assertApproxEqAbs(price.unwrap(), 0.5e18, 1e15);
    }

    function test_buyYesIncreasesPrice() public {
        UD60x18 priceBefore = market.priceYes();
        market.trade(true, ud(10e18));
        UD60x18 priceAfter = market.priceYes();

        assertGt(priceAfter.unwrap(), priceBefore.unwrap());
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
        LSLMSR asymMarket = new LSLMSR(
            ud(0.05e18),
            ud(150e18),
            ud(50e18),
            address(this)
        );

        UD60x18 price = asymMarket.priceYes();
        assertGt(price.unwrap(), 0.5e18);
    }

    // ─────────────────────────────────────────────────────────────
    // Category A: Input-domain edge cases
    // ─────────────────────────────────────────────────────────────

   function test_constructorRevertsOnZeroSeed() public {
    vm.expectRevert("qAbmmYes must be positive");
        new LSLMSR(
        ud(0.05e18),
        ud(0),
        ud(100e18),
        address(this)
        );
    }

    function test_constructorRevertsOnZeroAlpha() public {
     vm.expectRevert("alpha must be positive");
        new LSLMSR(
        ud(0),
        ud(100e18),
        ud(100e18),
        address(this)
        );
    } 

    function test_constructorRevertsOnZeroResolver() public {
     vm.expectRevert("resolver cannot be zero address");
        new LSLMSR(
        ud(0.05e18),
        ud(100e18),
        ud(100e18),
        address(0)
        );
    }

    function test_extremeImbalanceReverts() public {
        // With alpha = 0.005 and q_yes = 1000, q_no = 1, the ratio q_yes/b
        // exceeds PRBMath's exp() input ceiling (~133).
        LSLMSR extremeMarket = new LSLMSR(
            ud(0.005e18),
            ud(1000e18),
            ud(1e18),
            address(this)
        );

        vm.expectRevert();
        extremeMarket.priceYes();
    }

    function test_zeroSharesTradeIsNoOp() public {
        UD60x18 qYesBefore = market.qYes();
        UD60x18 qNoBefore = market.qNo();
        UD60x18 priceBefore = market.priceYes();

        market.trade(true, ud(0));

        assertEq(market.qYes().unwrap(), qYesBefore.unwrap());
        assertEq(market.qNo().unwrap(), qNoBefore.unwrap());
        assertEq(market.priceYes().unwrap(), priceBefore.unwrap());
    }

    // ─────────────────────────────────────────────────────────────
    // Category B: State and access control
    // ─────────────────────────────────────────────────────────────

    function test_tradeRevertsAfterResolution() public {
        market.resolve(true);

        vm.expectRevert("market resolved");
        market.trade(true, ud(10e18));
    }

    function test_onlyResolverCanResolve() public {
        address attacker = address(0xBEEF);

        vm.prank(attacker);
        vm.expectRevert("only resolver");
        market.resolve(true);
    }

    function test_cannotResolveTwice() public {
        market.resolve(true);

        vm.expectRevert("already resolved");
        market.resolve(false);
    }

    function test_resolutionEmitsEvent() public {
        vm.expectEmit(false, false, false, true);
        emit Resolved(true);
        market.resolve(true);
    }
}