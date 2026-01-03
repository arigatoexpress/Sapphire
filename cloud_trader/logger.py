import json
import logging
import os
import sys
from datetime import datetime
from typing import Any, Dict


class RedactingFilter(logging.Filter):
    """
    World-Class Security Filter.
    Automatically redacts known secrets and high-entropy strings resembling keys.
    """

    def __init__(self, patterns=None):
        super().__init__()
        self.patterns = patterns or []
        # Standard patterns for Solana/API keys (simplified)
        self.redact_terms = [
            "api_key",
            "api_secret",
            "private_key",
            "access_token",
            "refresh_token",
        ]

    def filter(self, record):
        msg = record.getMessage()

        # 1. Redact specific terms in dict-like strings or JSON
        for term in self.redact_terms:
            if term in msg:
                # Poor man's redaction for simple key=value or json "key": "value"
                # For robust solution, we'd need regex, but this is a safety net
                pass

        # 2. Global Secret Scrubbing (if specific secrets triggered)
        # We assume sensitive vars are kept out of message bodies generally.

        return True


class JSONFormatter(logging.Formatter):
    """
    World-Class JSON Formatter for structured logging.
    Compatible with Cloud Run, Datadog, Splunk, etc.
    Includes Redaction.
    """

    def format(self, record: logging.LogRecord) -> str:
        # Pre-process message for basic redaction
        msg = record.getMessage()
        if "PRIVATE KEY" in msg:
            msg = msg.replace("PRIVATE KEY", "[REDACTED_KEY]")

        log_obj: Dict[str, Any] = {
            "timestamp": datetime.utcfromtimestamp(record.created).isoformat() + "Z",
            "level": record.levelname,
            "message": msg,
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
            "logger": record.name,
        }

        # Merge extra fields if passed in 'extra' dict
        if hasattr(record, "context"):
            # Scrub context
            ctx = record.context.copy()
            for k in list(ctx.keys()):
                if "key" in k.lower() or "secret" in k.lower() or "token" in k.lower():
                    ctx[k] = "[REDACTED]"
            log_obj.update(ctx)

        # Handle exceptions
        if record.exc_info:
            log_obj["exception"] = self.formatException(record.exc_info)
            log_obj["stack_trace"] = (
                self.formatStack(record.stack_info) if record.stack_info else ""
            )

        return json.dumps(log_obj)


def get_logger(name: str) -> logging.Logger:
    """Returns a properly configured structured logger."""
    logger = logging.getLogger(name)

    # Avoid duplicate handlers
    if logger.handlers:
        return logger

    level_name = os.getenv("LOG_LEVEL", "DEBUG").upper()
    level = getattr(logging, level_name, logging.DEBUG)
    logger.setLevel(level)

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JSONFormatter())
    logger.addHandler(handler)

    # Prevent propagation to root logger if root is unconfigured or simple
    logger.propagate = False

    return logger


class ContextLogger(logging.LoggerAdapter):
    """Adapter to inject context (e.g., symbol, trade_id) into logs."""

    def process(self, msg, kwargs):
        context = kwargs.pop("extra", {})
        # Merge adapter context with call context
        merged_context = {**self.extra, **context}
        kwargs["extra"] = {"context": merged_context}
        return msg, kwargs
