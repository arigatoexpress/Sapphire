"""Unit tests for the Hyperliquid live-trading executor + risk caps."""

from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[2]
SERVICE_SRC = ROOT / "services" / "hyperliquid" / "src"
for path in (ROOT, SERVICE_SRC):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from hyperliquid_bot.risk import (  # noqa: E402
    ExecutionResult,
    HyperliquidLiveExecutor,
    HyperliquidLivePolicy,
    RiskState,
    evaluate_risk,
    killswitch_active,
    load_private_key,
    record_realized_pnl,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def policy(tmp_path: Path) -> HyperliquidLivePolicy:
    return HyperliquidLivePolicy(
        max_order_notional_usd=5.0,
        max_leverage=3.0,
        max_open_positions=5,
        daily_realized_loss_cap_usd=25.0,
        killswitch_path=str(tmp_path / "pause"),
        trade_log_path=str(tmp_path / "trades.jsonl"),
        daily_pnl_path=str(tmp_path / "daily_pnl.json"),
    )


def _state(
    *,
    open_positions: int = 0,
    daily_loss: float = 0.0,
    killswitch: bool = False,
    enabled: bool = True,
) -> RiskState:
    return RiskState(
        open_positions=open_positions,
        daily_realized_loss_usd=daily_loss,
        killswitch_active=killswitch,
        trading_enabled=enabled,
    )


class FakeClient:
    """Minimal stand-in for HyperliquidClient. Records every call."""

    address = "0xfake"

    def __init__(
        self,
        *,
        positions: list[dict[str, Any]] | None = None,
        mids: dict[str, str] | None = None,
        order_response: dict[str, Any] | None = None,
        raise_on_order: bool = False,
    ) -> None:
        self._positions = positions or []
        self._mids = mids or {"BTC": "60000"}
        self._order_response = order_response or {"status": "ok", "orderId": 7}
        self._raise = raise_on_order
        self.calls: list[tuple[str, tuple, dict]] = []

    async def get_user_state(self) -> dict[str, Any]:
        self.calls.append(("get_user_state", (), {}))
        return {"assetPositions": self._positions}

    async def get_all_mids(self) -> dict[str, str]:
        self.calls.append(("get_all_mids", (), {}))
        return self._mids

    async def market_order(
        self, coin: str, is_buy: bool, sz: float, *, reduce_only: bool = False
    ) -> dict[str, Any]:
        self.calls.append(("market_order", (coin, is_buy, sz), {"reduce_only": reduce_only}))
        if self._raise:
            raise RuntimeError("simulated network failure")
        return self._order_response

    async def close_position(self, coin: str) -> dict[str, Any]:
        self.calls.append(("close_position", (coin,), {}))
        if self._raise:
            raise RuntimeError("simulated network failure")
        return {"status": "closed", "coin": coin}


# ---------------------------------------------------------------------------
# Pure evaluate_risk tests
# ---------------------------------------------------------------------------


def test_evaluate_risk_caps_oversized_order(policy: HyperliquidLivePolicy) -> None:
    verdict = evaluate_risk({"symbol": "BTC", "action": "buy", "size_usd": 50}, _state(), policy)

    assert verdict.allowed
    assert verdict.bounded_notional_usd == 5.0
    assert "notional_capped_to_policy_max" in verdict.reasons


def test_evaluate_risk_caps_oversized_leverage(policy: HyperliquidLivePolicy) -> None:
    verdict = evaluate_risk(
        {"symbol": "BTC", "action": "buy", "size_usd": 5, "leverage": 10},
        _state(),
        policy,
    )

    assert verdict.allowed
    assert verdict.bounded_leverage == 3.0
    assert "leverage_capped_to_policy_max" in verdict.reasons


def test_evaluate_risk_blocks_when_killswitch_active(policy: HyperliquidLivePolicy) -> None:
    verdict = evaluate_risk(
        {"symbol": "BTC", "action": "buy", "size_usd": 5},
        _state(killswitch=True),
        policy,
    )

    assert not verdict.allowed
    assert "killswitch_active" in verdict.blockers


def test_evaluate_risk_blocks_when_trading_disabled(policy: HyperliquidLivePolicy) -> None:
    verdict = evaluate_risk(
        {"symbol": "BTC", "action": "buy", "size_usd": 5},
        _state(enabled=False),
        policy,
    )

    assert not verdict.allowed
    assert "trading_disabled_env_flag" in verdict.blockers


def test_evaluate_risk_blocks_when_daily_loss_cap_reached(
    policy: HyperliquidLivePolicy,
) -> None:
    verdict = evaluate_risk(
        {"symbol": "BTC", "action": "buy", "size_usd": 5},
        _state(daily_loss=25.0),
        policy,
    )

    assert not verdict.allowed
    assert "daily_loss_cap_reached" in verdict.blockers


def test_evaluate_risk_blocks_when_max_positions_reached(
    policy: HyperliquidLivePolicy,
) -> None:
    verdict = evaluate_risk(
        {"symbol": "BTC", "action": "buy", "size_usd": 5},
        _state(open_positions=5),
        policy,
    )

    assert not verdict.allowed
    assert "max_open_positions_reached" in verdict.blockers


def test_evaluate_risk_allows_close_at_position_limit(
    policy: HyperliquidLivePolicy,
) -> None:
    verdict = evaluate_risk(
        {"symbol": "BTC", "action": "close"},
        _state(open_positions=5),
        policy,
    )

    assert verdict.allowed


def test_evaluate_risk_blocks_invalid_size(policy: HyperliquidLivePolicy) -> None:
    verdict = evaluate_risk(
        {"symbol": "BTC", "action": "buy", "size_usd": -1},
        _state(),
        policy,
    )

    assert not verdict.allowed
    assert "missing_or_invalid_size_usd" in verdict.blockers


def test_evaluate_risk_blocks_unknown_action(policy: HyperliquidLivePolicy) -> None:
    verdict = evaluate_risk(
        {"symbol": "BTC", "action": "yolo", "size_usd": 5},
        _state(),
        policy,
    )

    assert not verdict.allowed
    assert "unsupported_action" in verdict.blockers


def test_evaluate_risk_close_uses_policy_max_when_size_missing(
    policy: HyperliquidLivePolicy,
) -> None:
    verdict = evaluate_risk({"symbol": "BTC", "action": "close"}, _state(open_positions=1), policy)

    assert verdict.allowed
    assert verdict.bounded_notional_usd == policy.max_order_notional_usd


# ---------------------------------------------------------------------------
# Killswitch + daily PnL ledger
# ---------------------------------------------------------------------------


def test_killswitch_active_reflects_file_presence(policy: HyperliquidLivePolicy) -> None:
    assert killswitch_active(policy) is False

    Path(policy.killswitch_path).expanduser().write_text("paused")

    assert killswitch_active(policy) is True


def test_record_realized_pnl_accumulates_loss(policy: HyperliquidLivePolicy) -> None:
    record_realized_pnl(policy, -3.0)
    record_realized_pnl(policy, -2.5)
    record_realized_pnl(policy, 1.0)  # gain shouldn't add to loss bucket

    body = json.loads(Path(policy.daily_pnl_path).read_text(encoding="utf-8"))
    today = body[date.today().isoformat()]

    assert today["realized_loss_usd"] == 5.5
    assert today["trade_count"] == 3


# ---------------------------------------------------------------------------
# Key loader
# ---------------------------------------------------------------------------


def test_load_private_key_falls_back_to_env(
    monkeypatch: pytest.MonkeyPatch, policy: HyperliquidLivePolicy
) -> None:
    monkeypatch.setenv("HYPERLIQUID_PRIVATE_KEY", "0xdeadbeef")
    monkeypatch.setattr("hyperliquid_bot.risk._load_from_keychain", lambda _policy: None)

    assert load_private_key(policy) == "0xdeadbeef"


def test_load_private_key_returns_none_when_no_source(
    monkeypatch: pytest.MonkeyPatch, policy: HyperliquidLivePolicy
) -> None:
    monkeypatch.delenv("HYPERLIQUID_PRIVATE_KEY", raising=False)
    monkeypatch.setattr("hyperliquid_bot.risk._load_from_keychain", lambda _policy: None)

    assert load_private_key(policy) is None


# ---------------------------------------------------------------------------
# Executor tests (async — pytest-asyncio auto mode)
# ---------------------------------------------------------------------------


async def test_executor_blocks_oversize_order_without_calling_client(
    policy: HyperliquidLivePolicy,
) -> None:
    client = FakeClient()
    executor = HyperliquidLiveExecutor(client, policy=policy, testnet=True, trading_enabled=True)
    Path(policy.killswitch_path).expanduser().write_text("paused")

    result = await executor.execute_signal({"symbol": "BTC", "action": "buy", "size_usd": 100})

    assert result.status == "blocked"
    assert "killswitch_active" in result.verdict.blockers
    assert all(call[0] == "get_user_state" for call in client.calls)


async def test_executor_dry_runs_when_trading_disabled(
    policy: HyperliquidLivePolicy,
) -> None:
    client = FakeClient()
    executor = HyperliquidLiveExecutor(client, policy=policy, testnet=True, trading_enabled=False)

    result = await executor.execute_signal({"symbol": "BTC", "action": "buy", "size_usd": 5})

    assert result.status == "blocked"
    assert "trading_disabled_env_flag" in result.verdict.blockers


async def test_executor_executes_with_capped_size(
    policy: HyperliquidLivePolicy,
) -> None:
    client = FakeClient(mids={"BTC": "50000"})
    executor = HyperliquidLiveExecutor(client, policy=policy, testnet=True, trading_enabled=True)

    result = await executor.execute_signal({"symbol": "BTC", "action": "buy", "size_usd": 50})

    assert result.status == "executed"
    assert result.verdict.bounded_notional_usd == 5.0
    market_calls = [c for c in client.calls if c[0] == "market_order"]
    assert len(market_calls) == 1
    coin, is_buy, sz = market_calls[0][1]
    assert coin == "BTC"
    assert is_buy is True
    assert sz == pytest.approx(5.0 / 50000)


async def test_executor_records_error_when_client_fails(
    policy: HyperliquidLivePolicy,
) -> None:
    client = FakeClient(raise_on_order=True)
    executor = HyperliquidLiveExecutor(client, policy=policy, testnet=True, trading_enabled=True)

    result = await executor.execute_signal({"symbol": "BTC", "action": "buy", "size_usd": 5})

    assert result.status == "error"
    assert "simulated network failure" in (result.error or "")


async def test_executor_logs_each_result_to_jsonl(
    policy: HyperliquidLivePolicy,
) -> None:
    client = FakeClient(mids={"BTC": "50000"})
    executor = HyperliquidLiveExecutor(client, policy=policy, testnet=True, trading_enabled=True)

    await executor.execute_signal({"symbol": "BTC", "action": "buy", "size_usd": 5})
    await executor.execute_signal({"symbol": "BTC", "action": "yolo", "size_usd": 5})

    lines = Path(policy.trade_log_path).read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    rows = [json.loads(line) for line in lines]
    assert {row["status"] for row in rows} == {"executed", "blocked"}


async def test_executor_treats_zero_size_position_as_closed(
    policy: HyperliquidLivePolicy,
) -> None:
    client = FakeClient(
        positions=[
            {"position": {"coin": "BTC", "szi": "0"}},
            {"position": {"coin": "ETH", "szi": "1.5"}},
        ]
    )
    executor = HyperliquidLiveExecutor(client, policy=policy, testnet=True, trading_enabled=True)

    status = await executor.status()

    assert status["state"]["open_positions"] == 1


def test_executor_refuses_mainnet_until_signing_verified(
    policy: HyperliquidLivePolicy,
) -> None:
    client = FakeClient()
    with pytest.raises(ValueError, match="signing not yet verified"):
        HyperliquidLiveExecutor(client, policy=policy, testnet=False, trading_enabled=True)


def test_executor_allows_mainnet_when_signing_marked_verified(
    tmp_path: Path,
) -> None:
    policy = HyperliquidLivePolicy(
        killswitch_path=str(tmp_path / "pause"),
        trade_log_path=str(tmp_path / "trades.jsonl"),
        daily_pnl_path=str(tmp_path / "daily_pnl.json"),
        signing_verified=True,
    )
    client = FakeClient()

    executor = HyperliquidLiveExecutor(client, policy=policy, testnet=False, trading_enabled=True)

    assert executor.testnet is False


# ---------------------------------------------------------------------------
# Result serialization
# ---------------------------------------------------------------------------


def test_execution_result_serializes_to_dict(policy: HyperliquidLivePolicy) -> None:
    verdict = evaluate_risk({"symbol": "BTC", "action": "buy", "size_usd": 5}, _state(), policy)
    result = ExecutionResult(status="dry_run", signal={"symbol": "BTC"}, verdict=verdict)

    body = result.to_dict()

    assert body["status"] == "dry_run"
    assert body["verdict"]["decision"] == "allow"
    assert "timestamp" in body
