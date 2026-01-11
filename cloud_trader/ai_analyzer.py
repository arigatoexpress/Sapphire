"""AI-powered trading analyzer for enhanced insights."""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, List, Optional

from .vertex_ai_client import get_vertex_client

logger = logging.getLogger(__name__)


class AITradingAnalyzer:
    """AI-powered trading analysis and insights using Vertex AI/Gemini."""

    def __init__(self):
        self.model_name = "market-analysis"
        self.client = get_vertex_client()

    async def _get_prediction(self, prompt: str, system_instruction: str = "") -> str:
        """Helper to get prediction from Vertex AI client."""
        full_prompt = f"{system_instruction}\n\n{prompt}" if system_instruction else prompt
        try:
            result = await self.client.predict(self.model_name, full_prompt)
            return result.get("response", "")
        except Exception as e:
            logger.error(f"AI Prediction failed: {e}")
            return ""

    async def analyze_trade(
        self, symbol: str, side: str, price: float, volume: float, market_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Analyze a trade opportunity using AI."""
        prompt = f"""
        Analyze this potential trade setup:
        Symbol: {symbol}
        Side: {side}
        Price: {price}
        Volume: {volume}
        Market Data: {json.dumps(market_data, default=str)}

        Provide a JSON response with the following keys:
        - confidence: float (0.0 to 1.0)
        - rationale: string (concise explanation)
        - risk_level: string (low, medium, high)
        - time_horizon: string (short, medium, long)
        - expected_move: dict with keys 'upside', 'downside', 'probability'
        - recommendations: list of strings (actionable advice)
        """

        response_text = await self._get_prediction(
            prompt, "You are an expert crypto trading analyst."
        )

        try:
            # Attempt to parse JSON from response (handling potential markdown code blocks)
            cleaned_text = response_text.replace("```json", "").replace("```", "").strip()
            analysis = json.loads(cleaned_text)
            return analysis
        except json.JSONDecodeError:
            logger.warning(f"Failed to parse AI response as JSON: {response_text[:100]}...")
            # Fallback structure
            return {
                "confidence": 0.5,
                "rationale": "AI Analysis returned unstructured text. Check logs for details.",
                "risk_level": "medium",
                "time_horizon": "short",
                "expected_move": {
                    "upside": price * 1.02,
                    "downside": price * 0.98,
                    "probability": 0.5,
                },
                "recommendations": ["Monitor closely"],
                "raw_response": response_text,
            }

    async def analyze_market_sentiment(
        self, symbol: str, market_data: Dict[str, Any], social_data: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Analyze market sentiment using AI."""
        prompt = f"""
        Analyze the market sentiment for {symbol}.
        Market Data: {json.dumps(market_data, default=str)}
        Social Data: {json.dumps(social_data, default=str) if social_data else 'Not available'}

        Provide a JSON response with:
        - overall: string (bullish, bearish, neutral)
        - confidence: float
        - key_drivers: list of strings
        - risk_factors: list of strings
        - recommendation: string
        """

        response_text = await self._get_prediction(prompt, "You are a sentiment analysis expert.")

        try:
            cleaned_text = response_text.replace("```json", "").replace("```", "").strip()
            return json.loads(cleaned_text)
        except json.JSONDecodeError:
            return {
                "overall": "neutral",
                "confidence": 0.5,
                "key_drivers": ["Analysis parsing failed"],
                "risk_factors": ["Unknown"],
                "recommendation": "Hold",
                "raw_response": response_text,
            }

    async def generate_performance_insights(
        self, performance_data: Dict[str, Any], period: str = "daily"
    ) -> Dict[str, Any]:
        """Generate AI-powered performance insights."""
        prompt = f"""
        Analyze trading performance for the {period} period.
        Data: {json.dumps(performance_data, default=str)}

        Provide a JSON response with:
        - overall_assessment: string
        - key_strengths: list of strings
        - areas_for_improvement: list of strings
        - recommendations: list of strings
        - risk_assessment: string
        """

        response_text = await self._get_prediction(prompt, "You are a trading performance coach.")

        try:
            cleaned_text = response_text.replace("```json", "").replace("```", "").strip()
            return json.loads(cleaned_text)
        except json.JSONDecodeError:
            return {
                "overall_assessment": "Could not generate assessment",
                "key_strengths": [],
                "areas_for_improvement": [],
                "recommendations": ["Check logs"],
                "risk_assessment": "unknown",
            }

    async def predict_market_movement(
        self, symbol: str, timeframe: str, market_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Predict market movement using AI."""
        prompt = f"""
        Predict market movement for {symbol} over a {timeframe} timeframe.
        Market Data: {json.dumps(market_data, default=str)}

        Provide a JSON response with:
        - direction: string
        - confidence: float
        - time_horizon: string
        - key_levels: dict with 'support' and 'resistance' lists
        - rationale: string
        """

        response_text = await self._get_prediction(prompt, "You are a technical analysis expert.")

        try:
            cleaned_text = response_text.replace("```json", "").replace("```", "").strip()
            return json.loads(cleaned_text)
        except json.JSONDecodeError:
            return {
                "direction": "neutral",
                "confidence": 0.0,
                "time_horizon": timeframe,
                "key_levels": {"support": [], "resistance": []},
                "rationale": "Parsing failed",
            }
