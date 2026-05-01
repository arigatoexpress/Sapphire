"""Bounded async queue + HTTP worker for forwarding ingested events.

The forwarder owns the only outbound HTTP path. The WS reader pushes enriched
events onto a bounded ``asyncio.Queue``; if the queue is full the oldest event
is dropped and a counter increments. This guarantees the WS reader never
blocks on signal-logger latency — important because MegaETH's ~10ms blocks
mean a single second of HTTP backpressure can wedge the reader for thousands
of events.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any, Protocol

logger = logging.getLogger(__name__)


class HttpPoster(Protocol):
    """Minimal protocol for the HTTP poster the forwarder uses."""

    async def post_json(self, url: str, payload: dict[str, Any]) -> bool:
        """POST ``payload`` as JSON. Return True on 2xx, False otherwise."""


@dataclass
class ForwarderStats:
    enqueued: int = 0
    forwarded: int = 0
    dropped_full_queue: int = 0
    dropped_paused: int = 0
    dropped_disabled: int = 0
    post_failures: int = 0
    last_error: str | None = None
    last_forwarded_block: int | None = None


@dataclass
class EventForwarder:
    """Bounded queue + worker pattern for downstream HTTP forwarding."""

    poster: HttpPoster
    target_url: str
    webhook_secret: str = ""
    queue_max: int = 4096
    forwarding_enabled: bool = False
    paused_provider: "PausedProvider | None" = None
    stats: ForwarderStats = field(default_factory=ForwarderStats)
    _queue: asyncio.Queue[dict[str, Any]] = field(init=False)
    _worker_task: asyncio.Task[None] | None = field(default=None, init=False)
    _stopped: bool = field(default=False, init=False)

    def __post_init__(self) -> None:
        self._queue = asyncio.Queue(maxsize=max(16, self.queue_max))

    @property
    def queue_size(self) -> int:
        return self._queue.qsize()

    def enqueue(self, event: dict[str, Any]) -> bool:
        """Drop-oldest enqueue. Returns True if event was queued."""
        if not self.forwarding_enabled:
            self.stats.dropped_disabled += 1
            return False
        if self._is_paused():
            self.stats.dropped_paused += 1
            return False
        # Drop-oldest semantics: if full, pop one then push.
        while self._queue.full():
            try:
                self._queue.get_nowait()
                self.stats.dropped_full_queue += 1
            except asyncio.QueueEmpty:  # pragma: no cover - race only
                break
        try:
            self._queue.put_nowait(event)
        except asyncio.QueueFull:  # pragma: no cover - race only
            self.stats.dropped_full_queue += 1
            return False
        self.stats.enqueued += 1
        return True

    def _is_paused(self) -> bool:
        if self.paused_provider is None:
            return False
        try:
            return bool(self.paused_provider.is_paused())
        except Exception:  # pragma: no cover - never trust provider
            return False

    async def start(self) -> None:
        if self._worker_task is not None:
            return
        self._worker_task = asyncio.create_task(self._run_worker(), name="megaeth-forwarder")

    async def stop(self) -> None:
        self._stopped = True
        if self._worker_task is None:
            return
        self._worker_task.cancel()
        try:
            await self._worker_task
        except (asyncio.CancelledError, Exception):
            pass
        self._worker_task = None

    async def drain(self, *, timeout: float = 5.0) -> None:
        """Wait until the queue is empty or timeout elapses (testing helper)."""
        try:
            await asyncio.wait_for(self._queue.join(), timeout=timeout)
        except asyncio.TimeoutError:
            return

    async def _run_worker(self) -> None:
        while not self._stopped:
            try:
                event = await self._queue.get()
            except asyncio.CancelledError:
                return
            try:
                await self._post_one(event)
            finally:
                self._queue.task_done()

    async def _post_one(self, event: dict[str, Any]) -> None:
        payload = dict(event)
        if self.webhook_secret:
            payload.setdefault("secret", self.webhook_secret)
        try:
            ok = await self.poster.post_json(self.target_url, payload)
        except Exception as exc:  # noqa: BLE001 - never let worker crash
            self.stats.post_failures += 1
            self.stats.last_error = f"{type(exc).__name__}: {exc}"
            logger.warning("megaeth_ingest: forward failed: %s", self.stats.last_error)
            return
        if not ok:
            self.stats.post_failures += 1
            self.stats.last_error = "non-2xx response"
            return
        self.stats.forwarded += 1
        block_number = event.get("block_number")
        if isinstance(block_number, int):
            self.stats.last_forwarded_block = block_number


class PausedProvider(Protocol):
    """Returns True when forwarding should be suspended."""

    def is_paused(self) -> bool:
        ...
