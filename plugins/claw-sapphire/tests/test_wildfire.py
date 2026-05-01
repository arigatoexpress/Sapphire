"""Tests for the wildfire-watch → Sapphire signal bridge.

Covers schema validation, JSONL persistence + idempotency, event_bus emit,
and the list/stats query surface.
"""

from __future__ import annotations

import importlib.util
import json
import sys
import uuid
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
sys.modules.pop("lib", None)

INTERNAL = ROOT / "plugins" / "claw-sapphire" / "tools" / "internal" / "wildfire.py"
_spec = importlib.util.spec_from_file_location("wildfire_internal", INTERNAL)
assert _spec is not None and _spec.loader is not None
wildfire = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = wildfire
_spec.loader.exec_module(wildfire)


@pytest.fixture
def isolated_paths(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Redirect signal + event JSONL writes into a tmp dir."""
    signals = tmp_path / "wildfire_signals.jsonl"
    events = tmp_path / "events" / "bus.jsonl"
    monkeypatch.setattr(wildfire, "SIGNALS_PATH", signals)
    monkeypatch.setattr(wildfire, "EVENTS_PATH", events)
    return tmp_path


def _make_signal(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "schema_version": "1.0.0",
        "signal_id": str(uuid.uuid4()),
        "drone_id": "wfw-unit01",
        "zone_id": "monterey-pinnacles-east",
        "timestamp": "2026-05-01T22:00:00+00:00",
        "coords": {
            "lat": 36.4906,
            "lon": -121.1825,
            "alt_agl_m": 80.0,
            "heading_deg": 270.0,
            "ground_speed_mps": 12.0,
        },
        "signal_type": "smoke",
        "confidence": 0.91,
        "evidence": {
            "frame_uris": ["gs://wildfire-watch-evidence/zone/2026-05-01/sig/frame_01.jpg"],
        },
        "risk_score": 78.0,
        "recommended_action": "notify_operator",
    }
    base.update(overrides)
    return base


def test_schema_info_action_returns_canonical_constants(isolated_paths: Path) -> None:
    result = wildfire.handle({"action": "schema_info"})
    assert result["ok"] is True
    assert result["schema_version"] == "1.0.0"
    assert "smoke" in result["signal_types"]
    assert "fire" in result["signal_types"]
    assert "notify_fire_dept" in result["recommended_actions"]


def test_ingest_persists_valid_signal_and_emits_event(isolated_paths: Path) -> None:
    signal = _make_signal()
    result = wildfire.handle({"action": "ingest", "signal": signal})
    assert result["ok"] is True
    assert result["duplicate"] is False
    assert result["signal_id"] == signal["signal_id"]
    assert result["priority"] in {"info", "elevated", "high", "critical"}

    rows = wildfire._load_signals()
    assert len(rows) == 1
    assert rows[0]["signal_id"] == signal["signal_id"]

    assert wildfire.EVENTS_PATH.exists()
    line = wildfire.EVENTS_PATH.read_text().strip()
    envelope = json.loads(line)
    assert envelope["type"] == "wildfire.signal.detected"
    assert envelope["tags"]["zone"] == signal["zone_id"]
    assert envelope["signal"]["signal_id"] == signal["signal_id"]


def test_ingest_idempotent_on_signal_id(isolated_paths: Path) -> None:
    signal = _make_signal()
    first = wildfire.handle({"action": "ingest", "signal": signal})
    second = wildfire.handle({"action": "ingest", "signal": signal})
    assert first["duplicate"] is False
    assert second["duplicate"] is True
    rows = wildfire._load_signals()
    assert len(rows) == 1


@pytest.mark.parametrize(
    "mutation,expected_fragment",
    [
        ({"signal_id": "not-a-uuid"}, "signal_id must be a valid UUID"),
        ({"drone_id": "bogus-id"}, "drone_id must match"),
        ({"signal_type": "explosion"}, "signal_type must be one of"),
        ({"recommended_action": "yeet"}, "recommended_action must be one of"),
        ({"confidence": 1.5}, "confidence must be a number in"),
        ({"risk_score": -3}, "risk_score must be a number in"),
        ({"coords": {"lat": 100, "lon": 0, "alt_agl_m": 50}}, "coords.lat"),
        ({"evidence": {"frame_uris": []}}, "frame_uris must be a non-empty array"),
        ({"schema_version": "0.9.0"}, "schema_version must be"),
    ],
)
def test_ingest_rejects_invalid_signals(
    isolated_paths: Path, mutation: dict[str, Any], expected_fragment: str
) -> None:
    signal = _make_signal(**mutation)
    result = wildfire.handle({"action": "ingest", "signal": signal})
    assert result["ok"] is False
    assert expected_fragment in result["error"]
    assert wildfire._load_signals() == []


def test_priority_for_fire_dept_recommendation_is_critical(isolated_paths: Path) -> None:
    signal = _make_signal(recommended_action="notify_fire_dept", risk_score=92, signal_type="fire")
    assert wildfire._priority_for(signal) == "critical"


def test_list_filters_zone_and_min_risk(isolated_paths: Path) -> None:
    sig_a = _make_signal(zone_id="zone-a", risk_score=90)
    sig_b = _make_signal(zone_id="zone-b", risk_score=20)
    sig_c = _make_signal(zone_id="zone-a", risk_score=10)
    for sig in (sig_a, sig_b, sig_c):
        wildfire.handle({"action": "ingest", "signal": sig})

    res = wildfire.handle({"action": "list", "zone_id": "zone-a", "min_risk": 50})
    assert res["count"] == 1
    assert res["signals"][0]["signal_id"] == sig_a["signal_id"]


def test_list_filters_signal_type(isolated_paths: Path) -> None:
    fire = _make_signal(signal_type="fire")
    smoke = _make_signal(signal_type="smoke")
    wildfire.handle({"action": "ingest", "signal": fire})
    wildfire.handle({"action": "ingest", "signal": smoke})

    res = wildfire.handle({"action": "list", "signal_type": "fire"})
    assert res["count"] == 1
    assert res["signals"][0]["signal_id"] == fire["signal_id"]


def test_stats_aggregates_by_zone_type_action_priority(isolated_paths: Path) -> None:
    signals = [
        _make_signal(zone_id="z1", signal_type="smoke", recommended_action="notify_operator", risk_score=60),
        _make_signal(zone_id="z1", signal_type="fire", recommended_action="notify_fire_dept", risk_score=95),
        _make_signal(zone_id="z2", signal_type="wildlife", recommended_action="log_only", risk_score=10),
    ]
    for sig in signals:
        wildfire.handle({"action": "ingest", "signal": sig})

    res = wildfire.handle({"action": "stats"})
    assert res["total"] == 3
    assert res["by_zone"] == {"z1": 2, "z2": 1}
    assert res["by_signal_type"] == {"smoke": 1, "fire": 1, "wildlife": 1}
    assert res["by_recommended_action"]["notify_fire_dept"] == 1
    assert res["by_priority"]["critical"] == 1
    assert res["max_risk_score"] == 95.0


def test_unknown_action_returns_error(isolated_paths: Path) -> None:
    result = wildfire.handle({"action": "demolish"})
    assert result["ok"] is False
    assert "unknown action" in result["error"]
    assert "ingest" in result["available_actions"]


def test_handle_with_no_action_defaults_to_schema_info(isolated_paths: Path) -> None:
    result = wildfire.handle({})
    assert result["ok"] is True
    assert result["schema_version"] == "1.0.0"
