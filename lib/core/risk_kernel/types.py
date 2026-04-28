"""Versioned public data contracts for the Sapphire risk kernel."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from typing import Any

SCHEMA_VERSION = 1


def _now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def _float_or_none(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _boolish(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return str(value).strip().lower() in {"1", "true", "yes", "on", "active", "enabled"}


@dataclass(frozen=True)
class DecisionEnvelope:
    """A proposed decision to evaluate before it can become an action.

    The envelope is intentionally wider than trading. Trading callers normally
    populate price, notional, equity, ATR, and drawdown fields; non-trading
    callers can place their safety evidence in ``risk_metrics`` and
    ``metadata`` while still receiving a complete verdict tree.
    """

    decision_id: str
    action: str
    symbol: str = ""
    side: str = ""
    quantity: float | None = None
    price: float | None = None
    notional_usd: float | None = None
    proposed_position_pct: float | None = None
    equity: float | None = None
    atr: float | None = None
    stop_loss_price: float | None = None
    confidence: float | None = None
    reduce_only: bool = False
    risk_metrics: dict[str, Any] = field(default_factory=dict)
    market_data: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=_now_iso)
    schema_version: int = SCHEMA_VERSION

    @classmethod
    def from_mapping(cls, payload: dict[str, Any]) -> DecisionEnvelope:
        """Coerce a mapping into a schema-version-1 decision envelope."""
        merged_metrics = dict(payload.get("risk_metrics") or {})
        merged_metadata = dict(payload.get("metadata") or {})
        decision_id = str(payload.get("decision_id") or payload.get("id") or "")
        if not decision_id:
            seed = json.dumps(payload, sort_keys=True, default=str)
            decision_id = f"decision-{hashlib.sha256(seed.encode()).hexdigest()[:16]}"
        return cls(
            decision_id=decision_id,
            action=str(payload.get("action") or payload.get("order_type") or ""),
            symbol=str(payload.get("symbol") or ""),
            side=str(payload.get("side") or payload.get("direction") or ""),
            quantity=_float_or_none(payload.get("quantity")),
            price=_float_or_none(payload.get("price")),
            notional_usd=_float_or_none(payload.get("notional_usd") or payload.get("position_usd")),
            proposed_position_pct=_float_or_none(
                payload.get("proposed_position_pct") or payload.get("position_pct")
            ),
            equity=_float_or_none(payload.get("equity") or payload.get("equity_estimate")),
            atr=_float_or_none(payload.get("atr") or merged_metrics.get("atr")),
            stop_loss_price=_float_or_none(
                payload.get("stop_loss_price")
                or payload.get("stop_loss")
                or payload.get("sl_price")
            ),
            confidence=_float_or_none(payload.get("confidence")),
            reduce_only=_boolish(payload.get("reduce_only")),
            risk_metrics=merged_metrics,
            market_data=dict(payload.get("market_data") or {}),
            metadata=merged_metadata,
            created_at=str(payload.get("created_at") or _now_iso()),
            schema_version=int(payload.get("schema_version") or SCHEMA_VERSION),
        )

    def metric(self, key: str, default: Any = None) -> Any:
        """Read a metric from top-level fields, risk metrics, market data, then metadata."""
        if hasattr(self, key):
            value = getattr(self, key)
            if value is not None:
                return value
        if key in self.risk_metrics:
            return self.risk_metrics[key]
        if key in self.market_data:
            return self.market_data[key]
        return self.metadata.get(key, default)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class PolicyResult:
    """Result returned by one risk policy."""

    policy: str
    version: str
    passed: bool
    reason: str
    severity: str = "block"
    metrics: dict[str, Any] = field(default_factory=dict)
    params: dict[str, Any] = field(default_factory=dict)

    @property
    def fired(self) -> bool:
        return not self.passed

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["fired"] = self.fired
        return data


@dataclass(frozen=True)
class RiskVerdict:
    """Complete risk verdict tree for a decision envelope."""

    decision_id: str
    allowed: bool
    policy_results: tuple[PolicyResult, ...]
    generated_at: str
    evaluation_ms: float
    kernel_version: str = "0.1.0"
    schema_version: int = SCHEMA_VERSION

    @property
    def fired_gates(self) -> tuple[PolicyResult, ...]:
        return tuple(result for result in self.policy_results if result.fired)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "kernel_version": self.kernel_version,
            "decision_id": self.decision_id,
            "allowed": self.allowed,
            "generated_at": self.generated_at,
            "evaluation_ms": self.evaluation_ms,
            "fired_gates": [result.to_dict() for result in self.fired_gates],
            "policy_results": [result.to_dict() for result in self.policy_results],
        }


class RiskPolicy:
    """Small policy protocol base class for type checkers and documentation."""

    name: str
    version: str
    params: dict[str, Any]

    def check(
        self, envelope: DecisionEnvelope
    ) -> PolicyResult:  # pragma: no cover - interface only
        raise NotImplementedError
