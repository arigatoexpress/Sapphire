"""HTTP-polling fallback for the MegaETH ingest service.

Activated when ``IngestConfig.wss_url`` is unset (and ``wss_required=False``).
Polls ``eth_getBlockByNumber('latest')`` against the configured HTTP RPC
every ``poll_interval_sec``. Each newly-seen block produces an enriched
``newHeads``-shaped event that mirrors the WSS path's output schema, so the
forwarder can't tell the two paths apart.

Latency note: ~1s polling adds ~1s of latency vs a real WS subscription
on a 10ms-block chain. This mode exists so the service can run end-to-end
without a partner-provider WSS key — public mainnet WSS does not exist
as of 2026-04-30.

The ``logs`` subscription path is **not** mirrored here: there is no
sane way to tail ``eth_getLogs`` on a 10ms-block chain via polling. If
``log_filters`` is set in HTTP-polling mode, the poller logs a warning
once and ignores them. Operators who need logs must wire a WSS URL.
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Protocol

from .config import IngestConfig, killswitch_active
from .forwarder import EventForwarder
from .ws_client import WsStats, _hex_to_int, enrich_event

logger = logging.getLogger(__name__)


class HttpPoster(Protocol):
    """Minimal interface for the HTTP RPC client used by the poller."""

    async def post_json(self, url: str, payload: dict[str, Any]) -> dict[str, Any] | None: ...


@dataclass
class HttpPollClient:
    """Async polling subscriber. Mirrors :class:`MegaEthWsClient`'s public surface.

    Methods:
      - ``run_forever`` — long-running loop driving ``eth_getBlockByNumber``.
      - ``stop`` — request graceful shutdown.
      - ``is_paused`` — for the ``EventForwarder.PausedProvider`` protocol.

    The poller never blocks on the forwarder; it uses drop-oldest enqueue.
    """

    config: IngestConfig
    forwarder: EventForwarder
    poster: HttpPoster
    sleep: Callable[[float], Any] = asyncio.sleep
    stats: WsStats = field(default_factory=WsStats)
    _stop_requested: bool = field(default=False, init=False)
    _last_block_number: int | None = field(default=None, init=False)
    _logged_logs_warning: bool = field(default=False, init=False)

    def stop(self) -> None:
        self._stop_requested = True

    @property
    def is_killswitched(self) -> bool:
        return killswitch_active(self.config.killswitch_path)

    def is_paused(self) -> bool:
        """``EventForwarder.PausedProvider`` impl."""
        return self.is_killswitched

    async def run_forever(self, *, max_iterations: int | None = None) -> dict[str, Any]:
        """Poll loop. Yields control via ``self.sleep``."""
        if self.config.log_filters and not self._logged_logs_warning:
            logger.warning(
                "megaeth_ingest http-polling mode does not support log_filters; "
                "ignoring %d filter(s). Wire a WSS URL to enable logs.",
                len(self.config.log_filters),
            )
            self._logged_logs_warning = True

        iterations = 0
        while not self._stop_requested:
            iterations += 1
            if max_iterations is not None and iterations > max_iterations:
                return {
                    "status": "stopped",
                    "reason": "max_iterations",
                    "iterations": iterations - 1,
                }
            try:
                await self._poll_once()
            except asyncio.CancelledError:
                return {"status": "cancelled"}
            except Exception as exc:  # noqa: BLE001 - daemon swallows + retries
                self.stats.connect_failures += 1
                self.stats.last_error = f"{type(exc).__name__}: {exc}"
                logger.warning("megaeth_ingest http-poll error: %s", self.stats.last_error)
            if self._stop_requested:
                break
            await self.sleep(self.config.poll_interval_sec)
        return {"status": "stopped"}

    async def _poll_once(self) -> None:
        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "eth_getBlockByNumber",
            "params": ["latest", False],
        }
        self.stats.connect_attempts += 1
        body = await self.poster.post_json(self.config.http_rpc_url, payload)
        if not isinstance(body, dict):
            return
        if "error" in body and body["error"]:
            raise RuntimeError(f"RPC error: {body['error']}")
        block = body.get("result")
        if not isinstance(block, dict):
            return

        self.stats.ws_connected = True  # treat "got a block" as healthy
        self.stats.last_connect_at = datetime.now(UTC)

        block_number = _hex_to_int(block.get("number"))
        if block_number is None:
            return
        # Deduplicate — same block emitted only once.
        if self._last_block_number is not None and block_number <= self._last_block_number:
            return
        self._last_block_number = block_number

        now = datetime.now(UTC)
        self.stats.new_heads_received += 1
        self.stats.last_block_number = block_number
        self.stats.last_block_at = now

        event = enrich_event(kind="newHeads", raw=block, chain_id=self.config.chain_id, received_at=now)
        self.forwarder.enqueue(event)


@dataclass
class AiohttpJsonPoster:
    """``HttpPoster`` impl wrapping ``aiohttp.ClientSession.post`` for JSON-RPC."""

    session: Any  # aiohttp.ClientSession
    timeout_sec: float = 5.0

    async def post_json(self, url: str, payload: dict[str, Any]) -> dict[str, Any] | None:
        try:
            async with self.session.post(url, json=payload) as resp:
                if resp.status >= 400:
                    raise RuntimeError(f"HTTP {resp.status}")
                text = await resp.text()
        except Exception as exc:  # noqa: BLE001 — caller handles retries
            raise RuntimeError(f"http-rpc transport: {exc}") from exc
        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"http-rpc non-JSON body: {exc}") from exc
        return data if isinstance(data, dict) else None
