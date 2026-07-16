#!/usr/bin/env python3
"""Autonomous trading executor bridge with Telegram approval gate.

Connects the Sapphire signal pipeline to the Robinhood Crypto API.

Safety-first design:
  - Disabled by default; paper-trading mode is the default.
  - Requires an explicit Telegram approval before any action.
  - Requires a file-system kill switch to be absent.
  - Requires pre-flight readiness, notional cap, and daily loss checks.
  - Live trading requires both ``--live`` AND ``AUTO_EXECUTOR_LIVE=1`` AND a
    typed confirmation token. No code path enables live mode automatically.

Usage:
    # Paper mode (default) — logs only, never submits to Robinhood
    python3 services/alpha/auto_executor.py

    # Live mode (manual, gated)
    AUTO_EXECUTOR_LIVE=1 python3 services/alpha/auto_executor.py --live \
        --confirm-token AUTO_EXECUTOR_LIVE_BUY_BTC-USD_5.00

The module is intentionally standalone and does not import the dashboard,
scheduler, or Telegram bot server, so it can be reviewed in isolation.
"""

from __future__ import annotations

import argparse
import contextlib
import json
import logging
import os
import ssl
import sys
import time
import urllib.error
import urllib.request
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, date
from pathlib import Path
from typing import Any

# ─── Path setup ───────────────────────────────────────────────────────────────

ROOT = Path(__file__).resolve().parents[2]
SERVICES_ALPHA = ROOT / "services" / "alpha"

for _p in (
    str(ROOT),
    str(SERVICES_ALPHA),
    str(ROOT / "lib" / "core"),
    str(ROOT / "scripts" / "ops"),
):
    if _p not in sys.path:
        sys.path.insert(0, _p)

log = logging.getLogger(__name__)

# ─── Optional imports (graceful degradation) ──────────────────────────────────

# Readiness report
_ROBINHOOD_READINESS_AVAILABLE = False
try:
    from robinhood_live_readiness import collect_report as _collect_readiness_report

    _ROBINHOOD_READINESS_AVAILABLE = True
except Exception as _e:  # pragma: no cover - runtime import guard
    log.debug("robinhood_live_readiness unavailable: %s", _e)

# Robinhood order submit
_ROBINHOOD_READER_AVAILABLE = False
try:
    from lib.portfolio.robinhood import RobinhoodReader

    _ROBINHOOD_READER_AVAILABLE = True
except Exception as _e:  # pragma: no cover - runtime import guard
    log.debug("RobinhoodReader unavailable: %s", _e)

# Strategy lab order drafts
try:
    from lib.trading.strategy_lab import (
        ROBINHOOD_FIRST_REAL_FUNDS_TEST_MAX_USD,
        asset_spec,
        build_order_drafts,
    )

    _STRATEGY_LAB_AVAILABLE = True
except Exception as _e:  # pragma: no cover - runtime import guard
    log.debug("strategy_lab unavailable: %s", _e)
    _STRATEGY_LAB_AVAILABLE = False

# ─── Constants ────────────────────────────────────────────────────────────────

SIGNALS_DIR = ROOT / "data" / "signals"
EXECUTOR_AUDIT_LOG = ROOT / "data" / "trading" / "auto_executor_orders.jsonl"

# Operator-controlled pause flag. If present, the executor skips all work.
KILLSWITCH_PATH = Path.home() / ".sapphire" / "autonomous_trading_pause"

# Daily loss tracker (file-backed, so it survives restarts).
DAILY_LOSS_FILE = Path.home() / ".sapphire" / "auto_executor_daily_loss.json"

# Telegram polling / send state
DEFAULT_POLL_INTERVAL_SECONDS = 30
DEFAULT_TELEGRAM_TIMEOUT_SECONDS = 30

# Safety caps
DEFAULT_MAX_NOTIONAL_USD = ROBINHOOD_FIRST_REAL_FUNDS_TEST_MAX_USD if (
    _STRATEGY_LAB_AVAILABLE
) else 5.0
DEFAULT_DAILY_LOSS_LIMIT_USD = 20.0

# Env vars
AUTO_EXECUTOR_LIVE_ENV = "AUTO_EXECUTOR_LIVE"
PAPER_TRADING_ENV = "PAPER_TRADING"

# Telegram credentials (same precedence as the rest of Sapphire)
TELEGRAM_BOT_TOKEN_ENV = "TELEGRAM_BOT_TOKEN"
TELEGRAM_CHAT_ID_ENV = "TELEGRAM_CHAT_ID"

# ─── Data classes ─────────────────────────────────────────────────────────────


@dataclass
class ExecutorConfig:
    """Runtime configuration for the auto executor."""

    live: bool = False
    confirm_token: str = ""
    max_notional_usd: float = DEFAULT_MAX_NOTIONAL_USD
    daily_loss_limit_usd: float = DEFAULT_DAILY_LOSS_LIMIT_USD
    poll_interval_seconds: int = DEFAULT_POLL_INTERVAL_SECONDS
    signals_dir: Path = field(default_factory=lambda: Path(SIGNALS_DIR))
    audit_log: Path = field(default_factory=lambda: Path(EXECUTOR_AUDIT_LOG))
    killswitch_path: Path = field(default_factory=lambda: Path(KILLSWITCH_PATH))
    daily_loss_file: Path = field(default_factory=lambda: Path(DAILY_LOSS_FILE))

    # Injectable for tests
    telegram_api_class: type["TelegramAPI"] | None = None
    robinhood_submit_fn: Any | None = None
    readiness_fn: Any | None = None
    time_fn: Any | None = None


@dataclass
class SignalRecord:
    """Minimal parsed signal record from the JSONL audit trail."""

    pipeline_id: str
    timestamp: str
    symbol: str
    action: str
    direction: str
    strategy: str
    price: float
    confidence: float
    score: float
    routing: str
    position_usd: float
    position_pct: float
    kernel_ok: bool
    kernel_reason: str
    take_profit: float = 0.0
    stop_loss: float = 0.0
    rr_ratio: float = 0.0
    raw: dict[str, Any] = field(default_factory=dict)


# ─── Telegram client (minimal, no external deps) ──────────────────────────────


class TelegramAPI:
    """Thin Telegram Bot API client for the executor's approval flow."""

    def __init__(self, token: str, chat_id: str, timeout_seconds: float = 30.0) -> None:
        self._token = token
        self._chat_id = chat_id
        self._timeout = timeout_seconds
        self._ssl_ctx = ssl.create_default_context()

    def _url(self, method: str) -> str:
        return f"https://api.telegram.org/bot{self._token}/{method}"

    def _post(self, method: str, payload: dict[str, Any]) -> dict[str, Any]:
        body = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            self._url(method),
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=self._timeout, context=self._ssl_ctx) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def send_confirmation_request(self, signal: SignalRecord) -> dict[str, Any] | None:
        """Send an inline-keyboard Approve/Reject message for a signal."""
        if not self._token or not self._chat_id:
            log.warning("Telegram not configured; cannot send confirmation request")
            return None

        icon = "🟢" if signal.direction == "long" else "🔴" if signal.direction == "short" else "⚪"
        text = (
            f"{icon} *Auto-Executor Approval Required*\n\n"
            f"Signal: `{signal.pipeline_id}`\n"
            f"Action: *{signal.action.upper()} {signal.symbol}*\n"
            f"Price: `${signal.price:,.4f}`\n"
            f"Confidence: `{signal.confidence:.0%}` | Score: `{signal.score:.0f}/100`\n"
            f"Recommended size: `${signal.position_usd:.2f}` ({signal.position_pct:.1%})\n"
            f"Strategy: `{signal.strategy}`\n\n"
            f"Tap *Approve* to queue for execution, *Reject* to discard."
        )

        payload = {
            "chat_id": self._chat_id,
            "text": text,
            "parse_mode": "Markdown",
            "reply_markup": {
                "inline_keyboard": [
                    [
                        {
                            "text": "✅ Approve",
                            "callback_data": f"ae:{signal.pipeline_id}:approve",
                        },
                        {
                            "text": "❌ Reject",
                            "callback_data": f"ae:{signal.pipeline_id}:reject",
                        },
                    ]
                ]
            },
        }
        try:
            data = self._post("sendMessage", payload)
            log.info("Telegram confirmation request sent for %s", signal.pipeline_id)
            return data
        except Exception as exc:
            log.warning("Telegram send failed for %s: %s", signal.pipeline_id, exc)
            return None

    def get_callback_updates(self, offset: int = 0) -> list[dict[str, Any]]:
        """Poll Telegram for callback queries from inline keyboards."""
        if not self._token:
            return []
        payload = {
            "offset": offset,
            "limit": 100,
            "timeout": min(10, int(self._timeout)),
            "allowed_updates": ["callback_query"],
        }
        try:
            data = self._post("getUpdates", payload)
            result = data.get("result", [])
            return [item for item in result if isinstance(item, dict)]
        except Exception as exc:
            log.warning("Telegram getUpdates failed: %s", exc)
            return []

    def answer_callback_query(self, callback_query_id: str) -> None:
        """Acknowledge a callback query so the spinner disappears."""
        if not self._token:
            return
        try:
            self._post("answerCallbackQuery", {"callback_query_id": callback_query_id})
        except Exception as exc:
            log.warning("answerCallbackQuery failed: %s", exc)


# ─── Telegram credentials resolution ──────────────────────────────────────────


def _resolve_telegram_credentials() -> tuple[str, str]:
    """Resolve Telegram bot token and chat id from env or secret files."""
    token = os.environ.get(TELEGRAM_BOT_TOKEN_ENV, "").strip()
    chat_id = os.environ.get(TELEGRAM_CHAT_ID_ENV, "").strip()

    if not token:
        for path in [
            Path.home() / ".config" / "sapphire-secrets" / "telegram_bot_token",
            Path.home() / ".config" / "sapphire" / "telegram_bot_token",
        ]:
            if path.exists():
                token = path.read_text().strip()
                break

    if not chat_id:
        for path in [
            Path.home() / ".config" / "sapphire-secrets" / "telegram_chat_id",
            Path.home() / ".config" / "sapphire" / "telegram_chat_id",
        ]:
            if path.exists():
                chat_id = path.read_text().strip()
                break

    return token, chat_id


# ─── Signal reading / writing ─────────────────────────────────────────────────


def _today_str() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%d")


def _signal_path(signals_dir: Path, day: str | None = None) -> Path:
    day = day or _today_str()
    return signals_dir / f"{day}.jsonl"


def _load_jsonl_records(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    records: list[dict[str, Any]] = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        with contextlib.suppress(json.JSONDecodeError):
            records.append(json.loads(line))
    return records


def _parse_signal_record(raw: dict[str, Any]) -> SignalRecord | None:
    """Parse a signal record from the audit trail."""
    routing = str(raw.get("routing", "")).upper()
    if routing != "CONFIRMATION_REQUIRED":
        return None
    return SignalRecord(
        pipeline_id=str(raw.get("pipeline_id", "")),
        timestamp=str(raw.get("timestamp", "")),
        symbol=str(raw.get("symbol", "")),
        action=str(raw.get("action", "")),
        direction=str(raw.get("direction", "")),
        strategy=str(raw.get("strategy", "")),
        price=float(raw.get("price", 0.0) or 0.0),
        confidence=float(raw.get("confidence", 0.0) or 0.0),
        score=float(raw.get("score", 0.0) or 0.0),
        routing=routing,
        position_usd=float(raw.get("position_usd", 0.0) or 0.0),
        position_pct=float(raw.get("position_pct", 0.0) or 0.0),
        kernel_ok=bool(raw.get("kernel_ok", False)),
        kernel_reason=str(raw.get("kernel_reason", "")),
        take_profit=float(raw.get("take_profit", 0.0) or 0.0),
        stop_loss=float(raw.get("stop_loss", 0.0) or 0.0),
        rr_ratio=float(raw.get("rr_ratio", 0.0) or 0.0),
        raw=raw,
    )


def _find_confirmation_required_signals(signals_dir: Path) -> list[SignalRecord]:
    """Return all CONFIRMATION_REQUIRED signals from today's audit file."""
    path = _signal_path(signals_dir)
    records = _load_jsonl_records(path)
    signals: list[SignalRecord] = []
    for raw in records:
        parsed = _parse_signal_record(raw)
        if parsed is not None:
            signals.append(parsed)
    return signals


def _executor_decisions_for_day(signals_dir: Path) -> dict[str, str]:
    """Map pipeline_id -> 'APPROVED' | 'REJECTED' from today's audit file."""
    path = _signal_path(signals_dir)
    records = _load_jsonl_records(path)
    decisions: dict[str, str] = {}
    for raw in records:
        if raw.get("record_type") == "executor_decision":
            pid = str(raw.get("pipeline_id", ""))
            decision = str(raw.get("decision", "")).upper()
            if pid and decision in {"APPROVED", "REJECTED"}:
                decisions[pid] = decision
    return decisions


def _append_executor_decision(
    signals_dir: Path,
    pipeline_id: str,
    decision: str,
    reason: str = "",
    source: str = "telegram_inline_button",
) -> None:
    """Append an executor approval/rejection record to the audit trail."""
    path = _signal_path(signals_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "record_type": "executor_decision",
        "pipeline_id": pipeline_id,
        "decision": decision.upper(),
        "source": source,
        "reason": reason,
        "timestamp": datetime.now(UTC).isoformat(),
    }
    with open(path, "a") as f:
        f.write(json.dumps(record) + "\n")


def _mark_confirmation_sent(signals_dir: Path, pipeline_id: str) -> None:
    """Record that a confirmation request was sent so we do not spam."""
    path = _signal_path(signals_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "record_type": "executor_confirmation_sent",
        "pipeline_id": pipeline_id,
        "timestamp": datetime.now(UTC).isoformat(),
    }
    with open(path, "a") as f:
        f.write(json.dumps(record) + "\n")


def _already_sent_confirmation(signals_dir: Path, pipeline_id: str) -> bool:
    path = _signal_path(signals_dir)
    for raw in _load_jsonl_records(path):
        if (
            raw.get("record_type") == "executor_confirmation_sent"
            and raw.get("pipeline_id") == pipeline_id
        ):
            return True
    return False


# ─── Safety / pre-flight checks ───────────────────────────────────────────────


def _paper_trading_enabled() -> bool:
    """Return True unless PAPER_TRADING is explicitly set to a false value."""
    raw = os.environ.get(PAPER_TRADING_ENV, "").strip().lower()
    if raw in {"0", "false", "no", "off", "n"}:
        return False
    return True  # default on, including unset


def _killswitch_active(killswitch_path: Path) -> bool:
    return killswitch_path.exists()


def _load_daily_loss_usd(daily_loss_file: Path) -> float:
    """Return the realized loss total for today (negative PnL only)."""
    if not daily_loss_file.exists():
        return 0.0
    try:
        data = json.loads(daily_loss_file.read_text())
        if data.get("date") == str(date.today()):
            return float(data.get("loss_usd", 0.0))
    except (json.JSONDecodeError, TypeError, ValueError):
        pass
    return 0.0


def _record_loss_usd(daily_loss_file: Path, loss_usd: float) -> None:
    """Add a realized loss amount to today's tracker."""
    daily_loss_file.parent.mkdir(parents=True, exist_ok=True)
    today = str(date.today())
    current = 0.0
    if daily_loss_file.exists():
        try:
            data = json.loads(daily_loss_file.read_text())
            if data.get("date") == today:
                current = float(data.get("loss_usd", 0.0))
        except (json.JSONDecodeError, TypeError, ValueError):
            pass
    daily_loss_file.write_text(
        json.dumps({"date": today, "loss_usd": round(current + max(0.0, loss_usd), 2)}, indent=2)
    )


def _collect_readiness(
    signal: SignalRecord,
    live_read_only: bool = False,
    readiness_fn: Any | None = None,
) -> dict[str, Any]:
    """Return the Robinhood live-readiness report for a signal."""
    fn = readiness_fn or (_collect_readiness_report if _ROBINHOOD_READINESS_AVAILABLE else None)
    if fn is None:
        return {
            "verdict": "BLOCKED_READINESS_UNAVAILABLE",
            "reason": "robinhood_live_readiness module unavailable",
        }
    try:
        return fn(
            symbol=signal.symbol,
            action=signal.action,
            notional_usd=signal.position_usd,
            live_read_only=live_read_only,
            max_spread_bps=150.0,
        )
    except Exception as exc:
        log.warning("Readiness report failed for %s: %s", signal.pipeline_id, exc)
        return {"verdict": "BLOCKED_READINESS_ERROR", "reason": str(exc)}


def _run_preflight_checks(
    signal: SignalRecord,
    config: ExecutorConfig,
    live_read_only: bool = False,
) -> tuple[bool, list[str]]:
    """Run all pre-flight safety checks. Returns (ok, blockers)."""
    blockers: list[str] = []

    if _killswitch_active(config.killswitch_path):
        blockers.append("killswitch_active")

    if not signal.kernel_ok:
        blockers.append(f"kernel_blocked:{signal.kernel_reason}")

    if signal.position_usd <= 0:
        blockers.append("zero_position_size")

    if signal.position_usd > config.max_notional_usd:
        blockers.append(
            f"notional_cap_exceeded:{signal.position_usd:.2f}>{config.max_notional_usd:.2f}"
        )

    daily_loss = _load_daily_loss_usd(config.daily_loss_file)
    if daily_loss >= config.daily_loss_limit_usd:
        blockers.append(
            f"daily_loss_limit_reached:{daily_loss:.2f}>={config.daily_loss_limit_usd:.2f}"
        )

    readiness = _collect_readiness(signal, live_read_only=live_read_only, readiness_fn=config.readiness_fn)
    readiness_verdict = readiness.get("verdict", "")
    if live_read_only and readiness_verdict != "READY_FOR_MANUAL_CONFIRMATION":
        blockers.append(f"readiness_not_ready:{readiness_verdict}")

    return (not blockers), blockers


# ─── Order construction / execution ───────────────────────────────────────────


def _normalize_side(action: str) -> str:
    a = str(action).lower()
    if a in {"buy", "long", "entry_long"}:
        return "buy"
    if a in {"sell", "short", "entry_short", "close", "exit"}:
        return "sell"
    return "hold"


def _robinhood_symbol(symbol: str) -> str:
    if _STRATEGY_LAB_AVAILABLE:
        spec = asset_spec(symbol)
        if spec.robinhood_symbol:
            return spec.robinhood_symbol
    # Fallback: common Robinhood crypto pair shape
    s = str(symbol).upper()
    if "-" in s:
        return s
    return f"{s}-USD"


def _build_order_body(signal: SignalRecord) -> dict[str, Any]:
    """Build a Robinhood v2 limit order body from an approved signal."""
    side = _normalize_side(signal.action)
    symbol = _robinhood_symbol(signal.symbol)
    client_order_id = str(uuid.uuid4())

    # Limit price: use signal price as a starting point. In a production flow
    # this would be refreshed from a live quote immediately before submit.
    limit_price = signal.price
    if limit_price <= 0:
        raise ExecutorError(f"invalid limit price {limit_price} for {signal.pipeline_id}")

    limit_config: dict[str, Any] = {
        "limit_price": f"{limit_price:.2f}",
        "time_in_force": "gtc",
    }
    if side == "buy":
        limit_config["quote_amount"] = f"{signal.position_usd:.2f}"
    else:
        # For sell, we need quantity. Estimate from price and notional.
        qty = signal.position_usd / limit_price if limit_price > 0 else 0.0
        limit_config["asset_quantity"] = f"{qty:.12f}".rstrip("0").rstrip(".")

    return {
        "client_order_id": client_order_id,
        "side": side,
        "type": "limit",
        "symbol": symbol,
        "limit_order_config": limit_config,
    }


def _expected_live_token(signal: SignalRecord) -> str:
    """Return the typed confirmation token required for live execution."""
    side = _normalize_side(signal.action)
    symbol = _robinhood_symbol(signal.symbol)
    return f"AUTO_EXECUTOR_LIVE_{side.upper()}_{symbol}_{signal.position_usd:.2f}"


def _submit_to_robinhood(signal: SignalRecord) -> dict[str, Any]:
    """Submit a real order to Robinhood Crypto."""
    if not _ROBINHOOD_READER_AVAILABLE:
        raise ExecutorError("RobinhoodReader unavailable")

    reader = RobinhoodReader()
    if not reader.is_configured():
        raise ExecutorError("Robinhood credentials not configured")

    account_number = reader._get_account_number()
    if not account_number:
        raise ExecutorError("Robinhood account number unavailable")

    body = _build_order_body(signal)
    client_order_id = body["client_order_id"]
    path = f"/api/v2/crypto/trading/orders/?account_number={account_number}"
    response = reader._request_json("POST", path, body=body)
    return {
        "client_order_id": client_order_id,
        "submit_response": _sanitize_submit_response(response),
    }


def _sanitize_submit_response(response: Any) -> dict[str, Any]:
    if not isinstance(response, dict):
        return {"raw_type": type(response).__name__}
    allowed = {
        "id",
        "client_order_id",
        "symbol",
        "side",
        "type",
        "state",
        "created_at",
        "updated_at",
        "average_price",
        "filled_asset_quantity",
    }
    return {key: response.get(key) for key in sorted(allowed) if key in response}


def _append_executor_audit(
    audit_log: Path,
    signal: SignalRecord,
    *,
    mode: str,
    verdict: str,
    blockers: list[str] | None = None,
    order_body: dict[str, Any] | None = None,
    confirmation_token: str = "",
    submit_response: dict[str, Any] | None = None,
    error: str = "",
) -> None:
    """Append a structured executor audit record."""
    audit_log.parent.mkdir(parents=True, exist_ok=True)
    record: dict[str, Any] = {
        "schema_version": 1,
        "generated_at": datetime.now(UTC).isoformat(),
        "mode": mode,
        "verdict": verdict,
        "pipeline_id": signal.pipeline_id,
        "signal_timestamp": signal.timestamp,
        "symbol": signal.symbol,
        "action": signal.action,
        "direction": signal.direction,
        "price": signal.price,
        "position_usd": signal.position_usd,
        "max_notional_usd": DEFAULT_MAX_NOTIONAL_USD,
        "paper_mode": mode != "live",
        "real_order_submitted": mode == "live" and verdict == "SUBMITTED",
        "order_body": order_body,
        "confirmation_token_required": confirmation_token,
    }
    if blockers:
        record["blockers"] = blockers
    if submit_response:
        record["submit_response"] = submit_response
    if error:
        record["error"] = error
    with open(audit_log, "a") as f:
        f.write(json.dumps(record, sort_keys=True) + "\n")


# ─── Main executor logic ──────────────────────────────────────────────────────


def _execute_signal(signal: SignalRecord, config: ExecutorConfig) -> dict[str, Any]:
    """Execute (paper or live) an approved signal after pre-flight checks."""
    is_live = config.live and os.environ.get(AUTO_EXECUTOR_LIVE_ENV, "").strip() == "1"
    mode = "live" if is_live else "paper"

    # Pre-flight checks (live mode runs read-only Robinhood probes)
    ok, blockers = _run_preflight_checks(
        signal, config, live_read_only=is_live
    )
    if not ok:
        _append_executor_audit(
            config.audit_log,
            signal,
            mode=mode,
            verdict="BLOCKED",
            blockers=blockers,
        )
        return {"verdict": "BLOCKED", "blockers": blockers}

    order_body = _build_order_body(signal)
    token = _expected_live_token(signal)

    if not is_live:
        # Paper mode: log the intent but never submit.
        _append_executor_audit(
            config.audit_log,
            signal,
            mode="paper",
            verdict="PAPER_EXECUTED",
            order_body=order_body,
            confirmation_token=token,
        )
        log.info("PAPER executed for %s (%s %s)", signal.pipeline_id, signal.action, signal.symbol)
        return {"verdict": "PAPER_EXECUTED", "order_body": order_body}

    # Live mode: confirmation token gate
    if config.confirm_token != token:
        _append_executor_audit(
            config.audit_log,
            signal,
            mode="live",
            verdict="BLOCKED_TOKEN_MISMATCH",
            order_body=order_body,
            confirmation_token=token,
        )
        return {"verdict": "BLOCKED_TOKEN_MISMATCH"}

    try:
        submit_fn = config.robinhood_submit_fn or _submit_to_robinhood
        result = submit_fn(signal)
        _append_executor_audit(
            config.audit_log,
            signal,
            mode="live",
            verdict="SUBMITTED",
            order_body=order_body,
            confirmation_token=token,
            submit_response=result.get("submit_response"),
        )
        log.info("LIVE submitted for %s", signal.pipeline_id)
        return {"verdict": "SUBMITTED", "client_order_id": result.get("client_order_id")}
    except Exception as exc:
        _append_executor_audit(
            config.audit_log,
            signal,
            mode="live",
            verdict="SUBMIT_ERROR",
            order_body=order_body,
            confirmation_token=token,
            error=str(exc),
        )
        log.exception("Live submit failed for %s", signal.pipeline_id)
        return {"verdict": "SUBMIT_ERROR", "error": str(exc)}


def _process_pending_confirmations(
    signals_dir: Path,
    telegram: TelegramAPI,
    offset: int,
) -> tuple[dict[str, str], int]:
    """Poll Telegram callbacks and return decisions + new offset."""
    decisions: dict[str, str] = {}
    try:
        updates = telegram.get_callback_updates(offset=offset)
    except Exception as exc:
        log.warning("Failed to poll Telegram callbacks: %s", exc)
        return decisions, offset

    for update in updates:
        update_id = update.get("update_id")
        if isinstance(update_id, int):
            offset = max(offset, update_id + 1)

        callback = update.get("callback_query", {})
        callback_id = callback.get("id")
        data = str(callback.get("data", ""))
        if not data.startswith("ae:"):
            continue

        parts = data.split(":")
        if len(parts) != 3:
            continue
        _, pipeline_id, action = parts
        decision = "APPROVED" if action == "approve" else "REJECTED"
        decisions[pipeline_id] = decision

        if callback_id:
            try:
                telegram.answer_callback_query(callback_id)
            except Exception:
                pass

        _append_executor_decision(
            signals_dir,
            pipeline_id,
            decision,
            reason=f"telegram_inline_button:{action}",
        )
        log.info("Executor decision recorded: %s -> %s", pipeline_id, decision)

    return decisions, offset


def _send_confirmation_requests(
    signals: list[SignalRecord],
    decisions: dict[str, str],
    signals_dir: Path,
    telegram: TelegramAPI,
) -> None:
    """Send Telegram confirmation requests for signals that need one."""
    for signal in signals:
        if signal.pipeline_id in decisions:
            continue
        if _already_sent_confirmation(signals_dir, signal.pipeline_id):
            continue
        telegram.send_confirmation_request(signal)
        _mark_confirmation_sent(signals_dir, signal.pipeline_id)


def run_once(config: ExecutorConfig) -> None:
    """Single executor pass: send confirmations, process approvals, execute."""
    if _killswitch_active(config.killswitch_path):
        log.info("Kill switch active at %s; skipping execution", config.killswitch_path)
        return

    signals = _find_confirmation_required_signals(config.signals_dir)
    if not signals:
        log.debug("No confirmation-required signals found")
        return

    decisions = _executor_decisions_for_day(config.signals_dir)

    # Send confirmation requests for signals that have not been decided yet.
    token, chat_id = _resolve_telegram_credentials()
    telegram_cls = config.telegram_api_class or TelegramAPI
    telegram = telegram_cls(token=token, chat_id=chat_id)
    _send_confirmation_requests(signals, decisions, config.signals_dir, telegram)

    # Poll for any new Telegram callback decisions.
    new_decisions, _ = _process_pending_confirmations(
        config.signals_dir, telegram, offset=0
    )
    decisions.update(new_decisions)

    # Execute approved signals.
    for signal in signals:
        decision = decisions.get(signal.pipeline_id)
        if decision == "APPROVED":
            _execute_signal(signal, config)
        elif decision == "REJECTED":
            log.info("Signal %s rejected; skipping execution", signal.pipeline_id)


def run_loop(config: ExecutorConfig) -> None:
    """Run the executor in a polling loop."""
    log.info(
        "Auto-executor starting: live=%s paper=%s poll_interval=%ss",
        config.live,
        not config.live,
        config.poll_interval_seconds,
    )
    while True:
        try:
            run_once(config)
        except Exception as exc:
            log.exception("Executor pass failed: %s", exc)
        time.sleep(config.poll_interval_seconds)


# ─── CLI ──────────────────────────────────────────────────────────────────────


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--live",
        action="store_true",
        help=(
            "Enable live Robinhood order submission. Also requires "
            f"{AUTO_EXECUTOR_LIVE_ENV}=1 and a typed --confirm-token."
        ),
    )
    parser.add_argument(
        "--confirm-token",
        default="",
        help="Typed confirmation token required when --live is set.",
    )
    parser.add_argument(
        "--max-notional-usd",
        type=float,
        default=DEFAULT_MAX_NOTIONAL_USD,
        help="Maximum notional USD allowed per approved signal.",
    )
    parser.add_argument(
        "--daily-loss-limit-usd",
        type=float,
        default=DEFAULT_DAILY_LOSS_LIMIT_USD,
        help="Daily realized-loss ceiling in USD.",
    )
    parser.add_argument(
        "--poll-interval",
        type=int,
        default=DEFAULT_POLL_INTERVAL_SECONDS,
        help="Seconds between signal-directory polls.",
    )
    parser.add_argument(
        "--signals-dir",
        type=Path,
        default=SIGNALS_DIR,
        help="Directory containing YYYY-MM-DD.jsonl signal audit files.",
    )
    parser.add_argument(
        "--audit-log",
        type=Path,
        default=EXECUTOR_AUDIT_LOG,
        help="Path to executor audit JSONL log.",
    )
    parser.add_argument(
        "--killswitch-path",
        type=Path,
        default=KILLSWITCH_PATH,
        help="Path to pause flag file.",
    )
    parser.add_argument(
        "--one-shot",
        action="store_true",
        help="Run a single pass and exit instead of looping.",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        help="Logging level.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    logging.basicConfig(
        level=getattr(logging, args.log_level.upper()),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )

    config = ExecutorConfig(
        live=args.live,
        confirm_token=args.confirm_token,
        max_notional_usd=args.max_notional_usd,
        daily_loss_limit_usd=args.daily_loss_limit_usd,
        poll_interval_seconds=args.poll_interval,
        signals_dir=args.signals_dir,
        audit_log=args.audit_log,
        killswitch_path=args.killswitch_path,
    )

    # Additional gate: --live without the env var is a hard block.
    if config.live and os.environ.get(AUTO_EXECUTOR_LIVE_ENV, "").strip() != "1":
        log.error(
            "--live requires %s=1 in the environment. Refusing to start.",
            AUTO_EXECUTOR_LIVE_ENV,
        )
        return 1

    if config.live and not config.confirm_token:
        log.error("--live requires --confirm-token. Refusing to start.")
        return 1

    if args.one_shot:
        run_once(config)
        return 0

    run_loop(config)
    return 0


class ExecutorError(RuntimeError):
    """Domain error raised by the executor."""


if __name__ == "__main__":
    raise SystemExit(main())
