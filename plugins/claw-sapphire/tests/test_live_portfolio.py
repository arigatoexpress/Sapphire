from __future__ import annotations

import importlib.util
import io
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

INTERNAL = ROOT / "plugins" / "claw-sapphire" / "tools" / "internal" / "live_portfolio.py"
spec = importlib.util.spec_from_file_location("live_portfolio_internal", INTERNAL)
assert spec is not None and spec.loader is not None
tool = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = tool
spec.loader.exec_module(tool)


def fill_payload() -> dict:
    trade = {
        "account": "Individual (...5966)",
        "symbol": "BTC",
        "type": "limit",
        "side": "buy",
        "date_filled": "2026-04-28T04:06:00Z",
        "filled_at": 76774.81,
        "amount_filled": 0.00006511,
        "fee": 0.04,
        "total_cost": 5.05,
    }
    trade["provenance"] = tool.provenance_for_operator_fill(trade)
    return trade


def test_status_action(tmp_path) -> None:
    out = tool.handle({"action": "status", "ledger_root": str(tmp_path)})
    assert out["ok"] is True
    assert out["live_api_calls"] == 0


def test_hash_account_action() -> None:
    out = tool.handle({"action": "hash-account", "account": "Individual (...5966)"})
    assert out["account_hash"].startswith("tenant_live_portfolio_")


def test_input_provenance_action() -> None:
    out = tool.handle({"action": "input-provenance", "trade": {"symbol": "BTC"}})
    assert out["ok"] is True
    assert out["provenance"]["generator"] == "live_portfolio.seed.operator_fill"


def test_seed_trade_non_persistent(tmp_path) -> None:
    out = tool.handle({"action": "seed-trade", "trade": fill_payload(), "ledger_root": str(tmp_path)})
    assert out["ok"] is True
    assert out["persisted"] is False


def test_seed_trade_persistent(tmp_path) -> None:
    out = tool.handle(
        {"action": "seed-trade", "trade": fill_payload(), "ledger_root": str(tmp_path), "persist": True}
    )
    assert out["ok"] is True
    assert out["persisted"] is True


def test_ledger_action(tmp_path) -> None:
    tool.handle({"action": "seed-trade", "trade": fill_payload(), "ledger_root": str(tmp_path), "persist": True})
    out = tool.handle({"action": "ledger", "ledger_root": str(tmp_path)})
    assert out["summary"]["trade_count"] == 1


def test_gate_status_action(tmp_path) -> None:
    out = tool.handle(
        {
            "action": "gate-status",
            "ledger_root": str(tmp_path),
            "returns": [0.01] * 14,
            "current_tier": 1,
            "now": "2026-04-30T00:00:00Z",
        }
    )
    assert out["ok"] is True
    assert out["status"]["current_tier"] == 1


def test_sortino_action() -> None:
    out = tool.handle({"action": "sortino", "returns": [0.01] * 14})
    assert out["sortino"]["value"] == "inf"


def test_forecast_action() -> None:
    out = tool.handle(
        {"action": "forecast-rung-completion", "tier_start": "2026-04-01T00:00:00Z"}
    )
    assert out["ok"] is True


def test_unknown_action() -> None:
    out = tool.handle({"action": "wat"})
    assert "error" in out


def test_main_invalid_json() -> None:
    buf = io.StringIO()
    rc = tool.main(stream_in=io.StringIO("{no"), stream_out=buf)
    assert rc == 2


def test_main_valid_json(tmp_path) -> None:
    buf = io.StringIO()
    rc = tool.main(
        stream_in=io.StringIO(json.dumps({"action": "status", "ledger_root": str(tmp_path)})),
        stream_out=buf,
    )
    assert rc == 0
    assert json.loads(buf.getvalue())["ok"] is True
