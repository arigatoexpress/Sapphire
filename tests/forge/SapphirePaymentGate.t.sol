// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "forge-std/Test.sol";
import {SapphirePaymentGate} from "../../contracts/SapphirePaymentGate.sol";

/// @title SapphirePaymentGate test suite
/// @notice Behavioural and security coverage for the micropayment + monthly
///         subscription gate that backs the off-chain x402 middleware in
///         `lib/payments/x402_middleware.py`.
/// @dev    14 cases cover happy paths, ACL, two-step treasury transfer,
///         subscription accumulation/expiry, credit consumption, zero-price
///         setter guards, withdraw, and event emission. Generated as part of
///         the Arbitrum London Buildathon smart-contract quality push (sibling
///         to `SapphireSentinelRegistry.t.sol`).
contract SapphirePaymentGateTest is Test {
    SapphirePaymentGate internal gate;

    // Standard actors. We avoid `address(this)` for non-treasury roles so
    // we can flip msg.sender between treasury and others cleanly.
    address internal treasury;
    address internal alice = address(0xA11CE);
    address internal bob = address(0xB0B);
    address internal stranger = address(0xDEAD);

    // Mirror events for vm.expectEmit. Solidity does not allow event
    // imports across contracts, so we redeclare them.
    event PaymentReceived(address indexed from, uint256 amount, string service);
    event SubscriptionActivated(address indexed subscriber, uint256 expiry);
    event CreditsConsumed(address indexed user, uint256 remaining);
    event TreasuryTransferStarted(address indexed previousTreasury, address indexed newTreasury);
    event TreasuryTransferred(address indexed previousTreasury, address indexed newTreasury);

    function setUp() public {
        // Pin block.timestamp so subscription-expiry math is deterministic.
        vm.warp(1_700_000_000);
        treasury = address(this);
        gate = new SapphirePaymentGate();
        // Fund the actors so they can pay.
        vm.deal(alice, 100 ether);
        vm.deal(bob, 100 ether);
        vm.deal(stranger, 100 ether);
    }

    // -----------------------------------------------------------------
    // payPerSignal: credits accumulator + event + insufficient-payment guard
    // -----------------------------------------------------------------

    /// @notice 01 — payPerSignal credits the buyer with floor(value/price)
    ///         signals and emits PaymentReceived with the "signal" tag.
    function test_PayPerSignal_HappyPath_CreditsAndEmits() public {
        uint256 price = gate.pricePerSignal();
        uint256 payment = price * 5;

        vm.expectEmit(true, false, false, true);
        emit PaymentReceived(alice, payment, "signal");

        vm.prank(alice);
        gate.payPerSignal{value: payment}();

        assertEq(gate.credits(alice), 5, "credits = value / price");
        assertTrue(gate.hasAccess(alice), "credit-holder has access");
    }

    /// @notice 02 — payPerSignal reverts when the value is below the per-signal
    ///         price (ensures buyers cannot drip 0-credit payments).
    function test_PayPerSignal_InsufficientPayment_Reverts() public {
        uint256 price = gate.pricePerSignal();
        vm.prank(alice);
        vm.expectRevert(bytes("Insufficient payment"));
        gate.payPerSignal{value: price - 1}();
        assertEq(gate.credits(alice), 0, "no credit on revert");
    }

    // -----------------------------------------------------------------
    // subscribe: 30-day window + accumulation across re-subscribe
    // -----------------------------------------------------------------

    /// @notice 03 — subscribe sets a 30-day expiry from now, emits both
    ///         SubscriptionActivated and PaymentReceived("subscription").
    function test_Subscribe_HappyPath_SetsExpiryAndEmits() public {
        uint256 monthly = gate.monthlySubscription();
        uint256 expectedExpiry = block.timestamp + 30 days;

        vm.expectEmit(true, false, false, true);
        emit SubscriptionActivated(alice, expectedExpiry);
        vm.expectEmit(true, false, false, true);
        emit PaymentReceived(alice, monthly, "subscription");

        vm.prank(alice);
        gate.subscribe{value: monthly}();

        assertEq(gate.subscriptionExpiry(alice), expectedExpiry, "expiry pinned");
        assertTrue(gate.isSubscribed(alice), "subscriber flag");
        assertTrue(gate.hasAccess(alice), "subscriber has access");
    }

    /// @notice 04 — subscribe reverts when the value is below the monthly
    ///         price (ensures the 2026-04-26 "subscribe-for-free" bug stays
    ///         shut for non-zero prices).
    function test_Subscribe_InsufficientPayment_Reverts() public {
        uint256 monthly = gate.monthlySubscription();
        vm.prank(alice);
        vm.expectRevert(bytes("Insufficient payment"));
        gate.subscribe{value: monthly - 1}();
        assertEq(gate.subscriptionExpiry(alice), 0, "no expiry on revert");
    }

    /// @notice 05 — Re-subscribing while still active extends from the
    ///         current expiry, not from now (lossless top-up).
    function test_Subscribe_WhileActive_ExtendsFromCurrentExpiry() public {
        uint256 monthly = gate.monthlySubscription();

        vm.prank(alice);
        gate.subscribe{value: monthly}();
        uint256 firstExpiry = gate.subscriptionExpiry(alice);

        // Move forward 10 days (still inside the first 30-day window).
        vm.warp(block.timestamp + 10 days);

        vm.prank(alice);
        gate.subscribe{value: monthly}();
        uint256 secondExpiry = gate.subscriptionExpiry(alice);

        assertEq(
            secondExpiry,
            firstExpiry + 30 days,
            "extends from first expiry, not from now"
        );
    }

    /// @notice 06 — Re-subscribing AFTER expiry resets the window from now
    ///         (does not stack a stale expiry).
    function test_Subscribe_AfterExpiry_RestartsFromNow() public {
        uint256 monthly = gate.monthlySubscription();
        vm.prank(alice);
        gate.subscribe{value: monthly}();

        // Jump past the first expiry.
        vm.warp(block.timestamp + 31 days);
        assertFalse(gate.isSubscribed(alice), "expired between subs");

        vm.prank(alice);
        gate.subscribe{value: monthly}();
        assertEq(
            gate.subscriptionExpiry(alice),
            block.timestamp + 30 days,
            "resets from current block"
        );
    }

    // -----------------------------------------------------------------
    // consumeCredit: ACL + monotonic decrement + empty guard
    // -----------------------------------------------------------------

    /// @notice 07 — consumeCredit is treasury-only and emits CreditsConsumed
    ///         with the post-decrement balance.
    function test_ConsumeCredit_HappyPath_DecrementsAndEmits() public {
        uint256 price = gate.pricePerSignal();
        vm.prank(alice);
        gate.payPerSignal{value: price * 3}();

        vm.expectEmit(true, false, false, true);
        emit CreditsConsumed(alice, 2);
        gate.consumeCredit(alice);

        assertEq(gate.credits(alice), 2, "credits decremented");
    }

    /// @notice 08 — Non-treasury cannot consume credits.
    function test_ConsumeCredit_OnlyTreasury_Reverts() public {
        uint256 price = gate.pricePerSignal();
        vm.prank(alice);
        gate.payPerSignal{value: price}();

        vm.prank(stranger);
        vm.expectRevert(bytes("Not treasury"));
        gate.consumeCredit(alice);
    }

    /// @notice 09 — consumeCredit reverts when the user has no credits
    ///         (pre-payment / fully spent).
    function test_ConsumeCredit_EmptyBalance_Reverts() public {
        vm.expectRevert(bytes("No credits"));
        gate.consumeCredit(alice);
    }

    // -----------------------------------------------------------------
    // Setter ACL + zero-price guards (closes the 2026-04-26 contracts review)
    // -----------------------------------------------------------------

    /// @notice 10 — setPricePerSignal rejects zero (would cause
    ///         division-by-zero DoS in payPerSignal) and is treasury-only.
    function test_SetPricePerSignal_ZeroAndACL_Revert() public {
        // Zero price guard.
        vm.expectRevert(bytes("Zero price"));
        gate.setPricePerSignal(0);

        // ACL guard.
        vm.prank(stranger);
        vm.expectRevert(bytes("Not treasury"));
        gate.setPricePerSignal(0.002 ether);

        // Happy path — treasury, non-zero.
        gate.setPricePerSignal(0.002 ether);
        assertEq(gate.pricePerSignal(), 0.002 ether, "price updated");
    }

    /// @notice 11 — setMonthlySubscription rejects zero (would let anyone
    ///         subscribe for free) and is treasury-only.
    function test_SetMonthlySubscription_ZeroAndACL_Revert() public {
        // Zero price guard.
        vm.expectRevert(bytes("Zero price"));
        gate.setMonthlySubscription(0);

        // ACL guard.
        vm.prank(stranger);
        vm.expectRevert(bytes("Not treasury"));
        gate.setMonthlySubscription(0.2 ether);

        // Happy path.
        gate.setMonthlySubscription(0.2 ether);
        assertEq(gate.monthlySubscription(), 0.2 ether, "monthly updated");
    }

    // -----------------------------------------------------------------
    // withdraw: ACL + balance drain to treasury
    // -----------------------------------------------------------------

    /// @notice 12 — withdraw is treasury-only and drains the contract's
    ///         entire balance to the treasury address.
    function test_Withdraw_DrainsToTreasury_OnlyTreasury() public {
        // Use a payable-EOA treasury so .transfer() succeeds, then nominate
        // it via the two-step handover so the gate's treasury matches.
        address payable payableTreasury = payable(address(0xCAFE));
        gate.transferTreasury(payableTreasury);
        vm.prank(payableTreasury);
        gate.acceptTreasury();

        // Stranger blocked.
        vm.prank(stranger);
        vm.expectRevert(bytes("Not treasury"));
        gate.withdraw();

        // Fund the gate via a real subscription so balance is non-zero.
        uint256 monthly = gate.monthlySubscription();
        vm.prank(alice);
        gate.subscribe{value: monthly}();
        assertEq(address(gate).balance, monthly, "gate funded");

        // New treasury drains the balance.
        uint256 before = payableTreasury.balance;
        vm.prank(payableTreasury);
        gate.withdraw();

        assertEq(address(gate).balance, 0, "gate drained");
        assertEq(payableTreasury.balance, before + monthly, "treasury credited");
    }

    // -----------------------------------------------------------------
    // Two-step treasury transfer (mirrors Sentinel's operator pattern)
    // -----------------------------------------------------------------

    /// @notice 13 — Two-step treasury handover: transferTreasury sets the
    ///         pendingTreasury and emits TreasuryTransferStarted; only the
    ///         pendingTreasury can finalise via acceptTreasury(), which
    ///         clears the pending slot and emits TreasuryTransferred.
    ///         Zero address is rejected at the nomination step.
    function test_TreasuryTransfer_TwoStepHandover() public {
        address newTreasury = address(0xBEEF);

        // Zero-address nomination guard.
        vm.expectRevert(bytes("Zero address"));
        gate.transferTreasury(address(0));

        // Non-treasury cannot start a transfer.
        vm.prank(stranger);
        vm.expectRevert(bytes("Not treasury"));
        gate.transferTreasury(newTreasury);

        // Treasury nominates.
        vm.expectEmit(true, true, false, false);
        emit TreasuryTransferStarted(treasury, newTreasury);
        gate.transferTreasury(newTreasury);

        assertEq(gate.pendingTreasury(), newTreasury, "pending slot");
        assertEq(gate.treasury(), treasury, "treasury unchanged until accept");

        // Stranger cannot accept.
        vm.prank(stranger);
        vm.expectRevert(bytes("Not pending treasury"));
        gate.acceptTreasury();

        // Pending treasury accepts → treasury flips, pending clears.
        vm.expectEmit(true, true, false, false);
        emit TreasuryTransferred(treasury, newTreasury);
        vm.prank(newTreasury);
        gate.acceptTreasury();

        assertEq(gate.treasury(), newTreasury, "treasury promoted");
        assertEq(gate.pendingTreasury(), address(0), "pending cleared");
    }

    // -----------------------------------------------------------------
    // Fuzz: payPerSignal credits = floor(value / price), no overflow
    // -----------------------------------------------------------------

    /// @notice 14 — Fuzz: any payment that is at least price-sized produces
    ///         exactly floor(value / price) credits and accumulates across
    ///         calls. Bound prevents OOG and astronomical payments.
    function testFuzz_PayPerSignal_CreditsAreFloorDivision(uint256 multiplier) public {
        multiplier = bound(multiplier, 1, 1_000_000);
        uint256 price = gate.pricePerSignal();
        uint256 payment = price * multiplier;
        vm.deal(bob, payment);

        vm.prank(bob);
        gate.payPerSignal{value: payment}();
        assertEq(gate.credits(bob), multiplier, "credits = value / price");
    }
}
