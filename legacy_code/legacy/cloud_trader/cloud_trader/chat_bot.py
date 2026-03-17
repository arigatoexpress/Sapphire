"""
Trading Chat Bot
Analyzes chat messages, responds to mentions, awards points for good advice,
and tracks profitable trade suggestions.
"""

import asyncio
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# Point values for different achievements
POINTS = {
    "message_sent": 2,  # Base points for sending a message
    "ticker_mention": 5,  # Bonus for mentioning a tradeable ticker
    "bot_interaction": 10,  # Direct @bot mention
    "advice_considered": 25,  # Bot considered the advice
    "advice_taken": 50,  # Bot acted on the advice
    "profitable_advice": 100,  # Advice led to profitable trade
    "high_profit_advice": 250,  # Advice led to >5% profit
    "streak_bonus": 15,  # Daily participation streak
}

# Bot response templates
RESPONSES = {
    "considering": [
        "🤔 Interesting perspective on ${ticker}! I'm analyzing this...",
        "💡 I see your point about ${ticker}. Let me run this through my models.",
        "📊 {username}, the ${ticker} analysis is intriguing. Checking market conditions...",
    ],
    "agreed": [
        "✅ @{username} I agree with your ${ticker} thesis! Opening position...",
        "🎯 Great call on ${ticker}, @{username}! Your analysis aligns with my signals.",
        "💎 @{username}'s ${ticker} insight confirmed by consensus. Executing!",
    ],
    "disagreed": [
        "⚠️ @{username}, my models show different signals for ${ticker} right now.",
        "🔄 Interesting take on ${ticker}, but current conditions suggest otherwise.",
        "📉 @{username}, the ${ticker} setup doesn't meet my entry criteria yet.",
    ],
    "profitable": [
        "🎉 WINNER! @{username}'s ${ticker} advice resulted in +{profit_pct}% profit! +{points} pts awarded!",
        "💰 @{username} called it! ${ticker} trade closed at +{profit_pct}%. You earned +{points} bonus points!",
        "🏆 Your ${ticker} suggestion paid off, @{username}! +{profit_pct}% profit = +{points} points!",
    ],
    "loss": [
        "📈 ${ticker} trade closed at {profit_pct}%. Markets are unpredictable - keep sharing insights!",
    ],
}


@dataclass
class TradeAdvice:
    """Tracks a piece of advice linked to a trade."""

    message_id: str
    user_id: str
    username: str
    ticker: str
    direction: str  # "long" or "short"
    timestamp: datetime
    trade_id: Optional[str] = None
    trade_entry_price: Optional[float] = None
    trade_exit_price: Optional[float] = None
    trade_pnl: Optional[float] = None
    trade_pnl_percent: Optional[float] = None
    points_awarded: int = 0
    resolved: bool = False


class TradingChatBot:
    """
    Bot that interacts with community chat, analyzes suggestions,
    and awards points for profitable advice.

    Features:
    - Monitors chat for ticker mentions
    - Responds to @bot mentions
    - Tracks which advice influenced trades
    - Awards bonus points for profitable suggestions
    - Posts trade outcomes back to chat
    """

    def __init__(self, chat_service=None):
        self.chat_service = chat_service
        self._pending_advice: Dict[str, TradeAdvice] = {}  # ticker -> advice
        self._recent_suggestions: List[TradeAdvice] = []
        self._last_analysis_time = None
        self.bot_id = "sapphire-ai"

    def _get_chat_service(self):
        """Lazy load chat service."""
        if self.chat_service is None:
            from .chat_service import get_chat_service

            self.chat_service = get_chat_service()
        return self.chat_service

    def _pick_response(self, category: str, **kwargs) -> str:
        """Pick a random response template and fill in variables."""
        import random

        templates = RESPONSES.get(category, ["Response not configured."])
        template = random.choice(templates)
        return template.format(**kwargs)

    async def analyze_recent_messages(self, limit: int = 20) -> List[Dict[str, Any]]:
        """
        Analyze recent chat messages for trading suggestions.

        Returns list of parsed suggestions with:
        - ticker: The mentioned ticker
        - direction: Inferred direction (long/short)
        - confidence: How confident the suggestion seems
        - message_id: Source message
        - user_id: Who suggested
        """
        chat = self._get_chat_service()
        messages = await chat.get_messages(limit=limit)

        suggestions = []

        for msg in messages:
            if msg.is_bot:
                continue

            if not msg.tickers:
                continue

            # Analyze sentiment of the message
            direction, confidence = self._parse_direction(msg.content)

            for ticker in msg.tickers:
                suggestion = {
                    "ticker": ticker,
                    "direction": direction,
                    "confidence": confidence,
                    "message_id": msg.id,
                    "user_id": msg.user_id,
                    "username": msg.username,
                    "content": msg.content,
                    "timestamp": msg.timestamp,
                }
                suggestions.append(suggestion)

                # Track as pending advice
                advice = TradeAdvice(
                    message_id=msg.id,
                    user_id=msg.user_id,
                    username=msg.username,
                    ticker=ticker,
                    direction=direction,
                    timestamp=msg.timestamp,
                )
                self._pending_advice[ticker] = advice
                self._recent_suggestions.append(advice)

        self._last_analysis_time = datetime.now(timezone.utc)

        return suggestions

    def _parse_direction(self, content: str) -> Tuple[str, float]:
        """
        Parse trading direction and confidence from message content.

        Returns:
            (direction, confidence) where direction is "long" or "short"
            and confidence is 0.0-1.0
        """
        content_lower = content.lower()

        # Long indicators
        long_patterns = [
            r"\blong\b",
            r"\bbuy\b",
            r"\bbullish\b",
            r"\bpump\b",
            r"\bmoon\b",
            r"\bbreakout\b",
            r"\buptrend\b",
            r"\brally\b",
            r"\bgo up\b",
            r"\bgoing up\b",
            r"\b📈\b",
            r"\b🚀\b",
        ]

        # Short indicators
        short_patterns = [
            r"\bshort\b",
            r"\bsell\b",
            r"\bbearish\b",
            r"\bdump\b",
            r"\bcrash\b",
            r"\bbreakdown\b",
            r"\bdowntrend\b",
            r"\bdrop\b",
            r"\bgo down\b",
            r"\bgoing down\b",
            r"\b📉\b",
        ]

        long_score = sum(1 for p in long_patterns if re.search(p, content_lower))
        short_score = sum(1 for p in short_patterns if re.search(p, content_lower))

        total = long_score + short_score

        if total == 0:
            return "neutral", 0.3

        if long_score > short_score:
            confidence = min(0.9, 0.5 + (long_score / (total * 2)))
            return "long", confidence
        elif short_score > long_score:
            confidence = min(0.9, 0.5 + (short_score / (total * 2)))
            return "short", confidence
        else:
            return "neutral", 0.4

    async def respond_to_mention(self, message_id: str, content: str, username: str):
        """
        Respond to a direct @bot mention in chat.
        """
        chat = self._get_chat_service()

        # Parse tickers from the mention
        tickers = chat.parse_tickers(content)

        if not tickers:
            await chat.send_bot_message(
                bot_id=self.bot_id,
                content=f"@{username}, mention a ticker like $BTC or $ETH and I'll analyze it for you!",
                reply_to=message_id,
            )
            return

        # Award points for bot interaction
        await chat.award_points(
            message_id=message_id,
            points=POINTS["bot_interaction"],
            reason="Bot interaction",
            bot_id=self.bot_id,
        )

        ticker = tickers[0]
        direction, confidence = self._parse_direction(content)

        # Respond based on analysis
        if confidence > 0.6:
            response = self._pick_response("considering", ticker=ticker, username=username)
        else:
            response = f"@{username}, I'm watching ${ticker}. Share more details about your thesis!"

        await chat.send_bot_message(
            bot_id=self.bot_id,
            content=response,
            reply_to=message_id,
        )

    async def on_trade_opened(
        self,
        symbol: str,
        side: str,
        entry_price: float,
        trade_id: str,
    ):
        """
        Called when a trade is opened. Check if any user advice influenced it.

        Args:
            symbol: Trading pair (e.g., "BTCUSDT")
            side: "BUY" or "SELL"
            entry_price: Trade entry price
            trade_id: Unique trade identifier
        """
        chat = self._get_chat_service()

        # Check for matching pending advice
        advice = self._pending_advice.get(symbol)

        if not advice:
            return

        # Check if advice direction matches trade
        trade_direction = "long" if side == "BUY" else "short"

        if advice.direction != trade_direction:
            return

        # Check if advice is recent (within 30 minutes)
        time_diff = datetime.now(timezone.utc) - advice.timestamp
        if time_diff > timedelta(minutes=30):
            return

        # Link advice to trade
        advice.trade_id = trade_id
        advice.trade_entry_price = entry_price

        # Award points for advice being taken
        await chat.award_points(
            message_id=advice.message_id,
            points=POINTS["advice_taken"],
            reason=f"${symbol} {trade_direction.upper()} trade influenced by your advice!",
            bot_id=self.bot_id,
        )

        advice.points_awarded += POINTS["advice_taken"]

        # Post to chat
        response = self._pick_response(
            "agreed",
            ticker=symbol.replace("USDT", ""),
            username=advice.username,
        )

        await chat.send_bot_message(
            bot_id=self.bot_id,
            content=response,
            reply_to=advice.message_id,
        )

        logger.info(f"Trade {trade_id} linked to advice from {advice.username}")

    async def on_trade_closed(
        self,
        symbol: str,
        trade_id: str,
        exit_price: float,
        pnl: float,
        pnl_percent: float,
    ):
        """
        Called when a trade is closed. Award bonus points if profitable.

        Args:
            symbol: Trading pair
            trade_id: Unique trade identifier
            exit_price: Trade exit price
            pnl: Profit/loss in USD
            pnl_percent: Profit/loss percentage
        """
        chat = self._get_chat_service()

        # Find advice linked to this trade
        advice = None
        for a in self._recent_suggestions:
            if a.trade_id == trade_id and not a.resolved:
                advice = a
                break

        if not advice:
            return

        # Update advice with trade result
        advice.trade_exit_price = exit_price
        advice.trade_pnl = pnl
        advice.trade_pnl_percent = pnl_percent
        advice.resolved = True

        # Award bonus points if profitable
        if pnl_percent > 0:
            if pnl_percent >= 5:
                bonus_points = POINTS["high_profit_advice"]
            else:
                bonus_points = POINTS["profitable_advice"]

            await chat.award_points(
                message_id=advice.message_id,
                points=bonus_points,
                reason=f"${symbol} trade closed at +{pnl_percent:.1f}% profit!",
                bot_id=self.bot_id,
            )

            advice.points_awarded += bonus_points

            # Post celebration to chat
            response = self._pick_response(
                "profitable",
                ticker=symbol.replace("USDT", ""),
                username=advice.username,
                profit_pct=f"{pnl_percent:.1f}",
                points=bonus_points,
            )

            await chat.send_bot_message(
                bot_id=self.bot_id,
                content=response,
            )

            logger.info(
                f"Awarded {bonus_points} bonus points to {advice.username} for profitable {symbol} advice"
            )
        else:
            # Still acknowledge the prediction was tracked
            response = self._pick_response(
                "loss",
                ticker=symbol.replace("USDT", ""),
                profit_pct=f"{pnl_percent:.1f}",
            )

            await chat.send_bot_message(
                bot_id=self.bot_id,
                content=response,
            )

        # Clean up pending advice
        if symbol in self._pending_advice:
            del self._pending_advice[symbol]

    async def get_crowd_sentiment(self, symbol: str) -> Dict[str, Any]:
        """
        Get crowd sentiment for a symbol based on recent chat.

        Returns:
            {
                "bullish_count": int,
                "bearish_count": int,
                "neutral_count": int,
                "direction": "long" | "short" | "neutral",
                "confidence": float,
                "messages": List[Dict],
            }
        """
        chat = self._get_chat_service()
        messages = await chat.get_messages_with_ticker(symbol, limit=50)

        if not messages:
            return {
                "bullish_count": 0,
                "bearish_count": 0,
                "neutral_count": 0,
                "direction": "neutral",
                "confidence": 0.5,
                "messages": [],
            }

        bullish = 0
        bearish = 0
        neutral = 0

        analyzed = []

        for msg in messages:
            direction, conf = self._parse_direction(msg.content)

            if direction == "long":
                bullish += 1
            elif direction == "short":
                bearish += 1
            else:
                neutral += 1

            analyzed.append(
                {
                    "username": msg.username,
                    "direction": direction,
                    "confidence": conf,
                    "timestamp": msg.timestamp.isoformat(),
                }
            )

        total = bullish + bearish + neutral

        if bullish > bearish:
            direction = "long"
            confidence = bullish / total
        elif bearish > bullish:
            direction = "short"
            confidence = bearish / total
        else:
            direction = "neutral"
            confidence = 0.5

        return {
            "bullish_count": bullish,
            "bearish_count": bearish,
            "neutral_count": neutral,
            "direction": direction,
            "confidence": confidence,
            "messages": analyzed,
        }

    def get_pending_advice_count(self) -> int:
        """Get number of pending advice being tracked."""
        return len(self._pending_advice)

    def get_recent_suggestions(self, limit: int = 20) -> List[Dict[str, Any]]:
        """Get recent suggestions with their status."""
        return [
            {
                "ticker": a.ticker,
                "direction": a.direction,
                "username": a.username,
                "timestamp": a.timestamp.isoformat(),
                "trade_linked": a.trade_id is not None,
                "resolved": a.resolved,
                "pnl_percent": a.trade_pnl_percent,
                "points_awarded": a.points_awarded,
            }
            for a in self._recent_suggestions[-limit:]
        ]


# Singleton instance
_chat_bot: Optional[TradingChatBot] = None


def get_chat_bot() -> TradingChatBot:
    """Get the singleton TradingChatBot instance."""
    global _chat_bot
    if _chat_bot is None:
        _chat_bot = TradingChatBot()
    return _chat_bot
