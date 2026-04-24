// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import { IdentityRegistry } from "./IdentityRegistry.sol";
import { Compliance } from "./Compliance.sol";

/// @title MilestoneToken
/// @notice ERC-3643-style permissioned security token representing fractional
///         ownership of a milestone payment right held in a Delaware SPV.
///         Each instance represents one milestone (IND, Phase 1, Phase 2, or
///         Approval).
/// @dev Transfer-gated via pluggable Compliance. Matches the ERC-3643 public
///      interface — identityRegistry(), compliance(), and canTransfer
///      pre-checks on every mint/transfer/burn.
contract MilestoneToken {
    string public name;
    string public symbol;
    uint8 public constant decimals = 18;

    uint256 public totalSupply;
    mapping(address => uint256) public balanceOf;
    mapping(address => mapping(address => uint256)) public allowance;

    /// @notice The registry that knows which addresses are verified.
    IdentityRegistry public immutable identityRegistry;

    /// @notice The compliance module that decides if each transfer is allowed.
    Compliance public immutable compliance;

    /// @notice The agent authorized to mint and burn. In production this would
    ///         be the SPV operator; for MVP it's the deployer.
    address public immutable agent;

    /// @notice Milestone metadata — describes what claim this token represents.
    /// @dev e.g. "IND filing for BI-1701963", "Phase 1 completion for sotorasib"
    string public milestoneDescription;

    event Transfer(address indexed from, address indexed to, uint256 value);
    event Approval(address indexed owner, address indexed spender, uint256 value);
    event Mint(address indexed to, uint256 value);
    event Burn(address indexed from, uint256 value);

    modifier onlyAgent() {
        require(msg.sender == agent, "only agent");
        _;
    }

    constructor(
        string memory _name,
        string memory _symbol,
        string memory _milestoneDescription,
        address _agent,
        IdentityRegistry _identityRegistry,
        Compliance _compliance
    ) {
        require(_agent != address(0), "agent zero");
        require(address(_identityRegistry) != address(0), "identity registry zero");
        require(address(_compliance) != address(0), "compliance zero");

        name = _name;
        symbol = _symbol;
        milestoneDescription = _milestoneDescription;
        agent = _agent;
        identityRegistry = _identityRegistry;
        compliance = _compliance;
    }

    // ─────────────────────────────────────────────────────────────
    // Agent operations (mint / burn)
    // ─────────────────────────────────────────────────────────────

    /// @notice Mint new tokens to a verified investor.
    /// @dev Reverts if `to` is not verified in the identity registry.
    function mint(address to, uint256 amount) external onlyAgent {
        require(
            compliance.canTransfer(address(0), to, amount),
            "recipient not compliant"
        );
        totalSupply += amount;
        balanceOf[to] += amount;
        emit Mint(to, amount);
        emit Transfer(address(0), to, amount);
    }

    /// @notice Burn tokens from a holder. Used when they redeem their SPV
    ///         interest for the underlying milestone payment.
    function burn(address from, uint256 amount) external onlyAgent {
        require(balanceOf[from] >= amount, "insufficient balance");
        require(
            compliance.canTransfer(from, address(0), amount),
            "sender not compliant"
        );
        balanceOf[from] -= amount;
        totalSupply -= amount;
        emit Burn(from, amount);
        emit Transfer(from, address(0), amount);
    }

    // ─────────────────────────────────────────────────────────────
    // ERC-20 with compliance hooks
    // ─────────────────────────────────────────────────────────────

    /// @notice Transfer tokens to another verified address.
    /// @dev Reverts if the compliance module rejects the transfer (typically
    ///      because sender or recipient lacks a valid accreditation claim).
    function transfer(address to, uint256 amount) external returns (bool) {
        require(
            compliance.canTransfer(msg.sender, to, amount),
            "transfer not compliant"
        );
        require(balanceOf[msg.sender] >= amount, "insufficient balance");

        balanceOf[msg.sender] -= amount;
        balanceOf[to] += amount;
        emit Transfer(msg.sender, to, amount);
        return true;
    }

    /// @notice Approve a spender to transfer tokens on your behalf.
    function approve(address spender, uint256 amount) external returns (bool) {
        allowance[msg.sender][spender] = amount;
        emit Approval(msg.sender, spender, amount);
        return true;
    }

    /// @notice Transfer tokens from one verified address to another on
    ///         behalf of the sender (requires prior approval).
    function transferFrom(
        address from,
        address to,
        uint256 amount
    ) external returns (bool) {
        require(
            compliance.canTransfer(from, to, amount),
            "transfer not compliant"
        );
        require(balanceOf[from] >= amount, "insufficient balance");
        require(allowance[from][msg.sender] >= amount, "insufficient allowance");

        allowance[from][msg.sender] -= amount;
        balanceOf[from] -= amount;
        balanceOf[to] += amount;
        emit Transfer(from, to, amount);
        return true;
    }
}
