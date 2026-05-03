"""Tests for scripts/og_publish_kronos.py — Kronos → 0G envelope mapping."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "scripts" / "og_publish_kronos.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("og_publish_kronos", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def kp():
    return _load_module()


class TestDirectionMapping:
    @pytest.mark.parametrize(
        "direction,expected",
        [
            ("bullish", "buy"),
            ("BULLISH", "buy"),
            ("long", "buy"),
            ("up", "buy"),
            ("buy", "buy"),
            ("bearish", "sell"),
            ("short", "sell"),
            ("down", "sell"),
            ("sell", "sell"),
            ("neutral", "hold"),
            ("", "hold"),
            ("garbage", "hold"),
        ],
    )
    def test_direction_to_action(self, kp, direction: str, expected: str) -> None:
        assert kp._direction_to_action(direction) == expected


class TestConfidenceMapping:
    @pytest.mark.parametrize(
        "confidence,expected",
        [
            (None, 0),
            (-0.5, 0),
            (0.0, 0),
            (0.5, 50),
            (0.432, 43),  # the actual ETH-USD value in current data
            (0.757, 76),  # actual ONDO-USD value
            (1.0, 100),
            (1.5, 100),
        ],
    )
    def test_confidence_to_score(self, kp, confidence: float | None, expected: int) -> None:
        assert kp._confidence_to_score(confidence) == expected


class TestSummarise:
    def test_empty_rows(self, kp) -> None:
        assert kp._summarise([]) == {"bars": 0}

    def test_close_extraction(self, kp) -> None:
        rows = [{"close": 100.5}, {"close": 102.0}, {"close": 99.0}]
        out = kp._summarise(rows)
        assert out["bars"] == 3
        assert out["first_close"] == 100.5
        assert out["last_close"] == 99.0
        assert out["min_close"] == 99.0
        assert out["max_close"] == 102.0

    def test_skips_non_numeric(self, kp) -> None:
        rows = [{"close": 100.0}, {"close": None}, {"close": "n/a"}, {"close": 105.0}]
        out = kp._summarise(rows)
        # Only the two numeric closes contribute; ordering preserved
        assert out["bars"] == 4
        assert out["first_close"] == 100.0
        assert out["last_close"] == 105.0


class TestLatestPredictions:
    def test_finds_latest_dated_dir(
        self, kp, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        intel = tmp_path / "intelligence"
        for date in ("2026-04-28", "2026-04-29", "2026-04-30"):
            d = intel / date
            d.mkdir(parents=True)
            (d / "predictions.json").write_text("{}")
        monkeypatch.setattr(kp, "INTELLIGENCE_DIR", intel)
        latest = kp._latest_predictions()
        assert latest is not None
        assert latest.parent.name == "2026-04-30"

    def test_returns_none_when_missing(
        self, kp, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(kp, "INTELLIGENCE_DIR", tmp_path / "nonexistent")
        assert kp._latest_predictions() is None

    def test_skips_non_date_dirs(self, kp, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        intel = tmp_path / "intelligence"
        (intel / "shadow-reports").mkdir(parents=True)
        (intel / "shadow-reports" / "predictions.json").write_text("{}")
        (intel / "2026-04-30").mkdir()
        (intel / "2026-04-30" / "predictions.json").write_text("{}")
        monkeypatch.setattr(kp, "INTELLIGENCE_DIR", intel)
        latest = kp._latest_predictions()
        assert latest is not None
        assert latest.parent.name == "2026-04-30"


class TestDryRun:
    def test_dry_run_does_not_require_flag(
        self, kp, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys
    ) -> None:
        # No SAPPHIRE_OG_ENABLED, no key — dry-run should still work
        monkeypatch.delenv("SAPPHIRE_OG_ENABLED", raising=False)
        monkeypatch.delenv("OG_PRIVATE_KEY", raising=False)

        # Build a tiny predictions file
        intel = tmp_path / "intelligence" / "2026-04-30"
        intel.mkdir(parents=True)
        (intel / "predictions.json").write_text(
            json.dumps(
                {
                    "generated_at": "2026-04-30T00:00:00Z",
                    "source": "kronos-test",
                    "predictions": {
                        "BTC-USD": {
                            "symbol": "BTC-USD",
                            "interval": "1h",
                            "current_price": 65000,
                            "direction": "bullish",
                            "confidence": 0.83,
                            "predict_bars": 24,
                            "predictions": [{"close": 65500}, {"close": 66000}],
                        }
                    },
                }
            )
        )
        monkeypatch.setattr(kp, "INTELLIGENCE_DIR", tmp_path / "intelligence")

        # Simulate CLI invocation
        monkeypatch.setattr("sys.argv", ["og_publish_kronos.py", "--dry-run"])
        rc = kp.main()
        assert rc == 0
        out = capsys.readouterr().out
        # The first JSON object on stdout is the would-publish line
        first_line = next(line for line in out.splitlines() if line.startswith("{"))
        parsed = json.loads(first_line)
        assert parsed["symbol"] == "BTC-USD"
        assert parsed["would_publish"]["action"] == "buy"
        assert parsed["would_publish"]["score"] == 83
        assert parsed["would_publish"]["strategy"] == "kronos_daily_24h"
