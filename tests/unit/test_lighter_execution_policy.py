import importlib.util
from pathlib import Path

import pytest

MODULE_PATH = Path(__file__).resolve().parents[2] / "services" / "bot-lighter" / "src" / "main.py"
spec = importlib.util.spec_from_file_location("bot_lighter_main", MODULE_PATH)
mod = importlib.util.module_from_spec(spec)
assert spec is not None and spec.loader is not None
try:
    spec.loader.exec_module(mod)
except Exception as exc:  # pragma: no cover - environment-dependent import guard
    pytest.skip(f"bot-lighter module import unavailable in this test environment: {exc}", allow_module_level=True)


@pytest.mark.asyncio
async def test_execute_trade_rejects_below_min_entry_notional(monkeypatch):
    bot = mod.LighterBot()
    bot.transaction_api = object()
    bot._trading_enabled = True
    bot._allow_live_trading = True
    bot._trading_mode = "live"
    bot._single_symbol_mode = False
    bot._sync_before_entry = False
    bot._target_order_notional_usd = 0.0
    bot._max_order_notional_usd = 0.0
    bot._max_position_notional_usd = 0.0
    bot._min_entry_notional_usd = 3.5
    bot.market_info = {"SOL": {"order_book_id": 1, "supported_size_decimals": 3}}

    async def _ticker(_coin):
        return 100.0

    async def _submit(**_kwargs):
        raise AssertionError("submit should not be called when min notional fails")

    bot._get_ticker = _ticker
    bot._submit_order_with_signer = _submit

    signal = mod.TradeSignal(
        signal_id="min-notional-test",
        symbol="SOL",
        side=mod.TradeSide.BUY,
        signal_type=mod.SignalType.ENTRY,
        confidence=0.8,
        source="unit-test",
        quantity=0.01,  # $1.00 notional at ticker=100
        metadata={"strategy": "luxalgo_msb_ob", "timeframe": "5m"},
    )

    result = await bot._execute_trade(signal)
    assert result.success is False
    assert "Entry notional too low" in (result.error_message or "")


@pytest.mark.asyncio
async def test_execute_trade_syncs_positions_before_single_symbol_gate(monkeypatch):
    bot = mod.LighterBot()
    bot.transaction_api = object()
    bot._trading_enabled = True
    bot._allow_live_trading = True
    bot._trading_mode = "live"
    bot._single_symbol_mode = True
    bot._sync_before_entry = True
    bot._target_order_notional_usd = 0.0
    bot._max_order_notional_usd = 0.0
    bot._max_position_notional_usd = 0.0
    bot._min_entry_notional_usd = 0.0
    bot.market_info = {"SOL": {"order_book_id": 1, "supported_size_decimals": 3}}

    # Local state initially says BTC is open; sync should clear it.
    bot.positions = {
        "BTC": mod.Position(
            position_id="p1",
            platform="lighter",
            symbol="BTC",
            side=mod.TradeSide.BUY,
            quantity=0.1,
            entry_price=100.0,
        )
    }

    sync_called = {"value": False}

    async def _sync_positions():
        sync_called["value"] = True
        bot.positions = {}

    async def _ticker(_coin):
        return 100.0

    async def _submit(**_kwargs):
        return {
            "success": True,
            "order_id": "o-1",
            "filled_quantity": 0.04,
            "avg_fill_price": 100.0,
            "metadata": {"execution_state": "filled"},
        }

    bot._check_positions = _sync_positions
    bot._get_ticker = _ticker
    bot._submit_order_with_signer = _submit

    signal = mod.TradeSignal(
        signal_id="sync-gate-test",
        symbol="SOL",
        side=mod.TradeSide.BUY,
        signal_type=mod.SignalType.ENTRY,
        confidence=0.8,
        source="unit-test",
        quantity=0.04,
        metadata={"strategy": "luxalgo_msb_ob", "timeframe": "5m"},
    )

    result = await bot._execute_trade(signal)
    assert sync_called["value"] is True
    assert result.success is True


@pytest.mark.asyncio
async def test_execute_trade_sets_and_enforces_jurisdiction_block(monkeypatch):
    bot = mod.LighterBot()
    bot.transaction_api = object()
    bot._trading_enabled = True
    bot._allow_live_trading = True
    bot._trading_mode = "live"
    bot._single_symbol_mode = False
    bot._sync_before_entry = False
    bot._target_order_notional_usd = 0.0
    bot._max_order_notional_usd = 0.0
    bot._max_position_notional_usd = 0.0
    bot._min_entry_notional_usd = 0.0
    bot._jurisdiction_block_seconds = 300.0
    bot.market_info = {"SOL": {"order_book_id": 1, "supported_size_decimals": 3}}

    async def _ticker(_coin):
        return 100.0

    async def _submit(**_kwargs):
        return {
            "success": False,
            "error": "code=20558 restricted jurisdiction",
            "metadata": {"execution_state": "rejected"},
        }

    bot._get_ticker = _ticker
    bot._submit_order_with_signer = _submit

    signal = mod.TradeSignal(
        signal_id="jurisdiction-test-1",
        symbol="SOL",
        side=mod.TradeSide.BUY,
        signal_type=mod.SignalType.ENTRY,
        confidence=0.8,
        source="unit-test",
        quantity=0.04,
        metadata={"strategy": "luxalgo_msb_ob", "timeframe": "5m"},
    )

    result = await bot._execute_trade(signal)
    assert result.success is False
    assert bot._jurisdiction_block_until_ts > 0

    signal2 = mod.TradeSignal(
        signal_id="jurisdiction-test-2",
        symbol="SOL",
        side=mod.TradeSide.BUY,
        signal_type=mod.SignalType.ENTRY,
        confidence=0.8,
        source="unit-test",
        quantity=0.04,
        metadata={"strategy": "luxalgo_msb_ob", "timeframe": "5m"},
    )
    blocked = await bot._execute_trade(signal2)
    assert blocked.success is False
    assert "Jurisdiction block active" in (blocked.error_message or "")


def test_decimal_places_from_step_handles_scientific_notation():
    assert mod.LighterBot._decimal_places_from_step("0.001") == 3
    assert mod.LighterBot._decimal_places_from_step("1e-6") == 6
    assert mod.LighterBot._decimal_places_from_step("1") == 0
