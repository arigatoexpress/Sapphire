"""Tests for the narrative_eval plugin tool."""

from __future__ import annotations

import importlib.util
import io
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

INTERNAL = ROOT / "plugins" / "claw-sapphire" / "tools" / "internal" / "narrative_eval.py"

_spec = importlib.util.spec_from_file_location("narrative_eval_internal", INTERNAL)
assert _spec is not None and _spec.loader is not None
ne = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = ne
_spec.loader.exec_module(ne)


def _thesis() -> dict:
    return {
        "symbol": "BTC",
        "timeframe": "1h",
        "generated_at": "2026-04-27T12:00:00+00:00",
        "implied_position": "long_mild",
        "confidence": 0.7,
    }


def _outcome() -> dict:
    return {
        "symbol": "BTC",
        "timeframe": "1h",
        "observed_at": "2026-04-28T12:00:00+00:00",
        "actual_return_pct": 1.2,
    }


def test_score_thesis_action() -> None:
    out = ne.handle(
        {
            "action": "score-thesis",
            "thesis": _thesis(),
            "outcome": _outcome(),
            "horizon_hours": 24,
        }
    )
    assert out["ok"] is True
    assert out["score"]["correct"] is True


def test_aggregates_action_accepts_inline_scores() -> None:
    score = ne.handle({"action": "score-thesis", "thesis": _thesis(), "outcome": _outcome()})[
        "score"
    ]
    out = ne.handle({"action": "aggregates", "scores": [score], "group_by": "symbol"})
    assert out["ok"] is True
    assert out["groups"]["BTC"]["scored"] == 1


def test_diagnostics_and_calibration_actions_accept_inline_scores() -> None:
    score = ne.handle(
        {
            "action": "score-thesis",
            "thesis": {**_thesis(), "implied_position": "short_mild", "confidence": 0.8},
            "outcome": _outcome(),
        }
    )["score"]
    assert ne.handle({"action": "diagnostics", "scores": [score]})["false_positives"]
    assert ne.handle({"action": "calibration", "scores": [score]})["overall"]["scored"] == 1


def test_status_action() -> None:
    out = ne.handle({"action": "status"})
    assert out["ok"] is True
    assert "score-thesis" in out["actions"]


def test_main_reads_stdin_and_writes_json() -> None:
    out_buf = io.StringIO()
    rc = ne.main(
        stream_in=io.StringIO(json.dumps({"action": "score-thesis", "thesis": _thesis()})),
        stream_out=out_buf,
    )
    assert rc == 0
    assert json.loads(out_buf.getvalue())["ok"] is True
