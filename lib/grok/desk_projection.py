"""Sovereign desk projection for public telemetry — plant fills, public never invents.

Produces a *candidate* desk block matching sapphire-alpha-dashboard live_telemetry
semantic shape. Plant publishers should merge this with real local observations.
Never includes wallets, balances, positions, or order ids.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

from lib.grok.genome import LessonBook
from lib.grok.policy import FREE_REIGN_DEFAULTS
from lib.grok.public_surface import public_operating_rules
from lib.grok.windows import evaluate_windows_acceptance


def _utc() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def build_desk_projection(
    *,
    posture: str = "capital_preservation",
    execution: str = "gated",
    regime_label: str = "unknown",
    thesis: str | None = None,
    win_state: Mapping[str, Any] | None = None,
    genome_path: Any | None = None,
    free_reign_armed: bool | None = None,
    moss_grant_hours_left: float | None = None,
    day_realized_pnl_usd: float | None = None,
    observed_extras: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a desk block. Prefer real plant observations via observed_extras."""
    now = _utc()
    win = evaluate_windows_acceptance(dict(win_state or {}))
    book = LessonBook()
    if genome_path is not None:
        try:
            book = LessonBook.load(genome_path)
        except Exception:  # noqa: BLE001
            book = LessonBook()
    gsum = book.summary()

    # Safety floor from monorepo truth + optional plant facts
    floor = {
        "gate_valid": True,  # monorepo policy kernel present
        "pause_clear": None,  # plant must set from pause files
        "ledger": "unknown",
        "bounded_policy": True,
        "notes": [
            "policy kernel: free_reign_multi_rail",
            f"l2_cap_usd: {(FREE_REIGN_DEFAULTS.get('rails') or {}).get('rh_l2', {}).get('max_notional_usd')}",
            "public: no wallets/positions on this projection",
        ],
    }
    if free_reign_armed is False:
        floor["notes"].append("free_reign_process: not_confirmed_live")
    if moss_grant_hours_left is not None:
        floor["notes"].append(
            "moss_grant: active" if moss_grant_hours_left > 0 else "moss_grant: expired"
        )

    risk = {
        "ledger_state": "unknown",
        "realized_drawdown_pct": None,
        "drawdown_limit_pct": None,
        "budget_remaining_pct": None,
        "new_risk": "restricted" if posture == "capital_preservation" else "unknown",
    }
    if day_realized_pnl_usd is not None:
        # only coarse signal — not a public PnL display number
        risk["day_pnl_sign"] = (
            "pos" if day_realized_pnl_usd > 0 else "neg" if day_realized_pnl_usd < 0 else "flat"
        )

    desk: dict[str, Any] = {
        "version": 1,
        "updated_at": now,
        "posture": posture if posture in {
            "capital_preservation", "selective_risk", "risk_seeking", "neutral", "unknown",
        } else "unknown",
        "leader": "unknown",
        "validation": {
            "oos_pass": None,
            "oos_total": None,
            "conflicts": None,
            "conflict_details": [],
            "replay_span_hours": None,
            "replay_data_through": None,
        },
        "decisions": {
            "pending": None,
            "pending_review": None,
            "approved_awaiting_execution": None,
            "eligible_execution": None,
            "blocked": None,
            "pending_policy_blocked": None,
        },
        "execution": execution if execution in {
            "halted", "off", "gated", "paper", "unknown",
        } else "unknown",
        "feeds": {"fresh": None, "total": None},
        "tracks": [],
        "risk": risk,
        "experiment": {
            "status": "unknown",
            "qualified_days": None,
            "required_days": None,
            "last_committed_date": None,
            "collector": "unknown",
        },
        "epistemics": {
            "updated_ts": now,
            "fresh": bool(thesis) or regime_label != "unknown",
            "thesis": thesis,
            "regime": {
                "label": regime_label,
                "fit": None,
                "data_quality": None,
                "drivers": [],
            },
            "falsifiers": [],
            "learning": {
                "status": "available" if gsum.get("count", 0) else "unavailable",
                "lesson_count": gsum.get("count"),
                "wins": gsum.get("wins"),
                "losses": gsum.get("losses"),
                # never publish realized_pnl_usd on public desk
            },
        },
        "autonomy": {
            "free_reign_mandate": FREE_REIGN_DEFAULTS.get("mandate"),
            "gate_scope": "via_free_reign_only",
            "windows_arm_l2_allowed": win.get("arm_l2_allowed"),
        },
        "safety_floor": floor,
        "operating_rules_ref": public_operating_rules()["schema"],
        "provenance": {
            "builder": "lib.grok.desk_projection",
            "note": "plant must overwrite unknowns with local observations; never invent fills",
        },
    }
    if observed_extras:
        # shallow merge allowed keys only
        for k, v in observed_extras.items():
            if k in desk and isinstance(desk[k], dict) and isinstance(v, dict):
                desk[k] = {**desk[k], **v}
            elif k in desk:
                desk[k] = v
    return desk


def markets_pulse(
    *,
    events_per_min: float | None = None,
    feed_age_s: float | None = None,
    decision_gate: str = "unknown",
    execution: str = "unknown",
    network: str = "Robinhood Chain",
) -> dict[str, Any]:
    return {
        "network": network,
        "status": "current" if feed_age_s is not None and feed_age_s < 120 else "unknown",
        "feed_age_s": feed_age_s,
        "events_per_min": events_per_min,
        "paper_strategies": None,
        "decision_gate": decision_gate if decision_gate in {"manual", "off", "unknown"} else "unknown",
        "execution": execution if execution in {"off", "paper", "gated", "halted", "unknown"} else "unknown",
    }


def publisher_checklist() -> list[str]:
    return [
        "Load desk from build_desk_projection() each cycle",
        "Set updated_at to now every publish (never reuse stale desk blob)",
        "Overwrite safety_floor.pause_clear from real pause files",
        "Set markets.decision_gate/execution from free-reign + pause truth",
        "Omit wallets/balances/positions/order_ids always",
        "If field unknown: explicit unknown — do not zero-fill PnL",
        "Verify curl https://sapphirealpha.xyz/api/v1/live desk.updated_at age < 3m",
    ]
