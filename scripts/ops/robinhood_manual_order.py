#!/usr/bin/env python3
"""Manual-only Robinhood Crypto live order executor.

Default mode is dry-run. Live execution requires all of:

- ``--execute``
- a typed confirmation token matching the exact order intent
- Robinhood live-read-only readiness gates passing immediately before submit
- the configured pilot caps

This script is intentionally not imported by dashboard, scheduler, Telegram, or
TradingView paths.
"""

from __future__ import annotations

import argparse
import json
import sys
import uuid
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
OPS_DIR = Path(__file__).resolve().parent
for path in (ROOT, OPS_DIR):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from robinhood_live_readiness import collect_report as collect_readiness_report  # noqa: E402

from lib.trading.strategy_lab import (  # noqa: E402
    ROBINHOOD_FIRST_REAL_FUNDS_TEST_MAX_USD,
    asset_spec,
)

DEFAULT_AUDIT_LOG = ROOT / "data" / "trading" / "robinhood_manual_orders.jsonl"


@dataclass(frozen=True)
class ManualOrderIntent:
    symbol: str
    side: str
    order_type: str
    limit_price: float
    quote_amount: float | None
    asset_quantity: float | None
    time_in_force: str
    max_notional_usd: float


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        report = build_or_execute(args)
    except ManualOrderError as exc:
        report = {
            "schema_version": 1,
            "generated_at": _now(),
            "mode": "execute" if args.execute else "dry_run",
            "verdict": "BLOCKED",
            "error": str(exc),
        }
        print(json.dumps(report, indent=2))
        return 20

    print(json.dumps(report, indent=2))
    return 0 if report["verdict"] in {"DRY_RUN_READY", "SUBMITTED"} else 20


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--symbol", default="BTC", help="Crypto symbol, e.g. BTC or BTC-USD.")
    parser.add_argument("--side", choices=["buy", "sell"], required=True)
    parser.add_argument("--limit-price", type=float, required=True)
    parser.add_argument("--quote-amount-usd", type=float, help="Required for buys.")
    parser.add_argument("--asset-quantity", type=float, help="Required for sells.")
    parser.add_argument("--time-in-force", default="gtc", choices=["gtc", "gfd", "gfw", "gfm"])
    parser.add_argument(
        "--max-notional-usd", type=float, default=ROBINHOOD_FIRST_REAL_FUNDS_TEST_MAX_USD
    )
    parser.add_argument("--audit-log", type=Path, default=DEFAULT_AUDIT_LOG)
    parser.add_argument("--execute", action="store_true", help="Place the real Robinhood order.")
    parser.add_argument(
        "--confirm-token",
        default="",
        help="Required with --execute; dry-run output prints the exact expected token.",
    )
    parser.add_argument(
        "--max-spread-bps",
        type=float,
        default=150.0,
        help="Maximum spread accepted by the live-read-only preflight.",
    )
    return parser


def build_or_execute(args: argparse.Namespace) -> dict[str, Any]:
    intent = build_intent(args)
    validate_intent(intent)
    token = expected_confirmation_token(intent)
    body = build_order_body(intent, client_order_id="<uuid_v4_at_submit_time>")
    readiness = collect_readiness_report(
        symbol=intent.symbol,
        action=intent.side,
        notional_usd=estimated_notional(intent),
        live_read_only=args.execute,
        max_spread_bps=args.max_spread_bps,
    )

    if not args.execute:
        report = base_report(intent, body, token, readiness, verdict="DRY_RUN_READY")
        append_audit(args.audit_log, report)
        return report

    if args.confirm_token != token:
        raise ManualOrderError(f"confirmation token mismatch; expected {token}")
    if readiness.get("verdict") != "READY_FOR_MANUAL_CONFIRMATION":
        raise ManualOrderError("live-read-only readiness gates did not pass")

    response = submit_order(intent)
    report = base_report(
        intent,
        build_order_body(intent, client_order_id=response["client_order_id"]),
        token,
        readiness,
        verdict="SUBMITTED",
    )
    report["submit_response"] = response["submit_response"]
    append_audit(args.audit_log, report)
    return report


def build_intent(args: argparse.Namespace) -> ManualOrderIntent:
    symbol = asset_spec(args.symbol).robinhood_symbol or str(args.symbol).upper()
    return ManualOrderIntent(
        symbol=symbol,
        side=args.side,
        order_type="limit",
        limit_price=args.limit_price,
        quote_amount=args.quote_amount_usd,
        asset_quantity=args.asset_quantity,
        time_in_force=args.time_in_force,
        max_notional_usd=args.max_notional_usd,
    )


def validate_intent(intent: ManualOrderIntent) -> None:
    if intent.limit_price <= 0:
        raise ManualOrderError("limit price must be positive")
    if intent.max_notional_usd <= 0:
        raise ManualOrderError("max notional cap must be positive")

    notional = estimated_notional(intent)
    if notional <= 0:
        raise ManualOrderError("estimated notional must be positive")
    if notional > intent.max_notional_usd:
        raise ManualOrderError(
            f"estimated notional ${notional:.2f} exceeds cap ${intent.max_notional_usd:.2f}"
        )

    if intent.side == "buy":
        if intent.quote_amount is None or intent.quote_amount <= 0:
            raise ManualOrderError("buy limit orders require --quote-amount-usd")
        if intent.asset_quantity is not None:
            raise ManualOrderError("buy limit orders must not include --asset-quantity")
        return

    if intent.asset_quantity is None or intent.asset_quantity <= 0:
        raise ManualOrderError("sell limit orders require --asset-quantity")
    if intent.quote_amount is not None:
        raise ManualOrderError("sell limit orders must not include --quote-amount-usd")


def estimated_notional(intent: ManualOrderIntent) -> float:
    if intent.side == "buy":
        return float(intent.quote_amount or 0.0)
    return float(intent.asset_quantity or 0.0) * intent.limit_price


def build_order_body(intent: ManualOrderIntent, *, client_order_id: str) -> dict[str, Any]:
    config: dict[str, Any] = {
        "limit_price": f"{intent.limit_price:.2f}",
        "time_in_force": intent.time_in_force,
    }
    if intent.side == "buy":
        config["quote_amount"] = f"{intent.quote_amount:.2f}"
    else:
        config["asset_quantity"] = f"{intent.asset_quantity:.12f}".rstrip("0").rstrip(".")
    return {
        "client_order_id": client_order_id,
        "side": intent.side,
        "type": intent.order_type,
        "symbol": intent.symbol,
        "limit_order_config": config,
    }


def expected_confirmation_token(intent: ManualOrderIntent) -> str:
    notional = estimated_notional(intent)
    return f"LIVE_ROBINHOOD_{intent.side.upper()}_{intent.symbol}_{notional:.2f}"


def submit_order(intent: ManualOrderIntent) -> dict[str, Any]:
    reader = _reader_class()()
    if not reader.is_configured():
        raise ManualOrderError("Robinhood credentials are not configured")
    account_number = reader._get_account_number()
    if not account_number:
        raise ManualOrderError("Robinhood account number unavailable")

    client_order_id = str(uuid.uuid4())
    body = build_order_body(intent, client_order_id=client_order_id)
    path = f"/api/v2/crypto/trading/orders/?account_number={account_number}"
    response = reader._request_json("POST", path, body=body)
    return {
        "client_order_id": client_order_id,
        "submit_response": sanitize_submit_response(response),
    }


def sanitize_submit_response(response: Any) -> dict[str, Any]:
    if not isinstance(response, dict):
        return {"raw_type": type(response).__name__}
    allowed = {
        "id",
        "client_order_id",
        "symbol",
        "side",
        "type",
        "state",
        "created_at",
        "updated_at",
        "average_price",
        "filled_asset_quantity",
    }
    return {key: response.get(key) for key in sorted(allowed) if key in response}


def base_report(
    intent: ManualOrderIntent,
    body: dict[str, Any],
    confirmation_token: str,
    readiness: dict[str, Any],
    *,
    verdict: str,
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "generated_at": _now(),
        "mode": "execute" if verdict == "SUBMITTED" else "dry_run",
        "verdict": verdict,
        "real_order_submitted": verdict == "SUBMITTED",
        "intent": asdict(intent),
        "estimated_notional_usd": estimated_notional(intent),
        "confirmation_token_required": confirmation_token,
        "endpoint": "/api/v2/crypto/trading/orders/?account_number=<masked>",
        "body": body,
        "readiness_verdict": readiness.get("verdict"),
        "readiness_live_gates": (readiness.get("live_read_only") or {}).get("gates", {}),
        "safety": {
            "dry_run_default": True,
            "limit_orders_only": True,
            "requires_typed_confirmation": True,
            "dashboard_or_scheduler_path": False,
            "secret_values_printed": False,
        },
    }


def append_audit(path: Path, report: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(report, sort_keys=True) + "\n")


def _reader_class():
    from lib.portfolio.robinhood import RobinhoodReader

    return RobinhoodReader


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


class ManualOrderError(RuntimeError):
    pass


if __name__ == "__main__":
    raise SystemExit(main())
