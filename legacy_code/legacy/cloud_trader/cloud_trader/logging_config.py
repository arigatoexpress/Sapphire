"""Advanced Logging Configuration for Trading System

Provides structured logging, audit trails, performance monitoring,
and correlation IDs for distributed tracing across all services.
"""

import json
import logging
import sys
import threading
import time
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

import structlog
from pythonjsonlogger import jsonlogger


class TradingLogger:
    """Advanced logging system for trading operations."""

    def _add_service_info(self, logger, method_name, event_dict):
        """Add service metadata to all log entries."""
        event_dict.update(
            {
                "service": self.service_name,
                "version": "1.0.0",
                "environment": "production",
            }
        )
        return event_dict

    def _add_correlation_id(self, logger, method_name, event_dict):
        """Add correlation ID for request tracing."""
        correlation_id = getattr(self.correlation_id, "value", None)
        if correlation_id:
            event_dict["correlation_id"] = correlation_id
        return event_dict

    def _add_request_context(self, logger, method_name, event_dict):
        """Add request context information."""
        context = getattr(self.request_context, "value", {})
        if context:
            event_dict.update(context)
        return event_dict

    def __init__(self, service_name: str, log_level: str = "INFO"):
        self.service_name = service_name
        self.correlation_id = threading.local()
        self.request_context = threading.local()

        # Configure structlog
        structlog.configure(
            processors=[
                structlog.contextvars.merge_contextvars,
                structlog.processors.add_log_level,
                structlog.processors.TimeStamper(fmt="iso"),
                self._add_service_info,
                self._add_correlation_id,
                self._add_request_context,
                structlog.processors.JSONRenderer(),
            ],
            wrapper_class=structlog.make_filtering_bound_logger(self._get_log_level(log_level)),
            context_class=dict,
            logger_factory=structlog.WriteLoggerFactory(),
            cache_logger_on_first_use=True,
        )

        # Configure standard logging
        self._configure_standard_logging(log_level)

        # Create logger
        self.logger = structlog.get_logger()

    def _get_log_level(self, level_str: str) -> int:
        levels = {
            "DEBUG": logging.DEBUG,
            "INFO": logging.INFO,
            "WARNING": logging.WARNING,
            "ERROR": logging.ERROR,
            "CRITICAL": logging.CRITICAL,
        }
        return levels.get(level_str.upper(), logging.INFO)

    def _configure_standard_logging(self, log_level: str):
        """Configure standard Python logging with JSON formatter."""
        # Create logs directory - use /tmp for container environments to avoid permission issues
        if Path("/app").exists():
            log_dir = Path("/tmp/app-logs")
        else:
            log_dir = Path("./logs")
        try:
            log_dir.mkdir(exist_ok=True, parents=True)
        except PermissionError:
            log_dir = Path("/tmp/app-logs")
            log_dir.mkdir(exist_ok=True, parents=True)

        # JSON formatter for structured logs
        json_formatter = jsonlogger.JsonFormatter(
            "%(asctime)s %(name)s %(levelname)s %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
        )

        # Console handler
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(json_formatter)

        # File handler for service logs
        file_handler = logging.FileHandler(log_dir / f"{self.service_name}.log", encoding="utf-8")
        file_handler.setFormatter(json_formatter)

        # Error file handler
        error_handler = logging.FileHandler(
            log_dir / f"{self.service_name}_error.log", encoding="utf-8"
        )
        error_handler.setLevel(logging.ERROR)
        error_handler.setFormatter(json_formatter)

        # Configure root logger
        root_logger = logging.getLogger()
        root_logger.setLevel(self._get_log_level(log_level))
        root_logger.addHandler(console_handler)
        root_logger.addHandler(file_handler)
        root_logger.addHandler(file_handler)
        root_logger.addHandler(error_handler)

        # Add WebSocket Handler
        ws_handler = WebSocketLogHandler()
        ws_handler.setFormatter(json_formatter)
        root_logger.addHandler(ws_handler)

    def set_correlation_id(self, correlation_id: str):
        """Set correlation ID for current thread."""
        self.correlation_id.value = correlation_id

    def set_request_context(self, **context):
        """Set request context for current thread."""
        self.request_context.value = context

    def clear_context(self):
        """Clear correlation ID and request context."""
        self.correlation_id.value = None
        self.request_context.value = None

    # Trading-specific logging methods
    def log_trade_signal(self, signal_data: Dict[str, Any]):
        """Log trading signal generation."""
        self.logger.info(
            "trade_signal_generated",
            signal=signal_data,
            agent=signal_data.get("source"),
            symbol=signal_data.get("symbol"),
            side=signal_data.get("side"),
            confidence=signal_data.get("confidence"),
            notional=signal_data.get("notional"),
            reasoning=signal_data.get("rationale"),
            timestamp=signal_data.get("timestamp"),
        )

    def log_trade_execution(self, execution_data: Dict[str, Any]):
        """Log trade execution."""
        self.logger.info(
            "trade_executed",
            execution=execution_data,
            order_id=execution_data.get("order_id"),
            symbol=execution_data.get("symbol"),
            side=execution_data.get("side"),
            quantity=execution_data.get("quantity"),
            price=execution_data.get("price"),
            slippage=execution_data.get("slippage"),
            fees=execution_data.get("fees"),
            timestamp=execution_data.get("timestamp"),
        )

    def log_portfolio_update(self, portfolio_data: Dict[str, Any]):
        """Log portfolio value changes."""
        self.logger.info(
            "portfolio_updated",
            portfolio=portfolio_data,
            total_value=portfolio_data.get("portfolio_value"),
            daily_pnl=portfolio_data.get("daily_pnl"),
            assets=portfolio_data.get("agent_allocations", {}),
            risk_limit=portfolio_data.get("risk_limit"),
            timestamp=portfolio_data.get("timestamp"),
        )

    def log_agent_decision(self, agent: str, decision_data: Dict[str, Any]):
        """Log AI agent decision making."""
        self.logger.info(
            "agent_decision",
            agent=agent,
            decision=decision_data,
            strategy=decision_data.get("strategy"),
            confidence=decision_data.get("confidence"),
            market_data=decision_data.get("market_context", {}),
            reasoning=decision_data.get("reasoning"),
            timestamp=decision_data.get("timestamp"),
        )

    def log_performance_metric(
        self, metric_name: str, value: float, metadata: Dict[str, Any] = None
    ):
        """Log performance metrics."""
        self.logger.info(
            "performance_metric",
            metric=metric_name,
            value=value,
            metadata=metadata or {},
            timestamp=datetime.now().isoformat(),
        )

    def log_error(self, error: Exception, context: Dict[str, Any] = None):
        """Log errors with context."""
        self.logger.error(
            "error_occurred",
            error=str(error),
            error_type=type(error).__name__,
            context=context or {},
            traceback=error.__traceback__,
        )

    def log_audit_event(
        self, event_type: str, user: str, action: str, resource: str, details: Dict[str, Any] = None
    ):
        """Log audit events for compliance."""
        self.logger.info(
            "audit_event",
            event_type=event_type,
            user=user,
            action=action,
            resource=resource,
            details=details or {},
            timestamp=datetime.now().isoformat(),
            ip_address=getattr(self.request_context, "value", {}).get("ip", "unknown"),
        )


@contextmanager
def correlation_context(correlation_id: str):
    """Context manager for setting correlation ID."""
    logger = get_trading_logger()
    old_id = getattr(logger.correlation_id, "value", None)
    logger.set_correlation_id(correlation_id)
    try:
        yield
    finally:
        logger.correlation_id.value = old_id


class WebSocketLogHandler(logging.Handler):
    """Log handler that streams logs to WebSocket."""

    def emit(self, record):
        try:
            # Avoid infinite loops / recursions
            if getattr(record, "ws_broadcast", False):
                return

            # Formatting
            msg = self.format(record)

            # Construct log entry object
            log_entry = {
                "id": str(record.created),
                "timestamp": datetime.fromtimestamp(record.created).isoformat(),
                "level": record.levelname,
                "module": record.name,
                "message": msg,
                "metadata": getattr(record, "metadata", {}),
            }

            # Helper to broadcast (import inside to avoid circular deps)
            import asyncio

            try:
                from .websocket_manager import broadcast_log

                # Check for running loop
                try:
                    loop = asyncio.get_running_loop()
                except RuntimeError:
                    return  # No loop running

                if loop.is_running():
                    loop.create_task(broadcast_log(log_entry))
            except ImportError:
                pass

        except Exception:
            self.handleError(record)


@contextmanager
def request_context(**context):
    """Context manager for setting request context."""
    logger = get_trading_logger()
    old_context = getattr(logger.request_context, "value", {})
    logger.set_request_context(**context)
    try:
        yield
    finally:
        logger.request_context.value = old_context


# Global logger instance
_trading_logger = None


def get_trading_logger(service_name: str = "trading-system") -> TradingLogger:
    """Get or create global trading logger instance."""
    global _trading_logger
    if _trading_logger is None:
        log_level = "INFO"  # Could be from environment variable
        _trading_logger = TradingLogger(service_name, log_level)
    return _trading_logger


def setup_correlation_middleware():
    """Setup correlation ID middleware for web frameworks."""
    import uuid

    def generate_correlation_id():
        return str(uuid.uuid4())

    return generate_correlation_id


# Performance monitoring decorator
def log_performance(operation_name: str):
    """Decorator to log performance of operations."""

    def decorator(func):
        def wrapper(*args, **kwargs):
            logger = get_trading_logger()
            start_time = time.time()

            try:
                result = func(*args, **kwargs)
                duration = time.time() - start_time

                logger.log_performance_metric(
                    f"{operation_name}_duration", duration, {"success": True}
                )

                return result

            except Exception as e:
                duration = time.time() - start_time

                logger.log_performance_metric(
                    f"{operation_name}_duration", duration, {"success": False, "error": str(e)}
                )

                logger.log_error(e, {"operation": operation_name})
                raise

        return wrapper

    return decorator
