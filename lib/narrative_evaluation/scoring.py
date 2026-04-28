"""Pure scoring primitives for NarrativeThesis outcome evaluation."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

DEFAULT_HORIZONS_HOURS: tuple[int, ...] = (6, 24)
GENERATOR = "lib.narrative_evaluation.scoring"
VERSION = "0.1.0"

_LONG = {"long_strong", "long_mild"}
_SHORT = {"short_strong", "short_mild"}
_NEUTRAL = {"neutral", "no_position"}


@dataclass(frozen=True)
class EvaluationOutcome:
    """Actual realized outcome for one thesis horizon."""

    symbol: str
    timeframe: str
    observed_at: str
    actual_return_pct: float
    source: str = "inline"
    regime: str = "unknown"
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class NarrativeEvaluationScore:
    """Deterministic score row for one thesis/horizon pair."""

    score_id: str
    thesis_id: str
    symbol: str
    timeframe: str
    horizon_hours: int
    generated_at: str
    due_at: str
    scored_at: str
    implied_position: str
    predicted_direction: int
    confidence: float
    edge_score: float | None
    edge_bucket: str
    source_mix: str
    source_count: int
    regime: str
    outcome_observed_at: str | None
    actual_return_pct: float | None
    actual_direction: int | None
    correct: bool | None
    false_positive: bool
    calibration_error: float | None
    brier_score: float | None
    status: str
    diagnostics: list[str]
    provenance_envelope: dict[str, Any]
    version: str = VERSION

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _canonical_hash(value: Any, *, length: int = 32) -> str:
    blob = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:length]


def _parse_ts(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value.astimezone(UTC)
    if not value:
        return None
    text = str(value).strip().replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(text).astimezone(UTC)
    except ValueError:
        return None


def _iso(dt: datetime) -> str:
    return dt.astimezone(UTC).replace(microsecond=0).isoformat()


def _float(value: Any) -> float | None:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _thesis_payload(row_or_thesis: Mapping[str, Any]) -> dict[str, Any]:
    row = dict(row_or_thesis)
    thesis = row.get("thesis")
    if isinstance(thesis, Mapping):
        merged = dict(thesis)
        for key in ("symbol", "timeframe", "generated_at", "mode_actual"):
            if key in row and not merged.get(key):
                merged[key] = row[key]
        if isinstance(row.get("source_signal"), Mapping):
            merged["_source_signal"] = dict(row["source_signal"])
        return merged
    return row


def _sources(thesis: Mapping[str, Any]) -> list[str]:
    prov = thesis.get("provenance_envelope")
    raw = prov.get("corroborated_by") if isinstance(prov, Mapping) else None
    if raw is None and isinstance(thesis.get("_source_signal"), Mapping):
        raw = thesis["_source_signal"].get("corroborated_by")
    if isinstance(raw, str):
        return [raw]
    if isinstance(raw, list):
        return sorted({str(item) for item in raw if str(item).strip()})
    evidence = thesis.get("evidence_bullets") or []
    if isinstance(evidence, list):
        found = []
        for item in evidence:
            text = str(item).lower()
            for name in ("tradingview", "telegram", "hyperliquid", "threat", "kronos", "scanner", "sovereign"):
                if name in text:
                    found.append(name)
        return sorted(set(found))
    return []


def _edge_score(thesis: Mapping[str, Any]) -> float | None:
    if isinstance(thesis.get("_source_signal"), Mapping):
        value = _float(thesis["_source_signal"].get("edge_score"))
        if value is not None:
            return value
    prov = thesis.get("provenance_envelope")
    if isinstance(prov, Mapping):
        value = _float(prov.get("edge_score"))
        if value is not None:
            return value
    return None


def edge_bucket(edge: float | None) -> str:
    if edge is None:
        return "unknown"
    if edge >= 0.65:
        return "strong_long"
    if edge > 0.2:
        return "mild_long"
    if edge <= -0.65:
        return "strong_short"
    if edge < -0.2:
        return "mild_short"
    return "flat"


def predicted_direction(position: str) -> int:
    if position in _LONG:
        return 1
    if position in _SHORT:
        return -1
    return 0


def actual_direction(actual_return_pct: float, *, neutral_band_pct: float = 0.05) -> int:
    if actual_return_pct > neutral_band_pct:
        return 1
    if actual_return_pct < -neutral_band_pct:
        return -1
    return 0


def _confidence(thesis: Mapping[str, Any]) -> float:
    value = _float(thesis.get("confidence"))
    if value is None:
        return 0.5
    return round(max(0.0, min(1.0, value)), 4)


def _coerce_outcome(outcome: Mapping[str, Any] | EvaluationOutcome | None) -> EvaluationOutcome | None:
    if outcome is None:
        return None
    raw = outcome.to_dict() if isinstance(outcome, EvaluationOutcome) else dict(outcome)
    actual = None
    for key in ("actual_return_pct", "return_pct", "pnl_pct", "move_pct"):
        actual = _float(raw.get(key))
        if actual is not None:
            break
    observed = raw.get("observed_at") or raw.get("timestamp") or raw.get("closed_at") or raw.get("generated_at")
    if actual is None or not observed:
        return None
    return EvaluationOutcome(
        symbol=str(raw.get("symbol") or "").upper(),
        timeframe=str(raw.get("timeframe") or "unknown").lower(),
        observed_at=_iso(_parse_ts(observed) or datetime.now(UTC)),
        actual_return_pct=actual,
        source=str(raw.get("source") or "inline"),
        regime=str(raw.get("regime") or raw.get("market_regime") or "unknown"),
        metadata={k: v for k, v in raw.items() if k not in {"symbol", "timeframe", "observed_at", "actual_return_pct"}},
    )


def score_thesis(
    thesis_or_row: Mapping[str, Any],
    outcome: Mapping[str, Any] | EvaluationOutcome | None,
    *,
    horizon_hours: int = 24,
    scored_at: datetime | None = None,
    neutral_band_pct: float = 0.05,
) -> NarrativeEvaluationScore:
    """Score one NarrativeThesis against one actual outcome.

    The function has no filesystem, network, model, or trading side effects.
    Missing or immature outcomes are represented honestly with ``status`` and
    ``correct=None`` so callers can persist pending rows without fake accuracy.
    """
    thesis = _thesis_payload(thesis_or_row)
    symbol = str(thesis.get("symbol") or "UNKNOWN").upper()
    timeframe = str(thesis.get("timeframe") or "unknown").lower()
    generated = _parse_ts(thesis.get("generated_at")) or datetime.now(UTC)
    horizon = max(1, int(horizon_hours))
    due = generated + timedelta(hours=horizon)
    scored = scored_at or datetime.now(UTC)
    position = str(thesis.get("implied_position") or "no_position")
    pred = predicted_direction(position)
    conf = _confidence(thesis)
    edge = _edge_score(thesis)
    sources = _sources(thesis)
    source_mix = "+".join(sources) if sources else "unknown"
    thesis_id = _canonical_hash(
        {
            "symbol": symbol,
            "timeframe": timeframe,
            "generated_at": _iso(generated),
            "implied_position": position,
            "thesis": thesis.get("thesis_one_paragraph"),
        }
    )
    score_id = _canonical_hash({"thesis_id": thesis_id, "horizon_hours": horizon})
    actual = _coerce_outcome(outcome)
    diagnostics: list[str] = []
    status = "scored"
    observed_at = None
    actual_ret = None
    actual_dir = None
    correct = None
    false_positive = False
    cal_error = None
    brier = None
    regime = "unknown"

    if scored < due:
        status = "pending_horizon"
        diagnostics.append("horizon_not_elapsed")
    elif actual is None:
        status = "no_outcome"
        diagnostics.append("no_matching_actual_outcome")
    else:
        observed_at = actual.observed_at
        actual_ret = round(actual.actual_return_pct, 6)
        actual_dir = actual_direction(actual.actual_return_pct, neutral_band_pct=neutral_band_pct)
        regime = actual.regime
        if pred == 0:
            correct = actual_dir == 0
        else:
            correct = pred == actual_dir
        false_positive = pred != 0 and actual_dir != pred
        outcome_prob = 1.0 if correct else 0.0
        cal_error = round(abs(conf - outcome_prob), 6)
        brier = round((conf - outcome_prob) ** 2, 6)
        if false_positive:
            diagnostics.append("false_positive_directional_thesis")
        if pred == 0 and actual_dir != 0:
            diagnostics.append("missed_directional_move")
        if conf >= 0.75 and correct is False:
            diagnostics.append("overconfident_miss")
        if conf <= 0.35 and correct is True:
            diagnostics.append("underconfident_hit")

    envelope = {
        "generator": GENERATOR,
        "version": VERSION,
        "thesis_hash": _canonical_hash(thesis, length=64),
        "outcome_hash": _canonical_hash(actual.to_dict(), length=64) if actual else None,
        "scored_at": _iso(scored),
        "dry_run": True,
    }
    return NarrativeEvaluationScore(
        score_id=score_id,
        thesis_id=thesis_id,
        symbol=symbol,
        timeframe=timeframe,
        horizon_hours=horizon,
        generated_at=_iso(generated),
        due_at=_iso(due),
        scored_at=_iso(scored),
        implied_position=position,
        predicted_direction=pred,
        confidence=conf,
        edge_score=round(edge, 6) if edge is not None else None,
        edge_bucket=edge_bucket(edge),
        source_mix=source_mix,
        source_count=len(sources),
        regime=regime,
        outcome_observed_at=observed_at,
        actual_return_pct=actual_ret,
        actual_direction=actual_dir,
        correct=correct,
        false_positive=false_positive,
        calibration_error=cal_error,
        brier_score=brier,
        status=status,
        diagnostics=diagnostics,
        provenance_envelope=envelope,
    )
