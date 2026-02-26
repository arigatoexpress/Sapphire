#!/usr/bin/env python3
"""
Sapphire Webhook Receiver — Windows PC
Receives TradingView alerts, optionally enriches via Ollama, forwards to rari1/rari2
"""

import json
import logging
import hmac
import hashlib
import httpx
import asyncio
from datetime import datetime, timezone
from typing import Optional
from dataclasses import dataclass, asdict, field
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, HTTPException, BackgroundTasks
from fastapi.responses import JSONResponse, HTMLResponse
import uvicorn

# ─── Config ──────────────────────────────────────────────────────────────────

WEBHOOK_SECRET  = "sapphire_trading_2024"  # Must match Pine Script alert message
RARI1_URL       = "http://192.168.1.23:8080"  # rari1 local IP (update if port differs)
OLLAMA_URL      = "http://localhost:11434"     # Ollama on this machine
WEBHOOK_PORT    = 9090
LOG_FILE        = "D:/CodingFiles/sapphire-webhook/webhook.log"
MAX_HISTORY     = 200

# Supported symbols → Lighter internal format
SYMBOL_MAP = {
    "ETHBTC": "ETHBTC", "SOLBTC": "SOLBTC", "ZECBTC": "ZECBTC",
    "BTCUSDT": "BTCUSDT", "ETHUSDT": "ETHUSDT", "HYPEUSDT": "HYPEUSDT",
    "SOLUSDT": "SOLUSDT", "HYPERUSDT": "HYPEUSDT",
}

VALID_ACTIONS = [
    "buy", "sell", "long", "short", "exit", "close",
    "entry_long", "entry_short", "exit_long", "exit_short",
]

# ─── Logging ─────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
log = logging.getLogger("sapphire-webhook")

# ─── Data Models ─────────────────────────────────────────────────────────────

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
    ai_verdict: Optional[str] = None  # Ollama enrichment result

    def to_dict(self):
        return asdict(self)

    @classmethod
    def from_webhook(cls, data: dict) -> "TradingViewAlert":
        raw_symbol = data.get("symbol", "").upper()
        # Strip exchange prefix (BINANCE:ETHBTC → ETHBTC)
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
        )


# ─── In-memory state ─────────────────────────────────────────────────────────

alert_history: list[dict] = []
stats = {"total": 0, "forwarded": 0, "errors": 0, "ai_enriched": 0}


# ─── App lifecycle ────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info("🚀 Sapphire Webhook Receiver starting on port %d", WEBHOOK_PORT)
    log.info("Ollama endpoint: %s", OLLAMA_URL)
    log.info("Rari1 forward:   %s", RARI1_URL)
    yield
    log.info("Webhook receiver shutting down")


app = FastAPI(
    title="Sapphire Webhook Receiver",
    version="1.0.0",
    lifespan=lifespan,
)


# ─── Helpers ─────────────────────────────────────────────────────────────────

def validate_payload(data: dict) -> bool:
    if "symbol" not in data or "action" not in data:
        return False
    return data.get("action", "").lower() in VALID_ACTIONS


def map_side(action: str) -> Optional[str]:
    if action in ("buy", "long", "entry_long"):
        return "buy"
    if action in ("sell", "short", "entry_short"):
        return "sell"
    if action in ("exit", "close", "exit_long", "exit_short"):
        return "exit"
    return None


async def ollama_enrich(alert: TradingViewAlert) -> Optional[str]:
    """Ask Ollama for a quick verdict on the signal."""
    prompt = (
        f"Trading signal received: {alert.action.upper()} {alert.symbol} "
        f"@ ${alert.price}. "
        + (f"Z-score: {alert.z_score:.2f}. " if alert.z_score else "")
        + (f"Confidence: {alert.confidence:.0%}. " if alert.confidence else "")
        + (f"Regime: {alert.regime_score:.2f}. " if alert.regime_score else "")
        + "In one sentence: is this signal high quality? Answer with CONFIRM, CAUTION, or REJECT and one reason."
    )
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            r = await client.post(
                f"{OLLAMA_URL}/api/generate",
                json={"model": "gemma3:27b", "prompt": prompt, "stream": False},
            )
            if r.status_code == 200:
                verdict = r.json().get("response", "").strip()
                log.info("Ollama verdict: %s", verdict[:120])
                stats["ai_enriched"] += 1
                return verdict[:200]
    except Exception as e:
        log.warning("Ollama enrichment skipped: %s", e)
    return None


async def forward_to_rari1(alert: TradingViewAlert) -> dict:
    """Forward signal to rari1 for execution routing."""
    payload = {
        "symbol": alert.symbol,
        "side": map_side(alert.action),
        "source": "tradingview_windows",
        "alert_price": alert.price,
        "z_score": alert.z_score,
        "confidence": alert.confidence,
        "ai_verdict": alert.ai_verdict,
        "timestamp": alert.timestamp,
        # Safety: low confidence → dry run
        "dry_run": bool(alert.confidence and alert.confidence < 0.70),
    }
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            r = await client.post(f"{RARI1_URL}/execute", json=payload)
            stats["forwarded"] += 1
            return {"forwarded": True, "rari1_status": r.status_code, "rari1_response": r.text[:200]}
    except Exception as e:
        log.error("Forward to rari1 failed: %s", e)
        stats["errors"] += 1
        return {"forwarded": False, "error": str(e)}


# ─── Routes ──────────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def dashboard():
    history_rows = "".join(
        f"<tr><td>{h['received_at'][:19]}</td><td>{h['alert']['action'].upper()}</td>"
        f"<td>{h['alert']['symbol']}</td><td>${h['alert']['price']}</td>"
        f"<td>{h['alert'].get('confidence', '-')}</td>"
        f"<td style='color:{'green' if h.get('forwarded') else 'gray'}'>"
        f"{'✓' if h.get('forwarded') else '–'}</td></tr>"
        for h in reversed(alert_history[-20:])
    )
    return f"""
    <html><head><title>Sapphire Webhook</title>
    <meta http-equiv="refresh" content="10">
    <style>body{{font-family:monospace;background:#0a0a0a;color:#00ff88;padding:20px}}
    table{{border-collapse:collapse;width:100%}}th,td{{border:1px solid #333;padding:6px 10px}}
    th{{background:#111}}h1{{color:#00aaff}}</style></head>
    <body>
    <h1>🔷 Sapphire Webhook Receiver</h1>
    <p>Total: {stats['total']} | Forwarded: {stats['forwarded']} |
       AI-enriched: {stats['ai_enriched']} | Errors: {stats['errors']}</p>
    <table><tr><th>Time</th><th>Action</th><th>Symbol</th><th>Price</th>
    <th>Confidence</th><th>Forwarded</th></tr>
    {history_rows or '<tr><td colspan=6>No alerts yet</td></tr>'}
    </table>
    </body></html>
    """


@app.get("/status")
async def status():
    return {
        "status": "active",
        "stats": stats,
        "ollama_url": OLLAMA_URL,
        "rari1_url": RARI1_URL,
        "supported_actions": VALID_ACTIONS,
        "symbol_map": SYMBOL_MAP,
    }


@app.get("/alerts")
async def get_alerts(limit: int = 20):
    return {"alerts": alert_history[-limit:], "total": len(alert_history)}


@app.post("/webhook/tradingview")
async def receive_tradingview(request: Request, background_tasks: BackgroundTasks):
    """Main TradingView webhook endpoint."""
    try:
        body = await request.body()
        data = json.loads(body)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    if not validate_payload(data):
        log.warning("Invalid payload rejected: %s", str(data)[:100])
        raise HTTPException(status_code=400, detail="Invalid payload — check symbol/action fields")

    alert = TradingViewAlert.from_webhook(data)
    stats["total"] += 1
    log.info("📨 %s %s @ $%s (conf=%s z=%s)",
             alert.action.upper(), alert.symbol, alert.price, alert.confidence, alert.z_score)

    # AI enrichment (non-blocking check for model availability)
    alert.ai_verdict = await ollama_enrich(alert)

    # Forward to rari1
    fwd_result = await forward_to_rari1(alert)

    # Store in history
    entry = {
        "received_at": datetime.now(timezone.utc).isoformat(),
        "alert": alert.to_dict(),
        "forwarded": fwd_result.get("forwarded", False),
        "forward_detail": fwd_result,
    }
    alert_history.append(entry)
    if len(alert_history) > MAX_HISTORY:
        alert_history.pop(0)

    return JSONResponse({
        "status": "ok",
        "alert_id": stats["total"],
        "symbol": alert.symbol,
        "action": alert.action,
        "ai_verdict": alert.ai_verdict,
        "forward": fwd_result,
    })


# ─── Entry point ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=WEBHOOK_PORT,
        log_level="info",
        access_log=True,
    )
