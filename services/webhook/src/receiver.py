#!/usr/bin/env python3
"""Sapphire Webhook Receiver — Windows PC (port 9090).

Receives TradingView alerts, validates HMAC, optionally enriches via local
Ollama, then forwards to the Sapphire signal logger on Mac (Tailscale
100.67.171.79:18081). Fully on-prem — no GCP Pub/Sub.

Signal flow:
  TradingView → POST /webhook/tradingview (this service, Windows, :9090)
                → HMAC validate + optional Ollama enrichment
                → POST http://100.67.171.79:18081/api/signals  ← Mac signal logger
"""

import asyncio
import contextlib
import json
import logging
import os
import platform
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
MAX_HISTORY = 200

# On-prem signal routing — api-gateway endpoints over Tailscale
# POST /api/signals/create with X-Sapphire-Control-Token header
ALPHA_ENGINE_RARI1 = os.getenv("ALPHA_ENGINE_RARI1", "http://100.120.191.1:18080")
ALPHA_ENGINE_RARI2 = os.getenv("ALPHA_ENGINE_RARI2", "http://100.87.225.89:18080")
# Mac signal logger — primary target now that Pis are decommissioned
SIGNAL_LOGGER_MAC = os.getenv("SIGNAL_LOGGER_MAC", "http://100.67.171.79:18081")
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

# ─── Data Models ──────────────────────────────────────────────────────────────


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
        raw_symbol = data.get("symbol", "").upper()
        symbol = raw_symbol.split(":")[-1] if ":" in raw_symbol else raw_symbol
        symbol = SYMBOL_MAP.get(symbol, symbol)
        return cls(
            symbol=symbol,
            action=data.get("action", "").lower(),
            price=float(data.get("price", 0)),
            timestamp=data.get("time", datetime.now(UTC).isoformat()),
            message=data.get("message", ""),
            exchange=data.get("exchange", ""),
            interval=data.get("interval", ""),
            z_score=float(data["z_score"]) if "z_score" in data else None,
            confidence=float(data["confidence"]) if "confidence" in data else None,
            regime_score=float(data["regime_score"]) if "regime_score" in data else None,
            quantity=float(data["quantity"]) if "quantity" in data else None,
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
) -> dict[str, Any]:
    commands = [item for item in manifest.get("commands", []) if isinstance(item, dict)]
    artifacts = list(manifest.get("artifacts", [])) if isinstance(manifest.get("artifacts"), list) else []
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

    status = "ok"
    if not safety_clear:
        status = "unsafe"
    elif failed_count:
        status = "degraded"

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
    manifest_path = _latest_research_worker_manifest(root)
    if manifest_path is None:
        payload = _research_worker_empty_payload("no manifest on disk")
        payload["output_root_label"] = _short_path_label(root)
        return payload
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        payload = _research_worker_empty_payload("latest manifest unreadable")
        payload["error"] = f"{exc.__class__.__name__}: {exc}"[:200]
        payload["manifest_path_label"] = _short_path_label(manifest_path)
        return payload
    if not isinstance(manifest, dict):
        payload = _research_worker_empty_payload("latest manifest is not an object")
        payload["manifest_path_label"] = _short_path_label(manifest_path)
        return payload
    return _build_research_worker_payload(manifest, manifest_path=manifest_path)


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
            return {
                "healthy": response.status_code == 200,
                "status_code": response.status_code,
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


async def publish_signal(signal: dict) -> dict:
    """
    On-prem signal routing over Tailscale. Targets (in priority order):
    1. Mac signal logger (primary — always-on, logs + AI assessment)
    2. rari2 api-gateway (secondary — if Pi is online)
    3. rari1 api-gateway (tertiary — rari1 is offline per CLAUDE.md, kept for legacy)
    """
    targets = [
        ("mac-logger", f"{SIGNAL_LOGGER_MAC}/api/signals"),
        ("rari2", f"{ALPHA_ENGINE_RARI2}/api/signals/create"),
        ("rari1", f"{ALPHA_ENGINE_RARI1}/api/signals/create"),
    ]
    headers = {"Content-Type": "application/json"}
    if SAPPHIRE_CONTROL_TOKEN:
        headers["X-Sapphire-Control-Token"] = SAPPHIRE_CONTROL_TOKEN
    results = []
    any_ok = False
    async with httpx.AsyncClient(timeout=8.0) as client:
        for name, url in targets:
            try:
                r = await client.post(url, json=signal, headers=headers)
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
    if "symbol" not in data or "action" not in data:
        return False
    return data.get("action", "").lower() in VALID_ACTIONS


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
async def get_alerts(limit: int = 20):
    return {"alerts": alert_history[-limit:], "total": len(alert_history)}


@app.post("/webhook/tradingview")
async def receive_tradingview(request: Request, background_tasks: BackgroundTasks):
    """Main TradingView webhook endpoint — validates, enriches, publishes."""
    try:
        body = await request.body()
        data = json.loads(body)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    if not validate_payload(data):
        log.warning("Invalid payload rejected: %s", str(data)[:100])
        raise HTTPException(
            status_code=400,
            detail="Invalid payload — check symbol/action fields",
        )

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

    # Step 4 — Store in local history
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
        host="0.0.0.0",
        port=WEBHOOK_PORT,
        log_level="info",
        access_log=True,
    )
