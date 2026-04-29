"""JSONL tail-poller for Sapphire trading signals.

The Mac signal logger (services/alpha/src/signal_logger.py) appends every
TradingView webhook signal to ``data/trading_signals.jsonl``. This module
follows that file from a persisted offset so the bot can resume cleanly
across restarts, normalizes each line into the contract the executor
expects, and skips entries the bot can't act on (unsupported symbol,
unknown action, replays of seen signal_ids).

Design choices:

* JSONL polling, not Redis pubsub. The local pipeline already writes the
  jsonl file as the canonical record. We avoid a new dep on
  ``google-cloud-pubsub`` (the only ``services/aster`` consumer pattern in
  tree imports a ``pubsub`` shim that doesn't exist on disk anymore).
* Offset persisted to ``data/hyperliquid_signal_offset.json`` so a restart
  picks up where it left off rather than re-replaying the full file.
* ``signal_id`` deduplication on a sliding window so a recovered offset
  that revisits already-handled signals can't double-fire orders.
* Translation is one place (:func:`translate_signal`) so the executor's
  signal contract stays decoupled from the upstream webhook shape.
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections import deque
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

DEFAULT_SIGNAL_PATH = Path("data/trading_signals.jsonl")
DEFAULT_OFFSET_PATH = Path("data/hyperliquid_signal_offset.json")
DEFAULT_DEDUPE_WINDOW = 1024
DEFAULT_POLL_INTERVAL_SECONDS = 1.0

# Hyperliquid supports 150+ assets; this is the conservative default for
# autonomous routing. Operators can widen via SignalSubscriber(symbols=...).
DEFAULT_SUPPORTED_SYMBOLS = frozenset({"BTC", "ETH", "SOL", "HYPE", "ARB", "AVAX"})

_BUY_ALIASES = frozenset({"buy", "long", "open_long"})
_SELL_ALIASES = frozenset({"sell", "short", "open_short"})
_CLOSE_ALIASES = frozenset({"close", "exit", "flatten"})


def translate_signal(
    raw: dict[str, Any], *, default_size_usd: float
) -> dict[str, Any] | None:
    """Map a webhook signal entry to the executor's expected shape.

    Returns ``None`` if the signal is unroutable (missing/unknown action or
    symbol). The executor still applies cap and killswitch logic on top —
    this filter only drops obviously malformed entries.
    """
    symbol = str(raw.get("symbol") or "").strip().upper()
    if not symbol:
        return None

    action_raw = str(raw.get("action") or raw.get("side") or "").strip().lower()
    if action_raw in _BUY_ALIASES:
        action = "buy"
    elif action_raw in _SELL_ALIASES:
        action = "sell"
    elif action_raw in _CLOSE_ALIASES:
        action = "close"
    else:
        return None

    size_usd = raw.get("size_usd")
    if not isinstance(size_usd, int | float) or size_usd <= 0:
        size_usd = default_size_usd

    return {
        "symbol": symbol,
        "action": action,
        "size_usd": float(size_usd),
        "confidence": _safe_float(raw.get("confidence")) or 0.0,
        "leverage": _safe_float(raw.get("leverage")) or 1.0,
        "signal_id": raw.get("signal_id") or raw.get("timestamp") or "",
        "source_strategy": raw.get("strategy") or "unknown",
        "source_timestamp": raw.get("timestamp"),
    }


class SignalSubscriber:
    """Tail ``data/trading_signals.jsonl`` and feed entries to a handler.

    Args:
        handler: ``async`` callable invoked once per routable signal.
        signal_path: jsonl source. Defaults to the signal-logger output.
        offset_path: where to persist the byte offset between runs.
        symbols: allowlist of symbols to forward. ``None`` means accept all.
        default_size_usd: fallback notional when the upstream signal omits
            ``size_usd``. The executor still applies its policy cap.
        poll_interval: seconds between file-size checks when idle.
        dedupe_window: how many recent signal_ids to remember; entries
            already seen within the window are dropped.
    """

    def __init__(
        self,
        handler: Callable[[dict[str, Any]], Awaitable[Any]],
        *,
        signal_path: Path = DEFAULT_SIGNAL_PATH,
        offset_path: Path = DEFAULT_OFFSET_PATH,
        symbols: frozenset[str] | None = DEFAULT_SUPPORTED_SYMBOLS,
        default_size_usd: float = 5.0,
        poll_interval: float = DEFAULT_POLL_INTERVAL_SECONDS,
        dedupe_window: int = DEFAULT_DEDUPE_WINDOW,
    ) -> None:
        self._handler = handler
        self._signal_path = signal_path
        self._offset_path = offset_path
        self._symbols = symbols
        self._default_size_usd = default_size_usd
        self._poll_interval = poll_interval
        self._offset = self._load_offset()
        self._seen_ids: deque[str] = deque(maxlen=dedupe_window)
        self._running = False

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def run(self) -> None:
        """Poll the signal file until :meth:`stop` is called."""
        self._running = True
        log.info(
            "signal subscriber starting path=%s offset=%d symbols=%s",
            self._signal_path,
            self._offset,
            "any" if self._symbols is None else ",".join(sorted(self._symbols)),
        )
        while self._running:
            try:
                await self.drain_once()
            except Exception:
                log.exception("signal subscriber drain failed; will retry")
            await asyncio.sleep(self._poll_interval)

    def stop(self) -> None:
        self._running = False

    # ------------------------------------------------------------------
    # Drain one batch (testable in isolation)
    # ------------------------------------------------------------------

    async def drain_once(self) -> int:
        """Read all new lines since the last offset. Returns processed count."""
        if not self._signal_path.exists():
            return 0
        size = self._signal_path.stat().st_size
        if size < self._offset:
            log.warning(
                "signal file shrank — resetting offset (was=%d size=%d)",
                self._offset,
                size,
            )
            self._offset = 0
        if size == self._offset:
            return 0

        processed = 0
        with self._signal_path.open("rb") as fh:
            fh.seek(self._offset)
            data = fh.read()
            new_offset = self._offset + len(data)

        for line in data.decode("utf-8", errors="replace").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                raw = json.loads(line)
            except json.JSONDecodeError:
                log.warning("skipping malformed signal line: %r", line[:120])
                continue
            if not isinstance(raw, dict):
                continue
            translated = translate_signal(raw, default_size_usd=self._default_size_usd)
            if translated is None:
                continue
            if self._symbols is not None and translated["symbol"] not in self._symbols:
                continue
            sid = translated.get("signal_id") or ""
            if sid and sid in self._seen_ids:
                continue
            if sid:
                self._seen_ids.append(sid)
            try:
                await self._handler(translated)
            except Exception:
                log.exception("handler failed for signal=%s", translated)
            processed += 1

        self._offset = new_offset
        self._persist_offset()
        return processed

    # ------------------------------------------------------------------
    # Offset persistence
    # ------------------------------------------------------------------

    def _load_offset(self) -> int:
        if not self._offset_path.exists():
            return 0
        try:
            body = json.loads(self._offset_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return 0
        offset = body.get("offset") if isinstance(body, dict) else None
        return int(offset) if isinstance(offset, int) and offset >= 0 else 0

    def _persist_offset(self) -> None:
        self._offset_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            self._offset_path.write_text(
                json.dumps(
                    {
                        "offset": self._offset,
                        "signal_path": str(self._signal_path),
                    },
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
        except OSError:
            log.exception("failed to persist signal offset")


def _safe_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


__all__ = [
    "DEFAULT_DEDUPE_WINDOW",
    "DEFAULT_OFFSET_PATH",
    "DEFAULT_POLL_INTERVAL_SECONDS",
    "DEFAULT_SIGNAL_PATH",
    "DEFAULT_SUPPORTED_SYMBOLS",
    "SignalSubscriber",
    "translate_signal",
]
