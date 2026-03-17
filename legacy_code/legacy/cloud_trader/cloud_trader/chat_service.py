"""
Community Chat Service
Handles live chat messages, ticker parsing, user profiles, and bot interaction.
"""

import logging
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Firestore collections
CHAT_MESSAGES_COLLECTION = "chat_messages"
USER_PROFILES_COLLECTION = "user_profiles"
CHAT_REACTIONS_COLLECTION = "chat_reactions"

# Ticker regex pattern (matches $BTC, $ETH, $XAUUSDT, etc.)
TICKER_PATTERN = re.compile(r"\$([A-Z]{2,10}(?:USDT)?)", re.IGNORECASE)

# Bot user IDs
BOT_USER_IDS = {
    "trend-momentum-agent": {"name": "Trend Bot", "avatar": "🚀"},
    "market-maker-agent": {"name": "Market Maker", "avatar": "💎"},
    "swing-trader-agent": {"name": "Swing Bot", "avatar": "🔄"},
    "sapphire-ai": {"name": "Sapphire AI", "avatar": "💠"},
}


@dataclass
class ChatMessage:
    """Represents a chat message with metadata."""

    id: str = ""
    user_id: str = ""
    username: str = ""
    display_name: str = ""
    avatar: str = ""
    content: str = ""
    tickers: List[str] = field(default_factory=list)
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    is_bot: bool = False
    bot_replied: bool = False
    points_awarded: int = 0
    award_reason: str = ""
    likes: int = 0
    liked_by: List[str] = field(default_factory=list)
    reply_to: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to Firestore-compatible dict."""
        return {
            "user_id": self.user_id,
            "username": self.username,
            "display_name": self.display_name,
            "avatar": self.avatar,
            "content": self.content,
            "tickers": self.tickers,
            "timestamp": self.timestamp,
            "is_bot": self.is_bot,
            "bot_replied": self.bot_replied,
            "points_awarded": self.points_awarded,
            "award_reason": self.award_reason,
            "likes": self.likes,
            "liked_by": self.liked_by,
            "reply_to": self.reply_to,
        }

    @classmethod
    def from_dict(cls, doc_id: str, data: Dict[str, Any]) -> "ChatMessage":
        """Create from Firestore document."""
        ts = data.get("timestamp")
        if hasattr(ts, "timestamp"):
            ts = datetime.fromtimestamp(ts.timestamp(), tz=timezone.utc)
        elif not isinstance(ts, datetime):
            ts = datetime.now(timezone.utc)

        return cls(
            id=doc_id,
            user_id=data.get("user_id", ""),
            username=data.get("username", "anonymous"),
            display_name=data.get("display_name", ""),
            avatar=data.get("avatar", "👤"),
            content=data.get("content", ""),
            tickers=data.get("tickers", []),
            timestamp=ts,
            is_bot=data.get("is_bot", False),
            bot_replied=data.get("bot_replied", False),
            points_awarded=data.get("points_awarded", 0),
            award_reason=data.get("award_reason", ""),
            likes=data.get("likes", 0),
            liked_by=data.get("liked_by", []),
            reply_to=data.get("reply_to"),
        )


@dataclass
class UserProfile:
    """User profile with username, alias, and stats."""

    uid: str = ""
    username: str = ""
    display_name: str = ""
    avatar_seed: str = ""
    bio: str = ""
    total_points: int = 0
    chat_points: int = 0
    messages_sent: int = 0
    bot_interactions: int = 0
    advice_taken: int = 0
    is_advisor: bool = False
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "uid": self.uid,
            "username": self.username,
            "display_name": self.display_name,
            "avatar_seed": self.avatar_seed,
            "bio": self.bio,
            "total_points": self.total_points,
            "chat_points": self.chat_points,
            "messages_sent": self.messages_sent,
            "bot_interactions": self.bot_interactions,
            "advice_taken": self.advice_taken,
            "is_advisor": self.is_advisor,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "UserProfile":
        ts = data.get("created_at")
        if hasattr(ts, "timestamp"):
            ts = datetime.fromtimestamp(ts.timestamp(), tz=timezone.utc)
        elif not isinstance(ts, datetime):
            ts = datetime.now(timezone.utc)

        return cls(
            uid=data.get("uid", ""),
            username=data.get("username", ""),
            display_name=data.get("display_name", ""),
            avatar_seed=data.get("avatar_seed", ""),
            bio=data.get("bio", ""),
            total_points=data.get("total_points", 0),
            chat_points=data.get("chat_points", 0),
            messages_sent=data.get("messages_sent", 0),
            bot_interactions=data.get("bot_interactions", 0),
            advice_taken=data.get("advice_taken", 0),
            is_advisor=data.get("is_advisor", False),
            created_at=ts,
        )


class ChatService:
    """
    Manages community chat with bot interaction.

    Features:
    - Real-time message storage in Firestore
    - Ticker mention detection ($BTC, $ETH, etc.)
    - Bot message posting
    - Point awarding for good advice
    - User profile management
    """

    def __init__(self, db=None):
        """Initialize with Firestore database reference."""
        self.db = db
        self._recent_messages_cache: List[ChatMessage] = []
        self._cache_timestamp = None

    def _get_db(self):
        """Lazy load Firestore if not provided."""
        if self.db is None:
            try:
                from google.cloud import firestore

                self.db = firestore.Client()
            except Exception as e:
                logger.error(f"Failed to initialize Firestore: {e}")
                raise
        return self.db

    def parse_tickers(self, content: str) -> List[str]:
        """Extract ticker mentions from message content."""
        matches = TICKER_PATTERN.findall(content)
        # Normalize to uppercase and add USDT if not present
        tickers = []
        for match in matches:
            ticker = match.upper()
            if not ticker.endswith("USDT"):
                ticker = f"{ticker}USDT"
            if ticker not in tickers:
                tickers.append(ticker)
        return tickers

    async def send_message(
        self,
        user_id: str,
        username: str,
        content: str,
        display_name: str = "",
        avatar: str = "👤",
        reply_to: str = None,
    ) -> ChatMessage:
        """
        Send a chat message.

        Args:
            user_id: Firebase UID or bot ID
            username: Display username
            content: Message content
            display_name: Optional alias
            avatar: Emoji or URL
            reply_to: Optional message ID to reply to

        Returns:
            Created ChatMessage
        """
        db = self._get_db()

        # Parse tickers from content
        tickers = self.parse_tickers(content)

        # Check if this is a bot message
        is_bot = user_id in BOT_USER_IDS

        message = ChatMessage(
            user_id=user_id,
            username=username,
            display_name=display_name or username,
            avatar=avatar,
            content=content,
            tickers=tickers,
            is_bot=is_bot,
            reply_to=reply_to,
        )

        # Store in Firestore
        doc_ref = db.collection(CHAT_MESSAGES_COLLECTION).document()
        doc_ref.set(message.to_dict())
        message.id = doc_ref.id

        # Update user stats
        if not is_bot:
            await self._increment_user_messages(user_id)

        logger.info(f"Chat message sent: {username} - {content[:50]}... (tickers: {tickers})")

        return message

    async def send_bot_message(
        self,
        bot_id: str,
        content: str,
        reply_to: str = None,
    ) -> ChatMessage:
        """Send a message from a bot."""
        bot_info = BOT_USER_IDS.get(bot_id, {"name": "Bot", "avatar": "🤖"})

        return await self.send_message(
            user_id=bot_id,
            username=bot_info["name"],
            content=content,
            avatar=bot_info["avatar"],
            reply_to=reply_to,
        )

    async def get_messages(
        self,
        limit: int = 50,
        before_timestamp: datetime = None,
    ) -> List[ChatMessage]:
        """Get recent chat messages."""
        db = self._get_db()

        query = (
            db.collection(CHAT_MESSAGES_COLLECTION)
            .order_by("timestamp", direction="DESCENDING")
            .limit(limit)
        )

        if before_timestamp:
            query = query.where("timestamp", "<", before_timestamp)

        docs = query.stream()

        messages = [ChatMessage.from_dict(doc.id, doc.to_dict()) for doc in docs]

        # Return in chronological order
        return list(reversed(messages))

    async def get_messages_with_ticker(self, ticker: str, limit: int = 20) -> List[ChatMessage]:
        """Get messages mentioning a specific ticker."""
        db = self._get_db()

        ticker_normalized = ticker.upper()
        if not ticker_normalized.endswith("USDT"):
            ticker_normalized = f"{ticker_normalized}USDT"

        query = (
            db.collection(CHAT_MESSAGES_COLLECTION)
            .where("tickers", "array_contains", ticker_normalized)
            .order_by("timestamp", direction="DESCENDING")
            .limit(limit)
        )

        docs = query.stream()

        return [ChatMessage.from_dict(doc.id, doc.to_dict()) for doc in docs]

    async def like_message(self, message_id: str, user_id: str) -> bool:
        """Like a message. Returns True if newly liked, False if already liked."""
        db = self._get_db()

        doc_ref = db.collection(CHAT_MESSAGES_COLLECTION).document(message_id)
        doc = doc_ref.get()

        if not doc.exists:
            return False

        data = doc.to_dict()
        liked_by = data.get("liked_by", [])

        if user_id in liked_by:
            return False

        # Add like
        doc_ref.update(
            {
                "likes": data.get("likes", 0) + 1,
                "liked_by": liked_by + [user_id],
            }
        )

        return True

    async def award_points(
        self,
        message_id: str,
        points: int,
        reason: str,
        bot_id: str = "sapphire-ai",
    ) -> bool:
        """
        Award points to a message author for good advice.

        Args:
            message_id: The message that earned points
            points: Number of points to award
            reason: Why points were awarded
            bot_id: Which bot is awarding

        Returns:
            True if successfully awarded
        """
        db = self._get_db()

        doc_ref = db.collection(CHAT_MESSAGES_COLLECTION).document(message_id)
        doc = doc_ref.get()

        if not doc.exists:
            logger.warning(f"Message {message_id} not found for point award")
            return False

        data = doc.to_dict()
        user_id = data.get("user_id")

        if not user_id or user_id in BOT_USER_IDS:
            return False

        # Update message with award
        doc_ref.update(
            {
                "points_awarded": data.get("points_awarded", 0) + points,
                "award_reason": reason,
                "bot_replied": True,
            }
        )

        # Update user's chat points
        await self._add_chat_points(user_id, points)

        # Send bot acknowledgment
        username = data.get("username", "user")
        await self.send_bot_message(
            bot_id=bot_id,
            content=f"🎉 @{username} earned **+{points} pts** - {reason}",
            reply_to=message_id,
        )

        logger.info(f"Awarded {points} points to {user_id} for message {message_id}: {reason}")

        return True

    async def _increment_user_messages(self, user_id: str):
        """Increment user's message count."""
        db = self._get_db()

        doc_ref = db.collection(USER_PROFILES_COLLECTION).document(user_id)
        doc = doc_ref.get()

        if doc.exists:
            from google.cloud.firestore import Increment

            doc_ref.update({"messages_sent": Increment(1)})

    async def _add_chat_points(self, user_id: str, points: int):
        """Add chat points to user profile."""
        db = self._get_db()

        doc_ref = db.collection(USER_PROFILES_COLLECTION).document(user_id)
        doc = doc_ref.get()

        if doc.exists:
            from google.cloud.firestore import Increment

            doc_ref.update(
                {
                    "chat_points": Increment(points),
                    "total_points": Increment(points),
                    "advice_taken": Increment(1),
                }
            )

    # ============ User Profile Management ============

    async def get_or_create_profile(
        self,
        uid: str,
        username: str = None,
        display_name: str = None,
    ) -> UserProfile:
        """Get or create a user profile."""
        db = self._get_db()

        doc_ref = db.collection(USER_PROFILES_COLLECTION).document(uid)
        doc = doc_ref.get()

        if doc.exists:
            return UserProfile.from_dict(doc.to_dict())

        # Create new profile
        import hashlib

        avatar_seed = hashlib.sha256(uid.encode()).hexdigest()[:8]

        profile = UserProfile(
            uid=uid,
            username=username or f"user_{avatar_seed}",
            display_name=display_name or username or f"User {avatar_seed[:4]}",
            avatar_seed=avatar_seed,
        )

        doc_ref.set(profile.to_dict())

        logger.info(f"Created new user profile: {profile.username}")

        return profile

    async def update_profile(
        self,
        uid: str,
        username: str = None,
        display_name: str = None,
        bio: str = None,
    ) -> UserProfile:
        """Update user profile fields."""
        db = self._get_db()

        doc_ref = db.collection(USER_PROFILES_COLLECTION).document(uid)

        updates = {}
        if username is not None:
            # Check username uniqueness
            existing = (
                db.collection(USER_PROFILES_COLLECTION)
                .where("username", "==", username)
                .limit(1)
                .stream()
            )

            for doc in existing:
                if doc.id != uid:
                    raise ValueError(f"Username '{username}' is already taken")

            updates["username"] = username

        if display_name is not None:
            updates["display_name"] = display_name

        if bio is not None:
            updates["bio"] = bio

        if updates:
            doc_ref.update(updates)

        return await self.get_or_create_profile(uid)

    async def check_username_available(self, username: str) -> bool:
        """Check if a username is available."""
        db = self._get_db()

        docs = (
            db.collection(USER_PROFILES_COLLECTION)
            .where("username", "==", username)
            .limit(1)
            .stream()
        )

        return not any(docs)


# Singleton instance
_chat_service: Optional[ChatService] = None


def get_chat_service() -> ChatService:
    """Get the singleton ChatService instance."""
    global _chat_service
    if _chat_service is None:
        _chat_service = ChatService()
    return _chat_service
