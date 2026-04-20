"""Portfolio-level circuit breaker — halts live trading on drawdown.

The kill switch is a *capital-protection* safety net, not an alpha signal.
Two guards run in parallel:

    - 24-hour rolling drawdown: >5% from the 24h peak halts trading.
    - Total drawdown: >15% from all-time peak halts trading.

Once tripped, every subsequent signal is forced to confidence=0 (see
``scale_confidence`` / ``should_halt``). The switch auto-deactivates only
after paper trading demonstrates a recovery — a ``recovery_threshold``
(default 2%) gain on a paper-trading PnL window — which keeps us honest
about whether the model has adapted to the new regime.

All activations/deactivations publish to the event bus
(``kill_switch.activated`` / ``kill_switch.deactivated``) and push a
Telegram P0 alert. Failures in notification never crash the switch.

Thread-safe; intended as a process singleton via :func:`get_kill_switch`.
"""

from __future__ import annotations

import logging
import threading
from collections import deque
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------


@dataclass
class KillSwitchEvent:
    """Snapshot of an activation or deactivation."""

    kind: str                 # "activated" | "deactivated"
    timestamp: datetime
    reason: str
    portfolio_value: float
    drawdown_24h: float
    drawdown_total: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "timestamp": self.timestamp.isoformat(),
            "reason": self.reason,
            "portfolio_value": round(self.portfolio_value, 2),
            "drawdown_24h": round(self.drawdown_24h, 4),
            "drawdown_total": round(self.drawdown_total, 4),
        }


@dataclass
class _PeakSample:
    ts: datetime
    value: float


# ---------------------------------------------------------------------------
# KillSwitch
# ---------------------------------------------------------------------------


@dataclass
class KillSwitchStatus:
    """Lightweight status struct for dashboards / APIs."""

    is_active: bool
    triggered_at: datetime | None
    reason: str | None
    peak_24h: float | None
    peak_all_time: float | None
    drawdown_24h: float
    drawdown_total: float
    last_value: float | None
    last_update: datetime | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "is_active": self.is_active,
            "triggered_at": self.triggered_at.isoformat() if self.triggered_at else None,
            "reason": self.reason,
            "peak_24h": round(self.peak_24h, 2) if self.peak_24h is not None else None,
            "peak_all_time": round(self.peak_all_time, 2) if self.peak_all_time is not None else None,
            "drawdown_24h": round(self.drawdown_24h, 4),
            "drawdown_total": round(self.drawdown_total, 4),
            "last_value": round(self.last_value, 2) if self.last_value is not None else None,
            "last_update": self.last_update.isoformat() if self.last_update else None,
        }


class KillSwitch:
    """Portfolio drawdown circuit breaker.

    Attributes
    ----------
    max_drawdown_24h
        Fractional drawdown threshold from the rolling 24h peak (default 0.05).
    max_drawdown_total
        Fractional drawdown threshold from the all-time peak (default 0.15).
    recovery_threshold
        Fractional paper-trading PnL required to auto-deactivate (default 0.02).
    """

    def __init__(
        self,
        max_drawdown_24h: float = 0.05,
        max_drawdown_total: float = 0.15,
        recovery_threshold: float = 0.02,
        *,
        publish_event: Any = None,
        notify: Any = None,
        now: Any = None,
    ) -> None:
        if max_drawdown_24h <= 0 or max_drawdown_24h >= 1:
            raise ValueError("max_drawdown_24h must be in (0, 1)")
        if max_drawdown_total <= 0 or max_drawdown_total >= 1:
            raise ValueError("max_drawdown_total must be in (0, 1)")
        if recovery_threshold <= 0 or recovery_threshold >= 1:
            raise ValueError("recovery_threshold must be in (0, 1)")

        self.max_drawdown_24h = max_drawdown_24h
        self.max_drawdown_total = max_drawdown_total
        self.recovery_threshold = recovery_threshold

        self._peak_all_time: float | None = None
        self._samples_24h: deque[_PeakSample] = deque()  # rolling window
        self._is_active: bool = False
        self._triggered_at: datetime | None = None
        self._activation_reason: str | None = None
        self._last_value: float | None = None
        self._last_update: datetime | None = None
        self._lock = threading.Lock()

        # Injected dependencies — default to the shared event bus / telegram.
        self._publish_event = publish_event
        self._notify = notify
        self._now = now or (lambda: datetime.now(UTC))

    # ------------------------------------------------------------------
    # Public state
    # ------------------------------------------------------------------

    @property
    def is_active(self) -> bool:
        return self._is_active

    @property
    def triggered_at(self) -> datetime | None:
        return self._triggered_at

    def status(self) -> KillSwitchStatus:
        with self._lock:
            peak_24h = self._peak_24h_unsafe()
            dd_24h, dd_total = self._drawdowns_unsafe()
            return KillSwitchStatus(
                is_active=self._is_active,
                triggered_at=self._triggered_at,
                reason=self._activation_reason,
                peak_24h=peak_24h,
                peak_all_time=self._peak_all_time,
                drawdown_24h=dd_24h,
                drawdown_total=dd_total,
                last_value=self._last_value,
                last_update=self._last_update,
            )

    def should_halt(self) -> bool:
        """True if trading should be halted right now."""
        return self._is_active

    def scale_confidence(self, confidence: float) -> float:
        """Return 0.0 when active; otherwise echo back the input."""
        return 0.0 if self._is_active else float(confidence)

    # ------------------------------------------------------------------
    # Check / update
    # ------------------------------------------------------------------

    def check(
        self,
        current_portfolio_value: float,
        timestamp: datetime | None = None,
    ) -> bool:
        """Record a new portfolio value; activate if either DD guard trips.

        Returns True when trading should be halted (same as :attr:`is_active`).
        """
        if current_portfolio_value is None or current_portfolio_value <= 0:
            raise ValueError("portfolio value must be > 0")

        ts = timestamp or self._now()
        with self._lock:
            # Track peaks (never lower them on recovery — drawdown is from peak)
            if self._peak_all_time is None or current_portfolio_value > self._peak_all_time:
                self._peak_all_time = current_portfolio_value

            # Prune rolling 24h window, then append
            cutoff = ts - timedelta(hours=24)
            while self._samples_24h and self._samples_24h[0].ts < cutoff:
                self._samples_24h.popleft()
            self._samples_24h.append(_PeakSample(ts=ts, value=current_portfolio_value))

            self._last_value = current_portfolio_value
            self._last_update = ts

            dd_24h, dd_total = self._drawdowns_unsafe()

            if self._is_active:
                return True

            reason: str | None = None
            if dd_total >= self.max_drawdown_total:
                reason = (
                    f"total drawdown {dd_total:.2%} exceeds limit "
                    f"{self.max_drawdown_total:.0%}"
                )
            elif dd_24h >= self.max_drawdown_24h:
                reason = (
                    f"24h drawdown {dd_24h:.2%} exceeds limit "
                    f"{self.max_drawdown_24h:.0%}"
                )

            if reason is None:
                return False

            self._is_active = True
            self._triggered_at = ts
            self._activation_reason = reason
            event = KillSwitchEvent(
                kind="activated",
                timestamp=ts,
                reason=reason,
                portfolio_value=current_portfolio_value,
                drawdown_24h=dd_24h,
                drawdown_total=dd_total,
            )

        # Notify *outside* the lock so slow publishers don't block check().
        self._emit(event)
        return True

    def check_recovery(self, paper_trading_pnl: float) -> bool:
        """Deactivate when paper-trading PnL hits recovery_threshold.

        ``paper_trading_pnl`` is a fractional return (e.g. 0.025 = +2.5%).
        Returns True when the switch was (or stayed) deactivated.
        """
        with self._lock:
            if not self._is_active:
                return True

            if paper_trading_pnl < self.recovery_threshold:
                return False

            ts = self._now()
            dd_24h, dd_total = self._drawdowns_unsafe()
            value = self._last_value or 0.0
            event = KillSwitchEvent(
                kind="deactivated",
                timestamp=ts,
                reason=(
                    f"paper trading recovered {paper_trading_pnl:.2%} "
                    f">= threshold {self.recovery_threshold:.0%}"
                ),
                portfolio_value=value,
                drawdown_24h=dd_24h,
                drawdown_total=dd_total,
            )
            self._is_active = False
            self._triggered_at = None
            self._activation_reason = None

        self._emit(event)
        return True

    def reset(self) -> None:
        """Clear all state — intended for tests and operator override."""
        with self._lock:
            self._peak_all_time = None
            self._samples_24h.clear()
            self._is_active = False
            self._triggered_at = None
            self._activation_reason = None
            self._last_value = None
            self._last_update = None

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _peak_24h_unsafe(self) -> float | None:
        if not self._samples_24h:
            return None
        return max(s.value for s in self._samples_24h)

    def _drawdowns_unsafe(self) -> tuple[float, float]:
        if self._last_value is None:
            return 0.0, 0.0
        peak_24h = self._peak_24h_unsafe() or self._last_value
        peak_total = self._peak_all_time or self._last_value
        dd_24h = max(0.0, (peak_24h - self._last_value) / peak_24h) if peak_24h > 0 else 0.0
        dd_total = max(0.0, (peak_total - self._last_value) / peak_total) if peak_total > 0 else 0.0
        return dd_24h, dd_total

    def _emit(self, event: KillSwitchEvent) -> None:
        # Event bus
        try:
            publisher = self._publish_event or _default_publisher()
            if publisher is not None:
                event_type = f"kill_switch.{event.kind}"
                publisher(event_type, event.to_dict())
        except Exception as e:
            log.error("kill_switch event publish failed: %s", e)

        # Telegram (P0 priority)
        try:
            notifier = self._notify or _default_notifier()
            if notifier is not None:
                if event.kind == "activated":
                    text = (
                        f"🚨 KILL SWITCH ACTIVATED\n"
                        f"{event.reason}\n"
                        f"Portfolio: ${event.portfolio_value:,.2f} | "
                        f"24h DD: {event.drawdown_24h:.2%} | "
                        f"Total DD: {event.drawdown_total:.2%}"
                    )
                else:
                    text = (
                        f"✅ KILL SWITCH DEACTIVATED\n"
                        f"{event.reason}\n"
                        f"Portfolio: ${event.portfolio_value:,.2f}"
                    )
                notifier(text, priority="p0")
        except Exception as e:
            log.error("kill_switch telegram notify failed: %s", e)


# ---------------------------------------------------------------------------
# Default dependency resolvers — imported lazily to keep this module cheap.
# ---------------------------------------------------------------------------


def _default_publisher():
    try:
        from lib.core.event_bus import publish as _pub
        return _pub
    except Exception:
        return None


def _default_notifier():
    try:
        from lib.telegram.src.sapphire_telegram.safe_send import send
        return send
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------


_switch: KillSwitch | None = None
_switch_lock = threading.Lock()


def get_kill_switch() -> KillSwitch:
    """Process-wide KillSwitch singleton."""
    global _switch
    with _switch_lock:
        if _switch is None:
            _switch = KillSwitch()
        return _switch


def reset_kill_switch() -> None:
    """Testing helper — drop the singleton."""
    global _switch
    with _switch_lock:
        _switch = None
