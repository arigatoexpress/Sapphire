"""Intraday drawdown guard policy."""

from __future__ import annotations

from typing import Any

from lib.core.risk_kernel.types import DecisionEnvelope, PolicyResult


class IntradayDrawdownPolicy:
    """Reject entries when local peak-to-current drawdown breaches the limit."""

    name = "intraday_drawdown"
    version = "1.0.0"

    def __init__(self, *, max_drawdown_pct: float = 3.5) -> None:
        self.params = {"max_drawdown_pct": max(0.0, float(max_drawdown_pct))}

    def check(self, envelope: DecisionEnvelope) -> PolicyResult:
        if envelope.reduce_only:
            return self._pass("reduce-only decision bypasses entry drawdown gate")

        drawdown_pct = _as_float(
            envelope.metric("intraday_drawdown_pct", envelope.metric("drawdown_pct"))
        )
        metrics = {"intraday_drawdown_pct": drawdown_pct}
        limit = float(self.params["max_drawdown_pct"])
        if limit > 0 and drawdown_pct is not None and drawdown_pct >= limit:
            return PolicyResult(
                policy=self.name,
                version=self.version,
                passed=False,
                reason=f"intraday_drawdown_pct {drawdown_pct:.2f}% >= {limit:.2f}%",
                metrics=metrics,
                params=dict(self.params),
            )
        return self._pass("intraday drawdown within configured limit", metrics)

    def _pass(self, reason: str, metrics: dict[str, Any] | None = None) -> PolicyResult:
        return PolicyResult(
            policy=self.name,
            version=self.version,
            passed=True,
            reason=reason,
            metrics=metrics or {},
            params=dict(self.params),
        )


def _as_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
