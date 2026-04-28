"""Tests for the narrative_synthesis plugin tool."""

from __future__ import annotations

import importlib.util
import io
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

INTERNAL = ROOT / "plugins" / "claw-sapphire" / "tools" / "internal" / "narrative_synthesis.py"

_spec = importlib.util.spec_from_file_location("narrative_synthesis_internal", INTERNAL)
assert _spec is not None and _spec.loader is not None
ns = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = ns
_spec.loader.exec_module(ns)


def _signal() -> dict:
    return {
        "symbol": "BTC",
        "timeframe": "1h",
        "edge_score": 0.72,
        "consensus": "AGREE_BULL",
        "corroborated_by": ["tradingview", "kronos_forecast"],
        "divergent_sources": [],
        "bull_sources": ["tradingview", "kronos_forecast"],
        "bear_sources": [],
        "neutral_sources": [],
        "freshness_seconds": 60,
        "contributing": 3,
        "raw_score": 0.7,
        "agreement_multiplier": 1.2,
        "contradict_factor": 1.0,
        "total_weight": 3.0,
        "generated_at": "2026-04-28T11:59:00+00:00",
        "provenance_envelope": {"generator": "lib.correlator.engine"},
    }


@pytest.fixture
def isolated(monkeypatch, tmp_path):
    output_root = tmp_path / "narratives"
    signal_root = tmp_path / "signals"
    monkeypatch.setattr(ns, "DEFAULT_OUTPUT_ROOT", output_root)
    monkeypatch.setattr(ns, "DEFAULT_SIGNAL_ROOT", signal_root)
    return output_root, signal_root


def test_synthesize_once_with_inline_signal(isolated) -> None:
    out = ns.handle({"action": "synthesize-once", "signal": _signal()})
    assert out["ok"] is True
    assert out["thesis"]["symbol"] == "BTC"
    assert out["metadata"]["mode_actual"] == "dry-run"


def test_synthesize_once_uses_latest_signal_fallback(isolated) -> None:
    _, signal_root = isolated
    path = signal_root / "2026-04-28" / "signals.jsonl"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(_signal()) + "\n", encoding="utf-8")
    out = ns.handle(
        {
            "action": "synthesize-once",
            "date": "2026-04-28",
            "symbol": "BTC",
            "timeframe": "1h",
        }
    )
    assert out["ok"] is True
    assert out["thesis"]["symbol"] == "BTC"


def test_synthesize_once_reports_missing_signal(isolated) -> None:
    out = ns.handle({"action": "synthesize-once", "symbol": "BTC"})
    assert out["ok"] is False
    assert "no signal" in out["reason"]


def test_latest_reads_rows(isolated) -> None:
    output_root, _ = isolated
    path = output_root / "2026-04-28" / "theses.jsonl"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({"symbol": "BTC", "timeframe": "1h"}) + "\n", encoding="utf-8")
    out = ns.handle({"action": "latest", "date": "2026-04-28"})
    assert out["ok"] is True
    assert out["count"] == 1


def test_history_filters_symbol_and_timeframe(isolated) -> None:
    output_root, _ = isolated
    path = output_root / "2026-04-28" / "theses.jsonl"
    path.parent.mkdir(parents=True)
    rows = [
        {"symbol": "BTC", "timeframe": "1h"},
        {"symbol": "ETH", "timeframe": "1h"},
    ]
    path.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")
    out = ns.handle({"action": "history", "date": "2026-04-28", "symbol": "BTC", "timeframe": "1h"})
    assert out["count"] == 1
    assert out["rows"][0]["symbol"] == "BTC"


def test_rubric_score_action(isolated) -> None:
    thesis = ns.handle({"action": "synthesize-once", "signal": _signal()})["thesis"]
    out = ns.handle({"action": "rubric-score", "thesis": thesis, "signal": _signal()})
    assert out["ok"] is True
    assert out["rubric"]["publishable"] is True


def test_rubric_score_requires_thesis(isolated) -> None:
    out = ns.handle({"action": "rubric-score"})
    assert out["ok"] is False
    assert "thesis" in out["error"]


def test_status_action(isolated) -> None:
    out = ns.handle({"action": "status"})
    assert out["ok"] is True
    assert "synthesize-once" in out["actions"]


def test_unknown_action(isolated) -> None:
    out = ns.handle({"action": "wat"})
    assert "valid_actions" in out


def test_main_reads_stdin_and_writes_json(isolated) -> None:
    out_buf = io.StringIO()
    rc = ns.main(
        stream_in=io.StringIO(json.dumps({"action": "synthesize-once", "signal": _signal()})),
        stream_out=out_buf,
    )
    assert rc == 0
    assert json.loads(out_buf.getvalue())["ok"] is True


def test_main_rejects_invalid_json(isolated) -> None:
    out_buf = io.StringIO()
    rc = ns.main(stream_in=io.StringIO("{"), stream_out=out_buf)
    assert rc == 2
    assert "invalid JSON" in out_buf.getvalue()


def test_main_rejects_non_object(isolated) -> None:
    out_buf = io.StringIO()
    rc = ns.main(stream_in=io.StringIO("[]"), stream_out=out_buf)
    assert rc == 2
