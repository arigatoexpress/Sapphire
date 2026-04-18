#!/usr/bin/env python3
"""Kronos daily prediction runner — LaunchAgent script.

Runs every morning at 7 AM CT. Generates Kronos-base candlestick forecasts
for the watchlist and writes results to data/intelligence/YYYY-MM-DD/predictions.json.
Also sends a Telegram summary via the notify tool.

Watchlist: BTC-USD, ETH-USD, SOL-USD, SPY, TSLA
"""

from __future__ import annotations

import contextlib
import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

SAPPHIRE = Path.home() / "Code" / "Sapphire"
KRONOS_TOOL = SAPPHIRE / "plugins" / "claw-sapphire" / "tools" / "predict_kronos.py"
NOTIFY_TOOL = SAPPHIRE / "plugins" / "claw-sapphire" / "tools" / "notify.py"
KRONOS_PYTHON = Path.home() / "Code" / "Kronos" / ".venv" / "bin" / "python3"
SYSTEM_PYTHON = Path("/usr/local/bin/python3")

WATCHLIST = ["BTC-USD", "ETH-USD", "SOL-USD", "SPY", "TSLA", "ONDO-USD", "ASTER-USD", "LIT-USD"]
PREDICT_BARS = 24
LOOKBACK_BARS = 200
INTERVAL = "1h"


def _python() -> str:
    return str(KRONOS_PYTHON) if KRONOS_PYTHON.exists() else str(SYSTEM_PYTHON)


def run_prediction(symbol: str) -> dict:
    payload = json.dumps({
        "action": "predict",
        "symbol": symbol,
        "lookback_bars": LOOKBACK_BARS,
        "predict_bars": PREDICT_BARS,
        "interval": INTERVAL,
    })
    env = {
        "PYTHONPATH": str(Path.home() / "Code" / "Kronos"),
        "HOME": str(Path.home()),
        "PATH": "/usr/local/bin:/usr/bin:/bin",
    }
    try:
        result = subprocess.run(
            [_python(), str(KRONOS_TOOL)],
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


def send_telegram(message: str) -> None:
    with contextlib.suppress(Exception):
        subprocess.run(
            [str(SYSTEM_PYTHON), str(NOTIFY_TOOL), message, "--priority", "p2"],
            timeout=15,
            capture_output=True,
        )


def build_summary(results: dict[str, dict]) -> str:
    lines = ["📊 *Kronos Daily Predictions* — " + datetime.now().strftime("%Y-%m-%d %H:%M") + " CT\n"]
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
            f"{icon} *{sym}*: {dir_.upper()} {conf*100:.0f}% conf · "
            f"${price:,.0f} → ${target:,.0f} ({sign}{pct:.1f}%)"
        )
    lines.append(f"\n_Model: Kronos-base 102M · {PREDICT_BARS}h horizon_")
    return "\n".join(lines)


def main() -> int:
    print(f"[{datetime.now().isoformat()}] Kronos daily run starting", flush=True)
    results: dict[str, dict] = {}

    for sym in WATCHLIST:
        print(f"  Predicting {sym}...", end=" ", flush=True)
        r = run_prediction(sym)
        results[sym] = r
        if "error" in r:
            print(f"ERROR: {r['error'][:80]}")
        else:
            print(f"OK ({r.get('direction','?')} {r.get('confidence',0)*100:.0f}%)")

    # Write aggregate snapshot
    today = datetime.now(UTC).strftime("%Y-%m-%d")
    out_dir = SAPPHIRE / "data" / "intelligence" / today
    out_dir.mkdir(parents=True, exist_ok=True)
    pred_file = out_dir / "predictions.json"

    snapshot = {
        "generated_at": datetime.now(UTC).isoformat(),
        "source": "kronos-daily LaunchAgent",
        "watchlist": WATCHLIST,
        "predictions": {
            sym: r for sym, r in results.items() if "error" not in r
        },
        "errors": {
            sym: r["error"] for sym, r in results.items() if "error" in r
        },
    }
    pred_file.write_text(json.dumps(snapshot, indent=2))
    print(f"Saved: {pred_file}")

    # Send Telegram
    summary = build_summary(results)
    send_telegram(summary)
    print("Telegram sent.")

    ok_count = sum(1 for r in results.values() if "error" not in r)
    print(f"[{datetime.now().isoformat()}] Done: {ok_count}/{len(WATCHLIST)} symbols OK")
    return 0 if ok_count > 0 else 1


if __name__ == "__main__":
    sys.exit(main())
