"""Daily market sentiment voting and prediction tracking service."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from google.cloud import firestore

logger = logging.getLogger(__name__)


class VotingService:
    def __init__(self):
        self.db = firestore.Client()

    async def submit_vote(
        self, uid: str, symbol: str, prediction: str, confidence: float
    ) -> Dict[str, Any]:
        """
        Submit a daily market prediction vote.

        Args:
            uid: User ID
            symbol: Trading symbol (e.g., 'BTCUSDT')
            prediction: 'bullish' | 'bearish' | 'neutral'
            confidence: 0.0 - 1.0

        Returns:
            Vote submission result with points awarded
        """
        # Validation
        if prediction not in ["bullish", "bearish", "neutral"]:
            return {"error": "Invalid prediction type"}

        if not (0.0 <= confidence <= 1.0):
            return {"error": "Confidence must be between 0.0 and 1.0"}

        # Check if user already voted for this symbol today
        today = datetime.now(timezone.utc).date().isoformat()
        existing_votes = (
            self.db.collection("daily_votes")
            .where("uid", "==", uid)
            .where("symbol", "==", symbol)
            .where("date", "==", today)
            .limit(1)
            .stream()
        )

        if list(existing_votes):
            return {"error": "Already voted for this symbol today"}

        # Get current price for later comparison
        from .credentials import CredentialManager
        from .exchange import AsterClient

        try:
            creds = CredentialManager().get_credentials()
            client = AsterClient(credentials=creds)
            ticker = await client.get_ticker(symbol)
            entry_price = float(ticker.get("lastPrice", 0))
        except Exception as e:
            logger.error(f"Failed to get price for {symbol}: {e}")
            entry_price = None

        # Create vote document
        vote_data = {
            "uid": uid,
            "symbol": symbol,
            "date": today,
            "prediction": prediction,
            "confidence": confidence,
            "voted_at": datetime.now(timezone.utc).isoformat(),
            "entry_price": entry_price,
            "scored": False,
            "correct": None,
            "points_awarded": 0,
        }

        self.db.collection("daily_votes").add(vote_data)

        # Award +5 points for voting
        user_ref = self.db.collection("users").document(uid)
        user_ref.update({"total_points": firestore.Increment(5)})

        # Record in points history
        self.db.collection("points_history").add(
            {
                "uid": uid,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "action": "vote_submitted",
                "points": 5,
                "reason": f"Voted {prediction} on {symbol}",
            }
        )

        logger.info(f"✅ Vote submitted: {uid} → {symbol} {prediction} ({confidence:.0%})")

        return {
            "success": True,
            "points_awarded": 5,
            "message": f"Vote recorded: {prediction} on {symbol}",
        }

    async def get_crowd_sentiment(self, symbol: str) -> Dict[str, Any]:
        """
        Get aggregated crowd sentiment for a symbol (today's votes).

        Returns:
            {
                symbol,
                bullish_pct,
                bearish_pct,
                neutral_pct,
                vote_count,
                avg_confidence
            }
        """
        today = datetime.now(timezone.utc).date().isoformat()

        votes = (
            self.db.collection("daily_votes")
            .where("symbol", "==", symbol)
            .where("date", "==", today)
            .stream()
        )

        bullish_count = 0
        bearish_count = 0
        neutral_count = 0
        total_confidence = 0.0
        total_votes = 0

        for vote in votes:
            vote_data = vote.to_dict()
            prediction = vote_data.get("prediction")
            confidence = vote_data.get("confidence", 0.5)

            if prediction == "bullish":
                bullish_count += 1
            elif prediction == "bearish":
                bearish_count += 1
            elif prediction == "neutral":
                neutral_count += 1

            total_confidence += confidence
            total_votes += 1

        if total_votes == 0:
            return {
                "symbol": symbol,
                "bullish_pct": 0.0,
                "bearish_pct": 0.0,
                "neutral_pct": 0.0,
                "vote_count": 0,
                "avg_confidence": 0.0,
            }

        return {
            "symbol": symbol,
            "bullish_pct": bullish_count / total_votes,
            "bearish_pct": bearish_count / total_votes,
            "neutral_pct": neutral_count / total_votes,
            "vote_count": total_votes,
            "avg_confidence": total_confidence / total_votes,
        }

    async def score_predictions(self) -> Dict[str, Any]:
        """
        Cron job to score yesterday's predictions.
        Compares 24h price movement vs user predictions.

        Awards:
        - +50 points for correct prediction
        - +100 points for high-confidence correct (>80%)
        """
        yesterday = (datetime.now(timezone.utc).date() - timedelta(days=1)).isoformat()

        # Get all unscored votes from yesterday
        votes = (
            self.db.collection("daily_votes")
            .where("date", "==", yesterday)
            .where("scored", "==", False)
            .stream()
        )

        scored_count = 0
        correct_count = 0
        points_awarded_total = 0

        from .credentials import CredentialManager
        from .exchange import AsterClient

        try:
            creds = CredentialManager().get_credentials()
            client = AsterClient(credentials=creds)
        except Exception as e:
            logger.error(f"Failed to initialize exchange client: {e}")
            return {"error": "Exchange client initialization failed"}

        for vote_doc in votes:
            vote_data = vote_doc.to_dict()
            symbol = vote_data.get("symbol")
            entry_price = vote_data.get("entry_price")
            prediction = vote_data.get("prediction")
            confidence = vote_data.get("confidence", 0.5)
            uid = vote_data.get("uid")

            if not entry_price:
                continue

            # Get current price
            try:
                ticker = await client.get_ticker(symbol)
                current_price = float(ticker.get("lastPrice", 0))
            except Exception as e:
                logger.error(f"Failed to get price for {symbol}: {e}")
                continue

            # Calculate price movement %
            price_change_pct = (current_price - entry_price) / entry_price

            # Determine if prediction was correct
            is_correct = False
            if prediction == "bullish" and price_change_pct > 0:
                is_correct = True
            elif prediction == "bearish" and price_change_pct < 0:
                is_correct = True
            elif prediction == "neutral" and abs(price_change_pct) < 0.02:  # ±2%
                is_correct = True

            # Award points
            points = 0
            if is_correct:
                correct_count += 1
                if confidence > 0.8:
                    points = 100  # High-confidence correct
                    logger.info(
                        f"🎯 {uid} HIGH-CONF CORRECT: {symbol} {prediction} ({confidence:.0%}) +100pts"
                    )
                else:
                    points = 50  # Regular correct
                    logger.info(f"✅ {uid} correct: {symbol} {prediction} +50pts")

                # Update user points
                user_ref = self.db.collection("users").document(uid)
                user_ref.update({"total_points": firestore.Increment(points)})

                # Record in points history
                self.db.collection("points_history").add(
                    {
                        "uid": uid,
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                        "action": "prediction_correct",
                        "points": points,
                        "reason": f"Correct prediction: {symbol} {prediction} ({price_change_pct:+.2%})",
                    }
                )

                points_awarded_total += points

            # Update vote as scored
            vote_doc.reference.update(
                {
                    "scored": True,
                    "correct": is_correct,
                    "points_awarded": points,
                    "exit_price": current_price,
                    "price_change_pct": price_change_pct,
                }
            )

            scored_count += 1

        logger.info(
            f"📊 Scored {scored_count} predictions: {correct_count} correct, {points_awarded_total} points awarded"
        )

        return {
            "scored_count": scored_count,
            "correct_count": correct_count,
            "points_awarded": points_awarded_total,
            "accuracy": (correct_count / scored_count * 100) if scored_count > 0 else 0,
        }


# Global instance
_voting_service: Optional[VotingService] = None


def get_voting_service() -> VotingService:
    """Get or create the global VotingService instance."""
    global _voting_service
    if _voting_service is None:
        _voting_service = VotingService()
        logger.info("📦 VotingService initialized")
    return _voting_service
