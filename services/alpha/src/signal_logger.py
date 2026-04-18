"""Sapphire Signal Logger — captures trading signals when execution is unavailable.

Runs on Mac as a lightweight replacement for the alpha engine when Pis are offline.
Receives signals from the webhook (Windows PC :9090), logs them to JSONL,
analyzes with Nemotron, and notifies via Telegram.

Usage:
    uvicorn signal_logger:app --host 0.0.0.0 --port 18081
"""

from __future__ import annotations

import contextlib
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

SIGNALS_PATH = Path.home() / "Code" / "Sapphire" / "data" / "trading_signals.jsonl"
EVENTS_PATH = Path.home() / "Code" / "Sapphire" / "data" / "system_events.jsonl"

# Add plugin lib to path for Telegram notifications
sys.path.insert(0, str(Path.home() / "Code" / "Sapphire" / "plugins" / "claw-sapphire" / "lib"))

# Signal pipeline (optional — graceful degradation if lib/core unavailable)
sys.path.insert(0, str(Path.home() / "Code" / "Sapphire" / "services" / "alpha"))
try:
    from signal_pipeline import pipeline as _signal_pipeline
    _PIPELINE_AVAILABLE = True
except Exception:
    _PIPELINE_AVAILABLE = False

app = FastAPI(title="Sapphire Signal Logger", version="0.1.0")

# Optional webhook secret for signal authentication (set WEBHOOK_SECRET env var)
# TradingView sends the secret as a field in the JSON body: {"secret": "...", ...}
_WEBHOOK_SECRET = os.environ.get("WEBHOOK_SECRET", "")


@app.get("/health")
async def health():
    paper_trading = os.environ.get("PAPER_TRADING", "0") == "1"
    return {
        "status": "ok",
        "mode": "signal_logger",
        "paper_trading": paper_trading,
        "note": "Pis offline — logging only, no execution",
    }


@app.post("/api/signals")
@app.post("/api/signals/create")
async def receive_signal(request: Request):
    """Receive a trading signal from the webhook and log it."""
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "invalid JSON"}, status_code=400)

    # Validate webhook secret if configured
    if _WEBHOOK_SECRET and body.get("secret") != _WEBHOOK_SECRET:
        return JSONResponse({"error": "unauthorized"}, status_code=401)

    signal = {
        "timestamp": datetime.now(UTC).isoformat(),
        "symbol": body.get("symbol", "UNKNOWN"),
        "action": body.get("action", body.get("side", "UNKNOWN")),
        "strategy": body.get("strategy", "unknown"),
        "price": body.get("price", 0),
        "confidence": body.get("confidence", 0),
        "signal_id": body.get("signal_id", ""),
        "source": "webhook",
        "execution": "LOGGED_ONLY",
        "raw": body,
    }

    # Log to signals file
    SIGNALS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(SIGNALS_PATH, "a") as f:
        f.write(json.dumps(signal) + "\n")

    # Log to event stream
    event = {
        "timestamp": signal["timestamp"],
        "type": "signal.received",
        "message": f"Signal: {signal['action']} {signal['symbol']} @ {signal['price']} (conf: {signal['confidence']}) — LOGGED ONLY",
        "tags": ["type:trading", "device:mac", "priority:p1"],
        "data": signal,
    }
    EVENTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(EVENTS_PATH, "a") as f:
        f.write(json.dumps(event) + "\n")

    # ── Signal Pipeline (scoring + routing + confirmation firewall) ─────────
    pipeline_result = None
    if _PIPELINE_AVAILABLE:
        with contextlib.suppress(Exception):
            pipeline_result = _signal_pipeline.process(signal)

    # ── Telegram notification (pipeline handles it if available) ────────────
    ai_assessment = "Analysis unavailable"
    if not pipeline_result or not pipeline_result.telegram_sent:
        # Fallback: quick Nemotron analysis + basic notification
        try:
            from nemotron import MODELS, generate
            analysis_prompt = f"Trading signal: {signal['action']} {signal['symbol']} at ${signal['price']} with confidence {signal['confidence']}. Strategy: {signal['strategy']}. Give a one-sentence assessment."
            result = generate(analysis_prompt, model=MODELS["classify"], timeout=10)
            ai_assessment = result.response if result.success else "Analysis unavailable"
        except Exception:
            ai_assessment = "Analysis unavailable"

        try:
            sys.path.insert(0, str(Path.home() / "Code" / "Sapphire" / "plugins" / "claw-sapphire" / "tools"))
            from notify import send_telegram_message
            send_telegram_message(
                f"📊 *Signal Received*\n\n"
                f"{'🟢' if 'buy' in signal['action'].lower() else '🔴'} {signal['action']} {signal['symbol']}\n"
                f"Price: ${signal['price']}\n"
                f"Confidence: {signal['confidence']}\n"
                f"Strategy: {signal['strategy']}\n\n"
                f"🤖 {ai_assessment}\n\n"
                f"⚠️ _Logged only — execution offline (Pis down)_",
                priority="p1",
            )
        except Exception:
            pass

    response: dict = {
        "status": "logged",
        "signal_id": signal["signal_id"],
        "execution": "LOGGED_ONLY",
        "note": "Pis offline — signal captured but not executed",
        "ai_assessment": ai_assessment,
    }
    if pipeline_result:
        response["pipeline"] = {
            "score": pipeline_result.scored.score,
            "routing": pipeline_result.scored.routing,
            "position_usd": pipeline_result.scored.position_usd,
            "kernel_ok": pipeline_result.scored.kernel_ok,
            "audit": pipeline_result.audit_path,
        }
    return response


@app.get("/api/signals/recent")
async def recent_signals():
    """Return recent signals."""
    if not SIGNALS_PATH.exists():
        return {"signals": [], "count": 0}

    lines = SIGNALS_PATH.read_text().strip().splitlines()[-20:]
    signals = []
    for line in lines:
        with contextlib.suppress(json.JSONDecodeError):
            signals.append(json.loads(line))

    return {"signals": list(reversed(signals)), "count": len(signals)}


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", "18081"))
    uvicorn.run(app, host="0.0.0.0", port=port)
