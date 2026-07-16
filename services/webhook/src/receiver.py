#!/usr/bin/env python3
"""Sapphire Webhook Receiver — Windows PC (port 9090).

Receives TradingView alerts, validates HMAC, optionally enriches via local
Ollama, then forwards to the Sapphire signal logger on Mac (Tailscale
100.x.x.w:18081). Fully on-prem — no GCP Pub/Sub.

Signal flow:
  TradingView → POST /webhook/tradingview (this service, Windows, :9090)
                → HMAC validate + optional Ollama enrichment
                → POST http://100.x.x.w:18081/api/signals  ← Mac signal logger
"""

import asyncio
import base64
import contextlib
import hashlib
import hmac
import json
import logging
import math
import os
import platform
import re
import socket
import subprocess
import uuid
from contextlib import asynccontextmanager
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Optional

import httpx
import uvicorn
from fastapi import BackgroundTasks, FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse

# GCP deps removed — on-prem mode uses Tailscale HTTP routing
pubsub_v1 = None
_PUBSUB_AVAILABLE = False
g_firestore = None
_FIRESTORE_AVAILABLE = False

# ─── Config ───────────────────────────────────────────────────────────────────

SYSTEM_LOGS_COLLECTION = "system_logs"

WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "")  # Must match Pine Script alert body
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")  # Local Ollama (RTX 5070 Ti)
WEBHOOK_PORT = int(os.getenv("WEBHOOK_PORT", "9090"))
LOG_FILE = os.getenv("WEBHOOK_LOG_FILE", "C:/sapphire/webhook.log")
ALERT_LOG_FILE = os.getenv("ALERT_LOG_FILE", "C:/sapphire/webhook/alerts.jsonl")
ALERT_LOG_MAX_BYTES = int(os.getenv("ALERT_LOG_MAX_BYTES", "10485760"))  # 10 MiB
ALERT_LOG_BACKUP_COUNT = int(os.getenv("ALERT_LOG_BACKUP_COUNT", "3"))
MAX_HISTORY = 200
MAX_WEBHOOK_BODY_BYTES = int(
    os.getenv("WEBHOOK_MAX_BODY_BYTES", os.getenv("MAX_WEBHOOK_BODY_BYTES", "8192"))
)

# On-prem signal routing — env-driven; no hardcoded Tailscale IPs.
# Examples:
#   SIGNAL_LOGGER_MAC=http://100.x.y.z:18081
#   ALPHA_ENGINE_RARI1=http://100.x.y.z:18080
#   ALPHA_ENGINE_RARI2=http://100.x.y.z:18080
#   SIGNAL_TARGETS=mac-logger=http://host:18081,desk=http://host:18082
ALPHA_ENGINE_RARI1 = os.getenv("ALPHA_ENGINE_RARI1", "").strip()
ALPHA_ENGINE_RARI2 = os.getenv("ALPHA_ENGINE_RARI2", "").strip()
SIGNAL_LOGGER_MAC = os.getenv("SIGNAL_LOGGER_MAC", "").strip()
SAPPHIRE_CONTROL_TOKEN = os.getenv("SAPPHIRE_CONTROL_API_TOKEN", "")

# Legacy GCP vars — kept for reference, no longer used
EDGE_CAPABILITIES_COLLECTION = "edge_capabilities"
SYSTEM_LOGS_COLLECTION = "system_logs"
CAPABILITY_SYNC_INTERVAL_SECONDS = int(os.getenv("CAPABILITY_SYNC_INTERVAL_SECONDS", "180"))
LOCAL_SERVICE_PROBE_TIMEOUT_SECONDS = float(os.getenv("LOCAL_SERVICE_PROBE_TIMEOUT_SECONDS", "5.0"))
RESEARCH_WORKER_OUTPUT_ROOT = os.getenv(
    "RESEARCH_WORKER_OUTPUT_ROOT",
    os.getenv("WINDOWS_RESEARCH_WORKER_OUTPUT_ROOT", "E:/Sapphire/research-worker"),
)
RESEARCH_WORKER_MAX_AGE_SECONDS = int(os.getenv("RESEARCH_WORKER_MAX_AGE_SECONDS", "129600"))
RESEARCH_WORKER_TASK_NAME = os.getenv("RESEARCH_WORKER_TASK_NAME", "SapphireResearchWorker")

# Idempotency: reject duplicate alerts within the dedup window.
# TradingView may retry a webhook on timeout; duplicate alerts share the same
# symbol/action/bar-time/exchange/interval/strategy fingerprint.
IDEMPOTENCY_WINDOW_SECONDS = int(os.getenv("IDEMPOTENCY_WINDOW_SECONDS", "300"))
_seen_alert_ids: set[str] = set()
_seen_alert_times: dict[str, datetime] = {}


def _alert_fingerprint(data: dict[str, Any]) -> str:
    """Stable idempotency key for a TradingView alert payload."""
    keys = ("symbol", "action", "time", "exchange", "interval", "strategy")
    parts = [str(data.get(k) or "").strip().lower() for k in keys]
    return hmac.new(
        (WEBHOOK_SECRET or "sapphire-webhook").encode(),
        "|".join(parts).encode(),
        hashlib.sha256,
    ).hexdigest()


def _record_seen(alert_id: str, *, now: datetime | None = None) -> None:
    """Track a seen alert id and expire stale entries."""
    current = now or datetime.now(UTC)
    _seen_alert_ids.add(alert_id)
    _seen_alert_times[alert_id] = current
    if len(_seen_alert_times) <= 1000:
        return
    cutoff = current.timestamp() - IDEMPOTENCY_WINDOW_SECONDS
    stale = [aid for aid, ts in _seen_alert_times.items() if ts.timestamp() < cutoff]
    for aid in stale:
        _seen_alert_ids.discard(aid)
        _seen_alert_times.pop(aid, None)


def _is_duplicate(alert_id: str, *, now: datetime | None = None) -> bool:
    """Return True if this alert id was seen recently."""
    if alert_id not in _seen_alert_ids:
        return False
    ts = _seen_alert_times.get(alert_id)
    if ts is None:
        return False
    current = now or datetime.now(UTC)
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=UTC)
    return (current - ts).total_seconds() <= IDEMPOTENCY_WINDOW_SECONDS


# Supported symbols → canonical Sapphire format
SYMBOL_MAP = {
    "ETHBTC": "ETHBTC",
    "SOLBTC": "SOLBTC",
    "ZECBTC": "ZECBTC",
    "BTCUSDT": "BTCUSDT",
    "ETHUSDT": "ETHUSDT",
    "HYPEUSDT": "HYPEUSDT",
    "SOLUSDT": "SOLUSDT",
    "HYPERUSDT": "HYPEUSDT",
}

VALID_ACTIONS = [
    "buy",
    "sell",
    "long",
    "short",
    "exit",
    "close",
    "entry_long",
    "entry_short",
    "exit_long",
    "exit_short",
]
SYMBOL_RE = re.compile(r"^[A-Z0-9:._/\-]{1,40}$")
SECRET_FIELDS = {"secret", "webhook_secret", "passphrase"}
SECRET_FIELD_RE = re.compile(r"(secret|token|passphrase|password|private[_-]?key)", re.I)

# ─── Logging ──────────────────────────────────────────────────────────────────

_log_dir = os.path.dirname(LOG_FILE)
if _log_dir:
    os.makedirs(_log_dir, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
log = logging.getLogger("sapphire-webhook")

# ─── Durable alert log ────────────────────────────────────────────────────────

_alert_log_lock = asyncio.Lock()


def _ensure_alert_log_dir() -> None:
    log_dir = os.path.dirname(ALERT_LOG_FILE)
    if log_dir:
        os.makedirs(log_dir, exist_ok=True)


def _alert_log_size_bytes() -> int:
    try:
        return os.path.getsize(ALERT_LOG_FILE)
    except FileNotFoundError:
        return 0
    except OSError:
        return 0


def _rotate_alert_log() -> None:
    """Simple rotation: move current file to .1, .2, .3, etc."""
    if _alert_log_size_bytes() < ALERT_LOG_MAX_BYTES:
        return
    for i in range(ALERT_LOG_BACKUP_COUNT, 0, -1):
        src = f"{ALERT_LOG_FILE}.{i}"
        dst = f"{ALERT_LOG_FILE}.{i + 1}"
        if os.path.exists(src):
            try:
                os.replace(src, dst)
            except OSError:
                pass
    if os.path.exists(ALERT_LOG_FILE):
        try:
            os.replace(ALERT_LOG_FILE, f"{ALERT_LOG_FILE}.1")
        except OSError:
            pass


async def _append_alert_log(entry: dict[str, Any]) -> None:
    """Append a single alert entry to the durable JSONL log.

    Uses rotation to cap disk usage. Runs under a lock so concurrent alerts
    never interleave JSON lines.
    """
    async with _alert_log_lock:
        await asyncio.to_thread(_ensure_alert_log_dir)
        await asyncio.to_thread(_rotate_alert_log)
        line = json.dumps(entry, default=str, ensure_ascii=False)
        await asyncio.to_thread(_write_alert_log_line, line)


def _write_alert_log_line(line: str) -> None:
    try:
        with open(ALERT_LOG_FILE, "a", encoding="utf-8") as fh:
            fh.write(line + "\n")
            fh.flush()
            os.fsync(fh.fileno())
    except OSError as exc:
        log.warning("Failed to write alert log: %s", exc)


def _read_alert_log_entries(*, limit: int = 100, offset: int = 0) -> list[dict[str, Any]]:
    """Read durable alert log newest-first."""
    entries: list[dict[str, Any]] = []
    try:
        if not os.path.exists(ALERT_LOG_FILE):
            return entries
        with open(ALERT_LOG_FILE, encoding="utf-8", errors="ignore") as fh:
            for raw_line in fh:
                raw_line = raw_line.strip()
                if not raw_line:
                    continue
                try:
                    entries.append(json.loads(raw_line))
                except json.JSONDecodeError:
                    continue
    except OSError:
        return entries
    # Newest first.
    entries.reverse()
    if offset:
        entries = entries[offset:]
    return entries[:limit]


# ─── Data Models ──────────────────────────────────────────────────────────────


def _canonical_symbol(raw_symbol: Any) -> str:
    raw = str(raw_symbol or "").strip().upper()
    symbol = raw.split(":")[-1] if ":" in raw else raw
    return SYMBOL_MAP.get(symbol, symbol)


def _parse_optional_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(parsed):
        return None
    return parsed


def _redacted_payload_summary(data: Any) -> dict[str, Any]:
    if not isinstance(data, dict):
        return {"payload_type": type(data).__name__}
    summary: dict[str, Any] = {}
    for key in ("symbol", "action", "exchange", "interval", "source", "strategy"):
        if key in data:
            summary[key] = data.get(key)
    for key in data:
        if SECRET_FIELD_RE.search(str(key)):
            summary[str(key)] = "<redacted>"
    summary["keys"] = sorted(str(key) for key in data)[:30]
    return summary


def verify_webhook_secret(data: dict[str, Any], headers: Any | None = None) -> bool:
    """Return true when ingress is allowed by the configured shared secret."""
    expected = str(WEBHOOK_SECRET or "").strip()
    if not expected:
        return True
    header_candidates = []
    if headers is not None:
        for name in (
            "X-Sapphire-Webhook-Secret",
            "X-TradingView-Secret",
            "X-Webhook-Secret",
        ):
            value = headers.get(name) if hasattr(headers, "get") else None
            if value:
                header_candidates.append(value)
    body_candidates = [
        value for key, value in data.items() if str(key).strip().lower() in SECRET_FIELDS
    ]
    for candidate in [*header_candidates, *body_candidates]:
        if candidate is not None and hmac.compare_digest(str(candidate), expected):
            return True
    return False


@dataclass
class TradingViewAlert:
    symbol: str
    action: str
    price: float
    timestamp: str
    message: str = ""
    exchange: str = ""
    interval: str = ""
    z_score: float | None = None
    confidence: float | None = None
    regime_score: float | None = None
    quantity: float | None = None
    ai_verdict: str | None = None  # Ollama enrichment

    def to_dict(self):
        return asdict(self)

    @classmethod
    def from_webhook(cls, data: dict) -> "TradingViewAlert":
        symbol = _canonical_symbol(data.get("symbol"))
        return cls(
            symbol=symbol,
            action=str(data.get("action", "")).lower(),
            price=_parse_optional_float(data.get("price")) or 0.0,
            timestamp=data.get("time", datetime.now(UTC).isoformat()),
            message=str(data.get("message", ""))[:500],
            exchange=str(data.get("exchange", ""))[:40],
            interval=str(data.get("interval", ""))[:40],
            z_score=_parse_optional_float(data.get("z_score")),
            confidence=_parse_optional_float(data.get("confidence")),
            regime_score=_parse_optional_float(data.get("regime_score")),
            quantity=_parse_optional_float(data.get("quantity")),
        )


# ─── In-memory state ──────────────────────────────────────────────────────────

alert_history: list[dict] = []
stats = {
    "total": 0,
    "published": 0,
    "errors": 0,
    "ai_enriched": 0,
    "pubsub_success": 0,
    "gateway_fallback": 0,
}


# ─── Pub/Sub singleton ────────────────────────────────────────────────────────

_publisher: Optional["pubsub_v1.PublisherClient"] = None  # type: ignore
_firestore_client = None
_capability_sync_task: asyncio.Task[Any] | None = None
_capability_snapshot: dict[str, Any] = {
    "available": False,
    "last_sync": None,
    "error": "not_initialized",
}


def _short_path_label(raw_path: Any) -> str | None:
    if raw_path in (None, ""):
        return None
    parts = [
        part
        for part in str(raw_path).replace("\\", "/").split("/")
        if part and not part.endswith(":")
    ]
    if not parts:
        return None
    return ".../" + "/".join(parts[-3:])


def _path_leaf(raw_path: Any) -> str | None:
    if raw_path in (None, ""):
        return None
    parts = [
        part
        for part in str(raw_path).replace("\\", "/").split("/")
        if part and not part.endswith(":")
    ]
    return parts[-1] if parts else None


def _parse_iso_timestamp(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


def _seconds_between(started_at: Any, finished_at: Any) -> float | None:
    started = _parse_iso_timestamp(started_at)
    finished = _parse_iso_timestamp(finished_at)
    if not started or not finished:
        return None
    return round(max((finished - started).total_seconds(), 0.0), 3)


def _age_seconds(generated_at: Any, *, now: datetime | None = None) -> int | None:
    generated = _parse_iso_timestamp(generated_at)
    if not generated:
        return None
    current = now or datetime.now(UTC)
    if generated.tzinfo is None:
        generated = generated.replace(tzinfo=UTC)
    return max(0, int((current - generated).total_seconds()))


def _research_worker_freshness(generated_at: Any) -> dict[str, Any]:
    age = _age_seconds(generated_at)
    status = "unknown"
    if age is not None:
        status = "fresh" if age <= RESEARCH_WORKER_MAX_AGE_SECONDS else "stale"
    return {
        "status": status,
        "age_seconds": age,
        "max_age_seconds": RESEARCH_WORKER_MAX_AGE_SECONDS,
        "fresh": status == "fresh",
    }


_TASK_RESULT_LABELS = {
    0: "success",
    267009: "running",
    267011: "not_started",
}


def _task_result_label(value: Any) -> str:
    try:
        code = int(value)
    except (TypeError, ValueError):
        return "unknown"
    return _TASK_RESULT_LABELS.get(code, f"code_{code}")


def _task_result_ok(value: Any) -> bool:
    return _task_result_label(value) in {"success", "running", "not_started"}


def _query_research_worker_task() -> dict[str, Any]:
    """Read Task Scheduler state without exposing task arguments."""
    if platform.system().lower() != "windows":
        return {
            "task_name": RESEARCH_WORKER_TASK_NAME,
            "status": "unavailable",
            "reason": "not_windows",
        }

    task_name_json = json.dumps(RESEARCH_WORKER_TASK_NAME)
    script = f"""
$ProgressPreference = 'SilentlyContinue'
$taskName = {task_name_json}
$task = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
$info = Get-ScheduledTaskInfo -TaskName $taskName -ErrorAction SilentlyContinue
if (-not $task) {{
  $payload = [pscustomobject]@{{ task_name = $taskName; status = 'missing' }}
}} else {{
  $payload = [pscustomobject]@{{
    task_name = $taskName
    status = 'ok'
    state = [string]$task.State
    last_run_time = if ($info -and $info.LastRunTime) {{ $info.LastRunTime.ToString('o') }} else {{ $null }}
    next_run_time = if ($info -and $info.NextRunTime) {{ $info.NextRunTime.ToString('o') }} else {{ $null }}
    last_task_result = if ($info) {{ $info.LastTaskResult }} else {{ $null }}
  }}
}}
$payload | ConvertTo-Json -Depth 4
"""
    encoded = base64.b64encode(script.encode("utf-16le")).decode("ascii")
    try:
        result = subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-EncodedCommand", encoded],
            capture_output=True,
            check=False,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return {
            "task_name": RESEARCH_WORKER_TASK_NAME,
            "status": "unavailable",
            "reason": f"{exc.__class__.__name__}: {exc}"[:160],
        }
    if result.returncode != 0:
        return {
            "task_name": RESEARCH_WORKER_TASK_NAME,
            "status": "unavailable",
            "reason": (result.stderr or "powershell_failed")[-160:],
        }
    raw_stdout = result.stdout.strip()
    start = raw_stdout.find("{")
    end = raw_stdout.rfind("}")
    if start == -1 or end == -1:
        return {
            "task_name": RESEARCH_WORKER_TASK_NAME,
            "status": "unavailable",
            "reason": "empty_task_json",
        }
    try:
        payload = json.loads(raw_stdout[start : end + 1])
    except json.JSONDecodeError as exc:
        return {
            "task_name": RESEARCH_WORKER_TASK_NAME,
            "status": "unavailable",
            "reason": f"JSONDecodeError: {exc}"[:160],
        }
    if not isinstance(payload, dict):
        return {
            "task_name": RESEARCH_WORKER_TASK_NAME,
            "status": "unavailable",
            "reason": "unexpected_task_payload",
        }
    label = _task_result_label(payload.get("last_task_result"))
    payload["last_task_result_label"] = label
    payload["last_result_ok"] = _task_result_ok(payload.get("last_task_result"))
    return payload


def _latest_research_worker_manifest(root: Path) -> Path | None:
    if not root.exists() or not root.is_dir():
        return None
    candidates = [
        child / "manifest.json"
        for child in root.iterdir()
        if child.is_dir() and (child / "manifest.json").is_file()
    ]
    candidates.sort(key=lambda path: (path.stat().st_mtime, path.parent.name), reverse=True)
    return candidates[0] if candidates else None


def _research_worker_empty_payload(reason: str) -> dict[str, Any]:
    return {
        "mode": "read_only_windows_research_worker",
        "status": "no_data",
        "source": "windows_webhook",
        "reason": reason,
        "freshness": _research_worker_freshness(None),
        "schedule": _query_research_worker_task(),
        "summary": {
            "command_count": 0,
            "failed_count": 0,
            "artifact_count": 0,
            "safety_clear": False,
        },
        "safety": {
            "paper_only": False,
            "live_trading_enabled": False,
            "telegram_sends_enabled": False,
        },
        "commands": [],
        "artifacts": [],
    }


def _build_research_worker_payload(
    manifest: dict[str, Any],
    *,
    manifest_path: Path | None = None,
    schedule: dict[str, Any] | None = None,
) -> dict[str, Any]:
    commands = [item for item in manifest.get("commands", []) if isinstance(item, dict)]
    artifacts = (
        list(manifest.get("artifacts", [])) if isinstance(manifest.get("artifacts"), list) else []
    )
    safety = {
        "paper_only": manifest.get("paper_only") is True,
        "live_trading_enabled": manifest.get("live_trading_enabled") is True,
        "telegram_sends_enabled": manifest.get("telegram_sends_enabled") is True,
    }
    safety_clear = (
        safety["paper_only"]
        and not safety["live_trading_enabled"]
        and not safety["telegram_sends_enabled"]
    )
    command_rows: list[dict[str, Any]] = []
    failed_count = 0
    for command in commands:
        exit_code = command.get("exit_code")
        failed = exit_code not in (0, "0")
        failed_count += int(failed)
        command_rows.append(
            {
                "name": str(command.get("name") or "unknown"),
                "status": "failed" if failed else "ok",
                "exit_code": exit_code,
                "started_at": command.get("started_at"),
                "finished_at": command.get("finished_at"),
                "duration_seconds": _seconds_between(
                    command.get("started_at"), command.get("finished_at")
                ),
                "log_path_label": _short_path_label(command.get("log_path")),
            }
        )

    freshness = _research_worker_freshness(manifest.get("generated_at"))
    status = "ok"
    if not safety_clear:
        status = "unsafe"
    elif failed_count:
        status = "degraded"
    elif freshness["status"] == "stale":
        status = "stale"

    return {
        "mode": "read_only_windows_research_worker",
        "status": status,
        "source": "windows_webhook",
        "generated_at": manifest.get("generated_at"),
        "host": manifest.get("host"),
        "git_sha": manifest.get("git_sha"),
        "git_sha_short": str(manifest.get("git_sha") or "")[:8] or None,
        "run_id": _path_leaf(manifest.get("run_dir")),
        "manifest_path_label": _short_path_label(manifest_path),
        "run_dir_label": _short_path_label(manifest.get("run_dir")),
        "output_root_label": _short_path_label(manifest.get("output_root")),
        "freshness": freshness,
        "schedule": schedule if schedule is not None else _query_research_worker_task(),
        "summary": {
            "command_count": len(command_rows),
            "failed_count": failed_count,
            "artifact_count": len(artifacts),
            "safety_clear": safety_clear,
        },
        "safety": safety,
        "commands": command_rows,
        "artifacts": [
            {
                "kind": _path_leaf(path) or "artifact",
                "path_label": _short_path_label(path),
            }
            for path in artifacts
        ],
    }


def _build_research_worker_status() -> dict[str, Any]:
    root = Path(RESEARCH_WORKER_OUTPUT_ROOT)
    schedule = _query_research_worker_task()
    manifest_path = _latest_research_worker_manifest(root)
    if manifest_path is None:
        payload = _research_worker_empty_payload("no manifest on disk")
        payload["output_root_label"] = _short_path_label(root)
        payload["schedule"] = schedule
        return payload
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
    except (json.JSONDecodeError, OSError) as exc:
        payload = _research_worker_empty_payload("latest manifest unreadable")
        payload["error"] = f"{exc.__class__.__name__}: {exc}"[:200]
        payload["manifest_path_label"] = _short_path_label(manifest_path)
        payload["schedule"] = schedule
        return payload
    if not isinstance(manifest, dict):
        payload = _research_worker_empty_payload("latest manifest is not an object")
        payload["manifest_path_label"] = _short_path_label(manifest_path)
        payload["schedule"] = schedule
        return payload
    return _build_research_worker_payload(manifest, manifest_path=manifest_path, schedule=schedule)


def _get_publisher():
    return None  # Pub/Sub removed — on-prem Tailscale routing


def _get_firestore_client():
    return None  # Firestore removed — on-prem mode


async def _fetch_ollama_models() -> list[dict]:
    """Best-effort local Ollama model inventory."""
    try:
        async with httpx.AsyncClient(timeout=2.5) as client:
            response = await client.get(f"{OLLAMA_URL}/api/tags")
            if response.status_code != 200:
                return []
            payload = (
                response.json()
                if response.headers.get("content-type", "").startswith("application/json")
                else {}
            )
            models = payload.get("models", []) if isinstance(payload, dict) else []
            rows: list[dict] = []
            for item in models:
                if not isinstance(item, dict):
                    continue
                rows.append(
                    {
                        "name": item.get("name"),
                        "size": item.get("size"),
                        "modified_at": item.get("modified_at"),
                    }
                )
            return rows
    except Exception:
        return []


def _detect_gpu_inventory() -> list[dict]:
    """Best-effort GPU inventory via nvidia-smi (Windows host)."""
    command = [
        "nvidia-smi",
        "--query-gpu=name,memory.total,driver_version",
        "--format=csv,noheader,nounits",
    ]
    try:
        result = subprocess.run(command, capture_output=True, text=True, check=True, timeout=4)
    except Exception:
        return []
    rows: list[dict] = []
    for line in result.stdout.splitlines():
        text = line.strip()
        if not text:
            continue
        parts = [p.strip() for p in text.split(",")]
        if len(parts) < 3:
            continue
        rows.append(
            {
                "name": parts[0],
                "memory_total_mb": float(parts[1])
                if parts[1].replace(".", "", 1).isdigit()
                else parts[1],
                "driver_version": parts[2],
            }
        )
    return rows


async def _probe_local_service(url: str) -> dict:
    started = datetime.now(UTC)
    try:
        async with httpx.AsyncClient(timeout=LOCAL_SERVICE_PROBE_TIMEOUT_SECONDS) as client:
            response = await client.get(url)
            latency_ms = int((datetime.now(UTC) - started).total_seconds() * 1000)
            body_status = None
            if response.headers.get("content-type", "").startswith("application/json"):
                with contextlib.suppress(Exception):
                    payload = response.json()
                    if isinstance(payload, dict):
                        body_status = str(payload.get("status") or "").lower() or None
            healthy = response.status_code == 200 and body_status not in {
                "degraded",
                "down",
                "error",
                "failed",
                "unhealthy",
            }
            return {
                "healthy": healthy,
                "status_code": response.status_code,
                "status": body_status,
                "latency_ms": latency_ms,
            }
    except Exception as exc:
        latency_ms = int((datetime.now(UTC) - started).total_seconds() * 1000)
        return {
            "healthy": False,
            "status_code": None,
            "latency_ms": latency_ms,
            "error": str(exc)[:180],
        }


async def _collect_windows_lab_snapshot() -> dict:
    """Collect local workstation capabilities and service health."""
    started = datetime.now(UTC)
    ollama_models = await _fetch_ollama_models()
    gpu_rows = await asyncio.to_thread(_detect_gpu_inventory)
    webhook_probe, tv_probe, ollama_probe = await asyncio.gather(
        _probe_local_service(f"http://127.0.0.1:{WEBHOOK_PORT}/status"),
        _probe_local_service("http://127.0.0.1:8081/health"),
        _probe_local_service(f"{OLLAMA_URL}/api/tags"),
    )
    snapshot = {
        "available": True,
        "updated_at": datetime.now(UTC).isoformat(),
        "host": {
            "hostname": socket.gethostname(),
            "os": platform.platform(),
            "python_version": platform.python_version(),
            "cpu_count": os.cpu_count(),
            "cpu_name": platform.processor(),
        },
        "hardware": {
            "gpu": gpu_rows,
            "gpu_count": len(gpu_rows),
        },
        "models": {
            "ollama_model_count": len(ollama_models),
            "ollama_models": ollama_models[:40],
        },
        "services": {
            "windows_webhook": webhook_probe,
            "windows_tv_agent": tv_probe,
            "windows_ollama": ollama_probe,
        },
        "stats": {
            "signals_total": stats["total"],
            "signals_published": stats["published"],
            "pubsub_success": stats["pubsub_success"],
            "gateway_fallback": stats["gateway_fallback"],
        },
        "source": "windows_webhook_receiver",
    }
    snapshot["collection_latency_ms"] = int((datetime.now(UTC) - started).total_seconds() * 1000)
    return snapshot


def _write_windows_capabilities(snapshot: dict):
    """Persist latest workstation capabilities into Firestore."""
    client = _get_firestore_client()
    if client is None:
        return
    try:
        client.collection(EDGE_CAPABILITIES_COLLECTION).document("windows_lab").set(
            snapshot, merge=True
        )
    except Exception as exc:
        log.warning("Windows capabilities Firestore write failed: %s", exc)


async def _capability_sync_loop():
    """Background sync loop for Windows AI lab capabilities."""
    global _capability_snapshot
    while True:
        try:
            snapshot = await _collect_windows_lab_snapshot()
            _capability_snapshot = snapshot
            _write_windows_capabilities(snapshot)
        except Exception as exc:
            _capability_snapshot = {
                "available": False,
                "updated_at": datetime.now(UTC).isoformat(),
                "error": str(exc)[:240],
                "source": "windows_webhook_receiver",
            }
            log.warning("Capability sync error: %s", exc)
        await asyncio.sleep(max(60, CAPABILITY_SYNC_INTERVAL_SECONDS))


def write_system_log(
    *,
    level: str,
    message: str,
    event_type: str,
    signal_id: str | None = None,
    symbol: str | None = None,
    action: str | None = None,
    metadata: dict | None = None,
):
    """Best-effort Firestore log emit used by unified operator frontend."""
    client = _get_firestore_client()
    if client is None:
        return

    payload = {
        "timestamp": datetime.now(UTC).isoformat(),
        "level": str(level or "INFO").upper(),
        "service": "windows_webhook",
        "message": str(message or "")[:500],
        "event_type": str(event_type or "event"),
        "signal_id": signal_id,
        "symbol": symbol,
        "action": action,
        "metadata": metadata or {},
    }
    try:
        client.collection(SYSTEM_LOGS_COLLECTION).add(payload)
    except Exception as exc:
        log.warning("Firestore log write failed: %s", exc)


# ─── Signal mapping ───────────────────────────────────────────────────────────


def map_signal(action: str) -> tuple[str, str]:
    """Map TradingView action → (TradeSide, SignalType) strings."""
    a = action.lower()
    if a in ("buy", "long", "entry_long"):
        return "BUY", "entry"
    if a in ("sell", "short", "entry_short"):
        return "SELL", "entry"
    if a in ("exit_long", "close"):
        # Closing a long → sell to exit
        return "SELL", "exit"
    if a == "exit_short":
        # Closing a short → buy to exit
        return "BUY", "exit"
    # Generic exit
    return "SELL", "exit"


def build_trade_signal(alert: TradingViewAlert) -> dict:
    """
    Construct a TradeSignal-compatible dict from a TradingViewAlert.
    Matches services/shared/models/trade_models.py::TradeSignal schema.
    """
    side, signal_type = map_signal(alert.action)
    return {
        "signal_id": str(uuid.uuid4()),
        "symbol": alert.symbol,
        "side": side,
        "signal_type": signal_type,
        "confidence": alert.confidence if alert.confidence is not None else 0.5,
        "source": "tradingview-workbench",
        "target_platforms": [],  # empty = all platforms consume
        "entry_price": alert.price,
        "stop_loss": None,
        "take_profit": None,
        "quantity": alert.quantity,
        "leverage": None,
        "timestamp": alert.timestamp,
        "metadata": {
            "z_score": alert.z_score,
            "regime_score": alert.regime_score,
            "ai_verdict": alert.ai_verdict,
            "exchange": alert.exchange,
            "interval": alert.interval,
            "message": alert.message,
            "origin": "windows_pc_webhook",
            "requested_quantity": alert.quantity,
            # Safety flag — bots should treat confidence < 0.70 as paper only
            "dry_run": bool(alert.confidence is not None and alert.confidence < 0.70),
        },
    }


# ─── Pub/Sub publish ──────────────────────────────────────────────────────────


def _resolve_signal_targets() -> list[tuple[str, str]]:
    """Build target list from SIGNAL_TARGETS env, then legacy env vars."""
    targets: list[tuple[str, str]] = []
    seen_urls: set[str] = set()

    raw = os.getenv("SIGNAL_TARGETS", "").strip()
    if raw:
        for item in raw.split(","):
            item = item.strip()
            if "=" not in item:
                continue
            name, url = item.split("=", 1)
            name = name.strip()
            url = url.strip().rstrip("/")
            if not name or not url or url in seen_urls:
                continue
            seen_urls.add(url)
            targets.append((name, url))
        if targets:
            return targets

    # Legacy env-driven fallback (no hardcoded defaults).
    if SIGNAL_LOGGER_MAC:
        targets.append(("mac-logger", f"{SIGNAL_LOGGER_MAC}/api/signals"))
    if ALPHA_ENGINE_RARI2:
        targets.append(("rari2", f"{ALPHA_ENGINE_RARI2}/api/signals/create"))
    if ALPHA_ENGINE_RARI1:
        targets.append(("rari1", f"{ALPHA_ENGINE_RARI1}/api/signals/create"))
    return targets


async def publish_signal(signal: dict) -> dict:
    """
    On-prem signal routing over Tailscale. Targets are env-driven via
    SIGNAL_TARGETS or legacy ALPHA_ENGINE_*/SIGNAL_LOGGER_MAC variables.
    """
    targets = _resolve_signal_targets()
    if not targets:
        log.warning("No signal targets configured; signal logged but not routed")
        stats["errors"] += 1
        return {"published": False, "channel": "none", "targets": [], "reason": "no_targets"}

    headers = {"Content-Type": "application/json"}
    if SAPPHIRE_CONTROL_TOKEN:
        headers["X-Sapphire-Control-Token"] = SAPPHIRE_CONTROL_TOKEN
    results = []
    any_ok = False
    async with httpx.AsyncClient(timeout=8.0) as client:
        for name, url in targets:
            payload = dict(signal)
            # The Mac signal logger validates the webhook secret in the body.
            # Include it so internal routing over localhost/Tailscale succeeds.
            if WEBHOOK_SECRET and url.endswith("/api/signals"):
                payload["secret"] = WEBHOOK_SECRET
            try:
                r = await client.post(url, json=payload, headers=headers)
                ok = r.status_code < 300
                if ok:
                    any_ok = True
                    stats["pubsub_success"] += 1
                log.info(
                    "📤 Signal → %s HTTP %d | %s %s",
                    name,
                    r.status_code,
                    signal["side"],
                    signal["symbol"],
                )
                results.append({"target": name, "ok": ok, "http_status": r.status_code})
            except Exception as e:
                log.warning("⚠️  Signal → %s failed: %s", name, e)
                results.append({"target": name, "ok": False, "error": str(e)[:120]})

    if any_ok:
        stats["published"] += 1
        return {"published": True, "channel": "tailscale", "targets": results}
    else:
        stats["errors"] += 1
        return {"published": False, "channel": "none", "targets": results}


# Kept for backwards compat — removed GCP gateway
async def forward_to_gateway(signal: dict) -> dict:
    return await publish_signal(signal)


# ─── Ollama enrichment ────────────────────────────────────────────────────────


async def ollama_enrich(alert: TradingViewAlert) -> str | None:
    """Ask local Ollama (gemma3:27b) for a one-sentence signal verdict."""
    prompt = (
        f"Trading signal received: {alert.action.upper()} {alert.symbol} "
        f"@ ${alert.price}. "
        + (f"Z-score: {alert.z_score:.2f}. " if alert.z_score else "")
        + (f"Confidence: {alert.confidence:.0%}. " if alert.confidence else "")
        + (f"Regime: {alert.regime_score:.2f}. " if alert.regime_score else "")
        + "In one sentence: is this signal high quality? "
        "Answer with CONFIRM, CAUTION, or REJECT and one reason."
    )
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            r = await client.post(
                f"{OLLAMA_URL}/api/generate",
                json={"model": "gemma3:27b", "prompt": prompt, "stream": False},
            )
            if r.status_code == 200:
                verdict = r.json().get("response", "").strip()
                log.info("🤖 Ollama: %s", verdict[:120])
                stats["ai_enriched"] += 1
                return verdict[:200]
    except Exception as e:
        log.warning("Ollama enrichment skipped: %s", e)
    return None


# ─── App lifecycle ────────────────────────────────────────────────────────────


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _capability_sync_task
    log.info("🚀 Sapphire Webhook Receiver starting on port %d", WEBHOOK_PORT)
    log.info("Signal routing:  rari1=%s  rari2=%s", ALPHA_ENGINE_RARI1, ALPHA_ENGINE_RARI2)
    log.info("Ollama endpoint: %s", OLLAMA_URL)
    log.info("On-prem mode:    Tailscale routing active (no GCP)")
    _capability_sync_task = asyncio.create_task(_capability_sync_loop())
    yield
    if _capability_sync_task is not None:
        _capability_sync_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await _capability_sync_task
        _capability_sync_task = None
    log.info("Webhook receiver shutting down")


app = FastAPI(
    title="Sapphire Webhook Receiver",
    version="2.0.0",
    lifespan=lifespan,
)


# ─── Validation ───────────────────────────────────────────────────────────────


def validate_payload(data: dict) -> bool:
    if not isinstance(data, dict):
        return False
    raw_symbol = str(data.get("symbol") or "").strip().upper()
    if not raw_symbol or not SYMBOL_RE.fullmatch(raw_symbol):
        return False
    action = str(data.get("action") or "").strip().lower()
    if action not in VALID_ACTIONS:
        return False
    for key in ("price", "z_score", "confidence", "regime_score", "quantity"):
        if key not in data:
            continue
        value = _parse_optional_float(data.get(key))
        if value is None:
            return False
        if key in {"price", "quantity"} and value < 0:
            return False
        if key == "confidence" and not 0 <= value <= 1:
            return False
    return True


# ─── Routes ───────────────────────────────────────────────────────────────────


@app.get("/", response_class=HTMLResponse)
async def dashboard():
    def _row(h: dict) -> str:
        color = "#00ff88" if h.get("published") else "#666"
        channel = h.get("channel", "")
        tick = ("✓ " + channel) if h.get("published") else "–"
        verdict = (h["alert"].get("ai_verdict") or "–")[:80]
        return (
            "<tr>"
            f"<td>{h['received_at'][:19]}</td>"
            f"<td>{h['alert']['action'].upper()}</td>"
            f"<td>{h['alert']['symbol']}</td>"
            f"<td>${h['alert']['price']}</td>"
            f"<td>{h['alert'].get('confidence', '–')}</td>"
            f"<td style='max-width:200px;overflow:hidden;font-size:11px'>{verdict}</td>"
            f"<td style='color:{color}'>{tick}</td>"
            "</tr>"
        )

    history_rows = "".join(_row(h) for h in reversed(alert_history[-20:]))
    pubsub_badge = (
        "<span style='color:#00ff88'>● Pub/Sub live</span>"
        if _PUBSUB_AVAILABLE
        else "<span style='color:#ff6600'>● Gateway fallback mode</span>"
    )
    return f"""
    <html><head><title>Sapphire Webhook</title>
    <meta http-equiv="refresh" content="10">
    <style>
      body{{font-family:monospace;background:#0a0a0a;color:#00ff88;padding:20px}}
      table{{border-collapse:collapse;width:100%}}
      th,td{{border:1px solid #333;padding:6px 10px;text-align:left}}
      th{{background:#111}}h1{{color:#00aaff}}
      .stat{{display:inline-block;margin-right:20px;color:#aaa}}
      .stat span{{color:#fff;font-weight:bold}}
    </style></head>
    <body>
    <h1>🔷 Sapphire Webhook Receiver v2</h1>
    <p>{pubsub_badge}</p>
    <p>
      <span class='stat'>Total <span>{stats["total"]}</span></span>
      <span class='stat'>Published <span>{stats["published"]}</span></span>
      <span class='stat'>Pub/Sub <span>{stats["pubsub_success"]}</span></span>
      <span class='stat'>Gateway <span>{stats["gateway_fallback"]}</span></span>
      <span class='stat'>AI-enriched <span>{stats["ai_enriched"]}</span></span>
      <span class='stat'>Errors <span>{stats["errors"]}</span></span>
    </p>
    <table>
      <tr><th>Time</th><th>Action</th><th>Symbol</th><th>Price</th>
          <th>Conf</th><th>AI Verdict</th><th>Published</th></tr>
      {history_rows or "<tr><td colspan=7>No alerts yet</td></tr>"}
    </table>
    </body></html>
    """


@app.get("/status")
async def status():
    services = (_capability_snapshot or {}).get("services", {})
    capabilities = (_capability_snapshot or {}).get("models", {})
    return {
        "status": "active",
        "version": "2.0.0",
        "stats": stats,
        "signal_routing": "tailscale",
        "alpha_engine_rari1": ALPHA_ENGINE_RARI1,
        "alpha_engine_rari2": ALPHA_ENGINE_RARI2,
        "ollama_url": OLLAMA_URL,
        "services": services,
        "capabilities": {
            "ollama_model_count": capabilities.get("ollama_model_count", 0),
            "gpu_count": ((_capability_snapshot or {}).get("hardware", {}) or {}).get(
                "gpu_count", 0
            ),
            "last_sync": (_capability_snapshot or {}).get("updated_at"),
        },
        "research_worker": _build_research_worker_status(),
        "supported_actions": VALID_ACTIONS,
        "symbol_map": SYMBOL_MAP,
    }


@app.get("/health")
async def health():
    services = (_capability_snapshot or {}).get("services", {})
    webhook_ok = services.get("windows_webhook", {}).get("healthy", True)
    return {
        "status": "healthy" if webhook_ok else "degraded",
        "service": "windows_webhook",
        "timestamp": datetime.now(UTC).isoformat(),
    }


@app.get("/webhook/health")
async def webhook_health():
    services = (_capability_snapshot or {}).get("services", {})
    return {
        "status": "healthy",
        "service": "windows_webhook",
        "version": "2.0.0",
        "timestamp": datetime.now(UTC).isoformat(),
        "services": services,
        "stats": stats,
        "capabilities": {
            "last_sync": (_capability_snapshot or {}).get("updated_at"),
            "available": bool((_capability_snapshot or {}).get("available")),
            "ollama_model_count": ((_capability_snapshot or {}).get("models", {}) or {}).get(
                "ollama_model_count", 0
            ),
            "gpu_count": ((_capability_snapshot or {}).get("hardware", {}) or {}).get(
                "gpu_count", 0
            ),
        },
        "research_worker": _build_research_worker_status(),
    }


@app.get("/windows/capabilities")
async def windows_capabilities():
    snapshot = dict(_capability_snapshot or {})
    if not snapshot:
        snapshot = {"available": False, "error": "capabilities_not_ready"}
    snapshot["timestamp"] = datetime.now(UTC).isoformat()
    return snapshot


@app.get("/windows/research-worker/latest")
async def windows_research_worker_latest():
    return _build_research_worker_status()


@app.get("/alerts")
async def get_alerts(limit: int = 20, persisted: bool = False, offset: int = 0):
    """Return recent alerts.

    By default returns the in-memory sliding window (fast). Set persisted=true
    to read from the durable JSONL alert log instead.
    """
    if persisted:
        entries = await asyncio.to_thread(_read_alert_log_entries, limit=limit, offset=offset)
        total = await asyncio.to_thread(_alert_log_total_count)
        return {
            "alerts": entries,
            "total": total,
            "source": "durable_log",
            "log_file": ALERT_LOG_FILE,
            "limit": limit,
            "offset": offset,
        }
    return {
        "alerts": alert_history[-limit:],
        "total": len(alert_history),
        "source": "memory",
        "limit": limit,
    }


def _alert_log_total_count() -> int:
    """Count lines in the durable alert log."""
    count = 0
    try:
        if not os.path.exists(ALERT_LOG_FILE):
            return 0
        with open(ALERT_LOG_FILE, encoding="utf-8", errors="ignore") as fh:
            for line in fh:
                if line.strip():
                    count += 1
    except OSError:
        pass
    return count


@app.post("/webhook/tradingview")
async def receive_tradingview(request: Request, background_tasks: BackgroundTasks):
    """Main TradingView webhook endpoint — validates, enriches, publishes."""
    try:
        body = await request.body()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid request body")
    if len(body) > MAX_WEBHOOK_BODY_BYTES:
        raise HTTPException(status_code=413, detail="Webhook body too large")
    try:
        data = json.loads(body)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON")
    if not isinstance(data, dict):
        raise HTTPException(status_code=400, detail="Invalid payload — expected JSON object")

    if not verify_webhook_secret(data, request.headers):
        log.warning("TradingView webhook secret rejected: %s", _redacted_payload_summary(data))
        raise HTTPException(status_code=403, detail="Webhook secret rejected")

    if not validate_payload(data):
        log.warning("Invalid payload rejected: %s", _redacted_payload_summary(data))
        raise HTTPException(
            status_code=400,
            detail="Invalid payload — check symbol/action fields",
        )

    alert_id = _alert_fingerprint(data)
    if _is_duplicate(alert_id):
        log.info(
            "🔄 Duplicate alert ignored: %s %s",
            data.get("action", ""),
            data.get("symbol", ""),
        )
        return JSONResponse(
            {
                "status": "duplicate",
                "alert_id": alert_id[:16],
                "detail": "Alert already processed within dedup window",
            },
            status_code=200,
        )

    _record_seen(alert_id)
    alert = TradingViewAlert.from_webhook(data)
    stats["total"] += 1
    log.info(
        "📨 %s %s @ $%s  conf=%s  z=%s",
        alert.action.upper(),
        alert.symbol,
        alert.price,
        alert.confidence,
        alert.z_score,
    )

    # Step 1 — Ollama enrichment (non-blocking but we await it here;
    #           it has an 8s timeout so won't delay the response much)
    alert.ai_verdict = await ollama_enrich(alert)

    # Step 2 — Build TradeSignal dict
    signal = build_trade_signal(alert)

    # Step 3 — Route signal to alpha service over Tailscale
    pub_result = await publish_signal(signal)

    write_system_log(
        level="INFO",
        message=f"Signal received {alert.action.upper()} {alert.symbol}",
        event_type="signal_received",
        signal_id=signal["signal_id"],
        symbol=alert.symbol,
        action=alert.action,
        metadata={
            "channel": pub_result.get("channel"),
            "published": bool(pub_result.get("published")),
            "confidence": alert.confidence,
            "z_score": alert.z_score,
            "regime_score": alert.regime_score,
            "dry_run": signal.get("metadata", {}).get("dry_run", False),
        },
    )

    if pub_result.get("published"):
        write_system_log(
            level="OK",
            message=f"Signal published {alert.symbol}",
            event_type="signal_published",
            signal_id=signal["signal_id"],
            symbol=alert.symbol,
            action=alert.action,
            metadata={
                "channel": pub_result.get("channel"),
                "message_id": pub_result.get("message_id"),
                "dry_run": signal.get("metadata", {}).get("dry_run", False),
            },
        )
    else:
        write_system_log(
            level="ERROR",
            message=f"Signal publish failed {alert.symbol}",
            event_type="signal_publish_failed",
            signal_id=signal["signal_id"],
            symbol=alert.symbol,
            action=alert.action,
            metadata={
                "channel": pub_result.get("channel"),
                "error": pub_result.get("error"),
                "dry_run": signal.get("metadata", {}).get("dry_run", False),
            },
        )

    # Step 4 — Store in local history and durable JSONL log
    entry = {
        "received_at": datetime.now(UTC).isoformat(),
        "alert": alert.to_dict(),
        "published": pub_result.get("published", False),
        "channel": pub_result.get("channel", "none"),
        "pub_detail": pub_result,
        "signal_id": signal["signal_id"],
    }
    alert_history.append(entry)
    if len(alert_history) > MAX_HISTORY:
        alert_history.pop(0)
    await _append_alert_log(entry)

    return JSONResponse(
        {
            "status": "ok",
            "alert_id": stats["total"],
            "signal_id": signal["signal_id"],
            "symbol": alert.symbol,
            "action": alert.action,
            "side": signal["side"],
            "signal_type": signal["signal_type"],
            "ai_verdict": alert.ai_verdict,
            "publish": pub_result,
        }
    )


# ─── Entry point ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    uvicorn.run(
        app,
        host="0.0.0.0",  # nosec B104 - Windows receiver is firewall/Tailscale scoped.
        port=WEBHOOK_PORT,
        log_level="info",
        access_log=True,
    )
