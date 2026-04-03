"""Tests for token budget governance."""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent.parent / "lib"))
import token_governor


def test_record_and_status():
    """Recording usage should update status correctly."""
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
        tmp = Path(f.name)

    with patch.object(token_governor, "USAGE_PATH", tmp):
        # Record some T0 usage
        token_governor.record("t0", prompt_tokens=100, eval_tokens=50, task="test")
        token_governor.record("t0", prompt_tokens=200, eval_tokens=100, task="test2")

        s = token_governor.status()
        assert s["t0"]["used"] == 450  # 100+50+200+100
        assert s["t0"]["calls"] == 2
        assert s["t0"]["prompt_tokens"] == 300
        assert s["t0"]["eval_tokens"] == 150

    tmp.unlink()


def test_budget_exhaustion():
    """T1 should show exhausted when over budget."""
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
        tmp = Path(f.name)

    with patch.object(token_governor, "USAGE_PATH", tmp):
        with patch.object(token_governor, "DAILY_BUDGETS", {"t0_nemotron": float("inf"), "t1_kimi": 100, "t2_claw": 300000, "t3_claude": 200000}):
            token_governor.record("t1", prompt_tokens=80, eval_tokens=30, task="test")
            assert not token_governor.is_available("t1")  # 110 > 100

    tmp.unlink()


def test_t0_always_available():
    """T0 (Nemotron) should always be available (unlimited budget)."""
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
        tmp = Path(f.name)

    with patch.object(token_governor, "USAGE_PATH", tmp):
        for _ in range(100):
            token_governor.record("t0", prompt_tokens=10000, eval_tokens=5000)
        assert token_governor.is_available("t0")

    tmp.unlink()


def test_format_report():
    """Format report should return a string with budget info."""
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
        tmp = Path(f.name)

    with patch.object(token_governor, "USAGE_PATH", tmp):
        report = token_governor.format_report()
        assert "Token Budget" in report
        assert "T0" in report or "Nemotron" in report

    tmp.unlink()
