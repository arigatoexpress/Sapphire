#!/usr/bin/env python3
"""
Sapphire Webhook Receiver — Windows PC

Receives TradingView alerts, enriches via local Ollama (gemma3:27b),
then publishes to GCP Pub/Sub `trading-signals` topic so the entire
swarm (alpha-engine, bot-lighter, bot-aster) can consume the signal.

Falls back to direct HTTPS → Sapphire Gateway if Pub/Sub is unavailable.

Signal flow:
  TradingView → POST /webhook/tradingview (this service, Windows PC)
                → Ollama enrichment (local, optional)
                → Pub/Sub trading-signals  ← primary
                → Gateway HTTPS fallback   ← if Pub/Sub fails
"""

import json
import logging
import httpx
import asyncio
import uuid
import os
import platform
import socket
import subprocess
from datetime import datetime, timezone
from typing import Any, Optional
from dataclasses import dataclass, asdict
from contextlib import asynccontextmanager
import contextlib

from fastapi import FastAPI, Request, HTTPException, BackgroundTasks
from fastapi.responses import JSONResponse, HTMLResponse
import uvicorn

try:
    from google.cloud import pubsub_v1
    _PUBSUB_AVAILABLE = True
except ImportError:
    pubsub_v1 = None
    _PUBSUB_AVAILABLE = False

try:
    from google.cloud import firestore as g_firestore
    _FIRESTORE_AVAILABLE = True
except ImportError:
    g_firestore = None
    _FIRESTORE_AVAILABLE = False

# ─── Config ───────────────────────────────────────────────────────────────────

WEBHOOK_SECRET  = "sapphire_trading_2024"   # Must match Pine Script alert body
GCP_PROJECT_ID  = "sapphire-479610"
PUBSUB_TOPIC    = f"projects/{GCP_PROJECT_ID}/topics/trading-signals"
GATEWAY_URL     = "https://sapphire-gateway-s77j6bxyra-uc.a.run.app"  # HTTPS fallback
OLLAMA_URL      = "http://localhost:11434"   # Local Ollama (RTX 5070 Ti)
WEBHOOK_PORT    = 9090
LOG_FILE        = os.getenv("WEBHOOK_LOG_FILE", "C:/sapphire/webhook.log")
MAX_HISTORY     = 200
SYSTEM_LOGS_COLLECTION = "system_logs"
EDGE_CAPABILITIES_COLLECTION = "edge_capabilities"
CAPABILITY_SYNC_INTERVAL_SECONDS = int(
    os.getenv("CAPABILITY_SYNC_INTERVAL_SECONDS", "180")
)
LOCAL_SERVICE_PROBE_TIMEOUT_SECONDS = float(
    os.getenv("LOCAL_SERVICE_PROBE_TIMEOUT_SECONDS", "5.0")
)

# Supported symbols → canonical Sapphire format
SYMBOL_MAP = {
    "ETHBTC":   "ETHBTC",   "SOLBTC":  "SOLBTC",  "ZECBTC": "ZECBTC",
    "BTCUSDT":  "BTCUSDT",  "ETHUSDT": "ETHUSDT", "HYPEUSDT": "HYPEUSDT",
    "SOLUSDT":  "SOLUSDT",  "HYPERUSDT": "HYPEUSDT",
}

VALID_ACTIONS = [
    "buy", "sell", "long", "short", "exit", "close",
    "entry_long", "entry_short", "exit_long", "exit_short",
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
    z_score: Optional[float] = None
    confidence: Optional[float] = None
    regime_score: Optional[float] = None
    quantity: Optional[float] = None
    ai_verdict: Optional[str] = None  # Ollama enrichment

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
            timestamp=data.get("time", datetime.now(timezone.utc).isoformat()),
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
stats = {"total": 0, "published": 0, "errors": 0, "ai_enriched": 0,
         "pubsub_success": 0, "gateway_fallback": 0}


# ─── Pub/Sub singleton ────────────────────────────────────────────────────────

_publisher: Optional["pubsub_v1.PublisherClient"] = None  # type: ignore
_firestore_client = None
_capability_sync_task: Optional[asyncio.Task[Any]] = None
_capability_snapshot: dict[str, Any] = {
    "available": False,
    "last_sync": None,
    "error": "not_initialized",
}


def _get_publisher():
    """Lazy-init a thread-safe Pub/Sub PublisherClient (singleton)."""
    global _publisher
    if _publisher is None and _PUBSUB_AVAILABLE:
        try:
            _publisher = pubsub_v1.PublisherClient()
            log.info("✅ Pub/Sub PublisherClient initialized")
        except Exception as e:
            log.error("❌ Failed to create PublisherClient: %s", e)
    return _publisher


def _get_firestore_client():
    """Lazy-init Firestore client for cross-surface operational logs."""
    global _firestore_client
    if _firestore_client is None and _FIRESTORE_AVAILABLE:
        try:
            _firestore_client = g_firestore.Client(project=GCP_PROJECT_ID)
            log.info("✅ Firestore client initialized")
        except Exception as exc:
            log.warning("Firestore client init failed: %s", exc)
            _firestore_client = None
    return _firestore_client


async def _fetch_ollama_models() -> list[dict]:
    """Best-effort local Ollama model inventory."""
    try:
        async with httpx.AsyncClient(timeout=2.5) as client:
            response = await client.get(f"{OLLAMA_URL}/api/tags")
            if response.status_code != 200:
                return []
            payload = response.json() if response.headers.get("content-type", "").startswith("application/json") else {}
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
                "memory_total_mb": float(parts[1]) if parts[1].replace(".", "", 1).isdigit() else parts[1],
                "driver_version": parts[2],
            }
        )
    return rows


async def _probe_local_service(url: str) -> dict:
    started = datetime.now(timezone.utc)
    try:
        async with httpx.AsyncClient(timeout=LOCAL_SERVICE_PROBE_TIMEOUT_SECONDS) as client:
            response = await client.get(url)
            latency_ms = int((datetime.now(timezone.utc) - started).total_seconds() * 1000)
            return {
                "healthy": response.status_code == 200,
                "status_code": response.status_code,
                "latency_ms": latency_ms,
            }
    except Exception as exc:
        latency_ms = int((datetime.now(timezone.utc) - started).total_seconds() * 1000)
        return {
            "healthy": False,
            "status_code": None,
            "latency_ms": latency_ms,
            "error": str(exc)[:180],
        }


async def _collect_windows_lab_snapshot() -> dict:
    """Collect local workstation capabilities and service health."""
    started = datetime.now(timezone.utc)
    ollama_models = await _fetch_ollama_models()
    gpu_rows = await asyncio.to_thread(_detect_gpu_inventory)
    webhook_probe, tv_probe, ollama_probe = await asyncio.gather(
        _probe_local_service(f"http://127.0.0.1:{WEBHOOK_PORT}/status"),
        _probe_local_service("http://127.0.0.1:8081/health"),
        _probe_local_service(f"{OLLAMA_URL}/api/tags"),
    )
    snapshot = {
        "available": True,
        "updated_at": datetime.now(timezone.utc).isoformat(),
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
    snapshot["collection_latency_ms"] = int(
        (datetime.now(timezone.utc) - started).total_seconds() * 1000
    )
    return snapshot


def _write_windows_capabilities(snapshot: dict):
    """Persist latest workstation capabilities into Firestore."""
    client = _get_firestore_client()
    if client is None:
        return
    try:
        client.collection(EDGE_CAPABILITIES_COLLECTION).document("windows_lab").set(snapshot, merge=True)
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
                "updated_at": datetime.now(timezone.utc).isoformat(),
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
    signal_id: Optional[str] = None,
    symbol: Optional[str] = None,
    action: Optional[str] = None,
    metadata: Optional[dict] = None,
):
    """Best-effort Firestore log emit used by unified operator frontend."""
    client = _get_firestore_client()
    if client is None:
        return

    payload = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
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
        "target_platforms": [],       # empty = all platforms consume
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

async def publish_to_pubsub(signal: dict) -> dict:
    """
    Primary path: publish TradeSignal dict to GCP Pub/Sub trading-signals.
    Falls back to gateway HTTPS if unavailable.
    """
    publisher = _get_publisher()
    if publisher:
        try:
            data = json.dumps(signal).encode("utf-8")
            future = await asyncio.to_thread(publisher.publish, PUBSUB_TOPIC, data)
            msg_id = await asyncio.to_thread(future.result, timeout=10)
            stats["published"] += 1
            stats["pubsub_success"] += 1
            log.info("📤 Published to Pub/Sub | id=%s | %s %s",
                     msg_id, signal["side"], signal["symbol"])
            return {"published": True, "channel": "pubsub", "message_id": msg_id}
        except Exception as e:
            log.error("⚠️  Pub/Sub failed: %s — trying gateway fallback", e)

    # Fallback
    return await forward_to_gateway(signal)


async def forward_to_gateway(signal: dict) -> dict:
    """
    HTTPS fallback: POST signal to Sapphire Gateway Cloud Run.
    Used when Pub/Sub credentials are unavailable or publish fails.
    """
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            r = await client.post(
                f"{GATEWAY_URL}/api/signals",
                json=signal,
                headers={"Content-Type": "application/json"},
            )
            stats["published"] += 1
            stats["gateway_fallback"] += 1
            log.info("📡 Gateway fallback → HTTP %d", r.status_code)
            return {
                "published": True,
                "channel": "gateway_https",
                "http_status": r.status_code,
                "response": r.text[:200],
            }
    except Exception as e:
        log.error("❌ Gateway fallback also failed: %s", e)
        stats["errors"] += 1
        return {"published": False, "channel": "none", "error": str(e)}


# ─── Ollama enrichment ────────────────────────────────────────────────────────

async def ollama_enrich(alert: TradingViewAlert) -> Optional[str]:
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
    log.info("Pub/Sub topic:   %s", PUBSUB_TOPIC)
    log.info("Gateway fallback: %s", GATEWAY_URL)
    log.info("Ollama endpoint:  %s", OLLAMA_URL)
    log.info("Pub/Sub available: %s", _PUBSUB_AVAILABLE)
    # Warm up publisher on startup
    _get_publisher()
    _get_firestore_client()
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
        color   = "#00ff88" if h.get("published") else "#666"
        channel = h.get("channel", "")
        tick    = ("✓ " + channel) if h.get("published") else "–"
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
        if _PUBSUB_AVAILABLE else
        "<span style='color:#ff6600'>● Gateway fallback mode</span>"
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
      <span class='stat'>Total <span>{stats['total']}</span></span>
      <span class='stat'>Published <span>{stats['published']}</span></span>
      <span class='stat'>Pub/Sub <span>{stats['pubsub_success']}</span></span>
      <span class='stat'>Gateway <span>{stats['gateway_fallback']}</span></span>
      <span class='stat'>AI-enriched <span>{stats['ai_enriched']}</span></span>
      <span class='stat'>Errors <span>{stats['errors']}</span></span>
    </p>
    <table>
      <tr><th>Time</th><th>Action</th><th>Symbol</th><th>Price</th>
          <th>Conf</th><th>AI Verdict</th><th>Published</th></tr>
      {history_rows or '<tr><td colspan=7>No alerts yet</td></tr>'}
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
        "pubsub_topic": PUBSUB_TOPIC,
        "pubsub_available": _PUBSUB_AVAILABLE,
        "gateway_url": GATEWAY_URL,
        "ollama_url": OLLAMA_URL,
        "services": services,
        "capabilities": {
            "ollama_model_count": capabilities.get("ollama_model_count", 0),
            "gpu_count": ((_capability_snapshot or {}).get("hardware", {}) or {}).get("gpu_count", 0),
            "last_sync": (_capability_snapshot or {}).get("updated_at"),
        },
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
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@app.get("/webhook/health")
async def webhook_health():
    services = (_capability_snapshot or {}).get("services", {})
    return {
        "status": "healthy",
        "service": "windows_webhook",
        "version": "2.0.0",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "services": services,
        "stats": stats,
        "capabilities": {
            "last_sync": (_capability_snapshot or {}).get("updated_at"),
            "available": bool((_capability_snapshot or {}).get("available")),
            "ollama_model_count": ((_capability_snapshot or {}).get("models", {}) or {}).get("ollama_model_count", 0),
            "gpu_count": ((_capability_snapshot or {}).get("hardware", {}) or {}).get("gpu_count", 0),
        },
    }


@app.get("/windows/capabilities")
async def windows_capabilities():
    snapshot = dict(_capability_snapshot or {})
    if not snapshot:
        snapshot = {"available": False, "error": "capabilities_not_ready"}
    snapshot["timestamp"] = datetime.now(timezone.utc).isoformat()
    return snapshot


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
    log.info("📨 %s %s @ $%s  conf=%s  z=%s",
             alert.action.upper(), alert.symbol, alert.price,
             alert.confidence, alert.z_score)

    # Step 1 — Ollama enrichment (non-blocking but we await it here;
    #           it has an 8s timeout so won't delay the response much)
    alert.ai_verdict = await ollama_enrich(alert)

    # Step 2 — Build TradeSignal dict
    signal = build_trade_signal(alert)

    # Step 3 — Publish to Pub/Sub (with gateway fallback)
    pub_result = await publish_to_pubsub(signal)

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
        "received_at": datetime.now(timezone.utc).isoformat(),
        "alert": alert.to_dict(),
        "published": pub_result.get("published", False),
        "channel": pub_result.get("channel", "none"),
        "pub_detail": pub_result,
        "signal_id": signal["signal_id"],
    }
    alert_history.append(entry)
    if len(alert_history) > MAX_HISTORY:
        alert_history.pop(0)

    return JSONResponse({
        "status": "ok",
        "alert_id": stats["total"],
        "signal_id": signal["signal_id"],
        "symbol": alert.symbol,
        "action": alert.action,
        "side": signal["side"],
        "signal_type": signal["signal_type"],
        "ai_verdict": alert.ai_verdict,
        "publish": pub_result,
    })


# ─── Entry point ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=WEBHOOK_PORT,
        log_level="info",
        access_log=True,
    )
