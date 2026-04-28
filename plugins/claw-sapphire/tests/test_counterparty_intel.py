from __future__ import annotations

import importlib.util
from pathlib import Path

TOOL_PATH = Path(__file__).resolve().parents[1] / "tools" / "internal" / "counterparty_intel.py"


def _tool():
    spec = importlib.util.spec_from_file_location("counterparty_intel_tool_test", TOOL_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_status_action():
    out = _tool().handle({"action": "status"})
    assert out["public_data_only"] is True


def test_leaderboard_action_returns_mock():
    out = _tool().handle({"action": "leaderboard", "top_n": 1})
    assert out["ok"] is True
    assert len(out["traders"]) == 1


def test_position_changes_action():
    out = _tool().handle(
        {
            "action": "position-changes",
            "previous": [{"trader": "0x1", "asset": "BTC", "side": "long", "size_usd": 100}],
            "current": [{"trader": "0x1", "asset": "BTC", "side": "long", "size_usd": 200}],
        }
    )
    assert out["position_changes"][0]["asset"] == "BTC"


def test_smart_money_consensus_action():
    out = _tool().handle(
        {
            "action": "smart-money-consensus",
            "position_changes": [
                {
                    "trader": "0x1",
                    "asset": "BTC",
                    "old_side": "long",
                    "new_side": "long",
                    "old_size_usd": 100,
                    "new_size_usd": 200,
                    "change_pct": 100,
                    "side": "long",
                    "detected_at": "now",
                }
            ],
        }
    )
    assert out["signals"][0]["asset"] == "BTC"


def test_unknown_action():
    assert "valid_actions" in _tool().handle({"action": "bogus"})


def test_main_invalid_json(capsys):
    rc = _tool().main(stream_in=type("S", (), {"read": lambda self: "{"})(), stream_out=__import__("sys").stdout)
    assert rc == 2
    assert "invalid JSON" in capsys.readouterr().out


def test_main_requires_object(capsys):
    rc = _tool().main(stream_in=type("S", (), {"read": lambda self: "[]"})(), stream_out=__import__("sys").stdout)
    assert rc == 2
    assert "JSON object" in capsys.readouterr().out


def test_main_success(capsys):
    rc = _tool().main(stream_in=type("S", (), {"read": lambda self: '{"action":"status"}'})(), stream_out=__import__("sys").stdout)
    assert rc == 0
    assert '"public_data_only": true' in capsys.readouterr().out


def test_tool_exports_version():
    assert _tool().VERSION == "0.1.0"


def test_actions_tuple_contains_expected():
    assert "leaderboard" in _tool().VALID_ACTIONS
