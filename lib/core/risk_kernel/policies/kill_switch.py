"""Kill-switch deference policy."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from lib.core.risk_kernel.types import DecisionEnvelope, PolicyResult


class KillSwitchPolicy:
    """Reject non-reducing entries when the provided kill switch is active."""

    name = "kill_switch_deference"
    version = "1.0.0"

    def __init__(self, *, status_provider: Callable[[], Any] | None = None) -> None:
        self.status_provider = status_provider
        self.params = {"uses_status_provider": bool(status_provider)}

    def check(self, envelope: DecisionEnvelope) -> PolicyResult:
        active, source = _active_from_envelope(envelope)
        if active is None and self.status_provider is not None:
            active, source = _active_from_provider(self.status_provider)

        metrics = {"kill_switch_active": active, "source": source}
        if envelope.reduce_only:
            return self._pass("reduce-only decision remains allowed during kill switch", metrics)
        if active is True:
            return PolicyResult(
                policy=self.name,
                version=self.version,
                passed=False,
                reason=f"kill switch active via {source}",
                metrics=metrics,
                params=dict(self.params),
            )
        return self._pass("kill switch inactive or not asserted", metrics)

    def _pass(self, reason: str, metrics: dict[str, Any] | None = None) -> PolicyResult:
        return PolicyResult(
            policy=self.name,
            version=self.version,
            passed=True,
            reason=reason,
            metrics=metrics or {},
            params=dict(self.params),
        )


def _active_from_envelope(envelope: DecisionEnvelope) -> tuple[bool | None, str]:
    for source, mapping in (
        ("risk_metrics", envelope.risk_metrics),
        ("metadata", envelope.metadata),
        ("market_data", envelope.market_data),
    ):
        if "kill_switch_active" in mapping:
            return _boolish(mapping["kill_switch_active"]), source
        if "security_kill_switch_active" in mapping:
            return _boolish(mapping["security_kill_switch_active"]), source
    return None, "not_provided"


def _active_from_provider(provider: Callable[[], Any]) -> tuple[bool | None, str]:
    try:
        status = provider()
    except Exception:
        return True, "status_provider_error"
    if isinstance(status, bool):
        return status, "status_provider"
    if isinstance(status, dict):
        for key in ("is_active", "active", "kill_switch_active"):
            if key in status:
                return _boolish(status[key]), f"status_provider.{key}"
    if hasattr(status, "is_active"):
        return _boolish(status.is_active), "status_provider.is_active"
    return None, "status_provider_unknown"


def _boolish(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return str(value).strip().lower() in {"1", "true", "yes", "on", "active", "enabled"}
