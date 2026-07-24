"""Performance tracker — records signals and outcomes, computes strategy stats.

Appends signal events to data/performance/signals.jsonl and scores them when
outcomes are known (TP hit / SL hit / timeout). Separate from the paper
trading system: this tracks EVERY generated signal regardless of execution.

Usage:
    from lib.analytics.performance_tracker import PerformanceTracker
    pt = PerformanceTracker()
    pt.record_signal(signal_data)      # on signal generation
    pt.record_outcome(signal_id, ...)  # on TP/SL/timeout
    stats = pt.get_all_stats()
    alerts = pt.get_decay_alerts()
"""

from __future__ import annotations

import json
import logging
import sys
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

log = logging.getLogger(__name__)

DATA_DIR = ROOT / "data" / "performance"
SIGNALS_FILE = DATA_DIR / "signals.jsonl"

# Strategy decay detection
_DECAY_WINDOW = 20  # last N signals to evaluate
_DECAY_WIN_RATE_DROP = 0.15  # if rolling win rate drops >15pp vs baseline
_DECAY_MIN_TRADES = 10  # minimum trades before decay check kicks in


class PerformanceTracker:
    """Records trading signals and outcomes; computes rolling stats."""

    def __init__(self, data_dir: Path | None = None):
        self._dir = data_dir or DATA_DIR
        self._dir.mkdir(parents=True, exist_ok=True)
        self._file = self._dir / "signals.jsonl"

    # ------------------------------------------------------------------
    # Write path
    # ------------------------------------------------------------------

    def record_signal(self, signal: dict[str, Any]) -> str:
        """Append a new signal. Returns assigned signal_id."""
        signal_id = signal.get("signal_id") or str(uuid.uuid4())[:8]
        entry = {
            "signal_id": signal_id,
            "recorded_at": datetime.now(UTC).isoformat(),
            "symbol": signal.get("symbol", "UNKNOWN"),
            "direction": signal.get("direction", signal.get("prediction", "UNKNOWN")),
            "confidence": signal.get("confidence", 0.0),
            "regime": signal.get("regime", "UNKNOWN"),
            "entry_price": signal.get("entry_price") or signal.get("current_price"),
            "tp_price": signal.get("tp_price") or signal.get("take_profit"),
            "sl_price": signal.get("sl_price") or signal.get("stop_loss"),
            "timeframe": signal.get("timeframe", "24h"),
            "source": signal.get("source", "signal_pipeline"),
            "enhancer_flags": signal.get("enhancer_flags") or [],
            "outcome": None,  # filled by record_outcome
            "exit_price": None,
            "pnl_pct": None,
            "closed_at": None,
        }
        self._append(entry)
        log.debug(
            "tracked signal %s %s %s (conf %.0f%%)",
            signal_id,
            entry["symbol"],
            entry["direction"],
            (entry["confidence"] or 0) * 100,
        )
        return signal_id

    def record_outcome(
        self,
        signal_id: str,
        outcome: str,  # "win" | "loss" | "timeout"
        exit_price: float | None = None,
        pnl_pct: float | None = None,
    ) -> bool:
        """Update an existing signal with its outcome. Returns True if found."""
        lines = self._read_lines()
        updated = False
        new_lines = []
        for raw in lines:
            try:
                entry = json.loads(raw)
            except json.JSONDecodeError:
                new_lines.append(raw)
                continue
            if entry.get("signal_id") == signal_id and entry.get("outcome") is None:
                entry["outcome"] = outcome
                entry["exit_price"] = exit_price
                entry["pnl_pct"] = pnl_pct
                entry["closed_at"] = datetime.now(UTC).isoformat()
                updated = True
            new_lines.append(json.dumps(entry))

        if updated:
            self._file.write_text("\n".join(new_lines) + "\n")
            log.debug(
                "recorded outcome %s for signal %s (%.1f%%)",
                outcome,
                signal_id,
                (pnl_pct or 0) * 100,
            )
        return updated

    # ------------------------------------------------------------------
    # Read path
    # ------------------------------------------------------------------

    def load_signals(self, limit: int | None = None) -> list[dict]:
        """Load all tracked signals (newest first)."""
        lines = self._read_lines()
        out = []
        for raw in reversed(lines):
            try:
                out.append(json.loads(raw))
            except json.JSONDecodeError:
                continue
            if limit and len(out) >= limit:
                break
        return out

    def get_all_stats(self) -> dict:
        """Compute aggregate stats over all recorded signals."""
        signals = self.load_signals()
        if not signals:
            return {
                "total_signals": 0,
                "scored_signals": 0,
                "win_rate": None,
                "avg_pnl_pct": None,
                "by_symbol": {},
                "by_regime": {},
                "note": "No signals tracked yet — tracking starts now.",
            }

        scored = [s for s in signals if s.get("outcome") in ("win", "loss")]
        wins = [s for s in scored if s["outcome"] == "win"]

        win_rate = len(wins) / len(scored) if scored else None
        avg_pnl = sum(s["pnl_pct"] or 0 for s in scored) / len(scored) if scored else None

        # Per-symbol breakdown
        by_sym: dict[str, dict] = {}
        for s in scored:
            sym = s.get("symbol", "UNKNOWN")
            if sym not in by_sym:
                by_sym[sym] = {"wins": 0, "losses": 0, "pnl": []}
            if s["outcome"] == "win":
                by_sym[sym]["wins"] += 1
            else:
                by_sym[sym]["losses"] += 1
            if s.get("pnl_pct") is not None:
                by_sym[sym]["pnl"].append(s["pnl_pct"])
        for d in by_sym.values():
            total = d["wins"] + d["losses"]
            d["win_rate"] = d["wins"] / total if total else None
            d["avg_pnl"] = sum(d["pnl"]) / len(d["pnl"]) if d["pnl"] else None

        # Per-regime breakdown
        by_regime: dict[str, dict] = {}
        for s in scored:
            reg = s.get("regime", "UNKNOWN")
            if reg not in by_regime:
                by_regime[reg] = {"wins": 0, "losses": 0}
            if s["outcome"] == "win":
                by_regime[reg]["wins"] += 1
            else:
                by_regime[reg]["losses"] += 1
        for d in by_regime.values():
            total = d["wins"] + d["losses"]
            d["win_rate"] = d["wins"] / total if total else None

        return {
            "total_signals": len(signals),
            "scored_signals": len(scored),
            "pending_signals": len(signals) - len(scored),
            "win_rate": round(win_rate, 4) if win_rate is not None else None,
            "avg_pnl_pct": round(avg_pnl, 4) if avg_pnl is not None else None,
            "by_symbol": by_sym,
            "by_regime": by_regime,
        }

    def get_decay_alerts(self) -> list[dict]:
        """Detect strategy decay: win rate dropping in recent N trades vs baseline."""
        signals = self.load_signals()
        scored = [s for s in signals if s.get("outcome") in ("win", "loss")]
        scored_chrono = list(reversed(scored))  # oldest first

        if len(scored_chrono) < _DECAY_MIN_TRADES:
            return []

        baseline_trades = (
            scored_chrono[:-_DECAY_WINDOW] if len(scored_chrono) > _DECAY_WINDOW else []
        )
        recent_trades = scored_chrono[-_DECAY_WINDOW:]

        if not baseline_trades or not recent_trades:
            return []

        baseline_wr = sum(1 for s in baseline_trades if s["outcome"] == "win") / len(
            baseline_trades
        )
        recent_wr = sum(1 for s in recent_trades if s["outcome"] == "win") / len(recent_trades)
        drop = baseline_wr - recent_wr

        alerts = []
        if drop >= _DECAY_WIN_RATE_DROP:
            alerts.append(
                {
                    "type": "win_rate_decay",
                    "severity": "high" if drop >= 0.25 else "moderate",
                    "baseline_win_rate": round(baseline_wr, 3),
                    "recent_win_rate": round(recent_wr, 3),
                    "drop": round(drop, 3),
                    "window": _DECAY_WINDOW,
                    "message": (
                        f"Win rate dropped {drop:.0%} — {recent_wr:.0%} recent vs "
                        f"{baseline_wr:.0%} baseline ({_DECAY_WINDOW} trade window)"
                    ),
                }
            )

        # Also flag if last 5 signals were all losses
        last5 = recent_trades[-5:]
        if len(last5) == 5 and all(s["outcome"] == "loss" for s in last5):
            alerts.append(
                {
                    "type": "consecutive_losses",
                    "severity": "high",
                    "count": 5,
                    "message": "Last 5 scored signals were losses — review signal quality",
                }
            )

        return alerts

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _append(self, entry: dict) -> None:
        with open(self._file, "a") as f:
            f.write(json.dumps(entry) + "\n")

    def _read_lines(self) -> list[str]:
        if not self._file.exists():
            return []
        return [l for l in self._file.read_text(encoding="utf-8").splitlines() if l.strip()]
