"""Tests for Layer A chain-factor deltas in plugins/claw-sapphire/tools/internal/predict.py.

Covers:
- ``chain_factor_deltas`` — pure delta computation for funding/OI inputs.
- ``_read_chain_features`` — best-effort adapter over the chain-refresh artifact.
- ``action_predict`` — opt-in env-flag path that wires the deltas into the
  six-factor score before classification. With the flag unset, behavior must
  be bit-for-bit identical to the legacy code path.

The Layer C threshold tests already live in test_predict.py — these tests
deliberately do not assert on the final ``direction`` classification.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from unittest.mock import patch

import pytest

TOOLS = Path(__file__).parent.parent / "tools"
sys.path.insert(0, str(TOOLS))
sys.path.insert(0, str(TOOLS.parent / "lib"))

_spec = importlib.util.spec_from_file_location(
    "predict", TOOLS / "internal" / "predict.py"
)
predict = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(predict)


# ---------------------------------------------------------------------------
# chain_factor_deltas — pure function
# ---------------------------------------------------------------------------


def test_chain_factor_deltas_high_positive_funding_z_adds_bear():
    """Crowded longs (funding_z >> 0) bias toward bear."""
    bull, bear, factors = predict.chain_factor_deltas(
        "BTC", funding_z=2.5, oi_change_pct=None
    )
    assert bull == 0.0
    assert bear == 0.5
    assert any("FundZ" in f for f in factors)
    assert any("↓" in f for f in factors)


def test_chain_factor_deltas_high_negative_funding_z_adds_bull():
    """Crowded shorts (funding_z << 0) bias toward bull."""
    bull, bear, factors = predict.chain_factor_deltas(
        "ETH", funding_z=-2.0, oi_change_pct=None
    )
    assert bull == 0.5
    assert bear == 0.0
    assert any("FundZ" in f for f in factors)
    assert any("↑" in f for f in factors)


def test_chain_factor_deltas_small_funding_z_returns_zero():
    """|z| under 1.5 is treated as noise — no contribution."""
    bull, bear, factors = predict.chain_factor_deltas(
        "BTC", funding_z=0.8, oi_change_pct=None
    )
    assert bull == 0.0
    assert bear == 0.0
    assert factors == []


def test_chain_factor_deltas_funding_z_at_threshold_is_noise():
    """Strict greater-than at the |z|=1.5 boundary — exactly 1.5 contributes nothing."""
    bull, bear, _ = predict.chain_factor_deltas(
        "BTC", funding_z=1.5, oi_change_pct=None
    )
    assert bull == 0.0
    assert bear == 0.0
    bull, bear, _ = predict.chain_factor_deltas(
        "BTC", funding_z=-1.5, oi_change_pct=None
    )
    assert bull == 0.0
    assert bear == 0.0


def test_chain_factor_deltas_oi_amplifies_bear_when_funding_is_bearish():
    """Rising OI in a crowded-long context = late-cycle long crowding -> bear."""
    bull, bear, factors = predict.chain_factor_deltas(
        "SOL", funding_z=2.0, oi_change_pct=8.0
    )
    # funding (+0.5 bear) + OI amplifying bear (+0.5) = 1.0 bear.
    assert bull == 0.0
    assert bear == 1.0
    assert any("OI" in f for f in factors)
    assert any("↓" in f for f in factors[-1:])  # OI label trailing the funding one


def test_chain_factor_deltas_oi_amplifies_bull_when_funding_is_bullish():
    """Rising OI in a crowded-short context amplifies bull."""
    bull, bear, factors = predict.chain_factor_deltas(
        "SOL", funding_z=-2.0, oi_change_pct=8.0
    )
    assert bull == 1.0
    assert bear == 0.0
    assert any("OI" in f for f in factors)


def test_chain_factor_deltas_oi_alone_without_dominant_context_does_nothing():
    """OI is amplification-only — with no funding lean it adds zero."""
    bull, bear, factors = predict.chain_factor_deltas(
        "BTC", funding_z=None, oi_change_pct=12.0
    )
    assert bull == 0.0
    assert bear == 0.0
    assert factors == []


def test_chain_factor_deltas_oi_below_threshold_does_nothing():
    """OI under +5% does not amplify."""
    bull, bear, factors = predict.chain_factor_deltas(
        "BTC", funding_z=2.0, oi_change_pct=2.0
    )
    # Only the funding contribution survives.
    assert bull == 0.0
    assert bear == 0.5
    assert all("OI" not in f for f in factors)


def test_chain_factor_deltas_both_none_returns_zero():
    bull, bear, factors = predict.chain_factor_deltas(
        "BTC", funding_z=None, oi_change_pct=None
    )
    assert bull == 0.0
    assert bear == 0.0
    assert factors == []


def test_chain_factor_deltas_caps_each_contribution_at_half():
    """Funding cap is 0.5 even at extreme z — no single factor can flip a direction."""
    bull, bear, _ = predict.chain_factor_deltas(
        "BTC", funding_z=99.0, oi_change_pct=None
    )
    assert bear == 0.5
    bull, bear, _ = predict.chain_factor_deltas(
        "BTC", funding_z=-99.0, oi_change_pct=None
    )
    assert bull == 0.5


# ---------------------------------------------------------------------------
# _read_chain_features — adapter contract
# ---------------------------------------------------------------------------


def test_read_chain_features_returns_none_when_file_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(predict, "CHAIN_LATEST_FILE", tmp_path / "nope.json")
    assert predict._read_chain_features("BTC") == (None, None)


def test_read_chain_features_returns_none_on_malformed_json(tmp_path, monkeypatch):
    bad = tmp_path / "chain.json"
    bad.write_text("{not valid json")
    monkeypatch.setattr(predict, "CHAIN_LATEST_FILE", bad)
    assert predict._read_chain_features("BTC") == (None, None)


def test_read_chain_features_returns_none_when_symbol_absent(tmp_path, monkeypatch):
    f = tmp_path / "chain.json"
    f.write_text(json.dumps({
        "funding": {"perps": [
            {"coin": "ETH", "funding_z": 2.0, "oi_change_pct": 3.0},
        ]}
    }))
    monkeypatch.setattr(predict, "CHAIN_LATEST_FILE", f)
    assert predict._read_chain_features("BTC") == (None, None)


def test_read_chain_features_extracts_values_from_funding_perps_shape(
    tmp_path, monkeypatch
):
    f = tmp_path / "chain.json"
    f.write_text(json.dumps({
        "funding": {"perps": [
            {"coin": "BTC", "funding_z": 1.8, "oi_change_pct": 7.2},
            {"coin": "ETH", "funding_z": -0.3, "oi_change_pct": 1.0},
        ]}
    }))
    monkeypatch.setattr(predict, "CHAIN_LATEST_FILE", f)
    assert predict._read_chain_features("BTC") == (1.8, 7.2)
    assert predict._read_chain_features("ETH") == (-0.3, 1.0)


def test_read_chain_features_extracts_from_per_symbol_shape(tmp_path, monkeypatch):
    """Future-proof: adapter accepts a ``per_symbol`` keyed dict too."""
    f = tmp_path / "chain.json"
    f.write_text(json.dumps({
        "per_symbol": {
            "SOL": {"funding_z": 2.4, "oi_change_pct": 9.0},
        }
    }))
    monkeypatch.setattr(predict, "CHAIN_LATEST_FILE", f)
    assert predict._read_chain_features("SOL") == (2.4, 9.0)


def test_read_chain_features_handles_empty_dict(tmp_path, monkeypatch):
    f = tmp_path / "chain.json"
    f.write_text("{}")
    monkeypatch.setattr(predict, "CHAIN_LATEST_FILE", f)
    assert predict._read_chain_features("BTC") == (None, None)


def test_read_chain_features_never_raises(tmp_path, monkeypatch):
    """Adapter is best-effort — even bizarre file content must yield (None, None)."""
    weird = tmp_path / "chain.json"
    weird.write_text("[1, 2, 3]")  # JSON, but wrong shape
    monkeypatch.setattr(predict, "CHAIN_LATEST_FILE", weird)
    assert predict._read_chain_features("BTC") == (None, None)


def test_read_chain_features_tolerates_non_numeric_values(tmp_path, monkeypatch):
    """String/null funding values are skipped, not crashed on."""
    f = tmp_path / "chain.json"
    f.write_text(json.dumps({
        "funding": {"perps": [
            {"coin": "BTC", "funding_z": "not-a-number", "oi_change_pct": None},
        ]}
    }))
    monkeypatch.setattr(predict, "CHAIN_LATEST_FILE", f)
    assert predict._read_chain_features("BTC") == (None, None)


# ---------------------------------------------------------------------------
# action_predict — env flag wiring
# ---------------------------------------------------------------------------


@dataclass
class _FakeProfile:
    """Minimal stand-in for technical_analysis.TechnicalProfile.

    Only the fields read by action_predict are populated. Values are picked so
    the legacy six-factor score is unambiguous and the chain-factor deltas land
    in a clearly observable place.
    """

    symbol: str = "BTC"
    price: float = 50000.0
    timestamp: str = "2026-04-26T00:00:00+00:00"
    # Price action
    change_24h_pct: float = 0.0
    change_7d_pct: float = 1.0  # below the ±5 threshold — no momentum bonus
    high_7d: float = 51000.0
    low_7d: float = 49000.0
    range_position: float = 0.5
    # MAs — bearish, so MA contributes +2.0 to bear_score
    sma_7: float = 49500.0
    sma_20: float = 50100.0
    sma_50: float | None = 50000.0
    above_sma_7: bool = True
    above_sma_20: bool = False
    ma_trend: str = "bearish"
    # RSI — neutral
    rsi_14: float = 50.0
    rsi_zone: str = "neutral"
    # ATR
    atr_14: float = 500.0
    atr_pct: float = 1.0
    volatility_regime: str = "low"
    # Volume — neutral (between 0.5 and 1.5)
    volume_avg_7d: float = 1000.0
    volume_ratio: float = 1.0
    volume_signal: str = "normal"
    # MACD — none
    macd_line: float = 0.0
    macd_signal: float = 0.0
    macd_histogram: float = 0.0
    macd_cross: str = "none"
    # Bollinger — middle
    bb_upper: float = 51000.0
    bb_middle: float = 50000.0
    bb_lower: float = 49000.0
    bb_position: str = "lower_half"
    # Aggregate
    signal_count_bullish: int = 0
    signal_count_bearish: int = 1
    net_signal: str = "bearish"


@pytest.fixture
def isolated_predictions_file(tmp_path, monkeypatch):
    """Redirect the predictions JSONL writer at a tmp file so tests don't pollute prod."""
    p = tmp_path / "trading_predictions.jsonl"
    monkeypatch.setattr(predict, "PREDICTIONS_FILE", p)
    return p


def _read_records(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def test_action_predict_default_off_unchanged_record(
    isolated_predictions_file, monkeypatch
):
    """With the flag unset, action_predict must produce the same record as legacy.

    We assert bull_score / bear_score / factor list show no chain-factor entries
    AND that the reasoning string contains exactly the legacy six-factor labels.
    """
    monkeypatch.delenv("SAPPHIRE_PREDICT_USE_CHAIN_FACTORS", raising=False)
    # Pre-empt: ensure the adapter is never called when the flag is off.
    monkeypatch.setattr(
        predict,
        "_read_chain_features",
        lambda sym: pytest.fail("adapter must not be called when flag is off"),
    )

    fake_profiles = {"BTC": _FakeProfile(symbol="BTC")}

    with patch.object(predict, "action_predict", wraps=predict.action_predict):
        # Patch the analyze_all import inside action_predict.
        fake_module = type(sys)("technical_analysis")
        fake_module.analyze_all = lambda: fake_profiles  # type: ignore[attr-defined]
        monkeypatch.setitem(sys.modules, "technical_analysis", fake_module)

        result = predict.action_predict()

    assert result["success"] is True
    records = _read_records(isolated_predictions_file)
    assert len(records) == 1
    rec = records[0]
    # No chain-factor labels in the reasoning string.
    assert "FundZ" not in rec["reasoning"]
    assert "OI" not in rec["reasoning"]
    # Bear is dominant (MA↓ = 2.0); reasoning carries the legacy Bear score.
    assert "Bear=2.0" in rec["reasoning"]


def test_action_predict_flag_on_chain_features_present_applies_deltas(
    isolated_predictions_file, monkeypatch
):
    """With the flag set AND patched chain features, deltas land in bull/bear scores.

    Setup: bearish MA (+2.0 bear), funding_z=2.5 (chain +0.5 bear), oi_change=8%
    in a bear-dominant context (chain +0.5 bear). Total bear = 3.0; bull = 0.0.
    The reasoning string must include the chain factor labels.

    We do NOT assert on the final ``direction`` — Layer C tests own the
    threshold contract. We only assert on the score deltas and the factor list.
    """
    monkeypatch.setenv("SAPPHIRE_PREDICT_USE_CHAIN_FACTORS", "1")
    monkeypatch.setattr(
        predict, "_read_chain_features", lambda sym: (2.5, 8.0)
    )

    fake_profiles = {"BTC": _FakeProfile(symbol="BTC")}
    fake_module = type(sys)("technical_analysis")
    fake_module.analyze_all = lambda: fake_profiles  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "technical_analysis", fake_module)

    result = predict.action_predict()
    assert result["success"] is True

    records = _read_records(isolated_predictions_file)
    assert len(records) == 1
    rec = records[0]
    # MA↓ (2.0) + chain bear (1.0) = 3.0 bear; bull untouched at 0.0.
    assert "Bear=3.0" in rec["reasoning"]
    assert "Bull=0.0" in rec["reasoning"]
    # Chain factor labels surface.
    assert "FundZ" in rec["reasoning"]
    assert "OI" in rec["reasoning"]


def test_action_predict_flag_on_no_chain_features_legacy_record(
    isolated_predictions_file, monkeypatch
):
    """Flag on but adapter returns (None, None) — record matches the legacy path.

    This is the production-rollout safety net: a corrupt/missing chain.json
    must not change scoring even when the operator has opted in.
    """
    monkeypatch.setenv("SAPPHIRE_PREDICT_USE_CHAIN_FACTORS", "1")
    monkeypatch.setattr(predict, "_read_chain_features", lambda sym: (None, None))

    fake_profiles = {"BTC": _FakeProfile(symbol="BTC")}
    fake_module = type(sys)("technical_analysis")
    fake_module.analyze_all = lambda: fake_profiles  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "technical_analysis", fake_module)

    predict.action_predict()
    rec = _read_records(isolated_predictions_file)[0]
    assert "Bear=2.0" in rec["reasoning"]
    assert "FundZ" not in rec["reasoning"]


def test_action_predict_flag_only_one_chain_value_skips_deltas(
    isolated_predictions_file, monkeypatch
):
    """Adapter contract: both values required. If either side is None,
    we apply no deltas — same as the missing-data case."""
    monkeypatch.setenv("SAPPHIRE_PREDICT_USE_CHAIN_FACTORS", "1")
    # funding_z is None — even though OI is present, we skip.
    monkeypatch.setattr(predict, "_read_chain_features", lambda sym: (None, 8.0))

    fake_profiles = {"BTC": _FakeProfile(symbol="BTC")}
    fake_module = type(sys)("technical_analysis")
    fake_module.analyze_all = lambda: fake_profiles  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "technical_analysis", fake_module)

    predict.action_predict()
    rec = _read_records(isolated_predictions_file)[0]
    assert "Bear=2.0" in rec["reasoning"]
    assert "OI" not in rec["reasoning"]


def test_action_predict_env_flag_zero_explicit(
    isolated_predictions_file, monkeypatch
):
    """Explicit ``0`` is identical to the unset case."""
    monkeypatch.setenv("SAPPHIRE_PREDICT_USE_CHAIN_FACTORS", "0")
    monkeypatch.setattr(
        predict,
        "_read_chain_features",
        lambda sym: pytest.fail("adapter must not be called when flag is 0"),
    )

    fake_profiles = {"BTC": _FakeProfile(symbol="BTC")}
    fake_module = type(sys)("technical_analysis")
    fake_module.analyze_all = lambda: fake_profiles  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "technical_analysis", fake_module)

    predict.action_predict()
    rec = _read_records(isolated_predictions_file)[0]
    assert "Bear=2.0" in rec["reasoning"]


def test_action_predict_baseline_record_matches_with_and_without_flag(
    tmp_path, monkeypatch
):
    """End-to-end equivalence: same inputs, two writes, only the flag differs.

    Compares the two records' bull/bear/factors-derived state. Skips the
    timestamp field because action_predict stamps it at call time.
    """
    fake_profiles = {"BTC": _FakeProfile(symbol="BTC")}
    fake_module = type(sys)("technical_analysis")
    fake_module.analyze_all = lambda: fake_profiles  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "technical_analysis", fake_module)

    # Run 1 — flag unset.
    monkeypatch.delenv("SAPPHIRE_PREDICT_USE_CHAIN_FACTORS", raising=False)
    p1 = tmp_path / "run1.jsonl"
    monkeypatch.setattr(predict, "PREDICTIONS_FILE", p1)
    predict.action_predict()
    baseline = _read_records(p1)[0]

    # Run 2 — flag on, but adapter empty -> same outcome.
    monkeypatch.setenv("SAPPHIRE_PREDICT_USE_CHAIN_FACTORS", "1")
    monkeypatch.setattr(predict, "_read_chain_features", lambda sym: (None, None))
    p2 = tmp_path / "run2.jsonl"
    monkeypatch.setattr(predict, "PREDICTIONS_FILE", p2)
    predict.action_predict()
    flagged = _read_records(p2)[0]

    # Reasoning is the most compact summary of the score state — drop the timestamps
    # the rest of the record carries.
    for k in ("timestamp",):
        baseline.pop(k, None)
        flagged.pop(k, None)
    assert baseline == flagged
