"""Unit tests for lib.trading.solana_wallet.

Network-bound paths (Jupiter quote API) are skipped — tested via CLI smoke run.
Here we target the keypair/ledger/base58 core.
"""

from __future__ import annotations

import importlib
import os
import sys
import types
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Cryptography is a top-level dep — skip entire file if unavailable
cryptography = pytest.importorskip("cryptography")


@pytest.fixture
def wallet_mod(tmp_path, monkeypatch):
    """Load solana_wallet with all on-disk paths redirected into tmp_path."""
    from lib.trading import solana_wallet as sw

    importlib.reload(sw)
    monkeypatch.setattr(sw, "SAPPHIRE_DIR", tmp_path / ".sapphire")
    monkeypatch.setattr(sw, "WALLET_PATH", tmp_path / ".sapphire" / "wallet.enc")
    monkeypatch.setattr(sw, "KEY_PATH", tmp_path / ".sapphire" / "wallet.key")
    monkeypatch.setattr(sw, "PROPOSALS_LOG", tmp_path / "data" / "proposals.jsonl")
    monkeypatch.setattr(sw, "LEDGER_PATH", tmp_path / "data" / "ledger.json")
    (tmp_path / ".sapphire").mkdir(parents=True, exist_ok=True)
    (tmp_path / "data").mkdir(parents=True, exist_ok=True)
    return sw


# ---------------------------------------------------------------------------
# Base58 encoder
# ---------------------------------------------------------------------------


def test_b58encode_known_values():
    from lib.trading.solana_wallet import _b58encode

    # "Hello, World!" → Base58-encoded known value
    assert _b58encode(b"\x00") == "1"
    assert _b58encode(b"\x00\x00\x00") == "111"
    # "abc" in hex = 616263 → Base58 should produce a non-empty string
    out = _b58encode(b"abc")
    assert len(out) > 0
    # Every char in alphabet
    alphabet = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
    assert all(c in alphabet for c in out)


def test_b58encode_preserves_leading_zeros():
    from lib.trading.solana_wallet import _b58encode

    assert _b58encode(b"\x00\x01").startswith("1")
    assert _b58encode(b"\x00\x00\x01").startswith("11")


def test_b58encode_nonempty_output():
    from lib.trading.solana_wallet import _b58encode

    out = _b58encode(b"\x01" * 32)
    assert len(out) > 10


# ---------------------------------------------------------------------------
# Wallet init/load round-trip
# ---------------------------------------------------------------------------


def test_init_creates_keypair_and_files(wallet_mod):
    w = wallet_mod.SolanaWallet()
    info = w.init_wallet()
    assert info.pubkey_base58
    assert len(info.pubkey_base58) >= 30
    assert Path(wallet_mod.WALLET_PATH).exists()
    assert Path(wallet_mod.KEY_PATH).exists()
    # Files are mode 0600
    wallet_mode = os.stat(wallet_mod.WALLET_PATH).st_mode & 0o777
    key_mode = os.stat(wallet_mod.KEY_PATH).st_mode & 0o777
    if sys.platform != "win32":
        assert wallet_mode == 0o600
    assert key_mode == 0o600


def test_init_refuses_overwrite_by_default(wallet_mod):
    w = wallet_mod.SolanaWallet()
    w.init_wallet()
    with pytest.raises(RuntimeError, match="already exists"):
        w.init_wallet()


def test_init_with_overwrite_regenerates(wallet_mod):
    w = wallet_mod.SolanaWallet()
    first = w.init_wallet()
    second = w.init_wallet(overwrite=True)
    assert first.pubkey_base58 != second.pubkey_base58


def test_load_roundtrips_keypair(wallet_mod):
    w1 = wallet_mod.SolanaWallet()
    info1 = w1.init_wallet()
    # Fresh instance, load from disk
    w2 = wallet_mod.SolanaWallet()
    info2 = w2.load()
    assert info1.pubkey_base58 == info2.pubkey_base58
    assert w2.pubkey() == info1.pubkey_base58


def test_load_without_wallet_raises(wallet_mod):
    w = wallet_mod.SolanaWallet()
    with pytest.raises(RuntimeError, match="no wallet"):
        w.load()


# ---------------------------------------------------------------------------
# Paper ledger
# ---------------------------------------------------------------------------


def test_init_seeds_paper_ledger(wallet_mod):
    w = wallet_mod.SolanaWallet()
    w.init_wallet()
    bal = w.balance()
    assert bal["SOL"] == wallet_mod.PAPER_STARTING_SOL
    assert bal["USDC"] == wallet_mod.PAPER_STARTING_USDC


def test_balance_without_ledger_returns_defaults(wallet_mod):
    w = wallet_mod.SolanaWallet()
    # No init — ledger doesn't exist yet
    bal = w.balance()
    assert bal["SOL"] == wallet_mod.PAPER_STARTING_SOL
    assert bal["USDC"] == wallet_mod.PAPER_STARTING_USDC


def test_simulate_swap_updates_ledger(wallet_mod):
    from lib.trading.solana_wallet import Proposal

    w = wallet_mod.SolanaWallet()
    w.init_wallet()
    before = w.balance()
    prop = Proposal(
        id="prop-test",
        ts="2026-04-18T00:00:00+00:00",
        input_token="SOL",
        output_token="USDC",
        input_amount=1.0,
        quoted_output=100.0,
        quote_price=100.0,
        status="APPROVED",
    )
    w._simulate_swap(prop)
    after = w.balance()
    assert after["SOL"] == pytest.approx(before["SOL"] - 1.0)
    assert after["USDC"] == pytest.approx(before["USDC"] + 100.0)


def test_corrupt_ledger_falls_back_to_defaults(wallet_mod):
    wallet_mod.LEDGER_PATH.write_text("{{{corrupt")
    w = wallet_mod.SolanaWallet()
    bal = w.balance()
    # Falls back rather than crashing
    assert bal["SOL"] == wallet_mod.PAPER_STARTING_SOL


# ---------------------------------------------------------------------------
# Mint address presence
# ---------------------------------------------------------------------------


def test_mints_dict_has_core_tokens(wallet_mod):
    assert set(wallet_mod.MINTS.keys()) >= {"SOL", "USDC", "USDT", "BONK", "JUP"}
    assert all(isinstance(v, str) and len(v) > 30 for v in wallet_mod.MINTS.values())


# ---------------------------------------------------------------------------
# Quote with unknown token is rejected
# ---------------------------------------------------------------------------


def test_quote_unknown_token_returns_none(wallet_mod):
    w = wallet_mod.SolanaWallet()
    # No network call made because mint lookup fails first
    assert w.quote("NOTATOKEN", "USDC", 1.0) is None
    assert w.quote("SOL", "ALSONOTATOKEN", 1.0) is None


# ---------------------------------------------------------------------------
# Confirmation firewall integration
# ---------------------------------------------------------------------------


class _RecordingFirewall:
    def __init__(self, approved=True, error: Exception | None = None):
        self.approved = approved
        self.error = error
        self.calls = []

    def request_confirmation(self, **kwargs):
        self.calls.append(kwargs)
        if self.error:
            raise self.error
        return self.approved


def _proposal(**overrides):
    from lib.trading.solana_wallet import Proposal

    data = {
        "id": "prop-test",
        "ts": "2026-04-25T00:00:00+00:00",
        "input_token": "SOL",
        "output_token": "USDC",
        "input_amount": 1.0,
        "quoted_output": 123.45,
        "quote_price": 123.45,
        "status": "PENDING",
    }
    data.update(overrides)
    return Proposal(**data)


def _install_fake_event_bus(monkeypatch):
    published = []

    class FakeBus:
        def publish(self, event_type, payload, source=None):
            published.append((event_type, payload, source))

    monkeypatch.setitem(
        sys.modules,
        "lib.core.event_bus",
        types.SimpleNamespace(get_bus=lambda: FakeBus()),
    )
    return published


def test_approval_amount_usd_prefers_stablecoin_side(wallet_mod):
    w = wallet_mod.SolanaWallet()

    assert w._approval_amount_usd(_proposal(output_token="USDC")) == pytest.approx(123.45)
    assert w._approval_amount_usd(
        _proposal(input_token="USDT", output_token="SOL", input_amount=50.0)
    ) == pytest.approx(50.0)
    assert w._approval_amount_usd(
        _proposal(input_token="SOL", output_token="JUP", quoted_output=10.0)
    ) == pytest.approx(0.0)


def test_request_approval_uses_confirmation_firewall(wallet_mod):
    firewall = _RecordingFirewall(approved=True)
    w = wallet_mod.SolanaWallet(confirmation_firewall=firewall)
    prop = _proposal()

    assert w._request_approval(prop) is True

    assert prop.audit[-1] == "confirmation_firewall_approved"
    call = firewall.calls[0]
    assert call["action"] == "paper swap SOL->USDC"
    assert call["risk"].value == "financial"
    assert call["details"] == "Mode: paper simulation. 1.0 SOL for ~123.45 USDC"
    assert call["amount"] == pytest.approx(123.45)


def test_request_approval_fails_closed_on_firewall_error(wallet_mod):
    firewall = _RecordingFirewall(error=RuntimeError("firewall offline"))
    w = wallet_mod.SolanaWallet(confirmation_firewall=firewall)
    prop = _proposal()

    assert w._request_approval(prop) is False

    assert prop.audit[-1] == "confirmation_firewall_error"


def test_propose_swap_denial_does_not_execute_paper_trade(wallet_mod, monkeypatch):
    _install_fake_event_bus(monkeypatch)
    firewall = _RecordingFirewall(approved=False)
    w = wallet_mod.SolanaWallet(confirmation_firewall=firewall)
    w.init_wallet()
    monkeypatch.setattr(
        w,
        "quote",
        lambda *_args, **_kwargs: {
            "out_amount": 100.0,
            "price": 100.0,
            "route_plan_hops": 1,
        },
    )
    before = w.balance()

    prop = w.propose_swap("SOL", "USDC", 1.0, reason="unit test")

    assert prop.status == "DENIED"
    assert prop.approver is None
    assert "confirmation_firewall_denied" in prop.audit
    assert "approval_not_granted" in prop.audit
    assert w.balance() == before


def test_propose_swap_approval_executes_paper_trade(wallet_mod, monkeypatch):
    published = _install_fake_event_bus(monkeypatch)
    firewall = _RecordingFirewall(approved=True)
    w = wallet_mod.SolanaWallet(confirmation_firewall=firewall)
    w.init_wallet()
    monkeypatch.setattr(
        w,
        "quote",
        lambda *_args, **_kwargs: {
            "out_amount": 100.0,
            "price": 100.0,
            "route_plan_hops": 1,
        },
    )

    prop = w.propose_swap("SOL", "USDC", 1.0, reason="unit test")

    assert prop.status == "EXECUTED_PAPER"
    assert prop.approver == "confirmation_firewall"
    assert "confirmation_firewall_approved" in prop.audit
    assert "paper_swap_simulated" in prop.audit
    assert w.balance()["SOL"] == pytest.approx(wallet_mod.PAPER_STARTING_SOL - 1.0)
    assert w.balance()["USDC"] == pytest.approx(wallet_mod.PAPER_STARTING_USDC + 100.0)
    assert published[0][0] == "trade.proposed"
