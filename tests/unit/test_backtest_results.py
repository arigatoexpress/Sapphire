"""Unit tests for lib.analytics.backtest_results."""

from __future__ import annotations

import json
import math

import pytest

from lib.analytics import backtest_results as br


class TestClean:
    def test_replaces_infinity_with_sentinel(self):
        assert br._clean(math.inf) == "inf"
        assert br._clean(-math.inf) == "inf"

    def test_replaces_nan_with_none(self):
        assert br._clean(math.nan) is None

    def test_recurses_into_dict(self):
        got = br._clean({"a": math.inf, "b": {"c": math.nan}, "d": 1.5})
        assert got == {"a": "inf", "b": {"c": None}, "d": 1.5}

    def test_recurses_into_list(self):
        assert br._clean([1, math.inf, math.nan, 2.5]) == [1, "inf", None, 2.5]

    def test_passes_through_other(self):
        assert br._clean("hello") == "hello"
        assert br._clean(42) == 42
        assert br._clean(None) is None


class TestMetricKey:
    def test_none_sorts_last(self):
        k = br._metric_key("sortino")
        rows = [{"sortino": None}, {"sortino": 5.0}, {"sortino": 2.0}]
        ranked = sorted(rows, key=k, reverse=True)
        # non-None first (sortino=5, sortino=2), None last
        assert ranked[0]["sortino"] == 5.0
        assert ranked[1]["sortino"] == 2.0
        assert ranked[2]["sortino"] is None

    def test_inf_sorts_high(self):
        k = br._metric_key("profit_factor")
        rows = [{"profit_factor": 2.0}, {"profit_factor": "inf"}, {"profit_factor": 5.0}]
        ranked = sorted(rows, key=k, reverse=True)
        assert ranked[0]["profit_factor"] == "inf"


class TestLeaderboard:
    def _write_sweep(self, tmp_path, rows):
        d = tmp_path / "data" / "backtests" / "strategies"
        d.mkdir(parents=True)
        f = d / "strategy_sweep_20260418T000000Z.json"
        f.write_text(
            json.dumps(
                {
                    "computed_at": "2026-04-18T00:00:00+00:00",
                    "total_backtests": len(rows),
                    "results": rows,
                }
            )
        )
        return d

    def test_empty_when_no_files(self, tmp_path, monkeypatch):
        monkeypatch.setattr(br, "BACKTESTS_DIR", tmp_path / "nope")
        r = br.leaderboard()
        assert r["rows"] == []
        assert "note" in r

    def test_ranks_by_metric(self, tmp_path, monkeypatch):
        d = self._write_sweep(
            tmp_path,
            [
                {"strategy_cls": "A", "symbol": "BTC", "sortino": 2.0, "total_trades": 10},
                {"strategy_cls": "B", "symbol": "ETH", "sortino": 5.0, "total_trades": 10},
                {"strategy_cls": "C", "symbol": "SOL", "sortino": 1.0, "total_trades": 10},
            ],
        )
        monkeypatch.setattr(br, "BACKTESTS_DIR", d)
        r = br.leaderboard(metric="sortino", limit=2)
        assert len(r["rows"]) == 2
        assert r["rows"][0]["strategy_cls"] == "B"
        assert r["rows"][1]["strategy_cls"] == "A"

    def test_filters_low_trade_count(self, tmp_path, monkeypatch):
        d = self._write_sweep(
            tmp_path,
            [
                {"strategy_cls": "HighVol", "sortino": 5.0, "total_trades": 10},
                {"strategy_cls": "LowVol", "sortino": 999.0, "total_trades": 1},
            ],
        )
        monkeypatch.setattr(br, "BACKTESTS_DIR", d)
        r = br.leaderboard()
        # LowVol filtered out due to <5 trades
        assert len(r["rows"]) == 1
        assert r["rows"][0]["strategy_cls"] == "HighVol"

    def test_include_minimal_trades(self, tmp_path, monkeypatch):
        d = self._write_sweep(
            tmp_path,
            [
                {"strategy_cls": "Low", "sortino": 999.0, "total_trades": 1},
            ],
        )
        monkeypatch.setattr(br, "BACKTESTS_DIR", d)
        r = br.leaderboard(include_minimal_trades=True)
        assert len(r["rows"]) == 1

    def test_invalid_metric_raises(self, tmp_path, monkeypatch):
        monkeypatch.setattr(br, "BACKTESTS_DIR", tmp_path)
        with pytest.raises(ValueError):
            br.leaderboard(metric="nope")


class TestSummary:
    def test_empty_when_no_files(self, tmp_path, monkeypatch):
        monkeypatch.setattr(br, "BACKTESTS_DIR", tmp_path / "nope")
        r = br.summary()
        assert r["have_results"] is False
        assert r["best_per_symbol"] == []
        assert r["total_backtests"] == 0

    def test_reads_best_per_symbol(self, tmp_path, monkeypatch):
        d = tmp_path / "data" / "backtests" / "strategies"
        d.mkdir(parents=True)
        (d / "best_per_symbol_20260418T000000Z.json").write_text(
            json.dumps(
                {
                    "computed_at": "2026-04-18T00:00:00+00:00",
                    "results": [
                        {
                            "strategy_cls": "Sapphire",
                            "symbol": "ETH-USD",
                            "sortino": 101,
                            "total_trades": 7,
                        },
                    ],
                }
            )
        )
        (d / "strategy_sweep_20260418T000000Z.json").write_text(
            json.dumps(
                {
                    "computed_at": "2026-04-18T00:00:00+00:00",
                    "total_backtests": 756,
                    "results": [],
                }
            )
        )
        monkeypatch.setattr(br, "BACKTESTS_DIR", d)
        r = br.summary()
        assert r["have_results"] is True
        assert len(r["best_per_symbol"]) == 1
        assert r["best_per_symbol"][0]["symbol"] == "ETH-USD"
        assert r["total_backtests"] == 756

    def test_inf_passes_through_after_clean(self, tmp_path, monkeypatch):
        d = tmp_path / "data" / "backtests" / "strategies"
        d.mkdir(parents=True)
        # Python json accepts Infinity when writing
        (d / "best_per_symbol_20260418T000000Z.json").write_text(
            '{"computed_at":"2026-04-18T00:00:00+00:00","results":[{"strategy_cls":"X","symbol":"BTC","profit_factor":Infinity,"total_trades":8}]}'
        )
        (d / "strategy_sweep_20260418T000000Z.json").write_text(
            '{"computed_at":"2026-04-18T00:00:00+00:00","total_backtests":1,"results":[]}'
        )
        monkeypatch.setattr(br, "BACKTESTS_DIR", d)
        r = br.summary()
        assert r["best_per_symbol"][0]["profit_factor"] == "inf"
