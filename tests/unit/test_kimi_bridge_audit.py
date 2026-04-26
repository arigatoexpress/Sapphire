"""Tests for Kimi bridge autonomy audit events."""

from __future__ import annotations

import importlib
import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CONTROL_PLANE = ROOT / "services" / "control-plane"
APP_DIR = CONTROL_PLANE / "app"
PACKAGE_NAME = "control_plane_test_app"

if PACKAGE_NAME not in sys.modules:
    spec = importlib.util.spec_from_file_location(
        PACKAGE_NAME,
        APP_DIR / "__init__.py",
        submodule_search_locations=[str(APP_DIR)],
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[PACKAGE_NAME] = module
    spec.loader.exec_module(module)

event_stream = importlib.import_module(f"{PACKAGE_NAME}.event_stream")
kimi_bridge = importlib.import_module(f"{PACKAGE_NAME}.kimi_bridge")


def test_autonomy_cycle_appends_sanitized_audit_event(monkeypatch, tmp_path):
    audit_path = tmp_path / "autonomy.jsonl"
    events = []

    monkeypatch.setenv("SAPPHIRE_AUTONOMY_AUDIT_LOG", str(audit_path))
    monkeypatch.setattr(kimi_bridge, "CONTROL_TOKEN", "ok")
    monkeypatch.setattr(
        event_stream,
        "append_event",
        lambda *args, **kwargs: events.append((args, kwargs)),
    )

    result = kimi_bridge.dispatch(
        "autonomy_cycle",
        {
            "actor": "kimi token=sample-token",
            "note": "password=sample-password",
        },
        token="ok",
    )

    assert result == {"status": "ok", "message": "autonomy cycle queued"}
    assert events
    record = json.loads(audit_path.read_text(encoding="utf-8").strip())
    serialized = json.dumps(record)

    assert record["event_type"] == "autonomy.cycle.requested"
    assert record["actor"] == "kimi_bridge"
    assert record["action"] == "request_autonomy_cycle"
    assert record["outcome"] == "queued"
    assert record["risk"] == "autonomy_coordination"
    assert record["metadata"]["payload_keys"] == ["actor", "note"]
    assert record["metadata"]["requested_actor_hash"]
    assert record["metadata"]["requested_actor_chars"] > 0
    assert "sample-token" not in serialized
    assert "sample-password" not in serialized


def test_unauthorized_autonomy_cycle_does_not_write_audit(monkeypatch, tmp_path):
    audit_path = tmp_path / "autonomy.jsonl"

    monkeypatch.setenv("SAPPHIRE_AUTONOMY_AUDIT_LOG", str(audit_path))
    monkeypatch.setattr(kimi_bridge, "CONTROL_TOKEN", "ok")

    result = kimi_bridge.dispatch("autonomy_cycle", {"actor": "kimi"}, token="wrong")

    assert result["status"] == "error"
    assert "unauthorized" in result["error"]
    assert not audit_path.exists()
