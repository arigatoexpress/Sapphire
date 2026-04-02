"""
Hard risk-kernel for fail-closed entry gating.

Purpose
-------
Centralize hard stop logic that protects against account ruin scenarios:
  - Daily loss breach
  - Intraday drawdown from local peak
  - Consecutive losing fills
  - Consecutive hard execution failures

This module is intentionally dependency-light so venue bots can reuse it.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, Optional


def _utc_day(ts: float) -> str:
    return datetime.fromtimestamp(float(ts), tz=timezone.utc).strftime("%Y-%m-%d")


@dataclass
class RiskKernelEvent:
    triggered: bool
    reason: str
    blocked_until_ts: float
    metrics: Dict[str, Any]

    def as_dict(self) -> Dict[str, Any]:
        return {
            "triggered": bool(self.triggered),
            "reason": str(self.reason),
            "blocked_until_ts": float(self.blocked_until_ts),
            "metrics": dict(self.metrics or {}),
        }


class HardRiskKernel:
    """
    Lightweight hard-risk governor with explicit hold windows.

    Notes
    -----
    * Entry gating only: exits/reduce-only orders should still be allowed.
    * Cooldown holds are extend-only (newer/higher hold wins).
    """

    def __init__(
        self,
        *,
        enabled: bool = True,
        hold_seconds: float = 1800.0,
        max_daily_loss_pct: float = 4.0,
        max_daily_loss_usd: float = 0.0,
        max_intraday_drawdown_pct: float = 3.5,
        max_consecutive_loss_events: int = 4,
        max_consecutive_hard_fails: int = 5,
        loss_event_min_delta_usd: float = 0.15,
    ) -> None:
        self.enabled = bool(enabled)
        self.hold_seconds = max(60.0, float(hold_seconds))
        self.max_daily_loss_pct = max(0.0, float(max_daily_loss_pct))
        self.max_daily_loss_usd = max(0.0, float(max_daily_loss_usd))
        self.max_intraday_drawdown_pct = max(0.0, float(max_intraday_drawdown_pct))
        self.max_consecutive_loss_events = max(0, int(max_consecutive_loss_events))
        self.max_consecutive_hard_fails = max(0, int(max_consecutive_hard_fails))
        self.loss_event_min_delta_usd = max(0.0, float(loss_event_min_delta_usd))

        self.current_day: str = _utc_day(time.time())
        self.day_start_equity: float = 0.0
        self.day_peak_equity: float = 0.0
        self.last_equity: float = 0.0
        self.last_execution_equity: float = 0.0

        self.consecutive_loss_events: int = 0
        self.consecutive_hard_fails: int = 0

        self.blocked_until_ts: float = 0.0
        self.block_reason: str = ""
        self.last_triggered_at_ts: float = 0.0

    def _roll_day_if_needed(self, ts: float, equity: float = 0.0) -> None:
        day = _utc_day(ts)
        if day == self.current_day:
            return
        self.current_day = day
        self.day_start_equity = float(equity) if equity > 0 else 0.0
        self.day_peak_equity = float(equity) if equity > 0 else 0.0
        self.last_equity = float(equity) if equity > 0 else 0.0
        self.last_execution_equity = float(equity) if equity > 0 else 0.0
        self.consecutive_loss_events = 0
        self.consecutive_hard_fails = 0

    def _clear_hold_if_elapsed(self, now_ts: float) -> None:
        if self.blocked_until_ts <= 0:
            return
        if now_ts < self.blocked_until_ts:
            return
        self.blocked_until_ts = 0.0
        self.block_reason = ""

    def _activate_hold(
        self,
        now_ts: float,
        reason: str,
        metrics: Optional[Dict[str, Any]] = None,
    ) -> RiskKernelEvent:
        self._clear_hold_if_elapsed(now_ts)
        hold_until = now_ts + self.hold_seconds
        if hold_until > self.blocked_until_ts:
            self.blocked_until_ts = hold_until
        self.block_reason = str(reason).strip()[:220]
        self.last_triggered_at_ts = now_ts
        return RiskKernelEvent(
            triggered=True,
            reason=self.block_reason,
            blocked_until_ts=self.blocked_until_ts,
            metrics=metrics or {},
        )

    def can_open_entry(self, now_ts: Optional[float] = None) -> tuple[bool, str]:
        """
        Hard gate for entry-like orders.
        """
        if not self.enabled:
            return True, ""
        ts = float(now_ts if now_ts is not None else time.time())
        self._clear_hold_if_elapsed(ts)
        if self.blocked_until_ts > ts:
            remaining = self.blocked_until_ts - ts
            return (
                False,
                f"risk_kernel_hold {remaining:.0f}s: {self.block_reason or 'risk limit breached'}",
            )
        return True, ""

    def ingest_equity_snapshot(
        self,
        snapshot: Dict[str, Any],
        *,
        now_ts: Optional[float] = None,
    ) -> Optional[RiskKernelEvent]:
        """
        Feed latest equity snapshot and trigger hard-halt if a core risk limit trips.
        """
        if not self.enabled:
            return None

        ts = float(now_ts if now_ts is not None else time.time())
        equity = 0.0
        try:
            equity = float(snapshot.get("equity_estimate", 0.0) or 0.0)
        except (TypeError, ValueError):
            equity = 0.0
        if equity <= 0:
            self._roll_day_if_needed(ts, 0.0)
            return None

        self._roll_day_if_needed(ts, equity)
        if self.day_start_equity <= 0:
            self.day_start_equity = equity
        if self.day_peak_equity <= 0:
            self.day_peak_equity = equity
        self.day_peak_equity = max(self.day_peak_equity, equity)
        self.last_equity = equity
        self._clear_hold_if_elapsed(ts)

        day_loss_usd = self.day_start_equity - equity
        day_loss_pct = (
            (day_loss_usd / self.day_start_equity) * 100.0 if self.day_start_equity > 0 else 0.0
        )
        intraday_dd_pct = (
            ((self.day_peak_equity - equity) / self.day_peak_equity) * 100.0
            if self.day_peak_equity > 0
            else 0.0
        )

        metrics = {
            "equity_estimate": round(equity, 8),
            "day_start_equity": round(self.day_start_equity, 8),
            "day_peak_equity": round(self.day_peak_equity, 8),
            "day_loss_usd": round(day_loss_usd, 8),
            "day_loss_pct": round(day_loss_pct, 6),
            "intraday_drawdown_pct": round(intraday_dd_pct, 6),
            "consecutive_loss_events": int(self.consecutive_loss_events),
            "consecutive_hard_fails": int(self.consecutive_hard_fails),
            "day": self.current_day,
        }

        if self.max_daily_loss_pct > 0 and day_loss_pct >= self.max_daily_loss_pct:
            return self._activate_hold(
                ts,
                (
                    f"daily_loss_pct {day_loss_pct:.2f}% >= "
                    f"{self.max_daily_loss_pct:.2f}%"
                ),
                metrics,
            )
        if self.max_daily_loss_usd > 0 and day_loss_usd >= self.max_daily_loss_usd:
            return self._activate_hold(
                ts,
                (
                    f"daily_loss_usd {day_loss_usd:.2f} >= "
                    f"{self.max_daily_loss_usd:.2f}"
                ),
                metrics,
            )
        if (
            self.max_intraday_drawdown_pct > 0
            and intraday_dd_pct >= self.max_intraday_drawdown_pct
        ):
            return self._activate_hold(
                ts,
                (
                    f"intraday_drawdown_pct {intraday_dd_pct:.2f}% >= "
                    f"{self.max_intraday_drawdown_pct:.2f}%"
                ),
                metrics,
            )
        return None

    def record_execution_outcome(
        self,
        *,
        outcome: str,
        equity_estimate: float = 0.0,
        now_ts: Optional[float] = None,
    ) -> Optional[RiskKernelEvent]:
        """
        Update risk counters from execution outcomes.
        """
        if not self.enabled:
            return None

        ts = float(now_ts if now_ts is not None else time.time())
        self._roll_day_if_needed(ts, equity_estimate if equity_estimate > 0 else self.last_equity)
        self._clear_hold_if_elapsed(ts)
        outcome_key = str(outcome or "").strip().lower()

        if outcome_key == "hard_failed":
            self.consecutive_hard_fails += 1
        elif outcome_key in {"filled_success", "accepted_no_fill", "noop", "policy_noop", "policy_reject"}:
            self.consecutive_hard_fails = 0

        if outcome_key == "filled_success" and equity_estimate > 0:
            if self.last_execution_equity > 0:
                delta = equity_estimate - self.last_execution_equity
                if delta <= -self.loss_event_min_delta_usd:
                    self.consecutive_loss_events += 1
                elif delta >= self.loss_event_min_delta_usd:
                    self.consecutive_loss_events = 0
            self.last_execution_equity = float(equity_estimate)

        metrics = {
            "outcome": outcome_key,
            "equity_estimate": round(float(equity_estimate or 0.0), 8),
            "consecutive_loss_events": int(self.consecutive_loss_events),
            "consecutive_hard_fails": int(self.consecutive_hard_fails),
            "loss_event_min_delta_usd": float(self.loss_event_min_delta_usd),
        }

        if (
            self.max_consecutive_hard_fails > 0
            and self.consecutive_hard_fails >= self.max_consecutive_hard_fails
        ):
            return self._activate_hold(
                ts,
                (
                    f"consecutive_hard_fails {self.consecutive_hard_fails} >= "
                    f"{self.max_consecutive_hard_fails}"
                ),
                metrics,
            )

        if (
            self.max_consecutive_loss_events > 0
            and self.consecutive_loss_events >= self.max_consecutive_loss_events
        ):
            return self._activate_hold(
                ts,
                (
                    f"consecutive_loss_events {self.consecutive_loss_events} >= "
                    f"{self.max_consecutive_loss_events}"
                ),
                metrics,
            )
        return None

    def status(self, now_ts: Optional[float] = None) -> Dict[str, Any]:
        ts = float(now_ts if now_ts is not None else time.time())
        self._clear_hold_if_elapsed(ts)
        return {
            "enabled": bool(self.enabled),
            "day": self.current_day,
            "day_start_equity": float(self.day_start_equity),
            "day_peak_equity": float(self.day_peak_equity),
            "last_equity": float(self.last_equity),
            "last_execution_equity": float(self.last_execution_equity),
            "consecutive_loss_events": int(self.consecutive_loss_events),
            "consecutive_hard_fails": int(self.consecutive_hard_fails),
            "blocked": bool(self.blocked_until_ts > ts),
            "blocked_until_ts": float(self.blocked_until_ts),
            "blocked_for_sec": max(0.0, float(self.blocked_until_ts - ts)),
            "block_reason": str(self.block_reason),
            "last_triggered_at_ts": float(self.last_triggered_at_ts),
            "config": {
                "hold_seconds": float(self.hold_seconds),
                "max_daily_loss_pct": float(self.max_daily_loss_pct),
                "max_daily_loss_usd": float(self.max_daily_loss_usd),
                "max_intraday_drawdown_pct": float(self.max_intraday_drawdown_pct),
                "max_consecutive_loss_events": int(self.max_consecutive_loss_events),
                "max_consecutive_hard_fails": int(self.max_consecutive_hard_fails),
                "loss_event_min_delta_usd": float(self.loss_event_min_delta_usd),
            },
        }
