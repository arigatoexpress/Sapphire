"""MegaETH WebSocket subscriber.

Subscribes to ``newHeads`` (always) and an optional set of ``logs`` filters
(driven by config). Each event is enriched with ``timestamp_iso``, ``chain_id``,
and a synthesized ``symbol`` so it slots into the existing signal-logger
schema, then handed to the forwarder.

Reconnect uses exponential backoff capped at ``reconnect_max_sec``. The WS
loop **never** waits on the forwarder — only on the queue's drop-oldest path.
"""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Callable, Protocol

from .config import IngestConfig, LogFilter, killswitch_active
from .forwarder import EventForwarder

try:
    import websockets
except ImportError:  # pragma: no cover - service requirements include websockets.
    websockets = None  # type: ignore[assignment]

logger = logging.getLogger(__name__)


class WsConnector(Protocol):
    """Protocol matching ``websockets.connect`` for testability."""

    def __call__(self, url: str, **kwargs: Any) -> Any:
        ...


@dataclass
class WsStats:
    ws_connected: bool = False
    connect_attempts: int = 0
    connect_failures: int = 0
    last_connect_at: datetime | None = None
    last_disconnect_at: datetime | None = None
    last_block_number: int | None = None
    last_block_at: datetime | None = None
    new_heads_received: int = 0
    logs_received: int = 0
    last_error: str | None = None


def _hex_to_int(value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        try:
            return int(text, 16) if text.startswith(("0x", "0X")) else int(text)
        except ValueError:
            return None
    return None


def build_subscription_payloads(filters: list[LogFilter]) -> list[dict[str, Any]]:
    """Build the JSON-RPC subscribe payloads we send on connect."""
    payloads: list[dict[str, Any]] = [
        {"jsonrpc": "2.0", "id": 1, "method": "eth_subscribe", "params": ["newHeads"]}
    ]
    for idx, log_filter in enumerate(filters, start=2):
        payloads.append(
            {
                "jsonrpc": "2.0",
                "id": idx,
                "method": "eth_subscribe",
                "params": ["logs", log_filter.to_subscription_params()],
            }
        )
    return payloads


def enrich_event(
    *,
    kind: str,
    raw: dict[str, Any],
    chain_id: int,
    received_at: datetime | None = None,
) -> dict[str, Any]:
    """Attach Sapphire-friendly metadata to a raw subscription notification."""
    received_at = received_at or datetime.now(UTC)
    block_number = _hex_to_int(raw.get("number") if kind == "newHeads" else raw.get("blockNumber"))
    out: dict[str, Any] = {
        "timestamp": received_at.isoformat(),
        "chain_id": chain_id,
        "source": "megaeth-ingest",
        "kind": kind,
        "block_number": block_number,
        "symbol": f"MEGAETH:{kind}",
        "action": "ingest",
        "strategy": "megaeth-realtime",
        "raw": raw,
    }
    if kind == "newHeads":
        out["block_hash"] = raw.get("hash")
        out["parent_hash"] = raw.get("parentHash")
        out["block_timestamp"] = _hex_to_int(raw.get("timestamp"))
    elif kind == "logs":
        out["address"] = raw.get("address")
        out["topics"] = raw.get("topics")
        out["log_index"] = _hex_to_int(raw.get("logIndex"))
        out["tx_hash"] = raw.get("transactionHash")
    return out


@dataclass
class MegaEthWsClient:
    """Async WSS subscriber + reconnect loop."""

    config: IngestConfig
    forwarder: EventForwarder
    connector: WsConnector | None = None
    sleep: Callable[[float], Any] = asyncio.sleep
    stats: WsStats = field(default_factory=WsStats)
    _stop_requested: bool = field(default=False, init=False)
    _backoff_seconds: float = field(default=0.0, init=False)

    def stop(self) -> None:
        self._stop_requested = True

    @property
    def is_killswitched(self) -> bool:
        return killswitch_active(self.config.killswitch_path)

    def is_paused(self) -> bool:
        """``EventForwarder.PausedProvider`` impl."""
        return self.is_killswitched

    def _next_backoff(self) -> float:
        if self._backoff_seconds <= 0:
            self._backoff_seconds = self.config.reconnect_backoff_sec
        else:
            self._backoff_seconds = min(self._backoff_seconds * 2.0, self.config.reconnect_max_sec)
        return self._backoff_seconds

    def _reset_backoff(self) -> None:
        self._backoff_seconds = 0.0

    async def run_forever(self, *, max_iterations: int | None = None) -> dict[str, Any]:
        """Top-level reconnect loop. Yields control via ``self.sleep``."""
        if self.connector is None:
            if websockets is None:
                return {"status": "blocked", "reason": "websockets not installed"}
            self.connector = websockets.connect

        iterations = 0
        while not self._stop_requested:
            iterations += 1
            if max_iterations is not None and iterations > max_iterations:
                return {"status": "stopped", "reason": "max_iterations", "iterations": iterations - 1}

            self.stats.connect_attempts += 1
            try:
                await self._connect_and_consume()
                self._reset_backoff()
            except asyncio.CancelledError:
                return {"status": "cancelled"}
            except Exception as exc:  # noqa: BLE001 - daemon swallows + retries
                self.stats.connect_failures += 1
                self.stats.last_error = f"{type(exc).__name__}: {exc}"
                self.stats.ws_connected = False
                self.stats.last_disconnect_at = datetime.now(UTC)
                logger.warning("megaeth_ingest ws disconnect: %s", self.stats.last_error)
                if self._stop_requested:
                    break
                await self.sleep(self._next_backoff())
        return {"status": "stopped"}

    async def _connect_and_consume(self) -> None:
        """One connect → subscribe → consume cycle."""
        assert self.connector is not None
        payloads = build_subscription_payloads(list(self.config.log_filters))
        async with self.connector(self.config.wss_url) as ws:
            self.stats.ws_connected = True
            self.stats.last_connect_at = datetime.now(UTC)
            for payload in payloads:
                await ws.send(json.dumps(payload, separators=(",", ":")))
            sub_id_to_kind: dict[str, str] = {}
            pending_subs: list[str] = ["newHeads"] + ["logs"] * len(self.config.log_filters)

            async for raw_message in ws:
                if self._stop_requested:
                    break
                payload = self._parse_message(raw_message)
                if payload is None:
                    continue
                # Subscribe responses come back first — record their sub IDs.
                if "result" in payload and "id" in payload and pending_subs:
                    sub_id = payload.get("result")
                    if isinstance(sub_id, str):
                        kind = pending_subs.pop(0)
                        sub_id_to_kind[sub_id] = kind
                    continue

                method = payload.get("method")
                if method != "eth_subscription":
                    continue
                params = payload.get("params") or {}
                sub_id = params.get("subscription")
                kind = sub_id_to_kind.get(sub_id) if isinstance(sub_id, str) else None
                if kind is None:
                    continue
                result = params.get("result")
                if not isinstance(result, dict):
                    continue
                self._handle_event(kind, result)

    @staticmethod
    def _parse_message(raw: Any) -> dict[str, Any] | None:
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8", errors="replace")
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return None
        return data if isinstance(data, dict) else None

    def _handle_event(self, kind: str, raw: dict[str, Any]) -> None:
        now = datetime.now(UTC)
        if kind == "newHeads":
            self.stats.new_heads_received += 1
            block_num = _hex_to_int(raw.get("number"))
            if block_num is not None:
                self.stats.last_block_number = block_num
                self.stats.last_block_at = now
        elif kind == "logs":
            self.stats.logs_received += 1
        else:
            return
        event = enrich_event(kind=kind, raw=raw, chain_id=self.config.chain_id, received_at=now)
        # Drop-oldest enqueue — never blocks the WS reader.
        self.forwarder.enqueue(event)
