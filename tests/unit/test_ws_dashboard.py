"""
Tests for the WebSocket dashboard endpoint in shared/health.py.

Verifies:
  - WS endpoint accepts connections and sends init message
  - Push loop broadcasts snapshots to connected clients
  - Origin validation rejects disallowed origins
  - Max client limit is enforced
  - Ping/pong keep-alive works
  - Snapshot builder handles handler failures gracefully
  - Dead clients are cleaned up
"""

import asyncio
import json
import os
import sys
import time
from unittest.mock import AsyncMock, patch

import pytest

# Add alpha-engine shared to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "services", "alpha-engine"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "services", "alpha-engine", "shared"))

from aiohttp import web
from aiohttp.test_utils import AioHTTPTestCase, unittest_run_loop, TestClient, TestServer

import health


# ── Helpers ──────────────────────────────────────────────────────────

def _make_app(
    cors_origins: str = "http://localhost:5173",
    control_handler=None,
    perf_handler=None,
    platform_handler=None,
    max_clients: int = 50,
) -> web.Application:
    """Build a minimal aiohttp app with WS endpoint configured."""
    app = web.Application(middlewares=[health.cors_middleware])
    app["cors_allowlist"] = {o.strip() for o in cors_origins.split(",") if o.strip()}
    app["control_api_token"] = ""
    app["_ws_clients"] = []

    # Register handlers that the snapshot builder looks for
    if control_handler:
        app["control_status_handler"] = control_handler
    if perf_handler:
        app["performance_stats_handler"] = perf_handler
    if platform_handler:
        app["platform_status_handler"] = platform_handler

    app.router.add_get("/ws", health._ws_dashboard_handler)
    return app


async def _mock_control_handler(_payload):
    return {
        "dex_execution_stage": "staged_live",
        "dex_stage_multiplier": 0.25,
        "dex_live_dispatch_enabled": True,
        "kill_switch_active": False,
        "pending_autonomy_decisions": 2,
    }


async def _mock_perf_handler(_payload):
    return {
        "metrics": {
            "system": {
                "total_trades": 42,
                "win_rate": 0.65,
                "realized_pnl": 123.45,
            }
        }
    }


async def _mock_platform_handler(_payload):
    return {
        "platforms": {
            "aster": {"price": 185.5, "status": "active"},
            "lighter": {"price": 185.3, "status": "active"},
        }
    }


# ── Tests ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_ws_connect_and_receive_init():
    """Client connects and receives init message with snapshot data."""
    app = _make_app(
        control_handler=_mock_control_handler,
        perf_handler=_mock_perf_handler,
        platform_handler=_mock_platform_handler,
    )
    async with TestClient(TestServer(app)) as client:
        ws = await client.ws_connect("/ws", headers={"Origin": "http://localhost:5173"})
        msg = await ws.receive_json()
        assert msg["type"] == "init"
        assert msg["control"]["dex_execution_stage"] == "staged_live"
        assert msg["performance"]["metrics"]["system"]["total_trades"] == 42
        assert msg["platforms"]["platforms"]["aster"]["price"] == 185.5
        assert "timestamp" in msg
        await ws.close()


@pytest.mark.asyncio
async def test_ws_ping_pong():
    """Client sends ping and receives pong."""
    app = _make_app(control_handler=_mock_control_handler)
    async with TestClient(TestServer(app)) as client:
        ws = await client.ws_connect("/ws", headers={"Origin": "http://localhost:5173"})
        _ = await ws.receive_json()  # consume init
        await ws.send_str("ping")
        resp = await ws.receive_str()
        assert resp == "pong"
        await ws.close()


@pytest.mark.asyncio
async def test_ws_origin_rejected():
    """Connections from disallowed origins are rejected."""
    app = _make_app(cors_origins="https://sapphire-479610.web.app")
    async with TestClient(TestServer(app)) as client:
        resp = await client.request("GET", "/ws", headers={
            "Origin": "https://evil.example.com",
            "Connection": "Upgrade",
            "Upgrade": "websocket",
            "Sec-WebSocket-Version": "13",
            "Sec-WebSocket-Key": "dGhlIHNhbXBsZSBub25jZQ==",
        })
        assert resp.status == 403


@pytest.mark.asyncio
async def test_ws_no_origin_allowed():
    """Connections without Origin header are accepted (e.g. local dev)."""
    app = _make_app(control_handler=_mock_control_handler)
    async with TestClient(TestServer(app)) as client:
        ws = await client.ws_connect("/ws")
        msg = await ws.receive_json()
        assert msg["type"] == "init"
        await ws.close()


@pytest.mark.asyncio
async def test_ws_max_clients_enforced():
    """Connections beyond max limit are rejected with 503."""
    app = _make_app(control_handler=_mock_control_handler)

    # Override max clients to a small number for testing
    with patch.object(health, '_WS_MAX_CLIENTS', 2):
        async with TestClient(TestServer(app)) as client:
            ws1 = await client.ws_connect("/ws", headers={"Origin": "http://localhost:5173"})
            _ = await ws1.receive_json()
            ws2 = await client.ws_connect("/ws", headers={"Origin": "http://localhost:5173"})
            _ = await ws2.receive_json()

            # Third connection should be rejected
            resp = await client.request("GET", "/ws", headers={
                "Origin": "http://localhost:5173",
                "Connection": "Upgrade",
                "Upgrade": "websocket",
                "Sec-WebSocket-Version": "13",
                "Sec-WebSocket-Key": "dGhlIHNhbXBsZSBub25jZQ==",
            })
            assert resp.status == 503

            await ws1.close()
            await ws2.close()


@pytest.mark.asyncio
async def test_ws_client_cleanup_on_disconnect():
    """Client list is cleaned up when a client disconnects."""
    app = _make_app(control_handler=_mock_control_handler)
    async with TestClient(TestServer(app)) as client:
        ws = await client.ws_connect("/ws", headers={"Origin": "http://localhost:5173"})
        _ = await ws.receive_json()
        assert len(app["_ws_clients"]) == 1
        await ws.close()
        # Give the server a moment to process disconnect
        await asyncio.sleep(0.1)
        assert len(app["_ws_clients"]) == 0


@pytest.mark.asyncio
async def test_build_dashboard_snapshot_handler_failure():
    """Snapshot builder handles handler failures gracefully."""
    async def _failing_handler(_payload):
        raise RuntimeError("Database unavailable")

    app = _make_app(
        control_handler=_failing_handler,
        perf_handler=_mock_perf_handler,
    )

    snapshot = await health._build_dashboard_snapshot(app)
    # Failed handler returns None, others succeed
    assert snapshot["control"] is None
    assert snapshot["performance"]["metrics"]["system"]["total_trades"] == 42
    assert snapshot["platforms"] is None  # not registered
    assert "timestamp" in snapshot


@pytest.mark.asyncio
async def test_build_dashboard_snapshot_no_handlers():
    """Snapshot builder returns None for all keys when no handlers registered."""
    app = _make_app()
    snapshot = await health._build_dashboard_snapshot(app)
    assert snapshot["control"] is None
    assert snapshot["performance"] is None
    assert snapshot["platforms"] is None


@pytest.mark.asyncio
async def test_ws_push_loop_sends_snapshots():
    """Push loop broadcasts snapshots to connected clients."""
    app = _make_app(
        control_handler=_mock_control_handler,
        perf_handler=_mock_perf_handler,
        platform_handler=_mock_platform_handler,
    )

    # Override push interval to be very fast for testing
    with patch.object(health, '_WS_PUSH_INTERVAL', 0.1):
        async with TestClient(TestServer(app)) as client:
            ws = await client.ws_connect("/ws", headers={"Origin": "http://localhost:5173"})
            init_msg = await ws.receive_json()
            assert init_msg["type"] == "init"

            # Start the push loop
            push_task = asyncio.create_task(health._ws_push_loop(app))
            try:
                # Wait for a push snapshot
                snapshot_msg = await asyncio.wait_for(ws.receive_json(), timeout=2.0)
                assert snapshot_msg["type"] == "snapshot"
                assert snapshot_msg["control"]["dex_execution_stage"] == "staged_live"
                assert "timestamp" in snapshot_msg
            finally:
                push_task.cancel()
                try:
                    await push_task
                except asyncio.CancelledError:
                    pass
                await ws.close()


@pytest.mark.asyncio
async def test_ws_multiple_clients_receive_broadcast():
    """Multiple connected clients all receive the same broadcast."""
    app = _make_app(control_handler=_mock_control_handler)

    with patch.object(health, '_WS_PUSH_INTERVAL', 0.1):
        async with TestClient(TestServer(app)) as client:
            ws1 = await client.ws_connect("/ws", headers={"Origin": "http://localhost:5173"})
            ws2 = await client.ws_connect("/ws", headers={"Origin": "http://localhost:5173"})
            _ = await ws1.receive_json()  # init
            _ = await ws2.receive_json()  # init

            push_task = asyncio.create_task(health._ws_push_loop(app))
            try:
                msg1 = await asyncio.wait_for(ws1.receive_json(), timeout=2.0)
                msg2 = await asyncio.wait_for(ws2.receive_json(), timeout=2.0)
                assert msg1["type"] == "snapshot"
                assert msg2["type"] == "snapshot"
            finally:
                push_task.cancel()
                try:
                    await push_task
                except asyncio.CancelledError:
                    pass
                await ws1.close()
                await ws2.close()


@pytest.mark.asyncio
async def test_ws_lifecycle_hooks():
    """Start and stop WS push lifecycle hooks work correctly."""
    app_obj = _make_app(control_handler=_mock_control_handler)
    # Simulate aiohttp lifecycle
    await health._start_ws_push(app_obj)
    assert "_ws_push_task" in app_obj
    assert not app_obj["_ws_push_task"].done()

    await health._stop_ws_push(app_obj)
    assert app_obj["_ws_push_task"].done()
