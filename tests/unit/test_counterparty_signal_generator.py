from __future__ import annotations

from datetime import UTC, datetime

from lib.counterparty.signal_generator import CounterpartySignal, generate_signals
from lib.counterparty.tracker import PositionChange


def _change(trader="0x1", asset="BTC", side="long", old=100, new=150, pct=50):
    return PositionChange(trader, asset, "long", side, old, new, pct, side, "2024-01-01T00:00:00+00:00")


def test_generate_signal_for_single_long_change():
    signals = generate_signals([_change()], generated_at=datetime(2024, 1, 1, tzinfo=UTC))
    assert signals[0].asset == "BTC"
    assert signals[0].side == "long"


def test_generate_signal_counts_unique_traders():
    signals = generate_signals([_change("0x1"), _change("0x2")])
    assert signals[0].traders_corroborating == 2


def test_generate_signal_groups_by_asset():
    signals = generate_signals([_change(asset="BTC"), _change(asset="ETH")])
    assert {s.asset for s in signals} == {"BTC", "ETH"}


def test_generate_signal_groups_by_side():
    signals = generate_signals([_change(side="long"), _change(side="short", old=150, new=200)])
    assert {s.side for s in signals} == {"long", "short"}


def test_short_signal_consensus_is_negative():
    signals = generate_signals([_change(side="short", old=100, new=200)])
    assert signals[0].smart_money_consensus < 0


def test_min_traders_filters_groups():
    assert generate_signals([_change()], min_traders=2) == []


def test_generate_signals_accepts_dict_changes():
    signals = generate_signals([_change().to_dict()])
    assert signals[0].asset == "BTC"


def test_unknown_side_is_ignored():
    assert generate_signals([_change(side="weird")]) == []


def test_empty_asset_is_ignored():
    assert generate_signals([_change(asset="")]) == []


def test_magnitude_is_capped_at_one():
    signals = generate_signals([_change(pct=500)])
    assert signals[0].magnitude == 1.0


def test_counterparty_signal_to_dict():
    signal = CounterpartySignal("BTC", "long", 0.5, 2, 0.4, 1000, "now")
    assert signal.to_dict()["source"] == "hyperliquid-counterparty-intel"


def test_generated_at_is_stable_when_supplied():
    signal = generate_signals([_change()], generated_at=datetime(2024, 1, 1, tzinfo=UTC))[0]
    assert signal.generated_at == "2024-01-01T00:00:00+00:00"


def test_flat_changes_generate_flat_context_signal():
    signal = generate_signals([_change(side="flat", old=100, new=0)])[0]
    assert signal.side == "flat"


def test_notional_delta_reflects_growth():
    signal = generate_signals([_change(old=100, new=180)])[0]
    assert signal.notional_delta_usd == 80.0
