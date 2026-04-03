"""Bot Reputation & Points System — Phase 4 Swarm Intelligence.

Tracks contributing agents/bots by:
- Ideas submitted (count)
- Accuracy (% of predictions that were correct)
- Profitability (average P&L of executed ideas)
- Info quality (forum quality ratings aggregated)
- Total reputation score (weighted composite)

Supports: reward, penalize, ban, leaderboard, reputation-weighted aggregation.
"""

import json
import os
import threading
import time
from pathlib import Path
from typing import Any

from loguru import logger


class BotReputationService:
    """Manages reputation scores for contributing agents and external bots."""

    # Weight factors for composite reputation score
    WEIGHTS = {
        "accuracy": 0.35,       # How often ideas are correct
        "profitability": 0.30,  # Average P&L of executed ideas
        "quality": 0.20,        # Forum quality ratings
        "consistency": 0.15,    # Frequency & reliability of contributions
    }

    # Reputation thresholds
    BAN_THRESHOLD = -50.0       # Auto-ban below this score
    TRUSTED_THRESHOLD = 100.0   # Elevated trust above this score
    DEFAULT_SCORE = 10.0        # Starting reputation for new bots

    # Points for actions
    POINTS = {
        "idea_submitted": 1.0,
        "idea_accurate": 10.0,
        "idea_inaccurate": -3.0,
        "idea_profitable": 15.0,
        "idea_unprofitable": -5.0,
        "quality_bonus": 5.0,       # High-quality contribution
        "quality_penalty": -2.0,    # Low-quality contribution
        "spam_penalty": -20.0,      # Detected spam/injection
        "malicious_ban": -100.0,    # Immediate ban for malicious activity
    }

    def __init__(self, store_path: str = ""):
        self._store_path = store_path or os.getenv(
            "SAPPHIRE_REPUTATION_STORE_PATH",
            str(Path(__file__).parent / "reputation_store.json"),
        )
        self._lock = threading.Lock()
        self._bots: dict[str, dict[str, Any]] = {}
        self._load()

    def _load(self) -> None:
        try:
            path = Path(self._store_path)
            if path.exists():
                data = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(data, dict) and "bots" in data:
                    self._bots = data["bots"]
        except Exception as exc:
            logger.warning(f"Reputation store load failed: {exc}")

    def _save_locked(self) -> None:
        try:
            path = Path(self._store_path)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(
                json.dumps({"bots": self._bots, "saved_at": int(time.time())}, indent=2),
                encoding="utf-8",
            )
        except Exception as exc:
            logger.warning(f"Reputation store save failed: {exc}")

    def _ensure_bot(self, bot_id: str) -> dict[str, Any]:
        """Get or create a bot reputation record."""
        key = str(bot_id or "").strip().upper()
        if key not in self._bots:
            self._bots[key] = {
                "bot_id": key,
                "score": self.DEFAULT_SCORE,
                "ideas_submitted": 0,
                "ideas_accurate": 0,
                "ideas_inaccurate": 0,
                "ideas_profitable": 0,
                "ideas_unprofitable": 0,
                "total_pnl": 0.0,
                "quality_sum": 0.0,
                "quality_count": 0,
                "penalties": 0,
                "rewards": 0,
                "status": "active",  # active | warned | banned
                "ban_reason": "",
                "registered_at": int(time.time()),
                "last_activity_at": int(time.time()),
                "history": [],  # Recent score changes [{action, points, timestamp}]
            }
        return self._bots[key]

    def _record_history(self, bot: dict[str, Any], action: str, points: float) -> None:
        """Append to score history (max 50 entries)."""
        history = bot.setdefault("history", [])
        history.append({
            "action": action,
            "points": points,
            "timestamp": int(time.time()),
        })
        if len(history) > 50:
            bot["history"] = history[-50:]

    def _compute_composite_score(self, bot: dict[str, Any]) -> float:
        """Compute the weighted composite reputation score."""
        total_ideas = bot.get("ideas_submitted", 0)
        if total_ideas == 0:
            return bot.get("score", self.DEFAULT_SCORE)

        accurate = bot.get("ideas_accurate", 0)
        inaccurate = bot.get("ideas_inaccurate", 0)
        evaluated = accurate + inaccurate
        accuracy_pct = (accurate / evaluated * 100) if evaluated > 0 else 50.0

        profitable = bot.get("ideas_profitable", 0)
        unprofitable = bot.get("ideas_unprofitable", 0)
        profit_evaluated = profitable + unprofitable
        profit_pct = (profitable / profit_evaluated * 100) if profit_evaluated > 0 else 50.0

        quality_count = bot.get("quality_count", 0)
        avg_quality = (bot.get("quality_sum", 0) / quality_count * 100) if quality_count > 0 else 50.0

        # Consistency: ideas per day since registration
        registered_at = bot.get("registered_at", int(time.time()))
        days_active = max(1, (int(time.time()) - registered_at) / 86400)
        consistency = min(100.0, (total_ideas / days_active) * 20)  # 5 ideas/day = 100

        composite = (
            self.WEIGHTS["accuracy"] * accuracy_pct
            + self.WEIGHTS["profitability"] * profit_pct
            + self.WEIGHTS["quality"] * avg_quality
            + self.WEIGHTS["consistency"] * consistency
        )
        return round(composite, 2)

    # ── Public API ─────────────────────────────────────────────────

    def get_reputation(self, bot_id: str) -> dict[str, Any]:
        """Get a bot's full reputation record."""
        with self._lock:
            key = str(bot_id or "").strip().upper()
            if key not in self._bots:
                return {"ok": False, "error": "bot_not_found"}
            bot = self._bots[key]
            return {
                "ok": True,
                "bot_id": key,
                "score": bot.get("score", 0),
                "composite": self._compute_composite_score(bot),
                "status": bot.get("status", "active"),
                "ideas_submitted": bot.get("ideas_submitted", 0),
                "ideas_accurate": bot.get("ideas_accurate", 0),
                "ideas_inaccurate": bot.get("ideas_inaccurate", 0),
                "ideas_profitable": bot.get("ideas_profitable", 0),
                "ideas_unprofitable": bot.get("ideas_unprofitable", 0),
                "total_pnl": bot.get("total_pnl", 0.0),
                "quality_avg": (
                    bot.get("quality_sum", 0) / bot.get("quality_count", 1)
                    if bot.get("quality_count", 0) > 0
                    else 0.0
                ),
                "penalties": bot.get("penalties", 0),
                "rewards": bot.get("rewards", 0),
                "ban_reason": bot.get("ban_reason", ""),
                "registered_at": bot.get("registered_at", 0),
                "last_activity_at": bot.get("last_activity_at", 0),
            }

    def record_idea(self, bot_id: str, idea_id: str = "") -> dict[str, Any]:
        """Record that a bot submitted a trade idea."""
        with self._lock:
            bot = self._ensure_bot(bot_id)
            if bot.get("status") == "banned":
                return {"ok": False, "error": "bot_is_banned", "ban_reason": bot.get("ban_reason", "")}
            bot["ideas_submitted"] = bot.get("ideas_submitted", 0) + 1
            bot["score"] = bot.get("score", 0) + self.POINTS["idea_submitted"]
            bot["last_activity_at"] = int(time.time())
            self._record_history(bot, "idea_submitted", self.POINTS["idea_submitted"])
            self._save_locked()
            return {"ok": True, "score": bot["score"], "ideas_submitted": bot["ideas_submitted"]}

    def record_outcome(
        self, bot_id: str, accurate: bool, profitable: bool, pnl: float = 0.0
    ) -> dict[str, Any]:
        """Record the outcome of a trade idea (after execution/validation)."""
        with self._lock:
            bot = self._ensure_bot(bot_id)
            if accurate:
                bot["ideas_accurate"] = bot.get("ideas_accurate", 0) + 1
                bot["score"] = bot.get("score", 0) + self.POINTS["idea_accurate"]
                self._record_history(bot, "idea_accurate", self.POINTS["idea_accurate"])
            else:
                bot["ideas_inaccurate"] = bot.get("ideas_inaccurate", 0) + 1
                bot["score"] = bot.get("score", 0) + self.POINTS["idea_inaccurate"]
                self._record_history(bot, "idea_inaccurate", self.POINTS["idea_inaccurate"])

            if profitable:
                bot["ideas_profitable"] = bot.get("ideas_profitable", 0) + 1
                bot["score"] = bot.get("score", 0) + self.POINTS["idea_profitable"]
                self._record_history(bot, "idea_profitable", self.POINTS["idea_profitable"])
            else:
                bot["ideas_unprofitable"] = bot.get("ideas_unprofitable", 0) + 1
                bot["score"] = bot.get("score", 0) + self.POINTS["idea_unprofitable"]
                self._record_history(bot, "idea_unprofitable", self.POINTS["idea_unprofitable"])

            bot["total_pnl"] = bot.get("total_pnl", 0.0) + float(pnl)
            bot["last_activity_at"] = int(time.time())

            # Auto-ban check
            if bot["score"] <= self.BAN_THRESHOLD:
                bot["status"] = "banned"
                bot["ban_reason"] = f"Auto-banned: score dropped to {bot['score']}"

            self._save_locked()
            return {
                "ok": True,
                "score": bot["score"],
                "status": bot.get("status", "active"),
                "composite": self._compute_composite_score(bot),
            }

    def record_quality(self, bot_id: str, quality_score: float) -> dict[str, Any]:
        """Record a quality rating (0.0–1.0) for a bot's contribution."""
        with self._lock:
            bot = self._ensure_bot(bot_id)
            q = max(0.0, min(1.0, float(quality_score)))
            bot["quality_sum"] = bot.get("quality_sum", 0.0) + q
            bot["quality_count"] = bot.get("quality_count", 0) + 1

            if q >= 0.7:
                bot["score"] = bot.get("score", 0) + self.POINTS["quality_bonus"]
                bot["rewards"] = bot.get("rewards", 0) + 1
                self._record_history(bot, "quality_bonus", self.POINTS["quality_bonus"])
            elif q <= 0.3:
                bot["score"] = bot.get("score", 0) + self.POINTS["quality_penalty"]
                bot["penalties"] = bot.get("penalties", 0) + 1
                self._record_history(bot, "quality_penalty", self.POINTS["quality_penalty"])

            bot["last_activity_at"] = int(time.time())
            self._save_locked()
            return {
                "ok": True,
                "score": bot["score"],
                "quality_avg": bot["quality_sum"] / bot["quality_count"],
            }

    def penalize(self, bot_id: str, reason: str, points: float = 0.0) -> dict[str, Any]:
        """Apply a penalty to a bot."""
        with self._lock:
            bot = self._ensure_bot(bot_id)
            penalty = points if points < 0 else self.POINTS["spam_penalty"]
            bot["score"] = bot.get("score", 0) + penalty
            bot["penalties"] = bot.get("penalties", 0) + 1
            bot["last_activity_at"] = int(time.time())
            self._record_history(bot, f"penalty:{reason[:40]}", penalty)

            if bot["score"] <= self.BAN_THRESHOLD:
                bot["status"] = "banned"
                bot["ban_reason"] = reason
            elif bot["penalties"] >= 5 and bot.get("status") != "banned":
                bot["status"] = "warned"

            self._save_locked()
            return {"ok": True, "score": bot["score"], "status": bot["status"]}

    def ban(self, bot_id: str, reason: str) -> dict[str, Any]:
        """Permanently ban a bot."""
        with self._lock:
            bot = self._ensure_bot(bot_id)
            bot["score"] = bot.get("score", 0) + self.POINTS["malicious_ban"]
            bot["status"] = "banned"
            bot["ban_reason"] = str(reason)[:200]
            bot["last_activity_at"] = int(time.time())
            self._record_history(bot, "banned", self.POINTS["malicious_ban"])
            self._save_locked()
            return {"ok": True, "score": bot["score"], "status": "banned", "reason": reason}

    def leaderboard(self, limit: int = 20) -> list[dict[str, Any]]:
        """Return top bots sorted by composite reputation score."""
        with self._lock:
            entries = []
            for key, bot in self._bots.items():
                if bot.get("status") == "banned":
                    continue
                entries.append({
                    "bot_id": key,
                    "score": bot.get("score", 0),
                    "composite": self._compute_composite_score(bot),
                    "ideas_submitted": bot.get("ideas_submitted", 0),
                    "ideas_accurate": bot.get("ideas_accurate", 0),
                    "status": bot.get("status", "active"),
                    "total_pnl": bot.get("total_pnl", 0.0),
                })
            entries.sort(key=lambda e: e["composite"], reverse=True)
            return entries[:limit]

    def reputation_weight(self, bot_id: str) -> float:
        """Return a 0.0–1.0 weight for reputation-weighted aggregation.

        Used to weight trade ideas from this bot when aggregating swarm signals.
        """
        with self._lock:
            key = str(bot_id or "").strip().upper()
            if key not in self._bots:
                return 0.1  # Unknown bot gets minimal weight
            bot = self._bots[key]
            if bot.get("status") == "banned":
                return 0.0
            composite = self._compute_composite_score(bot)
            # Normalize composite (0–100) to 0.0–1.0 range
            return max(0.05, min(1.0, composite / 100.0))

    def is_banned(self, bot_id: str) -> bool:
        """Check if a bot is banned."""
        with self._lock:
            key = str(bot_id or "").strip().upper()
            bot = self._bots.get(key)
            return bot.get("status") == "banned" if bot else False

    def bot_count(self) -> dict[str, int]:
        """Return count of bots by status."""
        with self._lock:
            counts: dict[str, int] = {"active": 0, "warned": 0, "banned": 0}
            for bot in self._bots.values():
                status = bot.get("status", "active")
                counts[status] = counts.get(status, 0) + 1
            return counts
