// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import { ClaimTopicsRegistry } from "./ClaimTopicsRegistry.sol";

/// @title Identity Registry
/// @notice Maps investor wallet addresses to their verified claims. Acts as
///         the authoritative source of "who is allowed to hold this token"
///         in the ERC-3643 permissioned security token standard.
/// @dev Simplified from full T-REX — claims are stored inline here rather
///      than via separate OnchainID contracts + ClaimIssuer attestations.
///      Preserves permissioning behavior; loses cryptographic issuer proof.
contract IdentityRegistry {
    /// @notice A claim attached to an investor's identity.
    struct Claim {
        uint256 topic;          // e.g. ACCREDITED_INVESTOR = 1
        address issuer;         // which trusted issuer issued this claim
        uint256 issuedAt;       // unix timestamp of issuance
        bool valid;             // false after revocation
    }

    /// @notice The registry of required claim topics (set at construction).
    ClaimTopicsRegistry public immutable claimTopicsRegistry;

    /// @notice Registered identities.
    /// @dev investor => topic => claim
    mapping(address => mapping(uint256 => Claim)) private _claims;

    /// @notice Set of investors registered in the system.
    mapping(address => bool) public isRegistered;

    /// @notice The platform operator — only address that can issue/revoke claims.
    address public immutable trustedIssuer;

    event IdentityRegistered(address indexed investor);
    event ClaimIssued(
        address indexed investor,
        uint256 indexed topic,
        address indexed issuer
    );
    event ClaimRevoked(
        address indexed investor,
        uint256 indexed topic,
        address indexed issuer
    );

    modifier onlyTrustedIssuer() {
        require(msg.sender == trustedIssuer, "only trusted issuer");
        _;
    }

    constructor(address _trustedIssuer, ClaimTopicsRegistry _claimTopicsRegistry) {
        require(_trustedIssuer != address(0), "trusted issuer zero");
        require(
            address(_claimTopicsRegistry) != address(0),
            "claim topics registry zero"
        );
        trustedIssuer = _trustedIssuer;
        claimTopicsRegistry = _claimTopicsRegistry;
    }

    // ─────────────────────────────────────────────────────────────
    // Identity management
    // ─────────────────────────────────────────────────────────────

    /// @notice Register an investor in the system. Must be called before
    ///         any claims can be issued to them.
    function registerIdentity(address investor) external onlyTrustedIssuer {
        require(investor != address(0), "investor zero");
        require(!isRegistered[investor], "already registered");
        isRegistered[investor] = true;
        emit IdentityRegistered(investor);
    }

    /// @notice Issue a claim of the given topic to a registered investor.
    function issueClaim(address investor, uint256 topic) external onlyTrustedIssuer {
        require(isRegistered[investor], "investor not registered");
        require(
            claimTopicsRegistry.isClaimTopicRegistered(topic),
            "topic not required"
        );

        _claims[investor][topic] = Claim({
            topic: topic,
            issuer: trustedIssuer,
            issuedAt: block.timestamp,
            valid: true
        });

        emit ClaimIssued(investor, topic, trustedIssuer);
    }

    /// @notice Revoke a claim. Used when an investor loses qualifying status
    ///         (e.g. becomes non-accredited, added to sanctions list).
    function revokeClaim(address investor, uint256 topic) external onlyTrustedIssuer {
        require(_claims[investor][topic].valid, "claim not active");
        _claims[investor][topic].valid = false;
        emit ClaimRevoked(investor, topic, trustedIssuer);
    }

    // ─────────────────────────────────────────────────────────────
    // Verification (called by Compliance during transfers)
    // ─────────────────────────────────────────────────────────────

    /// @notice True if the investor holds a valid claim for the given topic.
    function hasValidClaim(address investor, uint256 topic)
        public
        view
        returns (bool)
    {
        return _claims[investor][topic].valid;
    }

    /// @notice True if the investor holds valid claims for ALL required topics.
    ///         This is the primary gating check used by Compliance.
    function isVerified(address investor) external view returns (bool) {
        if (!isRegistered[investor]) return false;

        uint256[] memory topics = claimTopicsRegistry.getClaimTopics();
        uint256 len = topics.length;
        for (uint256 i = 0; i < len; i++) {
            if (!_claims[investor][topics[i]].valid) return false;
        }
        return true;
    }

    /// @notice Return the raw claim data for inspection.
    function getClaim(address investor, uint256 topic)
        external
        view
        returns (Claim memory)
    {
        return _claims[investor][topic];
    }
}
