"""Tests for pure helpers in ``services/intelligence/daily_brief.py``.

The daily brief is a 31KB module that synthesizes 8 intelligence streams
into a Telegram message. The bulk of its surface needs network/state mocks,
but the formatting helpers (``_fmt_usd``, ``_fmt_pct``, ``_regime_narrative``)
are pure functions with clear contracts. Untested before this file.
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
INTEL_ROOT = REPO_ROOT / "services" / "intelligence"

if str(INTEL_ROOT.parent) not in sys.path:
    sys.path.insert(0, str(INTEL_ROOT.parent))

# Load via importlib to avoid import-time side effects that the module's
# logging.basicConfig() would otherwise apply globally.
_spec = importlib.util.spec_from_file_location(
    "daily_brief_module",
    INTEL_ROOT / "daily_brief.py",
)
daily_brief = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(daily_brief)


# ── _fmt_usd ─────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "value,expected",
    [
        (None, "—"),
        (0.0, "$0.00"),
        (1.0, "$1.00"),
        (1234.0, "$1.23k"),
        (-1234.0, "-$1.23k"),
        (1_234_567.0, "$1.23M"),
        (-1_234_567.0, "-$1.23M"),
        (1_234_567_890.0, "$1.23B"),
        (-1_234_567_890.0, "-$1.23B"),
    ],
)
def test_fmt_usd_thresholds(value, expected):
    assert daily_brief._fmt_usd(value) == expected


def test_fmt_usd_respects_digits_argument():
    assert daily_brief._fmt_usd(1_234_567.0, digits=4) == "$1.2346M"
    assert daily_brief._fmt_usd(0.0, digits=0) == "$0"
    assert daily_brief._fmt_usd(1234.0, digits=0) == "$1k"


def test_fmt_usd_handles_small_negative_values():
    assert daily_brief._fmt_usd(-0.5) == "-$0.50"


def test_fmt_usd_uses_b_for_trillions_too():
    """Above 1B the ratio just keeps growing — there's no T suffix."""
    assert daily_brief._fmt_usd(1_500_000_000_000.0) == "$1500.00B"


def test_fmt_usd_boundary_just_below_million():
    """A value just under 1M is still in the k bucket."""
    assert daily_brief._fmt_usd(999_999.0) == "$1000.00k"


# ── _fmt_pct ─────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "value,expected",
    [
        (None, "—"),
        (0.0, "+0.0%"),
        (0.05, "+5.0%"),
        (-0.05, "-5.0%"),
        (1.0, "+100.0%"),
        (-1.0, "-100.0%"),
        (0.001, "+0.1%"),
    ],
)
def test_fmt_pct_thresholds(value, expected):
    assert daily_brief._fmt_pct(value) == expected


def test_fmt_pct_respects_digits_argument():
    assert daily_brief._fmt_pct(0.05, digits=3) == "+5.000%"
    assert daily_brief._fmt_pct(0.05, digits=0) == "+5%"


def test_fmt_pct_always_signed():
    """Output always carries a sign — never a bare number."""
    assert daily_brief._fmt_pct(0.0).startswith("+")
    assert daily_brief._fmt_pct(0.001).startswith("+")
    assert daily_brief._fmt_pct(-0.001).startswith("-")


# ── _regime_narrative ────────────────────────────────────────────────


def test_regime_narrative_empty_snapshot_returns_no_signal():
    result = daily_brief._regime_narrative("NEUTRAL", 0.0, 0.5, {})

    assert "No signal data" in result


@pytest.mark.parametrize(
    "fg,expected_label",
    [
        (0, "extreme fear"),
        (10, "extreme fear"),
        (19, "extreme fear"),
        (20, "fear"),
        (39, "fear"),
        (40, "neutral"),
        (59, "neutral"),
        (60, "greed"),
        (79, "greed"),
        (80, "extreme greed"),
        (100, "extreme greed"),
    ],
)
def test_regime_narrative_fear_greed_label_thresholds(fg, expected_label):
    result = daily_brief._regime_narrative(
        "NEUTRAL", 0.0, 0.5, {"fear_greed": fg}
    )

    assert f"({expected_label})" in result
    assert f"F&G {fg}" in result


def test_regime_narrative_total_mcap_inflow_phrasing():
    """Total mcap >+1.5% is described as capital inflowing."""
    result = daily_brief._regime_narrative(
        "RISK_ON", 0.5, 0.7,
        {"fear_greed": 55, "total_mcap_24h_change_pct": 2.5},
    )

    assert "+2.5%" in result
    assert "capital flowing in" in result


def test_regime_narrative_total_mcap_outflow_phrasing():
    """Total mcap <-1.5% is described as capital leaving."""
    result = daily_brief._regime_narrative(
        "RISK_OFF", -0.5, 0.7,
        {"fear_greed": 25, "total_mcap_24h_change_pct": -2.5},
    )

    assert "-2.5%" in result
    assert "capital leaving" in result


def test_regime_narrative_total_mcap_below_threshold_omits_phrase():
    """A small mcap change (-1.0% to +1.5%) doesn't trigger the inflow/outflow phrase."""
    result = daily_brief._regime_narrative(
        "NEUTRAL", 0.0, 0.5,
        {"fear_greed": 50, "total_mcap_24h_change_pct": 0.5},
    )

    assert "capital flowing in" not in result
    assert "capital leaving" not in result


def test_regime_narrative_btc_dominance_arrow_up():
    result = daily_brief._regime_narrative(
        "NEUTRAL", 0.0, 0.5,
        {"fear_greed": 50, "btc_dominance": 55.0, "btc_dominance_24h_change": 0.20},
    )

    assert "BTC.D 55.0%" in result
    assert "↑0.20%" in result


def test_regime_narrative_btc_dominance_arrow_down():
    result = daily_brief._regime_narrative(
        "NEUTRAL", 0.0, 0.5,
        {"fear_greed": 50, "btc_dominance": 55.0, "btc_dominance_24h_change": -0.20},
    )

    assert "↓0.20%" in result


def test_regime_narrative_btc_dominance_flat_arrow():
    """When |change| <= 0.05, the flat (→) arrow is used."""
    result = daily_brief._regime_narrative(
        "NEUTRAL", 0.0, 0.5,
        {"fear_greed": 50, "btc_dominance": 55.0, "btc_dominance_24h_change": 0.02},
    )

    assert "→0.02%" in result


def test_regime_narrative_funding_normal_tag():
    result = daily_brief._regime_narrative(
        "NEUTRAL", 0.0, 0.5,
        {"fear_greed": 50, "btc_funding_rate_pct": 0.02},
    )

    assert "funding +0.020%" in result
    assert "(normal)" in result


def test_regime_narrative_funding_flat_tag():
    """|funding| < 0.005 is tagged 'flat'."""
    result = daily_brief._regime_narrative(
        "NEUTRAL", 0.0, 0.5,
        {"fear_greed": 50, "btc_funding_rate_pct": 0.001},
    )

    assert "(flat)" in result


def test_regime_narrative_funding_longs_crowded_tag():
    """funding > 0.04 is tagged 'longs crowded'."""
    result = daily_brief._regime_narrative(
        "NEUTRAL", 0.0, 0.5,
        {"fear_greed": 50, "btc_funding_rate_pct": 0.05},
    )

    assert "(longs crowded)" in result


def test_regime_narrative_funding_shorts_crowded_tag():
    """funding < -0.04 is tagged 'shorts crowded'."""
    result = daily_brief._regime_narrative(
        "NEUTRAL", 0.0, 0.5,
        {"fear_greed": 50, "btc_funding_rate_pct": -0.05},
    )

    assert "(shorts crowded)" in result


def test_regime_narrative_eth_funding_appended_when_present():
    result = daily_brief._regime_narrative(
        "NEUTRAL", 0.0, 0.5,
        {"fear_greed": 50, "btc_funding_rate_pct": 0.02, "eth_funding_rate_pct": 0.03},
    )

    assert "ETH +0.030%" in result


def test_regime_narrative_dxy_and_vix_no_headwinds():
    """DXY ≤ 101 and VIX ≤ 20 → no 'macro headwinds' suffix."""
    result = daily_brief._regime_narrative(
        "NEUTRAL", 0.0, 0.5,
        {"fear_greed": 50, "dxy": 100.0, "vix": 15.0},
    )

    assert "DXY 100.0" in result
    assert "VIX 15.0" in result
    assert "macro headwinds" not in result


def test_regime_narrative_dxy_high_triggers_headwinds():
    result = daily_brief._regime_narrative(
        "NEUTRAL", 0.0, 0.5,
        {"fear_greed": 50, "dxy": 105.0, "vix": 15.0},
    )

    assert "macro headwinds" in result


def test_regime_narrative_vix_high_triggers_headwinds():
    """VIX > 20 also triggers 'macro headwinds' even with low DXY."""
    result = daily_brief._regime_narrative(
        "NEUTRAL", 0.0, 0.5,
        {"fear_greed": 50, "dxy": 100.0, "vix": 25.0},
    )

    assert "macro headwinds" in result


def test_regime_narrative_vix_warning_emoji_above_25():
    result = daily_brief._regime_narrative(
        "NEUTRAL", 0.0, 0.5,
        {"fear_greed": 50, "vix": 30.0},
    )

    assert "VIX 30.0 ⚠️" in result


def test_regime_narrative_vix_elevated_marker_18_to_25():
    result = daily_brief._regime_narrative(
        "NEUTRAL", 0.0, 0.5,
        {"fear_greed": 50, "vix": 22.0},
    )

    assert "VIX 22.0 (elevated)" in result


def test_regime_narrative_vix_under_18_no_marker():
    result = daily_brief._regime_narrative(
        "NEUTRAL", 0.0, 0.5,
        {"fear_greed": 50, "vix": 15.0},
    )

    assert "VIX 15.0" in result
    assert "(elevated)" not in result
    assert "⚠️" not in result


def test_regime_narrative_indented_with_two_spaces():
    """Output sentences are 2-space indented for the Telegram message tree."""
    result = daily_brief._regime_narrative(
        "NEUTRAL", 0.0, 0.5, {"fear_greed": 50},
    )

    for line in result.split("\n"):
        assert line.startswith("  ")


def test_regime_narrative_full_snapshot_renders_three_sentences():
    """All three sections present → three sentences (one per line)."""
    snap = {
        "fear_greed": 65,
        "total_mcap_24h_change_pct": 2.0,
        "btc_dominance": 53.0,
        "btc_dominance_24h_change": 0.30,
        "btc_funding_rate_pct": 0.02,
        "eth_funding_rate_pct": 0.025,
        "dxy": 105.0,
        "vix": 25.0,
    }

    result = daily_brief._regime_narrative("RISK_ON", 0.4, 0.7, snap)
    sentences = [line for line in result.split("\n") if line.strip()]

    assert len(sentences) == 3
