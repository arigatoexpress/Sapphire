"""Tests for the HTTP-polling fallback path."""

from __future__ import annotations

import asyncio
from typing import Any

import pytest
from megaeth_ingest.config import IngestConfig
from megaeth_ingest.forwarder import EventForwarder
from megaeth_ingest.http_poller import HttpPollClient


class RecordingPoster:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    async def post_json(self, url: str, payload: dict[str, Any]) -> bool:
        self.calls.append(payload)
        return True


class FakeJsonRpcPoster:
    """Replays a pre-canned sequence of ``eth_getBlockByNumber`` results."""

    def __init__(self, results: list[dict[str, Any] | None]) -> None:
        self._results = list(results)
        self.calls: list[dict[str, Any]] = []

    async def post_json(self, url: str, payload: dict[str, Any]) -> dict[str, Any] | None:
        self.calls.append({"url": url, "payload": payload})
        if not self._results:
            return {"jsonrpc": "2.0", "id": 1, "result": None}
        result = self._results.pop(0)
        return {"jsonrpc": "2.0", "id": 1, "result": result}


def _make_config(**overrides: Any) -> IngestConfig:
    base = {
        "wss_url": "",
        "http_rpc_url": "https://mainnet.megaeth.com/rpc",
        "chain_id": 4326,
        "forwarding_enabled": True,
        "queue_max": 64,
        "poll_interval_sec": 0.001,
    }
    base.update(overrides)
    return IngestConfig(**base)


def _make_client(
    *, results: list[dict[str, Any] | None], config: IngestConfig | None = None
) -> tuple[HttpPollClient, EventForwarder, FakeJsonRpcPoster]:
    cfg = config or _make_config()
    fwd = EventForwarder(
        poster=RecordingPoster(),
        target_url=cfg.signal_logger_url,
        queue_max=cfg.queue_max,
        forwarding_enabled=cfg.forwarding_enabled,
    )
    poster = FakeJsonRpcPoster(results)
    client = HttpPollClient(
        config=cfg, forwarder=fwd, poster=poster, sleep=lambda _t: asyncio.sleep(0)
    )
    return client, fwd, poster


@pytest.mark.asyncio
async def test_polling_emits_new_heads_event_for_new_block():
    block = {
        "number": "0x10",
        "hash": "0x" + "ab" * 32,
        "parentHash": "0x" + "cd" * 32,
        "timestamp": "0x6804ff00",
    }
    client, fwd, poster = _make_client(results=[block])
    summary = await client.run_forever(max_iterations=1)
    assert summary["status"] == "stopped"
    assert client.stats.new_heads_received == 1
    assert client.stats.last_block_number == 0x10
    # Forwarder enqueue with the right shape.
    assert fwd.stats.enqueued == 1
    # Poster called eth_getBlockByNumber('latest', false).
    assert poster.calls[0]["payload"]["method"] == "eth_getBlockByNumber"
    assert poster.calls[0]["payload"]["params"] == ["latest", False]


@pytest.mark.asyncio
async def test_polling_dedupes_repeated_block():
    block_a = {"number": "0x5", "hash": "0x" + "11" * 32}
    # Same block number returned twice in a row → only one event.
    client, fwd, _poster = _make_client(results=[block_a, block_a])
    await client.run_forever(max_iterations=2)
    assert client.stats.new_heads_received == 1
    assert fwd.stats.enqueued == 1


@pytest.mark.asyncio
async def test_polling_emits_event_only_on_advance():
    block_a = {"number": "0x5", "hash": "0x" + "11" * 32}
    block_b = {"number": "0x6", "hash": "0x" + "22" * 32}
    client, fwd, _poster = _make_client(results=[block_a, block_b])
    await client.run_forever(max_iterations=2)
    assert client.stats.new_heads_received == 2
    assert client.stats.last_block_number == 0x6
    assert fwd.stats.enqueued == 2


@pytest.mark.asyncio
async def test_polling_handles_rpc_error_without_crashing():
    class ErroringPoster:
        async def post_json(self, url: str, payload: dict[str, Any]) -> dict[str, Any] | None:
            return {"jsonrpc": "2.0", "id": 1, "error": {"code": -1, "message": "boom"}}

    cfg = _make_config()
    fwd = EventForwarder(
        poster=RecordingPoster(),
        target_url=cfg.signal_logger_url,
        queue_max=cfg.queue_max,
        forwarding_enabled=cfg.forwarding_enabled,
    )
    client = HttpPollClient(
        config=cfg, forwarder=fwd, poster=ErroringPoster(), sleep=lambda _t: asyncio.sleep(0)
    )
    # Should NOT raise — the daemon loop swallows + retries.
    summary = await client.run_forever(max_iterations=1)
    assert summary["status"] == "stopped"
    assert client.stats.connect_failures >= 1


@pytest.mark.asyncio
async def test_polling_logs_log_filters_warning_once():
    from megaeth_ingest.config import LogFilter

    addr = "0x" + "a" * 40
    cfg = _make_config(log_filters=(LogFilter(addresses=(addr,)),))
    block = {"number": "0x1", "hash": "0x" + "11" * 32}
    fwd = EventForwarder(
        poster=RecordingPoster(),
        target_url=cfg.signal_logger_url,
        queue_max=cfg.queue_max,
        forwarding_enabled=cfg.forwarding_enabled,
    )
    poster = FakeJsonRpcPoster([block, block])
    client = HttpPollClient(
        config=cfg, forwarder=fwd, poster=poster, sleep=lambda _t: asyncio.sleep(0)
    )
    await client.run_forever(max_iterations=2)
    # We don't intercept logging here — we just confirm the flag flipped so a
    # second iteration won't re-warn.
    assert client._logged_logs_warning is True


@pytest.mark.asyncio
async def test_polling_killswitch_makes_is_paused_true(tmp_path):
    pause = tmp_path / "pause"
    cfg = _make_config(killswitch_path=pause)
    client, _fwd, _poster = _make_client(results=[], config=cfg)
    assert client.is_paused() is False
    pause.write_text("")
    assert client.is_paused() is True
