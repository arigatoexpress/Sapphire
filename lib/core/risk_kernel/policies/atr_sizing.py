"""ATR and single-trade sizing guard policy."""

from __future__ import annotations

from typing import Any

from lib.core.risk_kernel.types import DecisionEnvelope, PolicyResult


class AtrSizingPolicy:
    """Reject entries whose notional or ATR risk exceeds configured limits."""

    name = "atr_sizing"
    version = "1.0.0"

    def __init__(
        self,
        *,
        max_position_pct: float = 10.0,
        max_atr_risk_pct: float = 2.0,
        max_single_trade_loss_pct: float = 1.0,
    ) -> None:
        self.params = {
            "max_position_pct": max(0.0, float(max_position_pct)),
            "max_atr_risk_pct": max(0.0, float(max_atr_risk_pct)),
            "max_single_trade_loss_pct": max(0.0, float(max_single_trade_loss_pct)),
        }

    def check(self, envelope: DecisionEnvelope) -> PolicyResult:
        if envelope.reduce_only:
            return self._pass("reduce-only decision bypasses entry sizing gate")

        metrics = _risk_metrics(envelope)
        reasons = []
        position_pct = metrics.get("position_pct")
        atr_risk_pct = metrics.get("atr_risk_pct")
        stop_loss_risk_pct = metrics.get("stop_loss_risk_pct")

        if envelope.metadata.get("position_sizing_override") and not envelope.metadata.get(
            "operator_approved"
        ):
            reasons.append("position_sizing_override without operator_approved")

        max_position_pct = float(self.params["max_position_pct"])
        if max_position_pct > 0 and position_pct is not None and position_pct > max_position_pct:
            reasons.append(f"position_pct {position_pct:.2f}% > {max_position_pct:.2f}%")

        max_atr_risk_pct = float(self.params["max_atr_risk_pct"])
        if max_atr_risk_pct > 0 and atr_risk_pct is not None and atr_risk_pct > max_atr_risk_pct:
            reasons.append(f"atr_risk_pct {atr_risk_pct:.2f}% > {max_atr_risk_pct:.2f}%")

        max_loss_pct = float(self.params["max_single_trade_loss_pct"])
        if (
            max_loss_pct > 0
            and stop_loss_risk_pct is not None
            and stop_loss_risk_pct > max_loss_pct
        ):
            reasons.append(f"stop_loss_risk_pct {stop_loss_risk_pct:.2f}% > {max_loss_pct:.2f}%")

        if reasons:
            return PolicyResult(
                policy=self.name,
                version=self.version,
                passed=False,
                reason="; ".join(reasons),
                metrics=metrics,
                params=dict(self.params),
            )
        return self._pass("ATR and notional risk within configured limits", metrics)

    def _pass(self, reason: str, metrics: dict[str, Any] | None = None) -> PolicyResult:
        return PolicyResult(
            policy=self.name,
            version=self.version,
            passed=True,
            reason=reason,
            metrics=metrics or {},
            params=dict(self.params),
        )


def _risk_metrics(envelope: DecisionEnvelope) -> dict[str, float | None]:
    equity = _as_float(envelope.equity)
    notional = _as_float(envelope.notional_usd)
    price = _as_float(envelope.price)
    quantity = _as_float(envelope.quantity)
    atr = _as_float(envelope.atr)
    stop_loss = _as_float(envelope.stop_loss_price)
    position_pct = _as_float(envelope.proposed_position_pct)

    if position_pct is None and equity and notional:
        position_pct = (notional / equity) * 100.0

    atr_risk_pct = None
    if equity and notional and price and atr:
        atr_risk_pct = (notional * (atr / price) / equity) * 100.0

    stop_loss_risk_pct = None
    if equity and price and quantity and stop_loss:
        stop_loss_risk_pct = (abs(price - stop_loss) * quantity / equity) * 100.0

    return {
        "equity": equity,
        "notional_usd": notional,
        "position_pct": position_pct,
        "atr": atr,
        "atr_risk_pct": atr_risk_pct,
        "stop_loss_risk_pct": stop_loss_risk_pct,
    }


def _as_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
