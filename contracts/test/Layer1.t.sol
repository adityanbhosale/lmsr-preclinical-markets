// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import { Test } from "forge-std/Test.sol";
import { ClaimTopicsRegistry } from "../src/layer1/ClaimTopicsRegistry.sol";
import { IdentityRegistry } from "../src/layer1/IdentityRegistry.sol";
import { Compliance } from "../src/layer1/Compliance.sol";
import { MilestoneToken } from "../src/layer1/MilestoneToken.sol";
import { MilestoneRegistry } from "../src/layer1/MilestoneRegistry.sol";

contract Layer1Test is Test {
    ClaimTopicsRegistry claimTopics;
    IdentityRegistry identityRegistry;
    Compliance compliance;
    MilestoneRegistry milestoneRegistry;

    // Reuse the same synthetic accredited investors as Layer 2
    address alice = address(0xA11CE);
    address bob   = address(0xB0B);
    address carol = address(0xCA401);
    address dave  = address(0xDADE);       // non-accredited for negative tests

    uint256 constant ACCREDITED = 1;

    // Events re-declared for vm.expectEmit
    event IdentityRegistered(address indexed investor);
    event ClaimIssued(address indexed investor, uint256 indexed topic, address indexed issuer);
    event ClaimRevoked(address indexed investor, uint256 indexed topic, address indexed issuer);
    event Transfer(address indexed from, address indexed to, uint256 value);

    function setUp() public {
        // Test contract acts as trusted issuer / agent
        claimTopics = new ClaimTopicsRegistry();
        identityRegistry = new IdentityRegistry(address(this), claimTopics);
        compliance = new Compliance(identityRegistry);
        milestoneRegistry = new MilestoneRegistry(
            "sotorasib",
            address(this),
            identityRegistry,
            compliance
        );

        // Register alice, bob, carol with accreditation claims
        // (dave is deliberately left non-accredited)
        identityRegistry.registerIdentity(alice);
        identityRegistry.issueClaim(alice, ACCREDITED);

        identityRegistry.registerIdentity(bob);
        identityRegistry.issueClaim(bob, ACCREDITED);

        identityRegistry.registerIdentity(carol);
        identityRegistry.issueClaim(carol, ACCREDITED);
    }

    // ─────────────────────────────────────────────────────────────
    // ClaimTopicsRegistry
    // ─────────────────────────────────────────────────────────────

    function test_claimTopics_accreditedRegisteredAtConstruction() public view {
        assertTrue(claimTopics.isClaimTopicRegistered(ACCREDITED));
        uint256[] memory topics = claimTopics.getClaimTopics();
        assertEq(topics.length, 1);
        assertEq(topics[0], ACCREDITED);
    }

    function test_claimTopics_addAndRemove() public {
        uint256 NEW_TOPIC = 42;
        claimTopics.addClaimTopic(NEW_TOPIC);
        assertTrue(claimTopics.isClaimTopicRegistered(NEW_TOPIC));

        claimTopics.removeClaimTopic(NEW_TOPIC);
        assertFalse(claimTopics.isClaimTopicRegistered(NEW_TOPIC));
    }

    function test_claimTopics_onlyOwnerCanAdd() public {
        vm.prank(alice);
        vm.expectRevert("only owner");
        claimTopics.addClaimTopic(42);
    }

    // ─────────────────────────────────────────────────────────────
    // IdentityRegistry — registration + claim lifecycle
    // ─────────────────────────────────────────────────────────────

    function test_identity_registerAndIssue() public {
        assertTrue(identityRegistry.isRegistered(alice));
        assertTrue(identityRegistry.hasValidClaim(alice, ACCREDITED));
        assertTrue(identityRegistry.isVerified(alice));
    }

    function test_identity_daveNotVerified() public view {
        assertFalse(identityRegistry.isRegistered(dave));
        assertFalse(identityRegistry.isVerified(dave));
    }

    function test_identity_cannotIssueToUnregistered() public {
        vm.expectRevert("investor not registered");
        identityRegistry.issueClaim(dave, ACCREDITED);
    }

    function test_identity_revokeClaim() public {
        identityRegistry.revokeClaim(alice, ACCREDITED);
        assertFalse(identityRegistry.hasValidClaim(alice, ACCREDITED));
        assertFalse(identityRegistry.isVerified(alice));
    }

    function test_identity_onlyTrustedIssuerCanRegister() public {
        vm.prank(alice);
        vm.expectRevert("only trusted issuer");
        identityRegistry.registerIdentity(dave);
    }

    function test_identity_onlyTrustedIssuerCanRevoke() public {
        vm.prank(alice);
        vm.expectRevert("only trusted issuer");
        identityRegistry.revokeClaim(bob, ACCREDITED);
    }

    // ─────────────────────────────────────────────────────────────
    // Compliance
    // ─────────────────────────────────────────────────────────────

    function test_compliance_verifiedToVerifiedAllowed() public view {
        assertTrue(compliance.canTransfer(alice, bob, 100));
    }

    function test_compliance_verifiedToUnverifiedBlocked() public view {
        assertFalse(compliance.canTransfer(alice, dave, 100));
    }

    function test_compliance_unverifiedToVerifiedBlocked() public view {
        assertFalse(compliance.canTransfer(dave, alice, 100));
    }

    function test_compliance_mintToVerifiedAllowed() public view {
        assertTrue(compliance.canTransfer(address(0), alice, 100));
    }

    function test_compliance_mintToUnverifiedBlocked() public view {
        assertFalse(compliance.canTransfer(address(0), dave, 100));
    }

    function test_compliance_burnFromVerifiedAllowed() public view {
        assertTrue(compliance.canTransfer(alice, address(0), 100));
    }

    // ─────────────────────────────────────────────────────────────
    // MilestoneToken — transfer gating
    // ─────────────────────────────────────────────────────────────

    function _indToken() internal view returns (MilestoneToken) {
        return milestoneRegistry.tokens(MilestoneRegistry.Milestone.IND);
    }

    function test_token_mintToAccreditedSucceeds() public {
        MilestoneToken ind = _indToken();
        ind.mint(alice, 100e18);
        assertEq(ind.balanceOf(alice), 100e18);
        assertEq(ind.totalSupply(), 100e18);
    }

    function test_token_mintToNonAccreditedReverts() public {
        MilestoneToken ind = _indToken();
        vm.expectRevert("recipient not compliant");
        ind.mint(dave, 100e18);
    }

    function test_token_transferBetweenAccreditedSucceeds() public {
        MilestoneToken ind = _indToken();
        ind.mint(alice, 100e18);

        vm.prank(alice);
        ind.transfer(bob, 30e18);

        assertEq(ind.balanceOf(alice), 70e18);
        assertEq(ind.balanceOf(bob), 30e18);
    }

    function test_token_transferToNonAccreditedReverts() public {
        MilestoneToken ind = _indToken();
        ind.mint(alice, 100e18);

        vm.prank(alice);
        vm.expectRevert("transfer not compliant");
        ind.transfer(dave, 30e18);
    }

    function test_token_transferFromRevokedHolderReverts() public {
        MilestoneToken ind = _indToken();
        ind.mint(alice, 100e18);

        // Revoke alice's accreditation — she can no longer transfer out
        identityRegistry.revokeClaim(alice, ACCREDITED);

        vm.prank(alice);
        vm.expectRevert("transfer not compliant");
        ind.transfer(bob, 30e18);
    }

    function test_token_burnFromAccreditedSucceeds() public {
        MilestoneToken ind = _indToken();
        ind.mint(alice, 100e18);

        ind.burn(alice, 40e18);
        assertEq(ind.balanceOf(alice), 60e18);
        assertEq(ind.totalSupply(), 60e18);
    }

    function test_token_onlyAgentCanMint() public {
        MilestoneToken ind = _indToken();
        vm.prank(alice);
        vm.expectRevert("only agent");
        ind.mint(bob, 100e18);
    }

    function test_token_transferFromWithApproval() public {
        MilestoneToken ind = _indToken();
        ind.mint(alice, 100e18);

        vm.prank(alice);
        ind.approve(bob, 50e18);

        vm.prank(bob);
        ind.transferFrom(alice, carol, 40e18);

        assertEq(ind.balanceOf(alice), 60e18);
        assertEq(ind.balanceOf(carol), 40e18);
        assertEq(ind.allowance(alice, bob), 10e18);
    }

    // ─────────────────────────────────────────────────────────────
    // MilestoneRegistry — four-token ladder
    // ─────────────────────────────────────────────────────────────

    function test_ladder_allFourTokensDeployed() public view {
        (
            MilestoneToken ind,
            MilestoneToken phase1,
            MilestoneToken phase2,
            MilestoneToken approval
        ) = milestoneRegistry.getAllTokens();

        assertTrue(address(ind) != address(0));
        assertTrue(address(phase1) != address(0));
        assertTrue(address(phase2) != address(0));
        assertTrue(address(approval) != address(0));

        // All distinct
        assertTrue(address(ind) != address(phase1));
        assertTrue(address(phase1) != address(phase2));
        assertTrue(address(phase2) != address(approval));
    }

    function test_ladder_allTokensShareSameIdentityRegistry() public view {
        (
            MilestoneToken ind,
            MilestoneToken phase1,
            MilestoneToken phase2,
            MilestoneToken approval
        ) = milestoneRegistry.getAllTokens();

        assertEq(address(ind.identityRegistry()), address(identityRegistry));
        assertEq(address(phase1.identityRegistry()), address(identityRegistry));
        assertEq(address(phase2.identityRegistry()), address(identityRegistry));
        assertEq(address(approval.identityRegistry()), address(identityRegistry));
    }

    function test_ladder_investorHoldsMultipleMilestones() public {
        (
            MilestoneToken ind,
            MilestoneToken phase1,
            MilestoneToken phase2,
            MilestoneToken approval
        ) = milestoneRegistry.getAllTokens();

        // Alice is registered once, can hold all four
        ind.mint(alice, 100e18);
        phase1.mint(alice, 200e18);
        phase2.mint(alice, 150e18);
        approval.mint(alice, 50e18);

        assertEq(ind.balanceOf(alice), 100e18);
        assertEq(phase1.balanceOf(alice), 200e18);
        assertEq(phase2.balanceOf(alice), 150e18);
        assertEq(approval.balanceOf(alice), 50e18);
    }

    function test_ladder_revocationAffectsAllMilestones() public {
        (MilestoneToken ind, MilestoneToken phase1,,) = milestoneRegistry
            .getAllTokens();

        ind.mint(alice, 100e18);
        phase1.mint(alice, 200e18);

        // Revoke alice's accreditation — she loses ability to transfer on
        // both IND and Phase 1 tokens simultaneously
        identityRegistry.revokeClaim(alice, ACCREDITED);

        vm.prank(alice);
        vm.expectRevert("transfer not compliant");
        ind.transfer(bob, 10e18);

        vm.prank(alice);
        vm.expectRevert("transfer not compliant");
        phase1.transfer(bob, 10e18);
    }
}
