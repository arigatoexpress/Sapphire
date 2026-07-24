#!/usr/bin/env python3
"""Wildfire-watch signal ingester for Sapphire.

Bridges the wildfire-watch drone fleet (~/Code/wildfire-watch) to the Sapphire
intelligence mesh. Validates incoming wildfire_signal payloads against the
v1 schema, appends them to data/wildfire_signals.jsonl, and emits an
event_bus event for downstream consumers (dashboard SSE, Telegram alerts via
hermes-agent, weekly content engine).

Read-only-query actions are also exposed (`list`, `stats`) so the dashboard
and operator console can surface recent signals without re-running the
ingestion path.

Beyond the drone bridge, the tool monitors the *local* fire situation from
free public feeds — NWS fire-weather alerts (api.weather.gov, no key) and
NIFC/WFIGS live wildfire incidents (public ArcGIS), plus optional NASA FIRMS
satellite hotspots when FIRMS_MAP_KEY is set. The `situation` action fuses
them into a single leveled picture around the configured home location, and
`fire_dept_brief` renders a public-safe markdown brief for the local fire
department (draft on disk only — a human sends it).

Usage (stdin JSON):
    echo '{"action":"ingest","signal":{...}}' | python3 wildfire.py
    echo '{"action":"list","limit":10,"min_risk":50}' | python3 wildfire.py
    echo '{"action":"stats","since_hours":24}' | python3 wildfire.py
    echo '{"action":"situation"}' | python3 wildfire.py
    echo '{"action":"situation","refresh":true}' | python3 wildfire.py
    echo '{"action":"fire_dept_brief"}' | python3 wildfire.py
    echo '{"action":"config","set":{"home":{"lat":39.0,"lon":-105.0,"label":"home"}}}' | python3 wildfire.py

Schema source of truth:
    ~/Code/wildfire-watch/sapphire_integration/wildfire_signal_schema.json

Design constraints:
- Stateless. All persistent state lives in data/wildfire_signals.jsonl.
- Idempotent on signal_id (re-ingesting the same UUID is a no-op).
- Inert when wildfire-watch repo is absent: validation falls back to a
  minimal in-process schema so the tool still works for tests.
- Never sends Telegram directly. recommended_action="notify_fire_dept"
  surfaces in stats and the event_bus event; the operator-supervised
  hermes skill (sapphire/wildfire-alert) is what actually pages. The same
  rule holds for public-feed escalation: `situation` only emits a
  wildfire.situation.updated bus event — no outward sends, ever.
- Public-feed fetchers are module-level and injectable; tests monkeypatch
  them so the suite never touches the network.
"""

from __future__ import annotations

import json
import math
import os
import ssl
import sys
import urllib.parse
import urllib.request
import uuid
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

SAPPHIRE_DIR = Path.home() / "Code" / "Sapphire"
SIGNALS_PATH = SAPPHIRE_DIR / "data" / "wildfire_signals.jsonl"
EVENTS_PATH = SAPPHIRE_DIR / "data" / "events" / "bus.jsonl"
WILDFIRE_REPO = Path.home() / "Code" / "wildfire-watch"
SCHEMA_PATH = WILDFIRE_REPO / "sapphire_integration" / "wildfire_signal_schema.json"

SCHEMA_VERSION = "1.0.0"
SIGNAL_TYPES = {"smoke", "fire", "thermal_anomaly", "wildlife", "anomaly", "system_event"}
RECOMMENDED_ACTIONS = {
    "log_only",
    "notify_operator",
    "notify_fire_dept",
    "loiter_and_capture",
    "rtl",
}


def _utcnow_iso() -> str:
    return datetime.now(UTC).isoformat()


def _ensure_dirs() -> None:
    SIGNALS_PATH.parent.mkdir(parents=True, exist_ok=True)
    EVENTS_PATH.parent.mkdir(parents=True, exist_ok=True)


def _load_signals() -> list[dict[str, Any]]:
    if not SIGNALS_PATH.exists():
        return []
    rows: list[dict[str, Any]] = []
    with SIGNALS_PATH.open() as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return rows


def _validate(signal: dict[str, Any]) -> tuple[bool, str | None]:
    """Minimal in-process validation of the v1 wildfire_signal schema.

    Doesn't pull jsonschema as a dep — Sapphire keeps test deps lean. Mirrors
    the `required` list and the constrained enums from the canonical schema
    at WILDFIRE_REPO/sapphire_integration/wildfire_signal_schema.json.
    """

    if not isinstance(signal, dict):
        return False, "signal must be an object"

    required = [
        "signal_id",
        "drone_id",
        "zone_id",
        "timestamp",
        "coords",
        "signal_type",
        "confidence",
        "evidence",
        "risk_score",
        "recommended_action",
        "schema_version",
    ]
    for key in required:
        if key not in signal:
            return False, f"missing required field: {key}"

    if signal.get("schema_version") != SCHEMA_VERSION:
        return False, f"schema_version must be {SCHEMA_VERSION}"

    sid = signal.get("signal_id", "")
    try:
        uuid.UUID(str(sid))
    except (ValueError, TypeError):
        return False, f"signal_id must be a valid UUID: {sid!r}"

    drone_id = str(signal.get("drone_id", ""))
    if not drone_id.startswith("wfw-") or len(drone_id) > 20:
        return False, f"drone_id must match ^wfw-[a-z0-9]{{4,16}}$ : {drone_id!r}"

    if signal.get("signal_type") not in SIGNAL_TYPES:
        return False, f"signal_type must be one of {sorted(SIGNAL_TYPES)}"

    if signal.get("recommended_action") not in RECOMMENDED_ACTIONS:
        return False, f"recommended_action must be one of {sorted(RECOMMENDED_ACTIONS)}"

    confidence = signal.get("confidence")
    if not isinstance(confidence, int | float) or not 0 <= confidence <= 1:
        return False, "confidence must be a number in [0, 1]"

    risk_score = signal.get("risk_score")
    if not isinstance(risk_score, int | float) or not 0 <= risk_score <= 100:
        return False, "risk_score must be a number in [0, 100]"

    coords = signal.get("coords") or {}
    if not isinstance(coords, dict):
        return False, "coords must be an object"
    for axis in ("lat", "lon", "alt_agl_m"):
        if axis not in coords:
            return False, f"coords.{axis} is required"
    lat, lon = coords.get("lat"), coords.get("lon")
    if not (isinstance(lat, int | float) and -90 <= lat <= 90):
        return False, "coords.lat must be in [-90, 90]"
    if not (isinstance(lon, int | float) and -180 <= lon <= 180):
        return False, "coords.lon must be in [-180, 180]"

    evidence = signal.get("evidence") or {}
    if not isinstance(evidence, dict):
        return False, "evidence must be an object"
    frame_uris = evidence.get("frame_uris")
    if not isinstance(frame_uris, list) or not frame_uris:
        return False, "evidence.frame_uris must be a non-empty array"

    return True, None


def _emit_event(signal: dict[str, Any]) -> None:
    """Append an event_bus envelope so dashboard SSE + content engine see it.

    Mirrors the `data/events/bus.jsonl` JSONL fallback pattern that the
    primary Redis Streams bus degrades to. Never raises.
    """

    try:
        envelope = {
            "ts": _utcnow_iso(),
            "type": "wildfire.signal.detected",
            "tags": {
                "service": "wildfire-watch",
                "device": signal.get("drone_id"),
                "zone": signal.get("zone_id"),
                "signal_type": signal.get("signal_type"),
                "priority": _priority_for(signal),
            },
            "signal": {
                "signal_id": signal.get("signal_id"),
                "risk_score": signal.get("risk_score"),
                "confidence": signal.get("confidence"),
                "recommended_action": signal.get("recommended_action"),
                "coords": signal.get("coords"),
            },
        }
        _ensure_dirs()
        with EVENTS_PATH.open("a") as fh:
            fh.write(json.dumps(envelope, separators=(",", ":")) + "\n")
    except OSError:
        pass


def _priority_for(signal: dict[str, Any]) -> str:
    risk = signal.get("risk_score") or 0
    action = signal.get("recommended_action") or "log_only"
    if action == "notify_fire_dept" or risk >= 80:
        return "critical"
    if action in ("loiter_and_capture", "notify_operator") or risk >= 50:
        return "high"
    if signal.get("signal_type") in ("fire", "smoke", "thermal_anomaly"):
        return "elevated"
    return "info"


def _action_ingest(payload: dict[str, Any]) -> dict[str, Any]:
    signal = payload.get("signal")
    if not isinstance(signal, dict):
        return {"ok": False, "error": "payload.signal must be an object"}

    ok, err = _validate(signal)
    if not ok:
        return {"ok": False, "error": err}

    sid = signal["signal_id"]
    existing = {row.get("signal_id") for row in _load_signals()}
    if sid in existing:
        return {"ok": True, "signal_id": sid, "duplicate": True}

    _ensure_dirs()
    with SIGNALS_PATH.open("a") as fh:
        fh.write(json.dumps(signal, separators=(",", ":")) + "\n")

    _emit_event(signal)

    return {
        "ok": True,
        "signal_id": sid,
        "duplicate": False,
        "priority": _priority_for(signal),
        "persisted_to": str(SIGNALS_PATH),
    }


def _action_list(payload: dict[str, Any]) -> dict[str, Any]:
    rows = _load_signals()
    zone = payload.get("zone_id")
    min_risk = payload.get("min_risk")
    signal_type = payload.get("signal_type")
    since_hours = payload.get("since_hours")
    limit = int(payload.get("limit") or 50)

    filtered = []
    cutoff: datetime | None = None
    if since_hours is not None:
        cutoff = datetime.now(UTC) - timedelta(hours=float(since_hours))
    for row in rows:
        if zone and row.get("zone_id") != zone:
            continue
        if signal_type and row.get("signal_type") != signal_type:
            continue
        if min_risk is not None and (row.get("risk_score") or 0) < float(min_risk):
            continue
        if cutoff is not None:
            ts = row.get("timestamp")
            try:
                ts_dt = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
            except (TypeError, ValueError):
                continue
            if ts_dt.tzinfo is None:
                ts_dt = ts_dt.replace(tzinfo=UTC)
            if ts_dt < cutoff:
                continue
        filtered.append(row)

    filtered.sort(key=lambda r: r.get("timestamp") or "", reverse=True)
    return {"ok": True, "count": len(filtered), "signals": filtered[:limit]}


def _action_stats(payload: dict[str, Any]) -> dict[str, Any]:
    rows = _load_signals()
    since_hours = payload.get("since_hours")
    if since_hours is not None:
        cutoff = datetime.now(UTC) - timedelta(hours=float(since_hours))
        windowed = []
        for row in rows:
            try:
                ts_dt = datetime.fromisoformat(str(row.get("timestamp")).replace("Z", "+00:00"))
            except (TypeError, ValueError):
                continue
            if ts_dt.tzinfo is None:
                ts_dt = ts_dt.replace(tzinfo=UTC)
            if ts_dt >= cutoff:
                windowed.append(row)
        rows = windowed

    by_zone: dict[str, int] = {}
    by_type: dict[str, int] = {}
    by_action: dict[str, int] = {}
    by_priority: dict[str, int] = {}
    max_risk = 0.0
    for row in rows:
        by_zone[row.get("zone_id", "unknown")] = by_zone.get(row.get("zone_id", "unknown"), 0) + 1
        by_type[row.get("signal_type", "unknown")] = (
            by_type.get(row.get("signal_type", "unknown"), 0) + 1
        )
        by_action[row.get("recommended_action", "unknown")] = (
            by_action.get(row.get("recommended_action", "unknown"), 0) + 1
        )
        prio = _priority_for(row)
        by_priority[prio] = by_priority.get(prio, 0) + 1
        max_risk = max(max_risk, float(row.get("risk_score") or 0))

    return {
        "ok": True,
        "total": len(rows),
        "by_zone": by_zone,
        "by_signal_type": by_type,
        "by_recommended_action": by_action,
        "by_priority": by_priority,
        "max_risk_score": max_risk,
        "as_of": _utcnow_iso(),
    }


def _action_schema_info(_: dict[str, Any]) -> dict[str, Any]:
    info: dict[str, Any] = {
        "ok": True,
        "schema_version": SCHEMA_VERSION,
        "schema_path": str(SCHEMA_PATH),
        "schema_present": SCHEMA_PATH.exists(),
        "signal_types": sorted(SIGNAL_TYPES),
        "recommended_actions": sorted(RECOMMENDED_ACTIONS),
        "signals_path": str(SIGNALS_PATH),
        "events_path": str(EVENTS_PATH),
    }
    return info


# ---------------------------------------------------------------------------
# Local situation monitor — public feeds (NWS + NIFC, optional NASA FIRMS)
# ---------------------------------------------------------------------------

CONFIG_PATH = SAPPHIRE_DIR / "data" / "wildfire_config.json"
SITUATION_CACHE_PATH = SAPPHIRE_DIR / "data" / "wildfire" / "situation_cache.json"
BRIEFS_DIR = SAPPHIRE_DIR / "data" / "wildfire" / "briefs"

DEFAULT_CONFIG: dict[str, Any] = {
    "home": {
        "lat": 36.4906,
        "lon": -121.1825,
        "label": "monterey-pinnacles-east (Phase-0 default — set your real location via the config action)",
    },
    "radius_km": 80.0,
    "cache_ttl_minutes": 15.0,
}

# NWS event names that matter for fire situational awareness.
FIRE_ALERT_EVENTS = {
    "Red Flag Warning",
    "Fire Weather Watch",
    "Fire Warning",
    "Extreme Fire Danger",
    "Evacuation - Immediate",
}

NWS_ALERTS_URL = "https://api.weather.gov/alerts/active?point={lat:.4f},{lon:.4f}"
NIFC_INCIDENTS_URL = (
    "https://services3.arcgis.com/T4QMspbfLg3qTGWY/arcgis/rest/services/"
    "WFIGS_Incident_Locations_Current/FeatureServer/0/query"
)
FIRMS_AREA_URL = (
    "https://firms.modaps.eosdis.nasa.gov/api/area/csv/{key}/VIIRS_SNPP_NRT/"
    "{west:.3f},{south:.3f},{east:.3f},{north:.3f}/2"
)
_HTTP_TIMEOUT_S = 20
_USER_AGENT = "sapphire-wildfire-watch (github.com/arigatoexpress/Sapphire)"


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = math.radians(lat2 - lat1), math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def _load_config() -> dict[str, Any]:
    cfg = json.loads(json.dumps(DEFAULT_CONFIG))  # deep copy
    if CONFIG_PATH.exists():
        try:
            stored = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return cfg
        if isinstance(stored, dict):
            home = stored.get("home")
            if isinstance(home, dict) and "lat" in home and "lon" in home:
                cfg["home"] = home
            for key in ("radius_km", "cache_ttl_minutes"):
                if isinstance(stored.get(key), int | float):
                    cfg[key] = float(stored[key])
    return cfg


def _ssl_context() -> ssl.SSLContext:
    # macOS framework Pythons often lack system root certs; prefer certifi's bundle.
    try:
        import certifi

        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        return ssl.create_default_context()


def _http_get(url: str) -> str:
    req = urllib.request.Request(
        url, headers={"User-Agent": _USER_AGENT, "Accept": "application/json, text/csv"}
    )
    with urllib.request.urlopen(req, timeout=_HTTP_TIMEOUT_S, context=_ssl_context()) as resp:  # noqa: S310
        return resp.read().decode("utf-8", errors="replace")


def _normalize_nws_payload(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Normalize an api.weather.gov active-alerts payload to fire-relevant rows."""
    alerts: list[dict[str, Any]] = []
    for feature in payload.get("features") or []:
        props = feature.get("properties") or {}
        event = props.get("event") or ""
        if event not in FIRE_ALERT_EVENTS:
            continue
        alerts.append(
            {
                "event": event,
                "headline": props.get("headline"),
                "severity": props.get("severity"),
                "area": props.get("areaDesc"),
                "onset": props.get("onset"),
                "ends": props.get("ends") or props.get("expires"),
            }
        )
    return alerts


def _normalize_nifc_payload(
    payload: dict[str, Any], lat: float, lon: float, radius_km: float
) -> list[dict[str, Any]]:
    """Normalize a WFIGS current-incidents ArcGIS payload to distance-annotated rows."""
    incidents: list[dict[str, Any]] = []
    for feature in payload.get("features") or []:
        attrs = feature.get("attributes") or {}
        geom = feature.get("geometry") or {}
        ilat, ilon = geom.get("y"), geom.get("x")
        if not isinstance(ilat, int | float) or not isinstance(ilon, int | float):
            continue
        distance_km = _haversine_km(lat, lon, ilat, ilon)
        if distance_km > radius_km:
            continue
        discovered = attrs.get("FireDiscoveryDateTime")
        if isinstance(discovered, int | float):  # ArcGIS epoch millis
            discovered = datetime.fromtimestamp(discovered / 1000, tz=UTC).isoformat()
        incidents.append(
            {
                "name": attrs.get("IncidentName") or "unnamed",
                "acres": attrs.get("IncidentSize") or attrs.get("DiscoveryAcres"),
                "percent_contained": attrs.get("PercentContained"),
                "category": attrs.get("IncidentTypeCategory"),
                "county": attrs.get("POOCounty"),
                "state": attrs.get("POOState"),
                "discovered": discovered,
                "lat": ilat,
                "lon": ilon,
                "distance_km": round(distance_km, 1),
            }
        )
    incidents.sort(key=lambda r: r["distance_km"])
    return incidents


def _parse_firms_csv(text: str, lat: float, lon: float, radius_km: float) -> list[dict[str, Any]]:
    """Parse a NASA FIRMS area CSV into distance-annotated hotspot rows."""
    lines = [ln for ln in text.strip().splitlines() if ln.strip()]
    if len(lines) < 2:
        return []
    header = [col.strip() for col in lines[0].split(",")]
    idx = {name: i for i, name in enumerate(header)}
    if "latitude" not in idx or "longitude" not in idx:
        return []
    hotspots: list[dict[str, Any]] = []
    for line in lines[1:]:
        cols = line.split(",")
        try:
            hlat, hlon = float(cols[idx["latitude"]]), float(cols[idx["longitude"]])
        except (ValueError, IndexError):
            continue
        distance_km = _haversine_km(lat, lon, hlat, hlon)
        if distance_km > radius_km:
            continue

        def _col(name: str, cols: list[str] = cols) -> str | None:
            i = idx.get(name)
            return cols[i].strip() if i is not None and i < len(cols) else None

        hotspots.append(
            {
                "lat": hlat,
                "lon": hlon,
                "distance_km": round(distance_km, 1),
                "frp_mw": _col("frp"),
                "confidence": _col("confidence"),
                "acq_date": _col("acq_date"),
                "acq_time": _col("acq_time"),
            }
        )
    hotspots.sort(key=lambda r: r["distance_km"])
    return hotspots


def _fetch_nws_alerts(lat: float, lon: float) -> list[dict[str, Any]]:
    url = NWS_ALERTS_URL.format(lat=lat, lon=lon)
    return _normalize_nws_payload(json.loads(_http_get(url)))


def _fetch_nifc_incidents(lat: float, lon: float, radius_km: float) -> list[dict[str, Any]]:
    deg = radius_km / 111.0  # ~1 degree latitude per 111 km; envelope is a coarse prefilter
    params = urllib.parse.urlencode(
        {
            "where": "1=1",
            "geometry": f"{lon - deg},{lat - deg},{lon + deg},{lat + deg}",
            "geometryType": "esriGeometryEnvelope",
            "inSR": "4326",
            "spatialRel": "esriSpatialRelIntersects",
            "outFields": (
                "IncidentName,IncidentSize,DiscoveryAcres,PercentContained,"
                "FireDiscoveryDateTime,IncidentTypeCategory,POOCounty,POOState"
            ),
            "returnGeometry": "true",
            "outSR": "4326",
            "f": "json",
        }
    )
    payload = json.loads(_http_get(f"{NIFC_INCIDENTS_URL}?{params}"))
    return _normalize_nifc_payload(payload, lat, lon, radius_km)


def _fetch_firms_hotspots(lat: float, lon: float, radius_km: float) -> list[dict[str, Any]]:
    """Optional satellite hotspots — needs a free FIRMS_MAP_KEY; [] when unset."""
    key = os.environ.get("FIRMS_MAP_KEY", "").strip()
    if not key:
        return []
    deg = radius_km / 111.0
    url = FIRMS_AREA_URL.format(
        key=key, west=lon - deg, south=lat - deg, east=lon + deg, north=lat + deg
    )
    return _parse_firms_csv(_http_get(url), lat, lon, radius_km)


# Escalation policy — the one knob that decides when the operator gets paged.
# Tuned conservative-out / sensitive-in: anything burning close to home is
# critical even without a weather flag; weather flags alone cap at "high".
def _situation_level(
    alerts: list[dict[str, Any]],
    incidents: list[dict[str, Any]],
    hotspots: list[dict[str, Any]],
) -> str:
    red_flag = any(a["event"] in ("Red Flag Warning", "Fire Warning") for a in alerts)
    evacuation = any(a["event"] == "Evacuation - Immediate" for a in alerts)
    nearest_incident = incidents[0]["distance_km"] if incidents else None
    nearest_hotspot = hotspots[0]["distance_km"] if hotspots else None

    if (
        evacuation
        or (nearest_incident is not None and nearest_incident <= 15)
        or (nearest_hotspot is not None and nearest_hotspot <= 10)
        or (red_flag and nearest_incident is not None and nearest_incident <= 40)
    ):
        return "critical"
    if red_flag or (nearest_incident is not None and nearest_incident <= 40):
        return "high"
    if alerts or incidents or hotspots:
        return "elevated"
    return "none"


_LEVEL_TO_PRIORITY = {
    "critical": "critical",
    "high": "high",
    "elevated": "elevated",
    "none": "info",
}

# Injectable feed registry — tests (or degraded environments) can swap these.
FEED_FETCHERS: dict[str, Callable[..., list[dict[str, Any]]]] = {
    "nws_alerts": _fetch_nws_alerts,
    "nifc_incidents": _fetch_nifc_incidents,
    "firms_hotspots": _fetch_firms_hotspots,
}


def _build_situation(cfg: dict[str, Any]) -> dict[str, Any]:
    home = cfg["home"]
    lat, lon, radius_km = float(home["lat"]), float(home["lon"]), float(cfg["radius_km"])
    feeds: dict[str, list[dict[str, Any]]] = {}
    errors: dict[str, str] = {}
    for name, args in (
        ("nws_alerts", (lat, lon)),
        ("nifc_incidents", (lat, lon, radius_km)),
        ("firms_hotspots", (lat, lon, radius_km)),
    ):
        try:
            feeds[name] = FEED_FETCHERS[name](*args)
        except Exception as exc:  # network feeds fail independently, never fatally
            feeds[name] = []
            errors[name] = f"{type(exc).__name__}: {exc}"

    alerts = feeds["nws_alerts"]
    incidents = feeds["nifc_incidents"]
    hotspots = feeds["firms_hotspots"]
    level = _situation_level(alerts, incidents, hotspots)
    return {
        "as_of": _utcnow_iso(),
        "home": home,
        "radius_km": radius_km,
        "level": level,
        "alerts": alerts,
        "incidents": incidents,
        "hotspots": hotspots,
        "feed_errors": errors,
        "sources": {
            "nws_alerts": "api.weather.gov active alerts (point query)",
            "nifc_incidents": "NIFC WFIGS current wildfire incident locations",
            "firms_hotspots": "NASA FIRMS VIIRS NRT (requires FIRMS_MAP_KEY)"
            if os.environ.get("FIRMS_MAP_KEY")
            else "disabled — set FIRMS_MAP_KEY (free at firms.modaps.eosdis.nasa.gov)",
        },
    }


def _emit_situation_event(situation: dict[str, Any]) -> None:
    try:
        envelope = {
            "ts": _utcnow_iso(),
            "type": "wildfire.situation.updated",
            "tags": {
                "service": "wildfire-watch",
                "priority": _LEVEL_TO_PRIORITY[situation["level"]],
                "level": situation["level"],
            },
            "summary": {
                "alerts": len(situation["alerts"]),
                "incidents": len(situation["incidents"]),
                "hotspots": len(situation["hotspots"]),
                "nearest_incident_km": situation["incidents"][0]["distance_km"]
                if situation["incidents"]
                else None,
            },
        }
        _ensure_dirs()
        with EVENTS_PATH.open("a") as fh:
            fh.write(json.dumps(envelope, separators=(",", ":")) + "\n")
    except OSError:
        pass


def _action_situation(payload: dict[str, Any]) -> dict[str, Any]:
    cfg = _load_config()
    force_refresh = bool(payload.get("refresh"))
    ttl = timedelta(minutes=float(cfg["cache_ttl_minutes"]))

    cached: dict[str, Any] | None = None
    if SITUATION_CACHE_PATH.exists():
        try:
            cached = json.loads(SITUATION_CACHE_PATH.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            cached = None

    if cached and not force_refresh:
        try:
            age = datetime.now(UTC) - datetime.fromisoformat(cached["as_of"])
            if age < ttl:
                return {"ok": True, "cached": True, "situation": cached}
        except (KeyError, ValueError):
            pass

    situation = _build_situation(cfg)
    all_feeds_failed = len(situation["feed_errors"]) == len(FEED_FETCHERS)
    if all_feeds_failed and cached:
        return {
            "ok": True,
            "cached": True,
            "stale": True,
            "feed_errors": situation["feed_errors"],
            "situation": cached,
        }

    try:
        SITUATION_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        SITUATION_CACHE_PATH.write_text(json.dumps(situation, indent=2))
    except OSError:
        pass
    _emit_situation_event(situation)
    return {"ok": True, "cached": False, "situation": situation}


def _render_brief(situation: dict[str, Any]) -> str:
    home = situation["home"]
    lines = [
        "# Wildfire Situation Brief",
        "",
        f"- **Prepared:** {situation['as_of']}",
        f"- **Area:** {home.get('label', 'configured home')} "
        f"({home['lat']:.4f}, {home['lon']:.4f}), {situation['radius_km']:.0f} km radius",
        f"- **Situation level:** **{situation['level'].upper()}**",
        "",
        "## Fire-weather alerts (NWS)",
    ]
    if situation["alerts"]:
        for a in situation["alerts"]:
            lines.append(
                f"- **{a['event']}** — {a.get('area') or 'area n/a'} (ends {a.get('ends') or 'n/a'})"
            )
    else:
        lines.append("- None active for this point.")
    lines += ["", "## Active incidents within radius (NIFC/WFIGS)"]
    if situation["incidents"]:
        lines.append("| Incident | Distance | Acres | Contained | County |")
        lines.append("|---|---|---|---|---|")
        for i in situation["incidents"][:15]:
            contained = (
                f"{i['percent_contained']}%" if i.get("percent_contained") is not None else "n/a"
            )
            lines.append(
                f"| {i['name']} | {i['distance_km']} km | {i.get('acres') or 'n/a'} "
                f"| {contained} | {i.get('county') or 'n/a'}, {i.get('state') or ''} |"
            )
    else:
        lines.append("- No active incidents reported within the radius.")
    lines += ["", "## Satellite hotspots (NASA FIRMS, last 48h)"]
    if situation["hotspots"]:
        nearest = situation["hotspots"][0]
        lines.append(
            f"- {len(situation['hotspots'])} detection(s); nearest {nearest['distance_km']} km "
            f"({nearest['lat']:.3f}, {nearest['lon']:.3f}), FRP {nearest.get('frp_mw') or 'n/a'} MW"
        )
    else:
        lines.append("- No detections within radius (or FIRMS_MAP_KEY not configured).")
    lines += [
        "",
        "---",
        "*Prepared by Sapphire wildfire-watch from public feeds "
        "(NWS api.weather.gov, NIFC WFIGS, NASA FIRMS). Informational only — "
        "verify against official channels before acting. Not an emergency alerting system.*",
        "",
    ]
    return "\n".join(lines)


def _action_fire_dept_brief(payload: dict[str, Any]) -> dict[str, Any]:
    """Render a public-safe markdown brief to disk. Draft only — never auto-sent."""
    situation_result = _action_situation(payload)
    situation = situation_result["situation"]
    brief = _render_brief(situation)
    stamp = datetime.now(UTC).strftime("%Y-%m-%d-%H%M")
    path = BRIEFS_DIR / f"wildfire-brief-{stamp}.md"
    try:
        BRIEFS_DIR.mkdir(parents=True, exist_ok=True)
        path.write_text(brief)
    except OSError as exc:
        return {"ok": False, "error": f"could not write brief: {exc}"}
    return {
        "ok": True,
        "path": str(path),
        "level": situation["level"],
        "brief": brief,
        "note": "Draft only. Review and send manually — this tool never contacts anyone.",
    }


def _action_config(payload: dict[str, Any]) -> dict[str, Any]:
    updates = payload.get("set")
    if updates is None:
        return {"ok": True, "config": _load_config(), "config_path": str(CONFIG_PATH)}
    if not isinstance(updates, dict):
        return {"ok": False, "error": "payload.set must be an object"}

    cfg = _load_config()
    home = updates.get("home")
    if home is not None:
        if (
            not isinstance(home, dict)
            or not isinstance(home.get("lat"), int | float)
            or not isinstance(home.get("lon"), int | float)
            or not -90 <= home["lat"] <= 90
            or not -180 <= home["lon"] <= 180
        ):
            return {
                "ok": False,
                "error": "home must be {lat in [-90,90], lon in [-180,180], label?}",
            }
        cfg["home"] = {"lat": home["lat"], "lon": home["lon"], "label": home.get("label", "home")}
    for key in ("radius_km", "cache_ttl_minutes"):
        if key in updates:
            if not isinstance(updates[key], int | float) or updates[key] <= 0:
                return {"ok": False, "error": f"{key} must be a positive number"}
            cfg[key] = float(updates[key])

    try:
        CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
        CONFIG_PATH.write_text(json.dumps(cfg, indent=2))
    except OSError as exc:
        return {"ok": False, "error": f"could not write config: {exc}"}
    return {"ok": True, "config": cfg, "config_path": str(CONFIG_PATH)}


_ACTIONS = {
    "ingest": _action_ingest,
    "list": _action_list,
    "stats": _action_stats,
    "schema_info": _action_schema_info,
    "situation": _action_situation,
    "fire_dept_brief": _action_fire_dept_brief,
    "config": _action_config,
}


def handle(payload: dict[str, Any]) -> dict[str, Any]:
    action = (payload or {}).get("action") or "schema_info"
    handler = _ACTIONS.get(action)
    if handler is None:
        return {
            "ok": False,
            "error": f"unknown action: {action}",
            "available_actions": sorted(_ACTIONS),
        }
    return handler(payload or {})


def main() -> None:
    raw = sys.stdin.read().strip()
    payload = json.loads(raw) if raw else {}
    result = handle(payload)
    print(json.dumps(result, indent=2 if "--pretty" in sys.argv else None))


if __name__ == "__main__":
    main()
