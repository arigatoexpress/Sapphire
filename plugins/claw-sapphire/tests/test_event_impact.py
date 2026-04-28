from __future__ import annotations

import importlib.util
import json
from pathlib import Path

TOOL_PATH = Path(__file__).resolve().parents[1] / "tools" / "internal" / "event_impact.py"


def _tool():
    spec = importlib.util.spec_from_file_location("event_impact_tool_test", TOOL_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_corpus_action_returns_default_count():
    out = _tool().corpus_action()
    assert out["ok"] is True
    assert out["count"] >= 80


def test_corpus_action_reports_categories():
    out = _tool().corpus_action()
    assert "fomc_decision" in out["categories"]


def test_lookup_action_reports_missing_model_when_no_model(tmp_path: Path, monkeypatch):
    tool = _tool()
    monkeypatch.setattr(tool, "DEFAULT_MODEL_DIR", tmp_path)
    out = tool.lookup_action({"event": {"category": "fomc_decision"}, "asset": "BTC"})
    assert out["ok"] is False
    assert "no event-impact model" in out["error"]


def test_lookup_action_uses_supplied_model_path(tmp_path: Path):
    model = {
        "schema_version": "0.1.0",
        "generated_at": "2024-01-01T00:00:00+00:00",
        "horizons_hours": [24],
        "metadata": {},
        "profiles": [
            {
                "category": "fomc_decision",
                "sub_category": "rate_hike",
                "asset": "BTC",
                "horizon_hours": 24,
                "mean_return_pct": -1,
                "median_return_pct": -1,
                "n": 6,
                "stdev": 2,
                "confidence_interval_95": [-3, 1],
                "direction_consensus": -0.5,
            }
        ],
    }
    path = tmp_path / "model.json"
    path.write_text(json.dumps(model), encoding="utf-8")
    out = _tool().lookup_action(
        {
            "model_path": str(path),
            "event": {"category": "fomc_decision", "sub_category": "rate_hike"},
            "asset": "BTC",
            "horizon_hours": 24,
        }
    )
    assert out["ok"] is True
    assert out["reaction"]["matched_level"] == "exact"


def test_rebuild_action_is_dry_run_without_env(monkeypatch):
    monkeypatch.delenv("SAPPHIRE_EVENT_IMPACT_REBUILD", raising=False)
    out = _tool().rebuild_action({})
    assert out["mode"] == "dry-run"


def test_rebuild_action_calls_builder_when_env_set(monkeypatch, tmp_path: Path):
    tool = _tool()
    monkeypatch.setenv("SAPPHIRE_EVENT_IMPACT_REBUILD", "1")
    called = {}

    def fake_build(output_dir, assets):
        called["assets"] = assets
        path = tmp_path / "model.json"
        path.write_text("{}", encoding="utf-8")
        return path

    import services.event_impact.build as build_module

    monkeypatch.setattr(build_module, "build", fake_build)
    out = tool.rebuild_action({"assets": ["btc"], "output_dir": str(tmp_path)})
    assert out["ok"] is True
    assert called["assets"] == ("BTC",)


def test_accuracy_audit_scores_direction_matches():
    out = _tool().accuracy_audit_action(
        {"observations": [{"expected": {"direction_consensus": 1}, "actual_return_pct": 2}]}
    )
    assert out["accuracy"] == 1.0


def test_accuracy_audit_handles_unscored_rows():
    out = _tool().accuracy_audit_action(
        {"observations": [{"expected": {"direction_consensus": 0}, "actual_return_pct": 2}]}
    )
    assert out["scored"] == 0
    assert out["accuracy"] is None


def test_handle_unknown_action_lists_valid_actions():
    out = _tool().handle({"action": "bogus"})
    assert "valid_actions" in out


def test_main_rejects_invalid_json(capsys):
    rc = _tool().main(stream_in=type("S", (), {"read": lambda self: "{"})(), stream_out=__import__("sys").stdout)
    captured = capsys.readouterr()
    assert rc == 2
    assert "invalid JSON" in captured.out


def test_main_accepts_json_object(capsys):
    rc = _tool().main(stream_in=type("S", (), {"read": lambda self: '{"action":"corpus"}'})(), stream_out=__import__("sys").stdout)
    captured = capsys.readouterr()
    assert rc == 0
    assert '"ok": true' in captured.out


def test_main_rejects_json_array(capsys):
    rc = _tool().main(stream_in=type("S", (), {"read": lambda self: "[]"})(), stream_out=__import__("sys").stdout)
    captured = capsys.readouterr()
    assert rc == 2
    assert "JSON object" in captured.out
