"""Unit tests for the PortfolioTracker module."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../services/alpha-engine"))

from src.execution.portfolio import PortfolioTracker


def _fill(
    venue="ASTER",
    symbol="SOL",
    side="BUY",
    qty=1.0,
    price=100.0,
    success=True,
    pnl=None,
):
    fill = {
        "platform": venue,
        "symbol": symbol,
        "side": side,
        "filled_quantity": qty,
        "avg_price": price,
        "success": success,
    }
    if pnl is not None:
        fill["realized_pnl"] = pnl
    return fill


# ── Basic Position Lifecycle ──────────────────────────────────────


def test_open_and_close_long():
    tracker = PortfolioTracker()
    tracker.process_fill(_fill(side="BUY", qty=1.0, price=100.0))

    assert len(tracker.open_positions) == 1
    pos = tracker.open_positions[0]
    assert pos.venue == "ASTER"
    assert pos.symbol == "SOL"
    assert pos.side == "LONG"
    assert pos.quantity == 1.0
    assert pos.entry_price == 100.0

    # Close at profit
    closed = tracker.process_fill(_fill(side="SELL", qty=1.0, price=110.0))
    assert closed is not None
    assert closed.realized_pnl == 10.0
    assert len(tracker.open_positions) == 0


def test_open_and_close_short():
    tracker = PortfolioTracker()
    tracker.process_fill(_fill(side="SHORT", qty=2.0, price=50.0))

    assert len(tracker.open_positions) == 1
    pos = tracker.open_positions[0]
    assert pos.side == "SHORT"

    closed = tracker.process_fill(_fill(side="BUY", qty=2.0, price=45.0))
    assert closed is not None
    assert closed.realized_pnl == 10.0  # (50 - 45) * 2


def test_close_action():
    tracker = PortfolioTracker()
    tracker.process_fill(_fill(side="BUY", qty=1.0, price=100.0))
    closed = tracker.process_fill(_fill(side="CLOSE", qty=1.0, price=105.0))
    assert closed is not None
    assert closed.realized_pnl == 5.0
    assert len(tracker.open_positions) == 0


# ── Averaging & Partial Fills ─────────────────────────────────────


def test_add_to_position_averages_price():
    tracker = PortfolioTracker()
    tracker.process_fill(_fill(side="BUY", qty=1.0, price=100.0))
    tracker.process_fill(_fill(side="BUY", qty=1.0, price=120.0))

    pos = tracker.open_positions[0]
    assert pos.quantity == 2.0
    assert pos.entry_price == 110.0  # weighted average


def test_partial_close():
    tracker = PortfolioTracker()
    tracker.process_fill(_fill(side="BUY", qty=2.0, price=100.0))
    result = tracker.process_fill(_fill(side="SELL", qty=1.0, price=120.0))

    # Partial close doesn't return a ClosedTrade
    assert result is None
    assert len(tracker.open_positions) == 1
    pos = tracker.open_positions[0]
    assert pos.quantity == 1.0

    snap = tracker.snapshot()
    assert snap["total_realized_pnl"] == 20.0  # (120 - 100) * 1


# ── Multi-Venue ───────────────────────────────────────────────────


def test_multi_venue_positions():
    tracker = PortfolioTracker()
    tracker.process_fill(_fill(venue="ASTER", symbol="SOL", side="BUY", qty=1.0, price=100.0))
    tracker.process_fill(_fill(venue="LIGHTER", symbol="SOL", side="SHORT", qty=0.5, price=100.0))
    tracker.process_fill(_fill(venue="ASTER", symbol="BTC", side="BUY", qty=0.01, price=65000.0))

    assert len(tracker.open_positions) == 3
    snap = tracker.snapshot()
    assert snap["open_count"] == 3


# ── Market Price Updates ──────────────────────────────────────────


def test_unrealized_pnl_calculation():
    tracker = PortfolioTracker()
    tracker.process_fill(_fill(side="BUY", qty=2.0, price=100.0))

    tracker.update_prices({"ASTER": {"SOL": {"price": 110.0}}})
    pos = tracker.open_positions[0]
    assert pos.unrealized_pnl == 20.0  # (110 - 100) * 2


def test_short_unrealized_pnl():
    tracker = PortfolioTracker()
    tracker.process_fill(_fill(side="SHORT", qty=1.0, price=100.0))

    tracker.update_prices({"ASTER": {"SOL": {"price": 90.0}}})
    pos = tracker.open_positions[0]
    assert pos.unrealized_pnl == 10.0  # (100 - 90) * 1


# ── Symbol Normalization ──────────────────────────────────────────


def test_symbol_normalization_strips_usdt():
    tracker = PortfolioTracker()
    tracker.process_fill(_fill(symbol="SOLUSDT", side="BUY", qty=1.0, price=100.0))

    pos = tracker.open_positions[0]
    assert pos.symbol == "SOL"

    # Same position keyed consistently
    tracker.process_fill(_fill(symbol="SOL", side="BUY", qty=1.0, price=120.0))
    assert len(tracker.open_positions) == 1
    assert tracker.open_positions[0].quantity == 2.0


# ── Statistics ────────────────────────────────────────────────────


def test_snapshot_stats():
    tracker = PortfolioTracker()
    # Win
    tracker.process_fill(_fill(side="BUY", qty=1.0, price=100.0))
    tracker.process_fill(_fill(side="SELL", qty=1.0, price=110.0))
    # Loss
    tracker.process_fill(_fill(side="BUY", qty=1.0, price=100.0))
    tracker.process_fill(_fill(side="SELL", qty=1.0, price=95.0))

    snap = tracker.snapshot()
    assert snap["total_trades"] == 4
    assert snap["wins"] == 1
    assert snap["losses"] == 1
    assert snap["total_realized_pnl"] == 5.0  # +10 - 5
    assert snap["win_rate"] == 50.0
    assert len(snap["recent_closed"]) == 2


def test_failed_fill_ignored():
    tracker = PortfolioTracker()
    tracker.process_fill(_fill(success=False))
    assert len(tracker.open_positions) == 0
    assert tracker.snapshot()["total_trades"] == 0


def test_fill_provided_pnl_used():
    tracker = PortfolioTracker()
    tracker.process_fill(_fill(side="BUY", qty=1.0, price=100.0))
    closed = tracker.process_fill(_fill(side="SELL", qty=1.0, price=110.0, pnl=8.5))
    # Uses the fill-provided PnL (8.5) instead of calculated (10.0)
    assert closed.realized_pnl == 8.5


def test_closed_trades_ring_buffer():
    tracker = PortfolioTracker(max_closed_trades=5)
    for i in range(10):
        tracker.process_fill(_fill(side="BUY", qty=1.0, price=100.0))
        tracker.process_fill(_fill(side="SELL", qty=1.0, price=110.0))
    assert len(tracker.closed_trades) == 5
