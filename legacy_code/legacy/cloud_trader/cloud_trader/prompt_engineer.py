"""Prompt engineering module for AI trading inference.

Provides structured prompt building, response validation, and prompt versioning.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field, ValidationError

from .config import get_settings
from .metrics import (
    AI_CONFIDENCE_DISTRIBUTION,
    AI_PROMPT_GENERATION_DURATION_SECONDS,
    AI_PROMPT_VERSION_USAGE_TOTAL,
    AI_RESPONSE_PARSE_ERRORS_TOTAL,
    AI_RESPONSE_VALIDATION_ERRORS_TOTAL,
)
from .schemas import AIStrategyResponse
from .strategy import MarketSnapshot

logger = logging.getLogger(__name__)


@dataclass
class PromptContext:
    """Context for building prompts."""

    symbol: str
    market_data: MarketSnapshot
    historical_data: Optional[Any] = None
    technical_signals: Optional[List[Dict[str, Any]]] = None
    portfolio_state: Optional[Dict[str, Any]] = None
    agent_type: str = "general"
    risk_limits: Optional[Dict[str, float]] = None


class PromptBuilder:
    """Builds structured prompts for AI trading agents."""

    def __init__(self, prompt_version: str = "v1.0"):
        self.settings = get_settings()
        self.prompt_version = prompt_version
        self.templates_dir = Path(__file__).parent / "prompt_templates"

    def build_prompt(self, context: PromptContext) -> str:
        """Build a complete prompt for the given context."""
        start_time = time.time()

        try:
            # Get agent-specific system prompt
            system_prompt = self._get_system_prompt(context.agent_type)

            # Build market data section
            market_section = self._build_market_section(context)

            # Build technical signals section
            signals_section = self._build_signals_section(context)

            # Build constraints section
            constraints_section = self._build_constraints_section(context)

            # Build few-shot examples
            examples_section = self._build_examples_section()

            # Combine into final prompt
            prompt = f"""{system_prompt}

## Current Market Context

{market_section}

{signals_section}

{constraints_section}

{examples_section}

## Your Analysis

Analyze the current market situation for {context.symbol} and provide your trading recommendation in JSON format.
"""

            duration = time.time() - start_time
            AI_PROMPT_GENERATION_DURATION_SECONDS.observe(duration)
            AI_PROMPT_VERSION_USAGE_TOTAL.labels(version=self.prompt_version).inc()

            return prompt.strip()

        except Exception as e:
            logger.error(f"Error building prompt: {e}", exc_info=True)
            # Return fallback prompt
            return self._build_fallback_prompt(context)

    def _get_system_prompt(self, agent_type: str) -> str:
        """Get system prompt for the agent type."""
        system_prompts = {
            "momentum": """You are a Momentum Trading AI agent specialized in identifying and capitalizing on market trends.

Your expertise:
- Identifying strong directional moves with volume confirmation
- Distinguishing between sustainable trends and temporary spikes
- Timing entry and exit points based on momentum indicators""",
            "mean_reversion": """You are a Mean Reversion Trading AI agent specialized in identifying overbought/oversold conditions.

Your expertise:
- Using Bollinger Bands to identify price extremes
- RSI analysis for reversal opportunities
- Identifying when assets deviate from their mean and are likely to revert""",
            "sentiment": """You are a Sentiment Analysis Trading AI agent specialized in market psychology and news impact.

Your expertise:
- Analyzing market sentiment from news and social media
- Identifying sentiment-driven price movements
- Distinguishing between noise and meaningful sentiment shifts""",
            "volatility": """You are a Volatility Trading AI agent specialized in risk-adjusted position sizing and VPIN analysis.

Your expertise:
- VPIN (Volume-synchronized Probability of Informed Trading) analysis
- ATR-based position sizing
- Volatility regime detection and risk management""",
            "general": """You are a Trading AI agent that analyzes market opportunities across multiple dimensions.

Your expertise:
- Technical analysis
- Market structure analysis
- Risk-adjusted decision making""",
        }

        return system_prompts.get(agent_type.lower(), system_prompts["general"])

    def _build_market_section(self, context: PromptContext) -> str:
        """Build market data section of the prompt."""
        md = context.market_data

        # Handle missing volume_24h attribute gracefully
        volume_24h = getattr(md, "volume_24h", 0.0)
        if volume_24h is None:
            volume_24h = 0.0

        section = f"""**Symbol**: {context.symbol}
**Current Price**: ${md.price:.4f}
**24h Change**: {md.change_24h:.2f}%
**24h Volume**: {volume_24h:,.0f}
**Volatility (ATR)**: {getattr(md, 'atr', 0.0) or 0.0:.4f}
"""

        if hasattr(md, "sma_20") and md.sma_20:
            section += f"**20-period SMA**: ${md.sma_20:.4f}\n"

        if hasattr(md, "rsi") and md.rsi:
            section += f"**RSI (14)**: {md.rsi:.2f}\n"

        return section

    def _build_signals_section(self, context: PromptContext) -> str:
        """Build technical signals section."""
        if not context.technical_signals:
            return "**Technical Signals**: None available."

        signals = []
        for signal in context.technical_signals[:3]:  # Top 3 signals
            signal_str = f"- **{signal.get('strategy_name', 'Unknown')}**: {signal.get('direction', 'HOLD')} (confidence: {signal.get('confidence', 0):.2f})"
            if signal.get("reasoning"):
                signal_str += f"\n  Reasoning: {signal.get('reasoning', '')[:100]}"
            signals.append(signal_str)

        return "**Technical Signals**:\n" + "\n".join(signals)

    def _build_constraints_section(self, context: PromptContext) -> str:
        """Build constraints and rules section."""
        max_position = self.settings.max_position_pct * 100
        min_confidence = self.settings.min_llm_confidence

        constraints = f"""**Trading Constraints**:
- Maximum position size: {max_position}% of portfolio
- Minimum confidence threshold: {min_confidence:.2f}
- Risk management: All positions must have stop-loss and take-profit levels
- Position sizing: Conservative allocation based on confidence level"""

        if context.risk_limits:
            constraints += f"\n- Current portfolio risk limits: {context.risk_limits}"

        return constraints

    def _build_examples_section(self) -> str:
        """Build few-shot examples section."""
        return """## Example Responses

**Example 1 - Strong Buy Signal**:
```json
{
  "direction": "BUY",
  "confidence": 0.85,
  "rationale": "Strong upward momentum with 15% 24h gain, high volume confirmation (2x average), RSI at 65 indicating room for further upside. Breakout above resistance level.",
  "risk_assessment": "Medium risk. Stop-loss at 5% below entry, take-profit at 8% above entry.",
  "position_size_recommendation": 0.025
}
```

**Example 2 - Hold Signal**:
```json
{
  "direction": "HOLD",
  "confidence": 0.60,
  "rationale": "Mixed signals: slight positive momentum but volume declining. RSI neutral at 52. Waiting for clearer directional confirmation.",
  "risk_assessment": "Low risk - no new position recommended.",
  "position_size_recommendation": 0.0
}
```

**Example 3 - Sell Signal**:
```json
{
  "direction": "SELL",
  "confidence": 0.75,
  "rationale": "Price extended 20% above 20-day SMA, RSI overbought at 78, volume decreasing on recent moves. Likely consolidation or reversal ahead.",
  "risk_assessment": "Medium-high risk. Consider taking profits or reducing position size.",
  "position_size_recommendation": 0.015
}
```"""

    def _build_fallback_prompt(self, context: PromptContext) -> str:
        """Build a minimal fallback prompt if template loading fails."""
        return f"""Analyze {context.symbol} for trading opportunity.

Market Data:
- Price: ${context.market_data.price:.4f}
- 24h Change: {context.market_data.change_24h:.2f}%

Provide trading recommendation in JSON format:
{{
    "direction": "BUY|SELL|HOLD",
    "confidence": 0.0-1.0,
    "rationale": "brief explanation"
}}"""


class ResponseValidator:
    """Validates and parses AI responses."""

    def __init__(self):
        self.settings = get_settings()

    def validate_and_parse(
        self, raw_response: Dict[str, Any], symbol: str
    ) -> Optional[AIStrategyResponse]:
        """Validate and parse AI response into structured format."""
        try:
            # Extract content from response
            content = self._extract_content(raw_response)
            if not content:
                AI_RESPONSE_PARSE_ERRORS_TOTAL.labels(error_type="empty_response").inc()
                return None

            # Parse JSON
            parsed = self._parse_json(content)
            if not parsed:
                AI_RESPONSE_PARSE_ERRORS_TOTAL.labels(error_type="json_parse_error").inc()
                return None

            # Validate schema
            try:
                validated = AIStrategyResponse(**parsed)
            except ValidationError as e:
                logger.warning(f"Validation error for {symbol}: {e}")
                AI_RESPONSE_VALIDATION_ERRORS_TOTAL.labels(error_type="schema_validation").inc()
                return None

            # Validate business rules
            if not self._validate_business_rules(validated):
                AI_RESPONSE_VALIDATION_ERRORS_TOTAL.labels(error_type="business_rule").inc()
                return None

            # Record confidence metric
            AI_CONFIDENCE_DISTRIBUTION.observe(validated.confidence)

            return validated

        except Exception as e:
            logger.error(f"Unexpected error validating response: {e}", exc_info=True)
            AI_RESPONSE_PARSE_ERRORS_TOTAL.labels(error_type="unexpected_error").inc()
            return None

    def _extract_content(self, response: Dict[str, Any]) -> Optional[str]:
        """Extract content string from response dict."""
        # Try common response formats
        content = (
            response.get("response")
            or response.get("content")
            or response.get("text")
            or response.get("choices", [{}])[0].get("message", {}).get("content")
            or response.get("predictions", [{}])[0].get("content")
        )

        if isinstance(content, dict):
            content = content.get("text") or content.get("content")

        return str(content) if content else None

    def _parse_json(self, content: str) -> Optional[Dict[str, Any]]:
        """Parse JSON from content string, handling markdown code blocks."""
        if not content:
            return None

        # Clean up content
        content = content.strip()

        # Remove markdown code blocks
        if content.startswith("```json"):
            content = content[7:]
        elif content.startswith("```"):
            content = content[3:]

        if content.endswith("```"):
            content = content[:-3]

        content = content.strip()

        # Try to find JSON object in the content
        try:
            # Direct JSON parse
            return json.loads(content)
        except json.JSONDecodeError:
            # Try to extract JSON from text
            import re

            json_match = re.search(r'\{[^{}]*"direction"[^{}]*\}', content, re.DOTALL)
            if json_match:
                try:
                    return json.loads(json_match.group(0))
                except json.JSONDecodeError:
                    pass

            # Try to find any JSON-like structure
            json_match = re.search(r"\{.*\}", content, re.DOTALL)
            if json_match:
                try:
                    return json.loads(json_match.group(0))
                except json.JSONDecodeError:
                    pass

        return None

    def _validate_business_rules(self, response: AIStrategyResponse) -> bool:
        """Validate business rules beyond schema validation."""
        # Rule 1: High confidence requires strong rationale
        if response.confidence > 0.7 and len(response.rationale) < 30:
            logger.warning(f"High confidence ({response.confidence}) but weak rationale")
            return False

        # Rule 2: Direction must match confidence level
        if response.direction == "HOLD" and response.confidence > 0.8:
            logger.warning("HOLD direction with very high confidence seems contradictory")
            # Not a hard failure, but log it

        # Rule 3: Position size should correlate with confidence
        if response.position_size_recommendation:
            expected_min_size = response.confidence * 0.01  # 1% base
            expected_max_size = response.confidence * 0.05  # 5% max
            if (
                response.position_size_recommendation < expected_min_size * 0.5
                or response.position_size_recommendation > expected_max_size * 1.5
            ):
                logger.debug(
                    f"Position size {response.position_size_recommendation} outside expected range for confidence {response.confidence}"
                )

        return True

    def create_fallback_signal(
        self, symbol: str, reason: str = "Response validation failed"
    ) -> AIStrategyResponse:
        """Create a fallback HOLD signal when validation fails."""
        return AIStrategyResponse(
            direction="HOLD",
            confidence=0.3,
            rationale=f"{reason}. Falling back to conservative HOLD position.",
            risk_assessment="Unable to assess risk - defaulting to no position.",
            position_size_recommendation=0.0,
        )
