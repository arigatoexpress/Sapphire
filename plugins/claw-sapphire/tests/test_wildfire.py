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
        _make_signal(
            zone_id="z1", signal_type="smoke", recommended_action="notify_operator", risk_score=60
        ),
        _make_signal(
            zone_id="z1", signal_type="fire", recommended_action="notify_fire_dept", risk_score=95
        ),
        _make_signal(
            zone_id="z2", signal_type="wildlife", recommended_action="log_only", risk_score=10
        ),
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


# ---------------------------------------------------------------------------
# Local situation monitor (public feeds)
# ---------------------------------------------------------------------------

HOME_LAT, HOME_LON = 36.4906, -121.1825


@pytest.fixture
def situation_paths(isolated_paths: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Redirect config, cache, and briefs into tmp; stub all feeds to empty."""
    monkeypatch.setattr(wildfire, "CONFIG_PATH", isolated_paths / "wildfire_config.json")
    monkeypatch.setattr(
        wildfire, "SITUATION_CACHE_PATH", isolated_paths / "wildfire" / "situation_cache.json"
    )
    monkeypatch.setattr(wildfire, "BRIEFS_DIR", isolated_paths / "wildfire" / "briefs")
    monkeypatch.setitem(wildfire.FEED_FETCHERS, "nws_alerts", lambda *a: [])
    monkeypatch.setitem(wildfire.FEED_FETCHERS, "nifc_incidents", lambda *a: [])
    monkeypatch.setitem(wildfire.FEED_FETCHERS, "firms_hotspots", lambda *a: [])
    return isolated_paths


def _alert(event: str = "Red Flag Warning") -> dict[str, Any]:
    return {
        "event": event,
        "headline": event,
        "severity": "Severe",
        "area": "Test Zone",
        "onset": None,
        "ends": None,
    }


def _incident(distance_km: float, name: str = "Test Fire") -> dict[str, Any]:
    return {
        "name": name,
        "acres": 120.0,
        "percent_contained": 10,
        "category": "WF",
        "county": "Test",
        "state": "US-CA",
        "discovered": "2026-07-01T00:00:00+00:00",
        "lat": HOME_LAT,
        "lon": HOME_LON,
        "distance_km": distance_km,
    }


def _hotspot(distance_km: float) -> dict[str, Any]:
    return {
        "lat": HOME_LAT,
        "lon": HOME_LON,
        "distance_km": distance_km,
        "frp_mw": "4.2",
        "confidence": "n",
        "acq_date": "2026-07-03",
        "acq_time": "0900",
    }


@pytest.mark.parametrize(
    "alerts,incidents,hotspots,expected",
    [
        ([], [], [], "none"),
        ([_alert("Fire Weather Watch")], [], [], "elevated"),
        ([_alert()], [], [], "high"),
        ([], [_incident(60.0)], [], "elevated"),
        ([], [_incident(39.0)], [], "high"),
        ([], [_incident(14.0)], [], "critical"),
        ([], [], [_hotspot(9.0)], "critical"),
        ([], [], [_hotspot(30.0)], "elevated"),
        ([_alert()], [_incident(35.0)], [], "critical"),
        ([_alert("Evacuation - Immediate")], [], [], "critical"),
    ],
)
def test_situation_level_policy(
    alerts: list[dict[str, Any]],
    incidents: list[dict[str, Any]],
    hotspots: list[dict[str, Any]],
    expected: str,
) -> None:
    assert wildfire._situation_level(alerts, incidents, hotspots) == expected


def test_situation_fetches_and_emits_event(
    situation_paths: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setitem(wildfire.FEED_FETCHERS, "nws_alerts", lambda *a: [_alert()])
    monkeypatch.setitem(wildfire.FEED_FETCHERS, "nifc_incidents", lambda *a: [_incident(12.0)])
    result = wildfire.handle({"action": "situation"})
    assert result["ok"] is True
    assert result["cached"] is False
    assert result["situation"]["level"] == "critical"
    assert wildfire.SITUATION_CACHE_PATH.exists()

    envelope = json.loads(wildfire.EVENTS_PATH.read_text().strip())
    assert envelope["type"] == "wildfire.situation.updated"
    assert envelope["tags"]["priority"] == "critical"
    assert envelope["summary"]["nearest_incident_km"] == 12.0


def test_situation_uses_fresh_cache(situation_paths: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    wildfire.handle({"action": "situation"})
    calls = {"n": 0}

    def counting_fetch(*a: Any) -> list[dict[str, Any]]:
        calls["n"] += 1
        return []

    monkeypatch.setitem(wildfire.FEED_FETCHERS, "nws_alerts", counting_fetch)
    result = wildfire.handle({"action": "situation"})
    assert result["cached"] is True
    assert calls["n"] == 0

    refreshed = wildfire.handle({"action": "situation", "refresh": True})
    assert refreshed["cached"] is False
    assert calls["n"] == 1


def test_situation_degrades_to_stale_cache_when_all_feeds_fail(
    situation_paths: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    wildfire.handle({"action": "situation"})

    def boom(*a: Any) -> list[dict[str, Any]]:
        raise OSError("network down")

    for feed in wildfire.FEED_FETCHERS:
        monkeypatch.setitem(wildfire.FEED_FETCHERS, feed, boom)
    result = wildfire.handle({"action": "situation", "refresh": True})
    assert result["ok"] is True
    assert result.get("stale") is True
    assert "nws_alerts" in result["feed_errors"]
    assert result["situation"]["level"] == "none"


def test_single_feed_failure_is_isolated(
    situation_paths: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def boom(*a: Any) -> list[dict[str, Any]]:
        raise OSError("nifc down")

    monkeypatch.setitem(wildfire.FEED_FETCHERS, "nifc_incidents", boom)
    monkeypatch.setitem(wildfire.FEED_FETCHERS, "nws_alerts", lambda *a: [_alert()])
    result = wildfire.handle({"action": "situation"})
    assert result["ok"] is True
    assert result["situation"]["level"] == "high"
    assert "nifc_incidents" in result["situation"]["feed_errors"]


def test_config_get_returns_defaults_and_set_roundtrips(situation_paths: Path) -> None:
    got = wildfire.handle({"action": "config"})
    assert got["ok"] is True
    assert "Phase-0 default" in got["config"]["home"]["label"]

    updated = wildfire.handle(
        {
            "action": "config",
            "set": {"home": {"lat": 39.0, "lon": -105.0, "label": "home"}, "radius_km": 50},
        }
    )
    assert updated["ok"] is True
    reread = wildfire.handle({"action": "config"})
    assert reread["config"]["home"]["lat"] == 39.0
    assert reread["config"]["radius_km"] == 50.0


@pytest.mark.parametrize(
    "bad_set",
    [
        {"home": {"lat": 99, "lon": 0}},
        {"home": {"lat": "x", "lon": 0}},
        {"radius_km": -5},
        {"cache_ttl_minutes": 0},
    ],
)
def test_config_rejects_invalid_values(situation_paths: Path, bad_set: dict[str, Any]) -> None:
    result = wildfire.handle({"action": "config", "set": bad_set})
    assert result["ok"] is False


def test_fire_dept_brief_writes_draft_and_never_sends(
    situation_paths: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setitem(wildfire.FEED_FETCHERS, "nifc_incidents", lambda *a: [_incident(22.5)])
    result = wildfire.handle({"action": "fire_dept_brief"})
    assert result["ok"] is True
    brief_path = Path(result["path"])
    assert brief_path.exists()
    text = brief_path.read_text()
    assert "Wildfire Situation Brief" in text
    assert "Test Fire" in text
    assert "22.5 km" in text
    assert "Informational only" in text
    assert "never contacts anyone" in result["note"]


def test_normalize_nws_payload_filters_fire_events() -> None:
    payload = {
        "features": [
            {
                "properties": {
                    "event": "Red Flag Warning",
                    "areaDesc": "West Slope",
                    "severity": "Severe",
                }
            },
            {"properties": {"event": "Severe Thunderstorm Warning", "areaDesc": "Elsewhere"}},
        ]
    }
    alerts = wildfire._normalize_nws_payload(payload)
    assert len(alerts) == 1
    assert alerts[0]["event"] == "Red Flag Warning"
    assert alerts[0]["area"] == "West Slope"


def test_normalize_nifc_payload_annotates_distance_and_filters_radius() -> None:
    payload = {
        "features": [
            {
                "attributes": {
                    "IncidentName": "Near Fire",
                    "IncidentSize": 50.0,
                    "PercentContained": 25,
                    "FireDiscoveryDateTime": 1783036000000,
                },
                "geometry": {"y": HOME_LAT + 0.1, "x": HOME_LON},
            },
            {
                "attributes": {"IncidentName": "Far Fire"},
                "geometry": {"y": HOME_LAT + 5.0, "x": HOME_LON},
            },
        ]
    }
    incidents = wildfire._normalize_nifc_payload(payload, HOME_LAT, HOME_LON, 80.0)
    assert [i["name"] for i in incidents] == ["Near Fire"]
    assert 10 < incidents[0]["distance_km"] < 13
    assert incidents[0]["discovered"].startswith("2026-07-0")


def test_parse_firms_csv_filters_radius_and_sorts() -> None:
    csv_text = (
        "latitude,longitude,bright_ti4,acq_date,acq_time,confidence,frp\n"
        f"{HOME_LAT + 0.2},{HOME_LON},330.1,2026-07-03,0912,n,5.5\n"
        f"{HOME_LAT + 0.05},{HOME_LON},345.0,2026-07-03,0912,h,12.1\n"
        f"{HOME_LAT + 9.0},{HOME_LON},300.0,2026-07-03,0912,l,1.0\n"
    )
    hotspots = wildfire._parse_firms_csv(csv_text, HOME_LAT, HOME_LON, 80.0)
    assert len(hotspots) == 2
    assert hotspots[0]["distance_km"] < hotspots[1]["distance_km"]
    assert hotspots[0]["frp_mw"] == "12.1"


def test_firms_fetch_returns_empty_without_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("FIRMS_MAP_KEY", raising=False)
    assert wildfire._fetch_firms_hotspots(HOME_LAT, HOME_LON, 80.0) == []
