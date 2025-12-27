"""Points system and leaderboard rankings."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from google.cloud import firestore

logger = logging.getLogger(__name__)


class PointsSystem:
    """Gamification rewards engine."""

    # Point awards
    DAILY_CHECKIN = 10
    VOTE_SUBMITTED = 5
    CORRECT_PREDICTION = 50
    HIGH_CONFIDENCE_CORRECT = 100  # >80% confidence
    STREAK_7_DAYS = 150
    TOP_10_MONTHLY = 500

    def __init__(self):
        self.db = firestore.Client()

    async def get_leaderboard(
        self, timeframe: str = "all", limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        Get leaderboard rankings.

        Args:
            timeframe: 'all' | 'monthly' | 'accuracy'
            limit: Max number of results (default 100)

        Returns:
            List of user rankings with stats
        """
        if timeframe == "all":
            return await self._get_all_time_leaderboard(limit)
        elif timeframe == "monthly":
            return await self._get_monthly_leaderboard(limit)
        elif timeframe == "accuracy":
            return await self._get_accuracy_leaderboard(limit)
        else:
            return {"error": f"Invalid timeframe: {timeframe}"}

    async def _get_all_time_leaderboard(self, limit: int) -> List[Dict[str, Any]]:
        """Get all-time points leaders."""
        users = (
            self.db.collection("users")
            .order_by("total_points", direction=firestore.Query.DESCENDING)
            .limit(limit)
            .stream()
        )

        leaderboard = []
        rank = 1

        for user_doc in users:
            user_data = user_doc.to_dict()
            leaderboard.append(
                {
                    "rank": rank,
                    "email": user_data.get("email", "Anonymous"),
                    "total_points": user_data.get("total_points", 0),
                    "streak_days": user_data.get("streak_days", 0),
                    "created_at": user_data.get("created_at"),
                }
            )
            rank += 1

        return leaderboard

    async def _get_monthly_leaderboard(self, limit: int) -> List[Dict[str, Any]]:
        """Get this month's top performers based on points earned this month."""
        # Get current month's points from points_history
        now = datetime.utcnow()
        month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0).isoformat()

        # Aggregate points by user for this month
        points_by_user: Dict[str, int] = {}

        history = (
            self.db.collection("points_history").where("timestamp", ">=", month_start).stream()
        )

        for record in history:
            data = record.to_dict()
            uid = data.get("uid")
            points = data.get("points", 0)

            if uid:
                points_by_user[uid] = points_by_user.get(uid, 0) + points

        # Sort by points
        sorted_users = sorted(points_by_user.items(), key=lambda x: x[1], reverse=True)[:limit]

        # Get user details
        leaderboard = []
        rank = 1

        for uid, monthly_points in sorted_users:
            user_ref = self.db.collection("users").document(uid)
            user_doc = user_ref.get()

            if user_doc.exists:
                user_data = user_doc.to_dict()
                leaderboard.append(
                    {
                        "rank": rank,
                        "email": user_data.get("email", "Anonymous"),
                        "monthly_points": monthly_points,
                        "total_points": user_data.get("total_points", 0),
                        "streak_days": user_data.get("streak_days", 0),
                    }
                )
                rank += 1

        return leaderboard

    async def _get_accuracy_leaderboard(self, limit: int) -> List[Dict[str, Any]]:
        """Get highest prediction accuracy (minimum 30 votes)."""
        MIN_VOTES = 30

        # Get all users' vote accuracy
        users = self.db.collection("users").stream()

        user_stats = []

        for user_doc in users:
            user_data = user_doc.to_dict()
            uid = user_data.get("uid")

            # Count votes and correct predictions
            votes = (
                self.db.collection("daily_votes")
                .where("uid", "==", uid)
                .where("scored", "==", True)
                .stream()
            )

            total_votes = 0
            correct_votes = 0

            for vote_doc in votes:
                vote_data = vote_doc.to_dict()
                total_votes += 1
                if vote_data.get("correct"):
                    correct_votes += 1

            # Only include users with minimum votes
            if total_votes >= MIN_VOTES:
                accuracy = (correct_votes / total_votes * 100) if total_votes > 0 else 0
                user_stats.append(
                    {
                        "email": user_data.get("email", "Anonymous"),
                        "accuracy": accuracy,
                        "total_votes": total_votes,
                        "correct_votes": correct_votes,
                        "total_points": user_data.get("total_points", 0),
                    }
                )

        # Sort by accuracy
        sorted_users = sorted(user_stats, key=lambda x: x["accuracy"], reverse=True)[:limit]

        # Add ranks
        leaderboard = []
        rank = 1
        for user in sorted_users:
            user["rank"] = rank
            leaderboard.append(user)
            rank += 1

        return leaderboard

    async def get_streak_leaderboard(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Get users with longest consecutive daily check-in streaks."""
        users = (
            self.db.collection("users")
            .order_by("streak_days", direction=firestore.Query.DESCENDING)
            .limit(limit)
            .stream()
        )

        leaderboard = []
        rank = 1

        for user_doc in users:
            user_data = user_doc.to_dict()
            if user_data.get("streak_days", 0) > 0:  # Only show active streaks
                leaderboard.append(
                    {
                        "rank": rank,
                        "email": user_data.get("email", "Anonymous"),
                        "streak_days": user_data.get("streak_days", 0),
                        "total_points": user_data.get("total_points", 0),
                        "last_checkin": user_data.get("last_checkin"),
                    }
                )
                rank += 1

        return leaderboard


# Global instance
_points_system: Optional[PointsSystem] = None


def get_points_system() -> PointsSystem:
    """Get or create the global PointsSystem instance."""
    global _points_system
    if _points_system is None:
        _points_system = PointsSystem()
        logger.info("📦 PointsSystem initialized")
    return _points_system
