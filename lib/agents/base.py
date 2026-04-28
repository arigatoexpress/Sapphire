"""Cycle-oriented base classes for Sapphire autonomous agents."""

from __future__ import annotations

import logging
import signal
import threading
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Protocol

log = logging.getLogger(__name__)


class EventPublisher(Protocol):
    """Protocol for event bus implementations used by agents."""

    def publish(
        self,
        event_type: str,
        data: dict[str, Any],
        source: str | None = None,
    ) -> str:
        """Publish an event and return its identifier."""


@dataclass(frozen=True, slots=True)
class Action:
    """Represents a single unit of work planned by an agent."""

    kind: str
    payload: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class Result:
    """Represents the outcome of executing a planned action."""

    action: Action
    status: str
    payload: dict[str, Any] = field(default_factory=dict)


class BaseAgent:
    """Base class for simple plan/act/observe autonomous agents."""

    def __init__(
        self,
        name: str,
        interval_sec: int,
        event_bus: EventPublisher | None = None,
    ) -> None:
        """Initialize the agent.

        Args:
            name: Stable agent identifier.
            interval_sec: Target delay between cycle starts.
            event_bus: Optional event bus used for lifecycle emission.
        """
        self.name = name
        self.interval_sec = max(0, int(interval_sec))
        self.event_bus = event_bus
        self.cycle_count = 0
        self.last_cycle_started_at: datetime | None = None
        self.last_cycle_completed_at: datetime | None = None
        self.last_observation: dict[str, Any] = {}
        self._stop_event = threading.Event()

    def plan(self) -> list[Action]:
        """Return the actions to execute in the current cycle."""
        raise NotImplementedError

    def act(self, actions: list[Action]) -> list[Result]:
        """Execute planned actions and return their results."""
        raise NotImplementedError

    def observe(self, results: list[Result]) -> dict[str, Any]:
        """Summarize the cycle results for the next planning step."""
        raise NotImplementedError

    def emit_event(self, event_type: str, data: dict[str, Any]) -> str | None:
        """Publish an event if an event bus is available."""
        if self.event_bus is None:
            return None
        try:
            return self.event_bus.publish(event_type, data, source=f"agent:{self.name}")
        except TypeError:
            return self.event_bus.publish(event_type, data)

    def stop(self) -> None:
        """Request that the long-running loop stop after the current wait."""
        self._stop_event.set()

    def run_once(self) -> dict[str, Any]:
        """Run one complete plan/act/observe cycle."""
        self.last_cycle_started_at = datetime.now(UTC)
        actions = self.plan()
        results = self.act(actions)
        observation = dict(self.observe(results))

        self.cycle_count += 1
        self.last_cycle_completed_at = datetime.now(UTC)
        self.last_observation = observation

        self.emit_event(
            "agent.cycle.completed",
            {
                "agent": self.name,
                "cycle_count": self.cycle_count,
                "started_at": self.last_cycle_started_at.isoformat(),
                "completed_at": self.last_cycle_completed_at.isoformat(),
                "observation": observation,
            },
        )
        return observation

    def run_forever(self) -> None:
        """Run until `stop()` or SIGTERM/SIGINT is received."""
        previous_handlers: dict[int, Any] = {}
        if threading.current_thread() is threading.main_thread():
            previous_handlers = self._install_signal_handlers()

        try:
            while not self._stop_event.is_set():
                cycle_started = time.monotonic()
                try:
                    self.run_once()
                except Exception:
                    log.exception(
                        "Agent %s failed during cycle %d", self.name, self.cycle_count + 1
                    )
                sleep_for = max(0.0, self.interval_sec - (time.monotonic() - cycle_started))
                if self._stop_event.wait(sleep_for):
                    break
        finally:
            self._restore_signal_handlers(previous_handlers)

    def _install_signal_handlers(self) -> dict[int, Any]:
        """Install SIGINT/SIGTERM handlers and return the previous handlers."""
        previous_handlers: dict[int, Any] = {}
        for signum in (signal.SIGINT, signal.SIGTERM):
            previous_handlers[signum] = signal.getsignal(signum)
            signal.signal(signum, self._handle_signal)
        return previous_handlers

    def _restore_signal_handlers(self, previous_handlers: dict[int, Any]) -> None:
        """Restore previously installed signal handlers."""
        for signum, handler in previous_handlers.items():
            signal.signal(signum, handler)

    def _handle_signal(self, signum: int, _frame: Any) -> None:
        """Request a graceful stop when the process receives a signal."""
        log.info("Agent %s received signal %s; stopping", self.name, signum)
        self.stop()


__all__ = ["Action", "BaseAgent", "Result"]
