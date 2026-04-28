"""
Tests for the unified position sizing module.

Covers:
- Kelly Criterion computation (raw + capped)
- Volatility multiplier bands
- Drawdown multiplier bands
- Full position sizing pipeline (confidence, vol, DD, regime, stage)
- Stage multiplier application
- Edge cases (zero balance, negative inputs, NaN guards)
- Environment variable overrides
- Exposure cap enforcement
- Minimum position enforcement
"""

import importlib.util
import sys
from pathlib import Path

import pytest

ROOT_DIR = Path(__file__).resolve().parents[2]
SIZING_PATH = ROOT_DIR / "lib/core/src/sapphire_core/position_sizing.py"
ALPHA_ENGINE_ROOT = ROOT_DIR / "lib/core/src"


def _load_sizing_module():
    mod_name = "sapphire_position_sizing"
    if mod_name in sys.modules:
        return sys.modules[mod_name]
    if str(ALPHA_ENGINE_ROOT) not in sys.path:
        sys.path.insert(0, str(ALPHA_ENGINE_ROOT))
    spec = importlib.util.spec_from_file_location(mod_name, SIZING_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    # Register before exec so @dataclass can resolve __module__
    sys.modules[mod_name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def sizing():
    return _load_sizing_module()


# ───────────────────────────────────────────────────────────────────
# Kelly Criterion
# ───────────────────────────────────────────────────────────────────


class TestComputeKelly:
    def test_basic_kelly(self, sizing):
        """Standard 55% WR, 2:1 RR → f* = 0.55 - 0.45/2 = 0.325"""
        raw, capped = sizing.compute_kelly(0.55, 2.0, cap=0.25)
        assert raw == pytest.approx(0.325, abs=0.001)
        assert capped == 0.25  # capped

    def test_exact_at_cap(self, sizing):
        """When raw Kelly equals cap, capped == raw."""
        raw, capped = sizing.compute_kelly(0.55, 2.0, cap=0.5)
        assert capped == pytest.approx(0.325, abs=0.001)

    def test_high_edge(self, sizing):
        """70% WR, 3:1 RR → f* = 0.70 - 0.30/3 = 0.60"""
        raw, capped = sizing.compute_kelly(0.70, 3.0, cap=0.25)
        assert raw == pytest.approx(0.60, abs=0.01)
        assert capped == 0.25  # capped at max

    def test_negative_edge(self, sizing):
        """30% WR, 1:1 RR → f* = 0.30 - 0.70/1 = -0.40 → capped at 0"""
        raw, capped = sizing.compute_kelly(0.30, 1.0, cap=0.25)
        assert raw < 0
        assert capped == 0.0

    def test_breakeven_edge(self, sizing):
        """50% WR, 1:1 RR → f* = 0.50 - 0.50/1 = 0.0"""
        raw, capped = sizing.compute_kelly(0.50, 1.0)
        assert raw == pytest.approx(0.0, abs=0.001)
        assert capped == 0.0

    def test_zero_win_rate(self, sizing):
        raw, capped = sizing.compute_kelly(0.0, 2.0)
        assert raw < 0
        assert capped == 0.0

    def test_100_pct_win_rate(self, sizing):
        raw, capped = sizing.compute_kelly(1.0, 2.0, cap=0.5)
        assert raw == pytest.approx(1.0, abs=0.001)
        assert capped == 0.5

    def test_near_zero_rr_ratio(self, sizing):
        """Near-zero RR is clamped to 0.01 minimum."""
        raw, capped = sizing.compute_kelly(0.55, 0.0)
        # 0.55 - 0.45/0.01 = 0.55 - 45 = -44.45
        assert raw < 0
        assert capped == 0.0

    def test_win_rate_clamped_above_1(self, sizing):
        """Win rate > 1.0 is clamped."""
        raw, capped = sizing.compute_kelly(1.5, 2.0)
        # Clamped to 1.0: f* = 1.0 - 0.0/2.0 = 1.0
        assert raw == pytest.approx(1.0, abs=0.001)

    def test_negative_win_rate_clamped(self, sizing):
        raw, capped = sizing.compute_kelly(-0.5, 2.0)
        assert capped == 0.0


# ───────────────────────────────────────────────────────────────────
# Volatility multiplier
# ───────────────────────────────────────────────────────────────────


class TestVolatilityMultiplier:
    def test_low_vol(self, sizing):
        """Below medium threshold → 1.0"""
        result = sizing.compute_volatility_multiplier(0.01)
        assert result == 1.0

    def test_medium_vol(self, sizing):
        """Between medium and high thresholds → 0.85"""
        result = sizing.compute_volatility_multiplier(0.035)
        assert result == pytest.approx(0.85, abs=0.01)

    def test_high_vol(self, sizing):
        """Above high threshold → 0.70"""
        result = sizing.compute_volatility_multiplier(0.06)
        assert result == pytest.approx(0.70, abs=0.01)

    def test_exact_medium_boundary(self, sizing):
        """At exactly the medium threshold → medium multiplier"""
        cfg = sizing.SizingConfig()
        result = sizing.compute_volatility_multiplier(cfg.medium_vol_threshold, cfg)
        assert result == cfg.medium_vol_multiplier

    def test_exact_high_boundary(self, sizing):
        """At exactly the high threshold → high multiplier"""
        cfg = sizing.SizingConfig()
        result = sizing.compute_volatility_multiplier(cfg.high_vol_threshold, cfg)
        assert result == cfg.high_vol_multiplier

    def test_zero_vol(self, sizing):
        result = sizing.compute_volatility_multiplier(0.0)
        assert result == 1.0

    def test_custom_config(self, sizing):
        cfg = sizing.SizingConfig(
            high_vol_threshold=0.10,
            high_vol_multiplier=0.50,
            medium_vol_threshold=0.05,
            medium_vol_multiplier=0.75,
        )
        assert sizing.compute_volatility_multiplier(0.12, cfg) == 0.50
        assert sizing.compute_volatility_multiplier(0.07, cfg) == 0.75
        assert sizing.compute_volatility_multiplier(0.02, cfg) == 1.0


# ───────────────────────────────────────────────────────────────────
# Drawdown multiplier
# ───────────────────────────────────────────────────────────────────


class TestDrawdownMultiplier:
    def test_no_drawdown(self, sizing):
        result = sizing.compute_drawdown_multiplier(0.0)
        assert result == 1.0

    def test_moderate_drawdown(self, sizing):
        """Between moderate and severe thresholds → 0.75"""
        result = sizing.compute_drawdown_multiplier(0.07)
        assert result == pytest.approx(0.75, abs=0.01)

    def test_severe_drawdown(self, sizing):
        """Above severe threshold → 0.50"""
        result = sizing.compute_drawdown_multiplier(0.15)
        assert result == pytest.approx(0.50, abs=0.01)

    def test_exact_moderate_boundary(self, sizing):
        cfg = sizing.SizingConfig()
        result = sizing.compute_drawdown_multiplier(cfg.moderate_dd_threshold, cfg)
        assert result == cfg.moderate_dd_multiplier

    def test_exact_severe_boundary(self, sizing):
        cfg = sizing.SizingConfig()
        result = sizing.compute_drawdown_multiplier(cfg.severe_dd_threshold, cfg)
        assert result == cfg.severe_dd_multiplier

    def test_small_drawdown_below_threshold(self, sizing):
        result = sizing.compute_drawdown_multiplier(0.02)
        assert result == 1.0


# ───────────────────────────────────────────────────────────────────
# Full position sizing pipeline
# ───────────────────────────────────────────────────────────────────


class TestComputePositionSize:
    def test_basic_kelly_sizing(self, sizing):
        inp = sizing.SizingInput(
            balance=10000.0,
            confidence=0.5,
            execution_stage="full_live",
        )
        result = sizing.compute_position_size(inp)
        assert result.position_usd > 0
        assert result.position_pct > 0
        assert result.method == "kelly"
        assert result.stage_mult == 1.0
        assert result.confidence_mult == 1.0  # 0.5 + 0.5 = 1.0

    def test_zero_balance(self, sizing):
        inp = sizing.SizingInput(balance=0.0)
        result = sizing.compute_position_size(inp)
        assert result.position_usd == 0.0
        assert result.position_pct == 0.0
        assert result.capped_reason == "zero_balance"

    def test_negative_balance(self, sizing):
        inp = sizing.SizingInput(balance=-500.0)
        result = sizing.compute_position_size(inp)
        assert result.position_usd == 0.0
        assert result.capped_reason == "zero_balance"

    def test_paper_stage_zeros_position(self, sizing):
        inp = sizing.SizingInput(
            balance=10000.0,
            confidence=0.5,
            execution_stage="paper",
        )
        result = sizing.compute_position_size(inp)
        # Paper stage multiplier is 0.0, so position should be zero
        assert result.position_usd == 0.0
        assert result.stage_mult == 0.0

    def test_staged_live_reduces_position(self, sizing):
        # Use a large max_position_pct so the cap doesn't mask the stage effect
        cfg = sizing.SizingConfig(max_position_pct=0.50)
        inp_full = sizing.SizingInput(
            balance=10000.0,
            confidence=0.5,
            execution_stage="full_live",
        )
        inp_staged = sizing.SizingInput(
            balance=10000.0,
            confidence=0.5,
            execution_stage="staged_live",
        )
        full = sizing.compute_position_size(inp_full, cfg=cfg)
        staged = sizing.compute_position_size(inp_staged, cfg=cfg)
        # Staged should be 25% of full
        if full.position_usd > 0 and staged.position_usd > 0:
            assert staged.position_usd == pytest.approx(full.position_usd * 0.25, rel=0.01)

    def test_confidence_scaling(self, sizing):
        """Higher confidence → larger position (use high cap to avoid masking)."""
        cfg = sizing.SizingConfig(max_position_pct=0.50)
        lo = sizing.SizingInput(balance=10000.0, confidence=0.0, execution_stage="full_live")
        hi = sizing.SizingInput(balance=10000.0, confidence=1.0, execution_stage="full_live")
        result_lo = sizing.compute_position_size(lo, cfg=cfg)
        result_hi = sizing.compute_position_size(hi, cfg=cfg)
        # Confidence mult: lo = 0.5, hi = 1.5 → 3x ratio
        assert result_lo.confidence_mult == pytest.approx(0.5, abs=0.01)
        assert result_hi.confidence_mult == pytest.approx(1.5, abs=0.01)
        if result_lo.position_usd > 0:
            assert result_hi.position_usd > result_lo.position_usd

    def test_high_volatility_reduces_size(self, sizing):
        cfg = sizing.SizingConfig(max_position_pct=0.50)
        calm = sizing.SizingInput(
            balance=10000.0, confidence=0.5, volatility=0.01, execution_stage="full_live"
        )
        volatile = sizing.SizingInput(
            balance=10000.0, confidence=0.5, volatility=0.06, execution_stage="full_live"
        )
        result_calm = sizing.compute_position_size(calm, cfg=cfg)
        result_volatile = sizing.compute_position_size(volatile, cfg=cfg)
        assert result_volatile.volatility_mult < result_calm.volatility_mult
        if result_calm.position_usd > 0 and result_volatile.position_usd > 0:
            assert result_volatile.position_usd < result_calm.position_usd

    def test_drawdown_reduces_size(self, sizing):
        cfg = sizing.SizingConfig(max_position_pct=0.50)
        normal = sizing.SizingInput(
            balance=10000.0, confidence=0.5, drawdown_pct=0.0, execution_stage="full_live"
        )
        in_dd = sizing.SizingInput(
            balance=10000.0, confidence=0.5, drawdown_pct=0.12, execution_stage="full_live"
        )
        result_normal = sizing.compute_position_size(normal, cfg=cfg)
        result_dd = sizing.compute_position_size(in_dd, cfg=cfg)
        assert result_dd.drawdown_mult < result_normal.drawdown_mult
        if result_normal.position_usd > 0 and result_dd.position_usd > 0:
            assert result_dd.position_usd < result_normal.position_usd

    def test_regime_trending_up_boosts(self, sizing):
        base = sizing.SizingInput(
            balance=10000.0,
            confidence=0.5,
            regime=sizing.MarketRegime.UNKNOWN,
            execution_stage="full_live",
        )
        trending = sizing.SizingInput(
            balance=10000.0,
            confidence=0.5,
            regime=sizing.MarketRegime.TRENDING_UP,
            execution_stage="full_live",
        )
        r_base = sizing.compute_position_size(base)
        r_trend = sizing.compute_position_size(trending)
        assert r_trend.regime_mult > r_base.regime_mult

    def test_regime_volatile_reduces(self, sizing):
        base = sizing.SizingInput(
            balance=10000.0,
            confidence=0.5,
            regime=sizing.MarketRegime.UNKNOWN,
            execution_stage="full_live",
        )
        vol_regime = sizing.SizingInput(
            balance=10000.0,
            confidence=0.5,
            regime=sizing.MarketRegime.VOLATILE,
            execution_stage="full_live",
        )
        r_base = sizing.compute_position_size(base)
        r_vol = sizing.compute_position_size(vol_regime)
        assert r_vol.regime_mult < r_base.regime_mult

    def test_max_position_pct_cap(self, sizing):
        """Enormous confidence + trending → still capped at max_position_pct."""
        cfg = sizing.SizingConfig(max_position_pct=0.05)
        inp = sizing.SizingInput(
            balance=10000.0,
            confidence=1.0,
            regime=sizing.MarketRegime.TRENDING_UP,
            execution_stage="full_live",
        )
        result = sizing.compute_position_size(inp, cfg=cfg)
        assert result.position_pct <= 0.05
        if result.capped_reason:
            assert result.capped_reason in ("max_position_pct", "below_minimum")

    def test_exposure_cap(self, sizing):
        """When current exposure nears max, position is constrained."""
        inp = sizing.SizingInput(
            balance=10000.0,
            confidence=0.5,
            execution_stage="full_live",
            current_exposure=4900.0,  # 49% of balance, max default is 50%
        )
        result = sizing.compute_position_size(inp)
        # Remaining capacity = 10000 * 0.50 - 4900 = 100
        assert result.position_usd <= 100.0

    def test_full_exposure_blocks(self, sizing):
        """When fully exposed, position is zero."""
        inp = sizing.SizingInput(
            balance=10000.0,
            confidence=0.5,
            execution_stage="full_live",
            current_exposure=5000.0,  # Exactly at 50% cap
        )
        result = sizing.compute_position_size(inp)
        assert result.position_usd == 0.0

    def test_below_minimum_returns_zero(self, sizing):
        """Tiny position below minimum → capped at zero."""
        cfg = sizing.SizingConfig(min_position_usd=100.0)
        inp = sizing.SizingInput(
            balance=100.0,
            confidence=0.1,
            execution_stage="staged_live",  # 0.25 multiplier
        )
        result = sizing.compute_position_size(inp, cfg=cfg)
        # Very small position will be below $100 min
        assert result.position_usd == 0.0
        assert result.capped_reason == "below_minimum"

    def test_volatility_method(self, sizing):
        inp = sizing.SizingInput(
            balance=10000.0,
            confidence=0.5,
            volatility=0.02,
            execution_stage="full_live",
        )
        result = sizing.compute_position_size(inp, method=sizing.SizingMethod.VOLATILITY)
        assert result.method == "volatility"
        assert result.position_usd > 0

    def test_fixed_pct_method(self, sizing):
        inp = sizing.SizingInput(
            balance=10000.0,
            confidence=0.5,
            execution_stage="full_live",
        )
        result = sizing.compute_position_size(inp, method=sizing.SizingMethod.FIXED_PCT)
        assert result.method == "fixed_pct"
        assert result.position_usd > 0

    def test_custom_win_rate_and_rr(self, sizing):
        """Overriding win rate and RR in input should affect Kelly."""
        default_inp = sizing.SizingInput(
            balance=10000.0,
            confidence=0.5,
            execution_stage="full_live",
        )
        custom_inp = sizing.SizingInput(
            balance=10000.0,
            confidence=0.5,
            execution_stage="full_live",
            win_rate=0.70,
            rr_ratio=3.0,
        )
        r_default = sizing.compute_position_size(default_inp)
        r_custom = sizing.compute_position_size(custom_inp)
        # Custom has better edge, so kelly_raw should be higher
        assert r_custom.kelly_raw > r_default.kelly_raw

    def test_result_fields_populated(self, sizing):
        inp = sizing.SizingInput(
            balance=10000.0,
            confidence=0.5,
            volatility=0.04,
            drawdown_pct=0.06,
            regime=sizing.MarketRegime.TRENDING_UP,
            execution_stage="full_live",
        )
        result = sizing.compute_position_size(inp)
        assert isinstance(result.position_usd, float)
        assert isinstance(result.position_pct, float)
        assert isinstance(result.kelly_raw, float)
        assert isinstance(result.kelly_capped, float)
        assert isinstance(result.volatility_mult, float)
        assert isinstance(result.drawdown_mult, float)
        assert isinstance(result.regime_mult, float)
        assert isinstance(result.stage_mult, float)
        assert isinstance(result.confidence_mult, float)
        assert isinstance(result.method, str)


# ───────────────────────────────────────────────────────────────────
# Stage multiplier application
# ───────────────────────────────────────────────────────────────────


class TestApplyStageMultiplier:
    def test_paper_zeros(self, sizing):
        result = sizing.apply_stage_multiplier(100.0, "paper")
        assert result == 0.0

    def test_staged_live(self, sizing):
        result = sizing.apply_stage_multiplier(100.0, "staged_live")
        assert result == pytest.approx(25.0, abs=0.01)

    def test_full_live(self, sizing):
        result = sizing.apply_stage_multiplier(100.0, "full_live")
        assert result == pytest.approx(100.0, abs=0.01)

    def test_unknown_stage_defaults_to_zero(self, sizing):
        """Unknown stage → fails closed to 0 (paper). A typo in the stage
        string must never promote an order to full_live."""
        result = sizing.apply_stage_multiplier(100.0, "unknown_stage")
        assert result == pytest.approx(0.0, abs=0.01)

    def test_override_multiplier(self, sizing):
        result = sizing.apply_stage_multiplier(100.0, "paper", multiplier_override=0.5)
        assert result == pytest.approx(50.0, abs=0.01)

    def test_override_zero(self, sizing):
        result = sizing.apply_stage_multiplier(100.0, "full_live", multiplier_override=0.0)
        assert result == 0.0

    def test_override_negative_clamped(self, sizing):
        """Negative override → clamped to 0.0."""
        result = sizing.apply_stage_multiplier(100.0, "full_live", multiplier_override=-0.5)
        assert result == 0.0

    def test_fractional_quantity(self, sizing):
        result = sizing.apply_stage_multiplier(0.123456789, "staged_live")
        # 0.123456789 * 0.25 = 0.030864...
        assert result == pytest.approx(0.030864, abs=0.000001)

    def test_large_quantity(self, sizing):
        result = sizing.apply_stage_multiplier(1_000_000.0, "staged_live")
        assert result == pytest.approx(250_000.0, abs=0.01)


# ───────────────────────────────────────────────────────────────────
# SizingConfig
# ───────────────────────────────────────────────────────────────────


class TestSizingConfig:
    def test_defaults(self, sizing):
        cfg = sizing.SizingConfig()
        assert cfg.default_win_rate == pytest.approx(0.55, abs=0.01)
        assert cfg.default_rr_ratio == pytest.approx(2.0, abs=0.01)
        assert cfg.kelly_cap == pytest.approx(0.25, abs=0.01)
        assert cfg.max_position_pct == pytest.approx(0.10, abs=0.01)
        assert cfg.max_total_exposure_pct == pytest.approx(0.50, abs=0.01)
        assert cfg.min_position_usd == pytest.approx(5.0, abs=0.01)

    def test_frozen(self, sizing):
        cfg = sizing.SizingConfig()
        with pytest.raises(AttributeError):
            cfg.kelly_cap = 0.5  # type: ignore

    def test_stage_multipliers(self, sizing):
        cfg = sizing.SizingConfig()
        assert cfg.stage_multipliers["paper"] == 0.0
        assert cfg.stage_multipliers["staged_live"] == pytest.approx(0.25, abs=0.01)
        assert cfg.stage_multipliers["full_live"] == pytest.approx(1.0, abs=0.01)

    def test_custom_config(self, sizing):
        cfg = sizing.SizingConfig(
            kelly_cap=0.30,
            max_position_pct=0.20,
            min_position_usd=10.0,
        )
        assert cfg.kelly_cap == 0.30
        assert cfg.max_position_pct == 0.20
        assert cfg.min_position_usd == 10.0


# ───────────────────────────────────────────────────────────────────
# Enums
# ───────────────────────────────────────────────────────────────────


class TestEnums:
    def test_sizing_method_values(self, sizing):
        assert sizing.SizingMethod.KELLY.value == "kelly"
        assert sizing.SizingMethod.VOLATILITY.value == "volatility"
        assert sizing.SizingMethod.FIXED_PCT.value == "fixed_pct"

    def test_market_regime_values(self, sizing):
        assert sizing.MarketRegime.TRENDING_UP.value == "trending_up"
        assert sizing.MarketRegime.VOLATILE.value == "volatile"
        assert sizing.MarketRegime.UNKNOWN.value == "unknown"

    def test_all_regimes_have_multipliers(self, sizing):
        """Every regime enum has a corresponding multiplier."""
        for regime in sizing.MarketRegime:
            assert regime in sizing.REGIME_MULTIPLIERS


# ───────────────────────────────────────────────────────────────────
# Environment variable overrides
# ───────────────────────────────────────────────────────────────────


class TestEnvOverrides:
    def test_env_float_valid(self, sizing, monkeypatch):
        monkeypatch.setenv("SIZING_KELLY_CAP", "0.35")
        # Need to create a new config to pick up env vars
        cfg = sizing.SizingConfig(kelly_cap=sizing._env_float("SIZING_KELLY_CAP", 0.25))
        assert cfg.kelly_cap == pytest.approx(0.35, abs=0.01)

    def test_env_float_invalid(self, sizing, monkeypatch):
        monkeypatch.setenv("SIZING_KELLY_CAP", "not_a_number")
        result = sizing._env_float("SIZING_KELLY_CAP", 0.25)
        assert result == 0.25  # falls back to default

    def test_env_int_valid(self, sizing, monkeypatch):
        monkeypatch.setenv("SOME_INT", "42")
        result = sizing._env_int("SOME_INT", 10)
        assert result == 42

    def test_env_int_invalid(self, sizing, monkeypatch):
        monkeypatch.setenv("SOME_INT", "bad")
        result = sizing._env_int("SOME_INT", 10)
        assert result == 10


# ───────────────────────────────────────────────────────────────────
# Edge cases & integration scenarios
# ───────────────────────────────────────────────────────────────────


class TestEdgeCases:
    def test_all_multipliers_stack(self, sizing):
        """Worst case: high vol, severe drawdown, volatile regime, staged, low confidence."""
        inp = sizing.SizingInput(
            balance=10000.0,
            confidence=0.0,  # 0.5x
            volatility=0.06,  # 0.70x
            drawdown_pct=0.12,  # 0.50x
            regime=sizing.MarketRegime.VOLATILE,  # 0.70x
            execution_stage="staged_live",  # 0.25x
        )
        result = sizing.compute_position_size(inp)
        # With all negative multipliers stacked, position should be small
        # Kelly base 25% * 0.5 * 0.70 * 0.50 * 0.70 * 0.25 = ~0.77% → $76.56
        assert result.position_usd < 100.0

    def test_all_multipliers_boost(self, sizing):
        """Best case: calm, trending up, full live, high confidence."""
        inp = sizing.SizingInput(
            balance=10000.0,
            confidence=1.0,  # 1.5x
            volatility=0.01,  # 1.0x
            drawdown_pct=0.0,  # 1.0x
            regime=sizing.MarketRegime.TRENDING_UP,  # 1.2x
            execution_stage="full_live",  # 1.0x
            win_rate=0.65,
            rr_ratio=2.5,
        )
        result = sizing.compute_position_size(inp)
        # Should hit the max position cap
        assert result.position_pct <= sizing.DEFAULT_CONFIG.max_position_pct

    def test_tiny_balance(self, sizing):
        inp = sizing.SizingInput(
            balance=1.0,
            confidence=0.5,
            execution_stage="full_live",
        )
        result = sizing.compute_position_size(inp)
        # $1 * ~10% = $0.10 which is below $5 min
        assert result.position_usd == 0.0
        assert result.capped_reason == "below_minimum"

    def test_very_large_balance(self, sizing):
        inp = sizing.SizingInput(
            balance=10_000_000.0,
            confidence=0.5,
            execution_stage="full_live",
        )
        result = sizing.compute_position_size(inp)
        assert result.position_usd > 0
        assert result.position_pct <= sizing.DEFAULT_CONFIG.max_position_pct

    def test_volatility_method_high_vol(self, sizing):
        """Volatility method with very high vol → small position."""
        inp = sizing.SizingInput(
            balance=10000.0,
            confidence=0.5,
            volatility=0.10,  # 10% vol
            execution_stage="full_live",
        )
        result = sizing.compute_position_size(inp, method=sizing.SizingMethod.VOLATILITY)
        # 0.01/0.10 = 0.10, but capped at max_position_pct (0.10)
        assert result.position_pct <= 0.10

    def test_volatility_method_low_vol(self, sizing):
        """Volatility method with tiny vol → larger position (capped)."""
        inp = sizing.SizingInput(
            balance=10000.0,
            confidence=0.5,
            volatility=0.005,  # 0.5% vol
            execution_stage="full_live",
        )
        result = sizing.compute_position_size(inp, method=sizing.SizingMethod.VOLATILITY)
        assert result.position_usd > 0

    def test_exposure_exactly_at_cap(self, sizing):
        """Exposure exactly at the cap → remaining capacity is 0."""
        cfg = sizing.SizingConfig(max_total_exposure_pct=0.50)
        inp = sizing.SizingInput(
            balance=10000.0,
            confidence=0.5,
            execution_stage="full_live",
            current_exposure=5000.0,
        )
        result = sizing.compute_position_size(inp, cfg=cfg)
        assert result.position_usd == 0.0

    def test_exposure_over_cap(self, sizing):
        """Already over-exposed → no new position."""
        inp = sizing.SizingInput(
            balance=10000.0,
            confidence=0.5,
            execution_stage="full_live",
            current_exposure=6000.0,  # 60% > 50% cap
        )
        result = sizing.compute_position_size(inp)
        assert result.position_usd == 0.0

    def test_default_config_singleton(self, sizing):
        """DEFAULT_CONFIG is a module-level singleton."""
        assert sizing.DEFAULT_CONFIG is not None
        assert isinstance(sizing.DEFAULT_CONFIG, sizing.SizingConfig)


# ───────────────────────────────────────────────────────────────────
# SizingInput defaults
# ───────────────────────────────────────────────────────────────────


class TestSizingInput:
    def test_defaults(self, sizing):
        inp = sizing.SizingInput(balance=1000.0)
        assert inp.balance == 1000.0
        assert inp.confidence == 0.5
        assert inp.volatility == 0.0
        assert inp.drawdown_pct == 0.0
        assert inp.win_rate == 0.0
        assert inp.rr_ratio == 0.0
        assert inp.regime == sizing.MarketRegime.UNKNOWN
        assert inp.execution_stage == "full_live"
        assert inp.current_exposure == 0.0

    def test_all_fields(self, sizing):
        inp = sizing.SizingInput(
            balance=5000.0,
            confidence=0.8,
            volatility=0.03,
            drawdown_pct=0.05,
            win_rate=0.60,
            rr_ratio=2.5,
            regime=sizing.MarketRegime.TRENDING_UP,
            execution_stage="staged_live",
            current_exposure=1000.0,
        )
        assert inp.balance == 5000.0
        assert inp.confidence == 0.8
        assert inp.volatility == 0.03


# ───────────────────────────────────────────────────────────────────
# Regime multiplier table
# ───────────────────────────────────────────────────────────────────


class TestRegimeMultipliers:
    def test_trending_up(self, sizing):
        assert sizing.REGIME_MULTIPLIERS[sizing.MarketRegime.TRENDING_UP] == 1.2

    def test_trending_down(self, sizing):
        assert sizing.REGIME_MULTIPLIERS[sizing.MarketRegime.TRENDING_DOWN] == 1.2

    def test_volatile(self, sizing):
        assert sizing.REGIME_MULTIPLIERS[sizing.MarketRegime.VOLATILE] == 0.7

    def test_calm(self, sizing):
        assert sizing.REGIME_MULTIPLIERS[sizing.MarketRegime.CALM] == 1.1

    def test_ranging(self, sizing):
        assert sizing.REGIME_MULTIPLIERS[sizing.MarketRegime.RANGING] == 0.8

    def test_unknown(self, sizing):
        assert sizing.REGIME_MULTIPLIERS[sizing.MarketRegime.UNKNOWN] == 1.0
