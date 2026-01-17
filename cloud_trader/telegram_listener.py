"""
Telegram Chat Listener for Sapphire Trading System.
Monitors specified Telegram groups for trading signals and alpha.

Features:
- Async polling for incoming messages
- Signal parsing and extraction
- In-memory queue for recent signals
- Integration with ElizaAgent context
"""

import asyncio
import logging
import re
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Set

import aiohttp

logger = logging.getLogger(__name__)


@dataclass
class ChatSignal:
    """Parsed trading signal from Telegram chat."""

    message_id: int
    chat_id: str
    chat_name: str
    sender: str
    symbols: List[str]
    sentiment: float  # -1 (bearish) to +1 (bullish)
    urgency: str  # "immediate", "swing", "hodl"
    original_text: str
    timestamp: float = field(default_factory=time.time)
    confidence: float = 0.5

    def to_dict(self) -> Dict[str, Any]:
        return {
            "message_id": self.message_id,
            "chat_id": self.chat_id,
            "chat_name": self.chat_name,
            "sender": self.sender,
            "symbols": self.symbols,
            "sentiment": self.sentiment,
            "urgency": self.urgency,
            "original_text": self.original_text[:200],  # Truncate for logs
            "timestamp": self.timestamp,
            "confidence": self.confidence,
        }


class ChatSignalParser:
    """Parses Telegram messages for trading signals."""

    # Ticker patterns
    TICKER_PATTERNS = [
        r"\$([A-Z]{2,10})",  # $BTC, $ETH
        r"\b([A-Z]{2,6})(USDT?|USD|USDC|PERP)\b",  # BTCUSDT, ETHUSDC
        r"\b(BTC|ETH|SOL|DOGE|PEPE|WIF|BONK|SHIB|XRP|ADA|AVAX|LINK|DOT|MATIC|ARB|OP)\b",  # Common tickers
    ]

    # Sentiment keywords
    BULLISH_KEYWORDS = [
        "buy",
        "long",
        "bullish",
        "moon",
        "pump",
        "sending",
        "breakout",
        "accumulate",
        "dip buy",
        "entry",
        "lfg",
        "wagmi",
        "rip",
        "send it",
        "bullish af",
        "reversal",
        "bottomed",
        "oversold",
        "🚀",
        "📈",
        "🟢",
        "💚",
        "🔥",
    ]

    BEARISH_KEYWORDS = [
        "sell",
        "short",
        "bearish",
        "dump",
        "crash",
        "breakdown",
        "exit",
        "take profit",
        "tp hit",
        "rekt",
        "ngmi",
        "overextended",
        "overbought",
        "top signal",
        "distribution",
        "📉",
        "🔴",
        "💀",
        "⚠️",
        "🩸",
    ]

    URGENCY_IMMEDIATE = ["now", "immediately", "asap", "quick", "fast", "rn", "right now"]
    URGENCY_SWING = ["swing", "daily", "4h", "1d", "weekly", "position"]
    URGENCY_HODL = ["hodl", "hold", "long term", "accumulate", "dca", "stack"]

    def parse(self, text: str, sender: str = "unknown") -> Optional[Dict[str, Any]]:
        """Parse a message for trading signals.

        Returns:
            Dict with symbols, sentiment, urgency, or None if no signal detected
        """
        if not text or len(text) < 3:
            return None

        text_lower = text.lower()

        # Extract symbols
        symbols = self._extract_symbols(text)
        if not symbols:
            return None

        # Calculate sentiment
        sentiment = self._calculate_sentiment(text_lower)

        # Determine urgency
        urgency = self._determine_urgency(text_lower)

        # Calculate confidence based on signal clarity
        confidence = self._calculate_confidence(text_lower, sentiment, len(symbols))

        return {
            "symbols": list(symbols),
            "sentiment": sentiment,
            "urgency": urgency,
            "confidence": confidence,
        }

    def _extract_symbols(self, text: str) -> Set[str]:
        """Extract ticker symbols from text."""
        symbols = set()

        for pattern in self.TICKER_PATTERNS:
            matches = re.findall(pattern, text, re.IGNORECASE)
            for match in matches:
                if isinstance(match, tuple):
                    match = match[0]
                symbol = match.upper()
                # Filter out common false positives
                if symbol not in {
                    "THE",
                    "FOR",
                    "AND",
                    "USD",
                    "USDT",
                    "USDC",
                    "A",
                    "I",
                    "IS",
                    "IT",
                    "TO",
                    "OF",
                    "IF",
                }:
                    symbols.add(symbol)

        return symbols

    def _calculate_sentiment(self, text: str) -> float:
        """Calculate sentiment score from -1 (bearish) to +1 (bullish)."""
        bullish_count = sum(1 for kw in self.BULLISH_KEYWORDS if kw in text)
        bearish_count = sum(1 for kw in self.BEARISH_KEYWORDS if kw in text)

        total = bullish_count + bearish_count
        if total == 0:
            return 0.0

        # Normalized sentiment
        sentiment = (bullish_count - bearish_count) / total
        return max(-1.0, min(1.0, sentiment))

    def _determine_urgency(self, text: str) -> str:
        """Determine trade urgency from text."""
        if any(kw in text for kw in self.URGENCY_IMMEDIATE):
            return "immediate"
        elif any(kw in text for kw in self.URGENCY_HODL):
            return "hodl"
        elif any(kw in text for kw in self.URGENCY_SWING):
            return "swing"
        return "swing"  # Default

    def _calculate_confidence(self, text: str, sentiment: float, symbol_count: int) -> float:
        """Calculate confidence in the signal."""
        confidence = 0.3  # Base confidence

        # Strong sentiment = higher confidence
        confidence += abs(sentiment) * 0.3

        # Specific symbols = higher confidence
        if symbol_count == 1:
            confidence += 0.2
        elif symbol_count > 3:
            confidence -= 0.1  # Too many symbols = less focused

        # Technical terms boost confidence
        technical_terms = ["support", "resistance", "breakout", "breakdown", "volume", "divergence"]
        if any(term in text for term in technical_terms):
            confidence += 0.1

        return max(0.1, min(1.0, confidence))


class TelegramListener:
    """
    Listens to specified Telegram chats for trading signals.
    Uses Telegram Bot API with long polling.
    """

    def __init__(
        self,
        bot_token: str,
        chat_ids: List[str],
        max_queue_size: int = 100,
        signal_ttl_minutes: int = 30,
    ):
        self.bot_token = bot_token.strip() if bot_token else ""
        self.chat_ids = set(str(cid) for cid in chat_ids)
        self.base_url = f"https://api.telegram.org/bot{self.bot_token}"

        self.parser = ChatSignalParser()
        self.signal_queue: deque = deque(maxlen=max_queue_size)
        self.signal_ttl = timedelta(minutes=signal_ttl_minutes)

        self._running = False
        self._last_update_id = 0
        self._session: Optional[aiohttp.ClientSession] = None

        # Chat name cache
        self._chat_names: Dict[str, str] = {}

        logger.info(f"📡 TelegramListener initialized for {len(chat_ids)} chats")

    async def start(self):
        """Start listening to Telegram updates."""
        if not self.bot_token:
            logger.warning("⚠️ No Telegram bot token - listener disabled")
            return

        if not self.chat_ids:
            logger.warning("⚠️ No chat IDs configured - listener disabled")
            return

        self._running = True
        self._session = aiohttp.ClientSession()

        logger.info("📡 Starting Telegram listener...")
        asyncio.create_task(self._poll_loop())

    async def stop(self):
        """Stop the listener."""
        self._running = False
        if self._session:
            await self._session.close()
            self._session = None
        logger.info("📡 Telegram listener stopped")

    async def _poll_loop(self):
        """Main polling loop for Telegram updates."""
        while self._running:
            try:
                await self._fetch_updates()
                await asyncio.sleep(2)  # Poll every 2 seconds
            except Exception as e:
                logger.error(f"❌ Telegram poll error: {e}")
                await asyncio.sleep(10)  # Back off on error

    async def _fetch_updates(self):
        """Fetch new updates from Telegram."""
        if not self._session:
            return

        url = f"{self.base_url}/getUpdates"
        params = {
            "offset": self._last_update_id + 1,
            "timeout": 30,
            "allowed_updates": ["message"],
        }

        try:
            async with self._session.get(url, params=params, timeout=35) as resp:
                if resp.status != 200:
                    logger.warning(f"Telegram API error: {resp.status}")
                    return

                data = await resp.json()
                if not data.get("ok"):
                    return

                for update in data.get("result", []):
                    self._last_update_id = update["update_id"]
                    await self._process_update(update)
        except asyncio.TimeoutError:
            pass  # Normal for long polling
        except Exception as e:
            logger.error(f"Error fetching updates: {e}")

    async def _process_update(self, update: Dict):
        """Process a single Telegram update."""
        message = update.get("message", {})
        if not message:
            return

        chat = message.get("chat", {})
        chat_id = str(chat.get("id", ""))

        # Only process messages from configured chats
        if chat_id not in self.chat_ids:
            return

        text = message.get("text", "")
        if not text:
            return

        # Parse the message
        sender = message.get("from", {}).get("first_name", "Anonymous")
        chat_name = chat.get("title", chat.get("first_name", "Unknown"))

        parsed = self.parser.parse(text, sender)
        if not parsed:
            return

        # Create signal
        signal = ChatSignal(
            message_id=message.get("message_id", 0),
            chat_id=chat_id,
            chat_name=chat_name,
            sender=sender,
            symbols=parsed["symbols"],
            sentiment=parsed["sentiment"],
            urgency=parsed["urgency"],
            original_text=text,
            confidence=parsed["confidence"],
        )

        self.signal_queue.append(signal)

        sentiment_emoji = "🟢" if signal.sentiment > 0 else "🔴" if signal.sentiment < 0 else "⚪"
        logger.info(
            f"📡 Signal from {chat_name}: {sentiment_emoji} {signal.symbols} "
            f"(sentiment={signal.sentiment:.2f}, urgency={signal.urgency})"
        )

    def get_recent_signals(
        self,
        symbol: Optional[str] = None,
        limit: int = 10,
    ) -> List[ChatSignal]:
        """Get recent signals, optionally filtered by symbol.

        Args:
            symbol: Filter to specific symbol (e.g., "BTC")
            limit: Maximum signals to return

        Returns:
            List of recent ChatSignal objects
        """
        now = time.time()
        cutoff = now - self.signal_ttl.total_seconds()

        signals = []
        for signal in reversed(self.signal_queue):
            if signal.timestamp < cutoff:
                continue

            if symbol:
                # Match symbol (handle BTC vs BTCUSDT)
                symbol_upper = (
                    symbol.upper().replace("-", "").replace("USDT", "").replace("USDC", "")
                )
                if not any(symbol_upper in s for s in signal.symbols):
                    continue

            signals.append(signal)
            if len(signals) >= limit:
                break

        return signals

    def get_crowd_sentiment(self, symbol: str) -> Dict[str, Any]:
        """Get aggregated crowd sentiment for a symbol.

        Args:
            symbol: Trading symbol (e.g., "BTC", "BTCUSDT")

        Returns:
            Dict with sentiment summary
        """
        signals = self.get_recent_signals(symbol, limit=20)

        if not signals:
            return {
                "symbol": symbol,
                "signal_count": 0,
                "avg_sentiment": 0.0,
                "direction": "neutral",
                "confidence": 0.0,
                "summary": "No recent signals",
            }

        sentiments = [s.sentiment for s in signals]
        avg_sentiment = sum(sentiments) / len(sentiments)
        confidences = [s.confidence for s in signals]
        avg_confidence = sum(confidences) / len(confidences)

        # Determine direction
        if avg_sentiment > 0.2:
            direction = "bullish"
        elif avg_sentiment < -0.2:
            direction = "bearish"
        else:
            direction = "neutral"

        # Build summary
        recent = signals[0] if signals else None
        summary = f"{len(signals)} signals, avg sentiment {avg_sentiment:.2f}"
        if recent:
            summary += f". Latest: '{recent.original_text[:50]}...'"

        return {
            "symbol": symbol,
            "signal_count": len(signals),
            "avg_sentiment": avg_sentiment,
            "direction": direction,
            "confidence": avg_confidence,
            "summary": summary,
            "signals": [s.to_dict() for s in signals[:5]],
        }

    def format_for_agent(self, symbol: str) -> str:
        """Format crowd signals for agent prompt injection.

        Args:
            symbol: Trading symbol

        Returns:
            Human-readable string for AI agent context
        """
        sentiment = self.get_crowd_sentiment(symbol)

        if sentiment["signal_count"] == 0:
            return f"No recent community signals for {symbol}."

        lines = [
            f"## Community Alpha for {symbol}",
            f"- Signal Count: {sentiment['signal_count']} in last 30 min",
            f"- Crowd Direction: {sentiment['direction'].upper()} (score: {sentiment['avg_sentiment']:+.2f})",
            f"- Confidence: {sentiment['confidence']:.0%}",
            "",
            "Recent mentions:",
        ]

        for sig in sentiment.get("signals", [])[:3]:
            emoji = "🟢" if sig["sentiment"] > 0 else "🔴" if sig["sentiment"] < 0 else "⚪"
            lines.append(f"  {emoji} [{sig['sender']}]: {sig['original_text']}")

        return "\n".join(lines)

    async def check_health(self) -> Dict[str, Any]:
        """Check connection health of the Telegram listener."""
        status = {
            "running": self._running,
            "connected": False,
            "bot_name": "Unknown",
            "chat_count": len(self.chat_ids),
            "queued_signals": len(self.signal_queue),
            "errors": [],
        }

        if not self.bot_token:
            status["errors"].append("No bot token configured")
            return status

        try:
            # Use dedicated session for health check if main session not active
            session = self._session or aiohttp.ClientSession()
            try:
                async with session.get(f"{self.base_url}/getMe", timeout=5) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        if data.get("ok"):
                            status["connected"] = True
                            status["bot_name"] = data["result"].get("first_name", "Unknown")
                        else:
                            status["errors"].append(f"API Error: {data.get('description')}")
                    else:
                        status["errors"].append(f"HTTP Error: {resp.status}")
            finally:
                if not self._session:
                    await session.close()

        except Exception as e:
            status["errors"].append(f"Connection failed: {str(e)}")

        return status


# Singleton instance
_telegram_listener: Optional[TelegramListener] = None


async def get_telegram_listener(
    bot_token: Optional[str] = None,
    chat_ids: Optional[List[str]] = None,
) -> TelegramListener:
    """Get or create the global Telegram listener instance."""
    global _telegram_listener

    if _telegram_listener is None:
        from .config import get_settings

        settings = get_settings()
        token = bot_token or settings.telegram_bot_token or ""
        chats = chat_ids or []

        # Load chat IDs from environment if not provided
        if not chats:
            import os

            chat_env = os.getenv("TELEGRAM_LISTEN_CHAT_IDS", "")
            if chat_env:
                chats = [cid.strip() for cid in chat_env.split(",") if cid.strip()]

        # If still no listen chats, but we have a notification chat_id, use that
        if not chats and settings.telegram_chat_id:
            chats = [settings.telegram_chat_id]
            logger.info(f"ℹ️ Defaulting Telegram listener to notification chat: {settings.telegram_chat_id}")

        _telegram_listener = TelegramListener(token, chats)

    return _telegram_listener
