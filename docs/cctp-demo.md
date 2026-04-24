# CCTP Cross-Chain Demo

## What this demonstrates

This end-to-end demo exercises the full dual-layer architecture using Circle's
Cross-Chain Transfer Protocol (CCTP) as the settlement bridge between layers.

An accredited investor wallet holds USDC on Ethereum Sepolia (the chain where
Layer 1 — the permissioned ERC-3643 tokenized milestone payment rights —
lives in production). That USDC is burned via CCTP, attested by Circle, and
minted freshly on Base Sepolia (where Layer 2 — the permissionless LS-LMSR
prediction market — lives). The investor then trades on Layer 2.

The outbound leg demonstrates:

- **Two-chain interoperability**: value moves between Layer 1's chain and
  Layer 2's chain using Circle's first-party infrastructure, not a
  custodial bridge
- **USDC as the unifying substrate**: both layers settle in the same asset,
  minted natively on each chain (not a wrapped derivative)
- **Real participation in Layer 2**: the USDC that arrived via CCTP funded
  a genuine trade against the live LSLMSR market, updating its state
  (`qYes` incremented, per-trader position recorded, events emitted)

A return leg (resolve + claim + CCTP back to Sepolia) is scripted and ready
to execute but has been deferred pending additional testnet USDC liquidity.
See "Deferred return leg" below.

## Status

| Leg | Status | Notes |
|-----|--------|-------|
| Outbound: Sepolia burn → Base Sepolia mint + trade | ✅ Complete | 2 txs on-chain, Circle attestation verified |
| Return: resolve + claim + CCTP back to Sepolia | ⏳ Deferred | Scripts ready; requires ≥105 USDC on Base Sepolia |

## Architecture note

In production, the resolver and the trader are independent parties — an
oracle or DSMB determines the outcome, and a trader claims their
proportional share. For this demo, the deployer wallet plays both roles to
produce a self-contained end-to-end flow. The mechanical property being
demonstrated is the CCTP machinery and its integration with the dual-layer
architecture, not the market dynamics.

## Outbound leg — executed

### Step 1: Burn USDC on Sepolia

Command:
```bash
source .env
forge script script/cctp/CctpBurnOutbound.s.sol:CctpBurnOutbound \
  --rpc-url sepolia --broadcast -vvvv
```

Result:
- **Approval tx**: `0xe6357e7de8c1371fd1a5c5cd0a40adeed4c6469240787453712e5ba4e6b5bd71`
- **Burn tx**: `0xb5d51882a2a26fe24d38785709022d762475d84d4e0e2ff84dea1d144baa6452`
- **Block**: 10723935
- **Amount burned**: 10 USDC
- **Destination domain**: 6 (Base Sepolia)

Etherscan: https://sepolia.etherscan.io/tx/0xb5d51882a2a26fe24d38785709022d762475d84d4e0e2ff84dea1d144baa6452

### Step 2: Poll Circle for attestation

Command:
```bash
node scripts/cctp_poll.js \
  0xb5d51882a2a26fe24d38785709022d762475d84d4e0e2ff84dea1d144baa6452 sepolia
```

Result: attestation ready after ~15 minutes. Script wrote `.cctp-message`
and `.cctp-attestation` to disk.

### Step 3: Mint USDC on Base Sepolia + trade on Layer 2

Command:
```bash
export CCTP_MESSAGE=$(cat .cctp-message)
export CCTP_ATTESTATION=$(cat .cctp-attestation)

forge script script/cctp/CctpMintAndTrade.s.sol:CctpMintAndTrade \
  --rpc-url base_sepolia --broadcast -vvvv
```

Result:
- **Attestation submit tx**: `0x52f1b98356d5d4b99b62a32b35134067800b7c1493178e984be2b09098d1a2ec`
- **USDC approval tx**: `0xba9620ec586edbd9d4637e38013cc0c1d768f870dbe44daf1e83f2ab7b61b41e`
- **Layer 2 trade tx**: `0x17dc2fa5ece9e77d831c3e568421dc846d962a31bf7d2613a0b5b90417d9bccd`
- **Block**: 40639999
- **USDC minted**: 10 USDC on Base Sepolia
- **Trade**: 5 YES shares purchased on LSLMSR at `0xb7Bd56113438961202EcFF985E7Cb2B9F2442475`

Basescan:
- Mint: https://sepolia.basescan.org/tx/0x52f1b98356d5d4b99b62a32b35134067800b7c1493178e984be2b09098d1a2ec
- Trade: https://sepolia.basescan.org/tx/0x17dc2fa5ece9e77d831c3e568421dc846d962a31bf7d2613a0b5b90417d9bccd

Post-trade Layer 2 state:
- `qYes`: 105 (100 ABMM seed + 5 trader shares)
- `qNo`: 100 (unchanged)
- Deployer position: `(yesShares=5, noShares=0)`

## Deferred return leg

The return leg (resolve → claim → CCTP return burn → final Sepolia mint) is
deferred due to a Circle testnet USDC faucet rate-limit encountered
mid-session. The solvency guarantee in `resolve()` requires the contract to
hold ≥ 1 USDC per winning share before resolution — with `qYes = 105`, that
means ≥105 USDC on Base Sepolia. Circle's public faucet limits are 20 USDC
per 2 hours per address per chain, creating a multi-hour accumulation
window that falls outside this session's scope.

### Remaining steps

All scripts are in place and tested. When ≥ 105 USDC is available on Base
Sepolia for the deployer, execute in sequence:

**Step 4: resolve + claim + return burn**
```bash
forge script script/cctp/CctpResolveClaimReturn.s.sol:CctpResolveClaimReturn \
  --rpc-url base_sepolia --broadcast -vvvv
```

Expected: deposits 105 USDC liquidity, resolves YES, claims ~5 USDC
proportional payout (5/105 of the pool), and initiates CCTP burn of the
claim payout targeting Sepolia.

**Step 5: poll for return attestation**
```bash
node scripts/cctp_poll.js <return_burn_tx_hash> base-sepolia
```

Expected: ~15-20 min wait, overwrites `.cctp-message` and `.cctp-attestation`.

**Step 6: final mint on Sepolia — closes the round-trip**
```bash
export CCTP_MESSAGE=$(cat .cctp-message)
export CCTP_ATTESTATION=$(cat .cctp-attestation)

forge script script/cctp/CctpFinalMint.s.sol:CctpFinalMint \
  --rpc-url sepolia --broadcast -vvvv
```

Expected: MessageTransmitter verifies the attestation and mints the claim
payout to the deployer on Sepolia, closing the round-trip.

### Reminders before resuming

- The `.env` file must contain `PRIVATE_KEY` and `ETHERSCAN_API_KEY`.
- `CctpResolveClaimReturn.s.sol` has `uint256 needed = 105 * 1e6;` — this
  was adjusted down from an earlier 150 USDC placeholder.
- Layer 2 V3 contract at `0xb7Bd56113438961202EcFF985E7Cb2B9F2442475` is
  holding the existing 5-share position; the resolve + claim flow is
  designed to operate against that state.
- Do **not** re-run step 1 (the Sepolia burn) — the outbound state is
  already correct and starting a new round-trip would invalidate the
  existing demo record.

## What this proves

Even with only the outbound leg complete:

- Circle's CCTP is compatible with the dual-layer architecture, with no
  custom bridge code required
- Value originating on Layer 1's chain can flow into Layer 2's market
  without the investor holding a wrapped or bridged asset
- A Layer 1 holder can participate in Layer 2 price discovery with the
  permissionless settlement properties that make Layer 2 distinct from
  Layer 1
- The round-trip symmetry (a Base Sepolia → Sepolia return leg is
  mechanically identical to the Sepolia → Base Sepolia outbound) means
  the remaining deferred steps do not introduce new architectural claims
