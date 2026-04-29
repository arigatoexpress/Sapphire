"""Tests for the Sapphire walkforward plugin tool.

Imports the internal module directly (mirrors the cross_asset_intel test
pattern). All test runs use the deterministic synthetic OHLCV path —
no live data, no filesystem reads against ``data/cross_asset/``.
"""

from __future__ import annotations

import importlib.util
import io
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

INTERNAL = ROOT / "plugins" / "claw-sapphire" / "tools" / "internal" / "walkforward.py"

_spec = importlib.util.spec_from_file_location("walkforward_internal", INTERNAL)
assert _spec is not None and _spec.loader is not None
wf = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = wf
_spec.loader.exec_module(wf)


def test_status_action_is_pure_no_io() -> None:
    out = wf.status_action()
    assert out["ok"] is True
    assert out["version"] == "0.1.0"
    assert "RegimeAwareRSI" in out["known_strategies"]
    assert out["caps"]["min_train_bars"] == 60
    assert out["caps"]["min_test_bars"] == 20


def test_run_action_produces_walkforward_result_dict() -> None:
    out = wf.handle(
        {
            "action": "run",
            "strategy": "RegimeAwareRSI",
            "n_bars": 200,
            "train": 60,
            "test": 20,
        }
    )
    assert out["ok"] is True
    assert out["strategy"] == "RegimeAwareRSI"
    result = out["result"]
    assert result["strategy_cls"] == "RegimeAwareRSI"
    assert result["n_windows"] > 0
    # JSON-serializable end-to-end
    json.dumps(out)


def test_run_action_rejects_unknown_strategy() -> None:
    out = wf.handle({"action": "run", "strategy": "DoesNotExist"})
    assert "error" in out
    assert "valid_actions" in out


def test_run_action_rejects_too_short_train() -> None:
    out = wf.handle({"action": "run", "strategy": "RegimeAwareRSI", "train": 30, "test": 20})
    assert "error" in out


def test_decompose_action_returns_buckets() -> None:
    out = wf.handle(
        {
            "action": "decompose",
            "strategy": "RegimeAwareRSI",
            "n_bars": 200,
            "train": 60,
            "test": 20,
            "labels": {"2025-01-01": "risk_on", "2025-04-01": "risk_off"},
        }
    )
    assert out["ok"] is True
    decomp = out["decomposition"]
    assert "buckets" in decomp
    assert "distribution" in decomp


def test_decompose_action_rejects_non_object_labels() -> None:
    out = wf.handle(
        {
            "action": "decompose",
            "strategy": "RegimeAwareRSI",
            "n_bars": 200,
            "labels": [{"a": "b"}],
        }
    )
    assert "error" in out


def test_deflated_action_returns_dsr_block() -> None:
    out = wf.handle(
        {
            "action": "deflated",
            "strategy": "RegimeAwareRSI",
            "n_bars": 200,
            "train": 60,
            "test": 20,
        }
    )
    assert out["ok"] is True
    dsr = out["deflated_sharpe"]
    assert "deflated_sharpe" in dsr
    assert "n_windows" in dsr


def test_latest_action_handles_missing_root(tmp_path: Path) -> None:
    out = wf.handle({"action": "latest", "output_root": str(tmp_path / "nonexistent")})
    assert out["ok"] is False
    assert "no walk-forward artifacts" in out["error"]


def test_latest_action_reads_real_manifest(tmp_path: Path) -> None:
    day_dir = tmp_path / "2026-04-29"
    day_dir.mkdir()
    manifest = {"version": "0.1.0", "artifacts": [{"strategy": "RegimeAwareRSI"}]}
    (day_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    out = wf.handle({"action": "latest", "output_root": str(tmp_path)})
    assert out["ok"] is True
    assert out["date"] == "2026-04-29"
    assert out["manifest"]["version"] == "0.1.0"


def test_unknown_action_returns_valid_actions() -> None:
    out = wf.handle({"action": "wat"})
    assert "error" in out
    assert "run" in out["valid_actions"]
    assert "status" in out["valid_actions"]


def test_main_reads_stdin_writes_json_object() -> None:
    out_buf = io.StringIO()
    rc = wf.main(stream_in=io.StringIO(json.dumps({"action": "status"})), stream_out=out_buf)
    assert rc == 0
    parsed = json.loads(out_buf.getvalue())
    assert parsed["ok"] is True
    assert "valid_actions" in parsed


def test_main_rejects_invalid_json() -> None:
    out_buf = io.StringIO()
    rc = wf.main(stream_in=io.StringIO("{not"), stream_out=out_buf)
    assert rc == 2


def test_main_rejects_non_object() -> None:
    out_buf = io.StringIO()
    rc = wf.main(stream_in=io.StringIO("[1,2]"), stream_out=out_buf)
    assert rc == 2


def test_main_returns_1_on_handler_error() -> None:
    out_buf = io.StringIO()
    rc = wf.main(stream_in=io.StringIO('{"action":"unknown"}'), stream_out=out_buf)
    assert rc == 1
