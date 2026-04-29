"""Tests for Hyperliquid public-feed signal rules."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SERVICE_SRC = ROOT / "services" / "hyperliquid" / "src"
for path in (ROOT, SERVICE_SRC):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from hyperliquid_bot.public_feed import HyperliquidSignalEngine


def _bbo(symbol: str = "BTC", bid_sz: str = "10", ask_sz: str = "10", time_ms: int = 0) -> dict:
    return {
        "coin": symbol,
        "time": time_ms,
        "bbo": [{"px": "100", "sz": bid_sz, "n": 2}, {"px": "101", "sz": ask_sz, "n": 2}],
    }


def _levels(size: float, *, price: float = 100.0, count: int = 10) -> list[list[dict]]:
    bids = [{"px": str(price - i), "sz": str(size), "n": 1} for i in range(count)]
    asks = [{"px": str(price + 1 + i), "sz": str(size), "n": 1} for i in range(count)]
    return [bids, asks]


def test_trade_below_threshold_does_not_signal():
    engine = HyperliquidSignalEngine()

    assert engine.process_trade({"coin": "BTC", "px": "100000", "sz": "2.0"}) == []


def test_trade_equal_threshold_does_not_signal():
    engine = HyperliquidSignalEngine()

    assert engine.process_trade({"coin": "BTC", "px": "100000", "sz": "2.5"}) == []


def test_trade_above_threshold_emits_large_trade_signal():
    engine = HyperliquidSignalEngine()

    signals = engine.process_trade(
        {"coin": "BTC", "px": "100000", "sz": "2.6", "side": "B", "tid": 42},
        now=100.0,
    )

    assert signals[0]["topic"] == "hyperliquid.trade"
    assert signals[0]["signal_type"] == "large_trade"
    assert signals[0]["notional_usd"] == 260000.0
    assert signals[0]["trade_id"] == 42


def test_trade_missing_price_or_size_is_ignored():
    engine = HyperliquidSignalEngine()

    assert engine.process_trade({"coin": "BTC", "px": "100000"}) == []
    assert engine.process_trade({"coin": "BTC", "sz": "4"}) == []


def test_process_message_handles_trade_arrays():
    engine = HyperliquidSignalEngine()
    message = {
        "channel": "trades",
        "data": [
            {"coin": "BTC", "px": "100000", "sz": "1"},
            {"coin": "BTC", "px": "100000", "sz": "4"},
        ],
    }

    signals = engine.process_message(message, now=100.0)

    assert len(signals) == 1
    assert signals[0]["topic"] == "hyperliquid.trade"


def test_process_message_ignores_subscription_ack():
    engine = HyperliquidSignalEngine()

    assert engine.process_message({"channel": "subscriptionResponse", "data": {}}) == []


def test_bbo_imbalance_requires_sustained_window():
    engine = HyperliquidSignalEngine()

    assert engine.process_bbo(_bbo(bid_sz="40", ask_sz="10"), now=100.0) == []
    assert engine.process_bbo(_bbo(bid_sz="40", ask_sz="10"), now=109.0) == []


def test_bbo_imbalance_emits_after_ten_seconds():
    engine = HyperliquidSignalEngine()
    engine.process_bbo(_bbo(bid_sz="40", ask_sz="10"), now=100.0)

    signals = engine.process_bbo(_bbo(bid_sz="40", ask_sz="10"), now=111.0)

    assert signals[0]["topic"] == "hyperliquid.imbalance"
    assert signals[0]["dominant_side"] == "bid"
    assert signals[0]["ratio"] > 3.0
    assert signals[0]["sustained_seconds"] == 11.0


def test_bbo_imbalance_resets_when_ratio_normalizes():
    engine = HyperliquidSignalEngine()
    engine.process_bbo(_bbo(bid_sz="40", ask_sz="10"), now=100.0)
    engine.process_bbo(_bbo(bid_sz="12", ask_sz="10"), now=105.0)

    assert engine.process_bbo(_bbo(bid_sz="40", ask_sz="10"), now=111.0) == []


def test_bbo_imbalance_resets_when_dominant_side_changes():
    engine = HyperliquidSignalEngine()
    engine.process_bbo(_bbo(bid_sz="40", ask_sz="10"), now=100.0)
    engine.process_bbo(_bbo(bid_sz="10", ask_sz="40"), now=105.0)

    assert engine.process_bbo(_bbo(bid_sz="10", ask_sz="40"), now=111.0) == []
    assert (
        engine.process_bbo(_bbo(bid_sz="10", ask_sz="40"), now=116.0)[0]["dominant_side"] == "ask"
    )


def test_bbo_imbalance_has_emit_cooldown():
    engine = HyperliquidSignalEngine()
    engine.process_bbo(_bbo(bid_sz="40", ask_sz="10"), now=100.0)

    assert engine.process_bbo(_bbo(bid_sz="40", ask_sz="10"), now=111.0)
    assert engine.process_bbo(_bbo(bid_sz="40", ask_sz="10"), now=115.0) == []


def test_l2_book_needs_baseline_before_thin_signal():
    engine = HyperliquidSignalEngine()

    assert engine.process_l2_book({"coin": "BTC", "levels": _levels(10)}, now=100.0) == []


def test_l2_book_emits_when_top_ten_depth_drops_more_than_thirty_percent():
    engine = HyperliquidSignalEngine()
    engine.process_l2_book({"coin": "BTC", "levels": _levels(10)}, now=100.0)

    signals = engine.process_l2_book({"coin": "BTC", "levels": _levels(6)}, now=120.0)

    assert signals[0]["topic"] == "hyperliquid.book.thin"
    assert signals[0]["signal_type"] == "top_10_depth_drop"
    assert signals[0]["drop_ratio"] > 0.30


def test_l2_book_does_not_emit_for_small_depth_drop():
    engine = HyperliquidSignalEngine()
    engine.process_l2_book({"coin": "BTC", "levels": _levels(10)}, now=100.0)

    assert engine.process_l2_book({"coin": "BTC", "levels": _levels(8)}, now=120.0) == []


def test_l2_book_prunes_baseline_after_window():
    engine = HyperliquidSignalEngine()
    engine.process_l2_book({"coin": "BTC", "levels": _levels(10)}, now=100.0)

    assert engine.process_l2_book({"coin": "BTC", "levels": _levels(6)}, now=170.1) == []


def test_l2_book_has_emit_cooldown():
    engine = HyperliquidSignalEngine()
    engine.process_l2_book({"coin": "BTC", "levels": _levels(10)}, now=100.0)

    assert engine.process_l2_book({"coin": "BTC", "levels": _levels(6)}, now=120.0)
    assert engine.process_l2_book({"coin": "BTC", "levels": _levels(5)}, now=130.0) == []


def test_unknown_channel_is_ignored():
    engine = HyperliquidSignalEngine()

    assert engine.process_message({"channel": "orders", "data": {"coin": "BTC"}}) == []
