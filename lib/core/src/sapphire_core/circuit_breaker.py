"""
Lightweight circuit breaker for venue API calls.

States:
  CLOSED    → Normal operation
  OPEN      → Halted after fail_max consecutive failures; stays open for reset_timeout seconds
  HALF_OPEN → One probe call allowed; success → CLOSED, failure → OPEN again
"""

import logging
import time
from collections.abc import Callable

logger = logging.getLogger(__name__)


class CircuitBreakerOpen(Exception):
    """Raised when a circuit breaker is in OPEN state."""


class CircuitBreaker:
    """
    Rolling-window circuit breaker with Telegram-alert callbacks.

    Usage::

        cb = CircuitBreaker("lighter", fail_max=5, reset_timeout=120, on_open=telegram_alert)
        try:
            cb.check()                  # raises CircuitBreakerOpen if open
            result = await place_order(...)
            cb.record_success()
        except CircuitBreakerOpen:
            raise                       # propagate — signal handling will log it
        except Exception as e:
            cb.record_failure(e)
            raise
    """

    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"

    def __init__(
        self,
        name: str,
        *,
        fail_max: int = 5,
        reset_timeout: float = 120.0,
        on_open: Callable[[str], None] | None = None,
        on_close: Callable[[str], None] | None = None,
    ) -> None:
        self.name = name
        self.fail_max = fail_max
        self.reset_timeout = reset_timeout
        self._on_open = on_open
        self._on_close = on_close
        self._state = self.CLOSED
        self._failure_count = 0
        self._last_failure_time: float = 0.0

    # ── State machine ──────────────────────────────────────────────────

    @property
    def state(self) -> str:
        if self._state == self.OPEN:
            elapsed = time.monotonic() - self._last_failure_time
            if elapsed >= self.reset_timeout:
                self._state = self.HALF_OPEN
                logger.info(
                    "⚡ CircuitBreaker[%s] → HALF_OPEN after %.0fs (testing recovery)",
                    self.name,
                    elapsed,
                )
        return self._state

    @property
    def is_open(self) -> bool:
        return self.state == self.OPEN

    # ── Record outcomes ────────────────────────────────────────────────

    def record_success(self) -> None:
        was_recovering = self._state != self.CLOSED
        self._failure_count = 0
        self._state = self.CLOSED
        if was_recovering:
            logger.info("✅ CircuitBreaker[%s] → CLOSED (recovered)", self.name)
            self._notify(self._on_close)

    def record_failure(self, error: Exception | None = None) -> None:
        self._failure_count += 1
        self._last_failure_time = time.monotonic()
        logger.warning(
            "⚠️  CircuitBreaker[%s] failure %d/%d: %s",
            self.name,
            self._failure_count,
            self.fail_max,
            error,
        )
        if self._failure_count >= self.fail_max and self._state != self.OPEN:
            self._state = self.OPEN
            remaining = self.reset_timeout
            logger.error(
                "🔴 CircuitBreaker[%s] → OPEN after %d consecutive failures — "
                "venue API calls halted for %.0fs",
                self.name,
                self._failure_count,
                remaining,
            )
            self._notify(self._on_open)

    # ── Gate ──────────────────────────────────────────────────────────

    def check(self) -> None:
        """Raise CircuitBreakerOpen if the breaker is currently OPEN."""
        if self.is_open:
            remaining = max(
                0.0,
                self.reset_timeout - (time.monotonic() - self._last_failure_time),
            )
            raise CircuitBreakerOpen(
                f"CircuitBreaker[{self.name}] is OPEN — venue API halted. "
                f"Retry in {remaining:.0f}s."
            )

    # ── Introspection ─────────────────────────────────────────────────

    def status(self) -> dict:
        return {
            "name": self.name,
            "state": self.state,
            "failure_count": self._failure_count,
            "fail_max": self.fail_max,
            "reset_timeout_seconds": self.reset_timeout,
            "seconds_until_retry": max(
                0.0,
                self.reset_timeout - (time.monotonic() - self._last_failure_time),
            )
            if self._state == self.OPEN
            else 0.0,
        }

    def _notify(self, callback: Callable[[str], None] | None) -> None:
        if callback is None:
            return
        try:
            callback(self.name)
        except Exception as exc:
            logger.warning("CircuitBreaker[%s] callback error: %s", self.name, exc)

    def __repr__(self) -> str:
        return (
            f"CircuitBreaker(name={self.name!r}, state={self.state!r}, "
            f"failures={self._failure_count}/{self.fail_max})"
        )
