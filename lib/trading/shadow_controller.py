"""Risk-managed paper-shadow trading controller.

The controller automates candidate selection and paper order drafting, but it
does not submit, cancel, replace, sign, or schedule real orders. Robinhood live
orders remain behind ``scripts/ops/robinhood_manual_order.py`` and its typed
confirmation token.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from lib.trading.strategy_lab import (
    ROBINHOOD_DAILY_REAL_FUNDS_TEST_MAX_USD,
    ROBINHOOD_FIRST_REAL_FUNDS_TEST_MAX_USD,
    VENUE_DOCS,
    build_market_universe,
    build_order_drafts,
)

SHADOW_CONTROLLER_SCHEMA_VERSION = 1
SHADOW_STRATEGY_ID = "sapphire_shadow_controller_v1"


@dataclass(frozen=True)
class ShadowRiskPolicy:
    """Fail-closed sizing and routing policy for shadow trading."""

    mode: str = "paper_shadow"
    live_execution_enabled: bool = False
    paper_trading_enabled: bool = True
    requested_candidate_notional_usd: float = ROBINHOOD_FIRST_REAL_FUNDS_TEST_MAX_USD
    max_candidate_notional_usd: float = ROBINHOOD_FIRST_REAL_FUNDS_TEST_MAX_USD
    daily_real_cap_usd: float = ROBINHOOD_DAILY_REAL_FUNDS_TEST_MAX_USD
    funded_cash_budget_usd: float = 50.0
    max_position_fraction_of_pilot: float = 0.20
    min_confidence: float = 0.72
    max_open_candidates: int = 3
    max_spread_bps: float = 150.0
    buy_change_min_pct: float = 0.25
    buy_change_max_pct: float = 6.0
    crash_guard_pct: float = -7.5
    chase_guard_pct: float = 10.0
    require_robinhood_crypto_symbol: bool = True
    limit_orders_only: bool = True
    manual_confirmation_required: bool = True
    disallowed_automation_surfaces: tuple[str, ...] = (
        "scheduler_live_submit",
        "dashboard_live_submit",
        "telegram_live_submit",
        "tradingview_webhook_live_submit",
        "stock_or_etf_robinhood_submit",
    )

    def __post_init__(self) -> None:
        if self.live_execution_enabled:
            raise ValueError("shadow controller cannot enable live execution")
        if self.mode != "paper_shadow":
            raise ValueError("shadow controller mode must remain paper_shadow")
        if self.requested_candidate_notional_usd <= 0:
            raise ValueError("requested notional must be positive")
        if self.max_candidate_notional_usd <= 0 or self.daily_real_cap_usd <= 0:
            raise ValueError("notional caps must be positive")
        if not 0 < self.max_position_fraction_of_pilot <= 1:
            raise ValueError("max position fraction must be in (0, 1]")
        if not 0 < self.min_confidence <= 1:
            raise ValueError("min confidence must be in (0, 1]")
        if self.max_open_candidates <= 0:
            raise ValueError("max open candidates must be positive")
        if self.buy_change_min_pct >= self.buy_change_max_pct:
            raise ValueError("buy change min must be below max")

    @property
    def bounded_candidate_notional_usd(self) -> float:
        """Return the paper/manual notional after all pilot caps."""
        portfolio_cap = self.funded_cash_budget_usd * self.max_position_fraction_of_pilot
        return round(
            min(
                self.requested_candidate_notional_usd,
                self.max_candidate_notional_usd,
                self.daily_real_cap_usd,
                portfolio_cap,
            ),
            2,
        )

    def to_dict(self) -> dict[str, Any]:
        body = asdict(self)
        body["bounded_candidate_notional_usd"] = self.bounded_candidate_notional_usd
        return body


@dataclass(frozen=True)
class ShadowCandidate:
    """One ranked market row with paper-shadow routing metadata."""

    symbol: str
    name: str
    decision: str
    action: str
    confidence: float
    notional_usd: float
    price_usd: float | None
    change_24h_pct: float | None
    priority: str
    tags: tuple[str, ...]
    robinhood_symbol: str | None
    reasons: tuple[str, ...]
    blockers: tuple[str, ...]
    order_drafts: tuple[dict[str, Any], ...]
    manual_order_candidate: dict[str, Any] | None

    def to_dict(self, *, include_drafts: bool = True) -> dict[str, Any]:
        body = asdict(self)
        if not include_drafts:
            body.pop("order_drafts", None)
        return body


def build_shadow_trading_report(
    *,
    market_universe: dict[str, Any] | None = None,
    fetch_live: bool = True,
    policy: ShadowRiskPolicy | None = None,
) -> dict[str, Any]:
    """Build a non-mutating automation report for paper-shadow trading."""
    active_policy = policy or ShadowRiskPolicy()
    market = market_universe or build_market_universe(fetch_live=fetch_live)
    rows = [row for row in market.get("combined_tokens", []) if isinstance(row, dict)]
    evaluated = [evaluate_market_row(row, active_policy) for row in rows]
    evaluated.sort(key=lambda item: (item.decision == "candidate_buy", item.confidence), reverse=True)

    actionable = [
        candidate
        for candidate in evaluated
        if candidate.decision == "candidate_buy"
    ][: active_policy.max_open_candidates]
    watchlist = [
        candidate.to_dict(include_drafts=False)
        for candidate in evaluated
        if candidate.decision != "candidate_buy"
    ][:10]

    return {
        "schema_version": SHADOW_CONTROLLER_SCHEMA_VERSION,
        "generated_at": _now_iso(),
        "mode": active_policy.mode,
        "strategy_id": SHADOW_STRATEGY_ID,
        "live_execution_enabled": False,
        "paper_trading_enabled": active_policy.paper_trading_enabled,
        "source": market.get("source"),
        "market_stale": bool(market.get("stale")),
        "market_errors": market.get("errors") or [],
        "risk_policy": active_policy.to_dict(),
        "candidates": [candidate.to_dict() for candidate in actionable],
        "watchlist": watchlist,
        "blocked_live_actions": blocked_live_actions(active_policy),
        "promotion_gates": promotion_gates(),
        "operator_next_step": operator_next_step(actionable),
        "docs": {
            "robinhood_crypto_api": VENUE_DOCS["robinhood_crypto_api"],
            "robinhood_crypto_support": VENUE_DOCS["robinhood_crypto"],
            "runbook": "docs/ops/robinhood-real-funds-readiness.md",
        },
    }


def evaluate_market_row(row: dict[str, Any], policy: ShadowRiskPolicy) -> ShadowCandidate:
    """Score one token row and build paper/manual order drafts when eligible."""
    symbol = str(row.get("symbol") or "").upper()
    name = str(row.get("name") or symbol)
    tags = tuple(str(tag) for tag in (row.get("tags") or []))
    priority = str(row.get("priority") or "watch")
    robinhood_symbol = _clean_str(row.get("robinhood_symbol"))
    price_usd = _safe_float(row.get("price_usd"))
    change_24h_pct = _safe_float(row.get("change_24h_pct"))
    trend_score = _safe_float(row.get("trend_score"))

    reasons: list[str] = []
    blockers: list[str] = []
    confidence = 0.50

    confidence += _priority_bonus(priority, reasons)
    confidence += _tag_bonus(tags, reasons)
    confidence += _trend_bonus(trend_score, reasons)

    if robinhood_symbol:
        confidence += 0.05
        reasons.append("robinhood_crypto_supported")
    elif policy.require_robinhood_crypto_symbol:
        confidence -= 0.25
        blockers.append("not_robinhood_crypto_tradable")

    if price_usd is None:
        confidence -= 0.15
        blockers.append("missing_live_price")
    if change_24h_pct is None:
        confidence -= 0.15
        blockers.append("missing_24h_change")
    else:
        confidence += _change_bonus(change_24h_pct, policy, reasons, blockers)

    confidence = round(_clamp(confidence, 0.0, 0.99), 3)
    action = "hold"
    decision = "blocked" if blockers else "watch"

    if (
        not blockers
        and confidence >= policy.min_confidence
        and change_24h_pct is not None
        and policy.buy_change_min_pct <= change_24h_pct <= policy.buy_change_max_pct
    ):
        action = "buy"
        decision = "candidate_buy"
        reasons.append("paper_shadow_candidate")
    elif not blockers:
        reasons.append("below_trade_threshold")

    notional = policy.bounded_candidate_notional_usd
    drafts = tuple(
        build_order_drafts(symbol, action, notional_usd=notional, strategy=SHADOW_STRATEGY_ID)
    )
    return ShadowCandidate(
        symbol=symbol,
        name=name,
        decision=decision,
        action=action,
        confidence=confidence,
        notional_usd=notional,
        price_usd=price_usd,
        change_24h_pct=change_24h_pct,
        priority=priority,
        tags=tags,
        robinhood_symbol=robinhood_symbol,
        reasons=tuple(dict.fromkeys(reasons)),
        blockers=tuple(dict.fromkeys(blockers)),
        order_drafts=drafts,
        manual_order_candidate=_manual_order_candidate(symbol, notional, decision, policy),
    )


def blocked_live_actions(policy: ShadowRiskPolicy) -> list[dict[str, Any]]:
    """Document every path that cannot currently place a real order."""
    return [
        {
            "surface": surface,
            "status": "blocked",
            "reason": "shadow_controller_is_paper_only_and_live_orders_require_manual_token",
        }
        for surface in policy.disallowed_automation_surfaces
    ]


def promotion_gates() -> list[str]:
    """Required evidence before any future automation promotion discussion."""
    return [
        "seven_consecutive_days_of_shadow_reports_written_without_errors",
        "paper_candidates_show_positive_net_pnl_after_fee_and_slippage_model",
        "max_shadow_drawdown_under_2_5_percent_for_the_pilot_book",
        "manual_order_script_remains_the_only_robinhood_submit_path",
        "no_scheduler_dashboard_telegram_or_tradingview_path_imports_the_submit_function",
        "ari_confirms_each_real_order_with_exact_symbol_side_limit_notional_and_loss_cap",
    ]


def operator_next_step(candidates: list[ShadowCandidate]) -> dict[str, Any]:
    if not candidates:
        return {
            "status": "no_manual_order_candidate",
            "action": "keep_collecting_shadow_reports",
            "reason": "no token cleared the confidence and risk gates",
        }
    first = candidates[0]
    return {
        "status": "manual_review_ready",
        "action": "review_shadow_candidate_then_run_manual_order_dry_run",
        "symbol": first.symbol,
        "notional_usd": first.notional_usd,
        "confidence": first.confidence,
        "dry_run_only": True,
    }


def write_shadow_report(report: dict[str, Any], path: Path) -> None:
    """Persist the latest report for dashboards or offline review."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _manual_order_candidate(
    symbol: str,
    notional: float,
    decision: str,
    policy: ShadowRiskPolicy,
) -> dict[str, Any] | None:
    if decision != "candidate_buy":
        return None
    return {
        "mode": "manual_dry_run_only",
        "script": "scripts/ops/robinhood_manual_order.py",
        "side": "buy",
        "symbol": symbol,
        "quote_amount_usd": notional,
        "max_spread_bps": policy.max_spread_bps,
        "command": [
            "python3",
            "scripts/ops/robinhood_manual_order.py",
            "--side",
            "buy",
            "--symbol",
            symbol,
            "--limit-price",
            "<guarded_limit_price_from_live_readiness>",
            "--quote-amount-usd",
            f"{notional:.2f}",
            "--max-spread-bps",
            f"{policy.max_spread_bps:.1f}",
        ],
        "execute_flag_included": False,
        "requires_exact_confirmation_token_for_live_order": True,
    }


def _priority_bonus(priority: str, reasons: list[str]) -> float:
    value = priority.lower()
    if value == "high":
        reasons.append("high_priority_asset")
        return 0.08
    if value == "medium":
        reasons.append("medium_priority_asset")
        return 0.04
    return 0.0


def _tag_bonus(tags: tuple[str, ...], reasons: list[str]) -> float:
    tag_set = {tag.lower() for tag in tags}
    bonus = 0.0
    if "preferred" in tag_set or "core" in tag_set:
        bonus += 0.05
        reasons.append("core_or_preferred_asset")
    if "liked" in tag_set:
        bonus += 0.03
        reasons.append("operator_liked_asset")
    if "privacy" in tag_set:
        bonus -= 0.02
        reasons.append("privacy_asset_extra_caution")
    return bonus


def _trend_bonus(trend_score: float | None, reasons: list[str]) -> float:
    if trend_score is None:
        return 0.0
    if trend_score <= 2:
        reasons.append("coingecko_top_trending")
        return 0.05
    if trend_score <= 6:
        reasons.append("coingecko_trending")
        return 0.025
    return 0.0


def _change_bonus(
    change: float,
    policy: ShadowRiskPolicy,
    reasons: list[str],
    blockers: list[str],
) -> float:
    if change <= policy.crash_guard_pct:
        blockers.append("crash_guard_triggered")
        reasons.append("avoid_buying_during_fast_breakdown")
        return -0.25
    if change >= policy.chase_guard_pct:
        blockers.append("chase_guard_triggered")
        reasons.append("avoid_chasing_extended_move")
        return -0.20
    if policy.buy_change_min_pct <= change <= policy.buy_change_max_pct:
        reasons.append("constructive_24h_momentum")
        return min(0.22, 0.08 + (change * 0.025))
    if -3.0 <= change < policy.buy_change_min_pct:
        reasons.append("base_building_watch")
        return 0.02
    reasons.append("momentum_not_in_buy_band")
    return -0.04


def _safe_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _clean_str(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


__all__ = [
    "SHADOW_CONTROLLER_SCHEMA_VERSION",
    "SHADOW_STRATEGY_ID",
    "ShadowCandidate",
    "ShadowRiskPolicy",
    "blocked_live_actions",
    "build_shadow_trading_report",
    "evaluate_market_row",
    "operator_next_step",
    "promotion_gates",
    "write_shadow_report",
]
