"""
Centralized Error Handling for Sapphire AI Trading System

This module provides a structured error hierarchy based on first principles:

PRINCIPLE 1: All errors should be typed and categorized
    - Makes debugging easier
    - Enables targeted error handling
    - Improves logging clarity

PRINCIPLE 2: Errors should carry context
    - What operation failed?
    - What were the inputs?
    - What is the recovery path?

PRINCIPLE 3: Errors should be actionable
    - User-facing messages should explain what to do
    - System errors should include remediation hints
"""

from __future__ import annotations

import logging
import traceback
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


class ErrorSeverity(Enum):
    """Error severity levels for prioritization."""

    LOW = "low"  # Informational, no action needed
    MEDIUM = "medium"  # Degraded functionality, monitoring needed
    HIGH = "high"  # Feature broken, intervention needed
    CRITICAL = "critical"  # System down, immediate action required


class ErrorCategory(Enum):
    """Error categories for routing and handling."""

    EXCHANGE = "exchange"  # Exchange API errors
    TRADING = "trading"  # Trade execution errors
    RISK = "risk"  # Risk limit violations
    DATA = "data"  # Data pipeline errors
    AUTH = "auth"  # Authentication errors
    NETWORK = "network"  # Network/connectivity errors
    VALIDATION = "validation"  # Input validation errors
    INTERNAL = "internal"  # Internal system errors


@dataclass
class ErrorContext:
    """Rich context for error tracking and debugging."""

    operation: str  # What operation was attempted
    component: str  # Which component failed
    inputs: Dict[str, Any] = field(default_factory=dict)  # Sanitized inputs
    timestamp: datetime = field(default_factory=datetime.utcnow)
    correlation_id: Optional[str] = None  # For request tracing
    user_id: Optional[str] = None  # Affected user
    symbol: Optional[str] = None  # Trading symbol if relevant

    def to_dict(self) -> Dict[str, Any]:
        return {
            "operation": self.operation,
            "component": self.component,
            "inputs": self.inputs,
            "timestamp": self.timestamp.isoformat(),
            "correlation_id": self.correlation_id,
            "user_id": self.user_id,
            "symbol": self.symbol,
        }


class SapphireError(Exception):
    """
    Base exception for all Sapphire trading system errors.

    All errors inherit from this class, enabling:
    - Consistent logging format
    - Centralized error tracking
    - Structured error responses

    Usage:
        raise SapphireError(
            message="Failed to execute trade",
            code="TRADE_EXEC_001",
            category=ErrorCategory.TRADING,
            severity=ErrorSeverity.HIGH,
            context=ErrorContext(operation="execute_trade", component="trading_service")
        )
    """

    def __init__(
        self,
        message: str,
        code: str = "UNKNOWN",
        category: ErrorCategory = ErrorCategory.INTERNAL,
        severity: ErrorSeverity = ErrorSeverity.MEDIUM,
        context: Optional[ErrorContext] = None,
        cause: Optional[Exception] = None,
        recovery_hint: Optional[str] = None,
    ):
        super().__init__(message)
        self.message = message
        self.code = code
        self.category = category
        self.severity = severity
        self.context = context
        self.cause = cause
        self.recovery_hint = recovery_hint
        self.traceback = traceback.format_exc() if cause else None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API responses and logging."""
        return {
            "error": True,
            "code": self.code,
            "message": self.message,
            "category": self.category.value,
            "severity": self.severity.value,
            "context": self.context.to_dict() if self.context else None,
            "recovery_hint": self.recovery_hint,
            "cause": str(self.cause) if self.cause else None,
        }

    def log(self):
        """Log this error with appropriate severity."""
        log_data = self.to_dict()

        if self.severity == ErrorSeverity.CRITICAL:
            logger.critical(f"[{self.code}] {self.message}", extra=log_data)
        elif self.severity == ErrorSeverity.HIGH:
            logger.error(f"[{self.code}] {self.message}", extra=log_data)
        elif self.severity == ErrorSeverity.MEDIUM:
            logger.warning(f"[{self.code}] {self.message}", extra=log_data)
        else:
            logger.info(f"[{self.code}] {self.message}", extra=log_data)


# ═══════════════════════════════════════════════════════════════════════════════
# EXCHANGE ERRORS
# ═══════════════════════════════════════════════════════════════════════════════


class ExchangeError(SapphireError):
    """Base class for exchange-related errors."""

    def __init__(self, message: str, **kwargs):
        kwargs.setdefault("category", ErrorCategory.EXCHANGE)
        super().__init__(message, **kwargs)


class ExchangeConnectionError(ExchangeError):
    """Failed to connect to exchange API."""

    def __init__(self, exchange: str, cause: Optional[Exception] = None):
        super().__init__(
            message=f"Failed to connect to {exchange} exchange",
            code="EX_CONN_001",
            severity=ErrorSeverity.HIGH,
            cause=cause,
            recovery_hint="Check network connectivity and exchange API status",
        )


class ExchangeAPIError(ExchangeError):
    """Exchange API returned an error response."""

    def __init__(self, exchange: str, api_code: str, api_message: str):
        super().__init__(
            message=f"{exchange} API error: {api_message}",
            code=f"EX_API_{api_code}",
            severity=ErrorSeverity.MEDIUM,
            recovery_hint="Check exchange API documentation for error code details",
        )


class InsufficientBalanceError(ExchangeError):
    """Insufficient balance for trade execution."""

    def __init__(self, required: float, available: float, symbol: str):
        super().__init__(
            message=f"Insufficient balance: need {required}, have {available}",
            code="EX_BAL_001",
            severity=ErrorSeverity.MEDIUM,
            context=ErrorContext(
                operation="check_balance",
                component="exchange",
                inputs={"required": required, "available": available},
                symbol=symbol,
            ),
            recovery_hint="Wait for pending orders to settle or deposit more funds",
        )


# ═══════════════════════════════════════════════════════════════════════════════
# TRADING ERRORS
# ═══════════════════════════════════════════════════════════════════════════════


class TradingError(SapphireError):
    """Base class for trading-related errors."""

    def __init__(self, message: str, **kwargs):
        kwargs.setdefault("category", ErrorCategory.TRADING)
        super().__init__(message, **kwargs)


class OrderExecutionError(TradingError):
    """Failed to execute an order."""

    def __init__(self, symbol: str, side: str, reason: str, cause: Optional[Exception] = None):
        super().__init__(
            message=f"Failed to execute {side} order for {symbol}: {reason}",
            code="TRADE_EXEC_001",
            severity=ErrorSeverity.HIGH,
            context=ErrorContext(
                operation="execute_order",
                component="trading_service",
                inputs={"symbol": symbol, "side": side},
                symbol=symbol,
            ),
            cause=cause,
            recovery_hint="Check exchange status and retry with smaller position",
        )


class PositionNotFoundError(TradingError):
    """Attempted operation on non-existent position."""

    def __init__(self, symbol: str):
        super().__init__(
            message=f"No open position found for {symbol}",
            code="TRADE_POS_001",
            severity=ErrorSeverity.LOW,
            context=ErrorContext(
                operation="get_position",
                component="position_manager",
                symbol=symbol,
            ),
        )


# ═══════════════════════════════════════════════════════════════════════════════
# RISK ERRORS
# ═══════════════════════════════════════════════════════════════════════════════


class RiskError(SapphireError):
    """Base class for risk-related errors."""

    def __init__(self, message: str, **kwargs):
        kwargs.setdefault("category", ErrorCategory.RISK)
        super().__init__(message, **kwargs)


class RiskLimitExceededError(RiskError):
    """A risk limit was exceeded, blocking the operation."""

    def __init__(self, limit_name: str, limit_value: float, current_value: float):
        super().__init__(
            message=f"Risk limit '{limit_name}' exceeded: {current_value} > {limit_value}",
            code="RISK_LIMIT_001",
            severity=ErrorSeverity.HIGH,
            context=ErrorContext(
                operation="check_risk_limits",
                component="risk_manager",
                inputs={"limit_name": limit_name, "limit": limit_value, "current": current_value},
            ),
            recovery_hint="Wait for positions to close or manually reduce exposure",
        )


class DailyLossLimitError(RiskError):
    """Daily loss limit reached, preventing further trading."""

    def __init__(self, loss_pct: float, limit_pct: float):
        super().__init__(
            message=f"Daily loss limit reached: {loss_pct:.2f}% (limit: {limit_pct:.2f}%)",
            code="RISK_DAY_001",
            severity=ErrorSeverity.CRITICAL,
            recovery_hint="Trading suspended until next trading day",
        )


# ═══════════════════════════════════════════════════════════════════════════════
# VALIDATION ERRORS
# ═══════════════════════════════════════════════════════════════════════════════


class ValidationError(SapphireError):
    """Input validation failed."""

    def __init__(self, field: str, message: str, value: Any = None):
        super().__init__(
            message=f"Validation error for '{field}': {message}",
            code="VAL_001",
            category=ErrorCategory.VALIDATION,
            severity=ErrorSeverity.LOW,
            context=ErrorContext(
                operation="validate_input",
                component="api",
                inputs={"field": field, "value": str(value)[:100] if value else None},
            ),
        )


# ═══════════════════════════════════════════════════════════════════════════════
# HELPER FUNCTIONS
# ═══════════════════════════════════════════════════════════════════════════════


def wrap_exception(
    exc: Exception, operation: str, component: str, **context_kwargs
) -> SapphireError:
    """
    Wrap a standard Python exception in a SapphireError.

    Useful for catching generic exceptions and converting them
    to structured errors with context.

    Usage:
        try:
            do_something()
        except Exception as e:
            raise wrap_exception(e, "do_something", "my_service")
    """
    return SapphireError(
        message=str(exc),
        code="WRAPPED_ERR",
        category=ErrorCategory.INTERNAL,
        severity=ErrorSeverity.MEDIUM,
        context=ErrorContext(
            operation=operation,
            component=component,
            **context_kwargs,
        ),
        cause=exc,
    )
