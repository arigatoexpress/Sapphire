from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "ops" / "robinhood_manual_order.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("robinhood_manual_order", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules["robinhood_manual_order"] = module
    spec.loader.exec_module(module)
    return module


def _args(module, *extra: str):
    return module.build_parser().parse_args([*extra])


def _ready_report():
    return {
        "verdict": "READY_FOR_MANUAL_CONFIRMATION",
        "live_read_only": {
            "gates": {
                "account_loaded": True,
                "account_active": True,
                "account_api_tradable": True,
                "buying_power_sufficient_for_requested_notional": True,
                "quote_available": True,
                "spread_available": True,
                "spread_within_threshold": True,
                "trading_pair_returned": True,
                "estimated_price_available": True,
                "no_probe_errors": True,
            }
        },
    }


def test_dry_run_builds_limit_order_without_live_readiness(tmp_path, monkeypatch):
    module = _load_module()
    calls = []
    monkeypatch.setattr(
        module,
        "collect_readiness_report",
        lambda **kwargs: calls.append(kwargs) or {"verdict": "BLOCKED_PENDING_MANUAL_CONFIRMATION"},
    )
    args = _args(
        module,
        "--side",
        "buy",
        "--limit-price",
        "77000",
        "--quote-amount-usd",
        "5",
        "--audit-log",
        str(tmp_path / "audit.jsonl"),
    )

    report = module.build_or_execute(args)

    assert report["verdict"] == "DRY_RUN_READY"
    assert report["real_order_submitted"] is False
    assert report["body"]["client_order_id"] == "<uuid_v4_at_submit_time>"
    assert report["body"]["limit_order_config"]["quote_amount"] == "5.00"
    assert report["confirmation_token_required"] == "LIVE_ROBINHOOD_BUY_BTC-USD_5.00"
    assert calls[0]["live_read_only"] is False
    assert (tmp_path / "audit.jsonl").exists()


def test_execute_requires_exact_confirmation_token(monkeypatch):
    module = _load_module()
    monkeypatch.setattr(module, "collect_readiness_report", lambda **_kwargs: _ready_report())
    args = _args(
        module,
        "--side",
        "buy",
        "--limit-price",
        "77000",
        "--quote-amount-usd",
        "5",
        "--execute",
        "--confirm-token",
        "wrong",
    )

    try:
        module.build_or_execute(args)
    except module.ManualOrderError as exc:
        assert "confirmation token mismatch" in str(exc)
    else:
        raise AssertionError("expected ManualOrderError")


def test_notional_cap_blocks_large_order():
    module = _load_module()
    args = _args(
        module,
        "--side",
        "buy",
        "--limit-price",
        "77000",
        "--quote-amount-usd",
        "6",
        "--max-notional-usd",
        "5",
    )

    try:
        module.build_or_execute(args)
    except module.ManualOrderError as exc:
        assert "exceeds cap" in str(exc)
    else:
        raise AssertionError("expected ManualOrderError")


def test_execute_posts_v2_limit_order_with_fake_reader(tmp_path, monkeypatch):
    module = _load_module()
    captured = {}

    class FakeReader:
        def is_configured(self):
            return True

        def _get_account_number(self):
            return "ACCT-1"

        def _request_json(self, method, path, body=None):
            captured["method"] = method
            captured["path"] = path
            captured["body"] = body
            return {
                "id": "ORDER-1",
                "client_order_id": body["client_order_id"],
                "symbol": body["symbol"],
                "side": body["side"],
                "type": body["type"],
                "state": "open",
                "account_number": "ACCT-1",
            }

    monkeypatch.setattr(module, "collect_readiness_report", lambda **_kwargs: _ready_report())
    monkeypatch.setattr(module, "_reader_class", lambda: FakeReader)
    args = _args(
        module,
        "--side",
        "buy",
        "--limit-price",
        "77000",
        "--quote-amount-usd",
        "5",
        "--execute",
        "--confirm-token",
        "LIVE_ROBINHOOD_BUY_BTC-USD_5.00",
        "--audit-log",
        str(tmp_path / "audit.jsonl"),
    )

    report = module.build_or_execute(args)

    assert report["verdict"] == "SUBMITTED"
    assert report["real_order_submitted"] is True
    assert captured["method"] == "POST"
    assert captured["path"] == "/api/v2/crypto/trading/orders/?account_number=ACCT-1"
    assert captured["body"]["limit_order_config"]["quote_amount"] == "5.00"
    assert "account_number" not in report["submit_response"]
