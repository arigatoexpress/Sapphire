from __future__ import annotations

from lib.grok.bridge_client import pick_transport, smart_query


def test_pick_mac_bridge_when_healthy():
    pick = pick_transport(
        env={"GROK_BRIDGE_URL": "http://127.0.0.1:19998"},
        health={"status": "ok", "mode": "mac-bridge"},
    )
    assert pick.rail == "mac-bridge"
    assert pick.base_url == "http://127.0.0.1:19998"


def test_pick_sim_when_prefer():
    pick = pick_transport(prefer_sim=True)
    assert pick.rail == "sim"


def test_pick_api_key():
    pick = pick_transport(
        env={"XAI_API_KEY": "x"},
        health={"status": "error", "mode": "unavailable"},
    )
    assert pick.rail == "api-key"


def test_smart_query_sim():
    out = smart_query("hello", prefer_sim=True)
    assert out["stopReason"] == "sim"
    assert out["_transport"]["rail"] == "sim"
