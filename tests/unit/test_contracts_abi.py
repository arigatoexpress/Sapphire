"""Smoke tests for the two production Solidity contracts.

These are *text-level* tests over the `.sol` source — they do not invoke
`forge` (not installed in CI per the 2026-04-26 contracts review) or compile
the bytecode. The intent is narrow: guard the High-finding fixes from the
2026-04-26 review (`docs/security/contracts-review-2026-04-26.md`) against
accidental regressions, and pin the public ABI surfaces that the deploy script
and the off-chain `lib/payments/x402_middleware.py` rely on.

If a future PR rewrites either contract (e.g. moves to OpenZeppelin
`Ownable2Step` or changes the function signatures), this file should be the
first thing to update — the assertions here are deliberately strict so the
breakage is visible at PR review time, not at deploy time.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
CONTRACTS = ROOT / "contracts"
SIGNAL_VERIFIER = CONTRACTS / "SapphireSignalVerifier.sol"
PAYMENT_GATE = CONTRACTS / "SapphirePaymentGate.sol"


@pytest.fixture(scope="module")
def signal_verifier_src() -> str:
    assert SIGNAL_VERIFIER.exists(), f"missing contract: {SIGNAL_VERIFIER}"
    return SIGNAL_VERIFIER.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def payment_gate_src() -> str:
    assert PAYMENT_GATE.exists(), f"missing contract: {PAYMENT_GATE}"
    return PAYMENT_GATE.read_text(encoding="utf-8")


# -----------------------------------------------------------------------------
# Pragma / compiler invariants. The 2026-04-26 review pinned 0.8.20.
# -----------------------------------------------------------------------------


def test_signal_verifier_pragma_0_8_20(signal_verifier_src: str) -> None:
    assert "pragma solidity ^0.8.20;" in signal_verifier_src


def test_payment_gate_pragma_0_8_20(payment_gate_src: str) -> None:
    assert "pragma solidity ^0.8.20;" in payment_gate_src


def test_no_openzeppelin_import(signal_verifier_src: str, payment_gate_src: str) -> None:
    """The follow-up PR is constrained to no new dependencies. Hand-rolled
    two-step transfer, no OZ Ownable2Step.
    """
    for src in (signal_verifier_src, payment_gate_src):
        assert "@openzeppelin" not in src
        assert "import " not in src


# -----------------------------------------------------------------------------
# High finding 1 + 2: SapphirePaymentGate setters reject zero price.
# -----------------------------------------------------------------------------


def test_set_price_per_signal_rejects_zero(payment_gate_src: str) -> None:
    """High: `setPricePerSignal(0)` previously allowed a DoS via division panic
    in `payPerSignal()`. The fix adds `require(price > 0, "Zero price")`.
    """
    setter = _extract_function(payment_gate_src, "setPricePerSignal")
    assert 'require(price > 0, "Zero price")' in setter


def test_set_monthly_subscription_rejects_zero(payment_gate_src: str) -> None:
    """High: `setMonthlySubscription(0)` previously allowed any caller to get a
    30-day subscription for 0 wei. The fix adds `require(price > 0, "Zero price")`.
    """
    setter = _extract_function(payment_gate_src, "setMonthlySubscription")
    assert 'require(price > 0, "Zero price")' in setter


# -----------------------------------------------------------------------------
# High finding 3: two-step role transfer on both contracts.
# -----------------------------------------------------------------------------


def test_signal_verifier_has_pending_operator(signal_verifier_src: str) -> None:
    """Two-step transfer requires a `pendingOperator` storage slot."""
    assert re.search(
        r"address\s+public\s+pendingOperator\s*;", signal_verifier_src
    ), "missing `address public pendingOperator;` storage slot"


def test_signal_verifier_has_accept_operator(signal_verifier_src: str) -> None:
    """Two-step transfer requires an `acceptOperator()` function."""
    assert re.search(
        r"function\s+acceptOperator\s*\(\s*\)\s+external", signal_verifier_src
    ), "missing `function acceptOperator() external` declaration"


def test_signal_verifier_transfer_operator_emits_started(signal_verifier_src: str) -> None:
    """`transferOperator` should now emit `OperatorTransferStarted` (step 1)
    instead of mutating `operator` directly.
    """
    fn = _extract_function(signal_verifier_src, "transferOperator")
    assert "pendingOperator = newOperator;" in fn
    assert "emit OperatorTransferStarted(" in fn
    # And critically: it must NOT set `operator = newOperator;` any more —
    # that's the whole point of two-step.
    assert "operator = newOperator;" not in fn


def test_signal_verifier_accept_operator_finalises(signal_verifier_src: str) -> None:
    """`acceptOperator` is the only path that mutates `operator` post-deployment."""
    fn = _extract_function(signal_verifier_src, "acceptOperator")
    assert 'require(msg.sender == pendingOperator, "Not pending operator")' in fn
    assert "operator = pendingOperator;" in fn
    assert "pendingOperator = address(0);" in fn
    assert "emit OperatorTransferred(" in fn


def test_signal_verifier_events_declared(signal_verifier_src: str) -> None:
    """Both new events must be declared at contract scope."""
    assert re.search(
        r"event\s+OperatorTransferStarted\s*\(\s*address\s+indexed\s+previousOperator\s*,"
        r"\s*address\s+indexed\s+newOperator\s*\)",
        signal_verifier_src,
    )
    assert re.search(
        r"event\s+OperatorTransferred\s*\(\s*address\s+indexed\s+previousOperator\s*,"
        r"\s*address\s+indexed\s+newOperator\s*\)",
        signal_verifier_src,
    )


def test_payment_gate_has_pending_treasury(payment_gate_src: str) -> None:
    """Two-step transfer requires a `pendingTreasury` storage slot."""
    assert re.search(
        r"address\s+public\s+pendingTreasury\s*;", payment_gate_src
    ), "missing `address public pendingTreasury;` storage slot"


def test_payment_gate_has_accept_treasury(payment_gate_src: str) -> None:
    """Two-step transfer requires an `acceptTreasury()` function."""
    assert re.search(
        r"function\s+acceptTreasury\s*\(\s*\)\s+external", payment_gate_src
    ), "missing `function acceptTreasury() external` declaration"


def test_payment_gate_transfer_treasury_emits_started(payment_gate_src: str) -> None:
    """`transferTreasury` should now emit `TreasuryTransferStarted` (step 1)
    instead of mutating `treasury` directly.
    """
    fn = _extract_function(payment_gate_src, "transferTreasury")
    assert "pendingTreasury = newTreasury;" in fn
    assert "emit TreasuryTransferStarted(" in fn
    assert "treasury = newTreasury;" not in fn


def test_payment_gate_accept_treasury_finalises(payment_gate_src: str) -> None:
    """`acceptTreasury` is the only path that mutates `treasury` post-deployment."""
    fn = _extract_function(payment_gate_src, "acceptTreasury")
    assert 'require(msg.sender == pendingTreasury, "Not pending treasury")' in fn
    assert "treasury = pendingTreasury;" in fn
    assert "pendingTreasury = address(0);" in fn
    assert "emit TreasuryTransferred(" in fn


def test_payment_gate_events_declared(payment_gate_src: str) -> None:
    """Both new events must be declared at contract scope."""
    assert re.search(
        r"event\s+TreasuryTransferStarted\s*\(\s*address\s+indexed\s+previousTreasury\s*,"
        r"\s*address\s+indexed\s+newTreasury\s*\)",
        payment_gate_src,
    )
    assert re.search(
        r"event\s+TreasuryTransferred\s*\(\s*address\s+indexed\s+previousTreasury\s*,"
        r"\s*address\s+indexed\s+newTreasury\s*\)",
        payment_gate_src,
    )


# -----------------------------------------------------------------------------
# Public ABI preservation. Removing or renaming any of these is a breaking
# change for the deploy script + the off-chain x402 middleware. New functions
# (`acceptOperator`, `acceptTreasury`) and new storage (`pendingOperator`,
# `pendingTreasury`) are additive and safe.
# -----------------------------------------------------------------------------


SIGNAL_VERIFIER_PRESERVED_SIGNATURES = (
    "function publishSignal(",
    "function getSignal(uint256 id) external view returns (Signal memory)",
    "function getLatestSignals(uint256 count) external view returns (Signal[] memory)",
    "function transferOperator(address newOperator) external onlyOperator",
    "mapping(uint256 => Signal) public signals;",
    "uint256 public signalCount;",
    "address public operator;",
    "event SignalPublished(uint256 indexed id, string symbol, uint8 direction, uint16 confidence);",
    "event SignalVerified(uint256 indexed id, bytes32 proofHash);",
)


PAYMENT_GATE_PRESERVED_SIGNATURES = (
    "function payPerSignal() external payable",
    "function subscribe() external payable",
    "function consumeCredit(address user) external onlyTreasury",
    "function hasAccess(address user) external view returns (bool)",
    "function isSubscribed(address user) external view returns (bool)",
    "function setPricePerSignal(uint256 price) external onlyTreasury",
    "function setMonthlySubscription(uint256 price) external onlyTreasury",
    "function withdraw() external onlyTreasury",
    "function transferTreasury(address newTreasury) external onlyTreasury",
    "address public treasury;",
    "mapping(address => uint256) public credits;",
    "mapping(address => uint256) public subscriptionExpiry;",
    "uint256 public pricePerSignal",
    "uint256 public monthlySubscription",
    "event PaymentReceived(address indexed from, uint256 amount, string service);",
    "event SubscriptionActivated(address indexed subscriber, uint256 expiry);",
    "event CreditsConsumed(address indexed user, uint256 remaining);",
)


@pytest.mark.parametrize("signature", SIGNAL_VERIFIER_PRESERVED_SIGNATURES)
def test_signal_verifier_abi_preserved(signal_verifier_src: str, signature: str) -> None:
    assert signature in signal_verifier_src, f"ABI surface vanished: {signature!r}"


@pytest.mark.parametrize("signature", PAYMENT_GATE_PRESERVED_SIGNATURES)
def test_payment_gate_abi_preserved(payment_gate_src: str, signature: str) -> None:
    assert signature in payment_gate_src, f"ABI surface vanished: {signature!r}"


# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------


def _extract_function(src: str, name: str) -> str:
    """Return the body of `function <name>(...)` up through its closing brace.

    Naive brace-balanced parser. Solidity functions don't nest in this codebase
    (no inline structs / lambdas), so depth-1 tracking is sufficient.
    """
    pattern = re.compile(rf"function\s+{re.escape(name)}\b")
    m = pattern.search(src)
    assert m, f"function not found: {name}"
    # Walk forward to the first `{`, then track depth.
    i = src.index("{", m.end())
    depth = 1
    j = i + 1
    while j < len(src) and depth > 0:
        if src[j] == "{":
            depth += 1
        elif src[j] == "}":
            depth -= 1
        j += 1
    assert depth == 0, f"unbalanced braces in {name}"
    return src[m.start() : j]
