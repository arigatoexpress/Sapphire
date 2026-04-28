from __future__ import annotations

from datetime import UTC, datetime

from lib.cross_asset.correlation_matrix import MethodMatrix
from lib.cross_asset.regime_detector import REGIME_LABELS, detect_regime, label_regime_history

FROZEN_NOW = datetime(2026, 4, 28, 12, 0, tzinfo=UTC)
ASSETS = ["BTC", "ETH", "SOL", "SPY", "QQQ", "DXY", "XAUUSD", "VIX"]


def _matrix(default: float | None = 0.0, overrides: dict[tuple[str, str], float] | None = None) -> MethodMatrix:
    overrides = overrides or {}
    values = [[1.0 if i == j else default for j in range(len(ASSETS))] for i in range(len(ASSETS))]
    index = {asset: idx for idx, asset in enumerate(ASSETS)}
    for (left, right), value in overrides.items():
        i = index[left]
        j = index[right]
        values[i][j] = values[j][i] = value
    return MethodMatrix(
        method="pearson",
        window="7d",
        observations=168,
        min_observations=30,
        assets=list(ASSETS),
        matrix=values,
        sample_counts=[[168 for _ in ASSETS] for _ in ASSETS],
    )


def _risk_overrides(value: float) -> dict[tuple[str, str], float]:
    risk = ["BTC", "ETH", "SOL", "SPY", "QQQ"]
    return {(risk[i], risk[j]): value for i in range(len(risk)) for j in range(i + 1, len(risk))}


def _risk_dollar_overrides(value: float) -> dict[tuple[str, str], float]:
    return {(risk, dollar): value for risk in ["BTC", "ETH", "SOL", "SPY", "QQQ"] for dollar in ["DXY"]}


def test_label_set_contains_all_lane_regimes() -> None:
    assert set(REGIME_LABELS) == {
        "risk_on_correlated",
        "risk_on_decorrelated",
        "risk_off_flight_to_dollar",
        "crisis_correlation_spike",
        "regime_uncertain",
    }


def test_detects_risk_on_correlated() -> None:
    label = detect_regime(_matrix(overrides=_risk_overrides(0.72)), timestamp=FROZEN_NOW)
    assert label.label == "risk_on_correlated"
    assert label.confidence > 0.7


def test_detects_risk_on_decorrelated() -> None:
    label = detect_regime(_matrix(overrides=_risk_overrides(0.22)), timestamp=FROZEN_NOW)
    assert label.label == "risk_on_decorrelated"


def test_detects_risk_off_flight_to_dollar() -> None:
    overrides = _risk_overrides(0.50)
    overrides.update(_risk_dollar_overrides(-0.62))
    label = detect_regime(_matrix(overrides=overrides), timestamp=FROZEN_NOW)
    assert label.label == "risk_off_flight_to_dollar"
    assert "risk assets moving against dollar bloc" in label.drivers


def test_detects_crisis_correlation_spike_from_broad_abs() -> None:
    label = detect_regime(_matrix(default=0.82), timestamp=FROZEN_NOW)
    assert label.label == "crisis_correlation_spike"


def test_detects_uncertain_on_sparse_matrix() -> None:
    sparse = MethodMatrix(
        method="pearson",
        window="7d",
        observations=168,
        min_observations=30,
        assets=["BTC", "ETH"],
        matrix=[[1.0, None], [None, 1.0]],
        sample_counts=[[10, 0], [0, 10]],
    )
    label = detect_regime(sparse, timestamp=FROZEN_NOW)
    assert label.label == "regime_uncertain"
    assert label.metrics["observed_pairs"] == 0


def test_none_matrix_returns_uncertain() -> None:
    label = detect_regime(None, timestamp=FROZEN_NOW)
    assert label.label == "regime_uncertain"
    assert label.confidence == 0.0


def test_previous_label_is_included_on_transition() -> None:
    label = detect_regime(
        _matrix(overrides=_risk_overrides(0.72)),
        timestamp=FROZEN_NOW,
        previous_label="risk_on_decorrelated",
    )
    assert "transition_from=risk_on_decorrelated" in label.drivers


def test_dict_matrix_input_is_supported() -> None:
    raw = _matrix(overrides=_risk_overrides(0.72)).to_dict()
    assert detect_regime(raw, timestamp=FROZEN_NOW).label == "risk_on_correlated"


def test_metrics_are_rounded_and_include_defensive_corr() -> None:
    overrides = _risk_overrides(0.3333333)
    overrides[("BTC", "XAUUSD")] = -0.25
    label = detect_regime(_matrix(overrides=overrides), timestamp=FROZEN_NOW)
    assert label.metrics["risk_asset_correlation"] == 0.3333
    assert "risk_defensive_correlation" in label.metrics


def test_confidence_stays_inside_probability_bounds() -> None:
    for matrix in [
        _matrix(overrides=_risk_overrides(0.72)),
        _matrix(default=0.82),
        _matrix(overrides=_risk_overrides(0.20)),
    ]:
        label = detect_regime(matrix, timestamp=FROZEN_NOW)
        assert 0.0 <= label.confidence <= 1.0


def test_history_smoothing_removes_single_sample_flicker() -> None:
    correlated = _matrix(overrides=_risk_overrides(0.72))
    decorrelated = _matrix(overrides=_risk_overrides(0.22))
    labels = label_regime_history([correlated, decorrelated, correlated], min_persistence=2)
    assert [item.label for item in labels] == [
        "risk_on_correlated",
        "risk_on_correlated",
        "risk_on_correlated",
    ]
    assert "smoothed_from=risk_on_decorrelated" in labels[1].drivers


def test_history_smoothing_accepts_persistent_transition() -> None:
    correlated = _matrix(overrides=_risk_overrides(0.72))
    decorrelated = _matrix(overrides=_risk_overrides(0.22))
    labels = label_regime_history([correlated, decorrelated, decorrelated], min_persistence=2)
    assert labels[-1].label == "risk_on_decorrelated"


def test_history_without_smoothing_keeps_raw_labels() -> None:
    correlated = _matrix(overrides=_risk_overrides(0.72))
    decorrelated = _matrix(overrides=_risk_overrides(0.22))
    labels = label_regime_history([correlated, decorrelated, correlated], min_persistence=1)
    assert labels[1].label == "risk_on_decorrelated"


def test_history_handles_gaps_in_input() -> None:
    labels = label_regime_history([None, _matrix(overrides=_risk_overrides(0.72))], min_persistence=1)
    assert labels[0].label == "regime_uncertain"
    assert labels[1].label == "risk_on_correlated"


def test_timestamps_are_applied_to_history() -> None:
    labels = label_regime_history(
        [_matrix(overrides=_risk_overrides(0.72))],
        timestamps=[FROZEN_NOW],
    )
    assert labels[0].timestamp == FROZEN_NOW.isoformat()


def test_dollar_pair_order_does_not_hide_cross_pairs() -> None:
    overrides = _risk_overrides(0.50)
    overrides.update(_risk_dollar_overrides(-0.60))
    label = detect_regime(_matrix(overrides=overrides), timestamp=FROZEN_NOW)
    assert label.metrics["risk_dollar_correlation"] == -0.6


def test_mixed_evidence_falls_back_to_uncertain() -> None:
    overrides = _risk_overrides(-0.20)
    overrides.update(_risk_dollar_overrides(0.55))
    label = detect_regime(_matrix(overrides=overrides), timestamp=FROZEN_NOW)
    assert label.label == "regime_uncertain"
