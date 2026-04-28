"""Tests for the onchain_intel plugin tool."""

from __future__ import annotations

import importlib.util
import io
import json
import sys
from pathlib import Path

TOOLS = Path(__file__).parent.parent / "tools"
ROOT = TOOLS.parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

_spec = importlib.util.spec_from_file_location(
    "onchain_intel_tool",
    TOOLS / "internal" / "onchain_intel.py",
)
onchain_intel = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(onchain_intel)


def test_status_action_is_fixture_by_default(monkeypatch):
    monkeypatch.delenv("SAPPHIRE_GLASSNODE_LIVE", raising=False)

    result = onchain_intel.handle({"action": "status"})

    assert result["service"] == "onchain_intel"
    assert result["mode"] == "fixture"
    assert result["wallet_keys_required"] is False
    assert result["trading_enabled"] is False


def test_snapshot_action_accepts_assets_and_backfill(monkeypatch, tmp_path):
    monkeypatch.setenv("SAPPHIRE_ONCHAIN_USAGE_FILE", str(tmp_path / "usage.json"))

    result = onchain_intel.handle(
        {"action": "snapshot", "assets": "BTC,ETH", "backfill_days": 9999}
    )

    assert sorted(result["assets"]) == ["BTC", "ETH"]
    assert result["limits"]["backfill_days_requested"] == 730
    assert result["summary"]["live_provider_count"] == 0


def test_unknown_action_returns_error():
    result = onchain_intel.handle({"action": "trade"})

    assert "unknown action" in result["error"]
    assert "write-snapshot" in result["valid_actions"]


def test_main_rejects_invalid_json():
    out = io.StringIO()

    code = onchain_intel.main(stream_in=io.StringIO("{bad"), stream_out=out)

    assert code == 2
    assert "invalid JSON" in out.getvalue()


def test_main_rejects_non_object_json():
    out = io.StringIO()

    code = onchain_intel.main(stream_in=io.StringIO("[]"), stream_out=out)

    assert code == 2
    assert "stdin payload must be a JSON object" in out.getvalue()


def test_run_returns_json_string(monkeypatch):
    monkeypatch.setattr(onchain_intel, "handle", lambda payload: {"action": payload["action"]})

    assert json.loads(onchain_intel.run("status")) == {"action": "status"}


def test_top_level_shim_exports_handle():
    spec = importlib.util.spec_from_file_location("onchain_intel_shim", TOOLS / "onchain_intel.py")
    shim = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(shim)

    assert hasattr(shim, "handle")
