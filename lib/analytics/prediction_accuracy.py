"""Prediction accuracy reader for data/trading_predictions.jsonl.

The TA scanner writes prediction records with `direction` + optional `correct`
set after scoring. This module reports accuracy overall and per symbol,
plus the scored / unscored / open counts so the dashboard can surface
prediction quality without coupling to the (heavier) signal performance
tracker.
"""

from __future__ import annotations

import json
import logging
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parents[2]
PREDICTIONS_FILE = ROOT / "data" / "trading_predictions.jsonl"


def _load() -> list[dict[str, Any]]:
    if not PREDICTIONS_FILE.exists():
        return []
    try:
        raw = PREDICTIONS_FILE.read_text()
    except OSError:
        return []
    out: list[dict[str, Any]] = []
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out


def report() -> dict[str, Any]:
    """Return overall + per-symbol + per-direction accuracy."""
    records = _load()
    total = len(records)
    scored = [r for r in records if r.get("correct") is not None]
    correct = [r for r in scored if r.get("correct")]

    by_symbol: dict[str, dict[str, int]] = defaultdict(lambda: {"total": 0, "scored": 0, "correct": 0})
    for r in records:
        sym = r.get("symbol") or "?"
        by_symbol[sym]["total"] += 1
        if r.get("correct") is not None:
            by_symbol[sym]["scored"] += 1
            if r["correct"]:
                by_symbol[sym]["correct"] += 1

    by_direction: dict[str, dict[str, int]] = defaultdict(lambda: {"total": 0, "scored": 0, "correct": 0})
    for r in records:
        d = r.get("direction") or "?"
        by_direction[d]["total"] += 1
        if r.get("correct") is not None:
            by_direction[d]["scored"] += 1
            if r["correct"]:
                by_direction[d]["correct"] += 1

    def _enrich(d: dict[str, int]) -> dict[str, Any]:
        acc = (d["correct"] / d["scored"]) if d["scored"] else None
        return {
            **d,
            "accuracy": round(acc, 4) if acc is not None else None,
        }

    recent = sorted(records, key=lambda r: r.get("timestamp") or "", reverse=True)[:10]

    return {
        "total": total,
        "scored": len(scored),
        "correct": len(correct),
        "open": total - len(scored),
        "accuracy": round(len(correct) / len(scored), 4) if scored else None,
        "by_symbol": {k: _enrich(v) for k, v in by_symbol.items()},
        "by_direction": {k: _enrich(v) for k, v in by_direction.items()},
        "recent": recent,
        "generated_at": datetime.now(UTC).isoformat(),
    }


if __name__ == "__main__":
    import sys
    json.dump(report(), sys.stdout, indent=2, default=str)
    print()
