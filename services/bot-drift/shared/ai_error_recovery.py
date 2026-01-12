"""
AI Error Recovery Agent - Intelligent Self-Healing for Trade Failures

Analyzes trade execution errors, classifies them, and either applies
automatic fixes or consults LLM for complex recovery strategies.

Part of the AI-Powered Resilience Layer for ACTS.
"""

import asyncio
import logging
import re
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class RecoveryAction:
    """Recommended recovery action for an error."""

    error_type: str
    recoverable: bool
    action: str  # "retry", "adjust", "skip", "escalate"
    corrections: Dict[str, Any]  # Suggested corrections to apply
    reason: str
    confidence: float


class AIErrorRecoveryAgent:
    """
    Analyzes trade failures and suggests/applies intelligent fixes.

    Error Classification Categories:
    - precision: Tick size / lot size violations
    - symbol: Invalid or unknown symbol
    - funds: Insufficient balance
    - rate_limit: API rate limiting
    - network: Connection issues
    - auth: Authentication failures
    - market: Market conditions (halted, illiquid)
    - unknown: Unclassified errors
    """

    # Known error patterns with classification and suggested actions
    ERROR_PATTERNS = [
        # Precision errors
        (r"Price must be divisible by tick size", "precision", "adjust", 0.95),
        (r"Order has invalid size", "precision", "adjust", 0.95),
        (r"quantity.*precision", "precision", "adjust", 0.9),
        (r"Precision is over", "precision", "adjust", 0.9),
        # Symbol errors
        (r"Invalid.*symbol", "symbol", "adjust", 0.9),
        (r"Symbol.*not found", "symbol", "adjust", 0.9),
        (r"Unknown.*token", "symbol", "adjust", 0.85),
        (r"Invalid token", "symbol", "adjust", 0.9),
        # Funds errors
        (r"Insufficient.*funds", "funds", "skip", 0.95),
        (r"Not enough.*balance", "funds", "skip", 0.95),
        (r"Insufficient margin", "funds", "skip", 0.9),
        (r"INSUFFICIENT_BALANCE", "funds", "skip", 0.95),
        # Rate limiting
        (r"rate limit", "rate_limit", "retry", 0.95),
        (r"Too many requests", "rate_limit", "retry", 0.95),
        (r"429", "rate_limit", "retry", 0.9),
        # Network errors
        (r"Connection.*refused", "network", "retry", 0.8),
        (r"timeout", "network", "retry", 0.85),
        (r"ECONNRESET", "network", "retry", 0.85),
        # Auth errors
        (r"Invalid API", "auth", "escalate", 0.95),
        (r"Authentication failed", "auth", "escalate", 0.95),
        (r"Signature.*invalid", "auth", "escalate", 0.9),
        # Market conditions
        (r"Market.*halted", "market", "skip", 0.95),
        (r"Trading.*suspended", "market", "skip", 0.95),
        (r"Reduce only", "market", "adjust", 0.8),
    ]

    def __init__(self):
        self._recovery_handlers: Dict[str, Callable] = {
            "precision": self._handle_precision_error,
            "symbol": self._handle_symbol_error,
            "funds": self._handle_funds_error,
            "rate_limit": self._handle_rate_limit,
            "network": self._handle_network_error,
            "auth": self._handle_auth_error,
            "market": self._handle_market_error,
        }

        # Track error frequency for adaptive behavior
        self._error_counts: Dict[str, int] = {}
        self._consecutive_failures: Dict[str, int] = {}

    async def handle_error(self, error_message: str, context: Dict[str, Any]) -> RecoveryAction:
        """
        Analyze an error and return recommended recovery action.

        Args:
            error_message: The error message from the failed trade
            context: Trade context including signal, platform, attempt number

        Returns:
            RecoveryAction with classification and suggested fixes
        """
        # 1. Classify the error
        error_type, suggested_action, confidence = self._classify_error(error_message)

        # Track error frequency
        self._error_counts[error_type] = self._error_counts.get(error_type, 0) + 1

        # 2. Get context info
        platform = context.get("platform", "unknown")
        symbol = context.get("symbol", "unknown")
        attempt = context.get("attempt", 0)

        # 3. Apply specific handler if available
        handler = self._recovery_handlers.get(error_type)
        if handler:
            recovery = await handler(error_message, context)
            if recovery:
                return recovery

        # 4. For unknown errors, consult LLM
        if error_type == "unknown":
            llm_recovery = await self._llm_analyze_error(error_message, context)
            if llm_recovery:
                return llm_recovery

        # 5. Default recovery action
        recoverable = suggested_action in ("retry", "adjust")

        return RecoveryAction(
            error_type=error_type,
            recoverable=recoverable,
            action=suggested_action,
            corrections={},
            reason=f"Classified as '{error_type}' with {confidence:.0%} confidence",
            confidence=confidence,
        )

    def _classify_error(self, error_message: str) -> tuple:
        """Classify error based on pattern matching."""
        error_lower = error_message.lower()

        for pattern, error_type, action, confidence in self.ERROR_PATTERNS:
            if re.search(pattern, error_message, re.IGNORECASE):
                return (error_type, action, confidence)

        return ("unknown", "escalate", 0.3)

    async def _handle_precision_error(
        self, error_message: str, context: Dict[str, Any]
    ) -> Optional[RecoveryAction]:
        """Handle precision-related errors by adjusting order parameters."""
        from .precision_normalizer import get_precision_normalizer

        normalizer = get_precision_normalizer()

        signal = context.get("signal")
        platform = context.get("platform", "hyperliquid")

        if not signal:
            return None

        try:
            # Re-normalize with fresh exchange info
            normalized = await normalizer.normalize_order(
                symbol=signal.symbol,
                platform=platform,
                price=signal.entry_price or 0,
                quantity=signal.quantity or 0,
            )

            return RecoveryAction(
                error_type="precision",
                recoverable=normalized["valid"],
                action="retry" if normalized["valid"] else "skip",
                corrections={
                    "price": normalized["price"],
                    "quantity": normalized["quantity"],
                },
                reason=f"Re-normalized order: {normalized.get('warnings', [])}",
                confidence=0.9,
            )

        except Exception as e:
            logger.warning(f"Precision recovery failed: {e}")
            return None

    async def _handle_symbol_error(
        self, error_message: str, context: Dict[str, Any]
    ) -> Optional[RecoveryAction]:
        """Handle symbol-related errors by re-resolving the symbol."""
        from .ai_symbol_resolver import get_symbol_resolver

        resolver = get_symbol_resolver()

        signal = context.get("signal")
        platform = context.get("platform", "hyperliquid")

        if not signal:
            return None

        try:
            # Re-resolve symbol with LLM fallback
            result = await resolver.resolve(signal.symbol, platform, use_llm_fallback=True)

            if result.confidence >= 0.6:
                return RecoveryAction(
                    error_type="symbol",
                    recoverable=True,
                    action="retry",
                    corrections={
                        "symbol": result.resolved,
                    },
                    reason=f"Re-resolved symbol via {result.method}: {result.original} -> {result.resolved}",
                    confidence=result.confidence,
                )

        except Exception as e:
            logger.warning(f"Symbol recovery failed: {e}")

        return None

    async def _handle_funds_error(
        self, error_message: str, context: Dict[str, Any]
    ) -> Optional[RecoveryAction]:
        """Handle insufficient funds errors."""
        signal = context.get("signal")

        # Try reducing position size
        if signal and hasattr(signal, "quantity") and signal.quantity:
            reduced_qty = signal.quantity * 0.5  # Try 50% size

            return RecoveryAction(
                error_type="funds",
                recoverable=True,
                action="retry",
                corrections={
                    "quantity": reduced_qty,
                },
                reason=f"Reduced position size from {signal.quantity} to {reduced_qty}",
                confidence=0.6,
            )

        return RecoveryAction(
            error_type="funds",
            recoverable=False,
            action="skip",
            corrections={},
            reason="Insufficient funds - manual intervention required",
            confidence=0.95,
        )

    async def _handle_rate_limit(
        self, error_message: str, context: Dict[str, Any]
    ) -> Optional[RecoveryAction]:
        """Handle rate limiting by suggesting delay."""
        attempt = context.get("attempt", 0)

        # Exponential backoff delay
        delay = min(2**attempt * 1000, 30000)  # Max 30 seconds

        return RecoveryAction(
            error_type="rate_limit",
            recoverable=True,
            action="retry",
            corrections={
                "delay_ms": delay,
            },
            reason=f"Rate limited - wait {delay}ms before retry",
            confidence=0.9,
        )

    async def _handle_network_error(
        self, error_message: str, context: Dict[str, Any]
    ) -> Optional[RecoveryAction]:
        """Handle network errors with retry."""
        attempt = context.get("attempt", 0)

        if attempt < 3:
            return RecoveryAction(
                error_type="network",
                recoverable=True,
                action="retry",
                corrections={
                    "delay_ms": 1000 * (attempt + 1),
                },
                reason=f"Network error - retry in {(attempt + 1)}s",
                confidence=0.8,
            )

        return RecoveryAction(
            error_type="network",
            recoverable=False,
            action="skip",
            corrections={},
            reason="Network errors persist after 3 retries",
            confidence=0.9,
        )

    async def _handle_auth_error(
        self, error_message: str, context: Dict[str, Any]
    ) -> Optional[RecoveryAction]:
        """Handle authentication errors."""
        return RecoveryAction(
            error_type="auth",
            recoverable=False,
            action="escalate",
            corrections={},
            reason="Authentication failure - check API credentials",
            confidence=0.95,
        )

    async def _handle_market_error(
        self, error_message: str, context: Dict[str, Any]
    ) -> Optional[RecoveryAction]:
        """Handle market condition errors."""
        return RecoveryAction(
            error_type="market",
            recoverable=False,
            action="skip",
            corrections={},
            reason="Market conditions prevent execution",
            confidence=0.9,
        )

    async def _llm_analyze_error(
        self, error_message: str, context: Dict[str, Any]
    ) -> Optional[RecoveryAction]:
        """Use LLM to analyze unknown errors."""
        try:
            from .vertex_ai_client import get_vertex_client

            client = get_vertex_client()
            if not client:
                return None

            platform = context.get("platform", "unknown")
            symbol = context.get("symbol", "unknown")

            prompt = f"""You are an expert cryptocurrency trading error analyst.

Analyze this trade execution error and provide recovery guidance:

Error: {error_message}
Platform: {platform}
Symbol: {symbol}

Respond in this JSON format:
{{
    "error_type": "precision|symbol|funds|rate_limit|network|auth|market|unknown",
    "recoverable": true|false,
    "action": "retry|adjust|skip|escalate",
    "suggested_fix": "brief description of fix",
    "confidence": 0.0-1.0
}}

Only respond with valid JSON, no other text.
"""

            response = await client.generate_content(prompt)

            import json

            result = json.loads(response.text.strip())

            return RecoveryAction(
                error_type=result.get("error_type", "unknown"),
                recoverable=result.get("recoverable", False),
                action=result.get("action", "skip"),
                corrections={},
                reason=f"LLM analysis: {result.get('suggested_fix', 'Unknown')}",
                confidence=result.get("confidence", 0.5),
            )

        except Exception as e:
            logger.warning(f"LLM error analysis failed: {e}")
            return None

    def get_error_stats(self) -> Dict[str, int]:
        """Get error frequency statistics."""
        return dict(self._error_counts)


# Global instance
_agent: Optional[AIErrorRecoveryAgent] = None


def get_error_recovery_agent() -> AIErrorRecoveryAgent:
    """Get global AIErrorRecoveryAgent instance."""
    global _agent
    if _agent is None:
        _agent = AIErrorRecoveryAgent()
    return _agent


async def recover_from_error(error_message: str, context: Dict[str, Any]) -> RecoveryAction:
    """Convenience function to handle an error."""
    agent = get_error_recovery_agent()
    return await agent.handle_error(error_message, context)
