"""Anchor today's Kronos predictions on 0G — one signal per watchlist asset.

Reads `data/intelligence/<date>/predictions.json` (produced by the kronos-daily
LaunchAgent), builds a signal envelope per asset, and calls the og_publish
plugin tool to upload to 0G Storage and anchor on 0G Chain.

Designed to be invoked from a scheduled task (`com.sapphire.kronos-og-anchor`)
right after kronos-daily completes.

Idempotency: each anchor includes the prediction timestamp inside the envelope,
so re-running on the same predictions.json produces a different rootHash if
the file changed. Writes its own progress log to data/og/kronos_anchor_log.jsonl.

Requires SAPPHIRE_OG_ENABLED=1 and OG_PRIVATE_KEY in the environment.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from lib.og.config import ENV_FLAG, ENV_PRIVATE_KEY  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s og_publish_kronos %(message)s")
log = logging.getLogger(__name__)

PUBLISH_TOOL = ROOT / "plugins" / "claw-sapphire" / "tools" / "og_publish.py"
INTELLIGENCE_DIR = ROOT / "data" / "intelligence"
ANCHOR_LOG = ROOT / "data" / "og" / "kronos_anchor_log.jsonl"


def _relative_or_str(path: Path) -> str:
    """Return path relative to the repo if possible, else the absolute path."""
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def _direction_to_action(direction: str) -> str:
    d = (direction or "").strip().lower()
    if d in {"bullish", "long", "up", "buy"}:
        return "buy"
    if d in {"bearish", "short", "down", "sell"}:
        return "sell"
    return "hold"


def _confidence_to_score(confidence: float | None) -> int:
    if confidence is None:
        return 0
    c = float(confidence)
    if c < 0:
        c = 0.0
    if c > 1:
        c = 1.0
    return int(round(c * 100))


def _latest_predictions() -> Path | None:
    if not INTELLIGENCE_DIR.exists():
        return None
    dated = sorted(p for p in INTELLIGENCE_DIR.iterdir() if p.is_dir() and p.name.count("-") == 2)
    if not dated:
        return None
    candidate = dated[-1] / "predictions.json"
    return candidate if candidate.exists() else None


def _publish_one(payload: dict) -> dict:
    proc = subprocess.run(
        [sys.executable, str(PUBLISH_TOOL)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        timeout=300,
        env=os.environ.copy(),
    )
    out = proc.stdout.strip()
    if not out:
        return {"ok": False, "error": "no stdout", "stderr": proc.stderr.strip()}
    try:
        return json.loads(out.splitlines()[-1])
    except json.JSONDecodeError as exc:
        return {"ok": False, "error": f"bad output: {exc}", "raw": out}


def _record(entry: dict) -> None:
    ANCHOR_LOG.parent.mkdir(parents=True, exist_ok=True)
    with open(ANCHOR_LOG, "a") as f:
        f.write(json.dumps(entry) + "\n")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--predictions", help="Path to a specific predictions.json (default: latest)"
    )
    parser.add_argument("--symbol", action="append", help="Restrict to specific symbol(s)")
    parser.add_argument("--dry-run", action="store_true", help="Print payloads without publishing")
    args = parser.parse_args()

    if not args.dry_run:
        if os.environ.get(ENV_FLAG, "0").strip() != "1":
            log.error("SAPPHIRE_OG_ENABLED=1 required to publish")
            return 1
        if ENV_PRIVATE_KEY not in os.environ:
            log.error("%s must be set", ENV_PRIVATE_KEY)
            return 1

    pred_path = Path(args.predictions) if args.predictions else _latest_predictions()
    if pred_path is None or not pred_path.exists():
        log.error("no predictions file found under %s", INTELLIGENCE_DIR)
        return 1

    log.info("Reading %s", pred_path)
    document = json.loads(pred_path.read_text())
    predictions = document.get("predictions", {})
    if not predictions:
        log.error("predictions object is empty")
        return 1

    target_symbols = set(args.symbol) if args.symbol else None
    summary = {"published": [], "skipped": [], "errors": []}

    for symbol, prediction in predictions.items():
        if target_symbols and symbol not in target_symbols:
            continue
        if not isinstance(prediction, dict):
            summary["skipped"].append({"symbol": symbol, "reason": "non-dict prediction"})
            continue

        payload = {
            "strategy": "kronos_daily_24h",
            "symbol": symbol,
            "action": _direction_to_action(prediction.get("direction", "")),
            "score": _confidence_to_score(prediction.get("confidence")),
            "signal": {
                "current_price": prediction.get("current_price"),
                "direction": prediction.get("direction"),
                "confidence": prediction.get("confidence"),
                "predict_bars": prediction.get("predict_bars"),
                "interval": prediction.get("interval"),
                "predictions_summary": _summarise(prediction.get("predictions") or []),
            },
            "inputs": {
                "predictions_file": _relative_or_str(pred_path),
                "generated_at": document.get("generated_at"),
                "source": document.get("source"),
                "lookback_used": prediction.get("lookback_used"),
            },
        }

        if args.dry_run:
            print(json.dumps({"symbol": symbol, "would_publish": payload}))
            continue

        log.info("publishing %s ...", symbol)
        result = _publish_one(payload)
        record = {
            "timestamp": datetime.now(UTC).isoformat(),
            "symbol": symbol,
            "predictions_file": _relative_or_str(pred_path),
            "result": result,
        }
        _record(record)
        if result.get("ok"):
            summary["published"].append(
                {
                    "symbol": symbol,
                    "signal_id": result.get("anchor", {}).get("signal_id"),
                    "tx_hash": result.get("anchor", {}).get("tx_hash"),
                    "explorer_url": result.get("anchor", {}).get("explorer_url"),
                }
            )
        else:
            summary["errors"].append({"symbol": symbol, "error": result.get("error")})

    print(json.dumps({"ok": len(summary["errors"]) == 0, "summary": summary}, indent=2))
    return 0 if not summary["errors"] else 2


def _summarise(rows: list[dict]) -> dict:
    if not rows:
        return {"bars": 0}
    closes = [r.get("close") for r in rows if isinstance(r.get("close"), (int, float))]
    return {
        "bars": len(rows),
        "first_close": closes[0] if closes else None,
        "last_close": closes[-1] if closes else None,
        "min_close": min(closes) if closes else None,
        "max_close": max(closes) if closes else None,
    }


if __name__ == "__main__":
    sys.exit(main())
