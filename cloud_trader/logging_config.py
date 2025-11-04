"""Centralised structured logging configuration for Cloud Trader services."""

from __future__ import annotations

import contextvars
import logging
import sys
from typing import Optional

import structlog


_CONFIGURED = False

# Context variable for correlation ID tracking across async operations
correlation_id: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    "correlation_id", default=None
)


def configure_logging(level: Optional[str] = None) -> None:
    """Initialise structured logging using structlog and the logging module with correlation ID support."""

    global _CONFIGURED
    if _CONFIGURED:
        return

    log_level = level.upper() if level else "INFO"

    logging.basicConfig(
        level=getattr(logging, log_level, logging.INFO),
        format="%(message)s",
        stream=sys.stdout,
    )

    def add_correlation_id(logger, method_name, event_dict):
        """Add correlation ID to log context if available."""
        corr_id = correlation_id.get()
        if corr_id:
            event_dict["correlation_id"] = corr_id
        return event_dict

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,  # Merge contextvars into log context
            add_correlation_id,  # Add correlation ID
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.add_log_level,
            structlog.processors.StackInfoRenderer(),
            structlog.processors.dict_tracebacks,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(getattr(logging, log_level, logging.INFO)),
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    _CONFIGURED = True


__all__ = ["configure_logging"]


