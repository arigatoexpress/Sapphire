// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "forge-std/Test.sol";
import {SapphireSentinelRegistry} from "../../contracts/SapphireSentinelRegistry.sol";

/// @title SapphireSentinelRegistry test suite
/// @notice Behavioural and security coverage for the non-custodial mandate +
///         payment-evaluation registry deployed on Robinhood Chain testnet.
/// @dev    18 test cases cover happy paths, ACL, replay protection, hash
///         binding, expiry, two-step operator transfer, edge cases, and
///         event emissions. Generated as part of the Arbitrum London
///         Buildathon smart-contract quality push.
contract SapphireSentinelRegistryTest is Test {
    SapphireSentinelRegistry internal registry;

    // Standard actors. We avoid `address(this)` for non-operator roles so
    // we can flip msg.sender between operator and others cleanly.
    address internal operator;
    address internal controller = address(0xC0117);
    address internal agent = address(0xA9E47);
    address internal payer = address(0xBABE);
    address internal stranger = address(0xDEAD);

    // Reusable identifiers/hashes — keccak256 of human-readable seeds so the
    // test traces tell you what each value is.
    bytes32 internal constant MANDATE_ID = keccak256("mandate:alpha");
    bytes32 internal constant RECEIPT_ID = keccak256("receipt:alpha-1");
    bytes32 internal constant POLICY_HASH = keccak256("policy:default");
    bytes32 internal constant RESOURCE_HASH = keccak256("resource:rwa-signal");
    bytes32 internal constant RESULT_HASH = keccak256("result:approved");
    bytes32 internal constant RISK_HASH = keccak256("risk:nominal");

    uint96 internal constant MAX_SPEND = 1_000_000; // 1.0 in 6-decimal atomic units
    uint64 internal constant FUTURE_EXPIRY = 1_000_000_000;

    // Mirror events for vm.expectEmit. Solidity does not allow event
    // imports across contracts, so we redeclare them.
    event MandateRegistered(
        bytes32 indexed mandateId,
        address indexed controller,
        address indexed agent,
        uint96 maxSpendAtomic,
        uint64 expiresAt,
        bytes32 policyHash
    );
    event MandateRevoked(bytes32 indexed mandateId);
    event PaymentEvaluated(
        bytes32 indexed receiptId,
        bytes32 indexed mandateId,
        address indexed payer,
        bool approved,
        uint96 amountAtomic,
        bytes32 resourceHash,
        bytes32 resultHash,
        bytes32 riskHash
    );
    event OperatorTransferStarted(address indexed previousOperator, address indexed newOperator);
    event OperatorTransferred(address indexed previousOperator, address indexed newOperator);

    function setUp() public {
        // Pin block.timestamp to a deterministic value so expiry math is
        // not sensitive to forge's default starting timestamp.
        vm.warp(1_700_000_000);
        operator = address(this);
        registry = new SapphireSentinelRegistry();
    }

    // -----------------------------------------------------------------
    // Mandate creation: happy path + ACL + duplicate guard
    // -----------------------------------------------------------------

    /// @notice 01 — registerMandate persists every field and emits the
    ///         documented event with all three indexed topics.
    function test_RegisterMandate_HappyPath_PersistsAndEmits() public {
        vm.expectEmit(true, true, true, true);
        emit MandateRegistered(MANDATE_ID, controller, agent, MAX_SPEND, FUTURE_EXPIRY, POLICY_HASH);

        registry.registerMandate(
            MANDATE_ID, controller, agent, MAX_SPEND, FUTURE_EXPIRY, POLICY_HASH
        );

        (
            address storedController,
            address storedAgent,
            uint96 storedMax,
            uint96 storedSpent,
            uint64 storedExpiry,
            bytes32 storedPolicy,
            bool storedRevoked
        ) = registry.mandates(MANDATE_ID);

        assertEq(storedController, controller, "controller");
        assertEq(storedAgent, agent, "agent");
        assertEq(storedMax, MAX_SPEND, "max spend");
        assertEq(storedSpent, 0, "spent starts at zero");
        assertEq(storedExpiry, FUTURE_EXPIRY, "expiry");
        assertEq(storedPolicy, POLICY_HASH, "policy hash");
        assertFalse(storedRevoked, "starts unrevoked");
        assertTrue(registry.isMandateActive(MANDATE_ID), "active right after registration");
    }

    /// @notice 02 — Only the operator can register mandates.
    function test_RegisterMandate_OnlyOperator_Reverts() public {
        vm.prank(stranger);
        vm.expectRevert(bytes("Not operator"));
        registry.registerMandate(
            MANDATE_ID, controller, agent, MAX_SPEND, FUTURE_EXPIRY, POLICY_HASH
        );
    }

    /// @notice 03 — Cannot register a mandate that already expires at-or-before
    ///         block.timestamp.
    function test_RegisterMandate_ExpiredMandate_Reverts() public {
        vm.expectRevert(bytes("Expired mandate"));
        registry.registerMandate(
            MANDATE_ID, controller, agent, MAX_SPEND, uint64(block.timestamp), POLICY_HASH
        );
    }

    /// @notice 04 — Re-registering the same mandateId is rejected.
    function test_RegisterMandate_DoubleCreate_Reverts() public {
        registry.registerMandate(
            MANDATE_ID, controller, agent, MAX_SPEND, FUTURE_EXPIRY, POLICY_HASH
        );
        vm.expectRevert(bytes("Mandate exists"));
        registry.registerMandate(
            MANDATE_ID, controller, agent, MAX_SPEND, FUTURE_EXPIRY, POLICY_HASH
        );
    }

    /// @notice 05 — Zero-address agent is rejected at the input-validation
    ///         layer (input-sanitization sweep).
    function test_RegisterMandate_ZeroAgent_Reverts() public {
        vm.expectRevert(bytes("Zero agent"));
        registry.registerMandate(
            MANDATE_ID, controller, address(0), MAX_SPEND, FUTURE_EXPIRY, POLICY_HASH
        );
    }

    // -----------------------------------------------------------------
    // Payment evaluation: structure + ACL + monotonic spend tracking
    // -----------------------------------------------------------------

    /// @notice 06 — recordPaymentEvaluation stores every field, increments
    ///         spentAtomic on approval, and emits PaymentEvaluated.
    function test_RecordPayment_HappyPath_PersistsAndEmits() public {
        _registerDefaultMandate();

        vm.expectEmit(true, true, true, true);
        emit PaymentEvaluated(
            RECEIPT_ID, MANDATE_ID, payer, true, 100, RESOURCE_HASH, RESULT_HASH, RISK_HASH
        );

        registry.recordPaymentEvaluation(
            RECEIPT_ID, MANDATE_ID, payer, 100, RESOURCE_HASH, RESULT_HASH, RISK_HASH, true
        );

        (
            bytes32 mandateId,
            address storedPayer,
            uint96 amount,
            bytes32 resource,
            bytes32 result,
            bytes32 risk,
            uint64 timestamp,
            bool approved
        ) = registry.receipts(RECEIPT_ID);

        assertEq(mandateId, MANDATE_ID, "mandate ref");
        assertEq(storedPayer, payer, "payer");
        assertEq(amount, 100, "amount");
        assertEq(resource, RESOURCE_HASH, "resource hash");
        assertEq(result, RESULT_HASH, "result hash");
        assertEq(risk, RISK_HASH, "risk hash");
        assertEq(timestamp, uint64(block.timestamp), "timestamp pinned to block");
        assertTrue(approved, "approved flag");

        // Spend tracking: approved payments decrement remaining spend.
        assertEq(registry.remainingSpend(MANDATE_ID), MAX_SPEND - 100, "remaining spend updated");
    }

    /// @notice 07 — Non-operator is locked out of recordPaymentEvaluation.
    function test_RecordPayment_OnlyOperator_Reverts() public {
        _registerDefaultMandate();
        vm.prank(stranger);
        vm.expectRevert(bytes("Not operator"));
        registry.recordPaymentEvaluation(
            RECEIPT_ID, MANDATE_ID, payer, 100, RESOURCE_HASH, RESULT_HASH, RISK_HASH, true
        );
    }

    /// @notice 08 — Replay protection: the same receiptId is rejected on
    ///         the second attempt regardless of payload mutation.
    function test_RecordPayment_Replay_SameReceiptId_Reverts() public {
        _registerDefaultMandate();
        registry.recordPaymentEvaluation(
            RECEIPT_ID, MANDATE_ID, payer, 100, RESOURCE_HASH, RESULT_HASH, RISK_HASH, true
        );
        // Second call with the same receiptId must revert even if payload differs.
        vm.expectRevert(bytes("Receipt exists"));
        registry.recordPaymentEvaluation(
            RECEIPT_ID,
            MANDATE_ID,
            payer,
            200, // different amount — replay still rejected
            RESOURCE_HASH,
            RESULT_HASH,
            RISK_HASH,
            true
        );
    }

    /// @notice 09 — Hash binding: tampering with a stored receipt requires
    ///         re-recording with a different receiptId. We assert that an
    ///         attempt to "rewrite history" using the original receiptId
    ///         is impossible (replay guard above), and that distinct
    ///         payloads produce distinct on-chain hashes.
    function test_RecordPayment_HashBinding_TamperingProducesDifferentReceipt() public {
        _registerDefaultMandate();
        registry.recordPaymentEvaluation(
            RECEIPT_ID, MANDATE_ID, payer, 100, RESOURCE_HASH, RESULT_HASH, RISK_HASH, true
        );

        bytes32 tamperedReceiptId = keccak256("receipt:alpha-1-tampered");
        bytes32 tamperedResult = keccak256("result:tampered");
        registry.recordPaymentEvaluation(
            tamperedReceiptId,
            MANDATE_ID,
            payer,
            100,
            RESOURCE_HASH,
            tamperedResult,
            RISK_HASH,
            true
        );

        (, , , , bytes32 originalResult, , , ) = registry.receipts(RECEIPT_ID);
        (, , , , bytes32 newResult, , , ) = registry.receipts(tamperedReceiptId);

        assertEq(originalResult, RESULT_HASH, "original receipt result hash unchanged");
        assertEq(newResult, tamperedResult, "tampered payload anchored under different id");
        assertTrue(originalResult != newResult, "tampering must surface as new receipt");
    }

    /// @notice 10 — Spend cap: cumulative approved amounts cannot exceed
    ///         maxSpendAtomic. Underflow/overflow guard.
    function test_RecordPayment_SpendCap_Exceeded_Reverts() public {
        _registerDefaultMandate();
        registry.recordPaymentEvaluation(
            keccak256("r1"), MANDATE_ID, payer, MAX_SPEND - 50, RESOURCE_HASH, RESULT_HASH, RISK_HASH, true
        );
        // Second approved evaluation exceeds the cap.
        vm.expectRevert(bytes("Spend limit exceeded"));
        registry.recordPaymentEvaluation(
            keccak256("r2"), MANDATE_ID, payer, 100, RESOURCE_HASH, RESULT_HASH, RISK_HASH, true
        );
    }

    /// @notice 11 — Rejected (non-approved) payments do not consume spend
    ///         budget but still anchor an auditable receipt.
    function test_RecordPayment_Rejected_DoesNotConsumeBudget() public {
        _registerDefaultMandate();
        registry.recordPaymentEvaluation(
            RECEIPT_ID, MANDATE_ID, payer, 0, RESOURCE_HASH, RESULT_HASH, RISK_HASH, false
        );
        assertEq(registry.remainingSpend(MANDATE_ID), MAX_SPEND, "rejected: budget untouched");
        (, , , , , , , bool approved) = registry.receipts(RECEIPT_ID);
        assertFalse(approved, "rejected receipt persists with approved=false");
    }

    /// @notice 12 — Cannot record payment against an unknown mandate.
    function test_RecordPayment_UnknownMandate_Reverts() public {
        vm.expectRevert(bytes("Unknown mandate"));
        registry.recordPaymentEvaluation(
            RECEIPT_ID, MANDATE_ID, payer, 100, RESOURCE_HASH, RESULT_HASH, RISK_HASH, true
        );
    }

    // -----------------------------------------------------------------
    // Revocation + expiry
    // -----------------------------------------------------------------

    /// @notice 13 — Revocation flips the active flag and blocks further
    ///         payments; emits MandateRevoked.
    function test_RevokeMandate_BlocksFurtherPayments() public {
        _registerDefaultMandate();
        vm.expectEmit(true, false, false, false);
        emit MandateRevoked(MANDATE_ID);
        registry.revokeMandate(MANDATE_ID);
        assertFalse(registry.isMandateActive(MANDATE_ID), "revoked mandate is not active");

        vm.expectRevert(bytes("Mandate revoked"));
        registry.recordPaymentEvaluation(
            RECEIPT_ID, MANDATE_ID, payer, 100, RESOURCE_HASH, RESULT_HASH, RISK_HASH, true
        );
    }

    /// @notice 14 — A mandate that was valid at creation but has since
    ///         expired blocks new payment evaluations.
    function test_RecordPayment_ExpiredMandate_Reverts() public {
        _registerDefaultMandate();
        // Jump past the expiry timestamp.
        vm.warp(uint256(FUTURE_EXPIRY) + 1);
        assertFalse(registry.isMandateActive(MANDATE_ID), "expired mandate is inactive");
        vm.expectRevert(bytes("Mandate expired"));
        registry.recordPaymentEvaluation(
            RECEIPT_ID, MANDATE_ID, payer, 100, RESOURCE_HASH, RESULT_HASH, RISK_HASH, true
        );
    }

    // -----------------------------------------------------------------
    // Read-only views
    // -----------------------------------------------------------------

    /// @notice 15 — `remainingSpend` returns 0 for unknown mandates and
    ///         saturates correctly when fully spent.
    function test_RemainingSpend_UnknownAndSaturated() public {
        assertEq(registry.remainingSpend(keccak256("nope")), 0, "unknown mandate -> 0");

        _registerDefaultMandate();
        registry.recordPaymentEvaluation(
            RECEIPT_ID, MANDATE_ID, payer, MAX_SPEND, RESOURCE_HASH, RESULT_HASH, RISK_HASH, true
        );
        assertEq(registry.remainingSpend(MANDATE_ID), 0, "fully spent -> 0");
    }

    /// @notice 16 — `isMandateActive` returns false for any not-yet-created
    ///         id (zero-controller sentinel).
    function test_IsMandateActive_UnknownReturnsFalse() public {
        assertFalse(registry.isMandateActive(keccak256("nope")), "unknown mandate -> inactive");
    }

    // -----------------------------------------------------------------
    // Two-step operator transfer
    // -----------------------------------------------------------------

    /// @notice 17 — Two-step operator handover: transferOperator sets the
    ///         pendingOperator and emits OperatorTransferStarted; only the
    ///         pendingOperator can finalise via acceptOperator(), which
    ///         clears the pending slot and emits OperatorTransferred.
    function test_OperatorTransfer_TwoStepHandover() public {
        address newOperator = address(0xBEEF);

        vm.expectEmit(true, true, false, false);
        emit OperatorTransferStarted(operator, newOperator);
        registry.transferOperator(newOperator);

        assertEq(registry.pendingOperator(), newOperator, "pending slot");
        assertEq(registry.operator(), operator, "operator unchanged until accept");

        // Stranger cannot accept.
        vm.prank(stranger);
        vm.expectRevert(bytes("Not pending operator"));
        registry.acceptOperator();

        // Pending operator accepts → operator flips, pending clears.
        vm.expectEmit(true, true, false, false);
        emit OperatorTransferred(operator, newOperator);
        vm.prank(newOperator);
        registry.acceptOperator();

        assertEq(registry.operator(), newOperator, "operator promoted");
        assertEq(registry.pendingOperator(), address(0), "pending cleared");
    }

    // -----------------------------------------------------------------
    // Edge cases / fuzzing
    // -----------------------------------------------------------------

    /// @notice 18 — Fuzz harness: any random uint96 amount that fits inside
    ///         a fresh mandate's budget is accepted exactly once and
    ///         updates remainingSpend by exactly that delta.
    function testFuzz_RecordPayment_AmountWithinBudget(uint96 amount) public {
        amount = uint96(bound(uint256(amount), 1, MAX_SPEND));
        _registerDefaultMandate();

        registry.recordPaymentEvaluation(
            RECEIPT_ID, MANDATE_ID, payer, amount, RESOURCE_HASH, RESULT_HASH, RISK_HASH, true
        );
        assertEq(
            registry.remainingSpend(MANDATE_ID),
            MAX_SPEND - amount,
            "remainingSpend reflects exact delta"
        );
    }

    // -----------------------------------------------------------------
    // Helpers
    // -----------------------------------------------------------------

    function _registerDefaultMandate() internal {
        registry.registerMandate(
            MANDATE_ID, controller, agent, MAX_SPEND, FUTURE_EXPIRY, POLICY_HASH
        );
    }
}
