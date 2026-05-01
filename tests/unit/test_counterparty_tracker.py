from __future__ import annotations

from datetime import UTC, datetime

from lib.counterparty.tracker import (
    MAX_TRADERS_TRACKED,
    PositionChange,
    TraderPosition,
    TraderStats,
    rank_traders,
    track_position_changes,
)


def test_trader_stats_from_dict_accepts_aliases():
    trader = TraderStats.from_dict(
        {"user": "0xABC", "pnl30d": 100000, "pnl90d": 200000, "sharpe": 1.5}
    )
    assert trader.address == "0xabc"
    assert trader.realized_pnl_30d_usd == 100000


def test_quality_score_rewards_pnl_and_sharpe():
    low = TraderStats("0x1", None, 100000, 0, 0.1)
    high = TraderStats("0x2", None, 100000, 0, 3.0)
    assert high.quality_score() > low.quality_score()


def test_rank_traders_filters_small_accounts():
    ranked = rank_traders([{"address": "0x1", "realized_pnl_30d_usd": 1000, "sharpe_30d": 9}])
    assert ranked == []


def test_rank_traders_orders_by_quality():
    ranked = rank_traders(
        [
            {
                "address": "0x1",
                "realized_pnl_30d_usd": 100000,
                "realized_pnl_90d_usd": 0,
                "sharpe_30d": 0,
            },
            {
                "address": "0x2",
                "realized_pnl_30d_usd": 120000,
                "realized_pnl_90d_usd": 300000,
                "sharpe_30d": 2,
            },
        ]
    )
    assert ranked[0].address == "0x2"


def test_rank_traders_caps_top_n_and_hard_max():
    rows = [
        {"address": f"0x{i}", "realized_pnl_30d_usd": 100000 + i, "sharpe_30d": 1}
        for i in range(150)
    ]
    assert len(rank_traders(rows, top_n=500)) == MAX_TRADERS_TRACKED


def test_position_from_dict_infers_long_side():
    pos = TraderPosition.from_dict("0xabc", {"coin": "btc", "notional": 10})
    assert pos.asset == "BTC"
    assert pos.side == "long"


def test_position_from_dict_infers_short_from_side():
    pos = TraderPosition.from_dict("0xabc", {"asset": "ETH", "side": "short", "size_usd": 25})
    assert pos.signed_size_usd == -25


def test_position_from_dict_infers_side_from_signed_notional():
    pos = TraderPosition.from_dict("0xabc", {"asset": "SOL", "signed_size_usd": -40})
    assert pos.side == "short"
    assert pos.size_usd == 40


def test_track_position_changes_detects_growth():
    changes = track_position_changes(
        [TraderPosition("0x1", "BTC", "long", 100)],
        [TraderPosition("0x1", "BTC", "long", 130)],
        threshold_pct=15,
        detected_at=datetime(2024, 1, 1, tzinfo=UTC),
    )
    assert len(changes) == 1
    assert changes[0].change_pct == 30.0


def test_track_position_changes_ignores_small_shift():
    changes = track_position_changes(
        [TraderPosition("0x1", "BTC", "long", 100)],
        [TraderPosition("0x1", "BTC", "long", 105)],
        threshold_pct=15,
    )
    assert changes == []


def test_track_position_changes_detects_new_position():
    changes = track_position_changes(
        [], [TraderPosition("0x1", "BTC", "long", 100)], threshold_pct=15
    )
    assert changes[0].old_size_usd == 0


def test_track_position_changes_detects_closed_position_as_flat():
    changes = track_position_changes(
        [TraderPosition("0x1", "BTC", "long", 100)], [], threshold_pct=15
    )
    assert changes[0].side == "flat"


def test_track_position_changes_detects_flip_long_to_short():
    changes = track_position_changes(
        [TraderPosition("0x1", "BTC", "long", 100)],
        [TraderPosition("0x1", "BTC", "short", 100)],
        threshold_pct=15,
    )
    assert changes[0].change_pct == 200.0


def test_track_position_changes_accepts_dict_inputs():
    changes = track_position_changes(
        [{"trader": "0x1", "asset": "BTC", "side": "long", "size_usd": 100}],
        [{"trader": "0x1", "asset": "BTC", "side": "long", "size_usd": 150}],
    )
    assert changes[0].trader == "0x1"


def test_track_position_changes_dedupes_by_trader_and_asset():
    changes = track_position_changes(
        [TraderPosition("0x1", "BTC", "long", 100), TraderPosition("0x1", "ETH", "long", 100)],
        [TraderPosition("0x1", "BTC", "long", 200), TraderPosition("0x1", "ETH", "long", 100)],
    )
    assert [c.asset for c in changes] == ["BTC"]


def test_position_change_to_dict():
    change = PositionChange("0x1", "BTC", "long", "long", 1, 2, 100, "long", "now")
    assert change.to_dict()["asset"] == "BTC"


def test_bad_numeric_values_default_to_zero():
    trader = TraderStats.from_dict(
        {"address": "0x1", "realized_pnl_30d_usd": "bad", "sharpe_30d": "bad"}
    )
    assert trader.realized_pnl_30d_usd == 0


def test_empty_trader_address_is_filtered():
    assert rank_traders([{"address": "", "realized_pnl_30d_usd": 999999, "sharpe_30d": 9}]) == []


def test_detected_at_is_iso_utc():
    change = track_position_changes(
        [],
        [TraderPosition("0x1", "BTC", "long", 100)],
        detected_at=datetime(2024, 1, 1, tzinfo=UTC),
    )[0]
    assert change.detected_at == "2024-01-01T00:00:00+00:00"
