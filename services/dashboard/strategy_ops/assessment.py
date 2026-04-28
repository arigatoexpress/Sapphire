from __future__ import annotations

import os
from typing import Any


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def build_strategy_ops_assessment(*, scorecard: dict, reject_tax: dict) -> dict:
    scorecard = scorecard if isinstance(scorecard, dict) else {}
    reject_tax = reject_tax if isinstance(reject_tax, dict) else {}
    totals = scorecard.get("totals", {}) if isinstance(scorecard.get("totals"), dict) else {}
    ranked = scorecard.get("ranked", []) if isinstance(scorecard.get("ranked"), list) else []

    sample_size = int(reject_tax.get("sample_size") or totals.get("sample_size") or 0)
    reject_tax_pct = _as_float(
        reject_tax.get("reject_tax_pct", totals.get("reject_tax_pct", 0.0)),
        0.0,
    )
    hard_fail_pct = _as_float(
        reject_tax.get("hard_fail_pct", totals.get("hard_fail_pct", 0.0)),
        0.0,
    )
    min_sample = max(1, int(_as_float(os.getenv("STRATEGY_OPS_GONOGO_MIN_SAMPLE_SIZE", "30"), 30)))
    max_reject = max(
        0.0,
        min(100.0, _as_float(os.getenv("STRATEGY_OPS_GONOGO_MAX_REJECT_TAX_PCT", "70"), 70.0)),
    )
    max_hard_fail = max(
        0.0,
        min(100.0, _as_float(os.getenv("STRATEGY_OPS_GONOGO_MAX_HARD_FAIL_PCT", "10"), 10.0)),
    )

    reasons = []
    if sample_size < min_sample:
        reasons.append(f"sample_size {sample_size} < {min_sample}")
    if reject_tax_pct > max_reject:
        reasons.append(f"reject_tax {reject_tax_pct:.1f}% > {max_reject:.1f}%")
    if hard_fail_pct > max_hard_fail:
        reasons.append(f"hard_fail {hard_fail_pct:.1f}% > {max_hard_fail:.1f}%")

    promote_lanes = [
        row for row in ranked if str((row or {}).get("recommendation", "")).lower() == "promote"
    ]
    top_promote = promote_lanes[0] if promote_lanes else None
    go = len(reasons) == 0
    return {
        "go": bool(go),
        "label": "GO" if go else "NO-GO",
        "reasons": reasons,
        "sample_size": sample_size,
        "reject_tax_pct": round(reject_tax_pct, 2),
        "hard_fail_pct": round(hard_fail_pct, 2),
        "promote_candidates": len(promote_lanes),
        "top_promote_lane": (
            f"{top_promote.get('strategy', 'unknown')}@{top_promote.get('timeframe', 'unknown')}"
            if isinstance(top_promote, dict)
            else ""
        ),
        "thresholds": {
            "min_sample_size": min_sample,
            "max_reject_tax_pct": round(max_reject, 2),
            "max_hard_fail_pct": round(max_hard_fail, 2),
        },
    }
