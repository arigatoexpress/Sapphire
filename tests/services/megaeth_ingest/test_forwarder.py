"""Tests for the bounded queue + worker forwarder."""

from __future__ import annotations

import asyncio
from typing import Any

import pytest
from megaeth_ingest.forwarder import EventForwarder


class RecordingPoster:
    def __init__(self, *, ok: bool = True, raises: Exception | None = None) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.ok = ok
        self.raises = raises

    async def post_json(self, url: str, payload: dict[str, Any]) -> bool:
        self.calls.append((url, payload))
        if self.raises is not None:
            raise self.raises
        return self.ok


class FakePauseProvider:
    def __init__(self, paused: bool = False) -> None:
        self.paused = paused

    def is_paused(self) -> bool:
        return self.paused


@pytest.mark.asyncio
async def test_forwards_when_enabled():
    poster = RecordingPoster()
    fwd = EventForwarder(
        poster=poster,
        target_url="http://x/api/signals",
        webhook_secret="topsecret",
        queue_max=16,
        forwarding_enabled=True,
    )
    await fwd.start()
    try:
        assert fwd.enqueue({"block_number": 1, "kind": "newHeads"}) is True
        await fwd.drain(timeout=1.0)
    finally:
        await fwd.stop()
    assert len(poster.calls) == 1
    url, payload = poster.calls[0]
    assert url == "http://x/api/signals"
    assert payload["secret"] == "topsecret"
    assert payload["block_number"] == 1
    assert fwd.stats.forwarded == 1
    assert fwd.stats.enqueued == 1
    assert fwd.stats.last_forwarded_block == 1


@pytest.mark.asyncio
async def test_drops_when_disabled():
    poster = RecordingPoster()
    fwd = EventForwarder(
        poster=poster,
        target_url="http://x/api/signals",
        queue_max=16,
        forwarding_enabled=False,  # gate off
    )
    await fwd.start()
    try:
        assert fwd.enqueue({"block_number": 7}) is False
        await asyncio.sleep(0.05)
    finally:
        await fwd.stop()
    assert poster.calls == []
    assert fwd.stats.forwarded == 0
    assert fwd.stats.dropped_disabled == 1


@pytest.mark.asyncio
async def test_drops_when_paused():
    poster = RecordingPoster()
    pause = FakePauseProvider(paused=True)
    fwd = EventForwarder(
        poster=poster,
        target_url="http://x",
        queue_max=16,
        forwarding_enabled=True,
        paused_provider=pause,
    )
    await fwd.start()
    try:
        for _ in range(3):
            fwd.enqueue({"block_number": 1})
        await asyncio.sleep(0.05)
    finally:
        await fwd.stop()
    assert poster.calls == []
    assert fwd.stats.dropped_paused == 3
    assert fwd.stats.forwarded == 0


@pytest.mark.asyncio
async def test_drop_oldest_on_full_queue():
    """Block the worker so the queue actually fills, then prove drop-oldest."""
    release = asyncio.Event()
    posted: list[dict[str, Any]] = []

    class BlockingPoster:
        async def post_json(self, url: str, payload: dict[str, Any]) -> bool:
            await release.wait()
            posted.append(payload)
            return True

    fwd = EventForwarder(
        poster=BlockingPoster(),
        target_url="http://x",
        queue_max=16,
        forwarding_enabled=True,
    )
    await fwd.start()
    try:
        # First event goes into the worker (it blocks on release.wait()).
        assert fwd.enqueue({"block_number": 0}) is True
        await asyncio.sleep(0)  # let worker pick it up

        # Fill the queue (queue_max=16) — 16 events.
        for i in range(1, 17):
            assert fwd.enqueue({"block_number": i}) is True
        # Push 4 more — these must drop the oldest.
        for i in range(17, 21):
            assert fwd.enqueue({"block_number": i}) is True

        # 1 (worker) + 16 (queue) + 4 (overflow) = 21 enqueue calls.
        assert fwd.stats.enqueued == 21
        assert fwd.stats.dropped_full_queue >= 4
        # Release the worker and let everything drain.
        release.set()
        await fwd.drain(timeout=2.0)
    finally:
        release.set()
        await fwd.stop()

    # Newest survives (block 20 should be in posted).
    posted_blocks = [p["block_number"] for p in posted]
    assert 20 in posted_blocks


@pytest.mark.asyncio
async def test_post_failure_increments_counter_no_crash():
    poster = RecordingPoster(raises=RuntimeError("boom"))
    fwd = EventForwarder(
        poster=poster,
        target_url="http://x",
        queue_max=4,
        forwarding_enabled=True,
    )
    await fwd.start()
    try:
        fwd.enqueue({"block_number": 1})
        fwd.enqueue({"block_number": 2})
        await fwd.drain(timeout=1.0)
    finally:
        await fwd.stop()
    assert fwd.stats.post_failures == 2
    assert fwd.stats.forwarded == 0
    assert "boom" in (fwd.stats.last_error or "")


@pytest.mark.asyncio
async def test_non_2xx_counts_as_failure():
    poster = RecordingPoster(ok=False)
    fwd = EventForwarder(
        poster=poster,
        target_url="http://x",
        queue_max=4,
        forwarding_enabled=True,
    )
    await fwd.start()
    try:
        fwd.enqueue({"block_number": 1})
        await fwd.drain(timeout=1.0)
    finally:
        await fwd.stop()
    assert fwd.stats.post_failures == 1
    assert fwd.stats.forwarded == 0
