"""Signal-only Hyperliquid public WebSocket feed.

This module subscribes only to public market-data channels and emits Sapphire
events when microstructure thresholds fire. It never imports wallet keys and
does not call Hyperliquid authenticated or exchange endpoints.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import re
import sys
import time
from collections import deque
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

try:
    import yaml
except ImportError:  # pragma: no cover - service requirements include PyYAML.
    yaml = None  # type: ignore[assignment]

try:
    import websockets
except ImportError:  # pragma: no cover - surfaced by runtime status.
    websockets = None  # type: ignore[assignment]

REPO_ROOT = Path(__file__).resolve().parents[4]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

logger = logging.getLogger(__name__)

WS_URL = "wss://api.hyperliquid.xyz/ws"
DEFAULT_SYMBOLS = ("BTC", "ETH", "SOL")
SUBSCRIPTION_TYPES = ("trades", "bbo", "l2Book")
SYMBOL_CONFIG_PATH = Path.home() / ".sapphire" / "hyperliquid_symbols.yaml"
SIGNAL_LOG_PATH = Path.home() / ".sapphire" / "hyperliquid_signals.jsonl"
ROUTINE_NAME = "hyperliquid-public-feed"

MAX_SYMBOLS = 8
MAX_SIGNALS_PER_HOUR = 240
MAX_RECONNECT_ATTEMPTS_PER_HOUR = 12

TRADE_NOTIONAL_THRESHOLD_USD = 250_000.0
IMBALANCE_RATIO_THRESHOLD = 3.0
IMBALANCE_SUSTAIN_SECONDS = 10.0
DEPTH_DROP_RATIO_THRESHOLD = 0.30
DEPTH_WINDOW_SECONDS = 60.0

SIGNAL_SOURCE = "hyperliquid-public-feed"
SYMBOL_PATTERN = re.compile(r"^[A-Za-z0-9@:_-]{1,32}$")


class EventPublisher(Protocol):
    """Minimal event bus protocol used by the feed."""

    def publish(self, event_type: str, data: dict[str, Any], source: str | None = None) -> str:
        """Publish a typed event and return its event id."""


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _iso_from_seconds(seconds: float | None = None) -> str:
    if seconds is None:
        return _utc_now().isoformat()
    return datetime.fromtimestamp(seconds, tz=UTC).isoformat()


def _float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _event_time_seconds(payload: dict[str, Any], now: float | None) -> float:
    if now is not None:
        return now
    raw_ms = payload.get("time")
    if isinstance(raw_ms, int | float) and raw_ms > 10_000_000_000:
        return float(raw_ms) / 1000.0
    return time.time()


def normalize_symbols(raw_symbols: Iterable[Any], *, max_symbols: int = MAX_SYMBOLS) -> list[str]:
    """Normalize user-configured symbols with dedupe, validation, and a hard cap."""
    normalized: list[str] = []
    seen: set[str] = set()
    for raw in raw_symbols:
        symbol = str(raw or "").strip().upper()
        if not symbol or symbol in seen:
            continue
        if not SYMBOL_PATTERN.fullmatch(symbol):
            continue
        seen.add(symbol)
        normalized.append(symbol)
        if len(normalized) >= max_symbols:
            break
    return normalized


@dataclass(frozen=True)
class SymbolConfig:
    """Resolved Hyperliquid symbol config."""

    symbols: tuple[str, ...]
    path: Path = SYMBOL_CONFIG_PATH
    source: str = "default"
    capped: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "symbols": list(self.symbols),
            "path": str(self.path),
            "source": self.source,
            "capped": self.capped,
            "max_symbols": MAX_SYMBOLS,
        }


def load_symbol_config(path: Path | None = None) -> SymbolConfig:
    """Load symbols from ``~/.sapphire/hyperliquid_symbols.yaml`` or defaults.

    Supported YAML shapes:

    ``symbols: [BTC, ETH, SOL]`` or a top-level list.
    """
    config_path = path or SYMBOL_CONFIG_PATH
    if not config_path.exists():
        return SymbolConfig(tuple(DEFAULT_SYMBOLS), path=config_path, source="default")
    if yaml is None:
        return SymbolConfig(tuple(DEFAULT_SYMBOLS), path=config_path, source="default-yaml-missing")

    try:
        loaded = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError):
        return SymbolConfig(tuple(DEFAULT_SYMBOLS), path=config_path, source="default-read-error")

    if isinstance(loaded, dict):
        raw = loaded.get("symbols") or loaded.get("coins") or []
    elif isinstance(loaded, list):
        raw = loaded
    else:
        raw = []

    raw_list = list(raw) if isinstance(raw, (list, tuple)) else []
    symbols = normalize_symbols(raw_list)
    if not symbols:
        return SymbolConfig(tuple(DEFAULT_SYMBOLS), path=config_path, source="default-empty")
    return SymbolConfig(
        tuple(symbols),
        path=config_path,
        source="file",
        capped=len(normalize_symbols(raw_list, max_symbols=10_000)) > MAX_SYMBOLS,
    )


def subscription_payloads(
    symbols: Sequence[str],
    *,
    channels: Sequence[str] = SUBSCRIPTION_TYPES,
) -> list[dict[str, Any]]:
    """Build Hyperliquid subscription messages for every symbol/channel pair."""
    normalized = normalize_symbols(symbols)
    payloads: list[dict[str, Any]] = []
    for symbol in normalized:
        for channel in channels:
            if channel not in SUBSCRIPTION_TYPES:
                continue
            payloads.append(
                {"method": "subscribe", "subscription": {"type": channel, "coin": symbol}}
            )
    return payloads


@dataclass
class HourlyLimiter:
    """Sliding-window limiter for feed safety caps."""

    max_events: int
    window_seconds: float = 3600.0
    timestamps: deque[float] = field(default_factory=deque)

    def prune(self, now: float | None = None) -> None:
        current = time.time() if now is None else now
        cutoff = current - self.window_seconds
        while self.timestamps and self.timestamps[0] <= cutoff:
            self.timestamps.popleft()

    def allow(self, now: float | None = None) -> bool:
        current = time.time() if now is None else now
        self.prune(current)
        if len(self.timestamps) >= self.max_events:
            return False
        self.timestamps.append(current)
        return True

    def snapshot(self, now: float | None = None) -> dict[str, Any]:
        self.prune(now)
        return {
            "used": len(self.timestamps),
            "remaining": max(0, self.max_events - len(self.timestamps)),
            "max": self.max_events,
            "window_seconds": int(self.window_seconds),
        }


@dataclass
class JsonlSignalStore:
    """Append-only local signal ledger used by the plugin's latest/status actions."""

    path: Path = SIGNAL_LOG_PATH

    def append(self, record: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, sort_keys=True, default=str) + "\n")

    def latest(self, limit: int = 10) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        rows: list[dict[str, Any]] = []
        try:
            lines = self.path.read_text(encoding="utf-8").splitlines()
        except OSError:
            return []
        for line in lines[-max(1, limit) :]:
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(payload, dict):
                rows.append(payload)
        return rows[::-1]


def _repo_event_bus() -> EventPublisher | None:
    try:
        from lib.core.event_bus import get_bus

        return get_bus()
    except Exception as exc:  # noqa: BLE001 - event bus fallback should be soft.
        logger.warning("event bus unavailable: %s", exc)
        return None


@dataclass
class SignalPublisher:
    """Publishes capped signals to the Sapphire event bus and local JSONL ledger."""

    bus: EventPublisher | None = None
    store: JsonlSignalStore = field(default_factory=JsonlSignalStore)
    limiter: HourlyLimiter = field(default_factory=lambda: HourlyLimiter(MAX_SIGNALS_PER_HOUR))

    def publish(
        self, topic: str, payload: dict[str, Any], *, now: float | None = None
    ) -> str | None:
        current = time.time() if now is None else now
        if not self.limiter.allow(current):
            logger.warning("hyperliquid signal cap reached; dropping %s", topic)
            return None

        enriched = {
            "schema_version": "hyperliquid.signal.v1",
            "topic": topic,
            "source": SIGNAL_SOURCE,
            "paper_only": True,
            "live_trading_enabled": False,
            "published_at": _iso_from_seconds(current),
            **payload,
        }
        bus = self.bus if self.bus is not None else _repo_event_bus()
        event_id: str | None = None
        if bus is not None:
            event_id = bus.publish(topic, enriched, source=SIGNAL_SOURCE)
        record = {**enriched, "event_id": event_id}
        self.store.append(record)
        return event_id


def _level_notional(level: dict[str, Any] | None) -> float:
    if not isinstance(level, dict):
        return 0.0
    return _float(level.get("px")) * _float(level.get("sz"))


def _top_depth_notional(
    levels: Sequence[Sequence[dict[str, Any]]] | None, depth: int = 10
) -> float:
    if not levels or len(levels) != 2:
        return 0.0
    total = 0.0
    for side in levels:
        for level in list(side)[:depth]:
            if isinstance(level, dict):
                total += _level_notional(level)
    return total


@dataclass
class HyperliquidSignalEngine:
    """Stateful signal rules for public Hyperliquid feed events."""

    trade_threshold_usd: float = TRADE_NOTIONAL_THRESHOLD_USD
    imbalance_ratio_threshold: float = IMBALANCE_RATIO_THRESHOLD
    imbalance_sustain_seconds: float = IMBALANCE_SUSTAIN_SECONDS
    depth_drop_ratio_threshold: float = DEPTH_DROP_RATIO_THRESHOLD
    depth_window_seconds: float = DEPTH_WINDOW_SECONDS
    _imbalance_since: dict[str, tuple[str, float, float]] = field(default_factory=dict)
    _last_imbalance_emit: dict[str, float] = field(default_factory=dict)
    _depth_history: dict[str, deque[tuple[float, float]]] = field(default_factory=dict)
    _last_thin_emit: dict[str, float] = field(default_factory=dict)

    def process_message(
        self, message: dict[str, Any], *, now: float | None = None
    ) -> list[dict[str, Any]]:
        channel = message.get("channel")
        data = message.get("data")
        if channel == "subscriptionResponse":
            return []
        if channel == "trades":
            trades = data if isinstance(data, list) else [data]
            return [
                signal
                for trade in trades
                if isinstance(trade, dict)
                for signal in self.process_trade(trade, now=now)
            ]
        if channel == "bbo" and isinstance(data, dict):
            return self.process_bbo(data, now=now)
        if channel == "l2Book" and isinstance(data, dict):
            return self.process_l2_book(data, now=now)
        return []

    def process_trade(
        self, trade: dict[str, Any], *, now: float | None = None
    ) -> list[dict[str, Any]]:
        symbol = str(trade.get("coin") or "").upper()
        price = _float(trade.get("px"))
        size = _float(trade.get("sz"))
        notional = price * size
        if not symbol or notional <= self.trade_threshold_usd:
            return []
        observed = _event_time_seconds(trade, now)
        return [
            {
                "topic": "hyperliquid.trade",
                "signal_type": "large_trade",
                "symbol": symbol,
                "side": trade.get("side"),
                "price": price,
                "size": size,
                "notional_usd": round(notional, 2),
                "threshold_usd": self.trade_threshold_usd,
                "exchange_time_ms": trade.get("time"),
                "trade_id": trade.get("tid"),
                "observed_at": _iso_from_seconds(observed),
            }
        ]

    def process_bbo(self, bbo: dict[str, Any], *, now: float | None = None) -> list[dict[str, Any]]:
        symbol = str(bbo.get("coin") or "").upper()
        levels = bbo.get("bbo")
        if not symbol or not isinstance(levels, (list, tuple)) or len(levels) != 2:
            return []

        observed = _event_time_seconds(bbo, now)
        bid_notional = _level_notional(levels[0])
        ask_notional = _level_notional(levels[1])
        smaller = min(bid_notional, ask_notional)
        larger = max(bid_notional, ask_notional)
        if smaller <= 0:
            self._imbalance_since.pop(symbol, None)
            return []

        ratio = larger / smaller
        side = "bid" if bid_notional >= ask_notional else "ask"
        if ratio <= self.imbalance_ratio_threshold:
            self._imbalance_since.pop(symbol, None)
            return []

        existing = self._imbalance_since.get(symbol)
        if existing is None or existing[0] != side:
            self._imbalance_since[symbol] = (side, observed, ratio)
            return []

        _, started_at, _ = existing
        sustained = observed - started_at
        last_emit = self._last_imbalance_emit.get(symbol, 0.0)
        if sustained < self.imbalance_sustain_seconds:
            return []
        if observed - last_emit < self.imbalance_sustain_seconds:
            return []

        self._last_imbalance_emit[symbol] = observed
        return [
            {
                "topic": "hyperliquid.imbalance",
                "signal_type": "top_of_book_imbalance",
                "symbol": symbol,
                "dominant_side": side,
                "ratio": round(ratio, 4),
                "threshold_ratio": self.imbalance_ratio_threshold,
                "sustained_seconds": round(sustained, 3),
                "bid_notional_usd": round(bid_notional, 2),
                "ask_notional_usd": round(ask_notional, 2),
                "exchange_time_ms": bbo.get("time"),
                "observed_at": _iso_from_seconds(observed),
            }
        ]

    def process_l2_book(
        self, book: dict[str, Any], *, now: float | None = None
    ) -> list[dict[str, Any]]:
        symbol = str(book.get("coin") or "").upper()
        levels = book.get("levels")
        if not symbol or not isinstance(levels, (list, tuple)):
            return []

        observed = _event_time_seconds(book, now)
        current_depth = _top_depth_notional(levels)
        if current_depth <= 0:
            return []

        history = self._depth_history.setdefault(symbol, deque())
        cutoff = observed - self.depth_window_seconds
        while history and history[0][0] < cutoff:
            history.popleft()

        signal: dict[str, Any] | None = None
        if history:
            baseline_at, baseline_depth = max(history, key=lambda item: item[1])
            drop_ratio = (
                (baseline_depth - current_depth) / baseline_depth if baseline_depth else 0.0
            )
            last_emit = self._last_thin_emit.get(symbol, 0.0)
            if (
                drop_ratio > self.depth_drop_ratio_threshold
                and observed - baseline_at <= self.depth_window_seconds
                and observed - last_emit >= self.depth_window_seconds
            ):
                self._last_thin_emit[symbol] = observed
                signal = {
                    "topic": "hyperliquid.book.thin",
                    "signal_type": "top_10_depth_drop",
                    "symbol": symbol,
                    "current_depth_usd": round(current_depth, 2),
                    "baseline_depth_usd": round(baseline_depth, 2),
                    "drop_ratio": round(drop_ratio, 4),
                    "threshold_drop_ratio": self.depth_drop_ratio_threshold,
                    "window_seconds": int(self.depth_window_seconds),
                    "baseline_observed_at": _iso_from_seconds(baseline_at),
                    "exchange_time_ms": book.get("time"),
                    "observed_at": _iso_from_seconds(observed),
                }
        history.append((observed, current_depth))
        return [signal] if signal else []


def decode_ws_message(raw: str | bytes) -> dict[str, Any] | None:
    """Decode a WebSocket frame into a dictionary, ignoring malformed frames."""
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8", errors="replace")
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


def _local_routine_pause_active(routine_name: str = ROUTINE_NAME) -> bool:
    pause_dir = Path(
        os.environ.get(
            "SAPPHIRE_ROUTINE_PAUSE_DIR", str(Path.home() / ".sapphire" / "routine_pause")
        )
    )
    return any(
        path.exists()
        for path in (
            pause_dir / routine_name,
            pause_dir / f"{routine_name}.pause",
            pause_dir / "hyperliquid",
            pause_dir / "all",
        )
    )


def routine_pause_status(routine_name: str = ROUTINE_NAME) -> dict[str, Any]:
    """Check shared routine pause helper when present, otherwise use local files."""
    if os.environ.get("SAPPHIRE_ROUTINE_PAUSE_DIR"):
        paused = _local_routine_pause_active(routine_name)
        return {"paused": paused, "source": "local-fallback"}

    try:
        from lib.core import routine_pause
    except Exception:
        paused = _local_routine_pause_active(routine_name)
        return {"paused": paused, "source": "local-fallback"}

    for attr in ("is_routine_paused", "routine_is_paused", "is_paused"):
        checker = getattr(routine_pause, attr, None)
        if checker is None:
            continue
        try:
            return {
                "paused": bool(checker(routine_name)),
                "source": f"lib.core.routine_pause.{attr}",
            }
        except TypeError:
            try:
                return {"paused": bool(checker()), "source": f"lib.core.routine_pause.{attr}"}
            except Exception:
                break
        except Exception:
            break
    return {"paused": _local_routine_pause_active(routine_name), "source": "local-fallback"}


def live_enabled(env: dict[str, str] | None = None) -> bool:
    values = os.environ if env is None else env
    return values.get("SAPPHIRE_HYPERLIQUID_LIVE", "").strip() == "1"


@dataclass
class HyperliquidPublicFeedSubscriber:
    """Async WebSocket subscriber for Hyperliquid public market data."""

    symbols: Sequence[str]
    ws_url: str = WS_URL
    engine: HyperliquidSignalEngine = field(default_factory=HyperliquidSignalEngine)
    publisher: SignalPublisher = field(default_factory=SignalPublisher)
    reconnect_limiter: HourlyLimiter = field(
        default_factory=lambda: HourlyLimiter(MAX_RECONNECT_ATTEMPTS_PER_HOUR)
    )
    reconnect_backoff_seconds: float = 5.0
    sleep: Callable[[float], Any] = asyncio.sleep
    _stop_requested: bool = False

    def __post_init__(self) -> None:
        self.symbols = tuple(normalize_symbols(self.symbols))
        if len(self.symbols) > MAX_SYMBOLS:
            self.symbols = tuple(self.symbols[:MAX_SYMBOLS])

    def stop(self) -> None:
        self._stop_requested = True

    def subscribe_test(self) -> dict[str, Any]:
        payloads = subscription_payloads(self.symbols)
        return {
            "status": "dry-run",
            "ws_url": self.ws_url,
            "symbols": list(self.symbols),
            "channels": list(SUBSCRIPTION_TYPES),
            "subscription_count": len(payloads),
            "subscriptions": payloads,
            "live_env": live_enabled(),
            "auth_required": False,
            "wallet_keys_required": False,
        }

    async def run_forever(
        self,
        *,
        connect: Any | None = None,
        stop_after_messages: int | None = None,
    ) -> dict[str, Any]:
        if not live_enabled():
            dry_run = self.subscribe_test()
            return {
                "status": "blocked",
                "reason": "SAPPHIRE_HYPERLIQUID_LIVE must be 1",
                "dry_run": True,
                "subscribe_test": dry_run,
            }
        if websockets is None and connect is None:
            return {"status": "blocked", "reason": "websockets package is not installed"}

        connector = connect or websockets.connect
        messages_seen = 0
        last_error: str | None = None
        while not self._stop_requested:
            pause = routine_pause_status()
            if pause["paused"]:
                await self.sleep(min(self.reconnect_backoff_seconds, 30.0))
                continue

            now = time.time()
            if not self.reconnect_limiter.allow(now):
                return {
                    "status": "blocked",
                    "reason": "reconnect cap reached",
                    "reconnects": self.reconnect_limiter.snapshot(now),
                    "last_error": last_error,
                }
            try:
                seen = await self._connect_once(
                    connector,
                    stop_after_messages=stop_after_messages,
                )
                messages_seen += seen
                if stop_after_messages is not None and messages_seen >= stop_after_messages:
                    return {"status": "stopped", "messages_seen": messages_seen}
            except Exception as exc:  # noqa: BLE001 - daemon keeps retrying under cap.
                last_error = f"{type(exc).__name__}: {exc}"
                logger.warning("hyperliquid feed reconnecting after %s", last_error)
                await self.sleep(self.reconnect_backoff_seconds)
        return {"status": "stopped", "messages_seen": messages_seen, "last_error": last_error}

    async def _connect_once(
        self,
        connector: Any,
        *,
        stop_after_messages: int | None = None,
    ) -> int:
        sent = subscription_payloads(self.symbols)
        messages_seen = 0
        async with connector(
            self.ws_url,
            ping_interval=20,
            ping_timeout=20,
            close_timeout=5,
        ) as ws:
            for payload in sent:
                await ws.send(json.dumps(payload, separators=(",", ":")))
            async for raw in ws:
                messages_seen += 1
                decoded = decode_ws_message(raw)
                if decoded is None:
                    continue
                for signal in self.engine.process_message(decoded):
                    topic = signal.pop("topic")
                    self.publisher.publish(topic, signal)
                if stop_after_messages is not None and messages_seen >= stop_after_messages:
                    self.stop()
                    break
        return messages_seen


def status_payload(
    *,
    symbol_config_path: Path | None = None,
    signal_log_path: Path | None = None,
) -> dict[str, Any]:
    config = load_symbol_config(symbol_config_path)
    store = JsonlSignalStore(signal_log_path or SIGNAL_LOG_PATH)
    latest = store.latest(limit=1)
    pause = routine_pause_status()
    return {
        "status": "configured",
        "mode": "signal-only",
        "live_env": live_enabled(),
        "ws_url": WS_URL,
        "symbol_config": config.as_dict(),
        "caps": {
            "max_symbols": MAX_SYMBOLS,
            "max_signals_per_hour": MAX_SIGNALS_PER_HOUR,
            "max_reconnect_attempts_per_hour": MAX_RECONNECT_ATTEMPTS_PER_HOUR,
        },
        "rules": {
            "large_trade_notional_usd": TRADE_NOTIONAL_THRESHOLD_USD,
            "top_of_book_imbalance_ratio": IMBALANCE_RATIO_THRESHOLD,
            "top_of_book_imbalance_sustain_seconds": IMBALANCE_SUSTAIN_SECONDS,
            "top_10_depth_drop_ratio": DEPTH_DROP_RATIO_THRESHOLD,
            "top_10_depth_window_seconds": DEPTH_WINDOW_SECONDS,
        },
        "event_topics": ["hyperliquid.trade", "hyperliquid.imbalance", "hyperliquid.book.thin"],
        "routine_pause": pause,
        "signal_log_path": str(store.path),
        "latest_signal": latest[0] if latest else None,
        "wallet_keys_required": False,
        "authenticated_endpoints_enabled": False,
        "live_trading_enabled": False,
    }


async def run_daemon() -> dict[str, Any]:
    config = load_symbol_config()
    subscriber = HyperliquidPublicFeedSubscriber(config.symbols)
    return await subscriber.run_forever()


def handle_action(action: str, *, limit: int = 10) -> dict[str, Any]:
    normalized = (action or "status").strip().lower().replace("_", "-")
    if normalized == "status":
        return status_payload()
    if normalized == "latest":
        return {"signals": JsonlSignalStore().latest(limit=limit), "limit": limit}
    if normalized == "subscribe-test":
        config = load_symbol_config()
        return HyperliquidPublicFeedSubscriber(config.symbols).subscribe_test()
    if normalized == "daemon":
        return asyncio.run(run_daemon())
    return {
        "error": f"unknown action '{action}'",
        "valid_actions": ["status", "latest", "subscribe-test", "daemon"],
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "action",
        nargs="?",
        default="status",
        choices=["status", "latest", "subscribe-test", "daemon"],
    )
    parser.add_argument("--limit", type=int, default=10)
    args = parser.parse_args(argv)
    payload = handle_action(args.action, limit=args.limit)
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 1 if payload.get("error") else 0


if __name__ == "__main__":
    raise SystemExit(main())
