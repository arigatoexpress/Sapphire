"""Unit tests for lib/analytics/walkforward/regime_decomp.py.

All tests use synthetic returns + label dictionaries — no live data, no
filesystem reads from the canonical ``data/cross_asset/`` tree (we use
``tmp_path`` for the loader exercise).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from lib.analytics.walkforward.regime_decomp import (  # noqa: E402
    RegimeDecompResult,
    RegimeReturnsBucket,
    _normalise_date,
    attach_regime_labels,
    decompose_by_regime,
    decompose_walkforward_result,
    load_regime_labels,
)

# ── _normalise_date ────────────────────────────────────────────────────────


def test_normalise_date_handles_iso_short() -> None:
    assert _normalise_date("2026-04-29") == "2026-04-29"


def test_normalise_date_handles_iso_with_time() -> None:
    assert _normalise_date("2026-04-29T12:00:00+00:00") == "2026-04-29"


def test_normalise_date_handles_z_suffix() -> None:
    assert _normalise_date("2026-04-29T12:00:00Z") == "2026-04-29"


def test_normalise_date_handles_space_separator() -> None:
    assert _normalise_date("2026-04-29 12:00:00+00:00") == "2026-04-29"


def test_normalise_date_returns_empty_for_garbage() -> None:
    assert _normalise_date("") == ""
    assert _normalise_date("not-a-date") == ""


# ── attach_regime_labels — semantics ───────────────────────────────────────


def test_attach_labels_exact_match_only_uses_present_dates() -> None:
    labels = {"2026-01-01": "risk_on", "2026-01-03": "risk_off"}
    out = attach_regime_labels(
        ["2026-01-01", "2026-01-02", "2026-01-03"], labels, semantics="exact_match"
    )
    assert out == ["risk_on", "regime_uncertain", "risk_off"]


def test_attach_labels_forward_fill_inherits_prior_label() -> None:
    labels = {"2026-01-01": "risk_on", "2026-01-04": "risk_off"}
    out = attach_regime_labels(
        ["2026-01-01", "2026-01-02", "2026-01-03", "2026-01-04", "2026-01-05"],
        labels,
        semantics="forward_fill",
    )
    assert out == ["risk_on", "risk_on", "risk_on", "risk_off", "risk_off"]


def test_attach_labels_forward_fill_uses_default_when_no_prior() -> None:
    labels = {"2026-01-05": "risk_on"}
    out = attach_regime_labels(
        ["2026-01-01", "2026-01-05"], labels, semantics="forward_fill"
    )
    assert out == ["regime_uncertain", "risk_on"]


def test_attach_labels_nearest_prior_falls_through_to_future() -> None:
    """If no prior label exists, ``nearest_prior`` should reach forward."""
    labels = {"2026-01-05": "risk_on"}
    out = attach_regime_labels(
        ["2026-01-01", "2026-01-05"], labels, semantics="nearest_prior"
    )
    assert out == ["risk_on", "risk_on"]


def test_attach_labels_default_label_overridable() -> None:
    out = attach_regime_labels(
        ["2026-01-01"],
        {"2026-01-02": "risk_on"},
        semantics="exact_match",
        default_label="UNKNOWN",
    )
    assert out == ["UNKNOWN"]


def test_attach_labels_rejects_unknown_semantics() -> None:
    with pytest.raises(ValueError, match="semantics must be"):
        attach_regime_labels(["2026-01-01"], {"2026-01-01": "x"}, semantics="bogus")


def test_attach_labels_handles_empty_label_map() -> None:
    out = attach_regime_labels(["2026-01-01", "2026-01-02"], {})
    assert out == ["regime_uncertain", "regime_uncertain"]


def test_attach_labels_skips_unparseable_timestamps() -> None:
    labels = {"2026-01-01": "risk_on"}
    out = attach_regime_labels(["", "garbage", "2026-01-01"], labels)
    assert out[0] == "regime_uncertain"
    assert out[1] == "regime_uncertain"
    assert out[2] == "risk_on"


# ── decompose_by_regime ────────────────────────────────────────────────────


def test_decompose_basic_two_regimes() -> None:
    returns = [0.01, -0.02, 0.005, 0.03, -0.01]
    timestamps = ["2026-01-01", "2026-01-02", "2026-01-03", "2026-01-04", "2026-01-05"]
    labels = {"2026-01-01": "risk_on", "2026-01-04": "risk_off"}
    result = decompose_by_regime(
        returns, timestamps, labels=labels, strategy_cls="Foo", symbol="BTC-USD"
    )
    assert isinstance(result, RegimeDecompResult)
    assert result.n_observations == 5
    label_set = {b.label for b in result.buckets}
    assert label_set == {"risk_on", "risk_off"}


def test_decompose_returns_pnl_share_normalised() -> None:
    returns = [0.10, -0.05, 0.02]
    timestamps = ["2026-01-01", "2026-01-02", "2026-01-03"]
    labels = {"2026-01-01": "A", "2026-01-02": "B", "2026-01-03": "A"}
    result = decompose_by_regime(returns, timestamps, labels=labels)
    total_share = sum(b.pnl_share for b in result.buckets)
    assert total_share == pytest.approx(1.0, abs=1e-3)


def test_decompose_distribution_fractions_sum_to_one() -> None:
    returns = [0.0] * 5
    timestamps = [f"2026-01-0{i + 1}" for i in range(5)]
    labels = {f"2026-01-0{i + 1}": "X" for i in range(5)}
    result = decompose_by_regime(returns, timestamps, labels=labels)
    assert sum(result.distribution.values()) == pytest.approx(1.0)


def test_decompose_dominant_regime_is_largest_bucket() -> None:
    returns = [0.0] * 6
    timestamps = [f"2026-01-0{i + 1}" for i in range(6)]
    labels = {
        "2026-01-01": "A",
        "2026-01-02": "A",
        "2026-01-03": "A",
        "2026-01-04": "B",
        "2026-01-05": "B",
        "2026-01-06": "C",
    }
    result = decompose_by_regime(returns, timestamps, labels=labels)
    assert result.dominant_regime == "A"


def test_decompose_empty_returns_yields_zero_buckets() -> None:
    result = decompose_by_regime([], [], labels={})
    assert result.n_observations == 0
    assert result.buckets == []


def test_decompose_length_mismatch_raises() -> None:
    with pytest.raises(ValueError, match="same length"):
        decompose_by_regime([0.1, 0.2], ["2026-01-01"], labels={})


def test_decompose_unlabelled_count_when_no_labels() -> None:
    returns = [0.01, -0.02]
    timestamps = ["2026-01-01", "2026-01-02"]
    result = decompose_by_regime(returns, timestamps, labels={})
    assert result.n_unlabelled == 2
    assert result.n_labelled == 0


def test_bucket_metrics_have_expected_signs() -> None:
    """Pure positive returns → positive mean, win_rate=1, no drawdown."""
    returns = [0.01, 0.02, 0.005, 0.015]
    timestamps = ["2026-01-01"] * 4
    labels = {"2026-01-01": "bull"}
    result = decompose_by_regime(returns, timestamps, labels=labels)
    bucket = result.buckets[0]
    assert bucket.mean_return > 0
    assert bucket.win_rate == 1.0
    assert bucket.max_drawdown == 0.0


def test_bucket_metrics_drawdown_present_with_losses() -> None:
    returns = [-0.05, -0.03, -0.01]
    timestamps = ["2026-01-01"] * 3
    labels = {"2026-01-01": "bear"}
    result = decompose_by_regime(returns, timestamps, labels=labels)
    bucket = result.buckets[0]
    assert bucket.win_rate == 0.0
    assert bucket.max_drawdown > 0


def test_bucket_metrics_sortino_nonzero_when_downside_present() -> None:
    returns = [0.02, -0.01, 0.03, -0.02, 0.04]
    timestamps = ["2026-01-01"] * 5
    labels = {"2026-01-01": "mixed"}
    result = decompose_by_regime(returns, timestamps, labels=labels)
    bucket = result.buckets[0]
    assert bucket.sortino != 0.0


def test_decompose_to_dict_roundtrips_through_json() -> None:
    returns = [0.01, -0.02]
    timestamps = ["2026-01-01", "2026-01-02"]
    labels = {"2026-01-01": "A", "2026-01-02": "B"}
    result = decompose_by_regime(returns, timestamps, labels=labels)
    blob = json.dumps(result.to_dict())
    parsed = json.loads(blob)
    assert parsed["n_observations"] == 2


# ── load_regime_labels — file + directory handling ─────────────────────────


def test_load_regime_labels_from_file(tmp_path: Path) -> None:
    f = tmp_path / "regimes.jsonl"
    f.write_text(
        "\n".join(
            [
                json.dumps({"timestamp": "2026-01-01T12:00:00+00:00", "label": "risk_on"}),
                json.dumps({"timestamp": "2026-01-02", "label": "risk_off"}),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    labels = load_regime_labels(source=f)
    assert labels == {"2026-01-01": "risk_on", "2026-01-02": "risk_off"}


def test_load_regime_labels_skips_malformed_lines(tmp_path: Path) -> None:
    f = tmp_path / "regimes.jsonl"
    f.write_text(
        "\n".join(
            [
                "{not json",
                json.dumps({"timestamp": "2026-01-01", "label": "risk_on"}),
                "{}",
                json.dumps({"timestamp": "2026-01-03", "label": "risk_off"}),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    labels = load_regime_labels(source=f)
    assert labels == {"2026-01-01": "risk_on", "2026-01-03": "risk_off"}


def test_load_regime_labels_from_directory(tmp_path: Path) -> None:
    """Walk a fake regime_dir tree like data/cross_asset/<date>/regimes.jsonl."""
    day1 = tmp_path / "2026-01-01"
    day2 = tmp_path / "2026-01-02"
    day1.mkdir()
    day2.mkdir()
    (day1 / "regimes.jsonl").write_text(
        json.dumps({"timestamp": "2026-01-01", "label": "risk_on"}) + "\n"
    )
    (day2 / "regimes.jsonl").write_text(
        json.dumps({"timestamp": "2026-01-02", "label": "risk_off"}) + "\n"
    )
    # When source=None, regime_dir is walked newest-first.
    labels = load_regime_labels(source=None, regime_dir=tmp_path)
    # Only the newest dir is read by default.
    assert labels == {"2026-01-02": "risk_off"}


def test_load_regime_labels_handles_missing_dir(tmp_path: Path) -> None:
    labels = load_regime_labels(source=None, regime_dir=tmp_path / "nonexistent")
    assert labels == {}


def test_load_regime_labels_explicit_directory_glob(tmp_path: Path) -> None:
    """source=<dir> globs <dir>/*/regimes.jsonl across all dated subdirs."""
    for d, lab in [("2026-01-01", "A"), ("2026-01-02", "B")]:
        sub = tmp_path / d
        sub.mkdir()
        (sub / "regimes.jsonl").write_text(json.dumps({"timestamp": d, "label": lab}) + "\n")
    labels = load_regime_labels(source=tmp_path)
    assert labels == {"2026-01-01": "A", "2026-01-02": "B"}


def test_load_regime_labels_latest_wins_on_duplicates(tmp_path: Path) -> None:
    f = tmp_path / "regimes.jsonl"
    f.write_text(
        "\n".join(
            [
                json.dumps({"timestamp": "2026-01-01", "label": "risk_on"}),
                json.dumps({"timestamp": "2026-01-01", "label": "risk_off"}),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    labels = load_regime_labels(source=f)
    assert labels == {"2026-01-01": "risk_off"}  # last line wins


# ── decompose_walkforward_result — convenience adapter ─────────────────────


class _FakeResult:
    """Stand-in for WalkforwardResult — only the duck-typed fields matter."""

    def __init__(self) -> None:
        self.strategy_cls = "FakeStrategy"
        self.symbol = "BTC-USD"
        self.concatenated_test_returns = [0.01, -0.02, 0.03]
        self.concatenated_test_timestamps = ["2026-01-01", "2026-01-02", "2026-01-03"]


def test_decompose_walkforward_result_consumes_duck_typed() -> None:
    fake = _FakeResult()
    result = decompose_walkforward_result(fake, labels={"2026-01-01": "A", "2026-01-03": "B"})
    assert result.strategy_cls == "FakeStrategy"
    assert result.symbol == "BTC-USD"
    assert result.n_observations == 3


def test_regime_returns_bucket_to_dict_has_stable_keys() -> None:
    bucket = RegimeReturnsBucket(
        label="x",
        n_observations=1,
        total_return=0.0,
        mean_return=0.0,
        median_return=0.0,
        volatility=0.0,
        downside_volatility=0.0,
        win_rate=0.0,
        max_drawdown=0.0,
        sharpe=0.0,
        sortino=0.0,
        pnl_share=0.0,
    )
    d = bucket.to_dict()
    assert "label" in d and "n_observations" in d and "sharpe" in d
