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
