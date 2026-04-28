"""Public Sapphire risk-kernel package.

``RiskKernelV1`` is the acquisition-facing policy kernel: callers pass a
``DecisionEnvelope`` and receive a ``RiskVerdict`` enumerating every policy
that fired. The legacy ``HardRiskKernel`` remains re-exported for compatibility
with existing signal-pipeline and unit-test imports.
"""

from __future__ import annotations

import time
from collections.abc import Iterable
from datetime import UTC, datetime
from typing import Any

from lib.core.risk_kernel.policies import (
    AtrSizingPolicy,
    DailyLossPolicy,
    DataLeakagePolicy,
    IntradayDrawdownPolicy,
    KillSwitchPolicy,
)
from lib.core.risk_kernel.types import DecisionEnvelope, PolicyResult, RiskPolicy, RiskVerdict

try:  # Prefer the existing canonical package path when callers provide it.
    from sapphire_core.risk_kernel import HardRiskKernel, RiskKernelEvent  # type: ignore
except ModuleNotFoundError:  # pragma: no cover - direct repo-root import path
    from lib.core.src.sapphire_core.risk_kernel import HardRiskKernel, RiskKernelEvent

try:
    from lib.core.confirmation_firewall import ActionRisk, ConfirmationFirewall, classify_action
except ModuleNotFoundError:  # pragma: no cover
    ActionRisk = None  # type: ignore
    ConfirmationFirewall = None  # type: ignore

    def classify_action(*_args: Any, **_kwargs: Any) -> None:  # type: ignore
        raise ModuleNotFoundError("lib.core.confirmation_firewall")


__version__ = "0.1.0"


class RiskKernelV1:
    """Evaluate decision envelopes against the default Sapphire policy set."""

    version = __version__

    def __init__(self, policies: Iterable[RiskPolicy] | None = None) -> None:
        self.policies = tuple(policies) if policies is not None else default_policies()

    def evaluate(self, decision: DecisionEnvelope | dict[str, Any]) -> RiskVerdict:
        """Return a full verdict tree for ``decision``.

        Policy exceptions fail closed and appear as fired policy results; this
        keeps a single broken plugin policy from silently allowing execution.
        """
        envelope = (
            decision
            if isinstance(decision, DecisionEnvelope)
            else DecisionEnvelope.from_mapping(dict(decision))
        )
        started = time.perf_counter()
        results: list[PolicyResult] = []
        for policy in self.policies:
            try:
                results.append(policy.check(envelope))
            except Exception as exc:
                results.append(
                    PolicyResult(
                        policy=getattr(policy, "name", policy.__class__.__name__),
                        version=getattr(policy, "version", "unknown"),
                        passed=False,
                        reason=f"policy error: {exc.__class__.__name__}",
                        severity="block",
                        metrics={},
                        params=dict(getattr(policy, "params", {}) or {}),
                    )
                )
        elapsed_ms = round((time.perf_counter() - started) * 1000.0, 4)
        return RiskVerdict(
            decision_id=envelope.decision_id,
            allowed=not any(result.fired for result in results),
            policy_results=tuple(results),
            generated_at=datetime.now(UTC).replace(microsecond=0).isoformat(),
            evaluation_ms=elapsed_ms,
            kernel_version=self.version,
        )


def default_policies() -> tuple[RiskPolicy, ...]:
    """Return the built-in 0.1.0 policy set."""
    return (
        DailyLossPolicy(max_loss_pct=4.0),
        IntradayDrawdownPolicy(max_drawdown_pct=3.5),
        AtrSizingPolicy(),
        KillSwitchPolicy(),
        DataLeakagePolicy(),
    )


__all__ = [
    "ActionRisk",
    "AtrSizingPolicy",
    "ConfirmationFirewall",
    "DailyLossPolicy",
    "DataLeakagePolicy",
    "DecisionEnvelope",
    "HardRiskKernel",
    "IntradayDrawdownPolicy",
    "KillSwitchPolicy",
    "PolicyResult",
    "RiskKernelEvent",
    "RiskKernelV1",
    "RiskPolicy",
    "RiskVerdict",
    "__version__",
    "classify_action",
    "default_policies",
]
