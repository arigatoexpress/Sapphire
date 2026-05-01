"""Tests for the health endpoint payload + aiohttp app."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from aiohttp.test_utils import TestClient, TestServer
from megaeth_ingest.config import IngestConfig
from megaeth_ingest.forwarder import EventForwarder, ForwarderStats
from megaeth_ingest.health import build_health_payload, make_health_app
from megaeth_ingest.ws_client import MegaEthWsClient, WsStats


class _NoopPoster:
    async def post_json(self, url, payload):
        return True


def _make_pieces(killswitch_path):
    cfg = IngestConfig(forwarding_enabled=True, queue_max=64, killswitch_path=killswitch_path)
    fwd = EventForwarder(
        poster=_NoopPoster(),
        target_url=cfg.signal_logger_url,
        queue_max=cfg.queue_max,
        forwarding_enabled=cfg.forwarding_enabled,
    )
    client = MegaEthWsClient(config=cfg, forwarder=fwd, connector=lambda u, **k: None)
    fwd.paused_provider = client
    return cfg, client, fwd


def test_health_payload_shape(tmp_path):
    cfg, client, fwd = _make_pieces(tmp_path / "missing")
    client.stats = WsStats(
        ws_connected=True,
        connect_attempts=2,
        new_heads_received=42,
        last_block_number=12345,
        last_block_at=datetime.now(UTC),
    )
    fwd.stats = ForwarderStats(enqueued=42, forwarded=40, dropped_full_queue=1, post_failures=1)
    payload = build_health_payload(cfg, client, fwd)
    assert payload["ok"] is True
    assert payload["ws_connected"] is True
    assert payload["paused"] is False
    assert payload["forwarding_enabled"] is True
    assert payload["last_block"] == 12345
    assert payload["chain_id"] == cfg.chain_id
    assert payload["queue_max"] == cfg.queue_max
    assert payload["stats"]["new_heads_received"] == 42
    assert payload["stats"]["forwarded"] == 40
    assert payload["lag_seconds"] is not None and payload["lag_seconds"] >= 0


def test_health_payload_paused_when_killswitch(tmp_path):
    pause = tmp_path / "pause"
    pause.write_text("")
    cfg, client, fwd = _make_pieces(pause)
    payload = build_health_payload(cfg, client, fwd)
    assert payload["paused"] is True


@pytest.mark.asyncio
async def test_health_endpoint_returns_json(tmp_path, aiohttp_client=None):
    cfg, client, fwd = _make_pieces(tmp_path / "missing")
    app = make_health_app(cfg, client, fwd)
    async with TestServer(app) as server:
        async with TestClient(server) as client_session:
            resp = await client_session.get("/health")
            assert resp.status == 200
            data = await resp.json()
            assert "ok" in data
            assert "ws_connected" in data
            assert "stats" in data
            assert data["chain_id"] == cfg.chain_id
