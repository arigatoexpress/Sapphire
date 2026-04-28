"""Tests for plugins/claw-sapphire/tools/internal/predict.py.

Covers the direction classification rule and the env-var-driven threshold
resolution introduced for the bearish-direction asymmetry mitigation
(Layer C of docs/research/bearish-direction-asymmetry-2026-04-26.md).
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

TOOLS = Path(__file__).parent.parent / "tools"
sys.path.insert(0, str(TOOLS))
sys.path.insert(0, str(TOOLS.parent / "lib"))

_spec = importlib.util.spec_from_file_location("predict", TOOLS / "internal" / "predict.py")
predict = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(predict)


# --- classify_direction -----------------------------------------------------


@pytest.mark.parametrize(
    "net,expected",
    [
        (1.6, "bullish"),
        (1.5, "neutral"),  # strict greater-than at bull threshold
        (1.51, "bullish"),
        (0.0, "neutral"),
        (-1.5, "neutral"),  # strict less-than at bear threshold
        (-1.51, "bearish"),
        (-1.6, "bearish"),
    ],
)
def test_classify_direction_default_thresholds_match_legacy(net, expected):
    """Default thresholds preserve the original symmetric ±1.5 rule."""
    assert predict.classify_direction(net) == expected


def test_classify_direction_asymmetric_bear_threshold_suppresses_marginal_bear():
    """A higher bear threshold drops MA-only false-bear calls (net = -2.0)."""
    # Three of five full-feature bear misses fired with net ≈ -2.0
    # because MA↓ alone contributes 2.0. A bear threshold of 2.5
    # converts those calls to neutral while keeping bull behavior intact.
    assert predict.classify_direction(-2.0) == "bearish"
    assert predict.classify_direction(-2.0, bear_threshold=2.5) == "neutral"
    assert predict.classify_direction(-3.5, bear_threshold=2.5) == "bearish"
    # Bull side is unaffected by raising the bear threshold.
    assert predict.classify_direction(2.0, bear_threshold=2.5) == "bullish"


def test_classify_direction_lowered_bull_threshold_raises_bull_calls():
    """Lowering the bull threshold makes bull calls easier — symmetric sanity."""
    assert predict.classify_direction(1.0) == "neutral"
    assert predict.classify_direction(1.0, bull_threshold=0.5) == "bullish"


# --- _resolve_threshold -----------------------------------------------------


def test_resolve_threshold_returns_default_when_env_unset(monkeypatch):
    monkeypatch.delenv("SAPPHIRE_PREDICT_BEAR_THRESHOLD", raising=False)
    assert predict._resolve_threshold("SAPPHIRE_PREDICT_BEAR_THRESHOLD", 1.5) == 1.5


def test_resolve_threshold_returns_default_when_env_blank(monkeypatch):
    monkeypatch.setenv("SAPPHIRE_PREDICT_BEAR_THRESHOLD", "")
    assert predict._resolve_threshold("SAPPHIRE_PREDICT_BEAR_THRESHOLD", 1.5) == 1.5


def test_resolve_threshold_returns_default_when_env_invalid(monkeypatch):
    monkeypatch.setenv("SAPPHIRE_PREDICT_BEAR_THRESHOLD", "not-a-number")
    assert predict._resolve_threshold("SAPPHIRE_PREDICT_BEAR_THRESHOLD", 1.5) == 1.5


def test_resolve_threshold_returns_default_when_env_non_positive(monkeypatch):
    monkeypatch.setenv("SAPPHIRE_PREDICT_BEAR_THRESHOLD", "-3")
    assert predict._resolve_threshold("SAPPHIRE_PREDICT_BEAR_THRESHOLD", 1.5) == 1.5
    monkeypatch.setenv("SAPPHIRE_PREDICT_BEAR_THRESHOLD", "0")
    assert predict._resolve_threshold("SAPPHIRE_PREDICT_BEAR_THRESHOLD", 1.5) == 1.5


def test_resolve_threshold_uses_env_when_valid(monkeypatch):
    monkeypatch.setenv("SAPPHIRE_PREDICT_BEAR_THRESHOLD", "2.75")
    assert predict._resolve_threshold("SAPPHIRE_PREDICT_BEAR_THRESHOLD", 1.5) == 2.75


def test_default_thresholds_are_legacy_symmetric():
    """Constants preserve the legacy ±1.5 symmetric behavior."""
    assert predict.DEFAULT_BULL_THRESHOLD == 1.5
    assert predict.DEFAULT_BEAR_THRESHOLD == 1.5
