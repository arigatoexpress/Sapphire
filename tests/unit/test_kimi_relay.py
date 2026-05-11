"""Tests for the Telegram-backed Kimi relay guardrails."""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
TELEGRAM_LIB = ROOT / "lib" / "telegram"


def _load_relay(monkeypatch: pytest.MonkeyPatch):
    if str(TELEGRAM_LIB) not in sys.path:
        sys.path.insert(0, str(TELEGRAM_LIB))
    for name in (
        "KIMI_RELAY_ENABLED",
        "TELEGRAM_BOT_TOKEN",
        "RELAY_READER_TOKEN",
        "KIMI_RELAY_CHAT_ID",
    ):
        monkeypatch.delenv(name, raising=False)
    sys.modules.pop("kimi_relay", None)
    return importlib.import_module("kimi_relay")


def test_relay_query_refuses_live_send_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    relay = _load_relay(monkeypatch)

    with pytest.raises(RuntimeError, match="KIMI_RELAY_ENABLED"):
        relay.relay_query("hello", timeout=1)


def test_send_message_refuses_live_send_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    relay = _load_relay(monkeypatch)

    with pytest.raises(RuntimeError, match="KIMI_RELAY_ENABLED"):
        relay._send_message("hello")
