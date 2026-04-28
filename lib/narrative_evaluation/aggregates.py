"""Rolling aggregate and diagnostic reports for narrative evaluations."""

from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime
from typing import Any

GROUP_FIELDS = ("symbol", "timeframe", "edge_bucket", "source_mix", "regime")


def _rows(scores: list[dict[str, Any]] | tuple[dict[str, Any], ...]) -> list[dict[str, Any]]:
    return [dict(row) for row in scores if isinstance(row, dict)]


def _metric(rows: list[dict[str, Any]]) -> dict[str, Any]:
    scored = [r for r in rows if r.get("correct") is not None]
    correct = [r for r in scored if r.get("correct") is True]
    false_positive = [r for r in scored if r.get("false_positive") is True]
    confidence = [float(r.get("confidence") or 0.0) for r in scored]
    returns = [float(r["actual_return_pct"]) for r in scored if r.get("actual_return_pct") is not None]
    cal = [float(r["calibration_error"]) for r in scored if r.get("calibration_error") is not None]
    brier = [float(r["brier_score"]) for r in scored if r.get("brier_score") is not None]
    return {
        "total": len(rows),
        "scored": len(scored),
        "pending": sum(1 for r in rows if r.get("status") == "pending_horizon"),
        "no_outcome": sum(1 for r in rows if r.get("status") == "no_outcome"),
        "correct": len(correct),
        "accuracy": round(len(correct) / len(scored), 6) if scored else None,
        "false_positives": len(false_positive),
        "false_positive_rate": round(len(false_positive) / len(scored), 6) if scored else None,
        "avg_confidence": round(sum(confidence) / len(confidence), 6) if confidence else None,
        "avg_actual_return_pct": round(sum(returns) / len(returns), 6) if returns else None,
        "avg_calibration_error": round(sum(cal) / len(cal), 6) if cal else None,
        "avg_brier_score": round(sum(brier) / len(brier), 6) if brier else None,
    }


def aggregate_scores(scores: list[dict[str, Any]], *, group_by: str | None = None) -> dict[str, Any]:
    rows = _rows(scores)
    generated_at = datetime.now(UTC).replace(microsecond=0).isoformat()
    if group_by is None:
        return {"generated_at": generated_at, "group_by": "overall", "overall": _metric(rows)}
    if group_by not in GROUP_FIELDS:
        raise ValueError(f"unsupported group_by '{group_by}'")
    buckets: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        buckets[str(row.get(group_by) or "unknown")].append(row)
    return {
        "generated_at": generated_at,
        "group_by": group_by,
        "groups": {
            key: {"key": key, **_metric(bucket)}
            for key, bucket in sorted(buckets.items())
        },
    }


def summary_report(scores: list[dict[str, Any]]) -> dict[str, Any]:
    rows = _rows(scores)
    return {
        "ok": True,
        "generated_at": datetime.now(UTC).replace(microsecond=0).isoformat(),
        "overall": _metric(rows),
        "by_symbol": aggregate_scores(rows, group_by="symbol")["groups"],
        "by_timeframe": aggregate_scores(rows, group_by="timeframe")["groups"],
        "by_edge_bucket": aggregate_scores(rows, group_by="edge_bucket")["groups"],
        "recent": sorted(rows, key=lambda r: r.get("scored_at") or "", reverse=True)[:20],
    }


def diagnostics_report(scores: list[dict[str, Any]], *, limit: int = 20) -> dict[str, Any]:
    rows = _rows(scores)
    false_positive = [r for r in rows if r.get("false_positive") is True]
    overconfident = [
        r for r in rows
        if "overconfident_miss" in (r.get("diagnostics") or [])
    ]
    pending = [r for r in rows if r.get("status") in {"pending_horizon", "no_outcome"}]
    return {
        "ok": True,
        "generated_at": datetime.now(UTC).replace(microsecond=0).isoformat(),
        "summary": _metric(rows),
        "false_positives": sorted(
            false_positive,
            key=lambda r: (r.get("confidence") or 0, abs(float(r.get("actual_return_pct") or 0))),
            reverse=True,
        )[:limit],
        "overconfident_misses": sorted(
            overconfident,
            key=lambda r: r.get("confidence") or 0,
            reverse=True,
        )[:limit],
        "unscored": sorted(pending, key=lambda r: r.get("due_at") or "", reverse=True)[:limit],
    }


def calibration_report(scores: list[dict[str, Any]]) -> dict[str, Any]:
    rows = [r for r in _rows(scores) if r.get("correct") is not None]
    buckets: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        conf = float(row.get("confidence") or 0.0)
        low = min(9, int(conf * 10)) / 10
        buckets[f"{low:.1f}-{low + 0.1:.1f}"].append(row)
    return {
        "ok": True,
        "generated_at": datetime.now(UTC).replace(microsecond=0).isoformat(),
        "buckets": {key: _metric(bucket) for key, bucket in sorted(buckets.items())},
        "overall": _metric(rows),
    }
