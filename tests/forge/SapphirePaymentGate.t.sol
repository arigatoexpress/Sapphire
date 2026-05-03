// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "forge-std/Test.sol";
import {SapphirePaymentGate} from "../../contracts/SapphirePaymentGate.sol";

/// @title SapphirePaymentGate test suite
/// @notice Behavioural + security coverage for the micropayment + monthly
///         subscription gate. Specifically covers the Slither best-practice
///         patches landed for the London Buildathon smart-contract-quality
///         criterion: `.call{value:}` withdraw path, inline non-reentrancy
///         lock, and setter events.
contract SapphirePaymentGateTest is Test {
    SapphirePaymentGate internal gate;

    address internal treasury;
    address internal user = address(0xBEEF);
    address internal stranger = address(0xDEAD);

    event PaymentReceived(address indexed from, uint256 amount, string service);
    event SubscriptionActivated(address indexed subscriber, uint256 expiry);
    event PricePerSignalUpdated(uint256 oldPrice, uint256 newPrice);
    event MonthlySubscriptionUpdated(uint256 oldPrice, uint256 newPrice);
    event TreasuryWithdrawal(address indexed to, uint256 amount);

    function setUp() public {
        treasury = address(this);
        gate = new SapphirePaymentGate();
        vm.deal(user, 100 ether);
    }

    // -----------------------------------------------------------------
    // Withdraw: .call{value:} happy path + return-value check
    // -----------------------------------------------------------------

    /// @notice 01 — Withdraw via `.call{value:}` succeeds for an EOA treasury,
    ///         drains the balance, and emits TreasuryWithdrawal.
    function test_Withdraw_HappyPath_DrainsBalanceAndEmits() public {
        vm.prank(user);
        gate.payPerSignal{value: 1 ether}();
        assertEq(address(gate).balance, 1 ether, "gate funded");

        uint256 before = treasury.balance;
        vm.expectEmit(true, false, false, true);
        emit TreasuryWithdrawal(treasury, 1 ether);
        gate.withdraw();

        assertEq(address(gate).balance, 0, "gate drained");
        assertEq(treasury.balance, before + 1 ether, "treasury credited");
    }

    /// @notice 02 — Withdraw rejects when the contract balance is zero so an
    ///         operator typo doesn't emit a no-op event.
    function test_Withdraw_ZeroBalance_Reverts() public {
        vm.expectRevert(bytes("Nothing to withdraw"));
        gate.withdraw();
    }

    /// @notice 03 — Only the treasury can withdraw.
    function test_Withdraw_OnlyTreasury_Reverts() public {
        vm.prank(user);
        gate.payPerSignal{value: 1 ether}();

        vm.prank(stranger);
        vm.expectRevert(bytes("Not treasury"));
        gate.withdraw();
    }

    /// @notice 04 — Withdraw to a smart-contract treasury whose `receive()`
    ///         consumes more than the legacy 2300-gas stipend succeeds. This
    ///         is the regression test for the `.transfer()` -> `.call{value:}`
    ///         migration: under the old path this transaction would revert
    ///         post-Istanbul.
    function test_Withdraw_ContractTreasuryAboveStipend_Succeeds() public {
        GasHungryTreasury hungry = new GasHungryTreasury();
        // Hand over treasury to the gas-hungry contract via two-step transfer.
        gate.transferTreasury(address(hungry));
        hungry.acceptFrom(gate);

        vm.prank(user);
        gate.payPerSignal{value: 1 ether}();

        vm.prank(address(hungry));
        gate.withdraw();
        assertEq(address(hungry).balance, 1 ether, "gas-hungry treasury funded");
    }

    // -----------------------------------------------------------------
    // Reentrancy: malicious treasury cannot drain twice
    // -----------------------------------------------------------------

    /// @notice 05 — A malicious contract treasury that re-enters `withdraw()`
    ///         from its `receive()` is blocked by the inline non-reentrancy
    ///         lock. The outer call surfaces the inner revert.
    function test_Withdraw_Reentrancy_BlockedByGuard() public {
        ReentrantTreasury attacker = new ReentrantTreasury();
        gate.transferTreasury(address(attacker));
        attacker.acceptFrom(gate);

        vm.prank(user);
        gate.payPerSignal{value: 1 ether}();

        vm.prank(address(attacker));
        vm.expectRevert(bytes("Withdraw failed"));
        gate.withdraw();

        // Funds remain in the gate because the outer call reverted.
        assertEq(address(gate).balance, 1 ether, "balance preserved on reentrancy");
    }

    // -----------------------------------------------------------------
    // Setter events: events-maths Slither finding fix
    // -----------------------------------------------------------------

    /// @notice 06 — setPricePerSignal emits PricePerSignalUpdated with old/new.
    function test_SetPricePerSignal_EmitsEvent() public {
        uint256 oldPrice = gate.pricePerSignal();
        uint256 newPrice = oldPrice * 2;

        vm.expectEmit(false, false, false, true);
        emit PricePerSignalUpdated(oldPrice, newPrice);
        gate.setPricePerSignal(newPrice);
        assertEq(gate.pricePerSignal(), newPrice, "price updated");
    }

    /// @notice 07 — setMonthlySubscription emits MonthlySubscriptionUpdated.
    function test_SetMonthlySubscription_EmitsEvent() public {
        uint256 oldPrice = gate.monthlySubscription();
        uint256 newPrice = oldPrice * 3;

        vm.expectEmit(false, false, false, true);
        emit MonthlySubscriptionUpdated(oldPrice, newPrice);
        gate.setMonthlySubscription(newPrice);
        assertEq(gate.monthlySubscription(), newPrice, "subscription updated");
    }

    /// @notice 08 — Zero price is still rejected on both setters (preserves
    ///         the divide-by-zero / free-subscription guards from the
    ///         2026-04-26 review).
    function test_Setters_ZeroPrice_Reverts() public {
        vm.expectRevert(bytes("Zero price"));
        gate.setPricePerSignal(0);
        vm.expectRevert(bytes("Zero price"));
        gate.setMonthlySubscription(0);
    }

    // The contract under test sends ETH to address(this) in the happy-path
    // withdraw test; we accept it silently here.
    receive() external payable {}
}

/// @notice Smart-contract treasury whose `receive()` consumes more than the
///         deprecated 2300-gas stipend. Used to prove the `.transfer()` ->
///         `.call{value:}` patch unblocks contract treasuries.
contract GasHungryTreasury {
    uint256 public counter;

    function acceptFrom(SapphirePaymentGate gate) external {
        gate.acceptTreasury();
    }

    receive() external payable {
        // Cheap storage writes that exceed the 2300-gas stipend.
        for (uint256 i = 0; i < 8; i++) {
            counter = counter + 1;
        }
    }
}

/// @notice Malicious treasury that re-enters `withdraw()` during `receive()`.
///         The non-reentrancy guard on `withdraw()` causes the inner call to
///         revert, which propagates out as `Withdraw failed`.
contract ReentrantTreasury {
    SapphirePaymentGate internal gate;
    bool internal armed = true;

    function acceptFrom(SapphirePaymentGate _gate) external {
        gate = _gate;
        gate.acceptTreasury();
    }

    receive() external payable {
        if (armed) {
            armed = false;
            // This call must revert because the outer withdraw holds the
            // reentrancy lock.
            gate.withdraw();
        }
    }
}
