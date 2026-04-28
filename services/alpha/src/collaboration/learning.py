"""Collaborative Learning — Swarm Knowledge Extraction & Pattern Recognition.

Learns from resolved trade ideas across the bot network to improve
future consensus quality.  Tracks:

- Symbol performance patterns (which symbols win/lose)
- Timeframe effectiveness (which timeframes produce better signals)
- Bot synergy patterns (which bot combinations correlate with wins)
- Direction bias (long vs short accuracy by market conditions)
- Conviction calibration (does high conviction actually predict success?)

Generates periodic insight reports that are published to the forum
for agent consumption and strategy refinement.
"""

import threading
import time
from collections import defaultdict
from typing import Any

from loguru import logger


class SwarmLearning:
    """Extracts actionable patterns from resolved swarm trade ideas."""

    # Minimum samples before generating insights
    MIN_SAMPLES_FOR_INSIGHT = 5
    # Maximum history entries to retain
    MAX_HISTORY = 2000
    # Insight generation cooldown (seconds)
    INSIGHT_COOLDOWN_SECONDS = 3600  # 1 hour

    def __init__(self):
        self._lock = threading.Lock()
        # Resolved idea outcomes — the raw learning data
        self._history: list[dict[str, Any]] = []
        # Aggregated performance by dimension
        self._symbol_stats: dict[str, dict[str, float]] = defaultdict(
            lambda: {"wins": 0, "losses": 0, "total_pnl": 0.0, "count": 0}
        )
        self._timeframe_stats: dict[str, dict[str, float]] = defaultdict(
            lambda: {"wins": 0, "losses": 0, "accurate": 0, "count": 0}
        )
        self._direction_stats: dict[str, dict[str, float]] = defaultdict(
            lambda: {"wins": 0, "losses": 0, "accurate": 0, "count": 0}
        )
        self._conviction_buckets: dict[str, dict[str, float]] = defaultdict(
            lambda: {"wins": 0, "losses": 0, "count": 0}
        )
        self._bot_pair_stats: dict[str, dict[str, float]] = defaultdict(
            lambda: {"wins": 0, "losses": 0, "count": 0}
        )
        self._last_insight_at = 0.0

    def record_outcome(
        self,
        symbol: str,
        direction: str,
        timeframe: str,
        conviction: float,
        contributors: list[str],
        accurate: bool,
        profitable: bool,
        pnl: float = 0.0,
        consensus: str = "",
    ) -> dict[str, Any]:
        """Record a resolved trade outcome for learning.

        This should be called after a swarm consensus trade is executed
        and the result is known.

        Args:
            symbol: Trading pair.
            direction: LONG or SHORT.
            timeframe: e.g. "1h", "4h", "1d".
            conviction: Swarm conviction level 0.0–1.0.
            contributors: List of bot IDs that contributed ideas.
            accurate: Whether the direction prediction was correct.
            profitable: Whether the trade was profitable.
            pnl: Realized P&L.
            consensus: The consensus label (LONG, SHORT, LEAN_LONG, etc).
        """
        with self._lock:
            record = {
                "symbol": str(symbol or "").strip().upper(),
                "direction": str(direction or "").strip().upper(),
                "timeframe": str(timeframe or "1h").strip(),
                "conviction": max(0.0, min(1.0, float(conviction))),
                "contributors": [str(b).strip().upper() for b in (contributors or [])],
                "consensus": str(consensus or direction).strip().upper(),
                "accurate": bool(accurate),
                "profitable": bool(profitable),
                "pnl": float(pnl),
                "recorded_at": int(time.time()),
            }

            # Append to history
            self._history.append(record)
            if len(self._history) > self.MAX_HISTORY:
                self._history = self._history[-self.MAX_HISTORY :]

            # Update symbol stats
            sym_stat = self._symbol_stats[record["symbol"]]
            sym_stat["count"] += 1
            sym_stat["total_pnl"] += record["pnl"]
            if record["profitable"]:
                sym_stat["wins"] += 1
            else:
                sym_stat["losses"] += 1

            # Update timeframe stats
            tf_stat = self._timeframe_stats[record["timeframe"]]
            tf_stat["count"] += 1
            if record["profitable"]:
                tf_stat["wins"] += 1
            else:
                tf_stat["losses"] += 1
            if record["accurate"]:
                tf_stat["accurate"] += 1

            # Update direction stats
            dir_stat = self._direction_stats[record["direction"]]
            dir_stat["count"] += 1
            if record["profitable"]:
                dir_stat["wins"] += 1
            else:
                dir_stat["losses"] += 1
            if record["accurate"]:
                dir_stat["accurate"] += 1

            # Update conviction buckets
            bucket = self._conviction_bucket(record["conviction"])
            conv_stat = self._conviction_buckets[bucket]
            conv_stat["count"] += 1
            if record["profitable"]:
                conv_stat["wins"] += 1
            else:
                conv_stat["losses"] += 1

            # Update bot pair synergy (every pair of contributors)
            bots = sorted(set(record["contributors"]))
            for i in range(len(bots)):
                for j in range(i + 1, len(bots)):
                    pair_key = f"{bots[i]}+{bots[j]}"
                    pair_stat = self._bot_pair_stats[pair_key]
                    pair_stat["count"] += 1
                    if record["profitable"]:
                        pair_stat["wins"] += 1
                    else:
                        pair_stat["losses"] += 1

            logger.info(
                f"Learning recorded: {record['symbol']} {record['direction']} "
                f"→ {'✅' if record['profitable'] else '❌'} (pnl={record['pnl']:+.2f})"
            )

            return {"ok": True, "total_records": len(self._history)}

    def get_symbol_insights(self, min_samples: int = 0) -> list[dict[str, Any]]:
        """Return performance insights per symbol."""
        threshold = min_samples or self.MIN_SAMPLES_FOR_INSIGHT
        with self._lock:
            results = []
            for symbol, stats in sorted(self._symbol_stats.items()):
                count = int(stats["count"])
                if count < threshold:
                    continue
                wins = int(stats["wins"])
                losses = int(stats["losses"])
                win_rate = wins / count if count > 0 else 0.0
                avg_pnl = stats["total_pnl"] / count if count > 0 else 0.0
                results.append(
                    {
                        "symbol": symbol,
                        "count": count,
                        "wins": wins,
                        "losses": losses,
                        "win_rate": round(win_rate, 4),
                        "total_pnl": round(stats["total_pnl"], 2),
                        "avg_pnl": round(avg_pnl, 2),
                        "edge": "positive"
                        if win_rate > 0.55
                        else ("negative" if win_rate < 0.45 else "neutral"),
                    }
                )
            results.sort(key=lambda x: x["win_rate"], reverse=True)
            return results

    def get_timeframe_insights(self, min_samples: int = 0) -> list[dict[str, Any]]:
        """Return performance insights per timeframe."""
        threshold = min_samples or self.MIN_SAMPLES_FOR_INSIGHT
        with self._lock:
            results = []
            for tf, stats in sorted(self._timeframe_stats.items()):
                count = int(stats["count"])
                if count < threshold:
                    continue
                wins = int(stats["wins"])
                accurate = int(stats["accurate"])
                win_rate = wins / count if count > 0 else 0.0
                accuracy = accurate / count if count > 0 else 0.0
                results.append(
                    {
                        "timeframe": tf,
                        "count": count,
                        "wins": wins,
                        "losses": int(stats["losses"]),
                        "win_rate": round(win_rate, 4),
                        "accuracy": round(accuracy, 4),
                        "edge": "positive"
                        if win_rate > 0.55
                        else ("negative" if win_rate < 0.45 else "neutral"),
                    }
                )
            results.sort(key=lambda x: x["win_rate"], reverse=True)
            return results

    def get_direction_insights(self) -> dict[str, Any]:
        """Return long vs short performance comparison."""
        with self._lock:
            result = {}
            for direction in ("LONG", "SHORT"):
                stats = self._direction_stats.get(direction, {})
                count = int(stats.get("count", 0))
                wins = int(stats.get("wins", 0))
                accurate = int(stats.get("accurate", 0))
                win_rate = wins / count if count > 0 else 0.0
                accuracy = accurate / count if count > 0 else 0.0
                result[direction] = {
                    "count": count,
                    "wins": wins,
                    "losses": int(stats.get("losses", 0)),
                    "win_rate": round(win_rate, 4),
                    "accuracy": round(accuracy, 4),
                }
            return result

    def get_conviction_calibration(self) -> list[dict[str, Any]]:
        """Return conviction vs actual win rate (calibration curve).

        This reveals whether high-conviction signals actually win more often.
        """
        with self._lock:
            results = []
            for bucket in ["0-25%", "25-50%", "50-70%", "70-85%", "85-100%"]:
                stats = self._conviction_buckets.get(bucket, {})
                count = int(stats.get("count", 0))
                if count == 0:
                    continue
                wins = int(stats.get("wins", 0))
                win_rate = wins / count if count > 0 else 0.0
                results.append(
                    {
                        "conviction_range": bucket,
                        "count": count,
                        "wins": wins,
                        "losses": int(stats.get("losses", 0)),
                        "actual_win_rate": round(win_rate, 4),
                        "calibrated": abs(win_rate - self._bucket_midpoint(bucket)) < 0.15,
                    }
                )
            return results

    def get_bot_synergy(self, min_samples: int = 0) -> list[dict[str, Any]]:
        """Return bot pair synergy insights.

        Which pairs of bots, when they agree, produce the best results?
        """
        threshold = min_samples or self.MIN_SAMPLES_FOR_INSIGHT
        with self._lock:
            results = []
            for pair_key, stats in sorted(self._bot_pair_stats.items()):
                count = int(stats["count"])
                if count < threshold:
                    continue
                wins = int(stats["wins"])
                win_rate = wins / count if count > 0 else 0.0
                bots = pair_key.split("+", 1)
                results.append(
                    {
                        "pair": pair_key,
                        "bot_a": bots[0] if len(bots) > 0 else "?",
                        "bot_b": bots[1] if len(bots) > 1 else "?",
                        "count": count,
                        "wins": wins,
                        "losses": int(stats["losses"]),
                        "win_rate": round(win_rate, 4),
                        "synergy": "strong"
                        if win_rate > 0.65
                        else ("weak" if win_rate < 0.40 else "moderate"),
                    }
                )
            results.sort(key=lambda x: x["win_rate"], reverse=True)
            return results

    def generate_report(self) -> dict[str, Any]:
        """Generate a comprehensive learning report.

        Combines all dimensions into a single structured report suitable
        for forum posting or agent consumption.
        """
        with self._lock:
            total = len(self._history)
            if total == 0:
                return {
                    "ok": True,
                    "total_records": 0,
                    "message": "No learning data yet.",
                    "generated_at": int(time.time()),
                }

            total_wins = sum(1 for r in self._history if r.get("profitable"))
            total_pnl = sum(r.get("pnl", 0) for r in self._history)
            overall_win_rate = total_wins / total if total > 0 else 0.0

        # Build report sections (release lock for insight methods that re-acquire)
        return {
            "ok": True,
            "total_records": total,
            "overall": {
                "win_rate": round(overall_win_rate, 4),
                "total_pnl": round(total_pnl, 2),
                "avg_pnl": round(total_pnl / total, 2) if total > 0 else 0.0,
                "wins": total_wins,
                "losses": total - total_wins,
            },
            "symbols": self.get_symbol_insights(min_samples=1),
            "timeframes": self.get_timeframe_insights(min_samples=1),
            "directions": self.get_direction_insights(),
            "conviction_calibration": self.get_conviction_calibration(),
            "bot_synergy": self.get_bot_synergy(min_samples=1),
            "generated_at": int(time.time()),
        }

    def get_symbol_bias(self, symbol: str) -> float:
        """Return a bias adjustment for a symbol based on historical performance.

        Returns:
            Float between -1.0 and 1.0.
            Positive = historically profitable, increase confidence.
            Negative = historically unprofitable, reduce confidence.
            Zero = insufficient data or neutral.
        """
        with self._lock:
            stats = self._symbol_stats.get(str(symbol or "").strip().upper())
            if not stats or stats["count"] < self.MIN_SAMPLES_FOR_INSIGHT:
                return 0.0
            win_rate = stats["wins"] / stats["count"] if stats["count"] > 0 else 0.5
            # Map win_rate to [-1, 1]: 0.5 → 0, 1.0 → 1.0, 0.0 → -1.0
            return round(max(-1.0, min(1.0, (win_rate - 0.5) * 2)), 4)

    def get_timeframe_bias(self, timeframe: str) -> float:
        """Return a bias adjustment for a timeframe."""
        with self._lock:
            stats = self._timeframe_stats.get(str(timeframe or "").strip())
            if not stats or stats["count"] < self.MIN_SAMPLES_FOR_INSIGHT:
                return 0.0
            win_rate = stats["wins"] / stats["count"] if stats["count"] > 0 else 0.5
            return round(max(-1.0, min(1.0, (win_rate - 0.5) * 2)), 4)

    def get_direction_bias(self, direction: str) -> float:
        """Return a bias adjustment for a direction (LONG/SHORT)."""
        with self._lock:
            stats = self._direction_stats.get(str(direction or "").strip().upper())
            if not stats or stats["count"] < self.MIN_SAMPLES_FOR_INSIGHT:
                return 0.0
            win_rate = stats["wins"] / stats["count"] if stats["count"] > 0 else 0.5
            return round(max(-1.0, min(1.0, (win_rate - 0.5) * 2)), 4)

    def adaptive_confidence(
        self,
        symbol: str,
        direction: str,
        timeframe: str,
        raw_confidence: float,
    ) -> float:
        """Adjust a raw confidence score using learned biases.

        This is the primary integration point — the swarm aggregator
        can call this to get a historically-calibrated confidence score.
        """
        sym_bias = self.get_symbol_bias(symbol)
        tf_bias = self.get_timeframe_bias(timeframe)
        dir_bias = self.get_direction_bias(direction)

        # Weighted combination of biases
        combined_bias = sym_bias * 0.4 + tf_bias * 0.3 + dir_bias * 0.3

        # Apply bias as a multiplier (capped)
        adjustment = 1.0 + (combined_bias * 0.25)  # ±25% max adjustment
        adjusted = raw_confidence * adjustment

        return round(max(0.0, min(1.0, adjusted)), 4)

    def summary(self) -> dict[str, Any]:
        """Quick summary stats."""
        with self._lock:
            total = len(self._history)
            if total == 0:
                return {
                    "total_records": 0,
                    "symbols_tracked": 0,
                    "timeframes_tracked": 0,
                    "bot_pairs_tracked": 0,
                }
            total_wins = sum(1 for r in self._history if r.get("profitable"))
            return {
                "total_records": total,
                "overall_win_rate": round(total_wins / total, 4) if total > 0 else 0.0,
                "total_pnl": round(sum(r.get("pnl", 0) for r in self._history), 2),
                "symbols_tracked": len(self._symbol_stats),
                "timeframes_tracked": len(self._timeframe_stats),
                "bot_pairs_tracked": len(self._bot_pair_stats),
            }

    @staticmethod
    def _conviction_bucket(conviction: float) -> str:
        """Map conviction to a bucket label."""
        if conviction < 0.25:
            return "0-25%"
        elif conviction < 0.50:
            return "25-50%"
        elif conviction < 0.70:
            return "50-70%"
        elif conviction < 0.85:
            return "70-85%"
        else:
            return "85-100%"

    @staticmethod
    def _bucket_midpoint(bucket: str) -> float:
        """Return the midpoint of a conviction bucket for calibration check."""
        midpoints = {
            "0-25%": 0.125,
            "25-50%": 0.375,
            "50-70%": 0.60,
            "70-85%": 0.775,
            "85-100%": 0.925,
        }
        return midpoints.get(bucket, 0.5)
