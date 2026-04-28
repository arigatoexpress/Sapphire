"""Unified Event Bus — the central nervous system of Sapphire OS.

Every module publishes typed events. Any module can subscribe.
Events persist in Redis Streams for replay and audit.

Design:
- Backed by Redis Streams (one stream per event type — `evt:<type>`)
- Glob pattern subscriptions via a background reader thread per subscriber
- JSONL fallback file (`data/events/bus.jsonl`) when Redis is unavailable,
  so local dev and tests still work without a running server
- WorldState is aggregated from recent events across the canonical streams

Event ID format: Redis Stream entry IDs (`<ms>-<seq>`) — monotonic across
a single stream and lexicographically comparable across streams.

Usage:
    from event_bus import get_bus, Event

    bus = get_bus()
    bus.publish("signal.generated", {"symbol": "BTC", "confidence": 0.82})

    def on_signal(ev: Event) -> None:
        print(ev.type, ev.data)

    bus.subscribe(["signal.*"], on_signal)

    ws = bus.get_world_state()
    print(ws.market_regime, ws.open_positions)
"""

from __future__ import annotations

import contextlib
import fnmatch
import json
import logging
import os
import threading
import time
import uuid
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

try:
    import redis

    _REDIS_AVAILABLE = True
except ImportError:
    redis = None  # type: ignore[assignment]
    _REDIS_AVAILABLE = False


# ---------------------------------------------------------------------------
# Canonical event types — keep in sync with docs/nist-alignment.md
# ---------------------------------------------------------------------------

EVENT_TYPES: tuple[str, ...] = (
    "regime.shifted",
    "regime.snapshot",
    "funding.extreme",
    "signal.generated",
    "signal.closed",
    "prediction.generated",
    "threat.detected",
    "lead.scored",
    "service.health",
    "correlation.broken",
    "sentiment.update",
)

STREAM_PREFIX = "evt:"
STREAM_MAXLEN = 10_000  # approx-trim per stream


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------


@dataclass
class Event:
    """A single event on the bus."""

    id: str  # redis stream id OR uuid when using fallback
    type: str  # e.g. "signal.generated"
    ts: str  # ISO-8601 UTC timestamp
    data: dict[str, Any]
    source: str = "unknown"

    def to_wire(self) -> dict[str, str]:
        """Serialize for Redis XADD (all values must be strings)."""
        return {
            "type": self.type,
            "ts": self.ts,
            "source": self.source,
            "data": json.dumps(self.data, default=str),
        }

    @classmethod
    def from_wire(cls, stream_id: str, fields: dict[str, str]) -> Event:
        raw = fields.get("data", "{}")
        try:
            data = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            data = {"_raw": raw}
        return cls(
            id=stream_id,
            type=fields.get("type", "unknown"),
            ts=fields.get("ts", datetime.now(UTC).isoformat()),
            source=fields.get("source", "unknown"),
            data=data,
        )


@dataclass
class WorldState:
    """Aggregated state across recent events."""

    market_regime: str = "UNKNOWN"  # RISK_ON / RISK_OFF / TRANSITION
    regime_confidence: float = 0.0
    regime_since: datetime | None = None
    fear_greed: int = -1  # 0-100, -1 = unknown
    funding_bias: str = "neutral"  # long / short / neutral
    correlation_state: str = "normal"  # normal / decorrelated
    portfolio_pnl: float = 0.0
    open_positions: int = 0
    threat_level: str = "low"  # low / elevated / high / critical
    infrastructure_health: str = "nominal"  # nominal / degraded / critical
    active_signals: int = 0
    last_update: datetime = field(default_factory=lambda: datetime.now(UTC))

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["regime_since"] = self.regime_since.isoformat() if self.regime_since else None
        d["last_update"] = self.last_update.isoformat()
        return d


# ---------------------------------------------------------------------------
# EventBus
# ---------------------------------------------------------------------------


class EventBus:
    """Central nervous system backed by Redis Streams with JSONL fallback."""

    _FALLBACK_PATH = Path.home() / "Code" / "Sapphire" / "data" / "events" / "bus.jsonl"

    def __init__(
        self,
        redis_url: str | None = None,
        source: str = "sapphire",
        fallback_path: Path | None = None,
    ) -> None:
        self.source = source
        self._redis_url = redis_url or os.environ.get("REDIS_URL", "redis://127.0.0.1:6379/0")
        self._fallback_path = fallback_path or self._FALLBACK_PATH
        self._fallback_path.parent.mkdir(parents=True, exist_ok=True)

        self._client: Any = None
        self._redis_ok = False
        self._connect()

        self._subscribers: list[_Subscription] = []
        self._subs_lock = threading.Lock()

    # ── Connection ────────────────────────────────────────────────────────────

    def _connect(self) -> None:
        if not _REDIS_AVAILABLE:
            log.warning("redis-py not installed — event bus running in fallback mode")
            return
        try:
            self._client = redis.Redis.from_url(
                self._redis_url,
                decode_responses=True,
                socket_connect_timeout=2,
                socket_timeout=2,
            )
            self._client.ping()
            self._redis_ok = True
        except Exception as e:
            log.warning("redis unavailable (%s) — event bus running in fallback mode", e)
            self._client = None
            self._redis_ok = False

    def healthy(self) -> bool:
        return self._redis_ok

    # ── Publish ───────────────────────────────────────────────────────────────

    def publish(self, event_type: str, data: dict, source: str | None = None) -> str:
        """Publish a typed event. Returns the event ID.

        Never raises — failures degrade to the JSONL fallback so the caller
        keeps running.
        """
        ts = datetime.now(UTC).isoformat()
        ev_source = source or self.source

        if self._redis_ok:
            try:
                stream_key = STREAM_PREFIX + event_type
                entry = {
                    "type": event_type,
                    "ts": ts,
                    "source": ev_source,
                    "data": json.dumps(data, default=str),
                }
                event_id = self._client.xadd(
                    stream_key, entry, maxlen=STREAM_MAXLEN, approximate=True
                )
                return event_id
            except Exception as e:
                log.warning("event publish to redis failed (%s) — using fallback", e)
                self._redis_ok = False

        # Fallback — append-only JSONL
        event_id = f"local-{int(time.time()*1000)}-{uuid.uuid4().hex[:8]}"
        record = {
            "id": event_id,
            "type": event_type,
            "ts": ts,
            "source": ev_source,
            "data": data,
        }
        try:
            with self._fallback_path.open("a") as f:
                f.write(json.dumps(record, default=str) + "\n")
        except Exception as e:
            log.error("fallback event write failed: %s", e)
        return event_id

    # ── Subscribe ─────────────────────────────────────────────────────────────

    def subscribe(
        self,
        patterns: list[str],
        callback: Callable[[Event], None],
        group: str | None = None,
        start_id: str = "$",
    ) -> _Subscription:
        """Subscribe to events matching any of the glob patterns.

        - patterns: e.g. ["signal.*", "regime.shifted"]
        - group: optional consumer group name for load-balanced reads
        - start_id: where to start reading ("$" = only new, "0" = from beginning)
        """
        sub = _Subscription(self, patterns, callback, group=group, start_id=start_id)
        with self._subs_lock:
            self._subscribers.append(sub)
        sub.start()
        return sub

    def unsubscribe_all(self) -> None:
        with self._subs_lock:
            for s in self._subscribers:
                s.stop()
            self._subscribers = []

    # ── Replay ────────────────────────────────────────────────────────────────

    def replay(
        self,
        event_type: str,
        since: datetime | None = None,
        limit: int = 1000,
    ) -> list[Event]:
        """Replay events of a given type since a given time."""
        since_ms = int(since.timestamp() * 1000) if since else 0
        out: list[Event] = []

        if self._redis_ok:
            try:
                stream_key = STREAM_PREFIX + event_type
                start = f"{since_ms}-0" if since_ms else "-"
                entries = self._client.xrange(stream_key, min=start, max="+", count=limit)
                for stream_id, fields in entries:
                    out.append(Event.from_wire(stream_id, fields))
                return out
            except Exception as e:
                log.warning("redis replay failed (%s) — using fallback", e)

        # Fallback — scan JSONL
        if self._fallback_path.exists():
            try:
                with self._fallback_path.open() as f:
                    for line in f:
                        try:
                            rec = json.loads(line)
                        except json.JSONDecodeError:
                            continue
                        if rec.get("type") != event_type:
                            continue
                        if since and rec.get("ts", "") < since.isoformat():
                            continue
                        out.append(
                            Event(
                                id=rec["id"],
                                type=rec["type"],
                                ts=rec["ts"],
                                source=rec.get("source", "unknown"),
                                data=rec.get("data", {}),
                            )
                        )
                        if len(out) >= limit:
                            break
            except Exception as e:
                log.error("fallback replay failed: %s", e)
        return out

    # ── World State ───────────────────────────────────────────────────────────

    def get_world_state(self, lookback: timedelta = timedelta(hours=24)) -> WorldState:
        """Aggregate the latest event per canonical type into a WorldState.

        Missing event types leave the WorldState field at its default.
        """
        ws = WorldState()
        since = datetime.now(UTC) - lookback

        latest = self._latest_per_type(since)

        if regime := latest.get("regime.snapshot") or latest.get("regime.shifted"):
            ws.market_regime = regime.data.get("regime", ws.market_regime)
            ws.regime_confidence = float(regime.data.get("confidence", 0.0))
            since_str = regime.data.get("since") or regime.ts
            try:
                ws.regime_since = datetime.fromisoformat(since_str.replace("Z", "+00:00"))
            except Exception:
                ws.regime_since = None

        if funding := latest.get("funding.extreme"):
            ws.funding_bias = funding.data.get("bias", ws.funding_bias)

        if sentiment := latest.get("sentiment.update"):
            fg = sentiment.data.get("fear_greed")
            if isinstance(fg, (int, float)):
                ws.fear_greed = int(fg)

        if corr := latest.get("correlation.broken"):
            ws.correlation_state = corr.data.get("state", "decorrelated")

        if health := latest.get("service.health"):
            ws.infrastructure_health = health.data.get("status", ws.infrastructure_health)

        if threat := latest.get("threat.detected"):
            ws.threat_level = threat.data.get("level", ws.threat_level)

        # Portfolio/position counts are derived from signal.generated - signal.closed
        # using the recent window. Each pair of generated/closed on a symbol nets 0.
        signals = self.replay("signal.generated", since=since, limit=2000)
        closed = self.replay("signal.closed", since=since, limit=2000)
        ws.active_signals = len(signals)
        ws.open_positions = max(0, len(signals) - len(closed))
        ws.portfolio_pnl = sum(float(e.data.get("pnl_usd", 0.0) or 0.0) for e in closed)
        ws.last_update = datetime.now(UTC)
        return ws

    def _latest_per_type(self, since: datetime) -> dict[str, Event]:
        """Return the most recent event for each canonical type in the window."""
        out: dict[str, Event] = {}
        for et in EVENT_TYPES:
            events = self.replay(et, since=since, limit=50)
            if events:
                out[et] = events[-1]
        return out


# ---------------------------------------------------------------------------
# _Subscription — background stream reader
# ---------------------------------------------------------------------------


class _Subscription:
    """Background thread that reads matching streams and fans out to a callback."""

    def __init__(
        self,
        bus: EventBus,
        patterns: list[str],
        callback: Callable[[Event], None],
        group: str | None = None,
        start_id: str = "$",
    ) -> None:
        self._bus = bus
        self._patterns = patterns
        self._callback = callback
        self._group = group
        self._start_id = start_id
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._consumer = f"c-{uuid.uuid4().hex[:8]}"

    def _matches(self, event_type: str) -> bool:
        return any(fnmatch.fnmatchcase(event_type, p) for p in self._patterns)

    def _matching_streams(self) -> list[str]:
        # Concrete patterns without wildcards resolve directly; wildcard patterns
        # expand across the canonical event type set.
        out: list[str] = []
        for p in self._patterns:
            if any(ch in p for ch in "*?["):
                for et in EVENT_TYPES:
                    if fnmatch.fnmatchcase(et, p):
                        out.append(STREAM_PREFIX + et)
            else:
                out.append(STREAM_PREFIX + p)
        # de-dup, preserve order
        seen: set[str] = set()
        unique: list[str] = []
        for s in out:
            if s not in seen:
                seen.add(s)
                unique.append(s)
        return unique

    def start(self) -> None:
        self._thread = threading.Thread(
            target=self._run, name=f"evtbus-{self._consumer}", daemon=True
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def _run(self) -> None:
        streams = self._matching_streams()
        if not streams:
            log.warning("subscription %s matched no streams", self._patterns)
            return
        cursor = {s: self._start_id for s in streams}

        if self._bus._redis_ok and self._group:
            for s in streams:
                with contextlib.suppress(Exception):
                    self._bus._client.xgroup_create(s, self._group, id="$", mkstream=True)

        while not self._stop.is_set():
            if not self._bus._redis_ok:
                # Fallback: tail JSONL — cheap & cheerful
                self._tail_fallback()
                time.sleep(1.0)
                continue
            try:
                if self._group:
                    res = self._bus._client.xreadgroup(
                        self._group,
                        self._consumer,
                        {s: ">" for s in streams},
                        count=50,
                        block=1000,
                    )
                else:
                    res = self._bus._client.xread(cursor, count=50, block=1000)
                if not res:
                    continue
                for stream_key, entries in res:
                    for stream_id, fields in entries:
                        ev = Event.from_wire(stream_id, fields)
                        if self._matches(ev.type):
                            try:
                                self._callback(ev)
                            except Exception as e:
                                log.error("subscriber callback error: %s", e)
                        cursor[stream_key] = stream_id
            except Exception as e:
                log.warning("subscription read error (%s) — retrying", e)
                time.sleep(1.0)

    def _tail_fallback(self) -> None:
        # Simple tail: read any new lines since last offset.
        path = self._bus._fallback_path
        if not path.exists():
            return
        try:
            offset_attr = f"_fallback_off_{self._consumer}"
            last_off = getattr(self, offset_attr, 0)
            with path.open() as f:
                f.seek(last_off)
                for line in f:
                    try:
                        rec = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if self._matches(rec.get("type", "")):
                        ev = Event(
                            id=rec["id"],
                            type=rec["type"],
                            ts=rec["ts"],
                            source=rec.get("source", "unknown"),
                            data=rec.get("data", {}),
                        )
                        try:
                            self._callback(ev)
                        except Exception as e:
                            log.error("subscriber callback error: %s", e)
                setattr(self, offset_attr, f.tell())
        except Exception as e:
            log.error("fallback tail error: %s", e)


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_BUS: EventBus | None = None
_BUS_LOCK = threading.Lock()


def get_bus(source: str = "sapphire") -> EventBus:
    """Return the process-wide EventBus singleton."""
    global _BUS
    with _BUS_LOCK:
        if _BUS is None:
            _BUS = EventBus(source=source)
        return _BUS


def publish(event_type: str, data: dict, source: str | None = None) -> str:
    """Convenience top-level publish using the default singleton."""
    return get_bus().publish(event_type, data, source=source)


__all__ = [
    "Event",
    "EventBus",
    "WorldState",
    "EVENT_TYPES",
    "get_bus",
    "publish",
]
