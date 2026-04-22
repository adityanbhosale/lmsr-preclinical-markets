// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import { UD60x18, ud, unwrap, convert } from "@prb/math/UD60x18.sol";

/// @title LS-LMSR Binary Prediction Market
/// @notice Liquidity-Sensitive Logarithmic Market Scoring Rule for YES/NO markets
contract LSLMSR {
    using { unwrap } for UD60x18;

    // Market state
    UD60x18 public qYes;
    UD60x18 public qNo;
    UD60x18 public alpha;

    // Market lifecycle
    address public immutable resolver;
    bool public resolved;
    bool public outcome;

    // Events
    event Trade(address indexed trader, bool isYes, UD60x18 shares, UD60x18 cost);
    event Resolved(bool outcome);

    constructor(UD60x18 _alpha, UD60x18 _qAbmmYes, UD60x18 _qAbmmNo, address _resolver) {
    require(_alpha.unwrap() > 0, "alpha must be positive");
    require(_qAbmmYes.unwrap() > 0, "qAbmmYes must be positive");
    require(_qAbmmNo.unwrap() > 0, "qAbmmNo must be positive");
    require(_resolver != address(0), "resolver cannot be zero address");
    
    alpha = _alpha;
    qYes = _qAbmmYes;
    qNo = _qAbmmNo;
    resolver = _resolver;
}

    /// @notice Computes the liquidity parameter b(q) = alpha * (q_yes + q_no)
    function b() public view returns (UD60x18) {
        return alpha.mul(qYes.add(qNo));
    }

    /// @notice Computes the LS-LMSR cost function C(q) = b * log(exp(q_yes/b) + exp(q_no/b))
    function cost() public view returns (UD60x18) {
        UD60x18 bVal = b();
        UD60x18 yesOverB = qYes.div(bVal);
        UD60x18 noOverB = qNo.div(bVal);

        UD60x18 expYes = yesOverB.exp();
        UD60x18 expNo = noOverB.exp();

        return bVal.mul(expYes.add(expNo).ln());
    }

    /// @notice Computes the marginal price of YES shares
    /// @return probability of YES outcome, in UD60x18 (1e18 = 100%)
    function priceYes() public view returns (UD60x18) {
        UD60x18 bVal = b();
        UD60x18 expYes = qYes.div(bVal).exp();
        UD60x18 expNo = qNo.div(bVal).exp();

        return expYes.div(expYes.add(expNo));
    }

    /// @notice Computes the cost of buying a given number of YES or NO shares
    /// @param isYes true for YES shares, false for NO
    /// @param shares number of shares to buy (in UD60x18)
    /// @return cost in units of the quote asset (USDC)
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

    /// @notice Executes a trade. User pays cost in quote token (not implemented here yet)
    /// @dev This version just updates state. Payment integration comes later.
    function trade(bool isYes, UD60x18 shares) external returns (UD60x18 tradeCost) {
        require(!resolved, "market resolved");
        tradeCost = costOfTrade(isYes, shares);

        if (isYes) {
            qYes = qYes.add(shares);
        } else {
            qNo = qNo.add(shares);
        }

        emit Trade(msg.sender, isYes, shares, tradeCost);
    }

    /// @notice Resolves the market
    function resolve(bool _outcome) external {
        require(msg.sender == resolver, "only resolver");
        require(!resolved, "already resolved");
        resolved = true;
        outcome = _outcome;
        emit Resolved(_outcome);
    }
}