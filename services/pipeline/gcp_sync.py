"""Sapphire → GCP data pipeline.

Syncs local JSONL/JSON data to GCS (raw/) and BigQuery (sapphire dataset).

Flow per source:
  1. Discover local files newer than a watermark (state file).
  2. Transform raw JSON into BigQuery-ready row dicts (schema matches
     infra/gcp/schemas/*.json).
  3. Upload the transformed rows as NDJSON to GCS under raw/<source>/YYYY-MM-DD/.
  4. Load NDJSON from GCS into the matching BQ table.
  5. Advance the watermark.

Usage:
    python -m services.pipeline.gcp_sync --once          # one-shot sync
    python -m services.pipeline.gcp_sync --source signals
    python -m services.pipeline.gcp_sync --dry-run
"""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import logging
import sys
import uuid
from collections.abc import Callable, Iterable, Iterator
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from google.cloud import bigquery, storage

from lib.core.routine_pause import abort_if_paused

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

PROJECT = "tho-ai-agent"
DATASET = "sapphire"
BUCKET = "sapphire-data-lake"

ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "data"
STATE_FILE = DATA_DIR / ".gcp_sync_state.json"

log = logging.getLogger("gcp_sync")


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _stable_id(*parts: Any) -> str:
    return hashlib.sha1("::".join(str(p) for p in parts).encode()).hexdigest()[:16]


def _grade_from_score_value(score: Any) -> str | None:
    if score is None:
        return None
    try:
        value = float(score)
    except (TypeError, ValueError):
        return None
    if value > 1:
        value = value / 100.0
    if value >= 0.80:
        return "A"
    if value >= 0.65:
        return "B"
    if value >= 0.50:
        return "C"
    if value >= 0.30:
        return "D"
    return "F"


# ---------------------------------------------------------------------------
# State (watermark per source)
# ---------------------------------------------------------------------------


def _load_state() -> dict:
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text())
        except json.JSONDecodeError:
            log.warning("state file corrupted, starting fresh")
    return {}


def _save_state(state: dict) -> None:
    """Atomically write state — tempfile + os.replace to survive a crash
    between truncate and write (which would leave STATE_FILE empty and
    trigger a full-history replay on the next run).
    """
    import os
    import tempfile

    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            dir=STATE_FILE.parent,
            delete=False,
            prefix=STATE_FILE.name + ".",
            suffix=".tmp",
        ) as tf:
            tf.write(json.dumps(state, indent=2, sort_keys=True))
            tf.flush()
            os.fsync(tf.fileno())
            tmp_path = tf.name
        os.replace(tmp_path, STATE_FILE)
        tmp_path = None
    finally:
        if tmp_path and os.path.exists(tmp_path):
            with contextlib.suppress(OSError):
                os.unlink(tmp_path)


# ---------------------------------------------------------------------------
# Transformers: raw local file -> iterator of BQ row dicts
# ---------------------------------------------------------------------------


def _parse_ts(s: Any) -> str:
    """Normalize to ISO-8601 timestamp (BQ accepts this for TIMESTAMP cols)."""
    if not s:
        return _now_iso()
    if isinstance(s, (int, float)):
        return datetime.fromtimestamp(s, tz=UTC).isoformat()
    if isinstance(s, str):
        if s.endswith("Z"):
            return s.replace("Z", "+00:00")
        # YYYYMMDD_HHMM (legacy lead pipeline format)
        if len(s) == 13 and s[8] == "_" and s[:8].isdigit() and s[9:].isdigit():
            try:
                dt = datetime.strptime(s, "%Y%m%d_%H%M").replace(tzinfo=UTC)
                return dt.isoformat()
            except ValueError:
                return _now_iso()
        return s
    return _now_iso()


def transform_signals(files: list[Path]) -> Iterator[dict]:
    """data/signals/YYYY-MM-DD.jsonl → trading_signals rows."""
    now = _now_iso()
    for fp in files:
        # Stream line-by-line; the prior `.read_text().splitlines()` loaded
        # the entire JSONL into memory twice (once as text, once as list),
        # which is expensive for multi-MB signal-days.
        try:
            handle = fp.open("r", encoding="utf-8")
        except OSError as e:
            log.warning("signals read failed %s: %s", fp, e)
            continue
        try:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    r = json.loads(line)
                except json.JSONDecodeError:
                    continue
                ts = _parse_ts(r.get("timestamp") or r.get("closed_at"))
                yield {
                    "signal_id": r.get("pipeline_id")
                    or _stable_id(r.get("symbol"), ts, r.get("action")),
                    "symbol": str(r.get("symbol", "UNKNOWN")).upper(),
                    "action": str(r.get("action", "unknown")).lower(),
                    "direction": r.get("direction"),
                    "score": r.get("score"),
                    "confidence": r.get("confidence"),
                    "original_confidence": r.get("original_confidence"),
                    "regime": r.get("regime"),
                    "regime_score": r.get("regime_score"),
                    "source": r.get("source"),
                    "price_at_signal": r.get("price") or r.get("price_at_signal"),
                    "notes": "; ".join(r.get("notes") or [])
                    if isinstance(r.get("notes"), list)
                    else r.get("notes"),
                    "flags": r.get("enhancer_flags") or r.get("flags") or [],
                    "outcome": r.get("outcome"),
                    "pnl_usd": r.get("pnl_usd"),
                    "closed_at": _parse_ts(r.get("closed_at")) if r.get("closed_at") else None,
                    "timestamp": ts,
                    "ingested_at": now,
                }
        except OSError as e:
            log.warning("signals read failed %s: %s", fp, e)
        finally:
            handle.close()


def transform_predictions(files: list[Path]) -> Iterator[dict]:
    """data/intelligence/YYYY-MM-DD/predictions.json → predictions rows."""
    now = _now_iso()
    for fp in files:
        try:
            data = json.loads(fp.read_text())
        except (OSError, json.JSONDecodeError) as e:
            log.warning("predictions read failed %s: %s", fp, e)
            continue
        preds = data.get("predictions") if isinstance(data, dict) else data
        gen_at = _parse_ts((data or {}).get("generated_at"))
        if isinstance(preds, dict):
            iterable = preds.values()
        elif isinstance(preds, list):
            iterable = preds
        else:
            iterable = []
        for entry in iterable:
            if not isinstance(entry, dict):
                continue
            sym = entry.get("symbol", "UNKNOWN")
            ts = _parse_ts(entry.get("timestamp") or gen_at)
            # Pull predicted_price from last bar of predicted_bars if present
            predicted_bars = entry.get("predictions") or entry.get("predicted_bars")
            predicted_price = None
            actual_move = None
            if isinstance(predicted_bars, list) and predicted_bars:
                last = predicted_bars[-1]
                if isinstance(last, dict):
                    predicted_price = last.get("close") or last.get("c")
            cp = entry.get("current_price")
            pm = (predicted_price - cp) / cp * 100.0 if cp and predicted_price else None
            yield {
                "prediction_id": _stable_id(sym, ts, entry.get("model", "kronos")),
                "symbol": str(sym).upper().replace("-USD", ""),
                "direction": entry.get("direction"),
                "confidence": entry.get("confidence"),
                "current_price": cp,
                "predicted_price_24h": predicted_price,
                "predicted_move_pct": pm,
                "horizon_bars": entry.get("predict_bars"),
                "model": entry.get("model"),
                "predicted_bars": json.dumps(predicted_bars) if predicted_bars else None,
                "actual_price_24h": None,
                "actual_move_pct": actual_move,
                "accuracy_score": None,
                "timestamp": ts,
                "ingested_at": now,
            }


def transform_threats(files: list[Path]) -> Iterator[dict]:
    """data/intelligence/YYYY-MM-DD/threats.json → threat_intel rows."""
    now = _now_iso()
    for fp in files:
        try:
            data = json.loads(fp.read_text())
        except (OSError, json.JSONDecodeError) as e:
            log.warning("threats read failed %s: %s", fp, e)
            continue
        refreshed = _parse_ts((data or {}).get("refreshed_at"))
        threats = (data or {}).get("threats", [])
        if not isinstance(threats, list):
            continue
        for t in threats:
            if not isinstance(t, dict):
                continue
            cve = t.get("canonical_id")
            if not cve:
                continue
            meta = t.get("metadata") or {}
            cvss = meta.get("cvss_v3_score") or meta.get("cvss_score") or t.get("score")
            severity = (
                meta.get("cvss_v3_severity") or meta.get("severity") or _severity_from_score(cvss)
            )
            yield {
                "cve_id": cve,
                "severity": severity,
                "cvss_score": float(cvss) if cvss is not None else None,
                "exploited": bool(t.get("exploited")),
                "in_kev": "cisa-kev" in str(t.get("source", "")).lower(),
                "source": t.get("source"),
                "attack_techniques": meta.get("attack_techniques") or [],
                "affected_products": meta.get("affected_products") or [],
                "description": (t.get("summary") or "")[:1000],
                "published_at": _parse_ts(t.get("published_at")) if t.get("published_at") else None,
                "modified_at": _parse_ts(meta.get("modified_at"))
                if meta.get("modified_at")
                else None,
                "timestamp": refreshed,
                "ingested_at": now,
            }


def _severity_from_score(score: Any) -> str | None:
    try:
        s = float(score)
    except (TypeError, ValueError):
        return None
    if s >= 9.0:
        return "CRITICAL"
    if s >= 7.0:
        return "HIGH"
    if s >= 4.0:
        return "MEDIUM"
    if s >= 0.1:
        return "LOW"
    return None


def transform_regime(files: list[Path]) -> Iterator[dict]:
    """data/chain/*.json snapshots → market_regime rows."""
    now = _now_iso()
    for fp in files:
        try:
            snap = json.loads(fp.read_text())
        except (OSError, json.JSONDecodeError) as e:
            log.warning("regime read failed %s: %s", fp, e)
            continue
        ts = _parse_ts(snap.get("timestamp") or snap.get("generated_at"))
        _raw_regime = snap.get("regime") or {}
        regime = _raw_regime if isinstance(_raw_regime, dict) else {}
        overview = snap.get("overview") or {}
        funding = snap.get("funding") or {}
        oi = snap.get("open_interest") or {}
        stable = snap.get("stablecoins") or {}
        sentiment = snap.get("sentiment") or {}
        yield {
            "snapshot_id": _stable_id(ts, regime.get("state")),
            "regime": regime.get("state", "UNKNOWN"),
            "score": regime.get("score"),
            "confidence": regime.get("confidence"),
            "reasoning": regime.get("reasoning") or [],
            "btc_price_usd": overview.get("btc_price_usd"),
            "btc_dominance": overview.get("btc_dominance"),
            "total_market_cap_usd": overview.get("total_market_cap_usd"),
            "market_cap_change_24h_pct": overview.get("market_cap_change_24h_pct"),
            "avg_funding_8h_pct": funding.get("avg_funding_pct"),
            "majors_funding_skew": funding.get("majors_skew"),
            "oi_total_usd": oi.get("total_oi_usd") or oi.get("total_usd"),
            "oi_delta_24h_pct": oi.get("delta_24h_pct"),
            "stablecoins_total_usd": stable.get("total_usd"),
            "stablecoins_delta_24h_usd": stable.get("delta_24h_usd"),
            "stablecoins_flow": stable.get("flow_direction"),
            "fear_greed_score": sentiment.get("score"),
            "fear_greed_label": sentiment.get("label"),
            "timestamp": ts,
            "ingested_at": now,
        }


def _passthrough_ndjson(files: list[Path]) -> Iterator[dict]:
    """Yield rows from pre-shaped NDJSON files (telemetry collector output)."""
    for fp in files:
        # Stream line-by-line to avoid loading entire file into memory.
        try:
            handle = fp.open("r", encoding="utf-8")
        except OSError as e:
            log.warning("ndjson read failed %s: %s", fp, e)
            continue
        try:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    yield json.loads(line)
                except json.JSONDecodeError:
                    continue
        except OSError as e:
            log.warning("ndjson read failed %s: %s", fp, e)
        finally:
            handle.close()


def transform_metrics(files: list[Path]) -> Iterator[dict]:
    """data/metrics/YYYY-MM-DD.ndjson → inference_metrics rows (passthrough)."""
    return _passthrough_ndjson(files)


def transform_health(files: list[Path]) -> Iterator[dict]:
    """data/health/YYYY-MM-DD.ndjson → service_health rows (passthrough)."""
    return _passthrough_ndjson(files)


def transform_leads(files: list[Path]) -> Iterator[dict]:
    """data/leads/pipeline_*.json or houston_leads.jsonl → leads rows."""
    now = _now_iso()
    for fp in files:
        if fp.name == "houston_leads.jsonl":
            yield from _transform_houston_leads_jsonl(fp, now=now)
            continue
        try:
            data = json.loads(fp.read_text())
        except (OSError, json.JSONDecodeError) as e:
            log.warning("leads read failed %s: %s", fp, e)
            continue
        ts = _parse_ts((data or {}).get("generated_at") or (data or {}).get("timestamp"))
        leads = (data or {}).get("leads") or (data if isinstance(data, list) else [])
        if not isinstance(leads, list):
            continue
        for l in leads:
            if not isinstance(l, dict):
                continue
            yield {
                "lead_id": l.get("id") or _stable_id(l.get("address"), l.get("permit_type"), ts),
                "address": l.get("address"),
                "neighborhood": l.get("neighborhood"),
                "city": l.get("city"),
                "state": l.get("state"),
                "zip": l.get("zip"),
                "score": l.get("score"),
                "grade": l.get("grade"),
                "permit_type": l.get("permit_type"),
                "permit_value_usd": l.get("permit_value_usd") or l.get("value_usd"),
                "owner_name": l.get("owner_name"),
                "contacted": bool(l.get("contacted")),
                "contacted_at": _parse_ts(l.get("contacted_at")) if l.get("contacted_at") else None,
                "status": l.get("status"),
                "source": l.get("source"),
                "timestamp": ts,
                "ingested_at": now,
            }


def _transform_houston_leads_jsonl(fp: Path, *, now: str) -> Iterator[dict]:
    """Map the local Houston lead JSONL store into the BigQuery lead schema."""
    try:
        handle = fp.open("r", encoding="utf-8")
    except OSError as e:
        log.warning("houston leads read failed %s: %s", fp, e)
        return
    try:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                lead = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(lead, dict):
                continue
            raw = lead.get("raw_data") if isinstance(lead.get("raw_data"), dict) else {}
            score = lead.get("score")
            timestamp = _parse_ts(lead.get("created_at") or lead.get("ingested_at"))
            yield {
                "lead_id": lead.get("id")
                or _stable_id(lead.get("address"), lead.get("type"), timestamp),
                "address": lead.get("address"),
                "neighborhood": lead.get("neighborhood"),
                "city": lead.get("city") or raw.get("city") or "Houston",
                "state": lead.get("state") or raw.get("state") or "TX",
                "zip": lead.get("zip") or raw.get("zip"),
                "score": score,
                "grade": lead.get("grade") or _grade_from_score_value(score),
                "permit_type": lead.get("permit_type") or lead.get("type") or raw.get("permit_type"),
                "permit_value_usd": lead.get("permit_value_usd")
                or raw.get("declared_value")
                or raw.get("value_usd"),
                "owner_name": lead.get("owner_name") or raw.get("owner"),
                "contacted": bool(lead.get("contacted")),
                "contacted_at": _parse_ts(lead.get("contacted_at"))
                if lead.get("contacted_at")
                else None,
                "status": lead.get("status") or "LEAD",
                "source": lead.get("source"),
                "timestamp": timestamp,
                "ingested_at": now,
            }
    except OSError as e:
        log.warning("houston leads read failed %s: %s", fp, e)
    finally:
        handle.close()


# ---------------------------------------------------------------------------
# Source registry
# ---------------------------------------------------------------------------


@dataclass
class Source:
    name: str
    table: str
    glob: str | tuple[str, ...]  # relative to DATA_DIR
    transform: Callable[[list[Path]], Iterator[dict]]


SOURCES: dict[str, Source] = {
    "signals": Source("signals", "trading_signals", "signals/*.jsonl", transform_signals),
    "predictions": Source(
        "predictions", "predictions", "intelligence/*/predictions.json", transform_predictions
    ),
    "threats": Source("threats", "threat_intel", "intelligence/*/threats.json", transform_threats),
    "regime": Source("regime", "market_regime", "chain/*.json", transform_regime),
    "leads": Source(
        "leads",
        "leads",
        ("leads/pipeline_*.json", "leads/houston_leads.jsonl"),
        transform_leads,
    ),
    "metrics": Source("metrics", "inference_metrics", "metrics/*.ndjson", transform_metrics),
    "health": Source("health", "service_health", "health/*.ndjson", transform_health),
}


# ---------------------------------------------------------------------------
# Upload + load
# ---------------------------------------------------------------------------


def _discover_files(glob: str | tuple[str, ...], since_mtime: float) -> list[Path]:
    """Find files matching glob with mtime > since_mtime."""
    patterns = (glob,) if isinstance(glob, str) else glob
    files: set[Path] = set()
    for pattern in patterns:
        files.update(
            p for p in DATA_DIR.glob(pattern) if p.is_file() and p.stat().st_mtime > since_mtime
        )
    return sorted(files)


def _write_ndjson(rows: Iterable[dict], dest: Path) -> int:
    dest.parent.mkdir(parents=True, exist_ok=True)
    n = 0
    with dest.open("w") as f:
        for r in rows:
            f.write(json.dumps(r, default=str) + "\n")
            n += 1
    return n


def _upload_to_gcs(gcs_client: storage.Client, local: Path, gcs_path: str) -> str:
    bucket = gcs_client.bucket(BUCKET)
    blob = bucket.blob(gcs_path)
    blob.upload_from_filename(str(local), content_type="application/x-ndjson")
    return f"gs://{BUCKET}/{gcs_path}"


def _load_to_bq(bq_client: bigquery.Client, gcs_uri: str, table: str) -> int:
    table_ref = bq_client.dataset(DATASET).table(table)
    job_config = bigquery.LoadJobConfig(
        source_format=bigquery.SourceFormat.NEWLINE_DELIMITED_JSON,
        write_disposition=bigquery.WriteDisposition.WRITE_APPEND,
        ignore_unknown_values=True,
    )
    job = bq_client.load_table_from_uri(gcs_uri, table_ref, job_config=job_config)
    job.result()  # wait
    if job.errors:
        raise RuntimeError(f"BQ load errors: {job.errors}")
    return job.output_rows or 0


# ---------------------------------------------------------------------------
# Sync runner
# ---------------------------------------------------------------------------


@dataclass
class SyncResult:
    source: str
    files_scanned: int
    rows_written: int
    rows_loaded: int
    gcs_uri: str | None
    ok: bool
    error: str | None = None


def sync_source(
    source: Source,
    state: dict,
    bq_client: bigquery.Client,
    gcs_client: storage.Client,
    dry_run: bool = False,
) -> SyncResult:
    watermark = float(state.get(source.name, {}).get("mtime", 0.0))
    files = _discover_files(source.glob, watermark)
    if not files:
        return SyncResult(source.name, 0, 0, 0, None, True, "no new files")

    log.info("[%s] %d file(s) since watermark %.0f", source.name, len(files), watermark)

    # Transform → NDJSON staging file
    day = datetime.now(UTC).strftime("%Y-%m-%d")
    run_id = uuid.uuid4().hex[:8]
    stage = DATA_DIR / ".gcp_stage" / f"{source.name}_{day}_{run_id}.ndjson"
    rows_written = _write_ndjson(source.transform(files), stage)
    log.info("[%s] wrote %d row(s) to %s", source.name, rows_written, stage.name)

    if rows_written == 0:
        with contextlib.suppress(OSError):
            stage.unlink()
        return SyncResult(source.name, len(files), 0, 0, None, True, "empty transform")

    if dry_run:
        log.info("[%s] DRY RUN — not uploading or loading", source.name)
        return SyncResult(source.name, len(files), rows_written, 0, None, True, "dry-run")

    # Upload to GCS — the sapphire-gcs-to-bq Cloud Function auto-loads into BigQuery
    # on object-finalize. We avoid a redundant bq load here; doing both races the
    # function and inserts every row twice.
    gcs_path = f"raw/{source.name}/{day}/{source.name}_{run_id}.ndjson"
    gcs_uri = _upload_to_gcs(gcs_client, stage, gcs_path)
    log.info(
        "[%s] uploaded → %s (Cloud Function will load into %s.%s)",
        source.name,
        gcs_uri,
        DATASET,
        source.table,
    )

    # Advance watermark
    new_mtime = max(p.stat().st_mtime for p in files)
    state[source.name] = {"mtime": new_mtime, "last_run": _now_iso(), "last_rows": rows_written}

    return SyncResult(source.name, len(files), rows_written, rows_written, gcs_uri, True)


def run_sync(sources: list[str] | None = None, dry_run: bool = False) -> list[SyncResult]:
    state = _load_state()
    bq_client = bigquery.Client(project=PROJECT)
    gcs_client = storage.Client(project=PROJECT)

    targets = [SOURCES[s] for s in (sources or list(SOURCES))]
    results: list[SyncResult] = []
    for source in targets:
        try:
            r = sync_source(source, state, bq_client, gcs_client, dry_run=dry_run)
        except Exception as e:
            log.exception("[%s] unhandled error: %s", source.name, e)
            r = SyncResult(source.name, 0, 0, 0, None, False, str(e))
        results.append(r)

    if not dry_run:
        _save_state(state)
    return results


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> int:
    abort_if_paused("gcp-sync")
    p = argparse.ArgumentParser()
    p.add_argument(
        "--source",
        action="append",
        choices=list(SOURCES),
        help="Only sync these sources (repeatable). Default: all.",
    )
    p.add_argument("--dry-run", action="store_true", help="Transform + stage; skip upload/load.")
    p.add_argument("--reset-watermark", action="store_true", help="Ignore watermark, rescan all.")
    p.add_argument("-v", "--verbose", action="store_true")
    args = p.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    if args.reset_watermark and STATE_FILE.exists():
        STATE_FILE.unlink()
        log.info("watermark reset")

    results = run_sync(sources=args.source, dry_run=args.dry_run)

    print("\n=== gcp_sync summary ===")
    any_fail = False
    for r in results:
        status = "OK " if r.ok else "FAIL"
        note = f" ({r.error})" if r.error else ""
        print(f"  {status}  {r.source:12} files={r.files_scanned:3} rows={r.rows_loaded:5}{note}")
        if not r.ok:
            any_fail = True
    return 1 if any_fail else 0


if __name__ == "__main__":
    sys.exit(main())
