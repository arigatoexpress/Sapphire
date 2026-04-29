"""Unit tests for Hyperliquid EIP-712 L1 action signing.

Mirrors the canonical implementation in
``hyperliquid-python-sdk/hyperliquid/utils/signing.py``. Tests run without
network — round-trip recovery proves the signature scheme is structurally
correct. Final verification still requires a testnet trade
(``scripts/ops/verify_hyperliquid_signing.py``) before flipping
``HyperliquidLivePolicy.signing_verified=True`` in code.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from eth_account import Account

ROOT = Path(__file__).resolve().parents[2]
SERVICE_SRC = ROOT / "services" / "hyperliquid" / "src"
for path in (ROOT, SERVICE_SRC):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from hyperliquid_bot.signing import (  # noqa: E402
    L1_DOMAIN,
    action_hash,
    construct_phantom_agent,
    float_to_wire,
    recover_l1_signer,
    sign_l1_action,
)

# Deterministic test wallet (NOT a real account — never funded).
TEST_PRIVKEY = "0x" + "11" * 32
TEST_WALLET = Account.from_key(TEST_PRIVKEY)


def _order_action() -> dict:
    return {
        "type": "order",
        "orders": [
            {
                "a": 0,
                "b": True,
                "p": "50000",
                "s": "0.0001",
                "r": False,
                "t": {"limit": {"tif": "Ioc"}},
            }
        ],
        "grouping": "na",
    }


# ---------------------------------------------------------------------------
# float_to_wire
# ---------------------------------------------------------------------------


def test_float_to_wire_strips_trailing_zeros() -> None:
    assert float_to_wire(50000.0) == "50000"
    assert float_to_wire(0.5) == "0.5"
    assert float_to_wire(0.00010000) == "0.0001"


def test_float_to_wire_handles_zero() -> None:
    assert float_to_wire(0.0) == "0"


def test_float_to_wire_rejects_excess_precision() -> None:
    with pytest.raises(ValueError, match="rounding"):
        float_to_wire(0.1234567890123)


def test_float_to_wire_accepts_eight_decimals() -> None:
    assert float_to_wire(0.12345678) == "0.12345678"


# ---------------------------------------------------------------------------
# action_hash determinism + sensitivity
# ---------------------------------------------------------------------------


def test_action_hash_is_deterministic() -> None:
    h1 = action_hash(_order_action(), None, 1700000000000, None)
    h2 = action_hash(_order_action(), None, 1700000000000, None)

    assert h1 == h2
    assert len(h1) == 32


def test_action_hash_differs_with_nonce() -> None:
    h1 = action_hash(_order_action(), None, 1700000000000, None)
    h2 = action_hash(_order_action(), None, 1700000000001, None)

    assert h1 != h2


def test_action_hash_differs_with_vault() -> None:
    h_no_vault = action_hash(_order_action(), None, 1, None)
    h_with_vault = action_hash(
        _order_action(), "0x1111111111111111111111111111111111111111", 1, None
    )

    assert h_no_vault != h_with_vault


def test_action_hash_differs_with_expires_after() -> None:
    h_no_exp = action_hash(_order_action(), None, 1, None)
    h_with_exp = action_hash(_order_action(), None, 1, 1700000000000)

    assert h_no_exp != h_with_exp


def test_action_hash_differs_with_action_payload() -> None:
    altered = _order_action()
    altered["orders"][0]["b"] = False  # flip buy → sell

    h_buy = action_hash(_order_action(), None, 1, None)
    h_sell = action_hash(altered, None, 1, None)

    assert h_buy != h_sell


# ---------------------------------------------------------------------------
# Phantom agent + domain
# ---------------------------------------------------------------------------


def test_phantom_agent_source_is_a_for_mainnet() -> None:
    agent = construct_phantom_agent(b"\x00" * 32, is_mainnet=True)

    assert agent["source"] == "a"


def test_phantom_agent_source_is_b_for_testnet() -> None:
    agent = construct_phantom_agent(b"\x00" * 32, is_mainnet=False)

    assert agent["source"] == "b"


def test_l1_domain_matches_sdk_constants() -> None:
    assert L1_DOMAIN["name"] == "Exchange"
    assert L1_DOMAIN["version"] == "1"
    assert L1_DOMAIN["chainId"] == 1337
    assert L1_DOMAIN["verifyingContract"] == "0x" + "0" * 40


# ---------------------------------------------------------------------------
# sign_l1_action — round-trip recovery
# ---------------------------------------------------------------------------


def test_sign_returns_r_s_v_components() -> None:
    sig = sign_l1_action(
        TEST_WALLET, _order_action(), nonce=1700000000000, is_mainnet=False
    )

    assert set(sig) == {"r", "s", "v"}
    assert sig["r"].startswith("0x")
    assert sig["s"].startswith("0x")
    assert sig["v"] in (27, 28)


def test_recover_returns_signer_address() -> None:
    nonce = 1700000000000
    sig = sign_l1_action(TEST_WALLET, _order_action(), nonce=nonce, is_mainnet=False)

    recovered = recover_l1_signer(
        _order_action(), sig, nonce=nonce, is_mainnet=False
    )

    assert recovered.lower() == TEST_WALLET.address.lower()


def test_mainnet_and_testnet_produce_different_signatures() -> None:
    nonce = 42
    main_sig = sign_l1_action(TEST_WALLET, _order_action(), nonce=nonce, is_mainnet=True)
    test_sig = sign_l1_action(
        TEST_WALLET, _order_action(), nonce=nonce, is_mainnet=False
    )

    assert main_sig != test_sig


def test_recovery_with_wrong_network_fails_to_match() -> None:
    """A testnet signature recovered as mainnet must NOT yield the right address."""
    nonce = 99
    sig = sign_l1_action(TEST_WALLET, _order_action(), nonce=nonce, is_mainnet=False)

    recovered_wrong_net = recover_l1_signer(
        _order_action(), sig, nonce=nonce, is_mainnet=True
    )

    assert recovered_wrong_net.lower() != TEST_WALLET.address.lower()


def test_signing_is_deterministic_for_same_inputs() -> None:
    nonce = 1234567890
    sig1 = sign_l1_action(TEST_WALLET, _order_action(), nonce=nonce, is_mainnet=True)
    sig2 = sign_l1_action(TEST_WALLET, _order_action(), nonce=nonce, is_mainnet=True)

    assert sig1 == sig2


def test_vault_address_threading_through_to_signature() -> None:
    """A signature with a vault must round-trip through the same vault."""
    nonce = 100
    vault = "0x" + "ab" * 20
    sig = sign_l1_action(
        TEST_WALLET,
        _order_action(),
        vault_address=vault,
        nonce=nonce,
        is_mainnet=False,
    )

    recovered = recover_l1_signer(
        _order_action(),
        sig,
        vault_address=vault,
        nonce=nonce,
        is_mainnet=False,
    )

    assert recovered.lower() == TEST_WALLET.address.lower()
