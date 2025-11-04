"""Asynchronous circuit breaker implementation tailored for asyncio workloads."""

from __future__ import annotations

import asyncio
import time
from typing import Any, Callable, Iterable, Optional


class CircuitBreakerError(RuntimeError):
    """Raised when the circuit breaker prevents execution due to an open circuit."""


class AsyncCircuitBreaker:
    """Minimal asyncio-friendly circuit breaker.

    The implementation mirrors the essential behaviour of traditional circuit breakers:

    * Closed: calls proceed normally while failures are tracked.
    * Open: calls fail-fast for ``reset_timeout`` seconds.
    * Half-open: a limited number of trial calls are allowed; a failure re-opens the circuit,
      while a configurable number of successes closes it again.
    """

    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"

    def __init__(
        self,
        *,
        fail_max: int = 5,
        reset_timeout: float = 60.0,
        success_threshold: int = 1,
        exclude: Optional[Iterable[type[BaseException] | Callable[[BaseException], bool]]] = None,
        name: str | None = None,
        clock: Callable[[], float] | None = None,
    ) -> None:
        if fail_max <= 0:
            raise ValueError("fail_max must be positive")
        if reset_timeout < 0:
            raise ValueError("reset_timeout must be non-negative")
        if success_threshold <= 0:
            raise ValueError("success_threshold must be positive")

        self.fail_max = fail_max
        self.reset_timeout = reset_timeout
        self.success_threshold = success_threshold
        self._exclude = tuple(exclude or ())
        self._name = name or "AsyncCircuitBreaker"
        self._clock = clock or time.monotonic

        self._state = self.CLOSED
        self._fail_counter = 0
        self._success_counter = 0
        self._opened_at: float | None = None
        self._lock = asyncio.Lock()

    # ------------------------------------------------------------------
    # Public properties
    # ------------------------------------------------------------------
    @property
    def name(self) -> str:
        return self._name

    @property
    def current_state(self) -> str:
        return self._state

    @property
    def fail_counter(self) -> int:
        return self._fail_counter

    @property
    def success_counter(self) -> int:
        return self._success_counter

    # ------------------------------------------------------------------
    # Core API
    # ------------------------------------------------------------------
    async def call(self, func: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
        """Execute ``func`` under circuit breaker protection."""

        await self._before_call()

        try:
            result = await func(*args, **kwargs)
        except Exception as exc:  # noqa: BLE001 - propagate original exceptions
            raise await self._handle_failure(exc) from exc
        else:
            await self._handle_success()
            return result

    # Backwards compatibility shim for previous pybreaker usage.
    async def call_async(self, func: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
        return await self.call(func, *args, **kwargs)

    async def reset(self) -> None:
        """Force the circuit breaker back to the closed state."""

        async with self._lock:
            self._transition_to_closed()

    async def force_open(self) -> None:
        """Force the circuit breaker into the open state."""

        async with self._lock:
            self._transition_to_open()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    async def _before_call(self) -> None:
        async with self._lock:
            if self._state == self.OPEN:
                if self._opened_at is None or (self._clock() - self._opened_at) < self.reset_timeout:
                    raise CircuitBreakerError(f"{self._name} circuit breaker is open")

                # Cool-down elapsed; allow a trial call.
                self._state = self.HALF_OPEN
                self._success_counter = 0

    async def _handle_success(self) -> None:
        async with self._lock:
            if self._state == self.HALF_OPEN:
                self._success_counter += 1
                if self._success_counter >= self.success_threshold:
                    self._transition_to_closed()
            else:
                # Reset failure tracking in closed state.
                self._fail_counter = 0

    async def _handle_failure(self, exc: BaseException) -> BaseException:
        if self._should_ignore(exc):
            await self._handle_success()
            return exc

        async with self._lock:
            if self._state == self.HALF_OPEN:
                self._transition_to_open()
                return CircuitBreakerError(f"{self._name} circuit breaker re-opened after trial failure")

            self._fail_counter += 1
            if self._fail_counter >= self.fail_max:
                self._transition_to_open()
                return CircuitBreakerError(f"{self._name} circuit breaker opened after {self.fail_max} failures")

        return exc

    def _should_ignore(self, exc: BaseException) -> bool:
        for exclusion in self._exclude:
            if isinstance(exclusion, type):
                if isinstance(exc, exclusion):
                    return True
            elif callable(exclusion):
                try:
                    if exclusion(exc):
                        return True
                except Exception:  # pragma: no cover - defensive guard against buggy predicates
                    continue
        return False

    def _transition_to_open(self) -> None:
        self._state = self.OPEN
        self._opened_at = self._clock()
        self._fail_counter = 0
        self._success_counter = 0

    def _transition_to_closed(self) -> None:
        self._state = self.CLOSED
        self._opened_at = None
        self._fail_counter = 0
        self._success_counter = 0


__all__ = ["AsyncCircuitBreaker", "CircuitBreakerError"]


