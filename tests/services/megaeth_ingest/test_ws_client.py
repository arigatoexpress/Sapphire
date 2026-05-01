"""Tests for the MegaETH WS client (subscribe + reconnect + killswitch)."""

from __future__ import annotations

import asyncio
import json
from typing import Any

import pytest
from megaeth_ingest.config import IngestConfig, LogFilter
from megaeth_ingest.forwarder import EventForwarder
from megaeth_ingest.ws_client import (
    MegaEthWsClient,
    build_subscription_payloads,
    enrich_event,
)


class RecordingPoster:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    async def post_json(self, url: str, payload: dict[str, Any]) -> bool:
        self.calls.append(payload)
        return True


class FakeWebSocket:
    """Async-iterable mock that mimics ``websockets`` connection."""

    def __init__(self, messages: list[str]) -> None:
        self._messages = messages
        self.sent: list[dict[str, Any]] = []
        self._iter: Any = None

    async def __aenter__(self) -> "FakeWebSocket":
        return self

    async def __aexit__(self, *_: object) -> None:
        return None

    async def send(self, payload: str) -> None:
        self.sent.append(json.loads(payload))

    def __aiter__(self) -> "FakeWebSocket":
        self._iter = iter(self._messages)
        return self

    async def __anext__(self) -> str:
        try:
            return next(self._iter)
        except StopIteration as exc:
            raise StopAsyncIteration from exc


def make_connector(ws: FakeWebSocket):
    """Return a ``websockets.connect``-shaped callable that yields ``ws``."""

    def _connect(url: str, **_: Any) -> FakeWebSocket:
        return ws

    return _connect


def make_client(
    *,
    forwarder: EventForwarder | None = None,
    ws: FakeWebSocket | None = None,
    config: IngestConfig | None = None,
):
    cfg = config or IngestConfig(forwarding_enabled=True, queue_max=64, reconnect_backoff_sec=0.01)
    fwd = forwarder
    if fwd is None:
        fwd = EventForwarder(
            poster=RecordingPoster(),
            target_url=cfg.signal_logger_url,
            queue_max=cfg.queue_max,
            forwarding_enabled=cfg.forwarding_enabled,
        )
    client = MegaEthWsClient(
        config=cfg,
        forwarder=fwd,
        connector=make_connector(ws) if ws is not None else None,
        sleep=lambda _t: asyncio.sleep(0),  # speed up backoff
    )
    fwd.paused_provider = client
    return client, fwd


def test_build_subscription_payloads_just_newheads():
    out = build_subscription_payloads([])
    assert len(out) == 1
    assert out[0]["method"] == "eth_subscribe"
    assert out[0]["params"] == ["newHeads"]


def test_build_subscription_payloads_with_logs():
    flt = LogFilter(addresses=("0x" + "a" * 40,), topics=("0xabc",))
    out = build_subscription_payloads([flt])
    assert len(out) == 2
    assert out[1]["params"][0] == "logs"
    assert out[1]["params"][1] == {"address": ["0x" + "a" * 40], "topics": ["0xabc"]}


def test_enrich_event_newheads_decodes_hex():
    raw = {"number": "0xa", "hash": "0xfeed", "timestamp": "0x1f"}
    enriched = enrich_event(kind="newHeads", raw=raw, chain_id=6342)
    assert enriched["block_number"] == 10
    assert enriched["block_hash"] == "0xfeed"
    assert enriched["block_timestamp"] == 31
    assert enriched["chain_id"] == 6342
    assert enriched["source"] == "megaeth-ingest"
    assert "timestamp" in enriched
    assert enriched["symbol"] == "MEGAETH:newHeads"


def test_enrich_event_logs_extracts_topics_and_addr():
    raw = {
        "address": "0xdead",
        "topics": ["0xabc"],
        "blockNumber": "0x5",
        "logIndex": "0x2",
        "transactionHash": "0xbeef",
    }
    enriched = enrich_event(kind="logs", raw=raw, chain_id=6342)
    assert enriched["block_number"] == 5
    assert enriched["address"] == "0xdead"
    assert enriched["log_index"] == 2
    assert enriched["tx_hash"] == "0xbeef"


@pytest.mark.asyncio
async def test_subscribe_and_consume_one_block():
    sub_resp = json.dumps({"jsonrpc": "2.0", "id": 1, "result": "sub-1"})
    new_head = json.dumps(
        {
            "jsonrpc": "2.0",
            "method": "eth_subscription",
            "params": {
                "subscription": "sub-1",
                "result": {"number": "0xff", "hash": "0xabcd"},
            },
        }
    )
    ws = FakeWebSocket(messages=[sub_resp, new_head])
    poster = RecordingPoster()
    fwd = EventForwarder(
        poster=poster,
        target_url="http://x",
        queue_max=64,
        forwarding_enabled=True,
    )
    client, _ = make_client(forwarder=fwd, ws=ws)

    await fwd.start()
    try:
        await client._connect_and_consume()
        await fwd.drain(timeout=1.0)
    finally:
        await fwd.stop()

    assert ws.sent[0]["method"] == "eth_subscribe"
    assert client.stats.new_heads_received == 1
    assert client.stats.last_block_number == 255
    assert len(poster.calls) == 1
    assert poster.calls[0]["block_number"] == 255
    assert poster.calls[0]["chain_id"] == 6342


@pytest.mark.asyncio
async def test_killswitch_blocks_forwarding_but_ws_still_consumes(tmp_path):
    pause_path = tmp_path / "megaeth_ingest_pause"
    pause_path.write_text("")  # killswitch ON
    cfg = IngestConfig(
        forwarding_enabled=True,
        queue_max=64,
        reconnect_backoff_sec=0.01,
        killswitch_path=pause_path,
    )
    sub_resp = json.dumps({"jsonrpc": "2.0", "id": 1, "result": "sub-1"})
    new_head = json.dumps(
        {
            "jsonrpc": "2.0",
            "method": "eth_subscription",
            "params": {"subscription": "sub-1", "result": {"number": "0x1"}},
        }
    )
    ws = FakeWebSocket(messages=[sub_resp, new_head])
    poster = RecordingPoster()
    fwd = EventForwarder(
        poster=poster,
        target_url="http://x",
        queue_max=64,
        forwarding_enabled=True,
    )
    client, _ = make_client(forwarder=fwd, ws=ws, config=cfg)

    assert client.is_killswitched is True
    await fwd.start()
    try:
        await client._connect_and_consume()
        await asyncio.sleep(0.05)
    finally:
        await fwd.stop()

    # WS still received the head event...
    assert client.stats.new_heads_received == 1
    # ...but forwarding was suppressed.
    assert poster.calls == []
    assert fwd.stats.dropped_paused == 1


@pytest.mark.asyncio
async def test_run_forever_reconnects_on_exception():
    """run_forever should retry after a connect exception (no crash)."""
    attempts = {"n": 0}

    def flaky_connector(url: str, **_: Any):
        attempts["n"] += 1
        raise RuntimeError("simulated drop")

    cfg = IngestConfig(forwarding_enabled=True, reconnect_backoff_sec=0.001)
    fwd = EventForwarder(
        poster=RecordingPoster(),
        target_url="http://x",
        queue_max=16,
        forwarding_enabled=True,
    )
    client = MegaEthWsClient(
        config=cfg,
        forwarder=fwd,
        connector=flaky_connector,
        sleep=lambda _t: asyncio.sleep(0),
    )
    fwd.paused_provider = client

    await fwd.start()
    try:
        result = await client.run_forever(max_iterations=3)
    finally:
        await fwd.stop()
    assert result["status"] == "stopped"
    assert attempts["n"] >= 3
    assert client.stats.connect_failures >= 3
    assert client.stats.last_error and "simulated drop" in client.stats.last_error


@pytest.mark.asyncio
async def test_backoff_grows_then_resets_on_success():
    """Successful consume should reset the backoff window."""
    cfg = IngestConfig(forwarding_enabled=True, reconnect_backoff_sec=0.001, reconnect_max_sec=0.5)
    sub_resp = json.dumps({"jsonrpc": "2.0", "id": 1, "result": "sub-1"})
    ws_ok = FakeWebSocket(messages=[sub_resp])  # subscribes then EOFs cleanly

    state = {"calls": 0}

    def connector(url: str, **_: Any):
        state["calls"] += 1
        if state["calls"] == 1:
            raise RuntimeError("first fail")
        return ws_ok

    fwd = EventForwarder(
        poster=RecordingPoster(),
        target_url="http://x",
        queue_max=16,
        forwarding_enabled=True,
    )
    client = MegaEthWsClient(
        config=cfg, forwarder=fwd, connector=connector, sleep=lambda _t: asyncio.sleep(0)
    )
    fwd.paused_provider = client
    await fwd.start()
    try:
        await client.run_forever(max_iterations=2)
    finally:
        await fwd.stop()
    # After the successful second iteration, backoff window must be reset.
    assert client._backoff_seconds == 0.0


@pytest.mark.asyncio
async def test_stop_request_breaks_loop():
    cfg = IngestConfig(forwarding_enabled=True, reconnect_backoff_sec=0.001)
    fwd = EventForwarder(
        poster=RecordingPoster(),
        target_url="http://x",
        queue_max=16,
        forwarding_enabled=True,
    )

    def connector(url: str, **_: Any):
        raise RuntimeError("never connects")

    client = MegaEthWsClient(
        config=cfg, forwarder=fwd, connector=connector, sleep=lambda _t: asyncio.sleep(0)
    )
    client.stop()
    await fwd.start()
    try:
        result = await client.run_forever()
    finally:
        await fwd.stop()
    assert result["status"] == "stopped"
