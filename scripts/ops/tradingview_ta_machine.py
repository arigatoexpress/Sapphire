#!/usr/bin/env python3
"""Generate or optionally apply Sapphire's dynamic TradingView TA workbench plan."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from lib.trading.tradingview_ta_machine import build_tradingview_ta_machine


def _write_text(path: str | None, body: str) -> str | None:
    if not path:
        return None
    target = Path(path).expanduser()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(body, encoding="utf-8")
    return str(target)


def _run_apply(plan: dict[str, Any], *, tv_bin: str, max_symbols: int) -> dict[str, Any]:
    allowed = os.getenv("SAPPHIRE_TV_MUTATION_ENABLED") == "1"
    rows = plan.get("watchlist", {}).get("symbols", [])[:max_symbols]
    if not allowed:
        return {
            "applied": False,
            "reason": "SAPPHIRE_TV_MUTATION_ENABLED must be 1",
            "symbol_count": len(rows),
        }

    results = []
    for row in rows:
        symbol = str(row.get("tradingview_symbol") or "").strip()
        if not symbol:
            continue
        cmd = [tv_bin, "watchlist", "add", symbol]
        proc = subprocess.run(  # noqa: S603 - explicit operator-gated local CLI.
            cmd,
            cwd=ROOT,
            text=True,
            capture_output=True,
            timeout=20,
            check=False,
        )
        results.append(
            {
                "symbol": symbol,
                "returncode": proc.returncode,
                "stdout": proc.stdout[-500:],
                "stderr": proc.stderr[-500:],
            }
        )
    return {
        "applied": True,
        "command": f"{tv_bin} watchlist add <symbol>",
        "symbol_count": len(results),
        "results": results,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--offline", action="store_true", help="Skip live market fetches")
    parser.add_argument("--limit", type=int, default=18, help="Max watchlist symbols")
    parser.add_argument("--json-out", help="Write the full plan JSON to this path")
    parser.add_argument("--watchlist-out", help="Write TradingView import TXT to this path")
    parser.add_argument("--print-commands", action="store_true", help="Print top work-order commands")
    parser.add_argument(
        "--apply-watchlist",
        action="store_true",
        help="Add symbols to the actual TradingView watchlist through the local tv CLI",
    )
    parser.add_argument("--tv-bin", default="tv", help="TradingView CLI binary")
    parser.add_argument("--apply-max", type=int, default=18, help="Max symbols to apply")
    args = parser.parse_args(argv)

    plan = build_tradingview_ta_machine(fetch_live=not args.offline, limit=args.limit)
    written = {
        "json": _write_text(args.json_out, json.dumps(plan, indent=2, sort_keys=True)),
        "watchlist": _write_text(args.watchlist_out, plan["watchlist"]["symbols_txt"] + "\n"),
    }
    apply_result = None
    if args.apply_watchlist:
        apply_result = _run_apply(plan, tv_bin=args.tv_bin, max_symbols=max(1, args.apply_max))

    summary = {
        "status": "ok",
        "mode": plan["mode"],
        "watchlist_name": plan["watchlist_name"],
        "symbol_count": plan["watchlist"]["symbol_count"],
        "watchlist_txt": plan["watchlist"]["symbols_txt"],
        "written": written,
        "apply": apply_result,
        "safety": plan["safety"],
    }
    print(json.dumps(summary, indent=2, sort_keys=True))
    if args.print_commands:
        for order in plan["work_orders"][:4]:
            print(f"\n# {order['id']} {order['tradingview_symbol']}")
            for cmd in order["operator_gated_mutation_commands"]:
                print(cmd)
            for cmd in order["read_only_readback_commands"]:
                print(cmd)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
