import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DAILY_PATH = ROOT / "infra" / "scripts" / "kronos_daily.py"
PREDICT_PATH = ROOT / "plugins" / "claw-sapphire" / "tools" / "internal" / "predict_kronos.py"


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_daily_dry_run_suppresses_telegram_and_snapshot_writes(tmp_path, monkeypatch, capsys):
    daily = _load_module("kronos_daily_test", DAILY_PATH)
    output_dir = tmp_path / "kronos-output"
    calls: list[tuple[str, bool]] = []
    telegram_calls: list[tuple[str, bool]] = []

    def fake_prediction(symbol: str, *, dry_run: bool = False, root: Path | None = None):
        calls.append((symbol, dry_run))
        return {
            "symbol": symbol,
            "direction": "bullish",
            "confidence": 0.8,
            "current_price": 100.0,
            "predictions": [{"close": 105.0}],
        }

    def fake_telegram(message: str, *, root: Path | None = None, enabled: bool = True):
        telegram_calls.append((message, enabled))
        return enabled

    monkeypatch.setenv("SAPPHIRE_KRONOS_OUTPUT_DIR", str(output_dir))
    monkeypatch.setattr(daily, "run_prediction", fake_prediction)
    monkeypatch.setattr(daily, "send_telegram", fake_telegram)

    assert daily.main(["--dry-run", "--watchlist", "SPY,TSLA"]) == 0

    snapshot = json.loads((output_dir / "predictions.json").read_text())
    assert snapshot["dry_run"] is True
    assert snapshot["watchlist"] == ["SPY", "TSLA"]
    assert calls == [("SPY", True), ("TSLA", True)]
    assert len(telegram_calls) == 1
    assert telegram_calls[0][1] is False
    assert "Telegram disabled" in capsys.readouterr().out


def test_daily_no_telegram_keeps_snapshot_enabled(tmp_path, monkeypatch):
    daily = _load_module("kronos_daily_no_telegram_test", DAILY_PATH)
    output_dir = tmp_path / "kronos-output"
    calls: list[tuple[str, bool]] = []

    def fake_prediction(symbol: str, *, dry_run: bool = False, root: Path | None = None):
        calls.append((symbol, dry_run))
        return {
            "symbol": symbol,
            "direction": "neutral",
            "confidence": 0.5,
            "current_price": 100.0,
            "predictions": [{"close": 100.0}],
        }

    monkeypatch.setenv("SAPPHIRE_KRONOS_OUTPUT_DIR", str(output_dir))
    monkeypatch.setattr(daily, "run_prediction", fake_prediction)
    monkeypatch.setattr(daily, "send_telegram", lambda *args, **kwargs: kwargs["enabled"])

    assert daily.main(["--no-telegram", "--watchlist", "SPY"]) == 0

    snapshot = json.loads((output_dir / "predictions.json").read_text())
    assert snapshot["dry_run"] is False
    assert calls == [("SPY", False)]


def test_predict_kronos_can_skip_snapshot(monkeypatch, capsys):
    predict = _load_module("predict_kronos_test", PREDICT_PATH)
    saved: list[tuple[dict, str]] = []

    monkeypatch.setattr(
        predict,
        "action_predict",
        lambda **kwargs: {"symbol": kwargs["symbol"], "direction": "neutral"},
    )
    monkeypatch.setattr(predict, "_save_intelligence_snapshot", lambda result, symbol: saved.append((result, symbol)))
    monkeypatch.setattr(
        predict.sys,
        "stdin",
        type("FakeStdin", (), {"read": lambda self: json.dumps({
            "action": "predict",
            "symbol": "SPY",
            "save_snapshot": False,
        })})(),
    )

    predict.main()

    assert saved == []
    assert json.loads(capsys.readouterr().out)["symbol"] == "SPY"
