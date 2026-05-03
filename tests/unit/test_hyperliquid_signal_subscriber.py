"""Unit tests for the Hyperliquid signal subscriber + translator."""

from __future__ import annotations

import asyncio
import json
import sys
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[2]
SERVICE_SRC = ROOT / "services" / "hyperliquid" / "src"
for path in (ROOT, SERVICE_SRC):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from hyperliquid_bot.signal_subscriber import (  # noqa: E402
    SignalSubscriber,
    translate_signal,
)

# ---------------------------------------------------------------------------
# translate_signal
# ---------------------------------------------------------------------------


def test_translate_signal_normalizes_uppercase_action() -> None:
    out = translate_signal({"symbol": "BTC", "action": "BUY", "price": 50000}, default_size_usd=5.0)

    assert out is not None
    assert out["symbol"] == "BTC"
    assert out["action"] == "buy"


def test_translate_signal_accepts_side_alias() -> None:
    out = translate_signal({"symbol": "eth", "side": "long"}, default_size_usd=5.0)

    assert out is not None
    assert out["symbol"] == "ETH"
    assert out["action"] == "buy"


def test_translate_signal_maps_close_aliases() -> None:
    for raw_action in ("close", "exit", "flatten"):
        out = translate_signal({"symbol": "SOL", "action": raw_action}, default_size_usd=5.0)
        assert out is not None
        assert out["action"] == "close"


def test_translate_signal_drops_unknown_action() -> None:
    out = translate_signal({"symbol": "BTC", "action": "yolo"}, default_size_usd=5.0)

    assert out is None


def test_translate_signal_drops_missing_symbol() -> None:
    out = translate_signal({"action": "buy"}, default_size_usd=5.0)

    assert out is None


def test_translate_signal_uses_default_size_when_missing() -> None:
    out = translate_signal({"symbol": "BTC", "action": "buy"}, default_size_usd=5.0)

    assert out is not None
    assert out["size_usd"] == 5.0


def test_translate_signal_passes_through_size_when_provided() -> None:
    out = translate_signal(
        {"symbol": "BTC", "action": "buy", "size_usd": 3.5},
        default_size_usd=5.0,
    )

    assert out is not None
    assert out["size_usd"] == 3.5


def test_translate_signal_carries_signal_id_for_dedupe() -> None:
    out = translate_signal(
        {"symbol": "BTC", "action": "buy", "signal_id": "abc-123"},
        default_size_usd=5.0,
    )

    assert out is not None
    assert out["signal_id"] == "abc-123"


# ---------------------------------------------------------------------------
# SignalSubscriber drain — no real polling loop
# ---------------------------------------------------------------------------


@pytest.fixture
def signal_paths(tmp_path: Path) -> dict[str, Path]:
    return {
        "signal_path": tmp_path / "signals.jsonl",
        "offset_path": tmp_path / "offset.json",
    }


def _append(path: Path, *entries: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        for entry in entries:
            fh.write(json.dumps(entry) + "\n")


def _capture_handler() -> tuple[list[dict[str, Any]], Callable[[dict], Awaitable[None]]]:
    captured: list[dict[str, Any]] = []

    async def handler(signal: dict) -> None:
        captured.append(signal)

    return captured, handler


async def test_drain_once_processes_appended_lines(
    signal_paths: dict[str, Path],
) -> None:
    captured, handler = _capture_handler()
    sub = SignalSubscriber(
        handler,
        signal_path=signal_paths["signal_path"],
        offset_path=signal_paths["offset_path"],
        default_size_usd=5.0,
    )
    _append(
        signal_paths["signal_path"],
        {"symbol": "BTC", "action": "buy", "signal_id": "1"},
        {"symbol": "ETH", "action": "sell", "signal_id": "2"},
    )

    processed = await sub.drain_once()

    assert processed == 2
    assert [s["symbol"] for s in captured] == ["BTC", "ETH"]


async def test_drain_once_resumes_from_persisted_offset(
    signal_paths: dict[str, Path],
) -> None:
    captured, handler = _capture_handler()
    sub_first = SignalSubscriber(
        handler,
        signal_path=signal_paths["signal_path"],
        offset_path=signal_paths["offset_path"],
        default_size_usd=5.0,
    )
    _append(signal_paths["signal_path"], {"symbol": "BTC", "action": "buy", "signal_id": "1"})
    await sub_first.drain_once()
    _append(signal_paths["signal_path"], {"symbol": "ETH", "action": "buy", "signal_id": "2"})

    captured_two, handler_two = _capture_handler()
    sub_second = SignalSubscriber(
        handler_two,
        signal_path=signal_paths["signal_path"],
        offset_path=signal_paths["offset_path"],
        default_size_usd=5.0,
    )
    processed = await sub_second.drain_once()

    assert processed == 1
    assert [s["symbol"] for s in captured_two] == ["ETH"]


async def test_drain_once_skips_unsupported_symbol(
    signal_paths: dict[str, Path],
) -> None:
    captured, handler = _capture_handler()
    sub = SignalSubscriber(
        handler,
        signal_path=signal_paths["signal_path"],
        offset_path=signal_paths["offset_path"],
        symbols=frozenset({"BTC"}),
        default_size_usd=5.0,
    )
    _append(
        signal_paths["signal_path"],
        {"symbol": "DOGE", "action": "buy", "signal_id": "1"},
        {"symbol": "BTC", "action": "buy", "signal_id": "2"},
    )

    await sub.drain_once()

    assert [s["symbol"] for s in captured] == ["BTC"]


async def test_drain_once_dedupes_repeated_signal_ids(
    signal_paths: dict[str, Path],
) -> None:
    captured, handler = _capture_handler()
    sub = SignalSubscriber(
        handler,
        signal_path=signal_paths["signal_path"],
        offset_path=signal_paths["offset_path"],
        default_size_usd=5.0,
    )
    _append(
        signal_paths["signal_path"],
        {"symbol": "BTC", "action": "buy", "signal_id": "dup"},
        {"symbol": "BTC", "action": "buy", "signal_id": "dup"},
        {"symbol": "BTC", "action": "buy", "signal_id": "fresh"},
    )

    await sub.drain_once()

    assert [s["signal_id"] for s in captured] == ["dup", "fresh"]


async def test_drain_once_skips_malformed_lines(
    signal_paths: dict[str, Path],
) -> None:
    captured, handler = _capture_handler()
    sub = SignalSubscriber(
        handler,
        signal_path=signal_paths["signal_path"],
        offset_path=signal_paths["offset_path"],
        default_size_usd=5.0,
    )
    signal_paths["signal_path"].write_text(
        "{not json\n"
        + json.dumps({"symbol": "BTC", "action": "buy", "signal_id": "1"})
        + "\n"
        + "[]\n",  # not a dict
        encoding="utf-8",
    )

    processed = await sub.drain_once()

    assert processed == 1
    assert captured[0]["signal_id"] == "1"


async def test_drain_once_resets_offset_when_file_shrinks(
    signal_paths: dict[str, Path],
) -> None:
    captured, handler = _capture_handler()
    sub = SignalSubscriber(
        handler,
        signal_path=signal_paths["signal_path"],
        offset_path=signal_paths["offset_path"],
        default_size_usd=5.0,
    )
    # Drain two entries so offset is well past where the truncated file ends.
    _append(
        signal_paths["signal_path"],
        {"symbol": "BTC", "action": "buy", "signal_id": "1"},
        {"symbol": "BTC", "action": "sell", "signal_id": "2"},
    )
    await sub.drain_once()

    # Truncate to a strictly shorter file (logrotate-style replacement).
    signal_paths["signal_path"].write_text(
        json.dumps({"symbol": "ETH", "action": "buy", "signal_id": "3"}) + "\n",
        encoding="utf-8",
    )

    processed = await sub.drain_once()

    assert processed == 1
    assert captured[-1]["symbol"] == "ETH"


async def test_drain_once_returns_zero_when_file_missing(
    signal_paths: dict[str, Path],
) -> None:
    captured, handler = _capture_handler()
    sub = SignalSubscriber(
        handler,
        signal_path=signal_paths["signal_path"],
        offset_path=signal_paths["offset_path"],
        default_size_usd=5.0,
    )

    processed = await sub.drain_once()

    assert processed == 0
    assert captured == []


async def test_drain_once_swallows_handler_exceptions(
    signal_paths: dict[str, Path],
) -> None:
    calls: list[dict[str, Any]] = []

    async def flaky_handler(signal: dict) -> None:
        calls.append(signal)
        if signal["symbol"] == "BTC":
            raise RuntimeError("simulated handler failure")

    sub = SignalSubscriber(
        flaky_handler,
        signal_path=signal_paths["signal_path"],
        offset_path=signal_paths["offset_path"],
        default_size_usd=5.0,
    )
    _append(
        signal_paths["signal_path"],
        {"symbol": "BTC", "action": "buy", "signal_id": "1"},
        {"symbol": "ETH", "action": "buy", "signal_id": "2"},
    )

    processed = await sub.drain_once()

    assert processed == 2
    assert [c["symbol"] for c in calls] == ["BTC", "ETH"]


async def test_run_can_be_stopped(signal_paths: dict[str, Path]) -> None:
    _captured, handler = _capture_handler()
    sub = SignalSubscriber(
        handler,
        signal_path=signal_paths["signal_path"],
        offset_path=signal_paths["offset_path"],
        default_size_usd=5.0,
        poll_interval=0.01,
    )

    task = asyncio.create_task(sub.run())
    await asyncio.sleep(0.05)
    sub.stop()
    await asyncio.wait_for(task, timeout=1.0)

    assert sub._running is False  # noqa: SLF001
