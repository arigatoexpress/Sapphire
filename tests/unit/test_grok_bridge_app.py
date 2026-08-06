"""Tests for services/grok-bridge/app.py — pure-logic checks only.

Loads app.py via importlib (mirroring test_inference_proxy_app.py) so the
production module is exercised without booting a real socket or shelling out
to the live `grok` CLI.

Run: /opt/homebrew/bin/python3 -m pytest tests/unit/test_grok_bridge_app.py -v
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SVC_DIR = ROOT / "services" / "grok-bridge"
APP_PATH = SVC_DIR / "app.py"
MODULE_NAME = "grok_bridge_app_under_test"


@pytest.fixture()
def app_module(monkeypatch):
    if str(SVC_DIR) not in sys.path:
        sys.path.insert(0, str(SVC_DIR))
    spec = importlib.util.spec_from_file_location(MODULE_NAME, APP_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[MODULE_NAME] = module
    spec.loader.exec_module(module)
    yield module
    sys.modules.pop(MODULE_NAME, None)


def test_bridge_mode_sim_when_flag_set(app_module, monkeypatch):
    monkeypatch.setattr(app_module, "SIM_MODE", True)
    assert app_module._bridge_mode() == "away-sim"


def test_bridge_mode_mac_bridge_when_cli_and_session_present(app_module, monkeypatch, tmp_path):
    fake_auth = tmp_path / "auth.json"
    fake_auth.write_text("{}")
    monkeypatch.setattr(app_module, "SIM_MODE", False)
    monkeypatch.setattr(app_module, "GROK_AUTH_FILE", fake_auth)
    monkeypatch.setattr(app_module, "_grok_bin", lambda: "/usr/bin/true")
    assert app_module._bridge_mode() == "mac-bridge"


def test_bridge_mode_unavailable_without_session(app_module, monkeypatch, tmp_path):
    missing_auth = tmp_path / "does-not-exist.json"
    monkeypatch.setattr(app_module, "SIM_MODE", False)
    monkeypatch.setattr(app_module, "GROK_AUTH_FILE", missing_auth)
    monkeypatch.setattr(app_module, "_grok_bin", lambda: "/usr/bin/true")
    assert app_module._bridge_mode() == "unavailable"


def test_sim_response_shape(app_module):
    resp = app_module._sim_response("hello world")
    assert resp["stopReason"] == "sim"
    assert "hello world" not in resp["text"]  # echoes length only, not content
    assert resp["usage"]["total_tokens"] == 0


def test_run_grok_raises_when_binary_missing(app_module, monkeypatch):
    monkeypatch.setattr(app_module, "_grok_bin", lambda: None)
    with pytest.raises(RuntimeError, match="grok CLI not found"):
        app_module._run_grok("hi")
