"""aiohttp ``/health`` server for the MegaETH ingest service."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from aiohttp import web

from .config import IngestConfig
from .forwarder import EventForwarder
from .ws_client import MegaEthWsClient

logger = logging.getLogger(__name__)


def _lag_seconds(client: MegaEthWsClient) -> float | None:
    if client.stats.last_block_at is None:
        return None
    return max(0.0, (datetime.now(UTC) - client.stats.last_block_at).total_seconds())


def build_health_payload(
    config: IngestConfig,
    client: MegaEthWsClient,
    forwarder: EventForwarder,
) -> dict[str, Any]:
    return {
        "ok": client.stats.ws_connected,
        "ws_connected": client.stats.ws_connected,
        "paused": client.is_killswitched,
        "forwarding_enabled": forwarder.forwarding_enabled,
        "last_block": client.stats.last_block_number,
        "last_block_at": client.stats.last_block_at.isoformat()
        if client.stats.last_block_at
        else None,
        "lag_seconds": _lag_seconds(client),
        "chain_id": config.chain_id,
        "wss_url": config.wss_url,
        "queue_size": forwarder.queue_size,
        "queue_max": config.queue_max,
        "stats": {
            "connect_attempts": client.stats.connect_attempts,
            "connect_failures": client.stats.connect_failures,
            "new_heads_received": client.stats.new_heads_received,
            "logs_received": client.stats.logs_received,
            "enqueued": forwarder.stats.enqueued,
            "forwarded": forwarder.stats.forwarded,
            "dropped_full_queue": forwarder.stats.dropped_full_queue,
            "dropped_paused": forwarder.stats.dropped_paused,
            "dropped_disabled": forwarder.stats.dropped_disabled,
            "post_failures": forwarder.stats.post_failures,
            "last_error": client.stats.last_error or forwarder.stats.last_error,
        },
    }


def make_health_app(
    config: IngestConfig,
    client: MegaEthWsClient,
    forwarder: EventForwarder,
) -> web.Application:
    app = web.Application()

    async def health_handler(_request: web.Request) -> web.Response:
        return web.json_response(build_health_payload(config, client, forwarder))

    app.router.add_get("/health", health_handler)
    return app


async def start_health_server(
    config: IngestConfig,
    client: MegaEthWsClient,
    forwarder: EventForwarder,
) -> tuple[web.AppRunner, web.TCPSite]:
    app = make_health_app(config, client, forwarder)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", config.health_port)
    await site.start()
    logger.info("megaeth_ingest health on http://127.0.0.1:%d/health", config.health_port)
    return runner, site
