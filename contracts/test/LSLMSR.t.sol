// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import { MockUSDC } from "./mocks/MockUSDC.sol";
import { Test, console2 } from "forge-std/Test.sol";
import { LSLMSR } from "../src/LSLMSR.sol";
import { UD60x18, ud } from "@prb/math/UD60x18.sol";

contract LSLMSRTest is Test {
    LSLMSR market;
    MockUSDC mockUsdc;

    address alice = address(0xA11CE);
    address bob   = address(0xB0B);
    address carol = address(0xCA401);

    // ─────────────────────────────────────────────────────────────
    // Events redeclared for use with vm.expectEmit
    // ─────────────────────────────────────────────────────────────

    event Trade(address indexed trader, bool isYes, UD60x18 shares, UD60x18 cost);
    event Resolved(bool outcome);
    event PositionUpdated(
        address indexed trader,
        bool isYes,
        UD60x18 sharesBought,
        UD60x18 newYesShares,
        UD60x18 newNoShares
    );
    event Claimed(address indexed trader, uint256 usdcPaid, UD60x18 winningShares);
    event LiquidityDeposited(address indexed from, uint256 amount);

    // ─────────────────────────────────────────────────────────────
    // setUp: deploy MockUSDC, deploy market, fund & approve traders
    // ─────────────────────────────────────────────────────────────

    function setUp() public {
        mockUsdc = new MockUSDC();
        market = new LSLMSR(
            ud(0.05e18),           // alpha
            ud(100e18),            // q_abmm_yes
            ud(100e18),            // q_abmm_no
            address(this),         // resolver (the test contract)
            address(mockUsdc)      // USDC settlement token
        );

        // Fund the test traders with plenty of USDC (1,000,000 each)
        mockUsdc.mint(alice, 1_000_000 * 1e6);
        mockUsdc.mint(bob,   1_000_000 * 1e6);
        mockUsdc.mint(carol, 1_000_000 * 1e6);

        // Pre-approve the market contract for all three traders
        vm.prank(alice);
        mockUsdc.approve(address(market), type(uint256).max);

        vm.prank(bob);
        mockUsdc.approve(address(market), type(uint256).max);

        vm.prank(carol);
        mockUsdc.approve(address(market), type(uint256).max);
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
        vm.prank(alice);
        market.trade(true, ud(10e18));
        UD60x18 priceAfter = market.priceYes();

        assertGt(priceAfter.unwrap(), priceBefore.unwrap());
    }

    function test_costFunctionMonotonic() public {
        UD60x18 costBefore = market.cost();
        vm.prank(alice);
        market.trade(true, ud(10e18));
        UD60x18 costAfter = market.cost();

        assertGt(costAfter.unwrap(), costBefore.unwrap());
    }

    function test_tradeCostMatchesCostDelta() public {
        UD60x18 costBefore = market.cost();
        UD60x18 tradeCost = market.costOfTrade(true, ud(10e18));
        vm.prank(alice);
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
            address(this),
            address(mockUsdc)
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
            address(this),
            address(mockUsdc)
        );
    }

    function test_constructorRevertsOnZeroAlpha() public {
        vm.expectRevert("alpha must be positive");
        new LSLMSR(
            ud(0),
            ud(100e18),
            ud(100e18),
            address(this),
            address(mockUsdc)
        );
    }

    function test_constructorRevertsOnZeroResolver() public {
        vm.expectRevert("resolver cannot be zero address");
        new LSLMSR(
            ud(0.05e18),
            ud(100e18),
            ud(100e18),
            address(0),
            address(mockUsdc)
        );
    }

    function test_extremeImbalanceReverts() public {
        // With alpha = 0.005 and q_yes = 1000, q_no = 1, the ratio q_yes/b
        // exceeds PRBMath's exp() input ceiling (~133).
        LSLMSR extremeMarket = new LSLMSR(
            ud(0.005e18),
            ud(1000e18),
            ud(1e18),
            address(this),
            address(mockUsdc)
        );

        vm.expectRevert();
        extremeMarket.priceYes();
    }

    function test_zeroSharesTradeReverts() public {
        vm.expectRevert("shares must be positive");
        vm.prank(alice);
        market.trade(true, ud(0));
    }

    // ─────────────────────────────────────────────────────────────
    // Category B: State and access control
    // ─────────────────────────────────────────────────────────────

    function test_tradeRevertsAfterResolution() public {
        vm.prank(alice);
        market.depositLiquidity(200 * 1e6);
        market.resolve(true);

        vm.expectRevert("market resolved");
        vm.prank(alice);
        market.trade(true, ud(10e18));
    }

    function test_onlyResolverCanResolve() public {
        address attacker = address(0xBEEF);
        vm.prank(attacker);
        vm.expectRevert("only resolver");
        market.resolve(true);
    }

    function test_cannotResolveTwice() public {
        vm.prank(alice);
        market.depositLiquidity(200 * 1e6);
        market.resolve(true);

        vm.expectRevert("already resolved");
        market.resolve(false);
    }

    function test_resolutionEmitsEvent() public {
        vm.prank(alice);
        market.depositLiquidity(200 * 1e6);

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

    // ─────────────────────────────────────────────────────────────
    // Category D: USDC integration
    // ─────────────────────────────────────────────────────────────

    /// @notice trade() pulls USDC from trader equal to costOfTrade().
    function test_usdc_tradeTransfersCorrectCost() public {
        uint256 aliceBalBefore = mockUsdc.balanceOf(alice);
        uint256 marketBalBefore = mockUsdc.balanceOf(address(market));

        UD60x18 expectedCost = market.costOfTrade(true, ud(10e18));
        uint256 expectedUsdcCost = expectedCost.unwrap() / 1e12;

        vm.prank(alice);
        market.trade(true, ud(10e18));

        assertEq(
            mockUsdc.balanceOf(alice),
            aliceBalBefore - expectedUsdcCost,
            "alice USDC decreased by cost"
        );
        assertEq(
            mockUsdc.balanceOf(address(market)),
            marketBalBefore + expectedUsdcCost,
            "market USDC increased by cost"
        );
    }

    /// @notice trade() reverts if trader hasn't approved the contract.
    function test_usdc_tradeRevertsWithoutApproval() public {
        address dave = address(0xDADE);
        mockUsdc.mint(dave, 1_000_000 * 1e6);
        // dave has NOT approved the market

        vm.prank(dave);
        vm.expectRevert();
        market.trade(true, ud(10e18));
    }

    /// @notice trade() reverts if trader has insufficient USDC balance.
    function test_usdc_tradeRevertsInsufficientBalance() public {
        address dave = address(0xDADE);
        // dave has 0 USDC, but does approve
        vm.prank(dave);
        mockUsdc.approve(address(market), type(uint256).max);

        vm.prank(dave);
        vm.expectRevert();
        market.trade(true, ud(10e18));
    }

    /// @notice depositLiquidity() transfers USDC into the contract and fires event.
    function test_usdc_depositLiquidity() public {
        uint256 depositAmount = 500 * 1e6;     // 500 USDC

        vm.expectEmit(true, false, false, true);
        emit LiquidityDeposited(alice, depositAmount);

        vm.prank(alice);
        market.depositLiquidity(depositAmount);

        assertEq(mockUsdc.balanceOf(address(market)), depositAmount);
    }

    // ─────────────────────────────────────────────────────────────
    // Category E: Resolution & claim
    // ─────────────────────────────────────────────────────────────

    /// @notice resolve() reverts if contract has insufficient USDC for max liability.
    function test_claim_resolveRevertsIfUndercollateralized() public {
        vm.prank(alice);
        market.trade(true, ud(10e18));

        vm.expectRevert("insufficient USDC for max liability");
        market.resolve(true);
    }

    /// @notice resolve() succeeds when liquidity is topped up to cover max liability.
    function test_claim_resolveSucceedsAfterTopUp() public {
        vm.prank(alice);
        market.trade(true, ud(10e18));

        uint256 needed = 110 * 1e6;
        vm.prank(alice);
        market.depositLiquidity(needed);

        market.resolve(true);
        assertTrue(market.resolved(), "market resolved");
        assertEq(
            market.totalWinningShares().unwrap(),
            110e18,
            "winning shares recorded"
        );
    }

    /// @notice Single winning trader gets a proportional payout from the pool.
    function test_claim_singleWinnerGetsFullPool() public {
        vm.prank(alice);
        market.trade(true, ud(10e18));

        vm.prank(alice);
        market.depositLiquidity(200 * 1e6);

        market.resolve(true);

        uint256 resBalance = market.resolutionBalance();
        UD60x18 totalWinning = market.totalWinningShares();

        // Alice's share = 10 / 110 of the pool
        uint256 expectedPayout = (uint256(10e18) * resBalance) / totalWinning.unwrap();

        uint256 aliceBalBefore = mockUsdc.balanceOf(alice);

        vm.prank(alice);
        market.claim();

        assertEq(
            mockUsdc.balanceOf(alice),
            aliceBalBefore + expectedPayout,
            "alice receives proportional payout"
        );
        assertTrue(market.claimed(alice), "alice marked as claimed");
    }

    /// @notice Two winners on same side split the pool proportionally.
    function test_claim_twoWinnersSplitProportionally() public {
        vm.prank(alice);
        market.trade(true, ud(10e18));

        vm.prank(bob);
        market.trade(true, ud(5e18));

        vm.prank(carol);
        market.depositLiquidity(300 * 1e6);

        market.resolve(true);

        uint256 aliceBalBeforeClaim = mockUsdc.balanceOf(alice);
        uint256 bobBalBeforeClaim = mockUsdc.balanceOf(bob);

        vm.prank(alice);
        market.claim();

        vm.prank(bob);
        market.claim();

        uint256 aliceReceived = mockUsdc.balanceOf(alice) - aliceBalBeforeClaim;
        uint256 bobReceived = mockUsdc.balanceOf(bob) - bobBalBeforeClaim;

        // Alice bought 2× as many shares as Bob, so she should receive ~2× the payout
        assertApproxEqRel(
            aliceReceived,
            2 * bobReceived,
            0.01e18,
            "alice gets ~2x bob's payout"
        );
    }

    /// @notice Loser cannot claim.
    function test_claim_loserCannotClaim() public {
        vm.prank(alice);
        market.trade(true, ud(10e18));

        vm.prank(bob);
        market.trade(false, ud(10e18));

        vm.prank(carol);
        market.depositLiquidity(200 * 1e6);

        market.resolve(true);                  // YES wins

        vm.prank(bob);
        vm.expectRevert("no winning position");
        market.claim();
    }

    /// @notice Cannot claim twice.
    function test_claim_cannotClaimTwice() public {
        vm.prank(alice);
        market.trade(true, ud(10e18));

        vm.prank(alice);
        market.depositLiquidity(200 * 1e6);

        market.resolve(true);

        vm.prank(alice);
        market.claim();

        vm.prank(alice);
        vm.expectRevert("already claimed");
        market.claim();
    }

    /// @notice Cannot claim before resolution.
    function test_claim_cannotClaimBeforeResolution() public {
        vm.prank(alice);
        market.trade(true, ud(10e18));

        vm.prank(alice);
        vm.expectRevert("market not resolved");
        market.claim();
    }
}
