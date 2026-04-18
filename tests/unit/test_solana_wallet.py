"""Unit tests for lib.trading.solana_wallet.

Network-bound paths (Jupiter quote API) are skipped — tested via CLI smoke run.
Here we target the keypair/ledger/base58 core.
"""

from __future__ import annotations

import importlib
import os
import sys
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
        id="prop-test", ts="2026-04-18T00:00:00+00:00",
        input_token="SOL", output_token="USDC",
        input_amount=1.0, quoted_output=100.0,
        quote_price=100.0, status="APPROVED",
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
