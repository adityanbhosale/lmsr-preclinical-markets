// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import { UD60x18, ud, unwrap, convert } from "@prb/math/UD60x18.sol";
import { IERC20 } from "@openzeppelin/contracts/token/ERC20/IERC20.sol";

/// @title LS-LMSR Binary Prediction Market
/// @notice Liquidity-Sensitive Logarithmic Market Scoring Rule for YES/NO markets
///         with per-trader position tracking and USDC settlement.
contract LSLMSR {
    using { unwrap } for UD60x18;

    // ─────────────────────────────────────────────────────────────
    // Market state
    // ─────────────────────────────────────────────────────────────

    UD60x18 public qYes;
    UD60x18 public qNo;
    UD60x18 public alpha;

    // Market lifecycle
    address public immutable resolver;
    bool public resolved;
    bool public outcome;

    // USDC settlement
    IERC20 public immutable usdc;

    // Resolution snapshot (set in resolve(), consumed in claim())
    UD60x18 public totalWinningShares;
    uint256 public resolutionBalance;
    mapping(address => bool) public claimed;

    // USDC has 6 decimals; PRBMath UD60x18 uses 18. This converts.
    uint256 private constant UD60X18_TO_USDC_SCALE = 1e12;

    // Position tracking
    struct Position {
        UD60x18 yesShares;
        UD60x18 noShares;
    }
    mapping(address => Position) public positions;

    // ─────────────────────────────────────────────────────────────
    // Events
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
    event Claimed(
        address indexed trader,
        uint256 usdcPaid,
        UD60x18 winningShares
    );
    event LiquidityDeposited(address indexed from, uint256 amount);

    // ─────────────────────────────────────────────────────────────
    // Constructor
    // ─────────────────────────────────────────────────────────────

    constructor(
        UD60x18 _alpha,
        UD60x18 _qAbmmYes,
        UD60x18 _qAbmmNo,
        address _resolver,
        address _usdc
    ) {
        require(_alpha.unwrap() > 0, "alpha must be positive");
        require(_qAbmmYes.unwrap() > 0, "qAbmmYes must be positive");
        require(_qAbmmNo.unwrap() > 0, "qAbmmNo must be positive");
        require(_resolver != address(0), "resolver cannot be zero address");
        require(_usdc != address(0), "usdc cannot be zero address");

        alpha = _alpha;
        qYes = _qAbmmYes;
        qNo = _qAbmmNo;
        resolver = _resolver;
        usdc = IERC20(_usdc);
    }

    // ─────────────────────────────────────────────────────────────
    // LS-LMSR math
    // ─────────────────────────────────────────────────────────────

    /// @notice Liquidity parameter b(q) = alpha * (q_yes + q_no)
    function b() public view returns (UD60x18) {
        return alpha.mul(qYes.add(qNo));
    }

    /// @notice LS-LMSR cost function C(q) = b * log(exp(q_yes/b) + exp(q_no/b))
    function cost() public view returns (UD60x18) {
        UD60x18 bVal = b();
        UD60x18 yesOverB = qYes.div(bVal);
        UD60x18 noOverB = qNo.div(bVal);

        UD60x18 expYes = yesOverB.exp();
        UD60x18 expNo = noOverB.exp();

        return bVal.mul(expYes.add(expNo).ln());
    }

    /// @notice Marginal price of YES shares (probability of YES, UD60x18).
    function priceYes() public view returns (UD60x18) {
        UD60x18 bVal = b();
        UD60x18 expYes = qYes.div(bVal).exp();
        UD60x18 expNo = qNo.div(bVal).exp();

        return expYes.div(expYes.add(expNo));
    }

    /// @notice Cost of buying a given number of YES or NO shares.
    function costOfTrade(bool isYes, UD60x18 shares) public view returns (UD60x18) {
        UD60x18 costBefore = cost();

        UD60x18 newQYes = isYes ? qYes.add(shares) : qYes;
        UD60x18 newQNo = isYes ? qNo : qNo.add(shares);

        UD60x18 newB = alpha.mul(newQYes.add(newQNo));
        UD60x18 expYesNew = newQYes.div(newB).exp();
        UD60x18 expNoNew = newQNo.div(newB).exp();
        UD60x18 costAfter = newB.mul(expYesNew.add(expNoNew).ln());

        return costAfter.sub(costBefore);
    }

    // ─────────────────────────────────────────────────────────────
    // Trading
    // ─────────────────────────────────────────────────────────────

    /// @notice Execute a trade against the LS-LMSR market.
    /// @dev Requires prior ERC-20 approval: trader must call
    ///      usdc.approve(address(market), cost) before calling trade().
    ///      Reverts if market is resolved, shares is zero, or USDC transfer fails.
    /// @param isYes True to buy YES shares, false to buy NO.
    /// @param shares Amount of shares to purchase (UD60x18).
    function trade(bool isYes, UD60x18 shares) external {
        require(!resolved, "market resolved");
        require(shares.unwrap() > 0, "shares must be positive");

        UD60x18 tradeCost = costOfTrade(isYes, shares);
        uint256 usdcCost = _toUSDC(tradeCost);
        require(usdcCost > 0, "trade cost rounds to zero");

        require(
            usdc.transferFrom(msg.sender, address(this), usdcCost),
            "USDC transfer failed"
        );

        if (isYes) {
            qYes = qYes.add(shares);
        } else {
            qNo = qNo.add(shares);
        }

        Position storage pos = positions[msg.sender];
        if (isYes) {
            pos.yesShares = pos.yesShares.add(shares);
        } else {
            pos.noShares = pos.noShares.add(shares);
        }

        emit Trade(msg.sender, isYes, shares, tradeCost);
        emit PositionUpdated(
            msg.sender,
            isYes,
            shares,
            pos.yesShares,
            pos.noShares
        );
    }

    // ─────────────────────────────────────────────────────────────
    // Resolution & claim
    // ─────────────────────────────────────────────────────────────

    /// @notice Resolve the market with the given outcome.
    /// @dev Only callable by the resolver, once. Reverts if the contract holds
    ///      insufficient USDC to cover 1 USDC per winning share. The resolver
    ///      must deposit additional USDC via depositLiquidity() before retrying.
    /// @param _outcome True for YES, false for NO.
    function resolve(bool _outcome) external {
        require(msg.sender == resolver, "only resolver");
        require(!resolved, "already resolved");

        UD60x18 winningShares = _outcome ? qYes : qNo;
        uint256 maxLiability = _toUSDC(winningShares);
        uint256 balance = usdc.balanceOf(address(this));
        require(balance >= maxLiability, "insufficient USDC for max liability");

        outcome = _outcome;
        resolved = true;
        totalWinningShares = winningShares;
        resolutionBalance = balance;

        emit Resolved(_outcome);
    }

    /// @notice Claim your payout after the market has resolved.
    /// @dev Pays out (trader's winning shares / total winning shares) × resolution
    ///      pool balance. Callable once per trader.
    function claim() external {
        require(resolved, "market not resolved");
        require(!claimed[msg.sender], "already claimed");

        Position memory pos = positions[msg.sender];
        UD60x18 winningShares = outcome ? pos.yesShares : pos.noShares;
        require(winningShares.unwrap() > 0, "no winning position");

        // Proportional payout: (winningShares / totalWinningShares) * resolutionBalance
        UD60x18 shareOfPool = winningShares.div(totalWinningShares);
        UD60x18 payoutUD = shareOfPool.mul(
            ud(resolutionBalance * UD60X18_TO_USDC_SCALE)
        );
        uint256 payout = _toUSDC(payoutUD);

        claimed[msg.sender] = true;

        require(usdc.transfer(msg.sender, payout), "USDC transfer failed");

        emit Claimed(msg.sender, payout, winningShares);
    }

    /// @notice Deposit USDC into the contract to cover future payout obligations.
    /// @dev Anyone can call. The resolver uses it before resolve() to ensure
    ///      the solvency check passes.
    /// @param amount USDC amount (6-decimal).
    function depositLiquidity(uint256 amount) external {
        require(amount > 0, "amount must be positive");
        require(
            usdc.transferFrom(msg.sender, address(this), amount),
            "USDC transfer failed"
        );
        emit LiquidityDeposited(msg.sender, amount);
    }

    // ─────────────────────────────────────────────────────────────
    // Internal helpers
    // ─────────────────────────────────────────────────────────────

    /// @notice Convert a UD60x18 amount (18 decimals) to USDC's 6-decimal precision.
    /// @dev Truncates (rounds down).
    function _toUSDC(UD60x18 amount) internal pure returns (uint256) {
        return amount.unwrap() / UD60X18_TO_USDC_SCALE;
    }
}
