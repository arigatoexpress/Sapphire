"""Public-safe trading surface — rules & honesty, never wallets/positions."""

from __future__ import annotations

from typing import Any

from lib.grok.policy import FREE_REIGN_DEFAULTS, DEFAULT_DENS_SYMBOLS, DEFAULT_DUST_NO_REBUY
from lib.grok.playbooks import playbook_summary, TA_STACK
from lib.grok.blindspots import blindspot_scoreboard


def public_operating_rules() -> dict[str, Any]:
    """What the public site may honestly claim about how we trade."""
    fr = FREE_REIGN_DEFAULTS
    axti = fr.get("axti") or {}
    l2 = (fr.get("rails") or {}).get("rh_l2") or {}
    cap = fr.get("capital_preservation") or {}
    return {
        "schema": "sapphire-public-operating-rules/v1",
        "mandate": fr.get("mandate"),
        "disclosure": {
            "wallets": "withheld",
            "balances": "withheld",
            "exact_positions": "withheld",
            "order_ids": "withheld",
            "policy": (
                "Public surfaces show process truth, coarse bands, and operating rules — "
                "never exact capital, wallets, or broker positions."
            ),
        },
        "rails": {
            "rh_agentic": "options-first free-reign auto lane (defined-risk preferred)",
            "rh_l2": f"experimental ≤${l2.get('max_notional_usd', 10)} notional, max_open={l2.get('max_open', 1)}",
            "moss": "session grant required (hours_left > 0)",
            "paper": "research / shadow",
            "hyperliquid": "signing gate default disarmed",
        },
        "permanent_dens_symbols": sorted(DEFAULT_DENS_SYMBOLS),
        "dust_no_rebuy": sorted(DEFAULT_DUST_NO_REBUY),
        "axti": {
            "scale_out_multiple": axti.get("scale_out_multiple"),
            "hard_sl_fraction": axti.get("hard_sl_fraction"),
            "defined_risk_only": axti.get("defined_risk_only"),
            "dte_band_days": [axti.get("min_dte_days"), axti.get("max_dte_days")],
        },
        "capital_preservation": {
            "max_options_premium_usd_per_day": cap.get("max_options_premium_usd_per_day"),
            "max_realized_loss_usd_per_day": cap.get("max_realized_loss_usd_per_day"),
            "block_meme_l2_in_crisis": cap.get("block_meme_l2_in_crisis"),
        },
        "ta_stack": [x["id"] for x in TA_STACK],
        "playbooks": playbook_summary(),
        "honesty": {
            "prefer_not_observed_over_zero": True,
            "stale_desk_is_not_flat_pnl": True,
            "capability_route_active_is_not_fill": True,
        },
    }


def diagnose_public_payloads(
    *,
    live: dict[str, Any] | None,
    widgets: dict[str, Any] | None,
) -> dict[str, Any]:
    """Score scarcity / staleness without inventing numbers."""
    issues: list[dict[str, str]] = []
    live = live or {}
    widgets = widgets or {}

    desk = live.get("desk") if isinstance(live.get("desk"), dict) else {}
    markets = live.get("markets") if isinstance(live.get("markets"), dict) else {}
    summary = live.get("summary") if isinstance(live.get("summary"), dict) else {}

    if live.get("status") != "live":
        issues.append({"id": "LIVE_NOT_LIVE", "sev": "P0", "msg": " /api/v1/live status != live"})
    if desk.get("posture") in (None, "unknown") and desk.get("execution") in (None, "unknown"):
        issues.append(
            {
                "id": "DESK_STALE_EMPTY",
                "sev": "P0",
                "msg": "desk posture/execution unknown — trading intelligence looks empty",
            }
        )
    if markets.get("decision_gate") in (None, "unknown") and markets.get("execution") in (None, "unknown"):
        issues.append(
            {
                "id": "MARKETS_GATE_UNKNOWN",
                "sev": "P1",
                "msg": "markets.decision_gate/execution unknown despite feed activity",
            }
        )
    if markets.get("paper_strategies") is None:
        issues.append(
            {
                "id": "NO_PAPER_STRATEGIES",
                "sev": "P1",
                "msg": "paper_strategies null — research strategies not on wire",
            }
        )
    gate = widgets.get("gate") if isinstance(widgets.get("gate"), dict) else {}
    if gate.get("state") in ("unavailable", None):
        issues.append(
            {
                "id": "GATE_FILE_UNAVAILABLE",
                "sev": "P1",
                "msg": "widgets.gate unavailable on Cloud Run (no ops-state files) — expected unless signed projection",
            }
        )
    research = widgets.get("research") if isinstance(widgets.get("research"), dict) else {}
    if not research.get("clips"):
        issues.append(
            {
                "id": "RESEARCH_CLIPS_EMPTY",
                "sev": "P1",
                "msg": "research clips empty — no public research cycle on widgets path",
            }
        )
    if widgets.get("recent_signals") == []:
        issues.append(
            {
                "id": "SIGNALS_EMPTY",
                "sev": "P1",
                "msg": "recent_signals empty",
            }
        )
    wallet = widgets.get("wallet") if isinstance(widgets.get("wallet"), dict) else {}
    if wallet.get("disclosure") == "withheld":
        issues.append(
            {
                "id": "WALLET_WITHHELD_OK",
                "sev": "info",
                "msg": "wallet withheld — intentional public policy (not a bug)",
            }
        )

    return {
        "issue_count": len([i for i in issues if i["sev"] != "info"]),
        "issues": issues,
        "live_summary": summary,
        "live_status": live.get("status"),
        "desk_updated_at": desk.get("updated_at"),
        "markets_events_per_min": markets.get("events_per_min"),
        "active_agents": summary.get("active_agents"),
        "blindspots": blindspot_scoreboard(),
        "public_rules": public_operating_rules(),
    }
