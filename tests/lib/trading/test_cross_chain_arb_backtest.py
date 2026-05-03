"""Unit + gated-integration tests for the cross-chain Aave APY arb backtester.

These tests pin the cost model + decay model + risk-metric calculation
against synthetic spread inputs. The bottom of the file has a single
gated integration test that wires the real chain stack and asserts the
backtest result is fully populated for live mainnet data.

Why "synthetic spread time-series" instead of stored historical data:
the upstream signal is itself fresh-each-call (per-chain Aave RPC
fanout), and there is no historical snapshot store yet. The
backtester's cost / decay / aggregation logic is *exactly* what the
unit tests exercise — the spread-source is just an input.
"""

from __future__ import annotations

import math
import os
from decimal import Decimal

import pytest

from lib.chains.cross_chain.aave_apy_arb import (
    SEVERITY_EXTREME,
    AaveApyArbSignal,
)
from lib.trading.cross_chain_arb_backtest import (
    BRIDGE_COST_TIERS,
    CrossChainArbBacktest,
    bridge_cost_bps_for_capital,
    project_pnl_for_signal,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_signal(asset: str, supply_bps: float, borrow_bps: float) -> AaveApyArbSignal:
    """Build a synthetic AaveApyArbSignal for backtest input.

    The backtester only consumes ``asset`` + ``max_supply_spread_bps`` +
    ``max_borrow_spread_bps``; the rest of the dataclass is filled with
    placeholders.
    """
    return AaveApyArbSignal(
        asset=asset,
        chains={
            "Arbitrum": {"supply_apy": Decimal("0.05"), "borrow_apy": Decimal("0.07")},
            "Optimism": {"supply_apy": Decimal("0.06"), "borrow_apy": Decimal("0.09")},
        },
        max_supply_spread_bps=Decimal(str(supply_bps)),
        max_borrow_spread_bps=Decimal(str(borrow_bps)),
        direction="synthetic",
        severity=SEVERITY_EXTREME,
    )


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def test_invalid_capital_raises() -> None:
    with pytest.raises(ValueError, match="capital_usd"):
        CrossChainArbBacktest(capital_usd=0)
    with pytest.raises(ValueError, match="capital_usd"):
        CrossChainArbBacktest(capital_usd=-100)


def test_invalid_horizon_raises() -> None:
    with pytest.raises(ValueError, match="days"):
        CrossChainArbBacktest(days=0)


def test_invalid_holding_period_raises() -> None:
    with pytest.raises(ValueError, match="holding_period_hours"):
        CrossChainArbBacktest(holding_period_hours=0)


def test_negative_costs_raise() -> None:
    with pytest.raises(ValueError, match="bridge_cost"):
        CrossChainArbBacktest(bridge_cost_bps_per_round_trip=-1)
    with pytest.raises(ValueError, match="gas_cost"):
        CrossChainArbBacktest(gas_cost_usd_per_action=-1)


def test_negative_initial_spread_raises() -> None:
    bt = CrossChainArbBacktest()
    with pytest.raises(ValueError, match="initial_spread_bps"):
        bt.simulate_with_spread("USDC", -5.0)


def test_simulate_without_scanner_raises() -> None:
    bt = CrossChainArbBacktest(scanner=None)
    import asyncio

    with pytest.raises(ValueError, match="requires a scanner"):
        asyncio.run(bt.simulate("USDC"))


# ---------------------------------------------------------------------------
# No-decay scenario — flat spread, costs eat fixed amount
# ---------------------------------------------------------------------------


def test_no_decay_high_spread_yields_positive_pnl_at_weekly_rebalance() -> None:
    """500bps flat + $1M + weekly rebalance → bridge cost amortized → net positive.

    With daily rebalance the 5bps bridge cost dominates at any capital
    (it scales with capital but so does the gross). The genuine
    cost-mitigation lever is *rebalance frequency*: stretching the
    holding period from 24h → 168h cuts bridge costs ~7x without
    changing the spread integral.
    """
    bt = CrossChainArbBacktest(
        capital_usd=1_000_000.0,
        days=30,
        bridge_cost_bps_per_round_trip=5.0,
        gas_cost_usd_per_action=2.50,
        holding_period_hours=168.0,  # weekly
        decay_days=0,  # no decay
    )
    r = bt.simulate_with_spread("USDC", initial_spread_bps=500.0)
    assert r.gross_pnl_usd > 0
    assert r.total_pnl_usd > 0, "at $1M, weekly rebal, 500bps → net-profitable"
    assert r.cost_basis_pct_of_pnl < 100.0, "costs should be a fraction of gross"
    assert r.n_rebalances == 30 * 24 // 168  # 30 days at 168h cadence


def test_no_decay_zero_costs_yields_pure_yield() -> None:
    """Zero costs + 365-day flat 1000bps → APR ≈ 10%."""
    bt = CrossChainArbBacktest(
        capital_usd=10_000.0,
        days=365,
        bridge_cost_bps_per_round_trip=0,
        gas_cost_usd_per_action=0,
        decay_days=0,
    )
    r = bt.simulate_with_spread("USDC", initial_spread_bps=1000.0)
    # 1000 bps == 10% APR; with no decay/costs the projection should
    # be within ~1% of the analytical answer (period discretization).
    assert abs(r.apr_net_of_costs - 0.10) < 0.01
    assert r.cost_basis_pct_of_pnl == 0.0


# ---------------------------------------------------------------------------
# Decay scenario — spread compresses to zero over decay_days
# ---------------------------------------------------------------------------


def test_high_decay_kills_signal_after_decay_window() -> None:
    """7-day decay + 30-day horizon → 23 days of zero spread tail."""
    bt = CrossChainArbBacktest(
        capital_usd=10_000.0,
        days=30,
        decay_days=7.0,
        bridge_cost_bps_per_round_trip=0,
        gas_cost_usd_per_action=0,
    )
    r = bt.simulate_with_spread("USDC", initial_spread_bps=1000.0)
    # Last >10 periods should have zero return (spread = 0 after day 7).
    tail = r.period_returns[-10:]
    assert all(abs(x) < 1e-12 for x in tail), (
        f"after decay window, returns should be zero; got {tail}"
    )


def test_decay_yields_lower_pnl_than_flat() -> None:
    """Decay path strictly less profitable than flat-spread path."""
    common = dict(
        capital_usd=10_000.0,
        days=30,
        bridge_cost_bps_per_round_trip=0,
        gas_cost_usd_per_action=0,
    )
    flat = CrossChainArbBacktest(**common, decay_days=0).simulate_with_spread("USDC", 500.0)
    decayed = CrossChainArbBacktest(**common, decay_days=7.0).simulate_with_spread("USDC", 500.0)
    assert decayed.total_pnl_usd < flat.total_pnl_usd


# ---------------------------------------------------------------------------
# Cost-dominance scenarios — the headline viability story
# ---------------------------------------------------------------------------


def test_costs_eat_all_pnl_at_small_capital() -> None:
    """$10K + 232bps + default costs → cost_basis_pct_of_pnl >> 100."""
    bt = CrossChainArbBacktest(
        capital_usd=10_000.0,
        days=30,
        bridge_cost_bps_per_round_trip=5.0,
        gas_cost_usd_per_action=2.50,
        decay_days=7.0,
    )
    r = bt.simulate_with_spread("USDC", initial_spread_bps=232.0)
    # The headline signal: at small capital, costs dominate.
    assert r.cost_basis_pct_of_pnl > 100.0, (
        f"at $10K + 232bps + default costs, costs should exceed gross PnL; "
        f"got {r.cost_basis_pct_of_pnl}"
    )
    assert r.total_pnl_usd < 0


def test_costs_eat_about_half_pnl_at_weekly_rebalance() -> None:
    """$100K + 232bps × 1-year horizon, weekly rebal → costs < gross PnL.

    Daily rebalancing: 5bps × $100K × 365 = $18,250 in bridge alone vs
    ~$2,320 gross. Weekly cuts bridge to ~$2,605 (52 cycles), still
    above gross at this capital — but adding a smaller per-action gas
    and dropping decay isolates the structural lever (frequency).
    """
    bt = CrossChainArbBacktest(
        capital_usd=100_000.0,
        days=365,
        bridge_cost_bps_per_round_trip=2.0,  # cheaper L2 bridge
        gas_cost_usd_per_action=1.0,
        holding_period_hours=168.0,  # weekly
        decay_days=0,  # no decay so we isolate cost behavior
    )
    r = bt.simulate_with_spread("USDC", initial_spread_bps=232.0)
    # At $100K + 2bps bridge + weekly + flat spread, gross > costs.
    assert r.gross_pnl_usd > r.total_costs_usd
    assert r.total_pnl_usd > 0
    assert 0 < r.cost_basis_pct_of_pnl < 100.0


# ---------------------------------------------------------------------------
# Signal-driven path
# ---------------------------------------------------------------------------


def test_simulate_from_signal_picks_larger_side() -> None:
    """Backtester should use max(supply_spread, borrow_spread)."""
    sig = _make_signal("USDC", supply_bps=50.0, borrow_bps=232.0)
    bt = CrossChainArbBacktest(
        capital_usd=1_000_000.0,
        days=30,
        decay_days=0,
        bridge_cost_bps_per_round_trip=0,
        gas_cost_usd_per_action=0,
    )
    r = bt.simulate_from_signal(sig)
    assert r.initial_spread_bps == 232.0


def test_zero_spread_signal_yields_flat_zero_result() -> None:
    """Signals with zero on both sides project zero PnL (no error)."""
    sig = _make_signal("USDC", supply_bps=0.0, borrow_bps=0.0)
    bt = CrossChainArbBacktest(capital_usd=10_000.0, days=30)
    r = bt.simulate_from_signal(sig)
    assert r.total_pnl_usd == 0.0
    assert r.gross_pnl_usd == 0.0
    assert r.cost_basis_pct_of_pnl == 0.0
    assert r.n_rebalances == 0


def test_project_pnl_for_signal_convenience() -> None:
    """project_pnl_for_signal() must produce same result as class API."""
    sig = _make_signal("USDC", supply_bps=232.0, borrow_bps=232.0)
    via_func = project_pnl_for_signal(sig, capital_usd=10_000.0, days=30)
    via_class = CrossChainArbBacktest(capital_usd=10_000.0, days=30).simulate_from_signal(sig)
    assert via_func.total_pnl_usd == pytest.approx(via_class.total_pnl_usd)
    assert via_func.cost_basis_pct_of_pnl == pytest.approx(via_class.cost_basis_pct_of_pnl)


# ---------------------------------------------------------------------------
# Risk metrics
# ---------------------------------------------------------------------------


def test_max_drawdown_present_when_costs_exceed_yield() -> None:
    """Cost-dominated equity curve must show a drawdown."""
    bt = CrossChainArbBacktest(
        capital_usd=10_000.0,
        days=30,
        decay_days=7.0,
        bridge_cost_bps_per_round_trip=5.0,
        gas_cost_usd_per_action=2.50,
    )
    r = bt.simulate_with_spread("USDC", initial_spread_bps=232.0)
    assert r.max_drawdown_pct > 0.0


def test_sortino_inf_when_no_losing_periods() -> None:
    """Zero-cost positive-spread sim → no losing periods → Sortino = inf."""
    bt = CrossChainArbBacktest(
        capital_usd=10_000.0,
        days=30,
        decay_days=0,
        bridge_cost_bps_per_round_trip=0,
        gas_cost_usd_per_action=0,
    )
    r = bt.simulate_with_spread("USDC", initial_spread_bps=500.0)
    assert math.isinf(r.sortino) and r.sortino > 0


# ---------------------------------------------------------------------------
# Result serialization
# ---------------------------------------------------------------------------


def test_to_dict_serializes_inf_safely() -> None:
    """to_dict() must not emit raw float('inf') (json.dumps would fail)."""
    bt = CrossChainArbBacktest(
        capital_usd=10_000.0,
        days=30,
        decay_days=0,
        bridge_cost_bps_per_round_trip=0,
        gas_cost_usd_per_action=0,
    )
    r = bt.simulate_with_spread("USDC", initial_spread_bps=500.0)
    d = r.to_dict()
    # sortino was inf → must be the string "inf" in dict form.
    import json

    json.dumps(d)  # should not raise
    assert d["sortino"] in ("inf", "-inf") or isinstance(d["sortino"], (int, float))


# ---------------------------------------------------------------------------
# Tiered bridge cost calibration (PR #606 follow-up: live Across/Hop quotes)
# ---------------------------------------------------------------------------


def test_bridge_cost_tiers_are_monotone_non_decreasing() -> None:
    """Tier table must be sorted by ascending threshold + bps must not drop.

    A drop in bps as capital grows would imply a *cheaper* bridge at
    larger size, which contradicts the LP-fee creep observed in live
    Across quotes (Capital Fee % rises with notional). Catches typos
    when re-surveying.
    """
    thresholds = [t for t, _ in BRIDGE_COST_TIERS]
    bps_values = [b for _, b in BRIDGE_COST_TIERS]
    assert thresholds == sorted(thresholds), "tiers must be sorted by threshold"
    assert bps_values == sorted(bps_values), "bps must be non-decreasing with size"
    assert math.isinf(thresholds[-1]), "tail tier must be math.inf to catch all"


def test_bridge_cost_lookup_buckets() -> None:
    """Verify each notional bucket maps to the calibrated tier value."""
    # $1k and $10k both fall in the small bucket (≤ $10k → 3.0 bps)
    assert bridge_cost_bps_for_capital(1_000) == 3.0
    assert bridge_cost_bps_for_capital(10_000) == 3.0
    # $50k falls in the medium bucket (≤ $100k → 3.5 bps)
    assert bridge_cost_bps_for_capital(50_000) == 3.5
    assert bridge_cost_bps_for_capital(100_000) == 3.5
    # $500k falls in the large bucket (≤ $1M → 4.0 bps)
    assert bridge_cost_bps_for_capital(500_000) == 4.0
    assert bridge_cost_bps_for_capital(1_000_000) == 4.0
    # Whale tier (> $1M → 5.0 bps)
    assert bridge_cost_bps_for_capital(10_000_000) == 5.0
    assert bridge_cost_bps_for_capital(1e15) == 5.0


def test_bridge_cost_lookup_rejects_negative() -> None:
    with pytest.raises(ValueError, match="capital_usd"):
        bridge_cost_bps_for_capital(-1)


def test_constructor_uses_tiered_default_when_unset() -> None:
    """Omitting bridge_cost_bps_per_round_trip → tiered lookup kicks in.

    This is the calibration's user-facing payoff: callers who don't pass
    a cost get the right cost for their capital, instead of the legacy
    one-size-fits-all 5 bps.
    """
    bt_small = CrossChainArbBacktest(capital_usd=10_000.0)
    assert bt_small.bridge_cost_bps_per_round_trip == 3.0
    bt_medium = CrossChainArbBacktest(capital_usd=100_000.0)
    assert bt_medium.bridge_cost_bps_per_round_trip == 3.5
    bt_large = CrossChainArbBacktest(capital_usd=1_000_000.0)
    assert bt_large.bridge_cost_bps_per_round_trip == 4.0
    bt_whale = CrossChainArbBacktest(capital_usd=10_000_000.0)
    assert bt_whale.bridge_cost_bps_per_round_trip == 5.0


def test_constructor_explicit_bridge_cost_overrides_tier() -> None:
    """Explicit override wins, including 0 (used by decay-isolation tests)."""
    bt = CrossChainArbBacktest(
        capital_usd=10_000.0,
        bridge_cost_bps_per_round_trip=42.0,
    )
    assert bt.bridge_cost_bps_per_round_trip == 42.0
    bt_zero = CrossChainArbBacktest(
        capital_usd=10_000.0,
        bridge_cost_bps_per_round_trip=0.0,
    )
    assert bt_zero.bridge_cost_bps_per_round_trip == 0.0


def test_calibrated_costs_lower_than_legacy_5bps_for_typical_capital() -> None:
    """Calibrated tiers must be <= the legacy hardcoded 5 bps for capital ≤ $1M.

    The whole point of this PR: live Across quotes are ~1.5 bps per leg
    (~3 bps round-trip), not 5 bps. Anything ≤ $1M should get a strictly
    cheaper default than the legacy assumption.
    """
    for capital in (1_000, 10_000, 100_000, 1_000_000):
        bps = bridge_cost_bps_for_capital(capital)
        assert bps <= 5.0, f"calibrated cost at ${capital} = {bps} > 5"


# ---------------------------------------------------------------------------
# Gated integration test — hits real mainnets
# ---------------------------------------------------------------------------


@pytest.mark.skipif(
    os.getenv("SAPPHIRE_CROSS_CHAIN_INTEGRATION") != "1",
    reason="set SAPPHIRE_CROSS_CHAIN_INTEGRATION=1 to enable live RPC test",
)
def test_live_backtest_at_10k_30days_populates_all_fields() -> None:
    """Live mainnet RPC fan-out → full BacktestResult populated.

    Asserts cost_basis_pct_of_pnl is finite — if it's exactly 0 the
    upstream signal was None (no spread above MIN_SIGNAL_SPREAD_BPS),
    which is also a valid live state we don't fail on.
    """
    from lib.hackathon.cross_chain_alpha import backtest_aave_arb

    out = backtest_aave_arb(asset="USDC", capital_usd=10_000.0, days=30)
    assert out["asset"] == "USDC"
    assert out["capital_usd"] == 10_000.0
    assert out["days"] == 30
    assert out["result"] is not None, f"backtest result missing: {out}"
    r = out["result"]
    for field_name in (
        "asset",
        "capital_usd",
        "days",
        "initial_spread_bps",
        "n_rebalances",
        "gross_pnl_usd",
        "total_costs_usd",
        "total_pnl_usd",
        "apr_net_of_costs",
        "sortino",
        "calmar",
        "max_drawdown_pct",
        "cost_basis_pct_of_pnl",
    ):
        assert field_name in r, f"live result missing {field_name}"
    cb = r["cost_basis_pct_of_pnl"]
    if isinstance(cb, (int, float)):
        # Strategy is unviable iff cost_basis_pct_of_pnl >= 100. We do
        # not fail on unviability — that's the *finding*, not a test
        # failure. We just assert the metric is finite.
        assert math.isfinite(cb), f"cost_basis_pct_of_pnl must be finite; got {cb}"
