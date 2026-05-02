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
  - Region         — from data/foundry/regional-intel/Region.ndjson
  - IntelItem      — from data/foundry/regional-intel/IntelItem.ndjson
  - IntelSourceHealth — from data/foundry/regional-intel/IntelSourceHealth.ndjson

Tranche-3 expansion (0.2.0):
  - IntelVectorRecord  — from lib.intel.bq_vector_store mock JSONL
  - TelegramIntelMessage — from services/telegram_intel daily JSONL
  - HyperliquidSignal  — from ~/.sapphire/hyperliquid_signals.jsonl ledger
  - OODAPacket         — from ~/.cache/sapphire/gemini_ooda/*.json cache
  - ThreatIndicator    — granular IOC extraction over threats.json + .md
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

log = logging.getLogger("foundry.ingestion")

_REGIONAL_EXPORT_DIR = Path("data/foundry/regional-intel")
_REGIONAL_OBJECT_FILES = {
    "Region": "Region.ndjson",
    "IntelItem": "IntelItem.ndjson",
    "IntelSourceHealth": "IntelSourceHealth.ndjson",
}


def _repo_root() -> Path:
    override = os.getenv("SAPPHIRE_REPO_ROOT")
    if override:
        return Path(override).expanduser()

    home_repo = Path.home() / "Code" / "Sapphire"
    local_repo = Path(__file__).resolve().parents[2]
    for c in (local_repo, home_repo):
        if (c / "lib" / "foundry").exists() or (c / "AGENTS.md").exists():
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


def _file_mtime_iso(path: Path) -> str | None:
    try:
        return _iso(datetime.fromtimestamp(path.stat().st_mtime, UTC))
    except OSError:
        return None


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
            trades.append(
                {
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
                }
            )

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
        alerts.append(
            {
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
            }
        )

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
                alerts.append(
                    {
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
                    }
                )

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
                svc = row.get("service_name") or row.get("service") or row.get("name") or fpath.stem
                last_check = _iso(row.get("timestamp") or row.get("ts")) or _file_mtime_iso(fpath)
                svc_id = _deterministic_id(svc, last_check or "")
                objects.append(
                    {
                        "id": svc_id,
                        "service": svc,
                        "status": row.get("status", "unknown"),
                        "latency_ms": row.get("response_ms")
                        or row.get("latency_ms")
                        or row.get("latency"),
                        "uptime_pct": row.get("uptime_pct"),
                        "error_count": row.get("error_count", 0),
                        "last_check": last_check,
                        "host": row.get("host") or row.get("endpoint"),
                        "tier": row.get("tier"),
                        "notes": row.get("notes") or row.get("error") or "",
                        "_sapphire_source": str(fpath.relative_to(root)),
                    }
                )

        # Aggregate heartbeat file — fan out the services dict into per-service
        # objects. The .jsonl extension means it is not matched by the glob above.
        heartbeat_path = health_dir / "heartbeat.jsonl"
        if heartbeat_path.is_file():
            for row in _load_jsonl(heartbeat_path, max_lines=500):
                if not isinstance(row, dict):
                    continue
                last_check = _iso(row.get("timestamp") or row.get("ts")) or _file_mtime_iso(
                    heartbeat_path
                )
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
                        svc_id = _deterministic_id(svc_name, last_check or "", "heartbeat")
                        objects.append(
                            {
                                "id": svc_id,
                                "service": svc_name,
                                "status": status_str,
                                "latency_ms": latency,
                                "uptime_pct": None,
                                "error_count": 0,
                                "last_check": last_check,
                                "host": None,
                                "tier": None,
                                "notes": notes,
                                "_sapphire_source": str(heartbeat_path.relative_to(root)),
                            }
                        )

    # Fallback: build from known services in infrastructure topology
    topology_path = root / "data" / "device_topology.json"
    topo = _load_json(topology_path)
    topology_last_check = _file_mtime_iso(topology_path)
    devices = topo.get("devices") or {}
    if isinstance(devices, dict):
        device_items = devices.items()
    else:
        device_items = ((d.get("name", ""), d) for d in devices if isinstance(d, dict))
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
                objects.append(
                    {
                        "id": svc_id,
                        "service": svc_name,
                        "status": "unknown",
                        "latency_ms": None,
                        "uptime_pct": None,
                        "error_count": 0,
                        "last_check": topology_last_check,
                        "host": device.get("tailscaleIp") or device.get("ip") or device_name,
                        "tier": None,
                        "notes": f"From topology ({device_name})",
                        "_sapphire_source": "data/device_topology.json",
                    }
                )

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
                tid = (
                    t.get("canonical_id")
                    or t.get("id")
                    or _deterministic_id(t.get("title", ""), ts)
                )
                objects.append(
                    {
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
                    }
                )

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
            objects.append(
                {
                    "id": tid,
                    "title": title,
                    "description": content[:500],
                    "severity": "medium",
                    "source": "sapphire-threat-intel",
                    "cve_ids": re.findall(r"CVE-\d{4}-\d+", content),
                    "affected_products": [],
                    "published_at": _iso(datetime.fromtimestamp(md_file.stat().st_mtime, UTC)),
                    "region": "GLOBAL",
                    "mitre_tactics": [],
                    "ioc_count": 0,
                    "link": "",
                    "_sapphire_source": str(md_file.relative_to(root)),
                }
            )

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
            objects.append(
                {
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
                }
            )
        elif brief_md.is_file():
            try:
                content = brief_md.read_text(errors="replace")[:8000]
            except OSError:
                continue
            title_match = re.search(r"^#\s+(.+)", content, re.MULTILINE)
            brief_id = _deterministic_id("brief", day_dir.name)
            objects.append(
                {
                    "id": brief_id,
                    "date": day_dir.name,
                    "title": title_match.group(1).strip()
                    if title_match
                    else f"Daily Brief — {day_dir.name}",
                    "summary": content[:1000],
                    "sections": [],
                    "market_outlook": None,
                    "threat_level": "normal",
                    "key_signals": [],
                    "generated_at": _iso(datetime.fromtimestamp(brief_md.stat().st_mtime, UTC)),
                    "_sapphire_source": str(brief_md.relative_to(root)),
                }
            )

    if since:
        objects = [o for o in objects if o.get("date", "") >= since.strftime("%Y-%m-%d")]

    log.info("Transformed %d DailyBrief objects", len(objects))
    return objects


# ---------------------------------------------------------------------------
# Regional intelligence exports — Foundry-ready NDJSON from sibling workbench
# ---------------------------------------------------------------------------


def _load_regional_export(
    root: Path,
    object_type: str,
    *,
    since: datetime | None = None,
) -> list[dict[str, Any]]:
    """Load staged regional-intel Foundry NDJSON rows for one object type."""
    filename = _REGIONAL_OBJECT_FILES[object_type]
    fpath = root / _REGIONAL_EXPORT_DIR / filename
    rows: list[dict[str, Any]] = []
    for row in _load_jsonl(fpath, max_lines=10000):
        if not isinstance(row, dict):
            continue
        ts = row.get("observed_at") or row.get("last_seen_at") or row.get("snapshot_updated_at")
        if since and ts and str(ts) < since.isoformat():
            continue
        obj = dict(row)
        object_id = obj.get("object_id") or obj.get("id")
        if object_id:
            obj.setdefault("id", object_id)
            obj.setdefault("object_id", object_id)
        obj["_sapphire_source"] = str(fpath.relative_to(root))
        rows.append(obj)
    log.info("Transformed %d %s objects from %s", len(rows), object_type, fpath)
    return rows


def transform_regions(
    root: Path | None = None,
    *,
    since: datetime | None = None,
) -> list[dict[str, Any]]:
    """Read staged regional-intel Region export rows."""
    root = root or _repo_root()
    return _load_regional_export(root, "Region", since=since)


def transform_intel_items(
    root: Path | None = None,
    *,
    since: datetime | None = None,
) -> list[dict[str, Any]]:
    """Read staged regional-intel IntelItem export rows."""
    root = root or _repo_root()
    return _load_regional_export(root, "IntelItem", since=since)


def transform_intel_source_health(
    root: Path | None = None,
    *,
    since: datetime | None = None,
) -> list[dict[str, Any]]:
    """Read staged regional-intel IntelSourceHealth export rows."""
    root = root or _repo_root()
    return _load_regional_export(root, "IntelSourceHealth", since=since)


# ---------------------------------------------------------------------------
# Tranche-3 expansion (ontology v0.2.0)
# ---------------------------------------------------------------------------


def _normalize_iso(value: Any) -> str | None:
    """Normalize a timestamp candidate to ISO-8601 string."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, (int, float)):
        if value <= 0:
            return None
        try:
            return datetime.fromtimestamp(float(value), tz=UTC).isoformat()
        except (OverflowError, OSError, ValueError):
            return None
    text = str(value).strip()
    return text or None


# ---------------------------------------------------------------------------
# IntelVectorRecord — BQ vector store mock JSONL → Foundry IntelVectorRecord
# ---------------------------------------------------------------------------


def _bq_vector_mock_path(root: Path) -> Path:
    """Resolve the BQ vector store mock JSONL.

    Honors ``SAPPHIRE_BQ_VECTOR_MOCK_PATH``; otherwise falls back to the
    canonical ``~/.cache/sapphire/bq_vector_mock.jsonl`` and to a repo-local
    ``data/intel/bq_vector_mock.jsonl`` mirror. Repo-local wins so tests
    don't trip on a developer's actual cache.
    """
    override = os.getenv("SAPPHIRE_BQ_VECTOR_MOCK_PATH")
    if override:
        return Path(override).expanduser()
    repo_local = root / "data" / "intel" / "bq_vector_mock.jsonl"
    if repo_local.is_file():
        return repo_local
    return Path.home() / ".cache" / "sapphire" / "bq_vector_mock.jsonl"


def transform_intel_vector_records(
    root: Path | None = None,
    *,
    since: datetime | None = None,
) -> list[dict[str, Any]]:
    """Read BQ vector store mock JSONL and produce IntelVectorRecord objects.

    The source file is one record per line, each shaped like
    ``VectorRecord.to_jsonable``. Embeddings are intentionally dropped from
    the Foundry envelope (high-dimensional vectors aren't meant to live in
    the ontology); we keep an ``embedding_dims`` count and a
    ``embedding_hash`` so a buyer can verify corpus shape without lifting
    raw vectors.
    """
    root = root or _repo_root()
    path = _bq_vector_mock_path(root)
    objects: list[dict[str, Any]] = []
    if not path.is_file():
        return objects
    for row in _load_jsonl(path, max_lines=10_000):
        if not isinstance(row, dict):
            continue
        if row.get("__meta__"):
            # Mock-store meta record (carries last_index_at + dims) — skip.
            continue
        record_id = str(row.get("id") or "").strip()
        text_value = str(row.get("text") or "").strip()
        if not record_id or not text_value:
            continue
        embedding = row.get("embedding") or []
        if not isinstance(embedding, list):
            embedding = []
        try:
            embedding_floats = [float(v) for v in embedding]
        except (TypeError, ValueError):
            embedding_floats = []
        embedding_hash = hashlib.sha256(
            "|".join(f"{v:.8f}" for v in embedding_floats).encode()
        ).hexdigest()[:16]
        created_iso = _normalize_iso(row.get("created_at"))
        if since and created_iso and created_iso < since.isoformat():
            continue
        metadata = row.get("metadata") if isinstance(row.get("metadata"), dict) else {}
        objects.append(
            {
                "id": record_id,
                "record_id": record_id,
                "text": text_value[:2000],
                "text_length": len(text_value),
                "source": str(row.get("source") or "ad_hoc"),
                "metadata": dict(metadata),
                "embedding_dims": len(embedding_floats),
                "embedding_hash": embedding_hash,
                "created_at": created_iso,
                "_sapphire_source": (
                    str(path.relative_to(root)) if path.is_relative_to(root) else str(path)
                ),
            }
        )
    log.info("Transformed %d IntelVectorRecord objects from %s", len(objects), path)
    return objects


def to_IntelVectorRecord(record: dict[str, Any]) -> dict[str, Any]:
    """Single-record transform: ``VectorRecord``-shape dict → Foundry envelope.

    Raises ``ValueError`` on malformed input (missing id or text).
    """
    if not isinstance(record, dict):
        raise ValueError("IntelVectorRecord source must be a dict")
    record_id = str(record.get("id") or "").strip()
    text_value = str(record.get("text") or "").strip()
    if not record_id:
        raise ValueError("IntelVectorRecord requires non-empty 'id'")
    if not text_value:
        raise ValueError("IntelVectorRecord requires non-empty 'text'")
    embedding = record.get("embedding") or []
    if not isinstance(embedding, list):
        raise ValueError("IntelVectorRecord 'embedding' must be a list")
    try:
        embedding_floats = [float(v) for v in embedding]
    except (TypeError, ValueError) as exc:
        raise ValueError(f"IntelVectorRecord embedding must be numeric: {exc}") from exc
    embedding_hash = hashlib.sha256(
        "|".join(f"{v:.8f}" for v in embedding_floats).encode()
    ).hexdigest()[:16]
    metadata = record.get("metadata") if isinstance(record.get("metadata"), dict) else {}
    return {
        "id": record_id,
        "record_id": record_id,
        "text": text_value[:2000],
        "text_length": len(text_value),
        "source": str(record.get("source") or "ad_hoc"),
        "metadata": dict(metadata),
        "embedding_dims": len(embedding_floats),
        "embedding_hash": embedding_hash,
        "created_at": _normalize_iso(record.get("created_at")),
    }


# ---------------------------------------------------------------------------
# TelegramIntelMessage — services/telegram_intel daily JSONL → Foundry objects
# ---------------------------------------------------------------------------


def _telegram_intel_dirs(root: Path) -> list[Path]:
    """Return candidate roots that may hold telegram_intel/<date>/messages.jsonl."""
    override = os.getenv("SAPPHIRE_TELEGRAM_INTEL_DATA_DIR")
    candidates: list[Path] = []
    if override:
        candidates.append(Path(override).expanduser())
    candidates.append(root / "data" / "telegram_intel")
    return [p for p in candidates if p.is_dir()]


def transform_telegram_intel_messages(
    root: Path | None = None,
    *,
    since: datetime | None = None,
) -> list[dict[str, Any]]:
    """Read telegram_intel daily JSONL and produce TelegramIntelMessage objects.

    Telegram intel records are stamped by ``services.telegram_intel.sink`` —
    they carry a ``canonical_id``, a structured ``channel``, ``message``,
    ``quality``, and ``classifier`` block, plus a provenance envelope. We
    flatten the most useful fields for downstream Foundry consumers and
    keep the canonical_id as the Foundry primary key so re-uploads are
    naturally idempotent.
    """
    root = root or _repo_root()
    objects: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for base in _telegram_intel_dirs(root):
        for msg_path in sorted(base.glob("*/messages.jsonl"), reverse=True)[:30]:
            for row in _load_jsonl(msg_path, max_lines=5_000):
                if not isinstance(row, dict):
                    continue
                canonical_id = str(row.get("canonical_id") or "").strip()
                if not canonical_id or canonical_id in seen_ids:
                    continue
                ingested_at = _normalize_iso(row.get("ingested_at"))
                if since and ingested_at and ingested_at < since.isoformat():
                    continue
                channel = row.get("channel") if isinstance(row.get("channel"), dict) else {}
                message = row.get("message") if isinstance(row.get("message"), dict) else {}
                quality = row.get("quality") if isinstance(row.get("quality"), dict) else {}
                classifier = (
                    row.get("classifier") if isinstance(row.get("classifier"), dict) else {}
                )
                published_at = _normalize_iso(message.get("published_at"))
                seen_ids.add(canonical_id)
                source_ref = (
                    str(msg_path.relative_to(root))
                    if msg_path.is_relative_to(root)
                    else str(msg_path)
                )
                objects.append(
                    {
                        "id": canonical_id,
                        "canonical_id": canonical_id,
                        "schema_version": int(row.get("schema_version") or 1),
                        "channel_id": str(channel.get("id") or channel.get("channel_id") or ""),
                        "channel_handle": str(channel.get("handle") or channel.get("name") or ""),
                        "channel_attribution": str(channel.get("attribution") or ""),
                        "message_id": str(message.get("id") or ""),
                        "text": str(message.get("text") or "")[:4000],
                        "text_length": len(str(message.get("text") or "")),
                        "truncated": bool(message.get("truncated", False)),
                        "published_at": published_at,
                        "ingested_at": ingested_at,
                        "quality_decision": str(quality.get("decision") or ""),
                        "quality_score": quality.get("score"),
                        "quality_reason": str(quality.get("reason") or ""),
                        "classifier_label": str(classifier.get("label") or ""),
                        "classifier_confidence": classifier.get("confidence"),
                        "classifier_source": str(classifier.get("source") or ""),
                        "classifier_model": str(classifier.get("model") or ""),
                        "_sapphire_source": source_ref,
                    }
                )
    log.info("Transformed %d TelegramIntelMessage objects", len(objects))
    return objects


def to_TelegramIntelMessage(record: dict[str, Any]) -> dict[str, Any]:
    """Single-record transform: telegram_intel sink row → Foundry envelope."""
    if not isinstance(record, dict):
        raise ValueError("TelegramIntelMessage source must be a dict")
    canonical_id = str(record.get("canonical_id") or "").strip()
    if not canonical_id:
        raise ValueError("TelegramIntelMessage requires non-empty 'canonical_id'")
    raw_message = record.get("message")
    if not isinstance(raw_message, dict):
        raise ValueError("TelegramIntelMessage 'message' must be a dict")
    channel = record.get("channel") if isinstance(record.get("channel"), dict) else {}
    message = raw_message
    quality = record.get("quality") if isinstance(record.get("quality"), dict) else {}
    classifier = record.get("classifier") if isinstance(record.get("classifier"), dict) else {}
    text = str(message.get("text") or "")
    return {
        "id": canonical_id,
        "canonical_id": canonical_id,
        "schema_version": int(record.get("schema_version") or 1),
        "channel_id": str(channel.get("id") or channel.get("channel_id") or ""),
        "channel_handle": str(channel.get("handle") or channel.get("name") or ""),
        "channel_attribution": str(channel.get("attribution") or ""),
        "message_id": str(message.get("id") or ""),
        "text": text[:4000],
        "text_length": len(text),
        "truncated": bool(message.get("truncated", False)),
        "published_at": _normalize_iso(message.get("published_at")),
        "ingested_at": _normalize_iso(record.get("ingested_at")),
        "quality_decision": str(quality.get("decision") or ""),
        "quality_score": quality.get("score"),
        "quality_reason": str(quality.get("reason") or ""),
        "classifier_label": str(classifier.get("label") or ""),
        "classifier_confidence": classifier.get("confidence"),
        "classifier_source": str(classifier.get("source") or ""),
        "classifier_model": str(classifier.get("model") or ""),
    }


# ---------------------------------------------------------------------------
# HyperliquidSignal — ~/.sapphire/hyperliquid_signals.jsonl → Foundry objects
# ---------------------------------------------------------------------------


def _hyperliquid_signal_paths(root: Path) -> list[Path]:
    """Return candidate hyperliquid signal log paths in priority order."""
    override = os.getenv("SAPPHIRE_HYPERLIQUID_SIGNAL_PATH")
    candidates: list[Path] = []
    if override:
        candidates.append(Path(override).expanduser())
    repo_local = root / "data" / "hyperliquid_signals.jsonl"
    if repo_local.is_file():
        candidates.append(repo_local)
    home_log = Path.home() / ".sapphire" / "hyperliquid_signals.jsonl"
    if home_log.is_file():
        candidates.append(home_log)
    return [p for p in candidates if p.is_file()]


def transform_hyperliquid_signals(
    root: Path | None = None,
    *,
    since: datetime | None = None,
) -> list[dict[str, Any]]:
    """Read hyperliquid signal JSONL and produce HyperliquidSignal objects.

    Each row in the source ledger is the dict ``SignalPublisher.publish``
    appends — already enriched with ``schema_version``, ``topic``,
    ``source``, ``published_at`` and any signal-specific fields.
    """
    root = root or _repo_root()
    objects: list[dict[str, Any]] = []
    seen_keys: set[str] = set()
    for path in _hyperliquid_signal_paths(root):
        for row in _load_jsonl(path, max_lines=20_000):
            if not isinstance(row, dict):
                continue
            published_at = _normalize_iso(row.get("published_at"))
            if since and published_at and published_at < since.isoformat():
                continue
            event_id = str(row.get("event_id") or "").strip()
            topic = str(row.get("topic") or "").strip()
            symbol = str(row.get("symbol") or "").strip().upper()
            signal_type = str(row.get("signal_type") or "").strip()
            # Stable PK: prefer event_id, otherwise hash topic+symbol+published.
            if event_id:
                signal_id = f"hl:{event_id}"
            else:
                signal_id = "hl:" + _deterministic_id(
                    topic, symbol, signal_type, published_at or ""
                )
            if signal_id in seen_keys:
                continue
            seen_keys.add(signal_id)
            source_ref = str(path.relative_to(root)) if path.is_relative_to(root) else str(path)
            objects.append(
                {
                    "id": signal_id,
                    "event_id": event_id or None,
                    "topic": topic,
                    "schema_version": str(row.get("schema_version") or "hyperliquid.signal.v1"),
                    "signal_type": signal_type,
                    "symbol": symbol,
                    "side": row.get("side"),
                    "dominant_side": row.get("dominant_side"),
                    "price": row.get("price"),
                    "size": row.get("size"),
                    "notional_usd": row.get("notional_usd"),
                    "threshold_usd": row.get("threshold_usd"),
                    "ratio": row.get("ratio"),
                    "threshold_ratio": row.get("threshold_ratio"),
                    "sustained_seconds": row.get("sustained_seconds"),
                    "current_depth_usd": row.get("current_depth_usd"),
                    "baseline_depth_usd": row.get("baseline_depth_usd"),
                    "drop_ratio": row.get("drop_ratio"),
                    "threshold_drop_ratio": row.get("threshold_drop_ratio"),
                    "window_seconds": row.get("window_seconds"),
                    "exchange_time_ms": row.get("exchange_time_ms"),
                    "trade_id": row.get("trade_id"),
                    "observed_at": _normalize_iso(row.get("observed_at")),
                    "baseline_observed_at": _normalize_iso(row.get("baseline_observed_at")),
                    "published_at": published_at,
                    "paper_only": bool(row.get("paper_only", True)),
                    "live_trading_enabled": bool(row.get("live_trading_enabled", False)),
                    "source": str(row.get("source") or "hyperliquid-public-feed"),
                    "_sapphire_source": source_ref,
                }
            )
    log.info("Transformed %d HyperliquidSignal objects", len(objects))
    return objects


def to_HyperliquidSignal(record: dict[str, Any]) -> dict[str, Any]:
    """Single-record transform: hyperliquid signal ledger row → Foundry envelope."""
    if not isinstance(record, dict):
        raise ValueError("HyperliquidSignal source must be a dict")
    topic = str(record.get("topic") or "").strip()
    if not topic:
        raise ValueError("HyperliquidSignal requires non-empty 'topic'")
    symbol = str(record.get("symbol") or "").strip().upper()
    if not symbol:
        raise ValueError("HyperliquidSignal requires non-empty 'symbol'")
    signal_type = str(record.get("signal_type") or "").strip()
    published_at = _normalize_iso(record.get("published_at"))
    event_id = str(record.get("event_id") or "").strip()
    if event_id:
        signal_id = f"hl:{event_id}"
    else:
        signal_id = "hl:" + _deterministic_id(topic, symbol, signal_type, published_at or "")
    return {
        "id": signal_id,
        "event_id": event_id or None,
        "topic": topic,
        "schema_version": str(record.get("schema_version") or "hyperliquid.signal.v1"),
        "signal_type": signal_type,
        "symbol": symbol,
        "side": record.get("side"),
        "dominant_side": record.get("dominant_side"),
        "price": record.get("price"),
        "size": record.get("size"),
        "notional_usd": record.get("notional_usd"),
        "threshold_usd": record.get("threshold_usd"),
        "ratio": record.get("ratio"),
        "threshold_ratio": record.get("threshold_ratio"),
        "sustained_seconds": record.get("sustained_seconds"),
        "current_depth_usd": record.get("current_depth_usd"),
        "baseline_depth_usd": record.get("baseline_depth_usd"),
        "drop_ratio": record.get("drop_ratio"),
        "threshold_drop_ratio": record.get("threshold_drop_ratio"),
        "window_seconds": record.get("window_seconds"),
        "exchange_time_ms": record.get("exchange_time_ms"),
        "trade_id": record.get("trade_id"),
        "observed_at": _normalize_iso(record.get("observed_at")),
        "baseline_observed_at": _normalize_iso(record.get("baseline_observed_at")),
        "published_at": published_at,
        "paper_only": bool(record.get("paper_only", True)),
        "live_trading_enabled": bool(record.get("live_trading_enabled", False)),
        "source": str(record.get("source") or "hyperliquid-public-feed"),
    }


# ---------------------------------------------------------------------------
# OODAPacket — ~/.cache/sapphire/gemini_ooda/*.json → Foundry objects
# ---------------------------------------------------------------------------


def _gemini_ooda_dirs(root: Path) -> list[Path]:
    override = os.getenv("SAPPHIRE_GEMINI_OODA_CACHE_DIR")
    candidates: list[Path] = []
    if override:
        candidates.append(Path(override).expanduser())
    repo_local = root / "data" / "gemini_ooda"
    if repo_local.is_dir():
        candidates.append(repo_local)
    home_cache = Path.home() / ".cache" / "sapphire" / "gemini_ooda"
    if home_cache.is_dir():
        candidates.append(home_cache)
    return [p for p in candidates if p.is_dir()]


def transform_ooda_packets(
    root: Path | None = None,
    *,
    since: datetime | None = None,
) -> list[dict[str, Any]]:
    """Read gemini_ooda cache JSON and produce OODAPacket objects.

    Each cache file is a stamped envelope around an OODA dict. We pull out
    the four OODA fields, the model + generator, the cache hash from the
    filename (== request hash) and the issued timestamp.
    """
    root = root or _repo_root()
    objects: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for cache_dir in _gemini_ooda_dirs(root):
        for cache_file in sorted(cache_dir.glob("*.json"), reverse=True)[:200]:
            if cache_file.name == "counters.json":
                continue
            data = _load_json(cache_file)
            if not isinstance(data, dict) or not data:
                continue
            ooda = data.get("ooda") if isinstance(data.get("ooda"), dict) else None
            if not ooda:
                # Skip cache files that aren't an OODA envelope (e.g. counter
                # files or corrupt-JSON returns from ``_load_json``).
                continue
            envelope = data.get("provenance") if isinstance(data.get("provenance"), dict) else {}
            cached_at = data.get("_cached_at")
            issued_at = (
                _normalize_iso(envelope.get("generated_at"))
                or _normalize_iso(cached_at)
                or _file_mtime_iso(cache_file)
            )
            if since and issued_at and issued_at < since.isoformat():
                continue
            request_hash = cache_file.stem
            packet_id = f"ooda:{request_hash}"
            if packet_id in seen_ids:
                continue
            seen_ids.add(packet_id)
            tokens = data.get("tokens") if isinstance(data.get("tokens"), dict) else {}
            metadata = (
                envelope.get("metadata") if isinstance(envelope.get("metadata"), dict) else {}
            )
            act_value = ooda.get("act") if isinstance(ooda.get("act"), list) else []
            source_ref = (
                str(cache_file.relative_to(root))
                if cache_file.is_relative_to(root)
                else str(cache_file)
            )
            objects.append(
                {
                    "id": packet_id,
                    "request_hash": request_hash,
                    "observe": str(ooda.get("observe") or "")[:1000],
                    "orient": str(ooda.get("orient") or "")[:1000],
                    "decide": str(ooda.get("decide") or "")[:1000],
                    "act": [str(a)[:500] for a in act_value][:8],
                    "model": str(envelope.get("model") or metadata.get("model") or ""),
                    "generator": str(envelope.get("generator") or ""),
                    "mode": str(metadata.get("mode") or "live"),
                    "issued_at": issued_at,
                    "ttl_seconds": envelope.get("ttl_seconds"),
                    "prompt_tokens": tokens.get("prompt_tokens"),
                    "output_tokens": tokens.get("output_tokens"),
                    "total_tokens": tokens.get("total_tokens"),
                    "cached": bool(metadata.get("cache", False)),
                    "_sapphire_source": source_ref,
                }
            )
    log.info("Transformed %d OODAPacket objects", len(objects))
    return objects


def to_OODAPacket(record: dict[str, Any]) -> dict[str, Any]:
    """Single-record transform: gemini_ooda cache envelope → Foundry envelope."""
    if not isinstance(record, dict):
        raise ValueError("OODAPacket source must be a dict")
    ooda = record.get("ooda") if isinstance(record.get("ooda"), dict) else None
    if not isinstance(ooda, dict):
        raise ValueError("OODAPacket source must contain 'ooda' dict")
    request_hash = str(record.get("request_hash") or record.get("topic_hash") or "").strip()
    if not request_hash:
        raise ValueError("OODAPacket requires 'request_hash' or 'topic_hash'")
    envelope = record.get("provenance") if isinstance(record.get("provenance"), dict) else {}
    metadata = envelope.get("metadata") if isinstance(envelope.get("metadata"), dict) else {}
    tokens = record.get("tokens") if isinstance(record.get("tokens"), dict) else {}
    act_value = ooda.get("act") if isinstance(ooda.get("act"), list) else []
    return {
        "id": f"ooda:{request_hash}",
        "request_hash": request_hash,
        "observe": str(ooda.get("observe") or "")[:1000],
        "orient": str(ooda.get("orient") or "")[:1000],
        "decide": str(ooda.get("decide") or "")[:1000],
        "act": [str(a)[:500] for a in act_value][:8],
        "model": str(envelope.get("model") or metadata.get("model") or ""),
        "generator": str(envelope.get("generator") or ""),
        "mode": str(metadata.get("mode") or "live"),
        "issued_at": _normalize_iso(envelope.get("generated_at") or record.get("_cached_at")),
        "ttl_seconds": envelope.get("ttl_seconds"),
        "prompt_tokens": tokens.get("prompt_tokens"),
        "output_tokens": tokens.get("output_tokens"),
        "total_tokens": tokens.get("total_tokens"),
        "cached": bool(metadata.get("cache", False)),
    }


# ---------------------------------------------------------------------------
# ThreatIndicator — granular IOC view over threats.json + threat_intel/*.md
# ---------------------------------------------------------------------------


_IOC_IPV4_RE = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")
_IOC_DOMAIN_RE = re.compile(
    r"\b[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?(?:\.[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?)+\b",
    re.IGNORECASE,
)
_IOC_HASH_RE = re.compile(r"\b[a-fA-F0-9]{32,64}\b")


def _extract_iocs(text: str) -> dict[str, list[str]]:
    """Extract a small set of IOC families from free-form text.

    The categories mirror the most common operator-actionable indicators:
    CVE IDs, IPv4 addresses, suspicious domain-shaped tokens, and hex
    hashes (MD5/SHA-1/SHA-256). Matches are deduplicated and capped.
    """
    cves = sorted(set(re.findall(r"CVE-\d{4}-\d+", text)))[:32]
    ipv4 = sorted(
        {
            ip
            for ip in _IOC_IPV4_RE.findall(text)
            if all(0 <= int(part) <= 255 for part in ip.split("."))
        }
    )[:32]
    hashes = sorted({h.lower() for h in _IOC_HASH_RE.findall(text)})[:32]
    domains: list[str] = []
    seen_domains: set[str] = set()
    for match in _IOC_DOMAIN_RE.findall(text):
        candidate = match.lower()
        # Skip pure IPv4-looking matches and obvious version strings.
        if _IOC_IPV4_RE.fullmatch(candidate):
            continue
        parts = candidate.split(".")
        if any(part.isdigit() for part in parts) and len(parts) <= 3:
            continue
        if candidate in seen_domains:
            continue
        seen_domains.add(candidate)
        domains.append(candidate)
        if len(domains) >= 32:
            break
    return {
        "cve_ids": cves,
        "ipv4": ipv4,
        "domains": domains,
        "hashes": hashes,
    }


def transform_threat_indicators(
    root: Path | None = None,
    *,
    since: datetime | None = None,
) -> list[dict[str, Any]]:
    """Granular threat indicator view (one ThreatIndicator per CVE/threat).

    Distinct from ``transform_threat_intel`` (which produces ``ThreatIntel``
    advisories): this transform breaks every advisory + markdown note down
    into its IOC fingerprint so a Foundry consumer can join indicators to
    services, alerts, or intel-vector hits without re-parsing free text.
    """
    root = root or _repo_root()
    objects: list[dict[str, Any]] = []
    seen_ids: set[str] = set()

    intel_dir = root / "data" / "intelligence"
    if intel_dir.is_dir():
        for threats_file in sorted(intel_dir.glob("*/threats.json"), reverse=True)[:10]:
            data = _load_json(threats_file)
            for t in data.get("threats") or []:
                if not isinstance(t, dict):
                    continue
                published = _normalize_iso(t.get("published") or threats_file.parent.name)
                if since and published and published < since.isoformat():
                    continue
                base_text = " ".join(
                    str(v) for v in (t.get("title"), t.get("description"), t.get("link")) if v
                )
                iocs = _extract_iocs(base_text)
                # Merge any author-provided arrays.
                for kind, values in (
                    ("cve_ids", t.get("cve_ids") or []),
                    ("ipv4", t.get("ipv4") or t.get("ips") or []),
                    ("domains", t.get("domains") or []),
                    ("hashes", t.get("hashes") or []),
                ):
                    merged = list(iocs[kind])
                    for v in values:
                        s = str(v).strip()
                        if s and s not in merged:
                            merged.append(s)
                    iocs[kind] = merged[:32]
                base_id = str(
                    t.get("canonical_id") or t.get("id") or ""
                ).strip() or _deterministic_id(t.get("title", ""), published or "")
                indicator_id = f"ti:{base_id}"
                if indicator_id in seen_ids:
                    continue
                seen_ids.add(indicator_id)
                source_ref = str(threats_file.relative_to(root))
                objects.append(
                    {
                        "id": indicator_id,
                        "advisory_id": base_id,
                        "title": str(t.get("title", ""))[:500],
                        "severity": str(t.get("severity", "medium")),
                        "score": t.get("score"),
                        "exploited": bool(t.get("exploited", False)),
                        "source": str(t.get("source", "")),
                        "cve_ids": iocs["cve_ids"],
                        "ipv4_addresses": iocs["ipv4"],
                        "domains": iocs["domains"],
                        "hashes": iocs["hashes"],
                        "ioc_total": (
                            len(iocs["cve_ids"])
                            + len(iocs["ipv4"])
                            + len(iocs["domains"])
                            + len(iocs["hashes"])
                        ),
                        "mitre_tactics": t.get("mitre_tactics") or [],
                        "affected_products": t.get("affected_products") or [],
                        "published_at": published,
                        "region": str(t.get("region", "GLOBAL")),
                        "link": str(t.get("link") or t.get("url", "")),
                        "_sapphire_source": source_ref,
                    }
                )

    threat_md_dir = root / "data" / "threat_intel"
    if threat_md_dir.is_dir():
        for md_file in sorted(threat_md_dir.glob("*.md"), reverse=True)[:30]:
            try:
                content = md_file.read_text(errors="replace")[:8000]
            except OSError:
                continue
            title_match = re.search(r"^#\s+(.+)", content, re.MULTILINE)
            title = title_match.group(1).strip() if title_match else md_file.stem
            base_id = _deterministic_id(md_file.name, title)
            indicator_id = f"ti:{base_id}"
            if indicator_id in seen_ids:
                continue
            seen_ids.add(indicator_id)
            iocs = _extract_iocs(content)
            published = _normalize_iso(datetime.fromtimestamp(md_file.stat().st_mtime, UTC))
            if since and published and published < since.isoformat():
                continue
            objects.append(
                {
                    "id": indicator_id,
                    "advisory_id": base_id,
                    "title": title[:500],
                    "severity": "medium",
                    "score": None,
                    "exploited": False,
                    "source": "sapphire-threat-intel",
                    "cve_ids": iocs["cve_ids"],
                    "ipv4_addresses": iocs["ipv4"],
                    "domains": iocs["domains"],
                    "hashes": iocs["hashes"],
                    "ioc_total": (
                        len(iocs["cve_ids"])
                        + len(iocs["ipv4"])
                        + len(iocs["domains"])
                        + len(iocs["hashes"])
                    ),
                    "mitre_tactics": [],
                    "affected_products": [],
                    "published_at": published,
                    "region": "GLOBAL",
                    "link": "",
                    "_sapphire_source": str(md_file.relative_to(root)),
                }
            )

    log.info("Transformed %d ThreatIndicator objects", len(objects))
    return objects


def to_ThreatIndicator(record: dict[str, Any]) -> dict[str, Any]:
    """Single-record transform: threat advisory dict → Foundry envelope."""
    if not isinstance(record, dict):
        raise ValueError("ThreatIndicator source must be a dict")
    title = str(record.get("title") or "").strip()
    if not title:
        raise ValueError("ThreatIndicator requires non-empty 'title'")
    base_id = str(
        record.get("canonical_id") or record.get("id") or ""
    ).strip() or _deterministic_id(title, _normalize_iso(record.get("published")) or "")
    base_text = " ".join(
        str(v)
        for v in (
            record.get("title"),
            record.get("description"),
            record.get("link"),
        )
        if v
    )
    iocs = _extract_iocs(base_text)
    for kind, values in (
        ("cve_ids", record.get("cve_ids") or []),
        ("ipv4", record.get("ipv4") or record.get("ips") or []),
        ("domains", record.get("domains") or []),
        ("hashes", record.get("hashes") or []),
    ):
        merged = list(iocs[kind])
        for v in values:
            s = str(v).strip()
            if s and s not in merged:
                merged.append(s)
        iocs[kind] = merged[:32]
    return {
        "id": f"ti:{base_id}",
        "advisory_id": base_id,
        "title": title[:500],
        "severity": str(record.get("severity", "medium")),
        "score": record.get("score"),
        "exploited": bool(record.get("exploited", False)),
        "source": str(record.get("source", "")),
        "cve_ids": iocs["cve_ids"],
        "ipv4_addresses": iocs["ipv4"],
        "domains": iocs["domains"],
        "hashes": iocs["hashes"],
        "ioc_total": (
            len(iocs["cve_ids"]) + len(iocs["ipv4"]) + len(iocs["domains"]) + len(iocs["hashes"])
        ),
        "mitre_tactics": record.get("mitre_tactics") or [],
        "affected_products": record.get("affected_products") or [],
        "published_at": _normalize_iso(record.get("published")),
        "region": str(record.get("region", "GLOBAL")),
        "link": str(record.get("link") or record.get("url", "")),
    }


# ---------------------------------------------------------------------------
# Convenience: all transforms
# ---------------------------------------------------------------------------


ALL_TRANSFORMS: dict[str, Any] = {
    "PaperTrade": transform_paper_trades,
    "Alert": transform_alerts,
    "ServiceHealth": transform_service_health,
    "ThreatIntel": transform_threat_intel,
    "DailyBrief": transform_daily_briefs,
    "Region": transform_regions,
    "IntelItem": transform_intel_items,
    "IntelSourceHealth": transform_intel_source_health,
    # Tranche-3 expansion (ontology v0.2.0).
    "IntelVectorRecord": transform_intel_vector_records,
    "TelegramIntelMessage": transform_telegram_intel_messages,
    "HyperliquidSignal": transform_hyperliquid_signals,
    "OODAPacket": transform_ooda_packets,
    "ThreatIndicator": transform_threat_indicators,
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
