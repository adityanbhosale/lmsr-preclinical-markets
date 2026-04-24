// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

/// @title Claim Topics Registry
/// @notice Maintains the list of claim topics that must be present on an
///         investor's identity for them to hold or transfer tokens in the
///         registered token ecosystem. Matches the ERC-3643 / T-REX
///         ClaimTopicsRegistry interface (minimal subset).
/// @dev For this MVP, the only claim topic is ACCREDITED_INVESTOR (topic ID 1).
///      Real T-REX deployments can register multiple topics (KYC, residency,
///      country restrictions, etc.) under one registry.
contract ClaimTopicsRegistry {
    /// @notice Canonical claim topic ID for accredited investor status.
    /// @dev Matches Tokeny's reference implementation numbering.
    uint256 public constant ACCREDITED_INVESTOR = 1;

    /// @notice Set of registered required claim topics.
    uint256[] private _claimTopics;
    mapping(uint256 => bool) private _isRegistered;

    address public immutable owner;

    event ClaimTopicAdded(uint256 indexed claimTopic);
    event ClaimTopicRemoved(uint256 indexed claimTopic);

    modifier onlyOwner() {
        require(msg.sender == owner, "only owner");
        _;
    }

    constructor() {
        owner = msg.sender;
        _addClaimTopic(ACCREDITED_INVESTOR);
    }

    /// @notice Add a required claim topic.
    function addClaimTopic(uint256 claimTopic) external onlyOwner {
        _addClaimTopic(claimTopic);
    }

    /// @notice Remove a required claim topic.
    function removeClaimTopic(uint256 claimTopic) external onlyOwner {
        require(_isRegistered[claimTopic], "topic not registered");
        _isRegistered[claimTopic] = false;

        uint256 len = _claimTopics.length;
        for (uint256 i = 0; i < len; i++) {
            if (_claimTopics[i] == claimTopic) {
                _claimTopics[i] = _claimTopics[len - 1];
                _claimTopics.pop();
                break;
            }
        }

        emit ClaimTopicRemoved(claimTopic);
    }

    /// @notice Returns the full list of required claim topics.
    function getClaimTopics() external view returns (uint256[] memory) {
        return _claimTopics;
    }

    /// @notice True if the given topic is currently required.
    function isClaimTopicRegistered(uint256 claimTopic) external view returns (bool) {
        return _isRegistered[claimTopic];
    }

    function _addClaimTopic(uint256 claimTopic) internal {
        require(!_isRegistered[claimTopic], "topic already registered");
        _isRegistered[claimTopic] = true;
        _claimTopics.push(claimTopic);
        emit ClaimTopicAdded(claimTopic);
    }
}
