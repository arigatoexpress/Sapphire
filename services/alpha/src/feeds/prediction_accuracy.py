"""Prediction Market Accuracy Tracker

Records prediction market probabilities at signal time and compares
against actual crypto price outcomes. Tracks:
  - Per-market Brier score (probability calibration)
  - Per-source accuracy (Polymarket vs Kalshi)
  - High-conviction signal hit rate
  - Symbol-level prediction performance
"""

import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from loguru import logger

from .prediction_signal import PredictionSignal, PredictionSource


@dataclass
class PredictionSnapshot:
    """A point-in-time snapshot of a prediction signal for accuracy tracking."""

    market_id: str
    source: PredictionSource
    question: str
    probability: float
    volume_usd: float
    symbols: List[str]
    was_high_conviction: bool
    snapshot_time: float  # unix timestamp
    # Outcome (filled in later)
    resolved: bool = False
    outcome: Optional[bool] = None  # True = event happened, False = didn't
    resolved_time: float = 0.0


class PredictionAccuracyTracker:
    """Tracks prediction market accuracy over time.

    Usage:
        tracker = PredictionAccuracyTracker()
        tracker.record_signal(signal)  # Called each poll cycle
        tracker.record_outcome("poly_btc100k", True)  # Event happened
        stats = tracker.get_accuracy_stats()
    """

    def __init__(self, max_snapshots: int = 1000):
        self._snapshots: Dict[str, PredictionSnapshot] = {}
        self._max_snapshots = max_snapshots
        # Per-source accuracy tracking
        self._source_stats: Dict[str, Dict[str, int]] = defaultdict(
            lambda: {"total": 0, "correct": 0, "brier_sum": 0.0}
        )

    def record_signal(self, signal: PredictionSignal) -> None:
        """Record a prediction signal snapshot for future accuracy comparison.

        Only records if this market_id hasn't been recorded yet (first sighting).
        """
        if signal.market_id in self._snapshots:
            return  # Already tracking

        # Enforce max capacity
        if len(self._snapshots) >= self._max_snapshots:
            self._evict_oldest()

        self._snapshots[signal.market_id] = PredictionSnapshot(
            market_id=signal.market_id,
            source=signal.source,
            question=signal.question,
            probability=signal.probability,
            volume_usd=signal.volume_usd,
            symbols=signal.symbols,
            was_high_conviction=signal.is_high_conviction,
            snapshot_time=time.time(),
        )

    def record_outcome(self, market_id: str, outcome: bool) -> Optional[Dict[str, Any]]:
        """Record whether a predicted event actually happened.

        Args:
            market_id: The prediction market identifier.
            outcome: True if the event occurred, False if not.

        Returns:
            Dict with accuracy metrics, or None if market not found.
        """
        snap = self._snapshots.get(market_id)
        if not snap or snap.resolved:
            return None

        snap.resolved = True
        snap.outcome = outcome
        snap.resolved_time = time.time()

        # Brier score: (probability - outcome)^2
        # Lower is better. 0 = perfect, 1 = worst
        outcome_val = 1.0 if outcome else 0.0
        brier = (snap.probability - outcome_val) ** 2

        # Was the prediction correct? (prob > 0.5 means "likely yes")
        predicted_yes = snap.probability >= 0.5
        correct = predicted_yes == outcome

        # Update source stats
        source_key = snap.source.value
        self._source_stats[source_key]["total"] += 1
        if correct:
            self._source_stats[source_key]["correct"] += 1
        self._source_stats[source_key]["brier_sum"] += brier

        return {
            "market_id": market_id,
            "question": snap.question,
            "probability": snap.probability,
            "outcome": outcome,
            "correct": correct,
            "brier_score": round(brier, 4),
            "source": source_key,
            "time_to_resolution_hours": round(
                (snap.resolved_time - snap.snapshot_time) / 3600, 1
            ),
        }

    def get_accuracy_stats(self) -> Dict[str, Any]:
        """Get overall and per-source accuracy statistics."""
        total_resolved = 0
        total_correct = 0
        total_brier = 0.0
        hc_resolved = 0
        hc_correct = 0

        for snap in self._snapshots.values():
            if not snap.resolved:
                continue
            total_resolved += 1
            predicted_yes = snap.probability >= 0.5
            if predicted_yes == snap.outcome:
                total_correct += 1
            total_brier += (snap.probability - (1.0 if snap.outcome else 0.0)) ** 2

            if snap.was_high_conviction:
                hc_resolved += 1
                if predicted_yes == snap.outcome:
                    hc_correct += 1

        source_stats = {}
        for source, stats in self._source_stats.items():
            total = stats["total"]
            source_stats[source] = {
                "total": total,
                "correct": stats["correct"],
                "accuracy_pct": round(stats["correct"] / total * 100, 1) if total else 0.0,
                "avg_brier": round(stats["brier_sum"] / total, 4) if total else 0.0,
            }

        return {
            "total_tracked": len(self._snapshots),
            "total_resolved": total_resolved,
            "total_pending": len(self._snapshots) - total_resolved,
            "overall_accuracy_pct": round(
                total_correct / total_resolved * 100, 1
            ) if total_resolved else 0.0,
            "overall_brier": round(
                total_brier / total_resolved, 4
            ) if total_resolved else 0.0,
            "high_conviction_resolved": hc_resolved,
            "high_conviction_accuracy_pct": round(
                hc_correct / hc_resolved * 100, 1
            ) if hc_resolved else 0.0,
            "by_source": source_stats,
        }

    def get_pending_markets(self) -> List[Dict[str, Any]]:
        """Get all unresolved prediction snapshots (awaiting outcome)."""
        pending = []
        for snap in self._snapshots.values():
            if not snap.resolved:
                pending.append({
                    "market_id": snap.market_id,
                    "source": snap.source.value,
                    "question": snap.question,
                    "probability": snap.probability,
                    "symbols": snap.symbols,
                    "was_high_conviction": snap.was_high_conviction,
                    "age_hours": round(
                        (time.time() - snap.snapshot_time) / 3600, 1
                    ),
                })
        return sorted(pending, key=lambda p: p["age_hours"], reverse=True)

    def format_telegram_accuracy(self) -> str:
        """Format accuracy stats for Telegram display."""
        stats = self.get_accuracy_stats()

        if stats["total_resolved"] == 0:
            return (
                "📊 **Prediction Accuracy Tracker**\n\n"
                f"Tracking: {stats['total_tracked']} markets\n"
                "No resolved predictions yet."
            )

        lines = [
            "📊 **Prediction Accuracy Tracker**\n",
            f"Tracked: {stats['total_tracked']} | "
            f"Resolved: {stats['total_resolved']} | "
            f"Pending: {stats['total_pending']}",
            f"Overall accuracy: **{stats['overall_accuracy_pct']}%**",
            f"Brier score: {stats['overall_brier']} (lower=better)",
        ]

        if stats["high_conviction_resolved"] > 0:
            lines.append(
                f"High-conviction accuracy: **{stats['high_conviction_accuracy_pct']}%** "
                f"({stats['high_conviction_resolved']} resolved)"
            )

        if stats["by_source"]:
            lines.append("\n**By Source:**")
            for source, src_stats in stats["by_source"].items():
                lines.append(
                    f"  {source}: {src_stats['accuracy_pct']}% "
                    f"({src_stats['correct']}/{src_stats['total']}, "
                    f"brier={src_stats['avg_brier']})"
                )

        return "\n".join(lines)

    def _evict_oldest(self) -> None:
        """Remove oldest resolved snapshots to stay under max capacity."""
        resolved = [
            (mid, snap) for mid, snap in self._snapshots.items() if snap.resolved
        ]
        if not resolved:
            # If no resolved, remove oldest unresolved
            oldest_key = min(
                self._snapshots, key=lambda k: self._snapshots[k].snapshot_time
            )
            del self._snapshots[oldest_key]
            return

        # Remove oldest resolved first
        resolved.sort(key=lambda x: x[1].resolved_time)
        del self._snapshots[resolved[0][0]]
