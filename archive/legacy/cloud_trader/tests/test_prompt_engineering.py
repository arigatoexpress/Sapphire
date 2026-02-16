"""Unit tests for prompt engineering functionality."""

import json
from unittest.mock import Mock, patch

import pytest

from cloud_trader.prompt_engineer import PromptBuilder, PromptContext, ResponseValidator
from cloud_trader.schemas import AIStrategyResponse
from cloud_trader.strategy import MarketSnapshot


@pytest.fixture
def sample_market_snapshot():
    """Create a sample market snapshot for testing."""
    return MarketSnapshot(
        price=50000.0,
        volume_24h=1000000.0,
        change_24h=5.5,
        volatility=0.02,
        sma_20=49000.0,
        rsi=65.0,
    )


@pytest.fixture
def sample_prompt_context(sample_market_snapshot):
    """Create a sample prompt context."""
    return PromptContext(
        symbol="BTCUSDT",
        market_data=sample_market_snapshot,
        technical_signals=[
            {
                "strategy_name": "Momentum",
                "direction": "BUY",
                "confidence": 0.75,
                "reasoning": "Strong upward trend",
            }
        ],
        agent_type="momentum",
    )


@pytest.fixture
def prompt_builder():
    """Create a prompt builder instance."""
    return PromptBuilder(prompt_version="v1.0")


@pytest.fixture
def response_validator():
    """Create a response validator instance."""
    return ResponseValidator()


class TestPromptBuilder:
    """Test prompt builder functionality."""

    def test_build_prompt_basic(self, prompt_builder, sample_prompt_context):
        """Test basic prompt generation."""
        prompt = prompt_builder.build_prompt(sample_prompt_context)

        assert isinstance(prompt, str)
        assert len(prompt) > 0
        assert "BTCUSDT" in prompt
        assert "50000.0" in prompt
        assert "5.5" in prompt

    def test_build_prompt_agent_types(self, prompt_builder, sample_market_snapshot):
        """Test prompt generation for different agent types."""
        agent_types = ["momentum", "mean_reversion", "sentiment", "volatility", "general"]

        for agent_type in agent_types:
            context = PromptContext(
                symbol="BTCUSDT", market_data=sample_market_snapshot, agent_type=agent_type
            )
            prompt = prompt_builder.build_prompt(context)

            assert isinstance(prompt, str)
            assert len(prompt) > 0
            # Check agent-specific content
            if agent_type == "momentum":
                assert "trend" in prompt.lower() or "momentum" in prompt.lower()

    def test_build_prompt_with_signals(self, prompt_builder, sample_prompt_context):
        """Test prompt generation with technical signals."""
        sample_prompt_context.technical_signals = [
            {
                "strategy_name": "Momentum",
                "direction": "BUY",
                "confidence": 0.85,
                "reasoning": "Strong upward momentum",
            },
            {
                "strategy_name": "RSI",
                "direction": "SELL",
                "confidence": 0.60,
                "reasoning": "Overbought conditions",
            },
        ]

        prompt = prompt_builder.build_prompt(sample_prompt_context)

        assert "Momentum" in prompt
        assert "BUY" in prompt
        assert "0.85" in prompt
        assert "RSI" in prompt

    def test_build_prompt_constraints(self, prompt_builder, sample_prompt_context):
        """Test that constraints section is included."""
        prompt = prompt_builder.build_prompt(sample_prompt_context)

        assert "Trading Constraints" in prompt or "Constraints" in prompt
        assert "position size" in prompt.lower() or "allocation" in prompt.lower()

    def test_build_prompt_examples(self, prompt_builder, sample_prompt_context):
        """Test that few-shot examples are included."""
        prompt = prompt_builder.build_prompt(sample_prompt_context)

        assert "Example" in prompt or "example" in prompt
        assert "JSON" in prompt or "json" in prompt

    def test_build_fallback_prompt(self, prompt_builder, sample_prompt_context):
        """Test fallback prompt generation on error."""
        # Force an error by corrupting context
        sample_prompt_context.agent_type = None

        prompt = prompt_builder.build_prompt(sample_prompt_context)

        assert isinstance(prompt, str)
        assert len(prompt) > 0
        assert "BTCUSDT" in prompt


class TestResponseValidator:
    """Test response validator functionality."""

    def test_validate_valid_response(self, response_validator):
        """Test validation of a valid response."""
        response = {
            "response": json.dumps(
                {
                    "direction": "BUY",
                    "confidence": 0.75,
                    "rationale": "Strong upward momentum with volume confirmation",
                    "risk_assessment": "Medium risk",
                    "position_size_recommendation": 0.025,
                }
            )
        }

        result = response_validator.validate_and_parse(response, "BTCUSDT")

        assert result is not None
        assert isinstance(result, AIStrategyResponse)
        assert result.direction == "BUY"
        assert result.confidence == 0.75
        assert len(result.rationale) >= 10

    def test_validate_response_with_markdown(self, response_validator):
        """Test parsing response wrapped in markdown code blocks."""
        response = {
            "response": """```json
{
  "direction": "SELL",
  "confidence": 0.65,
  "rationale": "Overbought conditions detected",
  "risk_assessment": "High risk",
  "position_size_recommendation": 0.015
}
```"""
        }

        result = response_validator.validate_and_parse(response, "BTCUSDT")

        assert result is not None
        assert result.direction == "SELL"
        assert result.confidence == 0.65

    def test_validate_response_invalid_direction(self, response_validator):
        """Test validation fails for invalid direction."""
        response = {
            "response": json.dumps(
                {
                    "direction": "INVALID",
                    "confidence": 0.75,
                    "rationale": "Test rationale that is long enough",
                }
            )
        }

        result = response_validator.validate_and_parse(response, "BTCUSDT")

        assert result is None

    def test_validate_response_invalid_confidence(self, response_validator):
        """Test validation fails for out-of-range confidence."""
        response = {
            "response": json.dumps(
                {
                    "direction": "BUY",
                    "confidence": 1.5,  # Out of range
                    "rationale": "Test rationale that is long enough",
                }
            )
        }

        result = response_validator.validate_and_parse(response, "BTCUSDT")

        assert result is None

    def test_validate_response_short_rationale(self, response_validator):
        """Test validation fails for short rationale."""
        response = {
            "response": json.dumps(
                {"direction": "BUY", "confidence": 0.75, "rationale": "Short"}  # Too short
            )
        }

        result = response_validator.validate_and_parse(response, "BTCUSDT")

        assert result is None

    def test_validate_response_missing_fields(self, response_validator):
        """Test validation fails for missing required fields."""
        response = {
            "response": json.dumps(
                {
                    "confidence": 0.75,
                    # Missing direction and rationale
                }
            )
        }

        result = response_validator.validate_and_parse(response, "BTCUSDT")

        assert result is None

    def test_validate_response_empty_response(self, response_validator):
        """Test validation handles empty response."""
        response = {"response": ""}

        result = response_validator.validate_and_parse(response, "BTCUSDT")

        assert result is None

    def test_validate_response_invalid_json(self, response_validator):
        """Test validation handles invalid JSON."""
        response = {"response": "This is not valid JSON {"}

        result = response_validator.validate_and_parse(response, "BTCUSDT")

        assert result is None

    def test_validate_business_rules_high_confidence_weak_rationale(self, response_validator):
        """Test business rule: high confidence requires strong rationale."""
        response = {
            "response": json.dumps(
                {
                    "direction": "BUY",
                    "confidence": 0.85,  # High confidence
                    "rationale": "Short rationale",  # Too short for high confidence
                }
            )
        }

        result = response_validator.validate_and_parse(response, "BTCUSDT")

        # Should fail business rule validation
        assert result is None

    def test_validate_business_rules_acceptable_high_confidence(self, response_validator):
        """Test business rule: high confidence with strong rationale passes."""
        response = {
            "response": json.dumps(
                {
                    "direction": "BUY",
                    "confidence": 0.85,
                    "rationale": "Strong upward momentum with 15% 24h gain, high volume confirmation (2x average), RSI at 65 indicating room for further upside",
                }
            )
        }

        result = response_validator.validate_and_parse(response, "BTCUSDT")

        assert result is not None
        assert result.confidence == 0.85

    def test_create_fallback_signal(self, response_validator):
        """Test fallback signal creation."""
        fallback = response_validator.create_fallback_signal("BTCUSDT", "Test reason")

        assert isinstance(fallback, AIStrategyResponse)
        assert fallback.direction == "HOLD"
        assert fallback.confidence == 0.3
        assert "Test reason" in fallback.rationale
        assert fallback.position_size_recommendation == 0.0

    def test_extract_content_various_formats(self, response_validator):
        """Test content extraction from various response formats."""
        # Test format 1: direct response
        response1 = {
            "response": '{"direction": "BUY", "confidence": 0.7, "rationale": "Test rationale"}',
            "content": "",
        }
        content1 = response_validator._extract_content(response1)
        assert content1 is not None
        assert "direction" in content1

        # Test format 2: content field
        response2 = {
            "content": '{"direction": "SELL", "confidence": 0.6, "rationale": "Test rationale"}'
        }
        content2 = response_validator._extract_content(response2)
        assert content2 is not None

        # Test format 3: choices array
        response3 = {
            "choices": [
                {
                    "message": {
                        "content": '{"direction": "HOLD", "confidence": 0.5, "rationale": "Test rationale"}'
                    }
                }
            ]
        }
        content3 = response_validator._extract_content(response3)
        assert content3 is not None

    def test_parse_json_with_extra_text(self, response_validator):
        """Test JSON parsing from text with extra content."""
        content = """Here is my analysis:
{
  "direction": "BUY",
  "confidence": 0.8,
  "rationale": "Strong momentum detected with high volume"
}
This is my recommendation."""

        parsed = response_validator._parse_json(content)

        assert parsed is not None
        assert parsed["direction"] == "BUY"
        assert parsed["confidence"] == 0.8


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
