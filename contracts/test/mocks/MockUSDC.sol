// ═══════════════════════════════════════════════════════════════════════════
// MockUSDC Contract — NEW FILE: contracts/test/mocks/MockUSDC.sol
// ═══════════════════════════════════════════════════════════════════════════
//
// Minimal ERC-20 with 6 decimals for use in unit tests. Includes a mint()
// function so tests can fund trader wallets arbitrarily.
 
// File: contracts/test/mocks/MockUSDC.sol
 
// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;
 
import { ERC20 } from "@openzeppelin/contracts/token/ERC20/ERC20.sol";
 
/// @notice Mock USDC for LS-LMSR tests. 6-decimal ERC-20 with open mint.
contract MockUSDC is ERC20 {
    constructor() ERC20("Mock USDC", "USDC") {}
 
    function decimals() public pure override returns (uint8) {
        return 6;
    }
 
    function mint(address to, uint256 amount) external {
        _mint(to, amount);
    }
}
 
 