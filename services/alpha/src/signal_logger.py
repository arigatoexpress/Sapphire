"""Sapphire Signal Logger — captures trading signals when execution is unavailable.

Runs on Mac as a lightweight replacement for the alpha engine when Pis are offline.
Receives signals from the webhook (Windows PC :9090), logs them to JSONL,
analyzes with Nemotron, and notifies via Telegram.

Usage:
    WEBHOOK_SECRET=<secret> uvicorn signal_logger:app --host 100.x.x.w --port 18081

Security:
    - Bind to Tailscale interface (100.x.x.w), NOT 0.0.0.0
    - WEBHOOK_SECRET must be set — all requests are rejected without it
    - All endpoints only accept connections from localhost or Tailscale CGNAT (100.x.x.x)
"""

from __future__ import annotations

import contextlib
import ipaddress
import json
import logging
import os
import sys
from datetime import UTC, datetime
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

log = logging.getLogger(__name__)

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

# ─── Security: private-network allowlist ─────────────────────────────────────
# Permit localhost, Tailscale CGNAT (100.64.0.0/10), and the home LAN subnet
# so the Windows webhook box can forward signals when Tailscale is down.
_TAILSCALE_NET = ipaddress.ip_network("100.64.0.0/10")
_HOME_LAN_NET = ipaddress.ip_network("192.168.1.0/24")
_LOCALHOST = ipaddress.ip_address("127.0.0.1")


class _TailscaleOnlyMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        client_ip = request.client.host if request.client else ""
        try:
            addr = ipaddress.ip_address(client_ip)
        except ValueError:
            return JSONResponse({"error": "forbidden"}, status_code=403)
        allowed = addr == _LOCALHOST or addr in _TAILSCALE_NET or addr in _HOME_LAN_NET
        if not allowed:
            log.warning("signal_logger: blocked request from non-allowlisted IP %s", client_ip)
            return JSONResponse({"error": "forbidden"}, status_code=403)
        return await call_next(request)


app = FastAPI(title="Sapphire Signal Logger", version="0.1.0")
app.add_middleware(_TailscaleOnlyMiddleware)


def _load_webhook_secret() -> str:
    """Load WEBHOOK_SECRET from env or the sapphire secrets dir."""
    secret = os.environ.get("WEBHOOK_SECRET", "")
    if secret:
        return secret
    fallback = Path.home() / ".config" / "sapphire-secrets" / "telegram_webhook_secret"
    try:
        return fallback.read_text().strip()
    except OSError:
        return ""


# WEBHOOK_SECRET is required — all signal POST requests are rejected without it.
# Set via WEBHOOK_SECRET env var, or place it in ~/.config/sapphire-secrets/telegram_webhook_secret.
_WEBHOOK_SECRET = _load_webhook_secret()
if not _WEBHOOK_SECRET:
    log.warning(
        "WEBHOOK_SECRET is not set — /api/signals endpoint will reject all requests. "
        "Set WEBHOOK_SECRET env var or store it in ~/.config/sapphire-secrets/telegram_webhook_secret."
    )


_PAPER_TRADING_TRUE = {"1", "true", "yes", "y", "on"}
_PAPER_TRADING_FALSE = {"0", "false", "no", "n", "off"}


def _paper_trading_env_enabled() -> bool:
    """Return paper-trading mode, defaulting safely to enabled."""
    raw = os.environ.get("PAPER_TRADING")
    if raw is None or raw.strip() == "":
        return True

    value = raw.strip().lower()
    if value in _PAPER_TRADING_TRUE:
        return True
    if value in _PAPER_TRADING_FALSE:
        return False

    log.warning("signal_logger: unrecognized PAPER_TRADING=%r; defaulting to paper", raw)
    return True


@app.get("/health")
async def health():
    paper_trading = _paper_trading_env_enabled()
    webhook_secret_configured = bool(_WEBHOOK_SECRET)
    blockers = []
    if not webhook_secret_configured:
        blockers.append("webhook_secret_unconfigured")
    return {
        "status": "ok",
        "mode": "signal_logger",
        "paper_trading": paper_trading,
        "webhook_secret_configured": webhook_secret_configured,
        "signal_ingest_ready": webhook_secret_configured,
        "blockers": blockers,
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

    # Validate webhook secret — required, not optional
    if not _WEBHOOK_SECRET:
        return JSONResponse(
            {"error": "service misconfigured — WEBHOOK_SECRET not set"}, status_code=503
        )
    if body.get("secret") != _WEBHOOK_SECRET:
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

    # 0G publish (fire-and-forget, gated by SAPPHIRE_OG_ENABLED).
    # Never blocks or raises; see lib/og/hooks.py.
    with contextlib.suppress(Exception):
        from lib.og.hooks import publish_signal_async

        publish_signal_async(signal)

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
            sys.path.insert(
                0, str(Path.home() / "Code" / "Sapphire" / "plugins" / "claw-sapphire" / "tools")
            )
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
    # Bind to Tailscale IP only — never 0.0.0.0
    host = os.environ.get("HOST", "100.x.x.w")
    uvicorn.run(app, host=host, port=port)
