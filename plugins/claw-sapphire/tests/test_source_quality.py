"""Tests for the source_quality plugin tool."""

from __future__ import annotations

import importlib.util
import io
import json
import sys
from pathlib import Path

TOOLS = Path(__file__).parent.parent / "tools"
ROOT = TOOLS.parents[2]
if str(ROOT) in sys.path:
    sys.path.remove(str(ROOT))
sys.path.insert(0, str(ROOT))

_spec = importlib.util.spec_from_file_location(
    "source_quality_tool",
    TOOLS / "internal" / "source_quality.py",
)
source_quality = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(source_quality)


def _seed_report(tmp_path: Path, payload: dict, *, report_date: str = "2026-04-29") -> Path:
    daily = tmp_path / report_date
    daily.mkdir(parents=True)
    report_path = daily / "report.json"
    report_path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
    return report_path


def _example_report() -> dict:
    return {
        "schema_version": 1,
        "report_date": "2026-04-29",
        "summary": {
            "sources_count": 1,
            "samples_total": 6,
            "near_duplicate_pairs": 0,
            "decayed_sources_count": 0,
        },
        "snr": {
            "alpha": {
                "source": "alpha",
                "samples": 6,
                "precision": 0.9,
                "recall": 0.85,
                "f1": 0.875,
                "true_positives": 5,
                "false_positives": 1,
                "true_negatives": 0,
                "false_negatives": 0,
                "low_sample": False,
                "notes": [],
                "window_start": "",
                "window_end": "",
            }
        },
        "correlation": {
            "sources": ["alpha"],
            "pairs": [],
            "near_duplicates": [],
            "bucket_minutes": 60,
            "min_overlap": 5,
            "near_duplicate_threshold": 0.87,
            "notes": [],
        },
        "near_duplicates": [],
        "decay": {
            "threshold": 0.15,
            "recent_days": 14,
            "window_hours": 24,
            "alerts": [],
            "decayed_sources": [],
            "notes": [],
        },
    }


def test_status_when_no_report_returns_has_report_false(tmp_path):
    response = source_quality.handle({"action": "status", "report_root": str(tmp_path)})

    assert response["has_report"] is False
    assert response["read_only"] is True
    assert response["daemon_version"] == "0.1.0"


def test_status_when_report_present(tmp_path):
    _seed_report(tmp_path, _example_report())

    response = source_quality.handle({"action": "status", "report_root": str(tmp_path)})

    assert response["has_report"] is True
    assert response["latest_report"].endswith("report.json")


def test_latest_report_returns_full_payload(tmp_path):
    _seed_report(tmp_path, _example_report())

    response = source_quality.handle({"action": "latest-report", "report_root": str(tmp_path)})

    assert response["status"] == "ok"
    assert response["report_date"] == "2026-04-29"
    assert "alpha" in response["snr"]


def test_snr_action_returns_only_snr_block(tmp_path):
    _seed_report(tmp_path, _example_report())

    response = source_quality.handle({"action": "snr", "report_root": str(tmp_path)})

    assert response["status"] == "ok"
    assert set(response["snr"].keys()) == {"alpha"}
    assert "decay" not in response


def test_near_duplicates_action_returns_empty_list_for_clean_report(tmp_path):
    _seed_report(tmp_path, _example_report())

    response = source_quality.handle({"action": "near-duplicates", "report_root": str(tmp_path)})

    assert response["status"] == "ok"
    assert response["near_duplicates"] == []


def test_decay_action_returns_decay_block(tmp_path):
    _seed_report(tmp_path, _example_report())

    response = source_quality.handle({"action": "decay", "report_root": str(tmp_path)})

    assert response["status"] == "ok"
    assert response["decay"]["alerts"] == []


def test_unknown_action_returns_error_with_valid_actions(tmp_path):
    response = source_quality.handle({"action": "rocket-launch", "report_root": str(tmp_path)})

    assert "error" in response
    assert "valid_actions" in response


def test_recompute_action_returns_memory_only_payload(tmp_path, monkeypatch):
    monkeypatch.setattr(source_quality, "DEFAULT_REPORT_ROOT", tmp_path)

    response = source_quality.handle({"action": "recompute", "report_root": str(tmp_path)})

    assert response["status"] == "ok"
    assert response.get("memory_only") is True


def test_recompute_with_write_blocked_unless_live_env(tmp_path, monkeypatch):
    monkeypatch.setenv("SAPPHIRE_SOURCE_QUALITY_LIVE", "1")

    response = source_quality.handle(
        {"action": "recompute", "write": True, "report_root": str(tmp_path)}
    )

    # Even with the live env flag, the plugin tool refuses to write —
    # the daemon is the only thing that does I/O.
    assert "error" in response
    assert "daemon" in response["error"]


def test_main_pipes_through_stdin_and_stdout(tmp_path):
    _seed_report(tmp_path, _example_report())
    stdin = io.StringIO(json.dumps({"action": "status", "report_root": str(tmp_path)}))
    stdout = io.StringIO()

    rc = source_quality.main(stream_in=stdin, stream_out=stdout)

    assert rc == 0
    payload = json.loads(stdout.getvalue())
    assert payload["has_report"] is True


def test_main_errors_on_invalid_json():
    stdin = io.StringIO("{not json")
    stdout = io.StringIO()

    rc = source_quality.main(stream_in=stdin, stream_out=stdout)

    assert rc == 2
    payload = json.loads(stdout.getvalue())
    assert "error" in payload


def test_main_errors_on_non_object_payload():
    stdin = io.StringIO("[1,2,3]")
    stdout = io.StringIO()

    rc = source_quality.main(stream_in=stdin, stream_out=stdout)

    assert rc == 2
    payload = json.loads(stdout.getvalue())
    assert "error" in payload
