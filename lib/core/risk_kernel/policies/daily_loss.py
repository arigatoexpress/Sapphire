"""Daily loss guard policy."""

from __future__ import annotations

from typing import Any

from lib.core.risk_kernel.types import DecisionEnvelope, PolicyResult


class DailyLossPolicy:
    """Reject entries after a configured daily loss threshold is reached."""

    name = "daily_loss"
    version = "1.0.0"

    def __init__(self, *, max_loss_pct: float = 4.0, max_loss_usd: float = 0.0) -> None:
        self.params = {
            "max_loss_pct": max(0.0, float(max_loss_pct)),
            "max_loss_usd": max(0.0, float(max_loss_usd)),
        }

    def check(self, envelope: DecisionEnvelope) -> PolicyResult:
        if envelope.reduce_only:
            return self._pass("reduce-only decision bypasses entry loss gate")

        loss_pct = _as_float(envelope.metric("daily_loss_pct"))
        loss_usd = _as_float(envelope.metric("daily_loss_usd"))
        metrics: dict[str, Any] = {"daily_loss_pct": loss_pct, "daily_loss_usd": loss_usd}

        max_pct = float(self.params["max_loss_pct"])
        max_usd = float(self.params["max_loss_usd"])
        pct_breach = max_pct > 0 and loss_pct is not None and loss_pct >= max_pct
        usd_breach = max_usd > 0 and loss_usd is not None and loss_usd >= max_usd
        if pct_breach or usd_breach:
            reasons = []
            if pct_breach:
                reasons.append(f"daily_loss_pct {loss_pct:.2f}% >= {max_pct:.2f}%")
            if usd_breach:
                reasons.append(f"daily_loss_usd {loss_usd:.2f} >= {max_usd:.2f}")
            return PolicyResult(
                policy=self.name,
                version=self.version,
                passed=False,
                reason="; ".join(reasons),
                metrics=metrics,
                params=dict(self.params),
            )
        return self._pass("daily loss within configured limits", metrics)

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
