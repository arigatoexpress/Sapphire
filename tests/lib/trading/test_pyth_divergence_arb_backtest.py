"""Unit tests for the Pyth divergence cross-chain arb backtest.

Pin the cost model + projection math so the dashboard / Telegram /
agent surface always shows arithmetic-correct numbers. The model
itself is deterministic and pure (no I/O in
``simulate_from_signal`` / ``simulate_with_divergence``); these
tests exercise the math without hitting any RPC.

What we pin:

* tiered bridge-cost lookup at every boundary
* zero-divergence → zero-PnL result (no costs incurred either)
* gross PnL = ``divergence_bps / 10000 * capital`` per cycle (point-
  in-time capture, NOT scaled by holding period — the structural
  difference vs the Aave APY arb model)
* per-cycle cost = round-trip bridge bps + 2 gas actions
* linear decay of divergence over ``decay_days``
* APR / Sortino / Calmar / max-drawdown wiring
* cost_basis_pct_of_pnl viability headline
* JSON safety on inf/nan
* explicit override beats tiered lookup
* error handling on bad capital / horizon / cost inputs
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from decimal import Decimal

import pytest

from lib.chains.cross_chain.pyth_divergence import (
    SEVERITY_EXTREME,
    SEVERITY_OPPORTUNITY,
    PythDivergenceSignal,
)
from lib.trading.pyth_divergence_arb_backtest import (
    BRIDGE_COST_TIERS,
    BacktestResult,
    PythArbBacktest,
    bridge_cost_bps_for_capital,
    project_pnl_for_pyth_signal,
)


def _sig(
    asset: str,
    bps: float,
    *,
    severity: str = SEVERITY_EXTREME,
) -> PythDivergenceSignal:
    """Build a minimal synthetic signal for the backtester."""
    return PythDivergenceSignal(
        asset=asset,
        chains={
            "Arbitrum": {
                "price": Decimal("100"),
                "publish_time": 1,
                "stale": False,
                "source_address": "0xff1a",
            },
            "Optimism": {
                "price": Decimal("101"),
                "publish_time": 2,
                "stale": False,
                "source_address": "0xff1a",
            },
        },
        max_divergence_bps=Decimal(str(bps)),
        freshest_chain="Optimism",
        stalest_chain="Arbitrum",
        severity=severity,
    )


# ---------------------------------------------------------------------------
# Bridge cost tiers
# ---------------------------------------------------------------------------


def test_bridge_cost_tiers_are_pinned() -> None:
    """The tier table is the public face of the cost model — pin it."""
    assert BRIDGE_COST_TIERS == (
        (10_000.0, 3.0),
        (100_000.0, 3.5),
        (1_000_000.0, 4.0),
        (math.inf, 5.0),
    )


@pytest.mark.parametrize(
    ("capital", "expected_bps"),
    [
        (0.0, 3.0),
        (1.0, 3.0),
        (10_000.0, 3.0),  # boundary inclusive on tier 1
        (10_000.01, 3.5),
        (50_000.0, 3.5),
        (100_000.0, 3.5),  # boundary inclusive on tier 2
        (100_000.01, 4.0),
        (500_000.0, 4.0),
        (1_000_000.0, 4.0),  # boundary inclusive on tier 3
        (1_000_000.01, 5.0),
        (10_000_000.0, 5.0),
        (1e15, 5.0),
    ],
)
def test_bridge_cost_lookup_picks_first_tier_inclusively(
    capital: float, expected_bps: float
) -> None:
    assert bridge_cost_bps_for_capital(capital) == expected_bps


def test_bridge_cost_negative_capital_raises() -> None:
    with pytest.raises(ValueError, match="non-negative"):
        bridge_cost_bps_for_capital(-1.0)


# ---------------------------------------------------------------------------
# Constructor validation
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("kwargs", "match"),
    [
        ({"capital_usd": 0.0}, "capital_usd"),
        ({"capital_usd": -1.0}, "capital_usd"),
        ({"days": 0}, "days"),
        ({"days": -5}, "days"),
        ({"holding_period_hours": 0}, "holding_period_hours"),
        ({"holding_period_hours": -1.0}, "holding_period_hours"),
        ({"bridge_cost_bps_per_round_trip": -0.01}, "bridge_cost"),
        ({"gas_cost_usd_per_action": -0.01}, "gas_cost"),
    ],
)
def test_constructor_rejects_invalid_params(kwargs: dict, match: str) -> None:
    with pytest.raises(ValueError, match=match):
        PythArbBacktest(**kwargs)


def test_simulate_with_negative_divergence_raises() -> None:
    bt = PythArbBacktest(capital_usd=10_000)
    with pytest.raises(ValueError, match="non-negative"):
        bt.simulate_with_divergence("BTC", -1.0)


# ---------------------------------------------------------------------------
# bridge_cost_bps_per_round_trip property: explicit override beats tier
# ---------------------------------------------------------------------------


def test_bridge_cost_property_returns_tier_when_no_override() -> None:
    bt = PythArbBacktest(capital_usd=50_000)
    assert bt.bridge_cost_bps_per_round_trip == 3.5  # tier 2


def test_bridge_cost_property_returns_explicit_override() -> None:
    bt = PythArbBacktest(capital_usd=50_000, bridge_cost_bps_per_round_trip=1.5)
    assert bt.bridge_cost_bps_per_round_trip == 1.5


def test_bridge_cost_zero_override_allowed() -> None:
    """Zero is non-negative → permitted (useful for cost-free what-ifs)."""
    bt = PythArbBacktest(capital_usd=10_000, bridge_cost_bps_per_round_trip=0.0)
    assert bt.bridge_cost_bps_per_round_trip == 0.0


# ---------------------------------------------------------------------------
# Zero-divergence and zero-signal paths
# ---------------------------------------------------------------------------


def test_zero_divergence_returns_zero_result() -> None:
    bt = PythArbBacktest(capital_usd=10_000, days=30)
    r = bt.simulate_with_divergence("BTC", 0.0)
    assert r.gross_pnl_usd == 0.0
    assert r.total_pnl_usd == 0.0
    assert r.total_costs_usd == 0.0
    assert r.n_rebalances == 0
    assert r.cost_basis_pct_of_pnl == 0.0


@pytest.mark.asyncio
async def test_simulate_without_scanner_raises() -> None:
    bt = PythArbBacktest(capital_usd=10_000)
    with pytest.raises(ValueError, match="requires a scanner"):
        await bt.simulate("BTC")


@pytest.mark.asyncio
async def test_simulate_with_scanner_emitting_no_signal_returns_zero_result() -> None:
    """If the scanner returns None for an asset, simulate() returns
    a zero-PnL result rather than raising."""

    @dataclass
    class _NoneScanner:
        async def scan_asset(self, _asset: str):
            return None

    bt = PythArbBacktest(scanner=_NoneScanner(), capital_usd=10_000)
    r = await bt.simulate("BTC")
    assert r.asset == "BTC"
    assert r.total_pnl_usd == 0.0


# ---------------------------------------------------------------------------
# Gross-PnL math: point-in-time capture (NOT scaled by period length)
# ---------------------------------------------------------------------------


def test_gross_pnl_equals_divergence_times_capital_no_decay() -> None:
    """100 bps once = 1% capital. 30 cycles × no decay = 30 × 1% = $3000
    gross at $10K. Cost: 30 × ($3 bridge + $5 gas) = $240. Net = $2760."""
    bt = PythArbBacktest(
        capital_usd=10_000,
        days=30,
        bridge_cost_bps_per_round_trip=3.0,
        gas_cost_usd_per_action=2.50,
        holding_period_hours=24.0,
        decay_days=0.0,  # no decay
    )
    r = bt.simulate_with_divergence("BTC", 100.0)
    assert r.n_rebalances == 30
    assert r.initial_divergence_bps == 100.0
    # 30 cycles × (100 bps / 10000) × $10K = 30 × $100 = $3000
    assert r.gross_pnl_usd == pytest.approx(3000.0, rel=1e-9)
    # Per-cycle cost: 3 bps / 10000 * 10000 + 2*2.50 = 3 + 5 = 8
    # Total: 30 × 8 = $240
    assert r.total_costs_usd == pytest.approx(240.0, rel=1e-9)
    assert r.total_pnl_usd == pytest.approx(2760.0, rel=1e-9)


def test_gross_pnl_with_linear_decay_halves() -> None:
    """Linear decay from 100bps to 0 over 7 days, evaluated at period
    midpoint. Daily rebalance over 7 days: midpoints at 0.5, 1.5, ...,
    6.5 days → fractions 13/14, 11/14, ..., 1/14. Sum = 49/14 = 3.5,
    so gross = 3.5 * (100bps/10000) * 10000 = $350."""
    bt = PythArbBacktest(
        capital_usd=10_000,
        days=7,
        bridge_cost_bps_per_round_trip=0.0,
        gas_cost_usd_per_action=0.0,
        holding_period_hours=24.0,
        decay_days=7.0,
    )
    r = bt.simulate_with_divergence("BTC", 100.0)
    assert r.n_rebalances == 7
    assert r.gross_pnl_usd == pytest.approx(350.0, rel=1e-9)


def test_decay_zeroes_out_after_decay_days() -> None:
    """Beyond ``decay_days``, divergence is zero (no PnL accrual)."""
    bt = PythArbBacktest(
        capital_usd=10_000,
        days=30,
        bridge_cost_bps_per_round_trip=0.0,
        gas_cost_usd_per_action=0.0,
        holding_period_hours=24.0,
        decay_days=7.0,
    )
    r = bt.simulate_with_divergence("BTC", 100.0)
    # Periods 0..6 contribute (decay still positive at period 6's
    # midpoint = 6.5 days, but day 7+ midpoints are >= decay_days → 0).
    # Periods 7..29 contribute nothing.
    # Sum of (1 - (i+0.5)/7) for i=0..6 = 49/14 = 3.5 → $350 same as above.
    assert r.gross_pnl_usd == pytest.approx(350.0, rel=1e-9)


# ---------------------------------------------------------------------------
# Cost-basis viability headline
# ---------------------------------------------------------------------------


def test_costs_eat_pnl_at_small_capital_signals_unviable() -> None:
    """At $10K capital with 30 bps divergence and no decay, costs >
    gross → cost_basis > 100% (the structural unviability flag)."""
    bt = PythArbBacktest(
        capital_usd=10_000,
        days=30,
        bridge_cost_bps_per_round_trip=3.0,
        gas_cost_usd_per_action=2.50,
        holding_period_hours=24.0,
        decay_days=0.0,
    )
    r = bt.simulate_with_divergence("BTC", 30.0)
    # gross = 30 * (30/10000) * 10000 = $900
    # costs = 30 * (3 + 5) = $240 → cost_basis = 26.67%
    # That's still < 100. Try smaller divergence:
    r2 = bt.simulate_with_divergence("BTC", 8.0)
    # gross = 30 * (8/10000) * 10000 = $240
    # costs = 30 * 8 = $240 → cost_basis exactly 100%
    assert r2.cost_basis_pct_of_pnl == pytest.approx(100.0, rel=1e-3)
    assert r2.total_pnl_usd == pytest.approx(0.0, abs=1e-9)
    # And smaller:
    r3 = bt.simulate_with_divergence("BTC", 4.0)
    # gross = 30 * (4/10000) * 10000 = $120, costs = $240 → cost_basis 200%
    assert r3.cost_basis_pct_of_pnl == pytest.approx(200.0, rel=1e-3)
    assert r3.total_pnl_usd < 0  # net loss

    # Sanity check the viable scenario too.
    assert r.cost_basis_pct_of_pnl == pytest.approx(26.67, rel=1e-3)
    assert r.total_pnl_usd > 0


# ---------------------------------------------------------------------------
# Risk metrics
# ---------------------------------------------------------------------------


def test_sortino_inf_when_no_negative_periods() -> None:
    """100 bps no decay → every period is positive → Sortino = inf."""
    bt = PythArbBacktest(
        capital_usd=10_000,
        days=30,
        bridge_cost_bps_per_round_trip=0.0,
        gas_cost_usd_per_action=0.0,
        decay_days=0.0,
    )
    r = bt.simulate_with_divergence("BTC", 100.0)
    assert math.isinf(r.sortino) and r.sortino > 0


def test_max_drawdown_zero_when_only_positive_periods() -> None:
    bt = PythArbBacktest(
        capital_usd=10_000,
        days=30,
        bridge_cost_bps_per_round_trip=0.0,
        gas_cost_usd_per_action=0.0,
        decay_days=0.0,
    )
    r = bt.simulate_with_divergence("BTC", 100.0)
    assert r.max_drawdown_pct == 0.0


def test_calmar_inf_when_no_drawdown() -> None:
    bt = PythArbBacktest(
        capital_usd=10_000,
        days=30,
        bridge_cost_bps_per_round_trip=0.0,
        gas_cost_usd_per_action=0.0,
        decay_days=0.0,
    )
    r = bt.simulate_with_divergence("BTC", 100.0)
    assert math.isinf(r.calmar) and r.calmar > 0


def test_max_drawdown_observed_when_costs_create_negative_periods() -> None:
    """Decay → late-period costs > gross → drawdown opens up."""
    bt = PythArbBacktest(
        capital_usd=10_000,
        days=30,
        bridge_cost_bps_per_round_trip=3.0,
        gas_cost_usd_per_action=2.50,
        decay_days=7.0,
    )
    r = bt.simulate_with_divergence("BTC", 50.0)
    assert r.max_drawdown_pct > 0
    # Sortino is finite here (some negative periods exist).
    assert not math.isinf(r.sortino)


# ---------------------------------------------------------------------------
# simulate_from_signal — wires through max_divergence_bps
# ---------------------------------------------------------------------------


def test_simulate_from_signal_uses_max_divergence_bps() -> None:
    sig = _sig("ETH", 75.0, severity=SEVERITY_OPPORTUNITY)
    bt = PythArbBacktest(capital_usd=10_000, days=30, decay_days=0.0)
    r = bt.simulate_from_signal(sig)
    assert r.asset == "ETH"
    assert r.initial_divergence_bps == 75.0


def test_project_pnl_convenience_wraps_class() -> None:
    sig = _sig("BTC", 142.0)
    r = project_pnl_for_pyth_signal(sig, capital_usd=10_000, days=30)
    assert isinstance(r, BacktestResult)
    assert r.initial_divergence_bps == 142.0
    assert r.capital_usd == 10_000.0
    assert r.bridge_cost_bps_used == 3.0  # tier 1 at $10K


# ---------------------------------------------------------------------------
# JSON safety
# ---------------------------------------------------------------------------


def test_to_dict_serializes_inf_as_string() -> None:
    bt = PythArbBacktest(
        capital_usd=10_000,
        days=30,
        bridge_cost_bps_per_round_trip=0.0,
        gas_cost_usd_per_action=0.0,
        decay_days=0.0,
    )
    r = bt.simulate_with_divergence("BTC", 100.0)
    d = r.to_dict()
    # Sortino + Calmar both inf → both should be string "inf".
    assert d["sortino"] == "inf"
    assert d["calmar"] == "inf"
    # Confirm json round-trip works.
    import json

    payload = json.dumps(d)
    parsed = json.loads(payload)
    assert parsed["sortino"] == "inf"


def test_to_dict_includes_bridge_cost_bps_used() -> None:
    """Operator needs to see what bps the simulation actually applied."""
    bt = PythArbBacktest(capital_usd=500_000, days=30)  # tier 3
    r = bt.simulate_with_divergence("BTC", 50.0)
    d = r.to_dict()
    assert d["bridge_cost_bps_used"] == 4.0


# ---------------------------------------------------------------------------
# Capital scaling — viability narrative
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("capital_usd", "expected_bridge_bps"),
    [
        (10_000, 3.0),
        (100_000, 3.5),
        (1_000_000, 4.0),
    ],
)
def test_capital_scale_picks_appropriate_bridge_tier_in_simulation(
    capital_usd: float, expected_bridge_bps: float
) -> None:
    bt = PythArbBacktest(capital_usd=capital_usd, days=30)
    r = bt.simulate_with_divergence("BTC", 100.0)
    assert r.bridge_cost_bps_used == expected_bridge_bps


def test_larger_capital_lowers_cost_basis_pct() -> None:
    """Gas is fixed in dollars so it amortizes across larger capital,
    pushing cost_basis_pct_of_pnl down — the viability story for
    institutional-scale deployment."""
    sig = _sig("BTC", 100.0)
    small = project_pnl_for_pyth_signal(sig, capital_usd=10_000, days=30, decay_days=0.0)
    big = project_pnl_for_pyth_signal(sig, capital_usd=1_000_000, days=30, decay_days=0.0)
    # Both bridge bps are small but at $1M tier rises to 4.0 — yet the
    # gas amortization still wins because gas is dollar-flat.
    assert big.cost_basis_pct_of_pnl < small.cost_basis_pct_of_pnl
