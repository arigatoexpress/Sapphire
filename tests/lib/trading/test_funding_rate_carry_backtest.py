"""Unit + gated-integration tests for the funding-rate carry backtester.

Mirrors the structure of ``test_cross_chain_arb_backtest.py``: pin the
cost model + funding-decay model + risk-metric calculation against
synthetic funding-rate inputs. The bottom of the file has a single gated
integration test that wires the real chain stack and asserts a live
funding-carry projection is fully populated.

Why "synthetic funding-rate inputs" instead of stored historical data:
the upstream signal is itself fresh-each-call (per-chain GMX V2 RPC
fanout), and there is no historical snapshot store yet. The backtester's
cost / decay / aggregation logic is *exactly* what the unit tests
exercise — the funding source is just an input.
"""

from __future__ import annotations

import math
import os

import pytest

from lib.trading.funding_rate_carry_backtest import (
    FundingCarryBacktest,
    PortfolioBacktestResult,
    project_carry_pnl,
)

# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def test_invalid_capital_raises() -> None:
    with pytest.raises(ValueError, match="capital_usd"):
        FundingCarryBacktest(capital_usd=0)
    with pytest.raises(ValueError, match="capital_usd"):
        FundingCarryBacktest(capital_usd=-100)


def test_invalid_horizon_raises() -> None:
    with pytest.raises(ValueError, match="days"):
        FundingCarryBacktest(days=0)


def test_invalid_leverage_raises() -> None:
    with pytest.raises(ValueError, match="leverage"):
        FundingCarryBacktest(leverage=0)
    with pytest.raises(ValueError, match="leverage"):
        FundingCarryBacktest(leverage=-1.0)


def test_invalid_funding_period_raises() -> None:
    with pytest.raises(ValueError, match="funding_period_hours"):
        FundingCarryBacktest(funding_period_hours=0)


def test_negative_costs_raise() -> None:
    with pytest.raises(ValueError, match="open_close_bps"):
        FundingCarryBacktest(gmx_open_close_bps=-1)
    with pytest.raises(ValueError, match="keeper"):
        FundingCarryBacktest(gmx_keeper_cost_per_funding_period_usd=-0.01)


# ---------------------------------------------------------------------------
# Side selection
# ---------------------------------------------------------------------------


def test_side_short_when_funding_positive() -> None:
    bt = FundingCarryBacktest(capital_usd=10_000, days=30)
    r = bt.simulate(market_addr="0x1", chain_id=42161, asset="ETH", current_funding_apr=0.20)
    assert r.side == "short"


def test_side_long_when_funding_negative() -> None:
    bt = FundingCarryBacktest(capital_usd=10_000, days=30)
    r = bt.simulate(market_addr="0x1", chain_id=42161, asset="BTC", current_funding_apr=-0.20)
    assert r.side == "long"


def test_side_flat_when_funding_zero() -> None:
    bt = FundingCarryBacktest(capital_usd=10_000, days=30)
    r = bt.simulate(market_addr="0x1", chain_id=42161, asset="ETH", current_funding_apr=0.0)
    assert r.side == "flat"
    assert r.gross_pnl_usd == 0.0
    assert r.total_pnl_usd == 0.0
    assert r.total_costs_usd == 0.0
    assert r.viable is False


def test_side_flat_below_threshold() -> None:
    """Tiny funding (< 1bp) below the noise floor is treated as flat."""
    bt = FundingCarryBacktest(capital_usd=10_000, days=30)
    r = bt.simulate(market_addr="0x1", chain_id=42161, asset="ETH", current_funding_apr=1e-6)
    assert r.side == "flat"


# ---------------------------------------------------------------------------
# Symmetry: short-positive and long-negative produce identical PnL magnitudes
# ---------------------------------------------------------------------------


def test_short_positive_equals_long_negative() -> None:
    bt = FundingCarryBacktest(capital_usd=10_000, days=30)
    r_short = bt.simulate(market_addr="0xa", chain_id=42161, asset="ETH", current_funding_apr=0.30)
    r_long = bt.simulate(market_addr="0xb", chain_id=42161, asset="ETH", current_funding_apr=-0.30)
    assert r_short.gross_pnl_usd == pytest.approx(r_long.gross_pnl_usd)
    assert r_short.total_costs_usd == pytest.approx(r_long.total_costs_usd)
    assert r_short.total_pnl_usd == pytest.approx(r_long.total_pnl_usd)


# ---------------------------------------------------------------------------
# High-magnitude funding produces > zero gross PnL even with decay
# ---------------------------------------------------------------------------


def test_high_magnitude_funding_collects_positive_gross() -> None:
    """+200% APR funding for 30d should produce visible gross collection
    even after the 7-day linear decay to 0.
    """
    bt = FundingCarryBacktest(capital_usd=10_000, days=30, leverage=1.0)
    r = bt.simulate(market_addr="0x1", chain_id=42161, asset="DOGE", current_funding_apr=2.0)
    # Linear decay 7d → integral over [0,7] of 2.0*(1 - t/7) = 7.0.
    # Gross funding $ = (1/365) * 7.0 * notional = 7/365 * 10_000 ≈ $191.78
    assert r.gross_pnl_usd == pytest.approx(7.0 / 365.0 * 10_000.0, rel=0.05)
    assert r.side == "short"


# ---------------------------------------------------------------------------
# Costs eat PnL at small scale — the "structurally unviable" case
# ---------------------------------------------------------------------------


def test_costs_eat_pnl_at_small_scale_low_funding() -> None:
    """Low funding (2% APR) at small capital ($10K) should fail viability."""
    r = project_carry_pnl(
        market_addr="0x1",
        chain_id=42161,
        asset="ETH",
        current_funding_apr=0.02,
        capital_usd=10_000,
        days=30,
    )
    assert r.viable is False
    assert r.total_pnl_usd < 0
    # Cost-basis ratio > 100 means costs ate the entire gross PnL.
    assert r.cost_basis_pct_of_pnl > 100


def test_zero_costs_yields_pure_funding_collection() -> None:
    """With all costs zeroed out, net PnL == gross funding collected."""
    bt = FundingCarryBacktest(
        capital_usd=10_000,
        days=30,
        gmx_open_close_bps=0.0,
        gmx_keeper_cost_per_funding_period_usd=0.0,
    )
    r = bt.simulate(market_addr="0x1", chain_id=42161, asset="ETH", current_funding_apr=0.50)
    assert r.total_costs_usd == 0.0
    assert r.total_pnl_usd == pytest.approx(r.gross_pnl_usd)
    assert r.viable is True


# ---------------------------------------------------------------------------
# Funding decay
# ---------------------------------------------------------------------------


def test_funding_decay_reduces_long_horizon_gross() -> None:
    """A 30d backtest with 7d decay collects far less than the naive
    annualized expectation. Specifically: integral of decaying APR over
    30d == integral over [0,7d] (decay zone) since post-7d funding is 0.
    """
    bt = FundingCarryBacktest(capital_usd=10_000, days=30, decay_days=7.0)
    r = bt.simulate(market_addr="0x1", chain_id=42161, asset="ETH", current_funding_apr=0.50)
    # Naive (no decay): 30/365 * 0.50 * 10_000 = $410.96
    naive = 30.0 / 365.0 * 0.50 * 10_000
    # With 7d decay: 0.5 * 7/365 * 0.50 * 10_000 = $47.95
    expected = 0.5 * 7.0 / 365.0 * 0.50 * 10_000
    assert r.gross_pnl_usd == pytest.approx(expected, rel=0.05)
    assert r.gross_pnl_usd < naive * 0.20  # decay collapses gross < 20% of naive


def test_no_decay_scenario_extends_collection() -> None:
    """``decay_days=0`` disables decay — gross scales linearly with horizon."""
    bt = FundingCarryBacktest(capital_usd=10_000, days=30, decay_days=0.0)
    r = bt.simulate(market_addr="0x1", chain_id=42161, asset="ETH", current_funding_apr=0.50)
    expected = 30.0 / 365.0 * 0.50 * 10_000
    assert r.gross_pnl_usd == pytest.approx(expected, rel=0.01)


# ---------------------------------------------------------------------------
# Leverage scales notional (and therefore both gross AND open/close costs)
# ---------------------------------------------------------------------------


def test_leverage_scales_gross_and_open_close_proportionally() -> None:
    bt_1x = FundingCarryBacktest(capital_usd=10_000, days=30, leverage=1.0)
    bt_5x = FundingCarryBacktest(capital_usd=10_000, days=30, leverage=5.0)
    r1 = bt_1x.simulate(market_addr="0x1", chain_id=42161, asset="ETH", current_funding_apr=0.50)
    r5 = bt_5x.simulate(market_addr="0x1", chain_id=42161, asset="ETH", current_funding_apr=0.50)
    # Gross funding scales 5x with notional.
    assert r5.gross_pnl_usd == pytest.approx(5.0 * r1.gross_pnl_usd, rel=1e-9)
    # Open/close costs scale 5x with notional.
    assert r5.open_close_costs_usd == pytest.approx(5.0 * r1.open_close_costs_usd, rel=1e-9)
    # Keeper costs do NOT scale with leverage.
    assert r5.keeper_costs_usd == pytest.approx(r1.keeper_costs_usd, rel=1e-9)


# ---------------------------------------------------------------------------
# Per-period accounting: number of funding periods matches horizon
# ---------------------------------------------------------------------------


def test_n_funding_periods_matches_horizon_at_default_period_hours() -> None:
    bt = FundingCarryBacktest(capital_usd=10_000, days=30, funding_period_hours=1.0)
    r = bt.simulate(market_addr="0x1", chain_id=42161, asset="ETH", current_funding_apr=0.20)
    assert r.n_funding_periods == 30 * 24
    assert len(r.period_returns) == r.n_funding_periods


def test_8h_funding_period_reduces_period_count() -> None:
    """A perp DEX with 8-hourly funding (e.g. Hyperliquid-style) should
    produce 1/8 the period count and 1/8 the keeper cost."""
    bt = FundingCarryBacktest(capital_usd=10_000, days=30, funding_period_hours=8.0)
    r = bt.simulate(market_addr="0x1", chain_id=42161, asset="ETH", current_funding_apr=0.50)
    assert r.n_funding_periods == 30 * 24 // 8
    # Keeper cost = $0.50/period * 90 periods = $45 (vs $360 at hourly).
    assert r.keeper_costs_usd == pytest.approx(0.50 * 90, rel=1e-9)


# ---------------------------------------------------------------------------
# Sortino, Calmar, drawdown
# ---------------------------------------------------------------------------


def test_sortino_calmar_populated_for_viable_market() -> None:
    """At $1M / 30d / 5x with +56% funding, the strategy is viable and
    risk metrics should be meaningful (not zero / not nan)."""
    r = project_carry_pnl(
        market_addr="0x1",
        chain_id=6342,
        asset="ETH",
        current_funding_apr=0.56,
        capital_usd=1_000_000,
        days=30,
        leverage=5.0,
    )
    assert r.viable is True
    assert r.total_pnl_usd > 0
    # Per-period returns include the per-period cost burden — many periods
    # are negative net once funding decays past day 7.
    assert any(pr < 0 for pr in r.period_returns)
    assert r.max_drawdown_pct > 0  # drawdown happens during decay
    # With negatives present, sortino is finite.
    assert math.isfinite(r.sortino)
    assert math.isfinite(r.calmar)


def test_to_dict_serializes_inf_safely() -> None:
    """JSON serialization must turn ±inf into strings."""
    r = project_carry_pnl(
        market_addr="0x1",
        chain_id=42161,
        asset="ETH",
        current_funding_apr=0.50,
        capital_usd=1_000_000,
        days=7,
        gmx_open_close_bps=0.0,
        gmx_keeper_cost_per_funding_period_usd=0.0,
    )
    d = r.to_dict()
    # With zero costs and only the decay-zone, all periods are positive
    # → sortino = inf.
    if math.isinf(r.sortino):
        assert d["sortino"] == "inf"
    if math.isinf(r.calmar):
        assert d["calmar"] == "inf"


# ---------------------------------------------------------------------------
# Portfolio aggregation
# ---------------------------------------------------------------------------


def test_simulate_portfolio_aggregates_per_market() -> None:
    bt = FundingCarryBacktest(capital_usd=10_000, days=30, leverage=1.0)
    markets = [
        {"market_addr": "0xa", "chain_id": 6342, "asset": "ETH", "current_funding_apr": 0.56},
        {"market_addr": "0xb", "chain_id": 6342, "asset": "BTC", "current_funding_apr": -0.434},
        {"market_addr": "0xc", "chain_id": 42161, "asset": "ETH", "current_funding_apr": 0.0213},
        {"market_addr": "0xd", "chain_id": 42161, "asset": "BTC", "current_funding_apr": -0.1568},
    ]
    p = bt.simulate_portfolio(markets)
    assert isinstance(p, PortfolioBacktestResult)
    assert p.n_markets == 4
    assert len(p.per_market) == 4
    # Aggregates sum per-market.
    assert p.total_gross_pnl_usd == pytest.approx(
        sum(r.gross_pnl_usd for r in p.per_market), rel=1e-9
    )
    assert p.total_costs_usd == pytest.approx(
        sum(r.total_costs_usd for r in p.per_market), rel=1e-9
    )
    assert p.total_net_pnl_usd == pytest.approx(
        sum(r.total_pnl_usd for r in p.per_market), rel=1e-9
    )


def test_portfolio_n_viable_counts_winners_only() -> None:
    """At $10K / 30d / 1x, none of the 4 known markets is viable."""
    bt = FundingCarryBacktest(capital_usd=10_000, days=30, leverage=1.0)
    markets = [
        {"market_addr": "0xa", "chain_id": 6342, "asset": "ETH", "current_funding_apr": 0.56},
        {"market_addr": "0xb", "chain_id": 6342, "asset": "BTC", "current_funding_apr": -0.434},
        {"market_addr": "0xc", "chain_id": 42161, "asset": "ETH", "current_funding_apr": 0.0213},
        {"market_addr": "0xd", "chain_id": 42161, "asset": "BTC", "current_funding_apr": -0.1568},
    ]
    p = bt.simulate_portfolio(markets)
    assert p.n_viable == 0


def test_portfolio_dict_round_trip() -> None:
    """``to_dict`` produces nested per-market dicts."""
    bt = FundingCarryBacktest(capital_usd=10_000, days=30)
    p = bt.simulate_portfolio(
        [{"market_addr": "0xa", "chain_id": 6342, "asset": "ETH", "current_funding_apr": 0.56}]
    )
    d = p.to_dict()
    assert d["n_markets"] == 1
    assert isinstance(d["per_market"], list)
    assert d["per_market"][0]["asset"] == "ETH"
    assert "side" in d["per_market"][0]


# ---------------------------------------------------------------------------
# Funding flip mid-horizon (decay overshoots — defensive)
# ---------------------------------------------------------------------------


def test_funding_decays_only_to_zero_never_overshoots() -> None:
    """The decay model is strictly toward 0, so per-period funding magnitude
    is monotonically decreasing — verify this so a future refactor doesn't
    accidentally turn a +50% rate into a -50% rate after the decay window.
    """
    from lib.trading.funding_rate_carry_backtest import _funding_at_period

    # Sample across periods 0..200 with hourly funding + 7d decay.
    samples = [
        _funding_at_period(0.50, i, funding_period_hours=1.0, decay_days=7.0) for i in range(200)
    ]
    # Magnitude monotonically decreasing (allow equal for the post-decay zeros).
    for a, b in zip(samples, samples[1:]):
        assert abs(b) <= abs(a) + 1e-12
    # All non-negative since initial is positive.
    assert all(s >= 0 for s in samples)


# ---------------------------------------------------------------------------
# Live-gated integration test (one market, one horizon)
# ---------------------------------------------------------------------------


@pytest.mark.skipif(
    os.getenv("SAPPHIRE_CROSS_CHAIN_INTEGRATION") != "1",
    reason="set SAPPHIRE_CROSS_CHAIN_INTEGRATION=1 to enable live MegaETH RPC",
)
def test_live_eth_megaeth_funding_carry_30d_10k() -> None:
    """Smoke test against the live MegaETH ETH market.

    Intentionally minimal: we only assert the projector returned a fully
    populated result and that the headline ``cost_basis_pct_of_pnl`` is
    finite. Whether the market is *viable* at $10K/30d is exactly the
    operator question this PR answers — we do NOT assert ``viable=True``.
    """
    from lib.hackathon.cross_chain_alpha import backtest_funding_carry

    # ETH market on MegaETH (canonical address from the GMX V2 wrappers).
    out = backtest_funding_carry(
        market_addr="0x" + "00" * 19 + "01",  # placeholder, override via env
        chain_id=6342,
        asset="ETH",
        capital_usd=10_000,
        days=30,
    )
    assert "result" in out
    if out.get("error"):
        pytest.skip(f"live RPC unavailable: {out['error']}")
    assert out["result"] is not None
    res = out["result"]
    assert res["asset"] == "ETH"
    assert res["chain_id"] == 6342
    assert res["capital_usd"] == 10_000
    assert res["days"] == 30
    # Viability flag is present and consistent with net PnL.
    assert res["viable"] == (res["total_pnl_usd"] > 0)
    # cost_basis_pct_of_pnl finite (not "inf") — live funding > 0.
    assert isinstance(res["cost_basis_pct_of_pnl"], (int, float))
