"""
Sapphire API Gateway - Central REST/WebSocket Interface

This service provides the unified API for the trading dashboard.
It aggregates data from all platform bots via Pub/Sub and Firestore.
"""

import asyncio
import hashlib
import json
import logging
import os
import time
import uuid

# Add shared library to path
import sys
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from fastapi import Depends, FastAPI, Header, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

try:
    from google.cloud import firestore as g_firestore
except ImportError:  # pragma: no cover
    g_firestore = None

try:
    from google.api_core.exceptions import AlreadyExists
except ImportError:  # pragma: no cover
    AlreadyExists = Exception

# ─── API Auth ────────────────────────────────────────────────────────────────

_CONTROL_TOKEN = os.getenv("SAPPHIRE_CONTROL_API_TOKEN", "")


async def require_control_token(
    x_sapphire_control_token: Optional[str] = Header(None, alias="X-Sapphire-Control-Token"),
) -> None:
    """
    Validate the X-Sapphire-Control-Token header on mutable endpoints.
    Token is sourced from SAPPHIRE_CONTROL_API_TOKEN env / Secret Manager.
    Returns 401 if missing, 403 if wrong.
    """
    if not _CONTROL_TOKEN:
        # Token not configured → log warning but allow (dev mode only)
        logger.warning("⚠️  SAPPHIRE_CONTROL_API_TOKEN not set — mutable endpoint unprotected!")
        return
    if not x_sapphire_control_token:
        raise HTTPException(status_code=401, detail="X-Sapphire-Control-Token header required")
    if x_sapphire_control_token != _CONTROL_TOKEN:
        raise HTTPException(status_code=403, detail="Invalid control token")

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from pubsub import get_pubsub_client, publish, subscribe
from utils import get_service_name, setup_logging, utc_now

from models import BalanceUpdate, Position, SignalType, TradeResult, TradeSide, TradeSignal

logger = logging.getLogger(__name__)

SERVICE_NAME = "api-gateway"
GCP_PROJECT_ID = os.getenv("GCP_PROJECT_ID", "sapphire-479610")
TRADINGVIEW_WEBHOOK_SECRET = os.getenv("SAPPHIRE_TRADINGVIEW_WEBHOOK_SECRET", "").strip()
TRADINGVIEW_IDEMPOTENCY_WINDOW_SECONDS = max(
    30, int(os.getenv("SAPPHIRE_TRADINGVIEW_IDEMPOTENCY_WINDOW_SECONDS", "300"))
)
TRADINGVIEW_IDEMPOTENCY_MAX_KEYS = max(
    50, int(os.getenv("SAPPHIRE_TRADINGVIEW_IDEMPOTENCY_MAX_KEYS", "1000"))
)
SYSTEM_LOGS_COLLECTION = os.getenv("SYSTEM_LOGS_COLLECTION", "system_logs")
TRADE_EXECUTIONS_COLLECTION = os.getenv("TRADE_EXECUTIONS_COLLECTION", "trade_executions")
TRADING_METRICS_COLLECTION = os.getenv("TRADING_METRICS_COLLECTION", "trading_metrics")
TRADING_METRICS_DOC_ID = os.getenv("TRADING_METRICS_DOC_ID", "current")

VALID_TV_ACTIONS = {
    "buy",
    "sell",
    "long",
    "short",
    "entry_long",
    "entry_short",
    "exit",
    "close",
    "exit_long",
    "exit_short",
}

_ALLOWED_TRADE_EXECUTION_PLATFORMS = {
    value.strip().lower()
    for value in os.getenv(
        "TRADE_EXECUTION_ALLOWED_PLATFORMS",
        "aster,lighter",
    ).split(",")
    if value.strip()
}
_ALLOWED_TRADE_EXECUTION_SIDES = {"BUY", "SELL", "LONG", "SHORT", "CLOSE"}


class ServiceState:
    """Shared state for aggregated platform data."""

    def __init__(self):
        # Aggregated from all bots via Pub/Sub
        self.balances: Dict[str, float] = {}
        self.positions: Dict[str, List[Dict]] = {}
        self.trade_history: List[Dict] = []
        self.bot_statuses: Dict[str, Dict] = {}

        # Real-time updates
        self.last_updates: Dict[str, datetime] = {}

        # WebSocket clients
        self.ws_clients: List[WebSocket] = []
        self.tradingview_ingress_stats: Dict[str, int] = {
            "total": 0,
            "published": 0,
            "duplicates": 0,
            "failed": 0,
            "rejected": 0,
        }
        self.tradingview_recent: List[Dict[str, Any]] = []
        self.tradingview_signal_seen_at: Dict[str, float] = {}
        self.tradingview_last_signal_at: Optional[str] = None

    def get_total_balance(self) -> float:
        """Get aggregated balance across all platforms."""
        return sum(self.balances.values())

    def get_all_positions(self) -> List[Dict]:
        """Get all positions across all platforms."""
        all_pos = []
        for platform, positions in self.positions.items():
            for pos in positions:
                pos["platform"] = platform
                all_pos.append(pos)
        return all_pos

    def get_active_platforms(self) -> List[str]:
        """Get list of active platforms."""
        return list(self.balances.keys())


state = ServiceState()
_firestore_client = None


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _coerce_float(value: Any, default: Optional[float] = None) -> Optional[float]:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _extract_text(payload: Dict[str, Any], keys: List[str], default: str = "") -> str:
    for key in keys:
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return default


def _parse_message_payload(message: Any) -> Dict[str, Any]:
    if isinstance(message, dict):
        return message
    if message is None:
        return {}

    text = str(message).strip()
    if not text:
        return {}

    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            return parsed
    except Exception:
        pass

    parsed: Dict[str, Any] = {}
    chunks = [chunk.strip() for chunk in text.replace("\n", ",").split(",") if chunk.strip()]
    for chunk in chunks:
        if "=" in chunk:
            key, value = chunk.split("=", 1)
        elif ":" in chunk:
            key, value = chunk.split(":", 1)
        else:
            continue
        parsed[key.strip()] = value.strip()
    return parsed


def _normalize_tv_symbol(raw_symbol: str) -> str:
    symbol = str(raw_symbol or "").strip().upper()
    if ":" in symbol:
        symbol = symbol.split(":")[-1]
    return symbol.replace("/", "").replace("-", "").replace("_", "")


def _normalize_tv_action(raw_action: str) -> str:
    action = str(raw_action or "").strip().lower()
    aliases = {
        "entry": "buy",
        "exit_all": "exit",
    }
    return aliases.get(action, action)


def _map_tv_action(action: str) -> tuple[TradeSide, SignalType]:
    if action in {"buy", "long", "entry_long"}:
        return TradeSide.BUY, SignalType.ENTRY
    if action in {"sell", "short", "entry_short"}:
        return TradeSide.SELL, SignalType.ENTRY
    if action in {"exit_long", "close", "exit"}:
        return TradeSide.SELL, SignalType.EXIT
    if action == "exit_short":
        return TradeSide.BUY, SignalType.EXIT
    raise ValueError(f"Unsupported action: {action}")


def _build_signal_key(
    payload: Dict[str, Any],
    symbol: str,
    action: str,
    timestamp: str,
    price: Optional[float],
) -> str:
    explicit_id = _extract_text(payload, ["signal_id", "alert_id", "id", "message_id", "tv_id"])
    if explicit_id:
        return explicit_id
    seed = json.dumps(
        {
            "symbol": symbol,
            "action": action,
            "timestamp": timestamp,
            "price": price,
        },
        sort_keys=True,
        default=str,
    )
    return hashlib.sha256(seed.encode("utf-8")).hexdigest()


def _is_duplicate_signal(signal_key: str) -> bool:
    now = time.time()
    cutoff = now - float(TRADINGVIEW_IDEMPOTENCY_WINDOW_SECONDS)
    stale_keys = [key for key, seen_at in state.tradingview_signal_seen_at.items() if seen_at < cutoff]
    for key in stale_keys:
        state.tradingview_signal_seen_at.pop(key, None)

    if signal_key in state.tradingview_signal_seen_at:
        return True

    state.tradingview_signal_seen_at[signal_key] = now
    if len(state.tradingview_signal_seen_at) > TRADINGVIEW_IDEMPOTENCY_MAX_KEYS:
        overflow = sorted(
            state.tradingview_signal_seen_at.items(), key=lambda item: item[1]
        )[: len(state.tradingview_signal_seen_at) - TRADINGVIEW_IDEMPOTENCY_MAX_KEYS]
        for old_key, _ in overflow:
            state.tradingview_signal_seen_at.pop(old_key, None)
    return False


def _append_tradingview_event(event: Dict[str, Any]) -> None:
    state.tradingview_recent.append(event)
    if len(state.tradingview_recent) > 200:
        state.tradingview_recent = state.tradingview_recent[-200:]


def _get_firestore_client():
    global _firestore_client
    if _firestore_client is None and g_firestore is not None:
        try:
            _firestore_client = g_firestore.Client(project=GCP_PROJECT_ID)
        except Exception as exc:
            logger.warning("Firestore client init failed: %s", exc)
            _firestore_client = None
    return _firestore_client


def _write_system_log(
    *,
    level: str,
    message: str,
    event_type: str,
    signal_id: Optional[str] = None,
    symbol: Optional[str] = None,
    action: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> None:
    client = _get_firestore_client()
    if client is None:
        return
    payload = {
        "timestamp": _utc_now_iso(),
        "level": str(level or "INFO").upper(),
        "service": "gateway_webhook",
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
        logger.warning("Firestore log write failed: %s", exc)


def _parse_timestamp(value: Any) -> datetime:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str):
        text = value.strip()
        if not text:
            return datetime.now(timezone.utc)
        try:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            return datetime.now(timezone.utc)
    else:
        return datetime.now(timezone.utc)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _extract_trade_pnl(payload: Dict[str, Any]) -> float:
    for key in ("realized_pnl", "pnl", "net_pnl", "profit", "realizedPnl", "netPnl"):
        value = _coerce_float(payload.get(key), default=None)
        if value is not None:
            return float(value)
    metadata = payload.get("metadata", {})
    if isinstance(metadata, dict):
        for key in ("realized_pnl", "pnl", "net_pnl", "profit"):
            value = _coerce_float(metadata.get(key), default=None)
            if value is not None:
                return float(value)
    return 0.0


def _extract_trade_success(payload: Dict[str, Any], pnl: float) -> bool:
    raw_success = payload.get("success")
    if isinstance(raw_success, bool):
        return raw_success
    if raw_success is not None:
        text = str(raw_success).strip().lower()
        if text in {"1", "true", "yes", "ok", "success", "filled"}:
            return True
        if text in {"0", "false", "no", "failed", "error", "rejected"}:
            return False

    status = str(payload.get("status", "")).strip().lower()
    if status in {"filled", "executed", "success", "ok"}:
        return True
    if status in {"failed", "rejected", "error"}:
        return False

    # Conservative fallback when no explicit status is present.
    return pnl >= 0.0


def _build_trade_execution_event(data: Dict[str, Any]) -> Dict[str, Any]:
    event = dict(data or {})
    timestamp_dt = _parse_timestamp(event.get("timestamp"))
    symbol = _normalize_tv_symbol(_extract_text(event, ["symbol", "ticker", "pair", "instrument"]))
    platform = str(event.get("platform", "unknown")).strip().lower() or "unknown"
    side = str(event.get("side", "")).strip().upper()
    signal_id = _extract_text(event, ["signal_id", "signalId"], default="")
    pnl = _extract_trade_pnl(event)
    success = _extract_trade_success(event, pnl)
    quantity = _coerce_float(event.get("filled_quantity"), default=0.0) or 0.0
    avg_price = _coerce_float(event.get("avg_price"), default=0.0) or 0.0
    fee = _coerce_float(event.get("fee"), default=0.0) or 0.0
    execution_time_ms = _coerce_float(event.get("execution_time_ms"), default=0.0) or 0.0
    error_message = str(event.get("error_message", "")).strip()
    metadata = event.get("metadata", {})
    if not isinstance(metadata, dict):
        metadata = {}

    trade_id = _extract_text(event, ["trade_id", "tradeId"], default="")
    if not trade_id:
        seed = json.dumps(
            {
                "signal_id": signal_id,
                "platform": platform,
                "symbol": symbol,
                "side": side,
                "timestamp": timestamp_dt.isoformat(),
                "qty": quantity,
                "price": avg_price,
            },
            sort_keys=True,
            default=str,
        )
        trade_id = f"trade-{hashlib.sha256(seed.encode('utf-8')).hexdigest()[:20]}"

    return {
        "trade_id": trade_id,
        "signal_id": signal_id or None,
        "platform": platform,
        "symbol": symbol or "UNKNOWN",
        "side": side or "UNKNOWN",
        "success": bool(success),
        "realized_pnl": float(pnl),
        "filled_quantity": float(quantity),
        "avg_price": float(avg_price),
        "fee": float(fee),
        "execution_time_ms": float(execution_time_ms),
        "error_message": error_message or None,
        "timestamp": timestamp_dt.isoformat(),
        "received_at": _utc_now_iso(),
        "metadata": metadata,
    }


def _validate_trade_execution_event(event: Dict[str, Any]) -> tuple[bool, str]:
    platform = str(event.get("platform", "")).strip().lower()
    symbol = str(event.get("symbol", "")).strip().upper()
    side = str(event.get("side", "")).strip().upper()

    if platform in {"", "unknown"}:
        return False, "invalid_platform"
    if _ALLOWED_TRADE_EXECUTION_PLATFORMS and platform not in _ALLOWED_TRADE_EXECUTION_PLATFORMS:
        return False, f"unsupported_platform:{platform}"
    if symbol in {"", "UNKNOWN", "NONE"}:
        return False, "invalid_symbol"
    if side in {"", "UNKNOWN", "NONE"}:
        return False, "invalid_side"
    if side not in _ALLOWED_TRADE_EXECUTION_SIDES:
        return False, f"unsupported_side:{side}"
    return True, ""


def _compute_window_metrics(client: Any) -> Dict[str, Any]:
    now = datetime.now(timezone.utc)
    day_start = now - timedelta(hours=24)
    week_start = now - timedelta(days=7)
    month_start = now - timedelta(days=30)

    month_docs = list(
        client.collection(TRADE_EXECUTIONS_COLLECTION)
        .where("timestamp", ">=", month_start.isoformat())
        .stream()
    )

    daily = {"count": 0, "pnl": 0.0}
    weekly = {"count": 0, "pnl": 0.0}
    monthly = {"count": 0, "pnl": 0.0}

    for doc in month_docs:
        row = doc.to_dict() or {}
        ts = _parse_timestamp(row.get("timestamp"))
        pnl = _coerce_float(row.get("realized_pnl"), default=0.0) or 0.0
        monthly["count"] += 1
        monthly["pnl"] += pnl
        if ts >= week_start:
            weekly["count"] += 1
            weekly["pnl"] += pnl
        if ts >= day_start:
            daily["count"] += 1
            daily["pnl"] += pnl

    return {
        "daily": {"count": int(daily["count"]), "pnl": float(round(daily["pnl"], 6))},
        "weekly": {"count": int(weekly["count"]), "pnl": float(round(weekly["pnl"], 6))},
        "monthly": {"count": int(monthly["count"]), "pnl": float(round(monthly["pnl"], 6))},
        "window_days": 30,
    }


def _update_trading_metrics_snapshot(event: Dict[str, Any]) -> Dict[str, Any]:
    client = _get_firestore_client()
    if client is None or g_firestore is None:
        return {"ok": False, "reason": "firestore_unavailable"}

    metrics_ref = client.collection(TRADING_METRICS_COLLECTION).document(TRADING_METRICS_DOC_ID)
    pnl = float(event.get("realized_pnl", 0.0) or 0.0)
    success = bool(event.get("success", False))
    wins_delta = 1 if success and pnl >= 0 else 0
    losses_delta = 1 if (not success) or pnl < 0 else 0

    metrics_ref.set(
        {
            "updated_at": _utc_now_iso(),
            "last_trade_id": event.get("trade_id"),
            "last_trade_symbol": event.get("symbol"),
            "last_trade_platform": event.get("platform"),
            "last_trade_success": success,
            "last_trade_pnl": pnl,
            "trades_total": g_firestore.Increment(1),
            "wins_total": g_firestore.Increment(wins_delta),
            "losses_total": g_firestore.Increment(losses_delta),
            "realized_pnl_total": g_firestore.Increment(pnl),
        },
        merge=True,
    )

    metrics_doc = metrics_ref.get()
    metrics_data = metrics_doc.to_dict() or {}
    total_trades = int(metrics_data.get("trades_total", 0) or 0)
    wins_total = int(metrics_data.get("wins_total", 0) or 0)
    losses_total = int(metrics_data.get("losses_total", 0) or 0)
    total_pnl = float(metrics_data.get("realized_pnl_total", 0.0) or 0.0)
    success_rate = round((wins_total / total_trades) * 100.0, 2) if total_trades > 0 else 0.0
    windows = _compute_window_metrics(client)

    payload = {
        "timestamp": _utc_now_iso(),
        "source": "api_gateway_trade_executions",
        "pnl": {
            "daily": windows["daily"]["pnl"],
            "weekly": windows["weekly"]["pnl"],
            "monthly": windows["monthly"]["pnl"],
            "total": float(round(total_pnl, 6)),
        },
        "trades": {
            "today": windows["daily"]["count"],
            "total": total_trades,
            "success_rate": success_rate,
            "wins": wins_total,
            "losses": losses_total,
            "failed": losses_total,
        },
        "positions": state.get_all_positions(),
        "windows": windows,
        # Legacy compatibility fields.
        "pnl_24h": windows["daily"]["pnl"],
        "pnl_7d": windows["weekly"]["pnl"],
        "pnl_30d": windows["monthly"]["pnl"],
        "win_rate": success_rate,
        "trades_today": windows["daily"]["count"],
        "trades_limit": total_trades,
    }
    metrics_ref.set(payload, merge=True)
    return {"ok": True, "snapshot": payload}


def _record_trade_execution(data: Dict[str, Any]) -> Dict[str, Any]:
    client = _get_firestore_client()
    if client is None:
        return {"stored": False, "reason": "firestore_unavailable"}

    event = _build_trade_execution_event(data)
    trade_id = str(event.get("trade_id", "")).strip()
    if not trade_id:
        return {"stored": False, "reason": "invalid_trade_id", "event": event}
    valid, invalid_reason = _validate_trade_execution_event(event)
    if not valid:
        return {
            "stored": False,
            "invalid": True,
            "reason": invalid_reason,
            "event": event,
        }

    try:
        client.collection(TRADE_EXECUTIONS_COLLECTION).document(trade_id).create(event)
    except AlreadyExists:
        return {"stored": False, "duplicate": True, "event": event}
    except Exception as exc:
        return {"stored": False, "error": str(exc), "event": event}

    snapshot = _update_trading_metrics_snapshot(event)
    return {"stored": True, "event": event, "snapshot": snapshot}


def _fetch_trade_history_from_firestore(limit: int = 50) -> List[Dict[str, Any]]:
    client = _get_firestore_client()
    if client is None:
        return []
    safe_limit = max(1, min(int(limit or 50), 500))
    try:
        docs = list(
            client.collection(TRADE_EXECUTIONS_COLLECTION)
            .order_by("timestamp", direction=g_firestore.Query.DESCENDING)
            .limit(safe_limit)
            .stream()
        )
    except Exception:
        docs = list(client.collection(TRADE_EXECUTIONS_COLLECTION).limit(safe_limit).stream())
        docs.sort(
            key=lambda doc: _parse_timestamp((doc.to_dict() or {}).get("timestamp")),
            reverse=True,
        )

    rows: List[Dict[str, Any]] = []
    for doc in docs:
        payload = doc.to_dict() or {}
        payload.setdefault("trade_id", doc.id)
        rows.append(payload)
    return rows[:safe_limit]


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize and cleanup on startup/shutdown."""
    logger.info("🚀 Starting API Gateway...")

    # Initialize Pub/Sub subscriptions (Non-blocking / Robust)
    try:
        pubsub = get_pubsub_client()
        # await pubsub.initialize() # This was likely blocking/timing out

        # Move subscription to background task to prevent startup hang
        asyncio.create_task(subscribe("balance-updates", handle_balance_update))
        asyncio.create_task(subscribe("position-updates", handle_position_update))
        asyncio.create_task(subscribe("trade-executed", handle_trade_executed))

        logger.info("✅ Pub/Sub subscription tasks started")
    except Exception as e:
        logger.error(f"⚠️ Pub/Sub init warning (continuing startup): {e}")

    # Initialize ACTS cognitive agents
    try:
        from src.acts import OracleAgent, ScoutAgent, SniperAgent, get_cognitive_mesh

        mesh = get_cognitive_mesh()

        # Spawn Scout agents
        scout1 = ScoutAgent("scout-0")
        scout2 = ScoutAgent("scout-1")
        await scout1.connect(mesh)
        await scout2.connect(mesh)

        # Spawn Sniper agents
        sniper1 = SniperAgent("sniper-0")
        sniper2 = SniperAgent("sniper-1")
        await sniper1.connect(mesh)
        await sniper2.connect(mesh)

        # Spawn Oracle (decision maker)
        oracle = OracleAgent("oracle-1")
        await oracle.connect(mesh)

        logger.info("🧠 ACTS agents initialized: 2 Scouts, 2 Snipers, 1 Oracle")
    except Exception as e:
        logger.error(f"⚠️ ACTS init warning: {e}")

    yield

    logger.info("🛑 Shutting down API Gateway...")


app = FastAPI(
    title="Sapphire Trading API",
    description="Unified API Gateway for multi-platform trading bots",
    version="2.0.0",
    lifespan=lifespan,
)

# CORS for dashboard
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============ Pub/Sub Handlers ============


async def handle_balance_update(data: Dict[str, Any]):
    """Handle balance update from a bot."""
    platform = data.get("platform")
    total_balance = data.get("total_balance", 0)

    if platform:
        state.balances[platform] = total_balance
        state.last_updates[platform] = utc_now()

        # Broadcast to WebSocket clients
        await broadcast_ws(
            {
                "type": "balance_update",
                "platform": platform,
                "balance": total_balance,
                "total": state.get_total_balance(),
            }
        )


async def handle_position_update(data: Dict[str, Any]):
    """Handle position update from a bot."""
    platform = data.get("platform")
    positions = data.get("positions", [])

    if platform:
        state.positions[platform] = positions
        state.last_updates[platform] = utc_now()

        await broadcast_ws(
            {
                "type": "position_update",
                "platform": platform,
                "positions": positions,
                "total_positions": len(state.get_all_positions()),
            }
        )


async def handle_trade_executed(data: Dict[str, Any]):
    """Handle trade execution from a bot."""
    state.trade_history.append(
        {
            **data,
            "received_at": utc_now().isoformat(),
        }
    )

    # Keep last 1000 trades
    if len(state.trade_history) > 1000:
        state.trade_history = state.trade_history[-1000:]

    persist_result = _record_trade_execution(data)
    event = persist_result.get("event", {})
    if persist_result.get("stored"):
        success = bool(event.get("success", False))
        event_type = "trade_executed" if success else "trade_execution_failed"
        level = "OK" if success else "WARN"
        pnl = float(event.get("realized_pnl", 0.0) or 0.0)
        symbol = str(event.get("symbol", "UNKNOWN"))
        side = str(event.get("side", "UNKNOWN"))
        platform = str(event.get("platform", "unknown"))
        message = (
            f"Trade executed {symbol} {side} on {platform} | pnl={pnl:+.4f}"
            if success
            else f"Trade failed {symbol} {side} on {platform}"
        )
        _write_system_log(
            level=level,
            message=message,
            event_type=event_type,
            signal_id=event.get("signal_id"),
            symbol=symbol,
            action=side.lower(),
            metadata={
                "platform": platform,
                "trade_id": event.get("trade_id"),
                "realized_pnl": pnl,
                "filled_quantity": event.get("filled_quantity"),
                "avg_price": event.get("avg_price"),
                "success": success,
            },
        )
    elif persist_result.get("duplicate"):
        logger.info("Duplicate trade execution ignored: %s", event.get("trade_id"))
    elif persist_result.get("invalid"):
        logger.warning(
            "Ignored malformed trade execution event: reason=%s payload=%s",
            persist_result.get("reason"),
            {
                "trade_id": event.get("trade_id"),
                "signal_id": event.get("signal_id"),
                "platform": event.get("platform"),
                "symbol": event.get("symbol"),
                "side": event.get("side"),
            },
        )
    elif persist_result.get("error"):
        logger.warning("Trade execution persistence failed: %s", persist_result.get("error"))

    await broadcast_ws(
        {
            "type": "trade_executed",
            "trade": data,
        }
    )


async def broadcast_ws(message: Dict[str, Any]):
    """Broadcast message to all WebSocket clients."""
    disconnected = []
    for ws in state.ws_clients:
        try:
            await ws.send_json(message)
        except Exception:
            disconnected.append(ws)

    for ws in disconnected:
        state.ws_clients.remove(ws)


# ============ REST Endpoints ============


@app.get("/health")
async def health():
    """Basic health check."""
    return {"status": "healthy", "service": SERVICE_NAME}


@app.get("/health/detailed")
async def health_detailed():
    """Detailed health with all components."""
    return {
        "status": "healthy",
        "service": SERVICE_NAME,
        "timestamp": utc_now().isoformat(),
        "platforms": {
            platform: {
                "balance": balance,
                "last_update": (
                    state.last_updates.get(platform, "never").isoformat()
                    if isinstance(state.last_updates.get(platform), datetime)
                    else "never"
                ),
            }
            for platform, balance in state.balances.items()
        },
        "metrics": {
            "total_balance": state.get_total_balance(),
            "total_positions": len(state.get_all_positions()),
            "active_platforms": state.get_active_platforms(),
            "ws_clients": len(state.ws_clients),
        },
    }


@app.get("/api/dashboard")
async def dashboard():
    """Main dashboard data endpoint."""
    return {
        "portfolio": {
            "total_balance": state.get_total_balance(),
            "portfolio_balance": state.get_total_balance(),
            "total_pnl": 0.0,
            "total_pnl_percent": 0.0,
            "by_platform": state.balances,
            "open_positions": state.get_all_positions(),
            "recent_trades": state.trade_history[-10:],
        },
        "agents": await get_dashboard_agents(),
        "positions": state.get_all_positions(),
        "recent_trades": state.trade_history[-10:],
        "signals": [],
        "active_platforms": state.get_active_platforms(),
    }


async def get_dashboard_agents():
    """Format agents for the dashboard."""
    try:
        mesh = get_cognitive_mesh()
        agents = []
        for agent_id, info in mesh.agents.items():
            agents.append(
                {
                    "id": agent_id,
                    "name": agent_id.replace("-", " ").title(),
                    "emoji": "🤖",
                    "pnl": 0.0,
                    "pnlPercent": 0.0,
                    "allocation": 100,
                    "status": "active",
                    "system": "acts",
                }
            )
        return agents
    except:
        return []


@app.get("/api/agents")
async def get_agents():
    """Proxy for dashboard agents."""
    return await get_dashboard_agents()


@app.get("/api/platform-router/status")
async def platform_router_status():
    """Satisfy HFT Status Widget."""
    return {
        "health": {
            "overall_healthy": True,
            "total_platforms": 4,
            "platforms": {
                p: {"is_healthy": p in state.balances}
                for p in ["aster", "aster", "lighter", "aster"]
            },
        },
        "metrics": {
            "avg_latency_ms": 120,
        },
        "arbitrage": {
            "opportunities": len(
                [t for t in state.trade_history if "arb" in t.get("signal_id", "")]
            ),
            "profit_24h": 0.0,
        },
        "vpin": {"signals_generated": 0},
    }


@app.get("/api/history/consensus")
async def history_consensus():
    return {"success": True, "data": []}


@app.get("/api/history/portfolio")
async def history_portfolio():
    return {"success": True, "data": []}


@app.get("/api/history/agents")
async def history_agents():
    return {"success": True, "data": []}


@app.get("/api/balances")
async def get_balances():
    """Get balances from all platforms."""
    return {
        "total": state.get_total_balance(),
        "platforms": state.balances,
        "last_updates": {
            p: ts.isoformat() if isinstance(ts, datetime) else str(ts)
            for p, ts in state.last_updates.items()
        },
    }


@app.get("/api/positions")
async def get_positions():
    """Get positions from all platforms."""
    return {
        "total": len(state.get_all_positions()),
        "positions": state.get_all_positions(),
    }


@app.get("/api/positions/{platform}")
async def get_platform_positions(platform: str):
    """Get positions for a specific platform."""
    if platform not in state.positions:
        raise HTTPException(status_code=404, detail=f"Platform {platform} not found")
    return {"platform": platform, "positions": state.positions[platform]}


@app.get("/api/trades")
async def get_trades(limit: int = 50):
    """Get recent trade history."""
    safe_limit = max(1, min(int(limit or 50), 500))
    in_memory = state.trade_history[-safe_limit:]
    if in_memory:
        return {"trades": in_memory}
    return {"trades": _fetch_trade_history_from_firestore(limit=safe_limit)}


def _validate_tradingview_secret(payload: Dict[str, Any], header_secret: Optional[str]) -> None:
    if not TRADINGVIEW_WEBHOOK_SECRET:
        raise HTTPException(
            status_code=503,
            detail="TradingView webhook secret is not configured",
        )

    body_secret = _extract_text(payload, ["passphrase", "secret", "token"])
    if (
        (header_secret and header_secret == TRADINGVIEW_WEBHOOK_SECRET)
        or (body_secret and body_secret == TRADINGVIEW_WEBHOOK_SECRET)
    ):
        return
    state.tradingview_ingress_stats["rejected"] += 1
    raise HTTPException(status_code=401, detail="Invalid webhook secret")


def _build_trade_signal_from_tv_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    message_payload = _parse_message_payload(payload.get("message"))
    merged: Dict[str, Any] = {**message_payload, **payload}

    symbol = _normalize_tv_symbol(_extract_text(merged, ["symbol", "ticker", "pair", "instrument"]))
    action = _normalize_tv_action(_extract_text(merged, ["action", "side", "signal"]))
    if not symbol:
        raise HTTPException(status_code=400, detail="Missing symbol")
    if action not in VALID_TV_ACTIONS:
        raise HTTPException(status_code=400, detail=f"Unsupported action: {action}")

    side, signal_type = _map_tv_action(action)
    timestamp = _extract_text(merged, ["time", "timestamp", "ts"], default=_utc_now_iso())
    price = _coerce_float(
        merged.get("price")
        or merged.get("entry_price")
        or merged.get("close")
        or merged.get("last"),
        default=None,
    )
    confidence = _coerce_float(merged.get("confidence"), default=0.5) or 0.5
    confidence = max(0.0, min(1.0, confidence))
    quantity = _coerce_float(merged.get("quantity"), default=None)
    z_score = _coerce_float(merged.get("z_score"), default=None)
    regime_score = _coerce_float(merged.get("regime_score"), default=None)

    signal_key = _build_signal_key(
        merged,
        symbol=symbol,
        action=action,
        timestamp=timestamp,
        price=price,
    )
    if _is_duplicate_signal(signal_key):
        state.tradingview_ingress_stats["duplicates"] += 1
        _write_system_log(
            level="WARN",
            message=f"Duplicate TradingView signal ignored {action.upper()} {symbol}",
            event_type="signal_duplicate",
            symbol=symbol,
            action=action,
            metadata={"signal_key": signal_key},
        )
        return {
            "duplicate": True,
            "signal_key": signal_key,
            "symbol": symbol,
            "action": action,
        }

    signal_id = f"tv-{uuid.uuid4()}"
    trade_signal = TradeSignal(
        signal_id=signal_id,
        symbol=symbol,
        side=side,
        signal_type=signal_type,
        confidence=confidence,
        source="tradingview-gateway",
        target_platforms=[],
        entry_price=price,
        quantity=quantity,
    )
    trade_signal.metadata = {
        "origin": "cloud_gateway_webhook",
        "signal_key": signal_key,
        "raw_action": action,
        "exchange": _extract_text(merged, ["exchange"]),
        "interval": _extract_text(merged, ["interval", "timeframe"]),
        "z_score": z_score,
        "regime_score": regime_score,
        "message": _extract_text(merged, ["message"]),
        "dry_run": confidence < 0.7,
    }
    trade_signal.timestamp = datetime.now(timezone.utc)

    return {
        "duplicate": False,
        "signal_key": signal_key,
        "signal": trade_signal,
        "symbol": symbol,
        "action": action,
    }


@app.get("/webhook/health")
async def tradingview_webhook_health():
    """Health endpoint for cloud failover TradingView ingress."""
    return {
        "status": "healthy",
        "service": SERVICE_NAME,
        "tradingview_ingress": {
            "enabled": bool(TRADINGVIEW_WEBHOOK_SECRET),
            "idempotency_window_seconds": TRADINGVIEW_IDEMPOTENCY_WINDOW_SECONDS,
            "stats": state.tradingview_ingress_stats,
            "last_signal_at": state.tradingview_last_signal_at,
            "recent_count": len(state.tradingview_recent),
        },
        "timestamp": _utc_now_iso(),
    }


@app.get("/webhook/tradingview/status")
async def tradingview_webhook_status(limit: int = 20):
    """Operational status for failover ingress without exposing secrets."""
    safe_limit = max(1, min(limit, 100))
    return {
        "status": "active",
        "service": SERVICE_NAME,
        "stats": state.tradingview_ingress_stats,
        "last_signal_at": state.tradingview_last_signal_at,
        "recent": state.tradingview_recent[-safe_limit:],
        "timestamp": _utc_now_iso(),
    }


@app.post("/webhook/tradingview")
async def tradingview_webhook_ingress(
    payload: Dict[str, Any],
    request: Request,
    x_sapphire_webhook_secret: Optional[str] = Header(None, alias="X-Sapphire-Webhook-Secret"),
):
    """
    Failover TradingView ingress endpoint hosted in Cloud Run.
    Publishes standardized TradeSignal events to Pub/Sub.
    """
    _validate_tradingview_secret(payload, x_sapphire_webhook_secret)

    state.tradingview_ingress_stats["total"] += 1
    parsed = _build_trade_signal_from_tv_payload(payload)
    if parsed.get("duplicate"):
        event = {
            "timestamp": _utc_now_iso(),
            "duplicate": True,
            "symbol": parsed.get("symbol"),
            "action": parsed.get("action"),
            "source_ip": request.client.host if request.client else None,
        }
        _append_tradingview_event(event)
        return {
            "status": "duplicate_ignored",
            "signal_key": parsed.get("signal_key"),
            "symbol": parsed.get("symbol"),
            "action": parsed.get("action"),
        }

    signal: TradeSignal = parsed["signal"]
    message_id = await publish("trading-signals", signal)
    if not message_id:
        state.tradingview_ingress_stats["failed"] += 1
        _write_system_log(
            level="ERROR",
            message=f"TradingView signal publish failed {signal.symbol}",
            event_type="signal_publish_failed",
            signal_id=signal.signal_id,
            symbol=signal.symbol,
            action=parsed.get("action"),
            metadata={"signal_key": parsed.get("signal_key")},
        )
        raise HTTPException(status_code=502, detail="Failed to publish TradingView signal")

    state.tradingview_ingress_stats["published"] += 1
    state.tradingview_last_signal_at = _utc_now_iso()

    _write_system_log(
        level="INFO",
        message=f"Signal published {signal.symbol}",
        event_type="signal_published",
        signal_id=signal.signal_id,
        symbol=signal.symbol,
        action=parsed.get("action"),
        metadata={
            "channel": "pubsub",
            "message_id": message_id,
            "confidence": signal.confidence,
            "dry_run": signal.metadata.get("dry_run", False),
        },
    )

    event = {
        "timestamp": _utc_now_iso(),
        "duplicate": False,
        "signal_id": signal.signal_id,
        "symbol": signal.symbol,
        "action": parsed.get("action"),
        "signal_type": signal.signal_type.value,
        "confidence": signal.confidence,
        "message_id": message_id,
        "source_ip": request.client.host if request.client else None,
        "dry_run": signal.metadata.get("dry_run", False),
    }
    _append_tradingview_event(event)

    return {
        "status": "published",
        "signal_id": signal.signal_id,
        "symbol": signal.symbol,
        "action": parsed.get("action"),
        "signal_type": signal.signal_type.value,
        "message_id": message_id,
        "dry_run": signal.metadata.get("dry_run", False),
    }


# ============ Trading Signal Endpoints ============


class TradingSignalRequest(BaseModel):
    symbol: str
    side: str  # BUY, SELL, LONG, SHORT
    signal_type: str = "entry"
    confidence: float = 0.7
    target_platforms: List[str] = Field(default_factory=list)  # Empty = all
    entry_price: Optional[float] = None
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    quantity: Optional[float] = None


@app.post("/api/signals/create", dependencies=[Depends(require_control_token)])
async def create_signal(request: TradingSignalRequest):
    """Create and publish a trading signal to all bots."""
    try:
        normalized_targets = []
        for target in request.target_platforms:
            value = str(target or "").strip().lower()
            if value:
                normalized_targets.append(value)

        quantity = request.quantity
        if quantity is not None and float(quantity) <= 0:
            raise ValueError("quantity must be > 0 when provided")

        signal = TradeSignal(
            signal_id=f"manual-{datetime.now().timestamp()}",
            symbol=request.symbol,
            side=TradeSide[request.side.upper()],
            signal_type=SignalType[request.signal_type.upper()],
            confidence=request.confidence,
            source="api-gateway",
            target_platforms=normalized_targets,
            entry_price=request.entry_price,
            stop_loss=request.stop_loss,
            take_profit=request.take_profit,
            quantity=quantity,
        )

        message_id = await publish("trading-signals", signal)
        if not message_id:
            raise RuntimeError("Failed to publish signal to Pub/Sub")

        return {"status": "published", "signal_id": signal.signal_id, "message_id": message_id}

    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/signals/close-all", dependencies=[Depends(require_control_token)])
async def close_all_positions():
    """Send signal to close all positions across all platforms."""
    from models import RiskAlert

    alert = RiskAlert(
        alert_id=f"manual-close-{datetime.now().timestamp()}",
        severity="warning",
        alert_type="manual_close",
        message="Manual close all positions requested",
        action="close_all",
    )

    await publish("risk-alerts", alert)

    return {"status": "published", "message": "Close all signal sent to all bots"}


# ============ WebSocket Endpoint ============


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket for real-time updates."""
    await websocket.accept()
    state.ws_clients.append(websocket)

    logger.info(f"WebSocket client connected. Total: {len(state.ws_clients)}")

    try:
        # Send initial state
        await websocket.send_json(
            {
                "type": "init",
                "balances": state.balances,
                "positions": state.get_all_positions(),
                "total_balance": state.get_total_balance(),
                "recent_trades": state.trade_history[-50:],
            }
        )

        # Keep connection alive
        while True:
            try:
                data = await asyncio.wait_for(websocket.receive_text(), timeout=30)
                # Handle incoming messages (e.g., subscriptions)
                if data == "ping":
                    await websocket.send_text("pong")
            except asyncio.TimeoutError:
                await websocket.send_text("ping")

    except WebSocketDisconnect:
        pass
    finally:
        if websocket in state.ws_clients:
            state.ws_clients.remove(websocket)
        logger.info(f"WebSocket client disconnected. Total: {len(state.ws_clients)}")


# ============ Platform Status ============


@app.get("/api/platforms")
async def get_platforms():
    """Get status of all trading platforms."""
    return {
        "platforms": [
            {
                "name": platform,
                "balance": state.balances.get(platform, 0),
                "positions": len(state.positions.get(platform, [])),
                "last_update": state.last_updates.get(platform, "never"),
                "status": "active" if platform in state.balances else "inactive",
            }
            for platform in ["aster", "aster", "lighter", "aster"]
        ]
    }


# ============ ACTS - Autonomous Cognitive Trading Swarm ============


# ACTS State (would be populated by cognitive mesh)
class ACTSState:
    """State for the ACTS cognitive swarm."""

    def __init__(self):
        self.agents = {}
        self.last_reasoning = {}
        self.episodes = []
        self.mesh_active = False


acts_state = ACTSState()

# Import ACTS modules from bundled package
from src.acts import MarketSnapshot, get_cognitive_mesh, get_enhanced_memory, init_cognitive_mesh

# Global ACTS mesh instance
_acts_mesh = None
_acts_memory = None


async def get_acts_instances():
    """Get or initialize ACTS instances."""
    global _acts_mesh, _acts_memory
    if _acts_mesh is None:
        _acts_mesh = get_cognitive_mesh()
        _acts_memory = get_enhanced_memory()
    return _acts_mesh, _acts_memory


@app.get("/api/acts/status")
async def get_acts_status():
    """Get ACTS swarm status."""
    try:
        mesh, memory = await get_acts_instances()

        return {
            "status": "active" if mesh else "inactive",
            "mesh": {
                "agents_registered": len(mesh.agents) if mesh else 0,
                "messages_logged": len(mesh.message_log) if mesh else 0,
            },
            "memory": memory.get_stats() if memory else {},
            "timestamp": utc_now().isoformat(),
        }
    except Exception as e:
        return {
            "status": "error",
            "error": str(e),
            "timestamp": utc_now().isoformat(),
        }


@app.get("/api/acts/agents")
async def get_acts_agents():
    """Get list of ACTS agents and their activity."""
    try:
        mesh, _ = await get_acts_instances()

        if not mesh:
            return {"agents": [], "error": "Mesh not initialized"}

        agents = []
        for agent_id, info in mesh.agents.items():
            # Get recent messages from this agent
            recent_msgs = [m for m in mesh.message_log[-50:] if m.agent_id == agent_id]

            role_value = info.get("role")
            if hasattr(role_value, "value"):
                role_value = role_value.value

            agents.append(
                {
                    "id": agent_id,
                    "role": role_value or "unknown",
                    "capabilities": info.get("capabilities", []),
                    "message_count": len(recent_msgs),
                    "last_message": recent_msgs[-1].reasoning[:100] if recent_msgs else None,
                    "last_confidence": recent_msgs[-1].confidence if recent_msgs else None,
                }
            )

        return {"agents": agents, "total": len(agents)}

    except Exception as e:
        return {"agents": [], "error": str(e)}


@app.get("/api/acts/memory")
async def get_acts_memory():
    """Get episodic memory insights."""
    try:
        _, memory = await get_acts_instances()

        # Get recent episodes
        recent_episodes = sorted(
            memory.episodes.values(),
            key=lambda e: e.start_time,
            reverse=True,
        )[:10]

        episode_summaries = []
        for ep in recent_episodes:
            regime_val = ep.regime.value if hasattr(ep.regime, "value") else ep.regime
            episode_summaries.append(
                {
                    "id": ep.episode_id,
                    "name": ep.name,
                    "regime": regime_val,
                    "duration_hours": (
                        (ep.end_time - ep.start_time).total_seconds() / 3600 if ep.end_time else 0
                    ),
                    "pnl": ep.total_pnl,
                    "win_rate": ep.win_rate,
                    "trade_count": len(ep.trades),
                    "lesson_tactical": ep.lessons.tactical if ep.lessons else None,
                    "lesson_strategic": ep.lessons.strategic if ep.lessons else None,
                }
            )

        return {
            "stats": memory.get_stats(),
            "temporal_insights": (
                memory.get_temporal_insights() if hasattr(memory, "get_temporal_insights") else {}
            ),
            "recent_episodes": episode_summaries,
        }

    except Exception as e:
        return {"error": str(e), "stats": {}, "recent_episodes": []}


@app.get("/api/acts/reasoning/{symbol}")
async def get_acts_reasoning(symbol: str):
    """Get cognitive reasoning for a symbol."""
    try:
        from datetime import datetime as dt
        from datetime import timezone as tz

        mesh, memory = await get_acts_instances()

        # Get recent reasoning messages about this symbol
        reasoning_msgs = [
            {
                "agent": m.agent_id,
                "role": m.agent_role.value if hasattr(m.agent_role, "value") else m.agent_role,
                "reasoning": m.reasoning,
                "action": m.suggested_action,
                "confidence": m.confidence,
                "timestamp": m.timestamp.isoformat() if hasattr(m, "timestamp") else None,
            }
            for m in mesh.message_log[-100:]
            if m.symbol == symbol.upper()
        ][
            -10:
        ]  # Last 10

        # Get memory recall
        snapshot = MarketSnapshot(timestamp=dt.now(tz.utc))
        memory_advice = (
            await memory.recall_for_decision(
                symbol=symbol.upper(),
                snapshot=snapshot,
                context="Dashboard query",
            )
            if hasattr(memory, "recall_for_decision")
            else "No memory available"
        )

        return {
            "symbol": symbol.upper(),
            "reasoning": reasoning_msgs,
            "memory_advice": memory_advice,
            "timestamp": utc_now().isoformat(),
        }

    except Exception as e:
        return {
            "symbol": symbol.upper(),
            "reasoning": [],
            "memory_advice": f"Error: {e}",
            "timestamp": utc_now().isoformat(),
        }


if __name__ == "__main__":
    import uvicorn

    setup_logging("INFO")
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", 8080)))
