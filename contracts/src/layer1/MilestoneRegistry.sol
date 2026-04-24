// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import { IdentityRegistry } from "./IdentityRegistry.sol";
import { Compliance } from "./Compliance.sol";
import { MilestoneToken } from "./MilestoneToken.sol";

/// @title MilestoneRegistry
/// @notice Deploys and tracks the four-milestone token ladder for a single
///         biotech program. Each milestone (IND / Phase 1 / Phase 2 /
///         Approval) is its own MilestoneToken, but all four share the same
///         IdentityRegistry and Compliance module — so an investor
///         credentialed once can hold any/all four.
/// @dev Matches the whitepaper's four-milestone SPV structure. In production
///      each milestone token would be issued against a separate Delaware
///      SPV holding the rights to that specific milestone payment.
contract MilestoneRegistry {
    /// @notice Shared identity + compliance infrastructure.
    IdentityRegistry public immutable identityRegistry;
    Compliance public immutable compliance;

    /// @notice The four milestone tokens in canonical order.
    enum Milestone { IND, Phase1, Phase2, Approval }

    /// @notice Deployed token addresses, indexed by Milestone enum.
    mapping(Milestone => MilestoneToken) public tokens;

    /// @notice Program identifier — e.g. "sotorasib", "BI-1701963".
    string public programName;

    address public immutable agent;

    event MilestoneTokenDeployed(
        Milestone indexed milestone,
        address indexed tokenAddress,
        string name,
        string symbol
    );

    constructor(
        string memory _programName,
        address _agent,
        IdentityRegistry _identityRegistry,
        Compliance _compliance
    ) {
        require(bytes(_programName).length > 0, "program name empty");
        require(_agent != address(0), "agent zero");

        programName = _programName;
        agent = _agent;
        identityRegistry = _identityRegistry;
        compliance = _compliance;

        _deployMilestone(
            Milestone.IND,
            string.concat(_programName, " IND Milestone"),
            string.concat(_programName, "-IND"),
            "IND filing milestone payment right"
        );
        _deployMilestone(
            Milestone.Phase1,
            string.concat(_programName, " Phase 1 Milestone"),
            string.concat(_programName, "-P1"),
            "Phase 1 completion milestone payment right"
        );
        _deployMilestone(
            Milestone.Phase2,
            string.concat(_programName, " Phase 2 Milestone"),
            string.concat(_programName, "-P2"),
            "Phase 2 completion milestone payment right"
        );
        _deployMilestone(
            Milestone.Approval,
            string.concat(_programName, " Approval Milestone"),
            string.concat(_programName, "-APR"),
            "FDA approval milestone payment right"
        );
    }

    function _deployMilestone(
        Milestone milestone,
        string memory tokenName,
        string memory tokenSymbol,
        string memory description
    ) internal {
        MilestoneToken token = new MilestoneToken(
            tokenName,
            tokenSymbol,
            description,
            agent,
            identityRegistry,
            compliance
        );
        tokens[milestone] = token;
        emit MilestoneTokenDeployed(milestone, address(token), tokenName, tokenSymbol);
    }

    /// @notice Convenience accessor for all four tokens.
    function getAllTokens()
        external
        view
        returns (
            MilestoneToken ind,
            MilestoneToken phase1,
            MilestoneToken phase2,
            MilestoneToken approval
        )
    {
        return (
            tokens[Milestone.IND],
            tokens[Milestone.Phase1],
            tokens[Milestone.Phase2],
            tokens[Milestone.Approval]
        );
    }
}
