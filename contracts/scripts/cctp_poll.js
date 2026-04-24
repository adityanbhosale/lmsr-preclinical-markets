#!/usr/bin/env node
/**
 * CCTP attestation poller.
 *
 * Given a burn transaction hash, extracts the MessageSent event, computes
 * the message hash, and polls Circle's testnet attestation API until the
 * attestation is ready (or 30 minutes elapse).
 *
 * Usage:
 *   node scripts/cctp_poll.js <tx_hash> <source_chain>
 *
 * Where <source_chain> is one of:
 *   sepolia       - Ethereum Sepolia (outbound burn)
 *   base-sepolia  - Base Sepolia (return burn)
 *
 * Output: writes two files the next Foundry script will consume:
 *   .cctp-message      - the raw CCTP message bytes
 *   .cctp-attestation  - Circle's signature
 *
 * Also prints export lines so you can:
 *   export CCTP_MESSAGE=$(cat .cctp-message)
 *   export CCTP_ATTESTATION=$(cat .cctp-attestation)
 *
 * Before running:  npm install ethers@6
 */

const fs = require('node:fs');
const { ethers } = require('ethers');

// ─────────────────────────────────────────────────────────────
// Configuration
// ─────────────────────────────────────────────────────────────

const RPC_URLS = {
    'sepolia':      'https://ethereum-sepolia-rpc.publicnode.com',
    'base-sepolia': 'https://sepolia.base.org',
};

const ATTESTATION_API = 'https://iris-api-sandbox.circle.com/attestations';

// MessageSent(bytes) event signature from MessageTransmitter
const MESSAGE_SENT_TOPIC = ethers.id('MessageSent(bytes)');

const POLL_INTERVAL_MS = 30_000;     // 30 seconds
const MAX_POLL_DURATION_MS = 30 * 60 * 1000;  // 30 minutes

// ─────────────────────────────────────────────────────────────
// Main
// ─────────────────────────────────────────────────────────────

async function main() {
    const [txHash, sourceChain] = process.argv.slice(2);
    if (!txHash || !sourceChain) {
        console.error('Usage: node scripts/cctp_poll.js <tx_hash> <sepolia|base-sepolia>');
        process.exit(1);
    }
    const rpcUrl = RPC_URLS[sourceChain];
    if (!rpcUrl) {
        console.error(`Unknown source chain: ${sourceChain}`);
        console.error('Expected one of: sepolia, base-sepolia');
        process.exit(1);
    }

    console.log(`\n=== CCTP Attestation Poller ===`);
    console.log(`Tx hash:       ${txHash}`);
    console.log(`Source chain:  ${sourceChain}\n`);

    // Step 1: Fetch the burn tx receipt and extract the MessageSent event
    const provider = new ethers.JsonRpcProvider(rpcUrl);
    const receipt = await provider.getTransactionReceipt(txHash);
    if (!receipt) {
        console.error(`No receipt found for tx ${txHash}`);
        process.exit(1);
    }

    const messageLog = receipt.logs.find(
        (log) => log.topics[0] === MESSAGE_SENT_TOPIC
    );
    if (!messageLog) {
        console.error('No MessageSent event found in tx logs');
        console.error('Confirm this is a CCTP burn transaction');
        process.exit(1);
    }

    // The MessageSent event emits the raw message as its single data field
    const messageBytes = ethers.AbiCoder.defaultAbiCoder()
        .decode(['bytes'], messageLog.data)[0];
    const messageHash = ethers.keccak256(messageBytes);

    console.log(`Message hash:  ${messageHash}`);
    console.log(`Polling Circle for attestation...\n`);

    // Step 2: Poll Circle's attestation API
    const startTime = Date.now();
    let attempt = 0;

    while (Date.now() - startTime < MAX_POLL_DURATION_MS) {
        attempt++;
        const elapsed = Math.floor((Date.now() - startTime) / 1000);
        process.stdout.write(`  [${attempt}] elapsed ${elapsed}s ... `);

        try {
            const response = await fetch(`${ATTESTATION_API}/${messageHash}`);
            if (response.ok) {
                const data = await response.json();
                if (data.status === 'complete' && data.attestation) {
                    console.log('complete!\n');
                    console.log(`=== Attestation ready ===`);
                    console.log(`Status:       ${data.status}`);
                    console.log(`Attestation:  ${data.attestation.slice(0, 40)}...`);
                    console.log('');

                    // Write outputs for Foundry consumption
                    fs.writeFileSync('.cctp-message', messageBytes);
                    fs.writeFileSync('.cctp-attestation', data.attestation);
                    console.log(`Wrote .cctp-message and .cctp-attestation`);
                    console.log('');
                    console.log('Next: run');
                    console.log(`  export CCTP_MESSAGE=$(cat .cctp-message)`);
                    console.log(`  export CCTP_ATTESTATION=$(cat .cctp-attestation)`);
                    console.log(`  forge script <next script> --rpc-url <destination chain> \\`);
                    console.log(`    --broadcast -vvvv`);
                    return;
                } else {
                    console.log(`status=${data.status}`);
                }
            } else {
                console.log(`http ${response.status}`);
            }
        } catch (err) {
            console.log(`error: ${err.message}`);
        }

        await new Promise((r) => setTimeout(r, POLL_INTERVAL_MS));
    }

    console.error(`\nTimeout after 30 min. Circle's attestation may be delayed.`);
    console.error(`Retry: node scripts/cctp_poll.js ${txHash} ${sourceChain}`);
    process.exit(1);
}

main().catch((err) => {
    console.error(err);
    process.exit(1);
});
