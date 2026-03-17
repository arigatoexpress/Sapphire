"""User management service for authentication and profile operations."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

from google.cloud import firestore

logger = logging.getLogger(__name__)


class UserService:
    def __init__(self):
        self.db = firestore.Client()

    async def create_user_profile(self, uid: str, email: str) -> Dict[str, Any]:
        """Initialize new user profile on first login."""
        user_ref = self.db.collection("users").document(uid)

        # Check if user already exists
        if user_ref.get().exists:
            logger.info(f"User {uid} already exists")
            return user_ref.get().to_dict()

        # Create new user profile
        user_data = {
            "uid": uid,
            "email": email,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "total_points": 0,
            "streak_days": 0,
            "last_checkin": None,
            "rank": None,
        }

        user_ref.set(user_data)
        logger.info(f"✅ Created new user profile: {email}")

        return user_data

    async def get_user_stats(self, uid: str) -> Dict[str, Any]:
        """Fetch user's points, streak, rank, and stats."""
        user_ref = self.db.collection("users").document(uid)
        user_doc = user_ref.get()

        if not user_doc.exists:
            return {"error": "User not found"}

        user_data = user_doc.to_dict()

        # Calculate rank (number of users with more points + 1)
        users_with_more_points = (
            self.db.collection("users")
            .where("total_points", ">", user_data["total_points"])
            .count()
            .get()
        )
        rank = users_with_more_points[0][0].value + 1

        # Get prediction accuracy
        votes = self.db.collection("daily_votes").where("uid", "==", uid).stream()
        total_votes = 0
        correct_votes = 0

        for vote in votes:
            vote_data = vote.to_dict()
            if vote_data.get("scored"):
                total_votes += 1
                if vote_data.get("correct"):
                    correct_votes += 1

        accuracy = (correct_votes / total_votes * 100) if total_votes > 0 else 0

        return {
            "uid": uid,
            "email": user_data.get("email"),
            "total_points": user_data.get("total_points", 0),
            "streak_days": user_data.get("streak_days", 0),
            "rank": rank,
            "total_votes": total_votes,
            "accuracy": accuracy,
            "last_checkin": user_data.get("last_checkin"),
        }

    async def record_daily_checkin(self, uid: str) -> Dict[str, Any]:
        """Award +10 points for daily login and update streak."""
        user_ref = self.db.collection("users").document(uid)
        user_doc = user_ref.get()

        if not user_doc.exists:
            return {"error": "User not found"}

        user_data = user_doc.to_dict()
        last_checkin = user_data.get("last_checkin")

        # Check if already checked in today
        if last_checkin:
            last_checkin_date = datetime.fromisoformat(last_checkin).date()
            today = datetime.now(timezone.utc).date()

            if last_checkin_date == today:
                return {"message": "Already checked in today", "points_awarded": 0}

            # Check if streak continues (checked in yesterday)
            yesterday = today - timedelta(days=1)
            if last_checkin_date == yesterday:
                # Continue streak
                new_streak = user_data.get("streak_days", 0) + 1
            else:
                # Streak broken, reset to 1
                new_streak = 1
        else:
            # First check-in
            new_streak = 1

        # Award points
        points_awarded = 10

        # Bonus for 7-day streak
        if new_streak % 7 == 0:
            points_awarded += 150
            logger.info(f"🔥 {uid} hit {new_streak}-day streak! Bonus +150 points")

        # Update user
        user_ref.update(
            {
                "total_points": firestore.Increment(points_awarded),
                "streak_days": new_streak,
                "last_checkin": datetime.now(timezone.utc).isoformat(),
            }
        )

        # Record in points history
        self.db.collection("points_history").add(
            {
                "uid": uid,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "action": "daily_checkin",
                "points": points_awarded,
                "reason": f"Daily check-in (Streak: {new_streak})",
            }
        )

        logger.info(f"✅ {uid} checked in: +{points_awarded} points (Streak: {new_streak})")

        return {
            "points_awarded": points_awarded,
            "new_total": user_data.get("total_points", 0) + points_awarded,
            "streak_days": new_streak,
        }


# Global instance
_user_service: Optional[UserService] = None


def get_user_service() -> UserService:
    """Get or create the global UserService instance."""
    global _user_service
    if _user_service is None:
        _user_service = UserService()
        logger.info("📦 UserService initialized")
    return _user_service
