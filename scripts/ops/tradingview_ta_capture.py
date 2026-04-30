#!/usr/bin/env python3
"""Capture TradingView TA artifacts for Sapphire.

Modes:
  sweep   Fast single-timeframe capture across N top-ranked symbols.
  deep    Multi-timeframe deep capture for one symbol with indicator stack.
  probe   Read-only snapshot of current TradingView state.

Safety:
  All mutations require SAPPHIRE_TV_MUTATION_ENABLED=1.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from lib.trading.pine_templates import (
    list_generated,
    render_sapphire_watch_indicator,
    write_template,
)
from lib.trading.tradingview_orchestrator import TradingViewOrchestrator
from lib.trading.tradingview_ta_machine import build_tradingview_ta_machine


def _write_json(path: str | None, data: Any) -> str | None:
    if not path:
        return None
    target = Path(path).expanduser()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")
    return str(target)


def cmd_probe(args: argparse.Namespace) -> int:
    orch = TradingViewOrchestrator(tv_bin=args.tv_bin)
    results = {
        "state": orch.probe_state(),
        "quote": orch.probe_quote(),
        "ohlcv": orch.probe_ohlcv(),
        "values": orch.probe_values(),
        "info": orch.probe_info(),
    }
    out = {"status": "ok", "results": results}
    _write_json(args.out, out)
    print(json.dumps(out, indent=2, sort_keys=True))
    return 0


def cmd_sweep(args: argparse.Namespace) -> int:
    plan = build_tradingview_ta_machine(fetch_live=not args.offline, limit=args.limit)
    symbols = plan["watchlist"]["symbols"][: args.limit]
    orch = TradingViewOrchestrator(
        tv_bin=args.tv_bin,
        mutation_enabled=args.mutate,
    )
    manifest = orch.capture_sweep(
        symbols,
        session_id=args.session_id,
        primary_timeframe=args.timeframe,
    )
    _write_json(args.out, manifest)
    summary = {
        "status": "ok",
        "mode": "sweep",
        "session_id": manifest["session_id"],
        "symbol_count": len(manifest["symbols"]),
        "mutation_enabled": manifest["mutation_enabled"],
        "manifest_path": manifest.get("manifest_path"),
        "symbols": [
            {
                "symbol": s["symbol"],
                "tradingview_symbol": s["tradingview_symbol"],
                "artifacts_ok": sum(1 for a in s["artifacts"] if a["ok"]),
            }
            for s in manifest["symbols"]
        ],
    }
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


def cmd_deep(args: argparse.Namespace) -> int:
    orch = TradingViewOrchestrator(
        tv_bin=args.tv_bin,
        mutation_enabled=args.mutate,
    )
    manifest = orch.capture_symbol_deep(
        symbol=args.symbol,
        tradingview_symbol=args.tv_symbol or args.symbol,
        timeframes=args.timeframes.split(",") if args.timeframes else None,
        session_id=args.session_id,
    )
    _write_json(args.out, manifest)
    summary = {
        "status": "ok",
        "mode": "deep",
        "session_id": manifest["session_id"],
        "symbol": manifest["symbol"],
        "timeframe_count": len(manifest["timeframes"]),
        "mutation_enabled": manifest["mutation_enabled"],
        "manifest_path": manifest.get("manifest_path"),
    }
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


def cmd_pine_list(args: argparse.Namespace) -> int:
    orch = TradingViewOrchestrator(tv_bin=args.tv_bin)
    out = {
        "status": "ok",
        "tv_account_scripts": orch.pine_list(),
        "generated_local": list_generated(),
    }
    _write_json(args.out, out)
    print(json.dumps(out, indent=2, sort_keys=True))
    return 0


def cmd_pine_validate(args: argparse.Namespace) -> int:
    orch = TradingViewOrchestrator(tv_bin=args.tv_bin)
    result = orch.pine_validate_file(args.path)
    out = {"status": "ok" if result["ok"] else "fail", "result": result}
    _write_json(args.out, out)
    print(json.dumps(out, indent=2, sort_keys=True))
    return 0 if result["ok"] else 2


def cmd_pine_generate(args: argparse.Namespace) -> int:
    pine = render_sapphire_watch_indicator(args.symbol)
    name = args.name or f"Sapphire_Watch_{args.symbol}"
    written = write_template(
        name,
        pine,
        metadata={
            "kind": "sapphire_watch_indicator",
            "tradingview_symbol": args.symbol,
        },
    )
    if args.validate:
        orch = TradingViewOrchestrator(tv_bin=args.tv_bin)
        validation = orch.pine_validate_file(written["pine_path"])
        written["validation"] = validation
    out: dict[str, Any] = {"status": "ok", "generated": written}
    _write_json(args.out, out)
    print(json.dumps(out, indent=2, sort_keys=True))
    return 0


def cmd_pine_generate_batch(args: argparse.Namespace) -> int:
    plan = build_tradingview_ta_machine(fetch_live=not args.offline, limit=args.limit)
    universe = plan["watchlist"]["symbols"][: args.limit]
    orch = TradingViewOrchestrator(tv_bin=args.tv_bin) if args.validate else None
    generated: list[dict[str, Any]] = []
    for row in universe:
        tv_symbol = str(row.get("tradingview_symbol") or row.get("symbol") or "").strip()
        if not tv_symbol:
            continue
        pine = render_sapphire_watch_indicator(tv_symbol)
        written = write_template(
            f"Sapphire_Watch_{tv_symbol}",
            pine,
            metadata={
                "kind": "sapphire_watch_indicator",
                "tradingview_symbol": tv_symbol,
                "rank": row.get("rank"),
                "base_symbol": row.get("symbol"),
            },
        )
        if orch is not None:
            validation = orch.pine_validate_file(written["pine_path"])
            written["validation_ok"] = validation["ok"]
            written["validation"] = validation
        generated.append(written)
    out = {
        "status": "ok",
        "mode": "pine-generate-batch",
        "count": len(generated),
        "validate": bool(args.validate),
        "all_valid": all(g.get("validation_ok", True) for g in generated),
        "generated": [
            {
                "name": g["name"],
                "slug": g["slug"],
                "pine_path": g["pine_path"],
                "validation_ok": g.get("validation_ok"),
            }
            for g in generated
        ],
    }
    _write_json(args.out, out)
    print(json.dumps(out, indent=2, sort_keys=True))
    return 0 if out["all_valid"] else 2


def cmd_pine_load(args: argparse.Namespace) -> int:
    orch = TradingViewOrchestrator(
        tv_bin=args.tv_bin,
        mutation_enabled=args.mutate,
    )
    set_res = orch.pine_set_from_file(args.path)
    compile_res: dict[str, Any] = {"mutated": False, "skipped": True}
    if args.compile:
        compile_res = orch.pine_compile()
    errors = orch.pine_errors() if args.compile else {"ok": True, "skipped": True}
    out = {
        "status": "ok" if set_res.get("ok", False) or set_res.get("mutated") is False else "fail",
        "set": set_res,
        "compile": compile_res,
        "errors": errors,
    }
    _write_json(args.out, out)
    print(json.dumps(out, indent=2, sort_keys=True))
    return 0


def cmd_alerts_list(args: argparse.Namespace) -> int:
    orch = TradingViewOrchestrator(tv_bin=args.tv_bin)
    payload = orch.alerts_list()
    body = (payload.get("payload") or {}) if isinstance(payload, dict) else {}
    out = {
        "status": "ok" if payload.get("ok") else "fail",
        "alert_count": body.get("alert_count"),
        "result": payload,
    }
    _write_json(args.out, out)
    print(json.dumps(out, indent=2, sort_keys=True))
    return 0


def cmd_latest(args: argparse.Namespace) -> int:
    orch = TradingViewOrchestrator(tv_bin=args.tv_bin)
    manifest = orch.latest_manifest()
    sessions = orch.list_sessions(limit=args.limit)
    out = {
        "status": "ok",
        "latest_manifest": manifest,
        "recent_sessions": sessions,
    }
    _write_json(args.out, out)
    print(json.dumps(out, indent=2, sort_keys=True))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tv-bin", default="tv", help="tv CLI binary path")
    parser.add_argument("--out", help="Write JSON output to this path")
    parser.add_argument(
        "--mutate",
        action="store_true",
        help=f"Enable TradingView mutations (requires {os.environ.get('SAPPHIRE_TV_MUTATION_ENABLED', 'SAPPHIRE_TV_MUTATION_ENABLED')}=1)",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_probe = sub.add_parser("probe", help="Read-only snapshot of current TV state")
    p_probe.set_defaults(func=cmd_probe)

    p_sweep = sub.add_parser("sweep", help="Fast sweep across top symbols")
    p_sweep.add_argument("--offline", action="store_true", help="Skip live market fetches")
    p_sweep.add_argument("--limit", type=int, default=6, help="Max symbols")
    p_sweep.add_argument("--timeframe", default="60", help="Primary timeframe")
    p_sweep.add_argument("--session-id", help="Override session ID")
    p_sweep.set_defaults(func=cmd_sweep)

    p_deep = sub.add_parser("deep", help="Deep multi-timeframe capture for one symbol")
    p_deep.add_argument("symbol", help="Base symbol (e.g. ETH)")
    p_deep.add_argument("--tv-symbol", help="TradingView symbol (e.g. BINANCE:ETHUSDT)")
    p_deep.add_argument("--timeframes", default="15,60,240,D", help="Comma-separated timeframes")
    p_deep.add_argument("--session-id", help="Override session ID")
    p_deep.set_defaults(func=cmd_deep)

    p_latest = sub.add_parser("latest", help="Show latest captured session manifest")
    p_latest.add_argument("--limit", type=int, default=10, help="Recent sessions to list")
    p_latest.set_defaults(func=cmd_latest)

    p_pine_list = sub.add_parser("pine-list", help="List TV-saved + locally-generated Pine scripts")
    p_pine_list.set_defaults(func=cmd_pine_list)

    p_pine_validate = sub.add_parser(
        "pine-validate",
        help="Run analyze + server-side check on a Pine source file",
    )
    p_pine_validate.add_argument("path", help="Path to .pine source file")
    p_pine_validate.set_defaults(func=cmd_pine_validate)

    p_pine_generate = sub.add_parser(
        "pine-generate",
        help="Generate a Sapphire-aligned Pine script for a symbol",
    )
    p_pine_generate.add_argument("symbol", help="TradingView symbol (e.g. BINANCE:ETHUSDT)")
    p_pine_generate.add_argument("--name", help="Template name override")
    p_pine_generate.add_argument(
        "--validate",
        action="store_true",
        help="Run analyze + check on the generated file (no chart needed)",
    )
    p_pine_generate.set_defaults(func=cmd_pine_generate)

    p_pine_batch = sub.add_parser(
        "pine-generate-batch",
        help="Generate Sapphire Pine indicators for top-N market universe symbols",
    )
    p_pine_batch.add_argument("--offline", action="store_true", help="Skip live market fetches")
    p_pine_batch.add_argument("--limit", type=int, default=6, help="Max symbols")
    p_pine_batch.add_argument(
        "--validate",
        action="store_true",
        help="Run analyze + check on each generated file",
    )
    p_pine_batch.set_defaults(func=cmd_pine_generate_batch)

    p_pine_load = sub.add_parser(
        "pine-load",
        help="Push a Pine source file into the TV editor (mutation-gated)",
    )
    p_pine_load.add_argument("path", help="Path to .pine source file")
    p_pine_load.add_argument(
        "--compile",
        action="store_true",
        help="Compile after loading and report errors",
    )
    p_pine_load.set_defaults(func=cmd_pine_load)

    p_alerts_list = sub.add_parser("alerts-list", help="List active TradingView alerts")
    p_alerts_list.set_defaults(func=cmd_alerts_list)

    args = parser.parse_args(argv)

    if args.mutate and os.getenv("SAPPHIRE_TV_MUTATION_ENABLED") != "1":
        print(
            json.dumps(
                {
                    "status": "error",
                    "reason": "SAPPHIRE_TV_MUTATION_ENABLED must be 1 for --mutate",
                }
            ),
            file=sys.stderr,
        )
        return 1

    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
