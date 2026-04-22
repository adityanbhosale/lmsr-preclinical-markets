# Testnet Reference Implementation

## Overview

The repository now includes a working Solidity reference implementation of the Layer 2 LS-LMSR automated market maker described in the whitepaper, deployed and live on Base Sepolia (Base's public testnet). For non-engineers: the pricing mechanism that was previously a mathematical proof and a Python simulation is now running as real smart contract code on a public blockchain, executing trades with the same math and producing the same prices. Anyone with a wallet configured for Base Sepolia can read the contract state, call its view functions, and submit trades against it.

The testnet deployment is a development artifact, not a production system — there is no real money, no real milestone payment rights, and no credentialed trader gate. But the contract is functionally identical to what a production Layer 2 deployment would look like, and the architecture allows clean upgrades toward production (credentialed trading, real USDC settlement, resolved markets) without rewriting the core math.

## Deployment Coordinates

| Field | Value |
|-------|-------|
| Network | Base Sepolia (chain ID 84532) |
| Contract address | `0x747DF6BebC9A8fb208886270E5D333F79c48F812` |
| Deployment tx | `0x66be2ae6fb6c30f75bc69dd0e93f416fe87632f329473112123c9bc31a9a3c0e` |
| Block | 40,653,253 |
| Deployer | `0xeAe842a316c5e96EC02824C4B5A7D030faEFd07C` |
| Deploy date | April 22, 2026 |
| Deploy gas cost | 0.00000648618 ETH (1,081,030 gas @ 0.006 gwei) |

Constructor parameters:
- `α = 0.05` (LS-LMSR liquidity scaling parameter)
- `q_abmm_yes = 100` (initial YES seed shares)
- `q_abmm_no = 100` (initial NO seed shares — symmetric, initial price = 0.5)
- `resolver = deployer` (admin-attested resolution stub for MVP)

Basescan: [https://sepolia.basescan.org/address/0x747DF6BebC9A8fb208886270E5D333F79c48F812](https://sepolia.basescan.org/address/0x747DF6BebC9A8fb208886270E5D333F79c48F812)

## Contract Architecture

Layer 2 is implemented in `contracts/src/LSLMSR.sol`. All internal calculations use PRBMath's `UD60x18` fixed-point type, since Solidity has no native floating-point and LS-LMSR requires `exp` and `ln` operations.

Public interface:

| Function | Returns | Description |
|----------|---------|-------------|
| `b()` | `UD60x18` | Current liquidity parameter `α · (q_yes + q_no)` |
| `cost()` | `UD60x18` | LS-LMSR cost function value at current state |
| `priceYes()` | `UD60x18` | Marginal price of YES shares (implied probability) |
| `costOfTrade(bool, UD60x18)` | `UD60x18` | Cost of a prospective trade |
| `trade(bool, UD60x18)` | — | Executes a trade, updates the `q` vector |
| `resolve(bool)` | — | Resolver-only; sets outcome and flips `resolved` to true |

Deliberate omissions — staged for later, not forgotten:

- Per-trader position accounting (next workflow item)
- USDC payment flow on `trade()` (current trades update the `q` vector but don't transfer value)
- `claim()` for resolved markets
- Access control on `trade()` (the identity-registry gate that makes this a credentialed market)

## Test Coverage

`contracts/test/LSLMSR.t.sol` contains 14 passing unit tests, organized into three groups:

**Core math (5 tests):** initial price equals 0.5 under symmetric seeding; buying YES increases the price; cost function is monotonic under trading; `costOfTrade()` output matches the actual cost delta from the trade; asymmetric seeding (`q_yes = 150`, `q_no = 50`) produces the correct marginal price.

**Category A — Input-domain boundaries (6 tests):** constructor reverts on zero alpha, zero YES seed, zero NO seed, zero resolver address; `trade()` reverts on zero share amount; extreme asymmetric seeding does not overflow PRBMath's exponential.

**Category B — State and access control (3 tests):** `resolve()` reverts when called by a non-resolver; `resolve()` reverts when called twice; `trade()` reverts after resolution.

Run locally:

```bash
cd contracts
forge test -vv
```

## Deployment Process

Stack:
- **Foundry** — faster than Hardhat, better test framework, modern standard for serious Solidity work
- **PRBMath UD60x18** — fixed-point `exp` and `ln` for LS-LMSR
- **OpenZeppelin Contracts** — standard patterns
- **Base Sepolia** — Base's public testnet, Coinbase L2 on OP Stack

The deployment script `contracts/script/DeployLSLMSR.s.sol` broadcasts with deterministic constructor parameters and logs the initial contract state — contract address, deployer, resolver, α, seed quantities, and initial `priceYes()` value — to console. The dry-run flow (`forge script` without `--broadcast`) runs the entire deployment against a forked Base Sepolia state in memory, allowing a sanity check on the initial price (should be exactly `5e17` = 0.5 under symmetric seeding) before any testnet ETH is spent.

Single-command deploy and verify:

```bash
forge script script/DeployLSLMSR.s.sol:DeployLSLMSR \
  --rpc-url base_sepolia \
  --broadcast \
  --verify \
  -vvvv
```

## Roadblocks and Resolutions

Several frictions came up during bring-up. Worth documenting because they'll recur for anyone reproducing the deployment.

### Faucet Sybil gate

Major Base Sepolia faucets (Alchemy, QuickNode, Chainstack) require a minimum mainnet ETH balance (~0.001 ETH, or ~$2–3) as an anti-bot measure before dripping testnet tokens. A fresh wallet with no mainnet activity gets rejected at the faucet UI regardless of the testnet network selected. Resolved by using the Coinbase Developer Platform (CDP) faucet, which issues up to 0.1 ETH per 24h on Base Sepolia without requiring mainnet balance. Gate-free alternatives: thirdweb, Bware Labs, GHOST.

### Etherscan API migration

The original workflow specified acquiring a BaseScan API key for contract verification. However, since August 2025 Etherscan has consolidated all its chain-specific explorers (BaseScan, BscScan, Polygonscan, Arbiscan, etc.) under a unified V2 API — a single Etherscan key now provides access to 60+ chains including Base. Legacy BaseScan keys were deprecated. `foundry.toml` was updated to the V2 format:

```toml
[etherscan]
base_sepolia = { key = "${ETHERSCAN_API_KEY}", chain = 84532 }
sepolia = { key = "${ETHERSCAN_API_KEY}", chain = 11155111 }
```

One env var, two chains.

### Verification indexer lag

Even with a confirmed deployment (verified on-chain directly via `cast code <address>` returning full bytecode and `cast call <address> "priceYes()(uint256)"` returning `5e17`), Etherscan's Base Sepolia indexer was slow to pick up the new contract, producing "Could not detect ContractCode at ..." errors on verification attempts via both `forge script --verify` and standalone `forge verify-contract`. Sourcify as a fallback verifier showed the same pattern, suggesting an RPC-endpoint divergence between the deployment transaction and the indexer's code-query path.

The deployment is unambiguously real — verification will resolve once Basescan's indexer catches up (typical lag on Base Sepolia: 15–60 minutes; occasionally longer). A retry command is parked in the deployment log for re-execution once the indexer catches up:

```bash
forge verify-contract \
  --chain 84532 \
  --watch \
  --rpc-url base_sepolia \
  --constructor-args $(cast abi-encode "constructor(uint256,uint256,uint256,address)" \
    50000000000000000 100000000000000000000 100000000000000000000 \
    0xeAe842a316c5e96EC02824C4B5A7D030faEFd07C) \
  0x747DF6BebC9A8fb208886270E5D333F79c48F812 \
  src/LSLMSR.sol:LSLMSR
```

### Empty-file silent compile

Early on, `forge build` returned `Compiler run successful` with only pragma warnings — but the compiler couldn't find the `LSLMSR` declaration when running tests. Root cause: the source file had been created but the full contract body hadn't been pasted. The "successful" build was compiling effectively empty files. Resolved by explicitly verifying file contents after creation before rebuilding. Worth noting for anyone following the workflow: `forge build` succeeding is not the same as your contract compiling — check that the expected contracts appear in `out/`.

## What's Next

The deployed contract is a working LS-LMSR cost function — mathematically complete but not yet a usable prediction market. The following components, added in order, convert the current reference into a complete Layer 2 MVP:

1. **Position tracking per trader** — `mapping(address => Position)` so individual holdings are tracked (prerequisite for claims and sales)
2. **USDC payment integration** — `trade()` transfers testnet USDC into the contract via `IERC20.transferFrom()` against Circle's Base Sepolia USDC
3. **Resolution claim function** — `claim()` pays out winning shares in USDC after `resolve()` has been called
4. **ERC-3643 Layer 1 via Tokeny T-REX** — permissioned security token on Ethereum Sepolia representing the SPV interest in a milestone payment right
5. **CCTP cross-chain demonstration** — Circle's testnet CCTP bridging USDC between Layer 1 (Ethereum Sepolia) and Layer 2 (Base Sepolia)

Steps 1–3 are Layer 2 continuation work on the existing contract. Step 4 begins Layer 1 work on a separate chain. Step 5 closes the two-layer loop and demonstrates end-to-end jurisdictional separation with stablecoin settlement.

## Reproducing the Deployment

With a funded Base Sepolia wallet (~0.001 ETH is more than sufficient) and an Etherscan V2 API key:

```bash
cd contracts
forge install                              # install PRBMath, OpenZeppelin, forge-std
source .env                                # load PRIVATE_KEY and ETHERSCAN_API_KEY
forge test -vv                             # verify 14/14 tests pass
forge script script/DeployLSLMSR.s.sol:DeployLSLMSR --rpc-url base_sepolia    # dry-run
forge script script/DeployLSLMSR.s.sol:DeployLSLMSR \
  --rpc-url base_sepolia --broadcast --verify -vvvv                          # live deploy
```

`.env` template (from `.env.example`):

```
PRIVATE_KEY=0x...              # your testnet wallet private key, NOT a mainnet key
ETHERSCAN_API_KEY=...           # single V2 key, works for Base and Ethereum
```
