"""Transform local Sapphire data into Foundry ontology objects.

Each ``transform_*`` function reads local files and returns a list of dicts
ready for :meth:`FoundryClient.upsert_objects` or
:meth:`FoundryClient.upload_rows`.

Object types (see docs/foundry-ontology-schema.md):
  - PaperTrade     — from data/signals/*.jsonl + data/paper_portfolio.json
  - Alert          — from data/security/**/*.json + data/system_events.jsonl
  - ServiceHealth  — from heartbeat / data/health/*.ndjson
  - ThreatIntel    — from data/intelligence/*/threats.json + data/threat_intel/*.md
  - DailyBrief     — from data/intelligence/*/daily_brief.json
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

log = logging.getLogger("foundry.ingestion")


def _repo_root() -> Path:
    home_repo = Path.home() / "Code" / "Sapphire"
    local_repo = Path(__file__).resolve().parents[2]
    for c in (home_repo, local_repo):
        if c.exists():
            return c
    return local_repo


def _load_jsonl(path: Path, *, max_lines: int = 5000) -> list[dict[str, Any]]:
    """Read a JSONL file, returning up to *max_lines* parsed records."""
    rows: list[dict[str, Any]] = []
    if not path.is_file():
        return rows
    try:
        with path.open() as fh:
            for i, line in enumerate(fh):
                if i >= max_lines:
                    break
                line = line.strip()
                if line:
                    try:
                        rows.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
    except OSError:
        pass
    return rows


def _load_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text())
    except Exception:
        return {}


def _deterministic_id(*parts: Any) -> str:
    """SHA-256-based deterministic ID from arbitrary key parts."""
    raw = "|".join(str(p) for p in parts)
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def _iso(ts: Any) -> str | None:
    """Best-effort ISO-8601 string from various timestamp formats."""
    if ts is None:
        return None
    if isinstance(ts, datetime):
        return ts.isoformat()
    s = str(ts).strip()
    if not s:
        return None
    return s


# ---------------------------------------------------------------------------
# PaperTrade — signals.jsonl → Foundry PaperTrade objects
# ---------------------------------------------------------------------------


def transform_paper_trades(
    root: Path | None = None,
    *,
    since: datetime | None = None,
) -> list[dict[str, Any]]:
    """Read signal JSONL files and return PaperTrade ontology objects."""
    root = root or _repo_root()
    signals_dir = root / "data" / "signals"
    if not signals_dir.is_dir():
        return []

    trades: list[dict[str, Any]] = []
    for jsonl_file in sorted(signals_dir.glob("*.jsonl")):
        if since:
            # Quick date filter from filename (YYYY-MM-DD.jsonl)
            try:
                file_date = datetime.strptime(jsonl_file.stem, "%Y-%m-%d").replace(tzinfo=UTC)
                if file_date.date() < since.date():
                    continue
            except ValueError:
                pass

        for row in _load_jsonl(jsonl_file):
            ts = row.get("timestamp")
            trade_id = row.get("pipeline_id") or _deterministic_id(
                row.get("symbol"), ts, row.get("strategy")
            )
            trades.append({
                "id": trade_id,
                "symbol": row.get("symbol", ""),
                "direction": row.get("direction", ""),
                "action": row.get("action", ""),
                "strategy": row.get("strategy", ""),
                "entry_price": row.get("price"),
                "take_profit": row.get("take_profit"),
                "stop_loss": row.get("stop_loss"),
                "rr_ratio": row.get("rr_ratio"),
                "confidence": row.get("confidence"),
                "score": row.get("score"),
                "position_usd": row.get("position_usd"),
                "sizing_method": row.get("sizing_method"),
                "routing": row.get("routing", ""),
                "outcome": row.get("outcome"),
                "pnl_usd": row.get("pnl_usd"),
                "close_price": row.get("close_price"),
                "opened_at": _iso(ts),
                "closed_at": _iso(row.get("closed_at")),
                "source": row.get("source", ""),
                "regime": row.get("regime"),
                "regime_score": row.get("regime_score"),
                "fear_greed": row.get("fear_greed"),
                "kronos_direction": row.get("kronos_direction"),
                "funding_rate": row.get("funding_rate"),
                "_sapphire_source": str(jsonl_file.relative_to(root)),
            })

    log.info("Transformed %d PaperTrade objects from %s", len(trades), signals_dir)
    return trades


# ---------------------------------------------------------------------------
# Alert — security reports + system events → Foundry Alert objects
# ---------------------------------------------------------------------------


def transform_alerts(
    root: Path | None = None,
    *,
    since: datetime | None = None,
) -> list[dict[str, Any]]:
    """Read security reports and system events to produce Alert objects."""
    root = root or _repo_root()
    alerts: list[dict[str, Any]] = []

    # 1) data/system_events.jsonl — filter for alert/incident/security events
    events_file = root / "data" / "system_events.jsonl"
    _ALERT_TYPES = {"alert", "incident", "security", "error", "circuit_breaker"}
    for row in _load_jsonl(events_file, max_lines=10000):
        evt_type = str(row.get("type", "")).lower()
        if not any(t in evt_type for t in _ALERT_TYPES):
            continue
        ts = row.get("timestamp") or row.get("ts")
        if since and ts:
            try:
                if str(ts) < since.isoformat():
                    continue
            except Exception:
                pass
        alert_id = row.get("id") or _deterministic_id(ts, evt_type, row.get("message", ""))
        alerts.append({
            "id": alert_id,
            "title": row.get("title") or row.get("message", "")[:120],
            "severity": row.get("priority") or row.get("severity", "medium"),
            "category": evt_type,
            "source": row.get("service") or row.get("source", "system"),
            "device": row.get("device"),
            "message": row.get("message", ""),
            "timestamp": _iso(ts),
            "resolved": row.get("resolved", False),
            "resolved_at": _iso(row.get("resolved_at")),
            "tags": row.get("tags") or [],
            "_sapphire_source": "data/system_events.jsonl",
        })

    # 2) data/security/**/*.json — if any structured security reports exist
    security_dir = root / "data" / "security"
    if security_dir.is_dir():
        for fpath in security_dir.rglob("*.json"):
            report = _load_json(fpath)
            if not report:
                continue
            findings = report.get("findings") or report.get("alerts") or [report]
            for f in findings:
                alert_id = f.get("id") or _deterministic_id(fpath.name, f.get("title", ""))
                alerts.append({
                    "id": alert_id,
                    "title": f.get("title", fpath.stem),
                    "severity": f.get("severity", "medium"),
                    "category": "security_report",
                    "source": f.get("source", fpath.stem),
                    "device": f.get("device"),
                    "message": f.get("description") or f.get("message", ""),
                    "timestamp": _iso(f.get("timestamp") or f.get("published")),
                    "resolved": f.get("resolved", False),
                    "resolved_at": None,
                    "tags": f.get("tags") or [],
                    "_sapphire_source": str(fpath.relative_to(root)),
                })

    log.info("Transformed %d Alert objects", len(alerts))
    return alerts


# ---------------------------------------------------------------------------
# ServiceHealth — heartbeat snapshots → Foundry ServiceHealth objects
# ---------------------------------------------------------------------------


def transform_service_health(
    root: Path | None = None,
) -> list[dict[str, Any]]:
    """Read health data and build ServiceHealth ontology objects.

    Handles two on-disk shapes written by services/heartbeat/heartbeat.py and
    the health probe pipeline:

    * Per-service probes in ``data/health/*.ndjson`` — one row per service per
      tick: ``{"service_name": "...", "status": "...", "response_ms": ...}``.
    * Aggregate heartbeat in ``data/health/heartbeat.jsonl`` — one row per tick
      with ``{"services": {"svc": "up"|"down"}, "timestamp": "..."}``. Each
      service in the dict becomes its own ServiceHealth object.
    """
    root = root or _repo_root()
    objects: list[dict[str, Any]] = []

    health_dir = root / "data" / "health"
    if health_dir.is_dir():
        # Per-service probe rows — current heartbeat writer uses `service_name`,
        # older rows may use `service`/`name`.
        for fpath in sorted(health_dir.glob("*.ndjson"), reverse=True)[:5]:
            for row in _load_jsonl(fpath, max_lines=500):
                if not isinstance(row, dict):
                    continue
                svc = (
                    row.get("service_name")
                    or row.get("service")
                    or row.get("name")
                    or fpath.stem
                )
                ts = row.get("timestamp")
                svc_id = _deterministic_id(svc, ts or "")
                objects.append({
                    "id": svc_id,
                    "service": svc,
                    "status": row.get("status", "unknown"),
                    "latency_ms": row.get("response_ms")
                        or row.get("latency_ms")
                        or row.get("latency"),
                    "uptime_pct": row.get("uptime_pct"),
                    "error_count": row.get("error_count", 0),
                    "last_check": _iso(ts),
                    "host": row.get("host") or row.get("endpoint"),
                    "tier": row.get("tier"),
                    "notes": row.get("notes") or row.get("error") or "",
                    "_sapphire_source": str(fpath.relative_to(root)),
                })

        # Aggregate heartbeat file — fan out the services dict into per-service
        # objects. The .jsonl extension means it is not matched by the glob above.
        heartbeat_path = health_dir / "heartbeat.jsonl"
        if heartbeat_path.is_file():
            for row in _load_jsonl(heartbeat_path, max_lines=500):
                if not isinstance(row, dict):
                    continue
                ts = row.get("timestamp")
                services_field = row.get("services")
                if isinstance(services_field, dict):
                    for svc_name, svc_val in services_field.items():
                        # Service value is either a plain status string ("up",
                        # "healthy") or a nested probe dict with status +
                        # latency + etc.
                        if isinstance(svc_val, dict):
                            status_str = svc_val.get("status", "unknown")
                            latency = (
                                svc_val.get("latency_ms")
                                or svc_val.get("response_ms")
                                or svc_val.get("latency")
                            )
                            notes = svc_val.get("notes") or svc_val.get("error") or "heartbeat"
                        elif isinstance(svc_val, str):
                            status_str = svc_val
                            latency = None
                            notes = "heartbeat"
                        else:
                            continue
                        svc_id = _deterministic_id(svc_name, ts or "", "heartbeat")
                        objects.append({
                            "id": svc_id,
                            "service": svc_name,
                            "status": status_str,
                            "latency_ms": latency,
                            "uptime_pct": None,
                            "error_count": 0,
                            "last_check": _iso(ts),
                            "host": None,
                            "tier": None,
                            "notes": notes,
                            "_sapphire_source": str(heartbeat_path.relative_to(root)),
                        })

    # Fallback: build from known services in infrastructure topology
    topology_path = root / "data" / "device_topology.json"
    topo = _load_json(topology_path)
    devices = topo.get("devices") or {}
    if isinstance(devices, dict):
        device_items = devices.items()
    else:
        device_items = (
            (d.get("name", ""), d) for d in devices if isinstance(d, dict)
        )
    for device_name, device in device_items:
        if not isinstance(device, dict):
            continue
        for svc in device.get("services") or []:
            if isinstance(svc, str):
                svc_name = svc
            elif isinstance(svc, dict):
                svc_name = svc.get("name", "")
            else:
                continue
            if not svc_name:
                continue
            svc_id = _deterministic_id(device_name, svc_name, "topology")
            # Only add if no health data exists for this service
            if not any(o["service"] == svc_name for o in objects):
                objects.append({
                    "id": svc_id,
                    "service": svc_name,
                    "status": "unknown",
                    "latency_ms": None,
                    "uptime_pct": None,
                    "error_count": 0,
                    "last_check": None,
                    "host": device.get("tailscaleIp") or device.get("ip") or device_name,
                    "tier": None,
                    "notes": f"From topology ({device_name})",
                    "_sapphire_source": "data/device_topology.json",
                })

    log.info("Transformed %d ServiceHealth objects", len(objects))
    return objects


# ---------------------------------------------------------------------------
# ThreatIntel — threat feeds → Foundry ThreatIntel objects
# ---------------------------------------------------------------------------


def transform_threat_intel(
    root: Path | None = None,
    *,
    since: datetime | None = None,
) -> list[dict[str, Any]]:
    """Read threat intel data and produce ThreatIntel ontology objects."""
    root = root or _repo_root()
    objects: list[dict[str, Any]] = []

    # 1) data/intelligence/*/threats.json
    intel_dir = root / "data" / "intelligence"
    if intel_dir.is_dir():
        for threats_file in sorted(intel_dir.glob("*/threats.json"), reverse=True)[:10]:
            data = _load_json(threats_file)
            for t in data.get("threats") or []:
                ts = t.get("published") or threats_file.parent.name
                if since and str(ts) < since.isoformat():
                    continue
                tid = t.get("canonical_id") or t.get("id") or _deterministic_id(
                    t.get("title", ""), ts
                )
                objects.append({
                    "id": tid,
                    "title": t.get("title", ""),
                    "description": t.get("description", ""),
                    "severity": t.get("severity", "medium"),
                    "source": t.get("source", ""),
                    "cve_ids": t.get("cve_ids") or [],
                    "affected_products": t.get("affected_products") or [],
                    "published_at": _iso(ts),
                    "region": t.get("region", "GLOBAL"),
                    "mitre_tactics": t.get("mitre_tactics") or [],
                    "ioc_count": len(t.get("iocs") or []),
                    "link": t.get("link") or t.get("url", ""),
                    "_sapphire_source": str(threats_file.relative_to(root)),
                })

    # 2) data/threat_intel/*.md — extract title from first heading
    threat_md_dir = root / "data" / "threat_intel"
    if threat_md_dir.is_dir():
        for md_file in sorted(threat_md_dir.glob("*.md"), reverse=True)[:10]:
            content = ""
            try:
                content = md_file.read_text(errors="replace")[:4000]
            except OSError:
                continue
            title_match = re.search(r"^#\s+(.+)", content, re.MULTILINE)
            title = title_match.group(1).strip() if title_match else md_file.stem
            tid = _deterministic_id(md_file.name, title)
            # Don't duplicate if already captured from threats.json
            if any(o["id"] == tid for o in objects):
                continue
            objects.append({
                "id": tid,
                "title": title,
                "description": content[:500],
                "severity": "medium",
                "source": "sapphire-threat-intel",
                "cve_ids": re.findall(r"CVE-\d{4}-\d+", content),
                "affected_products": [],
                "published_at": _iso(
                    datetime.fromtimestamp(md_file.stat().st_mtime, UTC)
                ),
                "region": "GLOBAL",
                "mitre_tactics": [],
                "ioc_count": 0,
                "link": "",
                "_sapphire_source": str(md_file.relative_to(root)),
            })

    log.info("Transformed %d ThreatIntel objects", len(objects))
    return objects


# ---------------------------------------------------------------------------
# DailyBrief — intelligence briefs → Foundry DailyBrief objects
# ---------------------------------------------------------------------------


def transform_daily_briefs(
    root: Path | None = None,
    *,
    since: datetime | None = None,
) -> list[dict[str, Any]]:
    """Read daily brief artifacts and produce DailyBrief ontology objects."""
    root = root or _repo_root()
    objects: list[dict[str, Any]] = []

    intel_dir = root / "data" / "intelligence"
    if not intel_dir.is_dir():
        return objects

    # Look for daily_brief.json or daily_brief.md in date folders
    for day_dir in sorted(intel_dir.iterdir(), reverse=True):
        if not day_dir.is_dir():
            continue

        brief_json = day_dir / "daily_brief.json"
        brief_md = day_dir / "daily_brief.md"

        if brief_json.is_file():
            data = _load_json(brief_json)
            if not data:
                continue
            brief_id = data.get("id") or _deterministic_id("brief", day_dir.name)
            objects.append({
                "id": brief_id,
                "date": day_dir.name,
                "title": data.get("title", f"Daily Brief — {day_dir.name}"),
                "summary": data.get("summary", ""),
                "sections": data.get("sections") or [],
                "market_outlook": data.get("market_outlook"),
                "threat_level": data.get("threat_level", "normal"),
                "key_signals": data.get("key_signals") or [],
                "generated_at": _iso(data.get("generated_at")),
                "_sapphire_source": str(brief_json.relative_to(root)),
            })
        elif brief_md.is_file():
            try:
                content = brief_md.read_text(errors="replace")[:8000]
            except OSError:
                continue
            title_match = re.search(r"^#\s+(.+)", content, re.MULTILINE)
            brief_id = _deterministic_id("brief", day_dir.name)
            objects.append({
                "id": brief_id,
                "date": day_dir.name,
                "title": title_match.group(1).strip() if title_match else f"Daily Brief — {day_dir.name}",
                "summary": content[:1000],
                "sections": [],
                "market_outlook": None,
                "threat_level": "normal",
                "key_signals": [],
                "generated_at": _iso(
                    datetime.fromtimestamp(brief_md.stat().st_mtime, UTC)
                ),
                "_sapphire_source": str(brief_md.relative_to(root)),
            })

    if since:
        objects = [o for o in objects if o.get("date", "") >= since.strftime("%Y-%m-%d")]

    log.info("Transformed %d DailyBrief objects", len(objects))
    return objects


# ---------------------------------------------------------------------------
# Convenience: all transforms
# ---------------------------------------------------------------------------


ALL_TRANSFORMS: dict[str, Any] = {
    "PaperTrade": transform_paper_trades,
    "Alert": transform_alerts,
    "ServiceHealth": transform_service_health,
    "ThreatIntel": transform_threat_intel,
    "DailyBrief": transform_daily_briefs,
}


def transform_all(
    root: Path | None = None,
    *,
    since: datetime | None = None,
) -> dict[str, list[dict[str, Any]]]:
    """Run every transform and return ``{object_type: [objects]}``."""
    root = root or _repo_root()
    result: dict[str, list[dict[str, Any]]] = {}
    for name, fn in ALL_TRANSFORMS.items():
        try:
            if name == "ServiceHealth":
                result[name] = fn(root)
            else:
                result[name] = fn(root, since=since)
        except Exception:
            log.exception("Transform %s failed", name)
            result[name] = []
    return result
