"""Adapter-by-adapter tests for ``lib.correlator.sources``.

Every test mocks the on-disk snapshot the adapter reads so nothing
depends on the live state of ``data/`` or ``~/.sapphire/``.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import pytest

from lib.correlator.sources import (
    ConvergenceWatchlistSource,
    CrossAssetRegimeSource,
    HyperliquidSource,
    KronosForecastSource,
    SourceSignal,
    SovereignThesisSource,
    TAScannerSource,
    TelegramIntelSource,
    ThreatIntelSource,
    TradingViewSource,
    available_sources,
    build_default_sources,
)


def _iso(now: datetime) -> str:
    return now.isoformat()


def test_available_sources_lists_full_adapter_set() -> None:
    classes = available_sources()
    assert len(classes) >= 14
    names = {c.__name__ for c in classes}
    assert "TradingViewSource" in names
    assert "KronosForecastSource" in names
    assert "CrossAssetRegimeSource" in names
    assert "DeFiLlamaSource" in names
    assert "LaborSource" in names
    # Lane 7 — SEC + earnings
    assert "SECEdgarSource" in names
    assert "EarningsCallSource" in names


def test_build_default_sources_returns_one_of_each() -> None:
    instances = build_default_sources()
    assert len(instances) == len(available_sources())
    assert {type(s).__name__ for s in instances} == {c.__name__ for c in available_sources()}


# ---------------------------------------------------------------------------
# TradingView
# ---------------------------------------------------------------------------


def test_tradingview_source_returns_none_when_dir_missing(tmp_path) -> None:
    src = TradingViewSource(base_dir=tmp_path / "missing")
    assert src.latest_for("BTC", "1h") is None


def test_tradingview_source_reads_latest_signal(tmp_path) -> None:
    base = tmp_path / "signals"
    base.mkdir()
    today = datetime.now(UTC) - timedelta(minutes=5)
    file = base / "2026-04-28.jsonl"
    file.write_text(
        json.dumps(
            {
                "symbol": "BTC",
                "direction": "long",
                "timestamp": _iso(today),
                "confidence": 0.82,
                "score": 87.0,
            }
        )
        + "\n",
        encoding="utf-8",
    )
    src = TradingViewSource(base_dir=base)
    sig = src.latest_for("BTC", "1h")
    assert sig is not None
    assert sig.direction == "bull"
    assert sig.symbol == "BTC"
    assert sig.confidence == pytest.approx(0.82)
    assert sig.age_seconds < 600


def test_tradingview_source_canonicalizes_btc_usd(tmp_path) -> None:
    base = tmp_path / "signals"
    base.mkdir()
    file = base / "2026-04-28.jsonl"
    file.write_text(
        json.dumps(
            {"symbol": "BTC-USD", "direction": "sell", "timestamp": _iso(datetime.now(UTC))}
        )
        + "\n",
        encoding="utf-8",
    )
    src = TradingViewSource(base_dir=base)
    sig = src.latest_for("BTC", "1h")
    assert sig is not None
    assert sig.direction == "bear"


def test_tradingview_source_skips_other_symbols(tmp_path) -> None:
    base = tmp_path / "signals"
    base.mkdir()
    file = base / "2026-04-28.jsonl"
    file.write_text(
        json.dumps({"symbol": "ETH", "direction": "long", "timestamp": _iso(datetime.now(UTC))})
        + "\n",
        encoding="utf-8",
    )
    src = TradingViewSource(base_dir=base)
    assert src.latest_for("BTC", "1h") is None


# ---------------------------------------------------------------------------
# Telegram intel
# ---------------------------------------------------------------------------


def test_telegram_intel_source_handles_missing_file(tmp_path) -> None:
    src = TelegramIntelSource(path=tmp_path / "absent.jsonl")
    assert src.latest_for("BTC", "1h") is None


def test_telegram_intel_source_reads_label(tmp_path) -> None:
    path = tmp_path / "telegram_intel_signals.jsonl"
    path.write_text(
        json.dumps(
            {
                "symbols": ["BTC"],
                "label": "bullish",
                "timestamp": _iso(datetime.now(UTC)),
                "confidence": 0.6,
                "channel": "@glassnode",
                "id": "msg-1",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    src = TelegramIntelSource(path=path)
    sig = src.latest_for("BTC", "1h")
    assert sig is not None
    assert sig.direction == "bull"
    assert sig.confidence == pytest.approx(0.6)


def test_telegram_intel_source_neutral_default(tmp_path) -> None:
    path = tmp_path / "telegram_intel_signals.jsonl"
    path.write_text(
        json.dumps(
            {"symbols": ["BTC"], "label": "uncertain", "timestamp": _iso(datetime.now(UTC))}
        )
        + "\n",
        encoding="utf-8",
    )
    src = TelegramIntelSource(path=path)
    sig = src.latest_for("BTC", "1h")
    assert sig is not None
    assert sig.direction == "neutral"


# ---------------------------------------------------------------------------
# Hyperliquid
# ---------------------------------------------------------------------------


def test_hyperliquid_source_reads_kind(tmp_path) -> None:
    path = tmp_path / "hyperliquid_signals.jsonl"
    path.write_text(
        json.dumps(
            {
                "symbol": "BTC",
                "kind": "trade_imbalance_buy",
                "timestamp": _iso(datetime.now(UTC)),
                "confidence": 0.4,
            }
        )
        + "\n",
        encoding="utf-8",
    )
    src = HyperliquidSource(path=path)
    sig = src.latest_for("BTC", "1h")
    assert sig is not None
    assert sig.direction == "bull"


def test_hyperliquid_source_falls_back_to_side(tmp_path) -> None:
    path = tmp_path / "hyperliquid_signals.jsonl"
    path.write_text(
        json.dumps(
            {
                "symbol": "BTC",
                "side": "ask",
                "timestamp": _iso(datetime.now(UTC)),
            }
        )
        + "\n",
        encoding="utf-8",
    )
    src = HyperliquidSource(path=path)
    sig = src.latest_for("BTC", "1h")
    assert sig is not None
    assert sig.direction == "bear"


def test_hyperliquid_source_unknown_kind_is_neutral(tmp_path) -> None:
    path = tmp_path / "hyperliquid_signals.jsonl"
    path.write_text(
        json.dumps({"symbol": "BTC", "kind": "weird-event", "timestamp": _iso(datetime.now(UTC))})
        + "\n",
        encoding="utf-8",
    )
    src = HyperliquidSource(path=path)
    sig = src.latest_for("BTC", "1h")
    assert sig is not None
    assert sig.direction == "neutral"


# ---------------------------------------------------------------------------
# Cross-asset regime
# ---------------------------------------------------------------------------


def test_cross_asset_regime_source_reads_crisis_regime(tmp_path) -> None:
    base = tmp_path / "cross_asset" / "2026-04-28"
    base.mkdir(parents=True)
    (base / "regimes.jsonl").write_text(
        json.dumps(
            {
                "label": "crisis_correlation_spike",
                "timestamp": _iso(datetime.now(UTC)),
                "confidence": 0.86,
                "metrics": {"average_abs_correlation": 0.91},
            }
        )
        + "\n",
        encoding="utf-8",
    )
    src = CrossAssetRegimeSource(base_dir=tmp_path / "cross_asset")

    sig = src.latest_for("BTC", "1h")

    assert sig is not None
    assert sig.source == "cross_asset_regime"
    assert sig.direction == "bear"
    assert sig.confidence == pytest.approx(0.86)
    assert sig.raw["label"] == "crisis_correlation_spike"


# ---------------------------------------------------------------------------
# Threat-intel
# ---------------------------------------------------------------------------


def test_threat_intel_source_returns_none_when_missing(tmp_path) -> None:
    src = ThreatIntelSource(path=tmp_path / "absent.json")
    assert src.latest_for("BTC", "1h") is None


def test_threat_intel_source_reads_bearish_signal(tmp_path) -> None:
    path = tmp_path / "sapphire_signals.json"
    path.write_text(
        json.dumps(
            {
                "generated_at": _iso(datetime.now(UTC)),
                "signals": {
                    "BTC": {
                        "sentiment": "bearish",
                        "confidence": 0.5,
                        "cves": ["CVE-2026-1340"],
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    src = ThreatIntelSource(path=path)
    sig = src.latest_for("BTC", "1h")
    assert sig is not None
    assert sig.direction == "bear"
    assert "CVE-2026-1340" in sig.raw["cves"]


def test_threat_intel_source_skips_unknown_symbol(tmp_path) -> None:
    path = tmp_path / "sapphire_signals.json"
    path.write_text(
        json.dumps({"generated_at": _iso(datetime.now(UTC)), "signals": {"BTC": {}}}),
        encoding="utf-8",
    )
    src = ThreatIntelSource(path=path)
    assert src.latest_for("ETH", "1h") is None


# ---------------------------------------------------------------------------
# Convergence watchlist
# ---------------------------------------------------------------------------


def test_convergence_watchlist_source_returns_bull_for_known_ticker(tmp_path) -> None:
    path = tmp_path / "convergence_watchlist.json"
    path.write_text(
        json.dumps(
            {
                "generated": "2026-04-19",
                "tiers": {
                    "growth_satellite": {
                        "positions": [
                            {"ticker": "FSLR", "thesis": "Solar"},
                        ]
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    src = ConvergenceWatchlistSource(path=path)
    sig = src.latest_for("FSLR", "1d")
    assert sig is not None
    assert sig.direction == "bull"
    assert sig.confidence == pytest.approx(0.65)


def test_convergence_watchlist_source_returns_none_for_unknown_ticker(tmp_path) -> None:
    path = tmp_path / "convergence_watchlist.json"
    path.write_text(
        json.dumps({"tiers": {"growth_satellite": {"positions": [{"ticker": "FSLR"}]}}}),
        encoding="utf-8",
    )
    src = ConvergenceWatchlistSource(path=path)
    assert src.latest_for("BTC", "1h") is None


# ---------------------------------------------------------------------------
# Sovereign-thesis
# ---------------------------------------------------------------------------


def test_sovereign_thesis_source_handles_missing_file(tmp_path) -> None:
    src = SovereignThesisSource(path=tmp_path / "absent.json")
    assert src.latest_for("BTC", "1h") is None


def test_sovereign_thesis_source_reads_composite_score(tmp_path) -> None:
    path = tmp_path / "sovereign-thesis.json"
    path.write_text(
        json.dumps(
            {
                "generated_at": _iso(datetime.now(UTC)),
                "assets": {
                    "BTC": {"composite_score": 0.8, "fit": "strong"},
                },
            }
        ),
        encoding="utf-8",
    )
    src = SovereignThesisSource(path=path)
    sig = src.latest_for("BTC", "1h")
    assert sig is not None
    assert sig.direction == "bull"


def test_sovereign_thesis_source_negative_score_is_bear(tmp_path) -> None:
    path = tmp_path / "sovereign-thesis.json"
    path.write_text(
        json.dumps({"assets": {"BTC": {"composite_score": -0.4}}}),
        encoding="utf-8",
    )
    src = SovereignThesisSource(path=path)
    sig = src.latest_for("BTC", "1h")
    assert sig is not None
    assert sig.direction == "bear"


# ---------------------------------------------------------------------------
# Kronos
# ---------------------------------------------------------------------------


def test_kronos_source_returns_none_when_dir_missing(tmp_path) -> None:
    src = KronosForecastSource(base_dir=tmp_path / "missing")
    assert src.latest_for("BTC", "1h") is None


def test_kronos_source_reads_latest_predictions(tmp_path) -> None:
    base = tmp_path / "intelligence"
    day = base / "2026-04-28"
    day.mkdir(parents=True)
    (day / "predictions.json").write_text(
        json.dumps(
            {
                "generated_at": _iso(datetime.now(UTC)),
                "predictions": {
                    "BTC-USD": {
                        "direction": "bullish",
                        "confidence": 0.74,
                        "interval": "1h",
                        "predict_bars": 24,
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    src = KronosForecastSource(base_dir=base)
    sig = src.latest_for("BTC", "1h")
    assert sig is not None
    assert sig.direction == "bull"
    assert sig.confidence == pytest.approx(0.74)


# ---------------------------------------------------------------------------
# TA scanner
# ---------------------------------------------------------------------------


def test_ta_scanner_source_handles_missing_file(tmp_path) -> None:
    src = TAScannerSource(path=tmp_path / "absent.jsonl")
    assert src.latest_for("BTC", "1h") is None


def test_ta_scanner_source_reads_latest_prediction(tmp_path) -> None:
    path = tmp_path / "trading_predictions.jsonl"
    path.write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "timestamp": _iso(datetime.now(UTC) - timedelta(hours=2)),
                        "symbol": "BTC",
                        "direction": "bullish",
                        "confidence": 0.85,
                        "timeframe": "24h",
                    }
                ),
                json.dumps(
                    {
                        "timestamp": _iso(datetime.now(UTC)),
                        "symbol": "BTC",
                        "direction": "bearish",
                        "confidence": 0.7,
                        "timeframe": "24h",
                    }
                ),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    src = TAScannerSource(path=path)
    # Reads in reverse, so the latest entry (bearish) wins.
    sig = src.latest_for("BTC", "1h")
    assert sig is not None
    assert sig.direction == "bear"
    assert sig.confidence == pytest.approx(0.7)


def test_source_signal_to_dict_roundtrips() -> None:
    sig = SourceSignal(
        source="x",
        symbol="BTC",
        timeframe="1h",
        direction="bull",
        confidence=0.5,
        age_seconds=60.0,
        timestamp_iso="2026-04-28T00:00:00+00:00",
        raw={"k": "v"},
    )
    blob = sig.to_dict()
    assert blob["source"] == "x"
    assert blob["confidence"] == 0.5
    assert blob["raw"] == {"k": "v"}
