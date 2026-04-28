"""Unit tests for lib.analytics.prediction_accuracy."""

from __future__ import annotations

import json

from lib.analytics import prediction_accuracy as pa


def _write(path, records):
    path.write_text("\n".join(json.dumps(r) for r in records) + "\n")


class TestReport:
    def test_empty_when_no_file(self, tmp_path, monkeypatch):
        monkeypatch.setattr(pa, "PREDICTIONS_FILE", tmp_path / "nonexistent.jsonl")
        r = pa.report()
        assert r["total"] == 0
        assert r["accuracy"] is None
        assert r["by_symbol"] == {}

    def test_computes_overall_accuracy(self, tmp_path, monkeypatch):
        f = tmp_path / "p.jsonl"
        _write(
            f,
            [
                {
                    "symbol": "BTC",
                    "direction": "bullish",
                    "correct": True,
                    "timestamp": "2026-04-18T00:00:00+00:00",
                },
                {
                    "symbol": "BTC",
                    "direction": "bullish",
                    "correct": False,
                    "timestamp": "2026-04-18T01:00:00+00:00",
                },
                {
                    "symbol": "BTC",
                    "direction": "bearish",
                    "correct": True,
                    "timestamp": "2026-04-18T02:00:00+00:00",
                },
            ],
        )
        monkeypatch.setattr(pa, "PREDICTIONS_FILE", f)
        r = pa.report()
        assert r["total"] == 3
        assert r["scored"] == 3
        assert r["correct"] == 2
        assert r["accuracy"] == 0.6667

    def test_counts_open_predictions(self, tmp_path, monkeypatch):
        f = tmp_path / "p.jsonl"
        _write(
            f,
            [
                {
                    "symbol": "BTC",
                    "direction": "bullish",
                    "correct": True,
                    "timestamp": "2026-04-18T00:00:00+00:00",
                },
                {
                    "symbol": "ETH",
                    "direction": "bullish",
                    "correct": None,
                    "timestamp": "2026-04-19T00:00:00+00:00",
                },
                {"symbol": "SOL", "direction": "bullish", "timestamp": "2026-04-19T00:00:00+00:00"},
            ],
        )
        monkeypatch.setattr(pa, "PREDICTIONS_FILE", f)
        r = pa.report()
        assert r["total"] == 3
        assert r["scored"] == 1
        assert r["open"] == 2

    def test_per_symbol_and_direction(self, tmp_path, monkeypatch):
        f = tmp_path / "p.jsonl"
        _write(
            f,
            [
                {
                    "symbol": "BTC",
                    "direction": "bullish",
                    "correct": True,
                    "timestamp": "2026-04-18T00:00:00+00:00",
                },
                {
                    "symbol": "BTC",
                    "direction": "bullish",
                    "correct": True,
                    "timestamp": "2026-04-18T01:00:00+00:00",
                },
                {
                    "symbol": "ETH",
                    "direction": "bearish",
                    "correct": False,
                    "timestamp": "2026-04-18T02:00:00+00:00",
                },
            ],
        )
        monkeypatch.setattr(pa, "PREDICTIONS_FILE", f)
        r = pa.report()
        assert r["by_symbol"]["BTC"]["accuracy"] == 1.0
        assert r["by_symbol"]["ETH"]["accuracy"] == 0.0
        assert r["by_direction"]["bullish"]["accuracy"] == 1.0
        assert r["by_direction"]["bearish"]["accuracy"] == 0.0

    def test_recent_sorted_desc(self, tmp_path, monkeypatch):
        f = tmp_path / "p.jsonl"
        _write(
            f,
            [
                {"symbol": "A", "timestamp": "2026-04-01T00:00:00+00:00"},
                {"symbol": "C", "timestamp": "2026-04-03T00:00:00+00:00"},
                {"symbol": "B", "timestamp": "2026-04-02T00:00:00+00:00"},
            ],
        )
        monkeypatch.setattr(pa, "PREDICTIONS_FILE", f)
        r = pa.report()
        assert [x["symbol"] for x in r["recent"]] == ["C", "B", "A"]
