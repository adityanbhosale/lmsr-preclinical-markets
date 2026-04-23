// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import { Test, console2 } from "forge-std/Test.sol";
import { LSLMSR } from "../src/LSLMSR.sol";
import { UD60x18, ud } from "@prb/math/UD60x18.sol";

contract LSLMSRTest is Test {
    LSLMSR market;

    address alice = address(0xA11CE);
    address bob   = address(0xB0B);
    address carol = address(0xCA401);

    // Events to test for emission
    event Trade(address indexed trader, bool isYes, UD60x18 shares, UD60x18 cost);
    event Resolved(bool outcome);

    event PositionUpdated(
    address indexed trader,
    bool isYes,
    UD60x18 sharesBought,
    UD60x18 newYesShares,
    UD60x18 newNoShares
);

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

   
    function test_zeroSharesTradeReverts() public {
        vm.expectRevert("shares must be positive");
        market.trade(true, ud(0));
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

    // ─────────────────────────────────────────────────────────────
    // Category C: Per-trader position tracking
    // ─────────────────────────────────────────────────────────────

    /// @notice Single trader buys YES; only yesShares should increment.
    function test_positionTracking_singleTraderBuysYes() public {
        vm.prank(alice);
        market.trade(true, ud(10e18));

        (UD60x18 yesShares, UD60x18 noShares) = market.positions(alice);
        assertEq(yesShares.unwrap(), 10e18, "alice yes = 10");
        assertEq(noShares.unwrap(), 0, "alice no = 0");
    }

    /// @notice Single trader buys NO; only noShares should increment.
    function test_positionTracking_singleTraderBuysNo() public {
        vm.prank(alice);
        market.trade(false, ud(5e18));

        (UD60x18 yesShares, UD60x18 noShares) = market.positions(alice);
        assertEq(yesShares.unwrap(), 0, "alice yes = 0");
        assertEq(noShares.unwrap(), 5e18, "alice no = 5");
    }

    /// @notice Same trader buys YES twice; yesShares should accumulate.
    function test_positionTracking_sameTraderAccumulates() public {
        vm.startPrank(alice);
        market.trade(true, ud(10e18));
        market.trade(true, ud(7e18));
        vm.stopPrank();

        (UD60x18 yesShares, UD60x18 noShares) = market.positions(alice);
        assertEq(yesShares.unwrap(), 17e18, "alice yes = 10 + 7");
        assertEq(noShares.unwrap(), 0, "alice no unchanged");
    }

    /// @notice Same trader buys on both sides; yes and no accumulate independently.
    function test_positionTracking_sameTraderMixedSides() public {
        vm.startPrank(alice);
        market.trade(true, ud(10e18));
        market.trade(false, ud(4e18));
        market.trade(true, ud(3e18));
        vm.stopPrank();

        (UD60x18 yesShares, UD60x18 noShares) = market.positions(alice);
        assertEq(yesShares.unwrap(), 13e18, "alice yes = 10 + 3");
        assertEq(noShares.unwrap(), 4e18, "alice no = 4");
    }

    /// @notice Two traders on opposite sides maintain separate positions.
    function test_positionTracking_twoTradersOppositeSides() public {
        vm.prank(alice);
        market.trade(true, ud(10e18));

        vm.prank(bob);
        market.trade(false, ud(8e18));

        (UD60x18 aliceYes, UD60x18 aliceNo) = market.positions(alice);
        (UD60x18 bobYes, UD60x18 bobNo) = market.positions(bob);

        assertEq(aliceYes.unwrap(), 10e18, "alice yes = 10");
        assertEq(aliceNo.unwrap(), 0, "alice no = 0");
        assertEq(bobYes.unwrap(), 0, "bob yes = 0");
        assertEq(bobNo.unwrap(), 8e18, "bob no = 8");
    }

    /// @notice Three traders each buy different amounts; positions are
    ///         tracked correctly without interference.
    function test_positionTracking_threeTraders() public {
        vm.prank(alice);
        market.trade(true, ud(10e18));

        vm.prank(bob);
        market.trade(false, ud(8e18));

        vm.prank(carol);
        market.trade(true, ud(5e18));

        (UD60x18 aliceYes,) = market.positions(alice);
        (, UD60x18 bobNo) = market.positions(bob);
        (UD60x18 carolYes,) = market.positions(carol);

        assertEq(aliceYes.unwrap(), 10e18, "alice yes = 10");
        assertEq(bobNo.unwrap(), 8e18, "bob no = 8");
        assertEq(carolYes.unwrap(), 5e18, "carol yes = 5");

        // Aggregate invariant: sum of yes positions = qYes - q_abmm_yes (100)
        assertEq(market.qYes().unwrap(), 115e18, "qYes aggregate");
        assertEq(market.qNo().unwrap(), 108e18, "qNo aggregate");
    }

    /// @notice PositionUpdated event fires with correct args on trade.
    function test_positionTracking_emitsEventOnTrade() public {
        vm.expectEmit(true, false, false, true);
        emit PositionUpdated(
            alice,
            true,
            ud(10e18),
            ud(10e18),
            ud(0)
        );

        vm.prank(alice);
        market.trade(true, ud(10e18));
    }


}