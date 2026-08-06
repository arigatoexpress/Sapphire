"""Plant free-reign gate — sole-writer pre-check (paper-safe pure functions).

Wire into ops-state free-reign / easy_mode / rh-chain decision path:

    from lib.grok.free_reign_gate import gate_order, GateRequest

    result = gate_order(GateRequest(...))
    if not result.allowed:
        return deny(result.code, result.reason)

Never places orders. Never imports plant secrets.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Mapping

from lib.grok.policy import OrderProposal, evaluate_proposal, evaluate_scale_out


@dataclass(frozen=True)
class GateRequest:
    symbol: str
    side: str
    rail: str
    asset_class: str
    notional_usd: float
    open_positions_on_rail: int = 0
    contract_address: str | None = None
    moss_grant_hours_left: float | None = None
    is_defined_risk_option: bool = False
    dte_days: float | None = None
    regime: str | None = None
    day_options_premium_usd: float = 0.0
    day_realized_pnl_usd: float = 0.0
    signal_source_count: int = 1
    hyperliquid_signing_gate_armed: bool | None = None
    has_catalyst_tag: bool = False
    meta: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class GateResult:
    allowed: bool
    code: str
    reason: str
    arm: str
    details: Mapping[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def gate_order(
    req: GateRequest,
    policy: Mapping[str, Any] | None = None,
) -> GateResult:
    """Authorize or deny a proposed free-reign order under monorepo policy."""
    d = evaluate_proposal(
        OrderProposal(
            symbol=req.symbol,
            side=req.side,
            rail=req.rail,
            asset_class=req.asset_class,
            notional_usd=req.notional_usd,
            open_positions_on_rail=req.open_positions_on_rail,
            contract_address=req.contract_address,
            moss_grant_hours_left=req.moss_grant_hours_left,
            is_defined_risk_option=req.is_defined_risk_option,
            dte_days=req.dte_days,
            regime=req.regime,
            day_options_premium_usd=req.day_options_premium_usd,
            day_realized_pnl_usd=req.day_realized_pnl_usd,
            signal_source_count=req.signal_source_count,
            hyperliquid_signing_gate_armed=req.hyperliquid_signing_gate_armed,
            has_catalyst_tag=req.has_catalyst_tag,
            meta=req.meta,
        ),
        policy=policy,
    )
    return GateResult(
        allowed=d.allow,
        code=d.code,
        reason=d.reason,
        arm=d.arm,
        details=dict(d.details),
    )


def gate_option_management(
    *,
    entry_premium: float,
    mark_premium: float,
    remaining_qty: float,
    policy: Mapping[str, Any] | None = None,
) -> GateResult:
    """AXTI scale-out / hard SL management decision."""
    d = evaluate_scale_out(
        entry_premium=entry_premium,
        mark_premium=mark_premium,
        remaining_qty=remaining_qty,
        policy=policy,
    )
    return GateResult(
        allowed=d.allow,
        code=d.code,
        reason=d.reason,
        arm=d.arm,
        details=dict(d.details),
    )


def batch_gate(
    requests: list[GateRequest],
    policy: Mapping[str, Any] | None = None,
) -> list[GateResult]:
    return [gate_order(r, policy=policy) for r in requests]
