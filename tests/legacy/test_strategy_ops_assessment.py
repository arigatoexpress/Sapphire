import pytest

pytest.skip("Legacy test — depends on removed module", allow_module_level=True)
pytestmark = pytest.mark.skip(reason="Legacy test — depends on removed module")
import importlib.util
from pathlib import Path

MODULE_PATH = Path(__file__).resolve().parents[2] / "services" / "unified-frontend" / "strategy_ops" / "assessment.py"
spec = importlib.util.spec_from_file_location("strategy_ops_assessment", MODULE_PATH)
module = importlib.util.module_from_spec(spec)
assert spec is not None and spec.loader is not None
spec.loader.exec_module(module)


def test_assessment_blocks_when_sample_size_too_low(monkeypatch):
    monkeypatch.delenv("STRATEGY_OPS_GONOGO_MIN_SAMPLE_SIZE", raising=False)
    result = module.build_strategy_ops_assessment(
        scorecard={"totals": {"sample_size": 8}, "ranked": []},
        reject_tax={"sample_size": 8, "reject_tax_pct": 10.0, "hard_fail_pct": 0.0},
    )
    assert result["go"] is False
    assert result["label"] == "NO-GO"
    assert "sample_size 8 < 30" in result["reasons"]


def test_assessment_allows_go_when_thresholds_pass():
    result = module.build_strategy_ops_assessment(
        scorecard={
            "totals": {"sample_size": 80, "reject_tax_pct": 22.0, "hard_fail_pct": 3.0},
            "ranked": [
                {"strategy": "overnight_ema_crossover", "timeframe": "5m", "recommendation": "promote"},
                {"strategy": "overnight_ema_crossover", "timeframe": "15m", "recommendation": "monitor"},
            ],
        },
        reject_tax={"sample_size": 80, "reject_tax_pct": 22.0, "hard_fail_pct": 3.0},
    )
    assert result["go"] is True
    assert result["label"] == "GO"
    assert result["promote_candidates"] == 1
    assert result["top_promote_lane"] == "overnight_ema_crossover@5m"


def test_assessment_respects_env_threshold_overrides(monkeypatch):
    monkeypatch.setenv("STRATEGY_OPS_GONOGO_MAX_REJECT_TAX_PCT", "40")
    monkeypatch.setenv("STRATEGY_OPS_GONOGO_MAX_HARD_FAIL_PCT", "5")
    result = module.build_strategy_ops_assessment(
        scorecard={"totals": {"sample_size": 120}, "ranked": []},
        reject_tax={"sample_size": 120, "reject_tax_pct": 39.9, "hard_fail_pct": 5.1},
    )
    assert result["go"] is False
    assert "hard_fail 5.1% > 5.0%" in result["reasons"]
    assert result["thresholds"]["max_reject_tax_pct"] == 40.0
    assert result["thresholds"]["max_hard_fail_pct"] == 5.0
