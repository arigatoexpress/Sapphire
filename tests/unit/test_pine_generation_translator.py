"""Tests for lib.pine_generation.translator.

Coverage targets (per Tranche 5 Lane 8 spec):
- ≥ 24 cases.
- ≥ 3 cases per strategy class (5 prod classes + 2 base/params forms).
- Generated Pine parses through the validator.
- Parameter substitution correctness.
"""

from __future__ import annotations

import pytest

from lib.pine_generation import (
    SUPPORTED_STRATEGIES,
    PineParams,
    PineSpec,
    available_strategies,
    generate_pine,
    spec_from_backtest_row,
    validate_pine,
)
from lib.pine_generation.translator import (
    DEFAULT_BTC_REF,
    DEFAULT_SPY_REF,
    SYMBOL_PREFIX_MAP,
    _kelly_size,
)

# ---------------------------------------------------------------------------
# 1) Module-level surface
# ---------------------------------------------------------------------------


def test_supported_strategies_listed() -> None:
    assert "RegimeAwareRSI" in SUPPORTED_STRATEGIES
    assert "FundingRateContrarian" in SUPPORTED_STRATEGIES
    assert "CorrelationBreakout" in SUPPORTED_STRATEGIES
    assert "MultiTFMomentum" in SUPPORTED_STRATEGIES
    assert "SapphireComposite" in SUPPORTED_STRATEGIES
    assert "BaseStrategy" in SUPPORTED_STRATEGIES
    assert "StrategyParams" in SUPPORTED_STRATEGIES
    assert len(SUPPORTED_STRATEGIES) == 7


def test_available_strategies_returns_copy() -> None:
    a = available_strategies()
    b = available_strategies()
    assert a == b
    a.append("Mutated")
    # Should not affect the canonical list
    assert "Mutated" not in SUPPORTED_STRATEGIES


def test_pine_spec_validates_strategy() -> None:
    with pytest.raises(ValueError, match="Unsupported strategy"):
        PineSpec(strategy="DoesNotExist", symbol="BTC")


def test_pine_spec_validates_symbol() -> None:
    with pytest.raises(ValueError, match="symbol"):
        PineSpec(strategy="RegimeAwareRSI", symbol="")


def test_pine_spec_validates_initial_capital() -> None:
    with pytest.raises(ValueError, match="initial_capital"):
        PineSpec(strategy="RegimeAwareRSI", symbol="BTC", initial_capital=0.0)


def test_pine_spec_validates_commission() -> None:
    with pytest.raises(ValueError, match="commission_pct"):
        PineSpec(strategy="RegimeAwareRSI", symbol="BTC", commission_pct=2.5)


def test_pine_spec_resolved_title_default() -> None:
    spec = PineSpec(strategy="RegimeAwareRSI", symbol="BTC-USD")
    assert "RegimeAwareRSI" in spec.resolved_title
    assert "BTC-USD" in spec.resolved_title


def test_pine_spec_resolved_title_override() -> None:
    spec = PineSpec(strategy="RegimeAwareRSI", symbol="BTC", title="Custom Title")
    assert spec.resolved_title == "Custom Title"


def test_pine_spec_tv_symbol_known() -> None:
    spec = PineSpec(strategy="RegimeAwareRSI", symbol="BTC")
    assert spec.tv_symbol == SYMBOL_PREFIX_MAP["BTC"]


def test_pine_spec_tv_symbol_unknown_passthrough() -> None:
    spec = PineSpec(strategy="RegimeAwareRSI", symbol="ATOMUSD")
    assert spec.tv_symbol == "ATOMUSD"


def test_pine_params_from_dict_drops_unknown() -> None:
    p = PineParams.from_dict({"rsi_period": 21, "garbage_field": 42})
    assert p.rsi_period == 21


def test_pine_params_from_dict_type_error() -> None:
    with pytest.raises(TypeError):
        PineParams.from_dict("not a dict")  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# 2) RegimeAwareRSI (>= 3 cases)
# ---------------------------------------------------------------------------


def test_regime_aware_rsi_renders_and_validates() -> None:
    spec = PineSpec(strategy="RegimeAwareRSI", symbol="BTC-USD")
    src = generate_pine(spec)
    res = validate_pine(src)
    assert res.ok, f"errors: {res.errors}"
    assert "RegimeAwareRSI" in src
    assert "//@version=5" in src
    assert "strategy(" in src


def test_regime_aware_rsi_param_substitution() -> None:
    p = PineParams(rsi_period=21, sl_pct=0.03, tp_pct=0.12, regime_period=30)
    spec = PineSpec(strategy="RegimeAwareRSI", symbol="BTC", params=p)
    src = generate_pine(spec)
    # rsi_period=21 should appear in the generated input default
    assert "input.int(21," in src
    # regime_period default
    assert "input.int(30," in src
    # sl_pct as percent (3.00)
    assert "input.float(3.00," in src
    # tp_pct as percent (12.00)
    assert "input.float(12.00," in src


def test_regime_aware_rsi_uses_btc_reference() -> None:
    spec = PineSpec(strategy="RegimeAwareRSI", symbol="ETH-USD")
    src = generate_pine(spec)
    # Should reference the BTC symbol via request.security
    assert "request.security(" in src
    assert DEFAULT_BTC_REF in src


def test_regime_aware_rsi_custom_btc_ref() -> None:
    spec = PineSpec(
        strategy="RegimeAwareRSI",
        symbol="ETH-USD",
        btc_ref_symbol="BINANCE:BTCUSDT",
    )
    src = generate_pine(spec)
    assert "BINANCE:BTCUSDT" in src
    assert validate_pine(src).ok


# ---------------------------------------------------------------------------
# 3) FundingRateContrarian (>= 3 cases)
# ---------------------------------------------------------------------------


def test_funding_rate_contrarian_renders_and_validates() -> None:
    spec = PineSpec(strategy="FundingRateContrarian", symbol="BTC-USD")
    src = generate_pine(spec)
    res = validate_pine(src)
    assert res.ok, f"errors: {res.errors}"
    assert "FundingRateContrarian" in src
    # Should reference the 3-day momentum proxy
    assert "close[3]" in src


def test_funding_rate_contrarian_param_substitution() -> None:
    p = PineParams(funding_high=0.025, funding_low=-0.012, sl_pct=0.04, tp_pct=0.08)
    spec = PineSpec(strategy="FundingRateContrarian", symbol="ETH-USD", params=p)
    src = generate_pine(spec)
    assert "0.0250" in src  # funding_high
    assert "-0.0120" in src  # funding_low
    assert "input.float(4.00," in src  # sl_pct = 4.0%
    assert "input.float(8.00," in src  # tp_pct = 8.0%


def test_funding_rate_contrarian_handles_both_directions() -> None:
    spec = PineSpec(strategy="FundingRateContrarian", symbol="SOL-USD")
    src = generate_pine(spec)
    # Both long and short paths must exist (this is a contrarian strategy)
    assert "strategy.entry(\"Long\"" in src or 'strategy.entry("Long"' in src
    assert "strategy.entry(\"Short\"" in src or 'strategy.entry("Short"' in src


# ---------------------------------------------------------------------------
# 4) CorrelationBreakout (>= 3 cases)
# ---------------------------------------------------------------------------


def test_correlation_breakout_renders_and_validates() -> None:
    spec = PineSpec(strategy="CorrelationBreakout", symbol="BTC-USD")
    src = generate_pine(spec)
    res = validate_pine(src)
    assert res.ok, f"errors: {res.errors}"
    assert "CorrelationBreakout" in src


def test_correlation_breakout_uses_spy_reference() -> None:
    spec = PineSpec(strategy="CorrelationBreakout", symbol="BTC-USD")
    src = generate_pine(spec)
    assert DEFAULT_SPY_REF in src
    assert "ta.correlation(" in src


def test_correlation_breakout_param_substitution() -> None:
    p = PineParams(corr_period=30, corr_threshold=0.20, rsi_period=10)
    spec = PineSpec(strategy="CorrelationBreakout", symbol="BTC-USD", params=p)
    src = generate_pine(spec)
    assert "input.int(30," in src  # corr_period
    assert "0.2000" in src  # corr_threshold
    assert "input.int(10," in src  # rsi_period


# ---------------------------------------------------------------------------
# 5) MultiTFMomentum (>= 3 cases)
# ---------------------------------------------------------------------------


def test_multi_tf_momentum_renders_and_validates() -> None:
    spec = PineSpec(strategy="MultiTFMomentum", symbol="BTC-USD")
    src = generate_pine(spec)
    res = validate_pine(src)
    assert res.ok, f"errors: {res.errors}"
    assert "MultiTFMomentum" in src


def test_multi_tf_momentum_three_proxies_present() -> None:
    spec = PineSpec(strategy="MultiTFMomentum", symbol="ETH-USD")
    src = generate_pine(spec)
    # 4H proxy via fast RSI
    assert "ta.rsi(close, tf_fast)" in src
    # Daily MA via SMA(20)
    assert "ta.sma(close, 20)" in src
    # Weekly proxy via tf_slow lookback
    assert "close[tf_slow]" in src


def test_multi_tf_momentum_param_substitution() -> None:
    p = PineParams(tf_fast=10, tf_slow=7)
    spec = PineSpec(strategy="MultiTFMomentum", symbol="BTC-USD", params=p)
    src = generate_pine(spec)
    assert "input.int(10," in src  # tf_fast
    assert "input.int(7," in src  # tf_slow


# ---------------------------------------------------------------------------
# 6) SapphireComposite (>= 3 cases)
# ---------------------------------------------------------------------------


def test_sapphire_composite_renders_and_validates() -> None:
    spec = PineSpec(strategy="SapphireComposite", symbol="BTC-USD")
    src = generate_pine(spec)
    res = validate_pine(src)
    assert res.ok, f"errors: {res.errors}"
    assert "SapphireComposite" in src


def test_sapphire_composite_has_all_5_score_components() -> None:
    spec = PineSpec(strategy="SapphireComposite", symbol="BTC-USD")
    src = generate_pine(spec)
    # All five score components in the composite
    assert "regime_score" in src
    assert "rsi_depth_score" in src
    assert "funding_score" in src
    assert "corr_score" in src
    assert "tf_score" in src
    assert "composite_score" in src
    assert "composite_threshold" in src


def test_sapphire_composite_kelly_sizing() -> None:
    # 50% sl, 100% tp → quarter-Kelly = 0.25 * (0.55 - 0.45/2) = ~0.0813 → 8.13
    spec = PineSpec(
        strategy="SapphireComposite",
        symbol="BTC-USD",
        params=PineParams(sl_pct=0.05, tp_pct=0.10),
    )
    src = generate_pine(spec)
    # default_qty_value should be a positive float in the strategy() declaration.
    assert "default_qty_value=" in src
    # The kelly value depends on tp/sl ratio; must be at least the floor 5.0
    assert validate_pine(src).ok


def test_sapphire_composite_aux_symbols_present() -> None:
    spec = PineSpec(strategy="SapphireComposite", symbol="ETH-USD")
    src = generate_pine(spec)
    # Both BTC + SPY references exist
    assert DEFAULT_BTC_REF in src
    assert DEFAULT_SPY_REF in src
    # Two request.security calls
    assert src.count("request.security(") >= 2


# ---------------------------------------------------------------------------
# 7) BaseStrategy (>= 3 cases)
# ---------------------------------------------------------------------------


def test_base_strategy_renders_and_validates() -> None:
    spec = PineSpec(strategy="BaseStrategy", symbol="BTC-USD")
    src = generate_pine(spec)
    res = validate_pine(src)
    assert res.ok, f"errors: {res.errors}"


def test_base_strategy_no_aux_data() -> None:
    """BaseStrategy should not pull aux symbols (it's RSI-only)."""
    spec = PineSpec(strategy="BaseStrategy", symbol="BTC-USD")
    src = generate_pine(spec)
    # Should not call request.security (no BTC/SPY aux)
    assert "request.security(" not in src


def test_base_strategy_param_substitution() -> None:
    p = PineParams(rsi_period=7, sl_pct=0.02, tp_pct=0.05)
    spec = PineSpec(strategy="BaseStrategy", symbol="ETH-USD", params=p)
    src = generate_pine(spec)
    assert "input.int(7," in src  # rsi_period
    assert "input.float(2.00," in src  # sl 2%
    assert "input.float(5.00," in src  # tp 5%


# ---------------------------------------------------------------------------
# 8) StrategyParams (>= 3 cases)
# ---------------------------------------------------------------------------


def test_params_only_renders_and_validates() -> None:
    spec = PineSpec(strategy="StrategyParams", symbol="BTC-USD")
    src = generate_pine(spec)
    res = validate_pine(src)
    assert res.ok, f"errors: {res.errors}"


def test_params_only_has_all_inputs() -> None:
    spec = PineSpec(strategy="StrategyParams", symbol="BTC-USD")
    src = generate_pine(spec)
    # Every StrategyParams field has an input declaration in the params-only template
    for token in (
        "rsi_period",
        "sl_pct",
        "tp_pct",
        "regime_period",
        "regime_on_threshold",
        "regime_off_threshold",
        "funding_high",
        "funding_low",
        "corr_period",
        "corr_threshold",
        "tf_fast",
        "tf_slow",
        "composite_threshold",
    ):
        assert f"{token} " in src or f"{token}=" in src, f"missing {token}"


def test_params_only_param_substitution() -> None:
    p = PineParams(rsi_period=14, composite_threshold=70.0)
    spec = PineSpec(strategy="StrategyParams", symbol="BTC", params=p)
    src = generate_pine(spec)
    assert "input.int(14," in src
    assert "70.00" in src  # composite_threshold


# ---------------------------------------------------------------------------
# 9) End-to-end: every strategy validates clean
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("strategy", SUPPORTED_STRATEGIES)
def test_every_strategy_renders_and_validates(strategy: str) -> None:
    spec = PineSpec(strategy=strategy, symbol="BTC-USD")
    src = generate_pine(spec)
    result = validate_pine(src)
    assert result.ok, f"{strategy}: {result.errors}"


@pytest.mark.parametrize(
    "symbol,expected_prefix",
    [
        ("BTC", "CRYPTOCAP:"),
        ("ETH-USD", "BINANCE:"),
        ("SPY", "AMEX:"),
        ("TSLA", "NASDAQ:"),
        ("UNKNOWN_TICKER", ""),  # passthrough
    ],
)
def test_symbol_prefix_mapping(symbol: str, expected_prefix: str) -> None:
    spec = PineSpec(strategy="BaseStrategy", symbol=symbol)
    if expected_prefix:
        assert spec.tv_symbol.startswith(expected_prefix)
    else:
        assert spec.tv_symbol == symbol


# ---------------------------------------------------------------------------
# 10) spec_from_backtest_row
# ---------------------------------------------------------------------------


def test_spec_from_backtest_row_happy() -> None:
    row = {
        "strategy_cls": "SapphireComposite",
        "strategy_name": "SapphireComposite(p=14,sl=5%,tp=10%)",
        "symbol": "BTC-USD",
        "params": {"rsi_period": 14, "sl_pct": 0.05, "tp_pct": 0.10},
        "sortino": 2.4,
        "sharpe": 1.8,
        "win_rate": 0.62,
        "total_trades": 25,
    }
    spec = spec_from_backtest_row(row)
    assert spec.strategy == "SapphireComposite"
    assert spec.symbol == "BTC-USD"
    assert spec.params.rsi_period == 14
    assert spec.meta["sortino"] == 2.4


def test_spec_from_backtest_row_unsupported_strategy() -> None:
    row = {
        "strategy_cls": "GhostStrategy",
        "symbol": "BTC",
        "params": {},
    }
    with pytest.raises(ValueError, match="not a supported"):
        spec_from_backtest_row(row)


def test_spec_from_backtest_row_missing_symbol() -> None:
    row = {"strategy_cls": "RegimeAwareRSI", "params": {}}
    with pytest.raises(ValueError, match="symbol"):
        spec_from_backtest_row(row)


def test_spec_from_backtest_row_missing_strategy() -> None:
    row = {"symbol": "BTC"}
    with pytest.raises(ValueError, match="strategy_cls"):
        spec_from_backtest_row(row)


def test_spec_from_backtest_row_type_error() -> None:
    with pytest.raises(TypeError):
        spec_from_backtest_row("not a dict")  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# 11) Error paths
# ---------------------------------------------------------------------------


def test_generate_pine_type_error() -> None:
    with pytest.raises(TypeError):
        generate_pine("not a spec")  # type: ignore[arg-type]


def test_generate_pine_output_ends_with_newline() -> None:
    spec = PineSpec(strategy="BaseStrategy", symbol="BTC-USD")
    src = generate_pine(spec)
    assert src.endswith("\n")


def test_kelly_size_clamped() -> None:
    # Edge cases for the helper
    f = _kelly_size(sl_pct=0.05, tp_pct=0.10)
    assert 0.05 <= f <= 0.50

    f_zero_sl = _kelly_size(sl_pct=0.0, tp_pct=0.10)
    assert 0.05 <= f_zero_sl <= 0.50


def test_meta_field_propagates_into_spec() -> None:
    spec = PineSpec(
        strategy="RegimeAwareRSI",
        symbol="BTC",
        meta={"note": "hello"},
    )
    assert spec.meta == {"note": "hello"}


def test_spec_kelly_size_pct_override() -> None:
    """Custom kelly_size_pct is used in default_qty_value when supplied."""
    spec = PineSpec(
        strategy="SapphireComposite",
        symbol="BTC-USD",
        kelly_size_pct=42.0,
    )
    src = generate_pine(spec)
    # The kelly override should land in default_qty_value.
    assert "default_qty_value=42" in src


# ---------------------------------------------------------------------------
# 12) Coverage of the symbol-prefix map
# ---------------------------------------------------------------------------


def test_symbol_prefix_map_handles_lower_case() -> None:
    spec = PineSpec(strategy="BaseStrategy", symbol="btc")  # lowercase
    assert spec.tv_symbol == SYMBOL_PREFIX_MAP["BTC"]


def test_btc_ref_default() -> None:
    spec = PineSpec(strategy="RegimeAwareRSI", symbol="ETH-USD")
    assert spec.btc_ref_symbol == DEFAULT_BTC_REF


def test_spy_ref_default() -> None:
    spec = PineSpec(strategy="CorrelationBreakout", symbol="ETH-USD")
    assert spec.spy_ref_symbol == DEFAULT_SPY_REF
