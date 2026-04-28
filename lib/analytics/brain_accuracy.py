"""Trading Brain decision accuracy tracker.

Records every GO/LEAN/WAIT decision from trading_brain and scores them
against actual price movement after the decision window closes.

Decision log: data/decisions/brain_decisions.jsonl
Each record: {symbol, decision, direction, confidence, votes, timestamp, scored, outcome, price_at_decision, price_at_close, pnl_pct}

Scoring windows:
  GO_LONG/GO_SHORT  — 24h forward price movement
  LEAN_LONG/LEAN_SHORT — 24h forward
  WAIT — scored as correct if price stayed within ±2% (no strong move)

A decision is "correct" if:
  GO_LONG  → price rose > 0.5%
  GO_SHORT → price fell > 0.5%
  LEAN_LONG  → price rose > 0.25%
  LEAN_SHORT → price fell > 0.25%
  WAIT → abs(price change) < 2%
"""

from __future__ import annotations

import json
import logging
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parents[2]
DECISIONS_FILE = ROOT / "data" / "decisions" / "brain_decisions.jsonl"
DECISIONS_DIR = ROOT / "data" / "decisions"

SCORING_WINDOW_H = 24
GO_THRESHOLD = 0.005  # 0.5% for GO signals
LEAN_THRESHOLD = 0.0025  # 0.25% for LEAN signals
WAIT_BAND = 0.02  # ±2% for WAIT


def record_decision(decision: dict[str, Any]) -> Path:
    """Append a trading_brain decision to the JSONL log.

    Args:
        decision: Output of trading_brain.action_decide() — must include
                  symbol, decision, direction, confidence, timestamp, votes.

    Returns:
        Path to the JSONL file written.
    """
    DECISIONS_DIR.mkdir(parents=True, exist_ok=True)
    record = {
        "symbol": decision.get("symbol"),
        "decision": decision.get("decision"),
        "direction": decision.get("direction"),
        "confidence": decision.get("confidence"),
        "votes": decision.get("votes", []),
        "aggregation": decision.get("aggregation", {}),
        "track_record": decision.get("track_record", {}),
        "timestamp": decision.get("timestamp") or datetime.now(UTC).isoformat(),
        "scored": False,
        "outcome": None,
        "price_at_decision": None,
        "price_at_close": None,
        "pnl_pct": None,
    }

    # Try to capture current price for later scoring
    try:
        import subprocess
        import sys

        tools_dir = ROOT / "plugins" / "claw-sapphire" / "tools"
        r = subprocess.run(
            [sys.executable, str(tools_dir / "market.py")],
            input=json.dumps({"action": "quote", "symbol": record["symbol"]}),
            capture_output=True,
            text=True,
            timeout=15,
        )
        if r.stdout.strip():
            quote = json.loads(r.stdout)
            record["price_at_decision"] = quote.get("price") or quote.get("last_price")
    except Exception:
        pass

    with DECISIONS_FILE.open("a") as f:
        f.write(json.dumps(record, default=str) + "\n")

    return DECISIONS_FILE


def _load_decisions() -> list[dict[str, Any]]:
    """Load all brain decisions from the JSONL log."""
    if not DECISIONS_FILE.exists():
        return []
    records = []
    for line in DECISIONS_FILE.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return records


def score_decisions() -> dict[str, Any]:
    """Score unscored decisions where the scoring window has elapsed.

    Rewrites the JSONL with updated scores. Returns summary stats.
    """
    records = _load_decisions()
    if not records:
        return {"scored": 0, "pending": 0}

    now = datetime.now(UTC)
    scored_count = 0
    pending_count = 0

    for r in records:
        if r.get("scored"):
            scored_count += 1
            continue

        ts = r.get("timestamp")
        if not ts:
            continue
        try:
            dt = datetime.fromisoformat(ts)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=UTC)
        except (ValueError, TypeError):
            continue

        # Check if scoring window has elapsed
        if now - dt < timedelta(hours=SCORING_WINDOW_H):
            pending_count += 1
            continue

        # Try to get closing price (price SCORING_WINDOW_H hours after decision)
        price_at_decision = r.get("price_at_decision")
        if price_at_decision is None:
            pending_count += 1
            continue

        # Fetch current price as proxy for closing price
        try:
            import subprocess
            import sys

            tools_dir = ROOT / "plugins" / "claw-sapphire" / "tools"
            result = subprocess.run(
                [sys.executable, str(tools_dir / "market.py")],
                input=json.dumps({"action": "quote", "symbol": r["symbol"]}),
                capture_output=True,
                text=True,
                timeout=15,
            )
            if result.stdout.strip():
                quote = json.loads(result.stdout)
                close_price = quote.get("price") or quote.get("last_price")
                if close_price:
                    r["price_at_close"] = close_price
                    pnl_pct = (close_price - price_at_decision) / price_at_decision
                    r["pnl_pct"] = round(pnl_pct, 6)

                    decision = r.get("decision", "")
                    if decision in ("GO_LONG", "LEAN_LONG"):
                        threshold = GO_THRESHOLD if "GO" in decision else LEAN_THRESHOLD
                        r["outcome"] = "correct" if pnl_pct > threshold else "incorrect"
                    elif decision in ("GO_SHORT", "LEAN_SHORT"):
                        threshold = GO_THRESHOLD if "GO" in decision else LEAN_THRESHOLD
                        r["outcome"] = "correct" if pnl_pct < -threshold else "incorrect"
                    elif decision == "WAIT":
                        r["outcome"] = "correct" if abs(pnl_pct) < WAIT_BAND else "incorrect"
                    else:
                        r["outcome"] = "unknown"

                    r["scored"] = True
                    scored_count += 1
                else:
                    pending_count += 1
            else:
                pending_count += 1
        except Exception:
            pending_count += 1

    # Rewrite the file with updated scores
    DECISIONS_DIR.mkdir(parents=True, exist_ok=True)
    with DECISIONS_FILE.open("w") as f:
        for r in records:
            f.write(json.dumps(r, default=str) + "\n")

    return {"scored": scored_count, "pending": pending_count}


def report() -> dict[str, Any]:
    """Generate accuracy report from scored decisions.

    Returns:
        {
            total_decisions, scored, pending,
            overall_accuracy, go_accuracy, lean_accuracy, wait_accuracy,
            by_symbol: {symbol: {total, correct, accuracy}},
            by_decision: {decision: {total, correct, accuracy}},
            recent: [last 10 scored decisions],
            confidence_calibration: [{bucket, decisions, accuracy}],
        }
    """
    records = _load_decisions()
    if not records:
        return {
            "total_decisions": 0,
            "scored": 0,
            "pending": 0,
            "overall_accuracy": None,
            "go_accuracy": None,
            "lean_accuracy": None,
            "wait_accuracy": None,
            "by_symbol": {},
            "by_decision": {},
            "recent": [],
            "confidence_calibration": [],
        }

    scored = [r for r in records if r.get("scored")]
    pending = [r for r in records if not r.get("scored")]
    correct = [r for r in scored if r.get("outcome") == "correct"]

    overall_acc = len(correct) / len(scored) if scored else None

    # By decision type
    by_decision: dict[str, dict[str, int]] = defaultdict(lambda: {"total": 0, "correct": 0})
    for r in scored:
        d = r.get("decision", "?")
        by_decision[d]["total"] += 1
        if r.get("outcome") == "correct":
            by_decision[d]["correct"] += 1

    for v in by_decision.values():
        v["accuracy"] = round(v["correct"] / v["total"], 4) if v["total"] else None

    # GO vs LEAN vs WAIT aggregates
    go_scored = [r for r in scored if "GO" in (r.get("decision") or "")]
    lean_scored = [r for r in scored if "LEAN" in (r.get("decision") or "")]
    wait_scored = [r for r in scored if r.get("decision") == "WAIT"]

    def _acc(subset):
        c = sum(1 for r in subset if r.get("outcome") == "correct")
        return round(c / len(subset), 4) if subset else None

    # By symbol
    by_symbol: dict[str, dict[str, int]] = defaultdict(lambda: {"total": 0, "correct": 0})
    for r in scored:
        s = r.get("symbol", "?")
        by_symbol[s]["total"] += 1
        if r.get("outcome") == "correct":
            by_symbol[s]["correct"] += 1
    for v in by_symbol.values():
        v["accuracy"] = round(v["correct"] / v["total"], 4) if v["total"] else None

    # Confidence calibration (buckets of 0.1)
    cal_buckets: dict[str, dict[str, int]] = defaultdict(lambda: {"total": 0, "correct": 0})
    for r in scored:
        conf = r.get("confidence", 0.5)
        bucket = f"{int(conf * 10) / 10:.1f}-{int(conf * 10) / 10 + 0.1:.1f}"
        cal_buckets[bucket]["total"] += 1
        if r.get("outcome") == "correct":
            cal_buckets[bucket]["correct"] += 1

    calibration = []
    for bucket, v in sorted(cal_buckets.items()):
        calibration.append(
            {
                "bucket": bucket,
                "decisions": v["total"],
                "accuracy": round(v["correct"] / v["total"], 4) if v["total"] else None,
            }
        )

    # Recent scored
    recent = sorted(scored, key=lambda r: r.get("timestamp", ""), reverse=True)[:10]
    recent_clean = []
    for r in recent:
        recent_clean.append(
            {
                "symbol": r.get("symbol"),
                "decision": r.get("decision"),
                "confidence": r.get("confidence"),
                "outcome": r.get("outcome"),
                "pnl_pct": r.get("pnl_pct"),
                "timestamp": r.get("timestamp"),
            }
        )

    return {
        "total_decisions": len(records),
        "scored": len(scored),
        "pending": len(pending),
        "overall_accuracy": round(overall_acc, 4) if overall_acc is not None else None,
        "go_accuracy": _acc(go_scored),
        "lean_accuracy": _acc(lean_scored),
        "wait_accuracy": _acc(wait_scored),
        "by_symbol": dict(by_symbol),
        "by_decision": dict(by_decision),
        "recent": recent_clean,
        "confidence_calibration": calibration,
    }


def brief_summary() -> str:
    """One-paragraph summary for the morning brief."""
    r = report()
    if r["scored"] == 0:
        if r["pending"] > 0:
            return f"  {r['pending']} decisions pending scoring (need {SCORING_WINDOW_H}h window)."
        return "  No trading brain decisions recorded yet."

    lines = []
    acc = r["overall_accuracy"]
    acc_str = f"{acc:.0%}" if acc is not None else "—"
    lines.append(f"  Brain accuracy: `{acc_str}` ({r['scored']} scored, {r['pending']} pending)")

    # Per-type
    parts = []
    if r["go_accuracy"] is not None:
        parts.append(f"GO {r['go_accuracy']:.0%}")
    if r["lean_accuracy"] is not None:
        parts.append(f"LEAN {r['lean_accuracy']:.0%}")
    if r["wait_accuracy"] is not None:
        parts.append(f"WAIT {r['wait_accuracy']:.0%}")
    if parts:
        lines.append(f"  {' · '.join(parts)}")

    # Best/worst symbol
    if r["by_symbol"]:
        best = max(r["by_symbol"].items(), key=lambda kv: kv[1].get("accuracy") or 0)
        worst = min(r["by_symbol"].items(), key=lambda kv: kv[1].get("accuracy") or 1)
        if best[1].get("accuracy") is not None:
            lines.append(
                f"  Best: {best[0]} {best[1]['accuracy']:.0%} · Worst: {worst[0]} {worst[1]['accuracy']:.0%}"
            )

    return "\n".join(lines)
