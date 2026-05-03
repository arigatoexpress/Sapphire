"""Tests for narrative self-evaluation scoring and service idempotence."""

from __future__ import annotations

import json
from datetime import UTC, datetime

from lib.narrative_evaluation import (
    aggregate_scores,
    calibration_report,
    diagnostics_report,
    score_thesis,
)
from services.narrative_evaluation import run as service

NOW = datetime(2026, 4, 29, 12, 0, 0, tzinfo=UTC)


def _thesis(position: str = "long_strong", confidence: float = 0.82) -> dict:
    return {
        "symbol": "BTC",
        "timeframe": "1h",
        "generated_at": "2026-04-28T12:00:00+00:00",
        "implied_position": position,
        "confidence": confidence,
        "thesis_one_paragraph": "BTC 1h source tradingview edge_score 0.72.",
        "provenance_envelope": {
            "corroborated_by": ["tradingview", "kronos_forecast"],
            "edge_score": 0.72,
        },
    }


def _outcome(return_pct: float = 1.4) -> dict:
    return {
        "symbol": "BTC",
        "timeframe": "1h",
        "observed_at": "2026-04-29T12:00:00+00:00",
        "actual_return_pct": return_pct,
        "regime": "risk_on",
    }


def test_score_thesis_marks_directional_hit() -> None:
    score = score_thesis(_thesis(), _outcome(), horizon_hours=24, scored_at=NOW).to_dict()
    assert score["status"] == "scored"
    assert score["correct"] is True
    assert score["false_positive"] is False
    assert score["edge_bucket"] == "strong_long"
    assert score["source_mix"] == "kronos_forecast+tradingview"


def test_score_thesis_reports_false_positive_and_calibration() -> None:
    score = score_thesis(_thesis(), _outcome(-1.0), horizon_hours=24, scored_at=NOW).to_dict()
    assert score["correct"] is False
    assert score["false_positive"] is True
    assert "false_positive_directional_thesis" in score["diagnostics"]
    assert "overconfident_miss" in score["diagnostics"]
    assert score["calibration_error"] == 0.82


def test_score_thesis_keeps_unelapsed_horizon_out_of_accuracy() -> None:
    score = score_thesis(_thesis(), _outcome(), horizon_hours=48, scored_at=NOW).to_dict()
    assert score["status"] == "pending_horizon"
    assert score["correct"] is None


def test_score_thesis_scores_zero_return_as_neutral_outcome() -> None:
    score = score_thesis(
        _thesis("neutral", 0.55), _outcome(0.0), horizon_hours=24, scored_at=NOW
    ).to_dict()
    assert score["status"] == "scored"
    assert score["actual_return_pct"] == 0.0
    assert score["correct"] is True


def test_aggregates_diagnostics_and_calibration() -> None:
    rows = [
        score_thesis(_thesis(), _outcome(), horizon_hours=24, scored_at=NOW).to_dict(),
        score_thesis(
            _thesis("short_mild", 0.8), _outcome(), horizon_hours=24, scored_at=NOW
        ).to_dict(),
    ]
    agg = aggregate_scores(rows, group_by="symbol")
    assert agg["groups"]["BTC"]["scored"] == 2
    assert agg["groups"]["BTC"]["accuracy"] == 0.5
    diag = diagnostics_report(rows)
    assert len(diag["false_positives"]) == 1
    cal = calibration_report(rows)
    assert cal["overall"]["avg_brier_score"] is not None


def test_service_run_once_is_idempotent(tmp_path) -> None:
    output_root = tmp_path / "eval"
    first = service.run_once(
        output_root=output_root,
        narratives=[{"thesis": _thesis()}],
        outcomes=[_outcome()],
        horizons_hours=(24,),
        now=NOW,
    )
    second = service.run_once(
        output_root=output_root,
        narratives=[{"thesis": _thesis()}],
        outcomes=[_outcome()],
        horizons_hours=(24,),
        now=NOW,
    )
    assert first["scores_written"] == 1
    assert second["scores_written"] == 0
    path = output_root / "2026-04-29" / "scores.jsonl"
    assert path.exists()
    assert path.with_name("scores.jsonl.envelope.json").exists()
    assert len([line for line in path.read_text(encoding="utf-8").splitlines() if line]) == 1
    row = json.loads(path.read_text(encoding="utf-8").splitlines()[0])
    assert row["provenance_envelope"]["dry_run"] is True
