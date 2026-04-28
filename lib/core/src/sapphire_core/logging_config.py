"""
Sapphire OS - Unified Logging Configuration

Structured logging for all services with GCP Cloud Logging + Firestore integration.
"""

import json
import logging
import os
import sys
from datetime import datetime
from enum import Enum
from typing import Any

# Optional Firestore import - only available when running with GCP credentials
try:
    from google.cloud import firestore

    FIRESTORE_AVAILABLE = True
except ImportError:
    FIRESTORE_AVAILABLE = False

FIRESTORE_ENABLED = os.environ.get("FIRESTORE_LOGGING", "true").lower() == "true"
FIRESTORE_COLLECTION = "system_logs"


class LogLevel(Enum):
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


class FirestoreLogHandler:
    """Async Firestore logging handler"""

    def __init__(self):
        self.db = None
        self.enabled = FIRESTORE_AVAILABLE and FIRESTORE_ENABLED

        if self.enabled:
            try:
                project = os.environ.get("GCP_PROJECT", "sapphire-479610")
                self.db = firestore.Client(project=project)
            except Exception as e:
                print(f"Firestore logging disabled: {e}")
                self.enabled = False

    def write_log(self, entry: dict[str, Any]):
        """Write log entry to Firestore (fire-and-forget)"""
        if not self.enabled or not self.db:
            return

        try:
            # Add to collection
            self.db.collection(FIRESTORE_COLLECTION).add(entry)
        except Exception:
            # Silent fail - don't disrupt main flow
            pass


class SapphireLogger:
    """Unified logger for all Sapphire OS components"""

    _firestore_handler = None

    def __init__(self, service_name: str, component: str = None):
        self.service_name = service_name
        self.component = component or service_name
        self.logger = logging.getLogger(f"sapphire.{service_name}")
        self.logger.setLevel(logging.DEBUG)

        # Console handler
        if not self.logger.handlers:
            handler = logging.StreamHandler(sys.stdout)
            formatter = logging.Formatter("%(asctime)s | %(name)s | %(levelname)s | %(message)s")
            handler.setFormatter(formatter)
            self.logger.addHandler(handler)

        # Firestore handler (shared across instances)
        if SapphireLogger._firestore_handler is None:
            SapphireLogger._firestore_handler = FirestoreLogHandler()
        self.firestore = SapphireLogger._firestore_handler

    def _format_log(self, level: LogLevel, message: str, **kwargs) -> dict[str, Any]:
        """Format structured log entry"""
        entry = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "service": self.service_name,
            "component": self.component,
            "level": level.value,
            "message": message,
            "severity": level.value,
        }

        # Add any additional context
        entry.update(kwargs)

        return entry

    def debug(self, message: str, **kwargs):
        """Debug level log"""
        entry = self._format_log(LogLevel.DEBUG, message, **kwargs)
        self.logger.debug(json.dumps(entry))
        if self.firestore.enabled:
            self.firestore.write_log(entry)

    def info(self, message: str, **kwargs):
        """Info level log"""
        entry = self._format_log(LogLevel.INFO, message, **kwargs)
        self.logger.info(json.dumps(entry))
        if self.firestore.enabled:
            self.firestore.write_log(entry)

    def warning(self, message: str, **kwargs):
        """Warning level log"""
        entry = self._format_log(LogLevel.WARNING, message, **kwargs)
        self.logger.warning(json.dumps(entry))
        if self.firestore.enabled:
            self.firestore.write_log(entry)

    def error(self, message: str, **kwargs):
        """Error level log"""
        entry = self._format_log(LogLevel.ERROR, message, **kwargs)
        self.logger.error(json.dumps(entry))
        if self.firestore.enabled:
            self.firestore.write_log(entry)

    def critical(self, message: str, **kwargs):
        """Critical level log"""
        entry = self._format_log(LogLevel.CRITICAL, message, **kwargs)
        self.logger.critical(json.dumps(entry))
        if self.firestore.enabled:
            self.firestore.write_log(entry)


# Trading-specific logger
class TradingLogger(SapphireLogger):
    """Logger for trading signals and execution"""

    def __init__(self):
        super().__init__("trading", "signal_processor")

    def log_signal_received(
        self, signal_id: str, symbol: str, action: str, source: str = "tradingview", **kwargs
    ):
        """Log when a signal is received"""
        self.info(
            f"Signal received: {symbol} {action}",
            event_type="signal_received",
            signal_id=signal_id,
            symbol=symbol,
            action=action,
            source=source,
            **kwargs,
        )

    def log_signal_validated(self, signal_id: str, symbol: str, validation_result: dict, **kwargs):
        """Log signal validation result"""
        self.info(
            f"Signal validated: {symbol}",
            event_type="signal_validated",
            signal_id=signal_id,
            symbol=symbol,
            validation=validation_result,
            **kwargs,
        )

    def log_signal_published(
        self, signal_id: str, symbol: str, channel: str, message_id: str, **kwargs
    ):
        """Log when signal is published to Pub/Sub"""
        self.info(
            f"Signal published: {symbol} via {channel}",
            event_type="signal_published",
            signal_id=signal_id,
            symbol=symbol,
            channel=channel,
            message_id=message_id,
            **kwargs,
        )

    def log_signal_error(self, signal_id: str, error: str, stage: str, **kwargs):
        """Log signal processing error"""
        self.error(
            f"Signal error at {stage}: {error}",
            event_type="signal_error",
            signal_id=signal_id,
            error=error,
            stage=stage,
            **kwargs,
        )

    def log_trade_executed(
        self,
        trade_id: str,
        signal_id: str,
        symbol: str,
        side: str,
        size: float,
        price: float,
        pnl: float = None,
        **kwargs,
    ):
        """Log executed trade"""
        self.info(
            f"Trade executed: {symbol} {side} @ {price}",
            event_type="trade_executed",
            trade_id=trade_id,
            signal_id=signal_id,
            symbol=symbol,
            side=side,
            size=size,
            price=price,
            pnl=pnl,
            **kwargs,
        )


# Webhook-specific logger
class WebhookLogger(SapphireLogger):
    """Logger for webhook receiver"""

    def __init__(self):
        super().__init__("webhook", "tradingview_receiver")

    def log_request_received(self, request_id: str, client_ip: str, symbol: str = None, **kwargs):
        """Log incoming webhook request"""
        self.info(
            f"Webhook request received from {client_ip}",
            event_type="webhook_request",
            request_id=request_id,
            client_ip=client_ip,
            symbol=symbol,
            **kwargs,
        )

    def log_request_validated(self, request_id: str, validation_result: bool, **kwargs):
        """Log request validation"""
        self.info(
            f"Webhook validation: {validation_result}",
            event_type="webhook_validation",
            request_id=request_id,
            validation_result=validation_result,
            **kwargs,
        )

    def log_ollama_enrichment(
        self, request_id: str, symbol: str, verdict: str, latency_ms: float, **kwargs
    ):
        """Log AI enrichment via Ollama"""
        self.info(
            f"Ollama enrichment: {symbol} verdict={verdict}",
            event_type="ollama_enrichment",
            request_id=request_id,
            symbol=symbol,
            verdict=verdict,
            latency_ms=latency_ms,
            **kwargs,
        )

    def log_response_sent(self, request_id: str, status_code: int, signal_id: str = None, **kwargs):
        """Log response sent back to TradingView"""
        self.info(
            f"Webhook response: {status_code}",
            event_type="webhook_response",
            request_id=request_id,
            status_code=status_code,
            signal_id=signal_id,
            **kwargs,
        )


# Self-improvement logger
class SelfImprovementLogger(SapphireLogger):
    """Logger for self-improvement loop"""

    def __init__(self):
        super().__init__("self_improvement", "review_engine")

    def log_review_started(self, review_id: str, week_ending: str, **kwargs):
        """Log start of weekly review"""
        self.info(
            f"Weekly review started: {review_id}",
            event_type="review_started",
            review_id=review_id,
            week_ending=week_ending,
            **kwargs,
        )

    def log_metrics_analyzed(self, review_id: str, metrics: dict, **kwargs):
        """Log metrics analysis"""
        self.info(
            f"Metrics analyzed for {review_id}",
            event_type="metrics_analyzed",
            review_id=review_id,
            metrics=metrics,
            **kwargs,
        )

    def log_task_created(
        self, review_id: str, task_id: str, priority: str, assignee: str, **kwargs
    ):
        """Log improvement task creation"""
        self.info(
            f"Task created: {task_id} ({priority}) -> {assignee}",
            event_type="task_created",
            review_id=review_id,
            task_id=task_id,
            priority=priority,
            assignee=assignee,
            **kwargs,
        )

    def log_review_completed(self, review_id: str, tasks_created: int, **kwargs):
        """Log review completion"""
        self.info(
            f"Review completed: {review_id} ({tasks_created} tasks)",
            event_type="review_completed",
            review_id=review_id,
            tasks_created=tasks_created,
            **kwargs,
        )


# Convenience functions
def get_logger(service_name: str, component: str = None) -> SapphireLogger:
    """Get a logger instance"""
    return SapphireLogger(service_name, component)


def get_trading_logger() -> TradingLogger:
    """Get trading logger"""
    return TradingLogger()


def get_webhook_logger() -> WebhookLogger:
    """Get webhook logger"""
    return WebhookLogger()


def get_self_improvement_logger() -> SelfImprovementLogger:
    """Get self-improvement logger"""
    return SelfImprovementLogger()
