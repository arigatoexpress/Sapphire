"""MegaETH ingest service entrypoint.

Reads config (env + ``config/megaeth.yaml``), spins up:

* a bounded ``EventForwarder`` worker (drop-oldest semantics)
* a WSS subscriber that runs forever with exponential backoff
* an aiohttp ``/health`` server on ``SAPPHIRE_MEGAETH_HEALTH_PORT`` (default 8788)

Forwarding is gated by ``SAPPHIRE_MEGAETH_INGEST_ENABLED=1``. The killswitch
file ``~/.sapphire/megaeth_ingest_pause`` suspends forwarding while keeping
the WS connection warm.
"""

from __future__ import annotations

import asyncio
import logging
import os
import signal
import sys
from pathlib import Path
from typing import Any

import aiohttp

# Service uses the Sapphire monorepo lib/core logging setup when available.
ROOT = Path(__file__).resolve().parents[4]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from .config import IngestConfig, load_config  # noqa: E402
from .forwarder import EventForwarder  # noqa: E402
from .health import start_health_server  # noqa: E402
from .ws_client import MegaEthWsClient  # noqa: E402

logger = logging.getLogger(__name__)


class AiohttpPoster:
    """``HttpPoster`` impl using a long-lived ``aiohttp.ClientSession``."""

    def __init__(self, *, timeout_sec: float = 5.0) -> None:
        self._timeout = aiohttp.ClientTimeout(total=timeout_sec)
        self._session: aiohttp.ClientSession | None = None

    async def __aenter__(self) -> "AiohttpPoster":
        self._session = aiohttp.ClientSession(timeout=self._timeout)
        return self

    async def __aexit__(self, *_: object) -> None:
        if self._session is not None:
            await self._session.close()
            self._session = None

    async def post_json(self, url: str, payload: dict[str, Any]) -> bool:
        if self._session is None:
            return False
        async with self._session.post(url, json=payload) as resp:
            return 200 <= resp.status < 300


def _setup_logging() -> None:
    try:
        from sapphire_core.logging_config import setup_logging  # type: ignore

        setup_logging()
        return
    except Exception:
        pass
    level_name = os.environ.get("SAPPHIRE_MEGAETH_LOG_LEVEL", "INFO").upper()
    logging.basicConfig(
        level=getattr(logging, level_name, logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )


async def run_service(config: IngestConfig | None = None) -> None:
    """Bring up the full service. Blocks until SIGINT/SIGTERM or stop()."""
    cfg = config or load_config()
    logger.info(
        "megaeth_ingest starting wss=%s chain_id=%s health_port=%d forwarding=%s queue_max=%d filters=%d",
        cfg.wss_url,
        cfg.chain_id,
        cfg.health_port,
        cfg.forwarding_enabled,
        cfg.queue_max,
        len(cfg.log_filters),
    )

    async with AiohttpPoster() as poster:
        forwarder = EventForwarder(
            poster=poster,
            target_url=cfg.signal_logger_url,
            webhook_secret=cfg.webhook_secret,
            queue_max=cfg.queue_max,
            forwarding_enabled=cfg.forwarding_enabled,
        )
        client = MegaEthWsClient(config=cfg, forwarder=forwarder)
        forwarder.paused_provider = client  # killswitch shared

        await forwarder.start()
        runner, _site = await start_health_server(cfg, client, forwarder)

        loop = asyncio.get_event_loop()
        stop_event = asyncio.Event()

        def _request_stop() -> None:
            stop_event.set()
            client.stop()

        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                loop.add_signal_handler(sig, _request_stop)
            except NotImplementedError:  # pragma: no cover - Windows
                pass

        ws_task = asyncio.create_task(client.run_forever(), name="megaeth-ws")
        stop_task = asyncio.create_task(stop_event.wait(), name="megaeth-stop")

        done, _pending = await asyncio.wait(
            {ws_task, stop_task}, return_when=asyncio.FIRST_COMPLETED
        )
        client.stop()
        if not ws_task.done():
            try:
                await asyncio.wait_for(ws_task, timeout=2.0)
            except (asyncio.TimeoutError, Exception):
                ws_task.cancel()
        await forwarder.stop()
        await runner.cleanup()
        # Surface ws_task exception, if any, for the operator log.
        for task in done:
            if task is ws_task and task.exception():
                logger.error("megaeth ws_task exited with: %s", task.exception())


def main() -> None:
    _setup_logging()
    try:
        asyncio.run(run_service())
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
