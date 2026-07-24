"""Tests for the MegaETH executor scaffold (no real network).

These tests exercise every safety gate in
``plugins/claw-sapphire/tools/internal/megaeth_executor.py``:

- Killswitch file present -> refuses send.
- Per-order cap exceeded -> refuses.
- Daily loss cap exceeded -> refuses (and persists state).
- ``signing_verified=False`` + mainnet ``chain_id`` -> refuses.
- ``signing_verified=False`` + testnet ``chain_id`` -> permitted, dry-run by
  default.
- Missing ``SAPPHIRE_MEGAETH_TESTNET_KEY`` -> refuses with clear error.

All eth_account / RPC interactions are mocked.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

# Make plugins/claw-sapphire/tools/internal importable as
# ``megaeth_executor`` without requiring the package shim layer.
ROOT = Path(__file__).resolve().parents[2]
INTERNAL = ROOT / "plugins" / "claw-sapphire" / "tools" / "internal"
if str(INTERNAL) not in sys.path:
    sys.path.insert(0, str(INTERNAL))

import megaeth_executor as me  # noqa: E402

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def isolated_paths(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Redirect every filesystem path the executor touches into tmp_path."""
    killswitch = tmp_path / "megaeth_trading_pause"
    trade_log = tmp_path / "trades.jsonl"
    daily_pnl = tmp_path / "daily_pnl.json"

    # Patch the dataclass defaults via a fresh policy instance per test.
    monkeypatch.setattr(me, "KILLSWITCH_PATH_DEFAULT", str(killswitch))
    monkeypatch.setattr(me, "TRADE_LOG_PATH_DEFAULT", str(trade_log))
    monkeypatch.setattr(me, "DAILY_PNL_PATH_DEFAULT", str(daily_pnl))
    return tmp_path


@pytest.fixture
def policy(isolated_paths: Path) -> me.MegaETHLivePolicy:
    return me.MegaETHLivePolicy(
        max_order_notional_usd=5.0,
        daily_realized_loss_cap_usd=25.0,
        killswitch_path=str(isolated_paths / "megaeth_trading_pause"),
        trade_log_path=str(isolated_paths / "trades.jsonl"),
        daily_pnl_path=str(isolated_paths / "daily_pnl.json"),
        signing_verified=False,
    )


@pytest.fixture
def good_tx() -> dict:
    return {
        "to": "0x" + "ab" * 20,
        "value": 0,
        "gas": 21000,
        "maxFeePerGas": 1_000_000_000,
        "maxPriorityFeePerGas": 100_000_000,
        "nonce": 0,
        "chainId": me.TESTNET_CHAIN_ID,
        "notional_usd": 1.0,
    }


@pytest.fixture
def fake_eth_account(monkeypatch: pytest.MonkeyPatch):
    """Replace ``eth_account.Account.sign_transaction`` with a stub.

    Returns the namespace used so individual tests can assert on it.
    """
    fake_signed = SimpleNamespace(raw_transaction=b"\xde\xad\xbe\xef")

    class FakeAccount:
        @staticmethod
        def sign_transaction(tx, key):
            return fake_signed

    fake_module = SimpleNamespace(Account=FakeAccount)
    monkeypatch.setitem(sys.modules, "eth_account", fake_module)
    return fake_signed


# ---------------------------------------------------------------------------
# Constructor tests
# ---------------------------------------------------------------------------


def test_constructor_refuses_unknown_chain_id(policy):
    with pytest.raises(ValueError, match="refusing unknown chain_id"):
        me.MegaETHExecutor(rpc_url="http://x", chain_id=1, policy=policy)


def test_constructor_accepts_testnet_chain_id(policy):
    ex = me.MegaETHExecutor(
        rpc_url="http://testnet.megaeth", chain_id=me.TESTNET_CHAIN_ID, policy=policy
    )
    assert ex.chain_id == me.TESTNET_CHAIN_ID
    assert ex.policy.signing_verified is False


def test_constructor_refuses_mainnet_unless_signing_verified(
    monkeypatch: pytest.MonkeyPatch, policy: me.MegaETHLivePolicy
):
    """Even a hardcoded mainnet chain_id is refused while signing_verified=False."""
    monkeypatch.setattr(me, "MAINNET_CHAIN_ID", 99999)
    with pytest.raises(NotImplementedError, match="MegaETH mainnet path is locked"):
        me.MegaETHExecutor(rpc_url="http://x", chain_id=99999, policy=policy)


def test_constructor_permits_mainnet_when_signing_verified(
    monkeypatch: pytest.MonkeyPatch, isolated_paths: Path
):
    monkeypatch.setattr(me, "MAINNET_CHAIN_ID", 99999)
    verified_policy = me.MegaETHLivePolicy(
        killswitch_path=str(isolated_paths / "megaeth_trading_pause"),
        trade_log_path=str(isolated_paths / "trades.jsonl"),
        daily_pnl_path=str(isolated_paths / "daily_pnl.json"),
        signing_verified=True,
    )
    ex = me.MegaETHExecutor(rpc_url="http://x", chain_id=99999, policy=verified_policy)
    assert ex.chain_id == 99999


def test_constructor_per_order_cap_override(policy: me.MegaETHLivePolicy):
    ex = me.MegaETHExecutor(
        rpc_url="http://x",
        chain_id=me.TESTNET_CHAIN_ID,
        policy=policy,
        per_order_cap_usd=2.5,
    )
    assert ex.policy.max_order_notional_usd == pytest.approx(2.5)


# ---------------------------------------------------------------------------
# send_transaction safety gates
# ---------------------------------------------------------------------------


def test_killswitch_present_refuses_send(
    policy, good_tx, fake_eth_account, monkeypatch: pytest.MonkeyPatch
):
    Path(policy.killswitch_path).touch()
    monkeypatch.setenv(me.ENV_KEY_TESTNET, "0x" + "11" * 32)
    ex = me.MegaETHExecutor(rpc_url="http://x", chain_id=me.TESTNET_CHAIN_ID, policy=policy)
    result = ex.send_transaction(good_tx)
    assert result.status == "blocked"
    assert "killswitch_active" in result.blockers


def test_per_order_cap_exceeded_refuses(
    policy, good_tx, fake_eth_account, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setenv(me.ENV_KEY_TESTNET, "0x" + "11" * 32)
    ex = me.MegaETHExecutor(rpc_url="http://x", chain_id=me.TESTNET_CHAIN_ID, policy=policy)
    big_tx = dict(good_tx, notional_usd=999.0)
    result = ex.send_transaction(big_tx)
    assert result.status == "blocked"
    assert "per_order_cap_exceeded" in result.blockers


def test_missing_notional_refuses(
    policy, good_tx, fake_eth_account, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setenv(me.ENV_KEY_TESTNET, "0x" + "11" * 32)
    ex = me.MegaETHExecutor(rpc_url="http://x", chain_id=me.TESTNET_CHAIN_ID, policy=policy)
    bad_tx = dict(good_tx)
    bad_tx.pop("notional_usd")
    result = ex.send_transaction(bad_tx)
    assert result.status == "blocked"
    assert "missing_or_invalid_notional_usd" in result.blockers


def test_daily_loss_cap_persists_and_blocks(
    policy: me.MegaETHLivePolicy,
    good_tx,
    fake_eth_account,
    monkeypatch: pytest.MonkeyPatch,
):
    """Realised loss recorded in one process must block the next call."""
    # Pre-populate the daily PnL ledger past the cap.
    me.record_realized_pnl(policy, -50.0)
    # Sanity: the persisted file is readable and has today's bucket.
    body = json.loads(Path(policy.daily_pnl_path).read_text(encoding="utf-8"))
    assert any(v.get("realized_loss_usd", 0) >= 25 for v in body.values())

    monkeypatch.setenv(me.ENV_KEY_TESTNET, "0x" + "11" * 32)
    ex = me.MegaETHExecutor(rpc_url="http://x", chain_id=me.TESTNET_CHAIN_ID, policy=policy)
    result = ex.send_transaction(good_tx)
    assert result.status == "blocked"
    assert "daily_loss_cap_reached" in result.blockers


def test_signing_verified_false_plus_mainnet_chain_blocks(
    monkeypatch: pytest.MonkeyPatch, isolated_paths: Path, good_tx, fake_eth_account
):
    """Belt-and-suspenders: even if construction somehow let mainnet through,
    send_transaction itself re-checks the gate."""
    monkeypatch.setattr(me, "MAINNET_CHAIN_ID", 99999)
    # Build with verified=True so the constructor permits it...
    verified_policy = me.MegaETHLivePolicy(
        killswitch_path=str(isolated_paths / "megaeth_trading_pause"),
        trade_log_path=str(isolated_paths / "trades.jsonl"),
        daily_pnl_path=str(isolated_paths / "daily_pnl.json"),
        signing_verified=True,
    )
    ex = me.MegaETHExecutor(rpc_url="http://x", chain_id=99999, policy=verified_policy)
    # ...then flip the policy to False to simulate tampering and confirm the
    # send-time check still catches it.
    object.__setattr__(
        ex,
        "policy",
        me.MegaETHLivePolicy(
            killswitch_path=str(isolated_paths / "megaeth_trading_pause"),
            trade_log_path=str(isolated_paths / "trades.jsonl"),
            daily_pnl_path=str(isolated_paths / "daily_pnl.json"),
            signing_verified=False,
        ),
    )
    monkeypatch.setenv(me.ENV_KEY_TESTNET, "0x" + "11" * 32)
    bad_tx = dict(good_tx, chainId=99999)
    result = ex.send_transaction(bad_tx)
    assert result.status == "blocked"
    assert "mainnet_locked_signing_not_verified" in result.blockers


def test_signing_verified_false_plus_testnet_dry_run_permitted(
    policy, good_tx, fake_eth_account, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setenv(me.ENV_KEY_TESTNET, "0x" + "11" * 32)
    monkeypatch.delenv(me.ENV_DRY_RUN, raising=False)  # default => dry run
    ex = me.MegaETHExecutor(rpc_url="http://x", chain_id=me.TESTNET_CHAIN_ID, policy=policy)
    result = ex.send_transaction(good_tx)
    assert result.status == "signed_dry_run"
    assert result.signed_tx_hex and result.signed_tx_hex.startswith("0x")


def test_missing_env_key_refuses_with_clear_error(
    policy, good_tx, fake_eth_account, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.delenv(me.ENV_KEY_TESTNET, raising=False)
    ex = me.MegaETHExecutor(rpc_url="http://x", chain_id=me.TESTNET_CHAIN_ID, policy=policy)
    result = ex.send_transaction(good_tx)
    assert result.status == "error"
    assert "missing_signing_key_env" in result.blockers
    assert me.ENV_KEY_TESTNET in (result.reason or "")


def test_tx_chain_id_mismatch_blocks(
    policy, good_tx, fake_eth_account, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setenv(me.ENV_KEY_TESTNET, "0x" + "11" * 32)
    ex = me.MegaETHExecutor(rpc_url="http://x", chain_id=me.TESTNET_CHAIN_ID, policy=policy)
    tx = dict(good_tx, chainId=999_999)  # disagrees with executor's binding
    result = ex.send_transaction(tx)
    assert result.status == "blocked"
    assert "tx_chain_id_mismatch" in result.blockers


def test_signing_failure_returns_error(policy, good_tx, monkeypatch: pytest.MonkeyPatch):
    """If eth_account itself raises, the executor must surface 'error', not crash."""
    monkeypatch.setenv(me.ENV_KEY_TESTNET, "0x" + "11" * 32)

    class BoomAccount:
        @staticmethod
        def sign_transaction(tx, key):
            raise RuntimeError("boom")

    monkeypatch.setitem(sys.modules, "eth_account", SimpleNamespace(Account=BoomAccount))
    ex = me.MegaETHExecutor(rpc_url="http://x", chain_id=me.TESTNET_CHAIN_ID, policy=policy)
    result = ex.send_transaction(good_tx)
    assert result.status == "error"
    assert "signing_failed" in (result.reason or "")


# ---------------------------------------------------------------------------
# Trade log + ledger persistence
# ---------------------------------------------------------------------------


def test_trade_log_appended_on_block(
    policy, good_tx, fake_eth_account, monkeypatch: pytest.MonkeyPatch
):
    Path(policy.killswitch_path).touch()
    monkeypatch.setenv(me.ENV_KEY_TESTNET, "0x" + "11" * 32)
    ex = me.MegaETHExecutor(rpc_url="http://x", chain_id=me.TESTNET_CHAIN_ID, policy=policy)
    ex.send_transaction(good_tx)
    log_path = Path(policy.trade_log_path)
    assert log_path.exists()
    rows = [json.loads(line) for line in log_path.read_text(encoding="utf-8").splitlines() if line]
    assert rows[-1]["status"] == "blocked"
    assert "killswitch_active" in rows[-1]["blockers"]


def test_record_realized_pnl_persists_loss_only(policy: me.MegaETHLivePolicy):
    me.record_realized_pnl(policy, -3.5)
    me.record_realized_pnl(policy, +2.0)  # gain shouldn't increase loss bucket
    body = json.loads(Path(policy.daily_pnl_path).read_text(encoding="utf-8"))
    today_entry = next(iter(body.values()))
    assert today_entry["realized_loss_usd"] == pytest.approx(3.5)
    assert today_entry["trade_count"] == 2


# ---------------------------------------------------------------------------
# Module hygiene — these are scaffold guards, not user-facing behavior.
# ---------------------------------------------------------------------------


def test_mainnet_chain_id_is_pinned():
    """MAINNET_CHAIN_ID is pinned to the canonical MegaETH mainnet value.

    Pinning the constant does NOT activate mainnet — that requires
    flipping ``signing_verified=True`` in source. The original placeholder
    contract (``MAINNET_CHAIN_ID is None``) was replaced with the real
    chain ID once MegaETH published it; the audit-loud-on-flip semantic
    is preserved by the ``signing_verified`` field, not by the constant.
    """
    assert me.MAINNET_CHAIN_ID == 4326, (
        "MAINNET_CHAIN_ID drifted from the canonical value 4326 (0x10e6). "
        "If MegaETH renumbered the chain, audit signing_verified before changing."
    )


def test_signing_verified_default_is_false():
    """Default policy must remain fail-closed.

    This is the single audit-loud-on-flip gate that allows mainnet
    sends; flipping it to True must be a code change reviewed against
    a clean testnet trade.
    """
    assert me.MegaETHLivePolicy().signing_verified is False


def test_no_broadcast_path_in_module():
    """Scaffold contract: there is no broadcast RPC call.

    ``send_transaction`` only ever returns ``signed_dry_run`` or
    ``blocked``/``error`` — never a ``broadcast`` status. This test
    enforces that contract by source-grepping for the JSON-RPC method
    names that would actually broadcast a tx; if a future refactor adds
    one of those calls, the test fails and the audit-loud contract
    requires the operator to revisit signing_verified before continuing.
    """
    import inspect

    src = inspect.getsource(me)
    forbidden = ("eth_sendRawTransaction", "eth_sendTransaction")
    for token in forbidden:
        assert token not in src, (
            f"module source mentions '{token}' — the scaffold must not "
            "include a broadcast path; revisit signing_verified before adding"
        )
    # ``send_transaction`` never returns a 'broadcast' status — the only
    # statuses the scaffold can emit are listed in the result-type docstring.
    sig_status_values = {"signed_dry_run", "blocked", "error"}
    # Spot-check: the SendResult status field's permitted values are exactly
    # those (sanity check for the contract).
    assert all(v in src for v in sig_status_values)


def test_testnet_chain_id_is_canonical():
    """TESTNET_CHAIN_ID is the canonical carrot testnet ID 6343 (0x18c7).

    A previous draft of this scaffold used 6342 — that was a typo. The
    correct value is 6343 per docs.megaeth.com.
    """
    assert me.TESTNET_CHAIN_ID == 6343
