"""
Error Classification System

Categorizes errors by type and severity to enable intelligent handling.
Used by all trading bots and the alpha engine.
"""

from enum import Enum
from typing import Tuple


class ErrorCategory(Enum):
    """Error categories with defined handling strategies."""

    TRANSIENT = "transient"  # Retry automatically
    RESOURCE = "resource"  # Skip, don't notify (user aware)
    AUTHENTICATION = "authentication"  # Alert immediately (critical)
    CONFIGURATION = "configuration"  # Alert immediately (requires fix)
    EXCHANGE = "exchange"  # Skip, log only (expected)
    SYSTEM = "system"  # Circuit break if persistent


class ErrorSeverity(Enum):
    """Error severity levels for notification decisions."""

    INFO = 1  # Log only, add to digest
    WARNING = 2  # Log, maybe notify if persistent
    ERROR = 3  # Log, circuit break, notify
    CRITICAL = 4  # Immediate alert regardless


# Error pattern matching (pattern -> (category, severity))
ERROR_PATTERNS = {
    # Transient errors - retry with backoff
    "TimeoutError": (ErrorCategory.TRANSIENT, ErrorSeverity.WARNING),
    "ConnectionError": (ErrorCategory.TRANSIENT, ErrorSeverity.WARNING),
    "Connection reset": (ErrorCategory.TRANSIENT, ErrorSeverity.WARNING),
    "429": (ErrorCategory.TRANSIENT, ErrorSeverity.INFO),  # Rate limit
    "Too many requests": (ErrorCategory.TRANSIENT, ErrorSeverity.INFO),
    "SendTransactionPreflightFailure": (ErrorCategory.TRANSIENT, ErrorSeverity.WARNING),
    # Resource errors - skip trade, don't spam notifications
    "Insufficient Margin": (ErrorCategory.RESOURCE, ErrorSeverity.INFO),
    "InsufficientCollateral": (ErrorCategory.RESOURCE, ErrorSeverity.INFO),
    "Margin Health too low": (ErrorCategory.RESOURCE, ErrorSeverity.INFO),
    "Insufficient balance": (ErrorCategory.RESOURCE, ErrorSeverity.INFO),
    "Account health": (ErrorCategory.RESOURCE, ErrorSeverity.INFO),
    # Authentication errors - immediate alert
    "Invalid API-key": (ErrorCategory.AUTHENTICATION, ErrorSeverity.CRITICAL),
    "-2015": (ErrorCategory.AUTHENTICATION, ErrorSeverity.CRITICAL),
    "Unauthorized": (ErrorCategory.AUTHENTICATION, ErrorSeverity.CRITICAL),
    "Authentication failed": (ErrorCategory.AUTHENTICATION, ErrorSeverity.CRITICAL),
    "sign_message": (ErrorCategory.AUTHENTICATION, ErrorSeverity.CRITICAL),
    # Configuration errors - immediate alert
    "Environment variable": (ErrorCategory.CONFIGURATION, ErrorSeverity.CRITICAL),
    "Missing configuration": (ErrorCategory.CONFIGURATION, ErrorSeverity.CRITICAL),
    # Exchange-specific errors - expected, don't notify
    "Could not get price": (ErrorCategory.EXCHANGE, ErrorSeverity.WARNING),
    "Symbol not found": (ErrorCategory.EXCHANGE, ErrorSeverity.WARNING),
    "Market closed": (ErrorCategory.EXCHANGE, ErrorSeverity.INFO),
    "Order rejected": (ErrorCategory.EXCHANGE, ErrorSeverity.WARNING),
    # System errors - circuit break if persistent
    "WebSocket": (ErrorCategory.SYSTEM, ErrorSeverity.WARNING),
    "Database": (ErrorCategory.SYSTEM, ErrorSeverity.ERROR),
    "Pub/Sub": (ErrorCategory.SYSTEM, ErrorSeverity.WARNING),
}


def classify_error(error_message: str) -> Tuple[ErrorCategory, ErrorSeverity]:
    """
    Classify an error message and return its category and severity.

    Args:
        error_message: The error message to classify

    Returns:
        Tuple of (ErrorCategory, ErrorSeverity)
    """
    error_lower = error_message.lower()

    # Check patterns in order of specificity
    for pattern, (category, severity) in ERROR_PATTERNS.items():
        if pattern.lower() in error_lower:
            return category, severity

    # Default: treat as system error
    return ErrorCategory.SYSTEM, ErrorSeverity.ERROR


def should_notify_immediately(category: ErrorCategory, severity: ErrorSeverity) -> bool:
    """
    Determine if an error should trigger immediate notification.

    Args:
        category: Error category
        severity: Error severity

    Returns:
        True if should notify immediately, False otherwise
    """
    # Always notify critical errors
    if severity == ErrorSeverity.CRITICAL:
        return True

    # Never notify INFO or resource errors
    if severity == ErrorSeverity.INFO or category == ErrorCategory.RESOURCE:
        return False

    # Authentication/config errors are always critical
    if category in (ErrorCategory.AUTHENTICATION, ErrorCategory.CONFIGURATION):
        return True

    # For other errors, only notify ERROR and above
    return severity >= ErrorSeverity.ERROR
