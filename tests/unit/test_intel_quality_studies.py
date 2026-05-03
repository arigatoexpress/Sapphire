from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from lib.intel.quality_studies import (
    analyze_counterparty_leaderboard_stability,
    analyze_regime_stability,
    normalize_leaderboard_snapshots,
)
from scripts.ops import intel_quality_studies as cli

FROZEN_NOW = datetime(2026, 4, 28, 12, 0, tzinfo=UTC)


def _regime(label: str, confidence: float = 0.82, idx: int = 0) -> dict:
    return {
        "timestamp": f"2026-04-28T{idx:02d}:00:00+00:00",
        "label": label,
        "confidence": confidence,
        "drivers": ["fixture"],
    }


def _leaderboard(snapshot_id: str, rows: list[tuple[str, int, float]]) -> dict:
    return {
        "snapshot_id": snapshot_id,
        "generated_at": f"2026-04-28T{snapshot_id}:00:00+00:00",
        "leaderboard": [
            {
                "address": address,
                "rank": rank,
                "realized_pnl_30d_usd": pnl,
                "realized_pnl_90d_usd": pnl * 2,
                "sharpe_30d": 1.5,
            }
            for address, rank, pnl in rows
        ],
    }


def test_regime_stability_rewards_persistent_confident_labels() -> None:
    rows = [
        _regime("risk_on_correlated", 0.88, 0),
        _regime("risk_on_correlated", 0.86, 1),
        _regime("risk_on_correlated", 0.84, 2),
        _regime("risk_on_correlated", 0.87, 3),
        _regime("risk_off_flight_to_dollar", 0.80, 4),
        _regime("risk_off_flight_to_dollar", 0.82, 5),
        _regime("risk_off_flight_to_dollar", 0.81, 6),
    ]

    report = analyze_regime_stability(rows, generated_at=FROZEN_NOW)

    assert report.observations == 7
    assert report.transition_count == 1
    assert report.verdict == "stable"
    assert report.suggested_global_regime_weight > 1.0
    assert report.per_label_weights["risk_on_correlated"]["suggested_weight"] > 0.9


def test_regime_stability_penalizes_flicker_and_uncertainty() -> None:
    rows = [
        _regime("risk_on_correlated", 0.60, 0),
        _regime("risk_on_decorrelated", 0.52, 1),
        _regime("risk_on_correlated", 0.58, 2),
        _regime("regime_uncertain", 0.20, 3),
        _regime("risk_off_flight_to_dollar", 0.55, 4),
        _regime("regime_uncertain", 0.10, 5),
    ]

    report = analyze_regime_stability(rows, generated_at=FROZEN_NOW)

    assert report.verdict == "unstable"
    assert report.suggested_global_regime_weight < 0.85
    assert report.one_sample_flip_rate > 0.4
    assert report.per_label_weights["regime_uncertain"]["suggested_weight"] <= 0.5


def test_regime_stability_accepts_nested_snapshot_shape() -> None:
    report = analyze_regime_stability(
        [{"regime": _regime("risk_on_correlated", 0.9, 0)}],
        generated_at=FROZEN_NOW,
    )

    assert report.label_counts == {"risk_on_correlated": 1}


def test_counterparty_stability_identifies_stable_watchlist() -> None:
    snapshots = [
        _leaderboard("01", [("0xaaa", 1, 200000), ("0xbbb", 2, 150000), ("0xccc", 3, 120000)]),
        _leaderboard("02", [("0xaaa", 1, 210000), ("0xbbb", 3, 140000), ("0xddd", 2, 130000)]),
        _leaderboard("03", [("0xaaa", 2, 205000), ("0xbbb", 1, 155000), ("0xddd", 3, 125000)]),
    ]

    report = analyze_counterparty_leaderboard_stability(
        snapshots,
        top_n=3,
        generated_at=FROZEN_NOW,
    )

    assert report.snapshots == 3
    assert report.mean_adjacent_jaccard and report.mean_adjacent_jaccard > 0.45
    assert report.leaderboard_stability_score > 0.55
    assert {row.address for row in report.stable_watchlist} >= {"0xaaa", "0xbbb"}


def test_counterparty_stability_penalizes_churn() -> None:
    snapshots = [
        _leaderboard("01", [("0xaaa", 1, 200000), ("0xbbb", 2, 150000)]),
        _leaderboard("02", [("0xccc", 1, 210000), ("0xddd", 2, 140000)]),
        _leaderboard("03", [("0xeee", 1, 205000), ("0xfff", 2, 155000)]),
    ]

    report = analyze_counterparty_leaderboard_stability(
        snapshots,
        top_n=2,
        generated_at=FROZEN_NOW,
    )

    assert report.verdict == "unstable"
    assert report.mean_churn_rate == 1.0
    assert report.stable_watchlist == []


def test_normalize_leaderboard_snapshots_groups_jsonl_rows() -> None:
    rows = [
        {"snapshot_id": "a", "address": "0x1", "rank": 1, "realized_pnl_30d_usd": 100000},
        {"snapshot_id": "a", "address": "0x2", "rank": 2, "realized_pnl_30d_usd": 90000},
        {"snapshot_id": "b", "address": "0x1", "rank": 2, "realized_pnl_30d_usd": 110000},
    ]

    snapshots = normalize_leaderboard_snapshots(rows, top_n=2)

    assert len(snapshots) == 2
    assert snapshots[0].traders[0]["address"] == "0x1"


def test_cli_loads_jsonl_and_prints_regime_report(tmp_path: Path, capsys) -> None:
    path = tmp_path / "regimes.jsonl"
    path.write_text(
        "\n".join(json.dumps(_regime("risk_on_correlated", 0.9, idx)) for idx in range(3)) + "\n",
        encoding="utf-8",
    )

    rc = cli.main(["regime-stability", "--input", str(path)])
    captured = capsys.readouterr()

    assert rc == 0
    assert '"observations": 3' in captured.out
    assert '"suggested_global_regime_weight"' in captured.out


def test_cli_writes_counterparty_report(tmp_path: Path) -> None:
    path = tmp_path / "leaderboards.json"
    output = tmp_path / "report.json"
    path.write_text(
        json.dumps(
            [
                _leaderboard("01", [("0xaaa", 1, 200000), ("0xbbb", 2, 150000)]),
                _leaderboard("02", [("0xaaa", 1, 210000), ("0xbbb", 2, 155000)]),
            ]
        ),
        encoding="utf-8",
    )

    rc = cli.main(
        [
            "counterparty-stability",
            "--input",
            str(path),
            "--output",
            str(output),
            "--top-n",
            "2",
        ]
    )

    assert rc == 0
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["snapshots"] == 2
    assert payload["stable_watchlist"]
