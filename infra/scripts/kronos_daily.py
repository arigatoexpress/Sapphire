#!/usr/bin/env python3
"""Kronos daily prediction runner — LaunchAgent script.

Runs every morning at 7 AM CT. Generates Kronos-base candlestick forecasts
for the watchlist and writes results to data/intelligence/YYYY-MM-DD/predictions.json.
Also sends a Telegram summary via the notify tool.

Watchlist: BTC-USD, ETH-USD, SOL-USD, SPY, TSLA
"""

from __future__ import annotations

import argparse
import contextlib
import json
import os
import subprocess
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path

KRONOS_PYTHON = Path.home() / "Code" / "Kronos" / ".venv" / "bin" / "python3"
SYSTEM_PYTHON = Path("/usr/local/bin/python3")

WATCHLIST = ["BTC-USD", "ETH-USD", "SOL-USD", "SPY", "TSLA", "ONDO-USD", "ASTER-USD", "LIT-USD"]
PREDICT_BARS = 24
LOOKBACK_BARS = 200
INTERVAL = "1h"


def _python() -> str:
    return str(KRONOS_PYTHON) if KRONOS_PYTHON.exists() else str(SYSTEM_PYTHON)


def _sapphire_root() -> Path:
    return Path(os.environ.get("SAPPHIRE_ROOT", Path.home() / "Code" / "Sapphire"))


def _kronos_tool(root: Path) -> Path:
    return root / "plugins" / "claw-sapphire" / "tools" / "predict_kronos.py"


def _notify_tool(root: Path) -> Path:
    return root / "plugins" / "claw-sapphire" / "tools" / "notify.py"


def _env_flag(name: str, *, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _watchlist(raw: str | None = None) -> list[str]:
    if not raw:
        return WATCHLIST
    symbols = [symbol.strip().upper() for symbol in raw.split(",") if symbol.strip()]
    return symbols or WATCHLIST


def _output_dir(root: Path, *, dry_run: bool) -> Path:
    today = datetime.now(UTC).strftime("%Y-%m-%d")
    configured = os.environ.get("SAPPHIRE_KRONOS_OUTPUT_DIR")
    if configured:
        return Path(configured)
    if dry_run:
        return Path(tempfile.gettempdir()) / "sapphire-kronos-dry-run" / today
    return root / "data" / "intelligence" / today


def run_prediction(symbol: str, *, dry_run: bool = False, root: Path | None = None) -> dict:
    root = root or _sapphire_root()
    payload = json.dumps(
        {
            "action": "predict",
            "symbol": symbol,
            "lookback_bars": LOOKBACK_BARS,
            "predict_bars": PREDICT_BARS,
            "interval": INTERVAL,
            "save_snapshot": not dry_run,
        }
    )
    env = {
        "PYTHONPATH": str(Path.home() / "Code" / "Kronos"),
        "HOME": str(Path.home()),
        "PATH": "/usr/local/bin:/usr/bin:/bin",
    }
    try:
        result = subprocess.run(
            [_python(), str(_kronos_tool(root))],
            input=payload,
            capture_output=True,
            text=True,
            timeout=120,
            env=env,
        )
        if result.returncode != 0:
            return {"error": result.stderr[-300:] if result.stderr else "non-zero exit"}
        return json.loads(result.stdout)
    except subprocess.TimeoutExpired:
        return {"error": "timeout after 120s"}
    except Exception as e:
        return {"error": str(e)}


def send_telegram(message: str, *, root: Path | None = None, enabled: bool = True) -> bool:
    if not enabled:
        print("Telegram skipped.")
        return False

    root = root or _sapphire_root()
    with contextlib.suppress(Exception):
        subprocess.run(
            [str(SYSTEM_PYTHON), str(_notify_tool(root)), message, "--priority", "p2"],
            timeout=15,
            capture_output=True,
        )
        return True
    return False


def build_summary(results: dict[str, dict]) -> str:
    lines = [
        "📊 *Kronos Daily Predictions* — " + datetime.now().strftime("%Y-%m-%d %H:%M") + " CT\n"
    ]
    for sym, r in results.items():
        if "error" in r:
            lines.append(f"• {sym}: ❌ {r['error'][:60]}")
            continue
        dir_ = r.get("direction", "neutral")
        conf = r.get("confidence", 0)
        price = r.get("current_price", 0)
        preds = r.get("predictions", [])
        target = preds[-1]["close"] if preds else price
        pct = ((target - price) / price * 100) if price else 0
        icon = "🟢" if dir_ == "bullish" else ("🔴" if dir_ == "bearish" else "⬜")
        sign = "+" if pct >= 0 else ""
        lines.append(
            f"{icon} *{sym}*: {dir_.upper()} {conf * 100:.0f}% conf · "
            f"${price:,.0f} → ${target:,.0f} ({sign}{pct:.1f}%)"
        )
    lines.append(f"\n_Model: Kronos-base 102M · {PREDICT_BARS}h horizon_")
    return "\n".join(lines)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the Sapphire Kronos daily prediction job")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="run predictions without Telegram or per-symbol intelligence snapshot writes",
    )
    parser.add_argument(
        "--no-telegram",
        action="store_true",
        help="suppress the Telegram summary while keeping normal output behavior",
    )
    parser.add_argument(
        "--watchlist",
        default=os.environ.get("SAPPHIRE_KRONOS_WATCHLIST"),
        help="comma-separated symbol list for targeted smoke tests",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    dry_run = args.dry_run or _env_flag("SAPPHIRE_KRONOS_DRY_RUN")
    notify_enabled = (
        not dry_run and not args.no_telegram and _env_flag("SAPPHIRE_KRONOS_NOTIFY", default=True)
    )
    root = _sapphire_root()
    watchlist = _watchlist(args.watchlist)

    print(f"[{datetime.now().isoformat()}] Kronos daily run starting", flush=True)
    if dry_run:
        print("  Dry-run mode: Telegram disabled; per-symbol snapshots disabled.", flush=True)
    results: dict[str, dict] = {}

    for sym in watchlist:
        print(f"  Predicting {sym}...", end=" ", flush=True)
        r = run_prediction(sym, dry_run=dry_run, root=root)
        results[sym] = r
        if "error" in r:
            print(f"ERROR: {r['error'][:80]}")
        else:
            print(f"OK ({r.get('direction', '?')} {r.get('confidence', 0) * 100:.0f}%)")

    # Write aggregate snapshot
    out_dir = _output_dir(root, dry_run=dry_run)
    out_dir.mkdir(parents=True, exist_ok=True)
    pred_file = out_dir / "predictions.json"

    snapshot = {
        "generated_at": datetime.now(UTC).isoformat(),
        "source": "kronos-daily LaunchAgent" + (" dry-run" if dry_run else ""),
        "dry_run": dry_run,
        "watchlist": watchlist,
        "predictions": {sym: r for sym, r in results.items() if "error" not in r},
        "errors": {sym: r["error"] for sym, r in results.items() if "error" in r},
    }
    pred_file.write_text(json.dumps(snapshot, indent=2))
    print(f"Saved: {pred_file}")

    # Send Telegram
    summary = build_summary(results)
    if send_telegram(summary, root=root, enabled=notify_enabled):
        print("Telegram sent.")

    ok_count = sum(1 for r in results.values() if "error" not in r)
    print(f"[{datetime.now().isoformat()}] Done: {ok_count}/{len(watchlist)} symbols OK")
    return 0 if ok_count > 0 else 1


if __name__ == "__main__":
    sys.exit(main())
