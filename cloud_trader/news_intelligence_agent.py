"""
News Intelligence Agent for Sapphire V2.3
Processes Telegram news/alpha and generates trading insights for autonomous agents
"""

import logging
import asyncio
from typing import List, Optional, Dict, Any
from datetime import datetime
from dataclasses import dataclass
import json

import google.generativeai as genai

from cloud_trader.telegram_news_monitor import NewsMessage

logger = logging.getLogger(__name__)


@dataclass
class NewsInsight:
    """Trading insight extracted from news"""
    timestamp: datetime
    source_chat: str
    source_message: str

    # Analysis
    relevance_score: float  # 0-1, how relevant to our trading
    urgency: str  # "low", "medium", "high", "critical"

    # Trading implications
    affected_tokens: List[str]  # Token symbols mentioned
    sentiment: str  # "bullish", "bearish", "neutral"
    suggested_action: str  # "buy", "sell", "hold", "monitor"
    confidence: float  # 0-1, AI confidence in analysis

    # Context
    reasoning: str  # AI's reasoning
    key_points: List[str]  # Bullet points of key info

    # Metadata
    raw_news: NewsMessage


class NewsIntelligenceAgent:
    """
    AI-powered news analysis agent that converts raw Telegram messages
    into actionable trading insights

    Uses Gemini 3 Flash for real-time news analysis
    """

    def __init__(self, gemini_model: str = "gemini-3-flash-preview"):
        """
        Initialize News Intelligence Agent

        Args:
            gemini_model: Gemini model to use for analysis
        """
        self.model_name = gemini_model
        self.model = None

        # Track recent news to avoid duplicate analysis
        self.recent_news_ids: set = set()
        self.max_recent = 1000

        # Callbacks for insights
        self.insight_callbacks: List[callable] = []

        logger.info(f"🧠 NewsIntelligenceAgent initialized with {gemini_model}")

    def initialize_model(self) -> None:
        """Initialize Gemini model"""
        try:
            self.model = genai.GenerativeModel(self.model_name)
            logger.info(f"✅ Gemini model initialized: {self.model_name}")
        except Exception as e:
            logger.error(f"❌ Failed to initialize Gemini model: {e}")
            raise

    def add_insight_callback(self, callback: callable) -> None:
        """
        Register callback to receive trading insights

        Args:
            callback: Function that receives NewsInsight objects
        """
        self.insight_callbacks.append(callback)
        logger.info(f"✅ Registered insight callback: {callback.__name__}")

    async def process_news(self, news: NewsMessage) -> Optional[NewsInsight]:
        """
        Process incoming news message and extract trading insights

        Args:
            news: NewsMessage from Telegram monitor

        Returns:
            NewsInsight if relevant, None otherwise
        """
        # Deduplicate
        news_id = f"{news.chat_id}:{news.message_id}"
        if news_id in self.recent_news_ids:
            return None

        self.recent_news_ids.add(news_id)
        if len(self.recent_news_ids) > self.max_recent:
            # Remove oldest entries (simple FIFO)
            self.recent_news_ids.pop()

        try:
            # Analyze with Gemini
            insight = await self._analyze_with_ai(news)

            if insight:
                # Forward to callbacks
                for callback in self.insight_callbacks:
                    try:
                        if asyncio.iscoroutinefunction(callback):
                            await callback(insight)
                        else:
                            callback(insight)
                    except Exception as e:
                        logger.error(f"❌ Error in insight callback: {e}")

                logger.info(
                    f"💡 News Insight: {insight.affected_tokens} | "
                    f"{insight.sentiment} | {insight.suggested_action} | "
                    f"confidence={insight.confidence:.2f}"
                )

            return insight

        except Exception as e:
            logger.error(f"❌ Error processing news: {e}", exc_info=True)
            return None

    async def _analyze_with_ai(self, news: NewsMessage) -> Optional[NewsInsight]:
        """
        Use Gemini to analyze news message

        Args:
            news: Raw news message

        Returns:
            NewsInsight if relevant, None if not trading-related
        """
        if not self.model:
            self.initialize_model()

        # Construct analysis prompt
        prompt = self._build_analysis_prompt(news)

        try:
            # Call Gemini API
            response = await asyncio.to_thread(
                self.model.generate_content,
                prompt
            )

            # Parse response
            insight = self._parse_ai_response(response.text, news)
            return insight

        except Exception as e:
            logger.error(f"❌ Gemini API error: {e}")
            return None

    def _build_analysis_prompt(self, news: NewsMessage) -> str:
        """Build structured prompt for Gemini analysis"""
        return f"""You are a crypto trading intelligence analyst. Analyze this message from a Telegram news/alpha channel.

**Message Details:**
- Source: {news.chat_name}
- Sender: {news.sender or 'Unknown'}
- Time: {news.timestamp}
- Text: {news.text}

**Your Task:**
Analyze if this message contains actionable trading intelligence for crypto/DeFi markets.

**Response Format (JSON):**
{{
    "is_relevant": true/false,
    "relevance_score": 0.0-1.0,
    "urgency": "low"/"medium"/"high"/"critical",
    "affected_tokens": ["TOKEN1", "TOKEN2"],
    "sentiment": "bullish"/"bearish"/"neutral",
    "suggested_action": "buy"/"sell"/"hold"/"monitor",
    "confidence": 0.0-1.0,
    "reasoning": "Brief explanation of your analysis",
    "key_points": ["Point 1", "Point 2"]
}}

**Guidelines:**
- Only set is_relevant=true for actual trading signals, market-moving news, or alpha
- affected_tokens should use standard ticker symbols (e.g., SOL, ETH, BTC)
- urgency=critical only for major breaking news requiring immediate action
- confidence should reflect certainty in your analysis
- Be conservative - false positives waste trader attention

**Output:** Return ONLY valid JSON, no additional text."""

    def _parse_ai_response(self, response_text: str, news: NewsMessage) -> Optional[NewsInsight]:
        """
        Parse Gemini JSON response into NewsInsight

        Args:
            response_text: Raw Gemini response
            news: Original news message

        Returns:
            NewsInsight or None if not relevant
        """
        try:
            # Extract JSON from response (handle markdown code blocks)
            json_text = response_text.strip()
            if json_text.startswith("```json"):
                json_text = json_text[7:]
            if json_text.startswith("```"):
                json_text = json_text[3:]
            if json_text.endswith("```"):
                json_text = json_text[:-3]
            json_text = json_text.strip()

            data = json.loads(json_text)

            # Check relevance
            if not data.get("is_relevant", False):
                return None

            # Build insight
            insight = NewsInsight(
                timestamp=datetime.now(),
                source_chat=news.chat_name,
                source_message=news.text,
                relevance_score=float(data.get("relevance_score", 0.5)),
                urgency=data.get("urgency", "low"),
                affected_tokens=data.get("affected_tokens", []),
                sentiment=data.get("sentiment", "neutral"),
                suggested_action=data.get("suggested_action", "monitor"),
                confidence=float(data.get("confidence", 0.5)),
                reasoning=data.get("reasoning", ""),
                key_points=data.get("key_points", []),
                raw_news=news,
            )

            return insight

        except json.JSONDecodeError as e:
            logger.error(f"❌ Failed to parse AI response as JSON: {e}")
            logger.debug(f"Response text: {response_text}")
            return None
        except Exception as e:
            logger.error(f"❌ Error parsing AI response: {e}", exc_info=True)
            return None

    def get_stats(self) -> Dict[str, Any]:
        """Get statistics about news processing"""
        return {
            "total_processed": len(self.recent_news_ids),
            "active_callbacks": len(self.insight_callbacks),
            "model": self.model_name,
        }
