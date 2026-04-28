"""Tests for the Hyperliquid plugin tool."""

from __future__ import annotations

import importlib.util
import io
import json
import sys
from pathlib import Path

TOOLS = Path(__file__).parent.parent / "tools"
ROOT = TOOLS.parents[2]
SERVICE_SRC = ROOT / "services" / "hyperliquid" / "src"
for path in (ROOT, SERVICE_SRC):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

_spec = importlib.util.spec_from_file_location("hyperliquid_tool", TOOLS / "internal" / "hyperliquid.py")
hyperliquid = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(hyperliquid)


def test_status_action_is_signal_only(tmp_path, monkeypatch):
    monkeypatch.setenv("SAPPHIRE_ROUTINE_PAUSE_DIR", str(tmp_path / "pause"))

    result = hyperliquid.handle({"action": "status"})

    assert result["mode"] == "signal-only"
    assert result["wallet_keys_required"] is False
    assert result["live_trading_enabled"] is False


def test_subscribe_test_action_is_dry_run(monkeypatch, tmp_path):
    monkeypatch.setenv("SAPPHIRE_ROUTINE_PAUSE_DIR", str(tmp_path / "pause"))

    result = hyperliquid.handle({"action": "subscribe-test"})

    assert result["status"] == "dry-run"
    assert result["subscription_count"] == 9
    assert result["auth_required"] is False


def test_subscribe_test_accepts_underscore_alias(monkeypatch, tmp_path):
    monkeypatch.setenv("SAPPHIRE_ROUTINE_PAUSE_DIR", str(tmp_path / "pause"))

    result = hyperliquid.handle({"action": "subscribe_test"})

    assert result["status"] == "dry-run"


def test_latest_action_uses_store_limit(monkeypatch):
    class FakeStore:
        def latest(self, limit: int = 10) -> list[dict]:
            return [{"limit": limit}]

    monkeypatch.setattr(hyperliquid, "JsonlSignalStore", lambda: FakeStore())

    result = hyperliquid.handle({"action": "latest", "limit": 3})

    assert result == {"signals": [{"limit": 3}], "limit": 3}


def test_unknown_action_returns_error():
    result = hyperliquid.handle({"action": "trade"})

    assert "unknown action" in result["error"]
    assert result["valid_actions"] == ["status", "latest", "subscribe-test"]


def test_run_returns_json_string(monkeypatch):
    monkeypatch.setattr(hyperliquid, "handle", lambda payload: {"action": payload["action"]})

    result = json.loads(hyperliquid.run("status"))

    assert result == {"action": "status"}


def test_main_rejects_invalid_json():
    out = io.StringIO()

    code = hyperliquid.main(stream_in=io.StringIO("{bad"), stream_out=out)

    assert code == 2
    assert "invalid JSON" in out.getvalue()


def test_main_rejects_non_object_json():
    out = io.StringIO()

    code = hyperliquid.main(stream_in=io.StringIO("[]"), stream_out=out)

    assert code == 2
    assert "stdin payload must be a JSON object" in out.getvalue()


def test_main_returns_nonzero_for_unknown_action():
    out = io.StringIO()

    code = hyperliquid.main(stream_in=io.StringIO('{"action":"bogus"}'), stream_out=out)

    assert code == 1
    assert "unknown action" in out.getvalue()


def test_top_level_shim_exports_handle():
    spec = importlib.util.spec_from_file_location("hyperliquid_shim", TOOLS / "hyperliquid.py")
    shim = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(shim)

    assert hasattr(shim, "handle")
