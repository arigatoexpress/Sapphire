"""Reusable fault-injection primitives.

These primitives compose into chaos scenarios but are independently useful for
any test that wants to inject controlled, deterministic failures. None of them
touch real I/O — clocks, sockets, and disks are all simulated via mocks.

Primitive overview
------------------
- ``ClockSkew`` — a frozen-or-skewed clock callable with explicit advance().
- ``NetworkPartition`` — a boolean toggle that, when ``partitioned``, raises
  the configured exception class for any callable wrapped in ``protect()``.
- ``SlowDisk`` — wraps ``open()``-style write calls and inflates their latency
  via an injected sleep callable (so tests can use a fake clock).
- ``IntermittentErrorPolicy`` — pattern-driven raise/return decisions per call
  index (e.g. "fail every 3rd call", "succeed for 5 then fail forever").
- ``FaultInjector`` — composition root that carries a registry of primitives
  and exposes a single ``trip(name)`` accessor for tests.

All primitives are pure Python and deterministic. They never spawn threads,
never touch sockets, and never sleep on the real wall clock.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

# ---------------------------------------------------------------------------
# ClockSkew
# ---------------------------------------------------------------------------


@dataclass
class ClockSkew:
    """A controllable monotonic clock for tests.

    Tests construct one, call ``now()`` instead of ``datetime.now(UTC)``, and
    drive time forward with ``advance(seconds)``.

    The clock never moves on its own; this is by design — chaos tests must be
    deterministic and reproducible.
    """

    start: datetime = field(default_factory=lambda: datetime(2026, 4, 29, 12, 0, 0, tzinfo=UTC))
    skew_seconds: float = 0.0

    def now(self) -> datetime:
        """Return the current simulated clock value."""
        return self.start + timedelta(seconds=self.skew_seconds)

    def advance(self, seconds: float) -> datetime:
        """Move the simulated clock forward by ``seconds``. Returns the new time."""
        if seconds < 0:
            raise ValueError(f"ClockSkew.advance only moves forward; got {seconds!r}")
        self.skew_seconds += seconds
        return self.now()

    def reset(self) -> None:
        """Snap the clock back to ``start``."""
        self.skew_seconds = 0.0

    def isoformat(self) -> str:
        """Convenience: ISO-8601 of the current simulated time."""
        return self.now().isoformat()


# ---------------------------------------------------------------------------
# NetworkPartition
# ---------------------------------------------------------------------------


class NetworkPartitionError(ConnectionError):
    """Raised by NetworkPartition.protect() when the partition is active."""


@dataclass
class NetworkPartition:
    """A boolean toggle that simulates a partition between two endpoints.

    Wrap any callable in ``protect()``. When ``partitioned=True`` the wrapped
    call raises the configured exception class; when ``False`` it passes
    through. Tests use this to simulate Redis becoming unreachable mid-stream.
    """

    name: str = "default"
    partitioned: bool = False
    exception_factory: Callable[[str], BaseException] = field(
        default=lambda msg: NetworkPartitionError(msg)
    )

    def trip(self) -> None:
        """Activate the partition."""
        self.partitioned = True

    def heal(self) -> None:
        """Restore connectivity."""
        self.partitioned = False

    def protect(self, fn: Callable[..., Any]) -> Callable[..., Any]:
        """Return a wrapper around ``fn`` that respects the partition state."""

        def wrapper(*args: Any, **kwargs: Any) -> Any:
            if self.partitioned:
                raise self.exception_factory(
                    f"network partition '{self.name}' is active",
                )
            return fn(*args, **kwargs)

        return wrapper


# ---------------------------------------------------------------------------
# SlowDisk
# ---------------------------------------------------------------------------


@dataclass
class SlowDisk:
    """Inflates the latency of a wrapped IO callable.

    The injected sleep is a callable that takes seconds; tests pass a fake
    sleep that mutates a ``ClockSkew`` instead of calling ``time.sleep``.

    ``write_latency_ms`` is the per-call delay added by the slow disk.
    Setting ``error_after_n_writes`` causes the disk to raise ``OSError`` once
    the threshold is crossed (simulates "disk fills up").
    """

    write_latency_ms: int = 0
    error_after_n_writes: int | None = None
    sleep_fn: Callable[[float], None] = field(default=lambda _s: None)
    _writes: int = 0

    def wrap_write(self, fn: Callable[..., Any]) -> Callable[..., Any]:
        """Wrap a write-style callable and inject latency / overflow."""

        def wrapper(*args: Any, **kwargs: Any) -> Any:
            self._writes += 1
            if self.error_after_n_writes is not None and self._writes > self.error_after_n_writes:
                raise OSError(f"simulated disk full after {self.error_after_n_writes} writes")
            if self.write_latency_ms:
                self.sleep_fn(self.write_latency_ms / 1000.0)
            return fn(*args, **kwargs)

        return wrapper

    @property
    def writes(self) -> int:
        return self._writes

    def reset(self) -> None:
        self._writes = 0


# ---------------------------------------------------------------------------
# IntermittentErrorPolicy
# ---------------------------------------------------------------------------


@dataclass
class IntermittentErrorPolicy:
    """Decides whether the Nth call should fail.

    Modes:
    - ``every_n``: fail every Nth call (1-indexed).
    - ``after_n``: succeed for the first N calls, fail thereafter.
    - ``flaky_window``: fail calls whose 1-indexed number lies in any of
      ``windows`` (a list of ``(low, high)`` inclusive intervals).
    """

    mode: str = "every_n"
    every_n: int = 0  # 0 disables
    after_n: int | None = None
    windows: tuple[tuple[int, int], ...] = ()
    exception_factory: Callable[[int], BaseException] = field(
        default=lambda i: ConnectionError(f"intermittent failure on call #{i}")
    )
    _calls: int = 0

    def should_fail(self, call_index: int | None = None) -> bool:
        """Return True iff the call at ``call_index`` should raise.

        If ``call_index`` is None, increments and uses an internal counter.
        """
        idx = call_index if call_index is not None else self._calls + 1
        if call_index is None:
            self._calls += 1
        if self.mode == "every_n":
            return self.every_n > 0 and idx % self.every_n == 0
        if self.mode == "after_n":
            return self.after_n is not None and idx > self.after_n
        if self.mode == "flaky_window":
            return any(low <= idx <= high for low, high in self.windows)
        raise ValueError(f"unknown IntermittentErrorPolicy mode: {self.mode!r}")

    def maybe_raise(self) -> None:
        """Raise per the policy, advancing the internal counter."""
        self._calls += 1
        if self._calls and self._mode_check(self._calls):
            raise self.exception_factory(self._calls)

    def _mode_check(self, idx: int) -> bool:
        if self.mode == "every_n":
            return self.every_n > 0 and idx % self.every_n == 0
        if self.mode == "after_n":
            return self.after_n is not None and idx > self.after_n
        if self.mode == "flaky_window":
            return any(low <= idx <= high for low, high in self.windows)
        raise ValueError(f"unknown IntermittentErrorPolicy mode: {self.mode!r}")

    def reset(self) -> None:
        self._calls = 0


# ---------------------------------------------------------------------------
# FaultInjector
# ---------------------------------------------------------------------------


@dataclass
class FaultInjector:
    """Composition root for chaos primitives.

    Tests construct a single FaultInjector, register the primitives they care
    about, and pass it to scenario drivers. Centralizing the registry makes it
    easy to dump the chaos transcript at the end of a test run.
    """

    name: str = "default"
    primitives: dict[str, Any] = field(default_factory=dict)
    transcript: list[tuple[str, str, dict[str, Any]]] = field(default_factory=list)

    def register(self, name: str, primitive: Any) -> Any:
        if name in self.primitives:
            raise ValueError(f"primitive {name!r} already registered")
        self.primitives[name] = primitive
        self.transcript.append(("register", name, {"type": type(primitive).__name__}))
        return primitive

    def trip(self, name: str) -> None:
        prim = self.primitives.get(name)
        if prim is None:
            raise KeyError(f"unknown primitive {name!r}")
        if hasattr(prim, "trip"):
            prim.trip()
            self.transcript.append(("trip", name, {}))
        else:
            raise TypeError(f"{name!r} of type {type(prim).__name__} cannot trip")

    def heal(self, name: str) -> None:
        prim = self.primitives.get(name)
        if prim is None:
            raise KeyError(f"unknown primitive {name!r}")
        if hasattr(prim, "heal"):
            prim.heal()
            self.transcript.append(("heal", name, {}))
        else:
            raise TypeError(f"{name!r} of type {type(prim).__name__} cannot heal")

    def reset_all(self) -> None:
        for prim in list(self.primitives.values()):
            if hasattr(prim, "reset"):
                prim.reset()
        self.transcript.append(("reset_all", self.name, {}))

    def names(self) -> Iterable[str]:
        return self.primitives.keys()


__all__ = [
    "ClockSkew",
    "FaultInjector",
    "IntermittentErrorPolicy",
    "NetworkPartition",
    "NetworkPartitionError",
    "SlowDisk",
]
