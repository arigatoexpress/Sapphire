from __future__ import annotations

from typing import Any


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def resolve_strategy_ops_decision(
    *,
    assessment: dict | None,
    operator_brief: dict | None,
    data_quality: dict | None,
) -> dict:
    assessment = assessment if isinstance(assessment, dict) else {}
    operator_brief = operator_brief if isinstance(operator_brief, dict) else {}
    data_quality = data_quality if isinstance(data_quality, dict) else {}

    assessment_go = bool(assessment.get("go", False))
    assessment_label = str(assessment.get("label", "NO-GO")).upper()
    assessment_reasons = assessment.get("reasons", []) if isinstance(assessment.get("reasons"), list) else []

    operator_go = bool(operator_brief.get("go", assessment_go))
    operator_label = str(operator_brief.get("label", "GO" if operator_go else "NO-GO")).upper()
    operator_reasons = (
        operator_brief.get("hard_blockers", [])
        if isinstance(operator_brief.get("hard_blockers"), list)
        else []
    )

    reasons = [str(r).strip() for r in (operator_reasons or assessment_reasons) if str(r).strip()]
    degraded = bool(data_quality.get("degraded", False))
    degraded_sources = (
        data_quality.get("degraded_sources", [])
        if isinstance(data_quality.get("degraded_sources"), list)
        else []
    )
    if degraded and operator_go:
        has_quality_reason = any("data_quality" in reason.lower() for reason in reasons)
        if not has_quality_reason:
            degraded_text = ", ".join(str(src) for src in degraded_sources[:3]) or "unknown sources"
            reasons.append(f"data_quality degraded: {degraded_text}")
        operator_go = False
        operator_label = "NO-GO"

    go = bool(operator_go and len(reasons) == 0)
    label = "GO" if go else "NO-GO"
    source = "operator_brief" if operator_brief else "assessment"
    confidence_score = _as_float(operator_brief.get("confidence_score"), 0.0)
    confidence_multiplier = _as_float(
        operator_brief.get("confidence_multiplier"),
        _as_float(data_quality.get("confidence_multiplier"), 1.0),
    )

    return {
        "go": go,
        "label": label,
        "source": source,
        "diverged": bool(assessment_label != label or assessment_go != go or operator_label != label),
        "assessment_label": assessment_label,
        "assessment_go": assessment_go,
        "operator_label": operator_label,
        "operator_go": operator_go,
        "reasons": reasons[:8],
        "why_this_matters_now": str(operator_brief.get("why_this_matters_now", "")).strip(),
        "confidence_score": round(confidence_score, 2),
        "confidence_multiplier": round(confidence_multiplier, 4),
        "data_quality_degraded": degraded,
        "degraded_sources": degraded_sources[:5],
    }


def build_go_no_go_brief_payload(*, ops_payload: dict, window_days: int, timestamp: str) -> dict:
    decision = ops_payload.get("decision", {}) if isinstance(ops_payload.get("decision"), dict) else {}
    operator_brief = (
        ops_payload.get("operator_brief", {}) if isinstance(ops_payload.get("operator_brief"), dict) else {}
    )
    assessment = ops_payload.get("assessment", {}) if isinstance(ops_payload.get("assessment"), dict) else {}
    data_quality = ops_payload.get("data_quality", {}) if isinstance(ops_payload.get("data_quality"), dict) else {}
    reject_tax = ops_payload.get("reject_tax", {}) if isinstance(ops_payload.get("reject_tax"), dict) else {}
    attribution = ops_payload.get("attribution", {}) if isinstance(ops_payload.get("attribution"), dict) else {}
    scorecard = ops_payload.get("scorecard", {}) if isinstance(ops_payload.get("scorecard"), dict) else {}

    blocker_rows = decision.get("reasons", []) if isinstance(decision.get("reasons"), list) else []
    if not blocker_rows:
        blocker_rows = (
            operator_brief.get("hard_blockers", [])
            if isinstance(operator_brief.get("hard_blockers"), list)
            else []
        )
    action_rows = operator_brief.get("top_actions", []) if isinstance(operator_brief.get("top_actions"), list) else []

    summary = {
        "decision_label": str(decision.get("label", "NO-GO")).upper(),
        "decision_go": bool(decision.get("go", False)),
        "decision_source": str(decision.get("source", "assessment")),
        "decision_diverged": bool(decision.get("diverged", False)),
        "confidence_score": round(_as_float(decision.get("confidence_score"), 0.0), 4),
        "confidence_multiplier": round(_as_float(decision.get("confidence_multiplier"), 1.0), 4),
        "sample_size": int(reject_tax.get("sample_size", 0) or 0),
        "reject_tax_pct": round(_as_float(reject_tax.get("reject_tax_pct"), 0.0), 2),
        "hard_fail_pct": round(_as_float(reject_tax.get("hard_fail_pct"), 0.0), 2),
        "net_pnl_after_fees": round(_as_float(attribution.get("net_pnl_after_fees"), 0.0), 6),
        "fill_rate_pct": round(_as_float(attribution.get("filled_success_pct"), 0.0), 2),
        "expected_value_error_pct": round(_as_float(attribution.get("expected_value_error_pct"), 0.0), 2),
        "max_drawdown_pct": round(_as_float(attribution.get("max_drawdown_pct"), 0.0), 2),
    }

    return {
        "timestamp": timestamp,
        "window_days": window_days,
        "summary": summary,
        "decision": decision,
        "assessment": assessment,
        "data_quality": data_quality,
        "why_this_matters_now": str(operator_brief.get("why_this_matters_now", "")).strip(),
        "hard_blockers": blocker_rows,
        "top_actions": action_rows[:3],
        "top_lanes": (scorecard.get("ranked", []) if isinstance(scorecard.get("ranked"), list) else [])[:3],
        "sources": {
            "strategy_ops": "/api/platform/strategy-ops",
            "agent_context": "/api/platform/agent-context",
        },
    }

