"""Unit tests for lib.analytics.forecast."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

from lib.analytics import forecast as fc


class TestDirectionClass:
    def test_bull_terms(self):
        for t in ("bullish", "long", "up", "buy", "BULLISH"):
            assert fc._direction_class(t) == "BULL"

    def test_bear_terms(self):
        for t in ("bearish", "short", "down", "sell", "BEARISH"):
            assert fc._direction_class(t) == "BEAR"

    def test_neutral_and_none(self):
        assert fc._direction_class(None) == "NEUTRAL"
        assert fc._direction_class("") == "NEUTRAL"
        assert fc._direction_class("sideways") == "NEUTRAL"


class TestConsensus:
    def test_agree_bull(self):
        k = {"direction": "bullish"}
        t = {"direction": "long"}
        assert fc._consensus(k, t) == "AGREE_BULL"

    def test_agree_bear(self):
        k = {"direction": "bearish"}
        t = {"direction": "short"}
        assert fc._consensus(k, t) == "AGREE_BEAR"

    def test_contradict(self):
        k = {"direction": "bullish"}
        t = {"direction": "bearish"}
        assert fc._consensus(k, t) == "CONTRADICT"

    def test_kronos_only(self):
        assert fc._consensus({"direction": "bullish"}, None) == "KRONOS_ONLY"

    def test_ta_only(self):
        assert fc._consensus(None, {"direction": "bullish"}) == "TA_ONLY"

    def test_neither(self):
        assert fc._consensus(None, None) == "NEITHER"

    def test_partial_when_one_neutral(self):
        assert fc._consensus({"direction": "bullish"}, {"direction": "sideways"}) == "PARTIAL"


class TestEdgeScore:
    def test_both_bull_high_conf(self):
        k = {"direction": "bullish", "confidence": 0.9}
        t = {"direction": "bullish", "confidence": 0.9}
        s = fc._edge_score(k, t, "AGREE_BULL")
        assert 0.8 <= s <= 1.0

    def test_both_bear_high_conf(self):
        k = {"direction": "bearish", "confidence": 0.9}
        t = {"direction": "bearish", "confidence": 0.9}
        s = fc._edge_score(k, t, "AGREE_BEAR")
        assert -1.0 <= s <= -0.8

    def test_contradict_dampened(self):
        k = {"direction": "bullish", "confidence": 0.9}
        t = {"direction": "bearish", "confidence": 0.9}
        s = fc._edge_score(k, t, "CONTRADICT")
        # net is 0 anyway, but edge weighting shouldn't blow up
        assert abs(s) < 0.1

    def test_clamped(self):
        k = {"direction": "bullish", "confidence": 10.0}  # absurd input
        t = {"direction": "bullish", "confidence": 10.0}
        s = fc._edge_score(k, t, "AGREE_BULL")
        assert s == 1.0


class TestLoadTA:
    def _write(self, path: Path, records: list[dict]) -> None:
        path.write_text("\n".join(json.dumps(r) for r in records) + "\n")

    def test_picks_latest_per_symbol(self, tmp_path, monkeypatch):
        f = tmp_path / "predictions.jsonl"
        now = datetime.now(UTC)
        self._write(
            f,
            [
                {
                    "timestamp": (now - timedelta(hours=2)).isoformat(),
                    "symbol": "BTC",
                    "direction": "bearish",
                    "confidence": 0.5,
                },
                {
                    "timestamp": (now - timedelta(hours=1)).isoformat(),
                    "symbol": "BTC",
                    "direction": "bullish",
                    "confidence": 0.9,
                },
            ],
        )
        monkeypatch.setattr(fc, "TRADING_PREDICTIONS", f)
        got = fc._load_ta_latest_per_symbol()
        assert got["BTC"]["direction"] == "bullish"
        assert got["BTC"]["confidence"] == 0.9

    def test_skips_stale(self, tmp_path, monkeypatch):
        f = tmp_path / "predictions.jsonl"
        now = datetime.now(UTC)
        self._write(
            f,
            [
                {
                    "timestamp": (now - timedelta(hours=48)).isoformat(),
                    "symbol": "ETH",
                    "direction": "bullish",
                    "confidence": 0.7,
                },
            ],
        )
        monkeypatch.setattr(fc, "TRADING_PREDICTIONS", f)
        got = fc._load_ta_latest_per_symbol()
        assert "ETH" not in got

    def test_empty_when_no_file(self, tmp_path, monkeypatch):
        monkeypatch.setattr(fc, "TRADING_PREDICTIONS", tmp_path / "nonexistent.jsonl")
        assert fc._load_ta_latest_per_symbol() == {}


class TestForecastIntegration:
    def test_merges_kronos_and_ta_via_alias(self, tmp_path, monkeypatch):
        # Set up Kronos data under data/intelligence/2026-04-19/predictions.json
        idir = tmp_path / "intelligence" / "2026-04-19"
        idir.mkdir(parents=True)
        (idir / "predictions.json").write_text(
            json.dumps(
                {
                    "generated_at": "2026-04-19T01:00:00+00:00",
                    "predictions": {
                        "BTC-USD": {
                            "current_price": 75000,
                            "direction": "bullish",
                            "confidence": 0.8,
                            "predict_bars": 24,
                            "interval": "1h",
                            "predictions": [
                                {"high": 76000, "low": 74500, "close": 75500},
                                {"high": 76500, "low": 75000, "close": 76000},
                            ],
                        },
                    },
                }
            )
        )
        # Set up TA data
        now = datetime.now(UTC)
        ta_file = tmp_path / "predictions.jsonl"
        ta_file.write_text(
            json.dumps(
                {
                    "timestamp": (now - timedelta(hours=1)).isoformat(),
                    "symbol": "BTC",
                    "direction": "bullish",
                    "confidence": 0.75,
                    "target_price": 77000,
                    "entry_price": 75500,
                    "timeframe": "24h",
                }
            )
            + "\n"
        )
        monkeypatch.setattr(fc, "INTELLIGENCE_DIR", tmp_path / "intelligence")
        monkeypatch.setattr(fc, "TRADING_PREDICTIONS", ta_file)
        got = fc.forecast()
        # BTC-USD (Kronos) and BTC (TA) canonicalize to BTC
        assert len(got["rows"]) == 1
        row = got["rows"][0]
        assert row["symbol"] == "BTC"
        assert row["consensus"] == "AGREE_BULL"
        assert row["edge_score"] > 0
        assert row["kronos"]["target_high"] == 76500
        assert row["kronos"]["target_low"] == 74500
        assert row["ta"]["target_price"] == 77000

    def test_no_data_graceful(self, tmp_path, monkeypatch):
        monkeypatch.setattr(fc, "INTELLIGENCE_DIR", tmp_path / "nope")
        monkeypatch.setattr(fc, "TRADING_PREDICTIONS", tmp_path / "nope.jsonl")
        got = fc.forecast()
        assert got["rows"] == []
        assert got["kronos_stamp"] is None
