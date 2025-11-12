"""Market sentiment analysis for enhanced trading insights."""
from __future__ import annotations
import logging
from typing import Dict, List, Any, Optional
from datetime import datetime, timedelta
import asyncio

logger = logging.getLogger(__name__)

class MarketSentimentAnalyzer:
    """Advanced market sentiment analysis."""

    def __init__(self):
        self.sentiment_sources = [
            'technical_indicators',
            'order_flow',
            'volume_analysis',
            'price_action',
            'market_structure'
        ]

    async def analyze_sentiment(
        self,
        symbol: str,
        timeframe: str = '1h',
        market_data: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """Analyze comprehensive market sentiment."""
        sentiment_scores = await self._calculate_sentiment_scores(symbol, timeframe, market_data)

        overall_sentiment = self._determine_overall_sentiment(sentiment_scores)
        confidence = self._calculate_confidence(sentiment_scores)

        analysis = {
            'symbol': symbol,
            'timeframe': timeframe,
            'overall_sentiment': overall_sentiment,
            'confidence': confidence,
            'sentiment_scores': sentiment_scores,
            'key_drivers': self._identify_key_drivers(sentiment_scores),
            'risk_assessment': self._assess_sentiment_risk(sentiment_scores),
            'recommendation': self._generate_sentiment_recommendation(overall_sentiment, confidence),
            'timestamp': datetime.now()
        }

        return analysis

    async def get_market_mood(self, symbol: str) -> Dict[str, Any]:
        """Get current market mood and psychology."""
        # Mock market mood analysis
        mood = {
            'fear_greed_index': 65,  # 0-100 scale
            'momentum': 'bullish',
            'volatility_regime': 'normal',
            'liquidity_conditions': 'good',
            'institutional_sentiment': 'neutral',
            'retail_sentiment': 'optimistic'
        }

        return mood

    async def detect_sentiment_shifts(
        self,
        symbol: str,
        historical_data: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Detect significant sentiment shifts."""
        shifts = []

        # Analyze sentiment changes over time
        for i in range(1, len(historical_data)):
            prev_sentiment = historical_data[i-1].get('sentiment', 'neutral')
            curr_sentiment = historical_data[i].get('sentiment', 'neutral')

            if prev_sentiment != curr_sentiment:
                shift = {
                    'timestamp': historical_data[i]['timestamp'],
                    'from_sentiment': prev_sentiment,
                    'to_sentiment': curr_sentiment,
                    'magnitude': self._calculate_shift_magnitude(prev_sentiment, curr_sentiment),
                    'trigger': self._identify_shift_trigger(historical_data[i])
                }
                shifts.append(shift)

        return shifts

    async def _calculate_sentiment_scores(
        self,
        symbol: str,
        timeframe: str,
        market_data: Dict[str, Any]
    ) -> Dict[str, float]:
        """Calculate sentiment scores from various sources."""
        # Mock sentiment calculation - would use real market data
        scores = {
            'technical_indicators': 0.75,  # RSI, MACD, etc.
            'order_flow': 0.82,           # Buy/sell order imbalance
            'volume_analysis': 0.68,      # Volume patterns
            'price_action': 0.71,         # Price movement patterns
            'market_structure': 0.79      # Support/resistance, trends
        }

        return scores

    def _determine_overall_sentiment(self, sentiment_scores: Dict[str, float]) -> str:
        """Determine overall market sentiment."""
        avg_score = sum(sentiment_scores.values()) / len(sentiment_scores)

        if avg_score >= 0.7:
            return 'bullish'
        elif avg_score >= 0.55:
            return 'moderately_bullish'
        elif avg_score >= 0.45:
            return 'neutral'
        elif avg_score >= 0.3:
            return 'moderately_bearish'
        else:
            return 'bearish'

    def _calculate_confidence(self, sentiment_scores: Dict[str, float]) -> float:
        """Calculate confidence in sentiment analysis."""
        # Higher confidence when scores are more consistent
        variance = sum((score - sum(sentiment_scores.values())/len(sentiment_scores))**2
                      for score in sentiment_scores.values()) / len(sentiment_scores)

        # Convert variance to confidence (lower variance = higher confidence)
        confidence = max(0.1, 1.0 - variance * 2)

        return round(confidence, 2)

    def _identify_key_drivers(self, sentiment_scores: Dict[str, float]) -> List[str]:
        """Identify key drivers of current sentiment."""
        drivers = []

        # Sort scores by importance
        sorted_scores = sorted(sentiment_scores.items(), key=lambda x: x[1], reverse=True)

        for source, score in sorted_scores[:3]:  # Top 3 drivers
            if score >= 0.7:
                drivers.append(f"Strong {source.replace('_', ' ')}")
            elif score >= 0.6:
                drivers.append(f"Positive {source.replace('_', ' ')}")

        return drivers

    def _assess_sentiment_risk(self, sentiment_scores: Dict[str, float]) -> str:
        """Assess risk level based on sentiment analysis."""
        avg_score = sum(sentiment_scores.values()) / len(sentiment_scores)
        consistency = 1.0 - (max(sentiment_scores.values()) - min(sentiment_scores.values()))

        if consistency < 0.3 or avg_score < 0.4 or avg_score > 0.8:
            return 'high'
        elif consistency < 0.5 or avg_score < 0.5 or avg_score > 0.7:
            return 'medium'
        else:
            return 'low'

    def _generate_sentiment_recommendation(
        self,
        sentiment: str,
        confidence: float
    ) -> str:
        """Generate trading recommendation based on sentiment."""
        if confidence < 0.6:
            return "Wait for clearer signals"

        if sentiment == 'bullish':
            return "Consider long positions with proper risk management"
        elif sentiment == 'moderately_bullish':
            return "Monitor for entry opportunities"
        elif sentiment == 'neutral':
            return "Sideways market - wait for directional clarity"
        elif sentiment == 'moderately_bearish':
            return "Exercise caution with long positions"
        else:  # bearish
            return "Focus on risk management and short opportunities"

    def _calculate_shift_magnitude(self, from_sentiment: str, to_sentiment: str) -> str:
        """Calculate magnitude of sentiment shift."""
        sentiment_values = {
            'bullish': 2,
            'moderately_bullish': 1,
            'neutral': 0,
            'moderately_bearish': -1,
            'bearish': -2
        }

        from_value = sentiment_values.get(from_sentiment, 0)
        to_value = sentiment_values.get(to_sentiment, 0)

        shift = abs(to_value - from_value)

        if shift >= 2:
            return 'major'
        elif shift == 1:
            return 'moderate'
        else:
            return 'minor'

    def _identify_shift_trigger(self, market_data: Dict[str, Any]) -> str:
        """Identify what triggered the sentiment shift."""
        # Analyze market data to identify trigger
        if market_data.get('volume_spike', False):
            return 'volume_spike'
        elif market_data.get('price_breakout', False):
            return 'price_breakout'
        elif market_data.get('news_event', False):
            return 'news_event'
        else:
            return 'technical_signal'
