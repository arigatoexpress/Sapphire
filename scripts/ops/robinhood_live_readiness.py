#!/usr/bin/env python3
"""Robinhood Crypto real-funds readiness report.

By default this helper performs no Robinhood network calls, reads no secret
values, and cannot submit orders. Pass ``--live-read-only`` to load Robinhood
credentials in-process and call read-only account, product, quote, and estimated
price endpoints. Even in live-read-only mode, it cannot submit, cancel, replace,
or sign an order body.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from lib.trading.strategy_lab import (  # noqa: E402
    ROBINHOOD_AUTH_ENV_VARS,
    ROBINHOOD_AUTH_FILE_NAMES,
    build_order_drafts,
    build_robinhood_real_funds_readiness,
)


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    report = collect_report(
        symbol=args.symbol,
        action=args.action,
        notional_usd=args.notional_usd,
        live_read_only=args.live_read_only,
        max_spread_bps=args.max_spread_bps,
    )
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print(render_markdown(report))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--symbol", default="BTC", help="Draft symbol, e.g. BTC or BTCUSDT.")
    parser.add_argument("--action", default="buy", choices=["buy", "sell", "close", "hold"])
    parser.add_argument("--notional-usd", type=float, default=5.0)
    parser.add_argument(
        "--live-read-only",
        action="store_true",
        help="Load credentials and perform read-only Robinhood API readiness probes.",
    )
    parser.add_argument(
        "--max-spread-bps",
        type=float,
        default=150.0,
        help="Maximum inclusive bid/ask spread for manual-confirmation readiness.",
    )
    parser.add_argument("--json", action="store_true", help="Emit JSON instead of Markdown.")
    return parser


def collect_report(
    *,
    symbol: str,
    action: str,
    notional_usd: float,
    live_read_only: bool = False,
    max_spread_bps: float = 150.0,
) -> dict[str, Any]:
    configured = credential_presence()
    readiness = build_robinhood_real_funds_readiness(configured=configured["configured"])
    drafts = build_order_drafts(
        symbol,
        action,
        notional_usd=notional_usd,
        strategy="robinhood_live_readiness",
    )
    robinhood_draft = next(
        (draft for draft in drafts if draft["venue"] == "robinhood_crypto"), None
    )
    payload = robinhood_draft.get("payload", {}) if robinhood_draft else {}
    robinhood_symbol = str(payload.get("symbol") or "")
    live_readiness = (
        collect_live_read_only(
            symbol=robinhood_symbol,
            notional_usd=notional_usd,
            max_spread_bps=max_spread_bps,
        )
        if live_read_only
        else {
            "performed": False,
            "reason": "pass --live-read-only to run read-only Robinhood API probes",
            "secret_values_loaded": False,
            "secret_values_printed": False,
        }
    )

    if robinhood_draft is None:
        verdict = "BLOCKED_NO_ROBINHOOD_SYMBOL"
    elif live_read_only and live_readiness.get("ready_for_manual_confirmation") is True:
        verdict = "READY_FOR_MANUAL_CONFIRMATION"
    elif live_read_only:
        verdict = "BLOCKED_LIVE_READINESS_GATES"
    else:
        verdict = "BLOCKED_PENDING_MANUAL_CONFIRMATION"

    return {
        "schema_version": 1,
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "network_calls_performed": bool(live_readiness.get("performed")),
        "secret_values_read": bool(live_readiness.get("secret_values_loaded")),
        "secret_values_printed": False,
        "credential_presence": configured,
        "verdict": verdict,
        "readiness": readiness,
        "order_draft": robinhood_draft,
        "live_read_only": live_readiness,
    }


def credential_presence() -> dict[str, Any]:
    env = {name: bool(os.getenv(name)) for name in ROBINHOOD_AUTH_ENV_VARS}
    base = Path.home() / ".config" / "sapphire-secrets"
    files: dict[str, bool] = {}
    for name in ROBINHOOD_AUTH_FILE_NAMES:
        try:
            path = base / name
            files[name] = path.exists() and path.stat().st_size > 0
        except OSError:
            files[name] = False
    return {
        "configured": all(env.values()) or all(files.values()),
        "env": env,
        "files": files,
        "values_redacted": True,
    }


def collect_live_read_only(
    *,
    symbol: str,
    notional_usd: float,
    max_spread_bps: float,
) -> dict[str, Any]:
    if not symbol:
        return {
            "performed": False,
            "ready_for_manual_confirmation": False,
            "reason": "no Robinhood Crypto symbol in order draft",
            "secret_values_loaded": False,
            "secret_values_printed": False,
        }

    reader = _reader_class()()
    if not reader.is_configured():
        return {
            "performed": False,
            "ready_for_manual_confirmation": False,
            "reason": "Robinhood credentials are not configured",
            "secret_values_loaded": False,
            "secret_values_printed": False,
        }

    errors: list[str] = []
    account = _redact_account(reader.get_account())
    quote = _empty_quote(symbol)
    trading_pair = {"symbol": symbol, "returned": False, "status": None}
    estimated_price = {"available": False}

    try:
        quote_rows = reader._get_results(
            "/api/v2/crypto/marketdata/best_bid_ask/",
            params={"symbol": [symbol]},
        )
        quote = _summarize_quote(symbol, quote_rows[0] if quote_rows else {})
    except Exception as exc:
        errors.append(f"best_bid_ask: {type(exc).__name__}: {exc}")

    try:
        pair_rows = reader._get_results(
            "/api/v2/crypto/trading/trading_pairs/",
            params={"symbol": [symbol]},
        )
        trading_pair = _summarize_trading_pair(symbol, pair_rows[0] if pair_rows else {})
    except Exception as exc:
        errors.append(f"trading_pairs: {type(exc).__name__}: {exc}")

    if quote.get("ask") and quote["ask"] > 0:
        quantity = max(notional_usd, 0.0) / quote["ask"]
        try:
            path = "/api/v2/crypto/trading/estimated_price/" + _encode_query(
                {
                    "symbol": symbol,
                    "side": "ask",
                    "quantity": f"{quantity:.12f}".rstrip("0").rstrip("."),
                }
            )
            estimated_price = _summarize_estimated_price(reader._request_json("GET", path))
        except Exception as exc:
            errors.append(f"estimated_price: {type(exc).__name__}: {exc}")

    gates = {
        "account_loaded": account.get("source") == "robinhood",
        "account_active": str(account.get("status") or "").lower() == "active",
        "account_api_tradable": account.get("is_api_tradable") is True,
        "buying_power_sufficient_for_requested_notional": (
            _safe_float(account.get("buying_power")) or 0.0
        )
        >= max(0.0, notional_usd),
        "quote_available": quote.get("price") is not None,
        "spread_available": quote.get("spread_bps") is not None,
        "spread_within_threshold": (
            quote.get("spread_bps") is not None and quote["spread_bps"] <= max_spread_bps
        ),
        "trading_pair_returned": trading_pair.get("returned") is True,
        "estimated_price_available": estimated_price.get("available") is True,
        "no_probe_errors": not errors,
    }
    return {
        "performed": True,
        "ready_for_manual_confirmation": all(gates.values()),
        "secret_values_loaded": True,
        "secret_values_printed": False,
        "account": account,
        "quote": quote,
        "trading_pair": trading_pair,
        "estimated_price": estimated_price,
        "gates": gates,
        "max_spread_bps": max_spread_bps,
        "errors": errors,
    }


def _reader_class():
    from lib.portfolio.robinhood import RobinhoodReader

    return RobinhoodReader


def _encode_query(params: dict[str, Any]) -> str:
    from lib.portfolio.robinhood import _encode_query as encode_query

    return encode_query(params)


def _safe_float(value: Any) -> float | None:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _redact_account(account: dict[str, Any]) -> dict[str, Any]:
    redacted = dict(account)
    account_number = str(redacted.pop("account_number", "") or "")
    redacted["account_number_masked"] = _mask_identifier(account_number)
    return redacted


def _mask_identifier(value: str) -> str:
    if not value:
        return ""
    if len(value) <= 8:
        return "*" * len(value)
    return f"{value[:4]}...{value[-4:]}"


def _empty_quote(symbol: str) -> dict[str, Any]:
    return {
        "symbol": symbol,
        "price": None,
        "bid": None,
        "ask": None,
        "spread_bps": None,
        "timestamp": None,
    }


def _summarize_quote(symbol: str, row: dict[str, Any]) -> dict[str, Any]:
    bid = _first_float(row, "bid_inclusive_of_sell_spread", "bid")
    ask = _first_float(row, "ask_inclusive_of_buy_spread", "ask")
    price = _safe_float(row.get("price"))
    if price is None and bid is not None and ask is not None:
        price = (bid + ask) / 2.0
    elif price is None:
        price = bid if bid is not None else ask
    spread_bps = None
    bid_ask_crossed = None
    if bid is not None and ask is not None and price and price > 0:
        bid_ask_crossed = ask < bid
        spread_bps = round(abs(ask - bid) / price * 10_000, 2)
    return {
        "symbol": str(row.get("symbol") or symbol),
        "price": price,
        "bid": bid,
        "ask": ask,
        "spread_bps": spread_bps,
        "bid_ask_crossed": bid_ask_crossed,
        "timestamp": row.get("timestamp"),
    }


def _summarize_trading_pair(symbol: str, row: dict[str, Any]) -> dict[str, Any]:
    status = row.get("status") or row.get("state") or row.get("tradability")
    return {
        "symbol": str(row.get("symbol") or symbol),
        "returned": bool(row),
        "status": status,
        "asset_code": row.get("asset_code"),
        "quote_code": row.get("quote_code"),
    }


def _summarize_estimated_price(payload: Any) -> dict[str, Any]:
    row: dict[str, Any]
    if (
        isinstance(payload, dict)
        and isinstance(payload.get("results"), list)
        and payload["results"]
    ):
        row = payload["results"][0] if isinstance(payload["results"][0], dict) else {}
    elif isinstance(payload, dict):
        row = payload
    else:
        row = {}

    return {
        "available": bool(row),
        "symbol": row.get("symbol"),
        "side": row.get("side"),
        "price": _first_float(row, "price", "estimated_price", "ask", "bid"),
        "quantity": _safe_float(row.get("quantity")),
        "estimated_fee": _safe_float(row.get("est_fee")),
        "estimated_total_cost": _safe_float(row.get("est_total_cost")),
        "timestamp": row.get("timestamp"),
        "fields_returned": sorted(str(key) for key in row)[:20],
    }


def _first_float(row: dict[str, Any], *keys: str) -> float | None:
    for key in keys:
        value = _safe_float(row.get(key))
        if value is not None:
            return value
    return None


def render_markdown(report: dict[str, Any]) -> str:
    readiness = report["readiness"]
    draft = report.get("order_draft") or {}
    payload = draft.get("payload") or {}
    caps = payload.get("live_test_caps") or readiness["crypto"]
    live = report.get("live_read_only") or {}
    blockers = "\n".join(f"- {item}" for item in readiness["submit_blockers"])
    gates = "\n".join(f"- {item}" for item in readiness["promotion_gates"])
    live_gates = "\n".join(
        f"- {name}: `{value}`" for name, value in (live.get("gates") or {}).items()
    )
    live_errors = "\n".join(f"- {item}" for item in live.get("errors") or [])
    return "\n".join(
        [
            "# Robinhood Live Readiness",
            "",
            f"- Verdict: `{report['verdict']}`",
            f"- Network calls performed: `{report['network_calls_performed']}`",
            f"- Secret values read: `{report['secret_values_read']}`",
            f"- Secret values printed: `{report['secret_values_printed']}`",
            f"- Credentials configured: `{report['credential_presence']['configured']}`",
            f"- Draft symbol: `{payload.get('symbol', 'unavailable')}`",
            f"- Draft side: `{payload.get('side', 'unavailable')}`",
            f"- First-order cap: `${caps.get('first_order_max_notional_usd')}`",
            f"- Live read-only ready: `{live.get('ready_for_manual_confirmation', False)}`",
            "",
            "## Submit Blockers",
            blockers,
            "",
            "## Live Gates",
            live_gates or "- not run",
            "",
            "## Live Errors",
            live_errors or "- none",
            "",
            "## Promotion Gates",
            gates,
        ]
    )


if __name__ == "__main__":
    raise SystemExit(main())
