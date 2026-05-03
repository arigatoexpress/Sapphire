"""Cross-chain Aave APY arbitrage PnL backtest module.

Turns the live cross-chain Aave APY spread signal
(:mod:`lib.chains.cross_chain.aave_apy_arb`) into a *projected dollar
PnL* under a realistic-decay model and explicit bridge + gas cost
deduction. PnL is king per Sapphire's stated user preference; an
"interesting" 232 bps borrow spread is just a number until it's been
turned into "$X projected over 30 days at $10K capital, net of $Y
costs."

Why a sibling module instead of bolting onto ``strategy_lab.py``:

* ``strategy_lab.py`` is a non-mutating draft generator for *single-venue*
  spot/perp orders against TradingView/Robinhood/Hyperliquid. It does
  not model recurring rebalances, bridge costs, or APY decay. Bolting a
  cross-chain rate-arb backtester onto it would conflate two distinct
  problem shapes.
* This module is purely a *projector* — given a live signal (or a
  synthetic spread time-series in tests), produce the dollar PnL net of
  costs. It never sources orders. Routing remains a separate, gated
  decision the operator (or a future executor) makes.

The model:

* Initial spread is read from the live signal (basis points).
* Spread *decays linearly* from its initial value to zero over a
  configurable half-life (default 7 days), reflecting the "as more
  capital chases the arb, the spread compresses" empirical reality. A
  flat-spread / no-decay scenario is also supported via the
  ``decay_days`` parameter.
* Per rebalance cycle (default 24 h), we deduct one round-trip bridge
  fee (in basis points of capital) plus a fixed gas cost in USD per
  action.
* Net per-period PnL = ``(spread_bps_during_period / 10000) * capital
  * holding_period_years - bridge_cost_usd - gas_cost_usd``.
* Period returns are aggregated into Sortino, Calmar, max drawdown.

Defaults reflect *small-scale* (Sapphire-typical) conditions:

* ``capital_usd = 10_000`` — Sapphire's actual operating scale; do NOT
  bake in $1M-style assumptions that hide cost dominance.
* ``bridge_cost_bps_per_round_trip`` — defaults to a *tiered lookup*
  (:data:`BRIDGE_COST_TIERS`) calibrated 2026-05-03 from live Across,
  Hop, Stargate, and CCTP quotes for USDC ARB↔OP. The single 5 bps
  legacy default was ~3× too high; live Across is ~1.5 bps round-trip
  per leg, ~3 bps round-trip. Override by passing an explicit float.
* ``gas_cost_usd_per_action = 2.50`` — average of L2 gas for an Aave
  withdraw + bridge + Aave deposit (Optimism cheap, Arbitrum mid).
* ``holding_period_hours = 24`` — daily rebalance frequency.

Re-survey the bridge quotes monthly via
``scripts/research/bridge_cost_survey.py`` and refresh
:data:`BRIDGE_COST_TIERS` if any tier shifts more than 0.5 bps.

The output is a :class:`BacktestResult` dataclass whose key headline
metric is ``cost_basis_pct_of_pnl`` — what fraction of the *gross*
spread-PnL is eaten by bridge + gas. Above ~50 % at small capital
strongly suggests the strategy needs $100 K+ to be viable.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from lib.chains.cross_chain.aave_apy_arb import (
    AaveApyArbSignal,
    CrossChainAaveScanner,
)

# ---------------------------------------------------------------------------
# Bridge cost tiers — calibrated 2026-05-03 from live Across/Hop/Stargate/CCTP
# quotes for USDC ARB↔OP. See scripts/research/bridge_cost_survey.py + the
# raw quote dump under data/research/bridge_quotes_2026-05-03.json.
#
# Each tier = (max_capital_usd_inclusive, round_trip_bps). Lookup picks the
# *first* tier whose threshold is >= capital_usd. The tail tier (math.inf)
# captures whale-scale capital where Across LP fees creep up to ~2 bps per
# leg (~4 bps round-trip).
#
# Per leg ≈ Across one-way fee (~1.5 bps observed). Round-trip = 2x leg.
# Hop's bonderFee is structurally fixed at $0.01 (~0 bps for $10k+) but its
# hAMM destination swap can add 1-3 bps under thin liquidity, so we don't
# default to Hop's headline number — Across is the operational pick.
# Stargate at ~6-7 bps is too expensive; CCTP at near-zero is too slow
# (15+ min) for daily rebalancing.
#
# Re-survey monthly. Update tiers if any value shifts more than 0.5 bps.
# ---------------------------------------------------------------------------
BRIDGE_COST_TIERS: tuple[tuple[float, float], ...] = (
    (10_000.0, 3.0),       # ≤ $10k:    ~1.5 bps × 2 legs (Across)
    (100_000.0, 3.5),      # ≤ $100k:   ~1.5-1.75 bps × 2 legs (Across)
    (1_000_000.0, 4.0),    # ≤ $1M:     ~2 bps × 2 legs (LP fee creep)
    (math.inf, 5.0),       # >  $1M:    ~2.5 bps × 2 legs (whale, slippage)
)


def bridge_cost_bps_for_capital(capital_usd: float) -> float:
    """Return calibrated round-trip bridge cost in bps for ``capital_usd``.

    Looks up :data:`BRIDGE_COST_TIERS` and picks the first tier whose
    inclusive threshold is ≥ ``capital_usd``. The tail tier (``math.inf``)
    guarantees a value is always returned.

    Examples
    --------
    >>> bridge_cost_bps_for_capital(1_000)
    3.0
    >>> bridge_cost_bps_for_capital(10_000)
    3.0
    >>> bridge_cost_bps_for_capital(50_000)
    3.5
    >>> bridge_cost_bps_for_capital(500_000)
    4.0
    >>> bridge_cost_bps_for_capital(10_000_000)
    5.0
    """
    if capital_usd < 0:
        raise ValueError("capital_usd must be non-negative")
    for threshold, bps in BRIDGE_COST_TIERS:
        if capital_usd <= threshold:
            return bps
    # Unreachable given math.inf tail, but defensive:
    return BRIDGE_COST_TIERS[-1][1]


@dataclass(frozen=True)
class BacktestResult:
    """Projected PnL + risk metrics for one cross-chain arb scenario.

    All dollar fields are floats (not Decimal) — by the time we surface
    a backtest result the upstream basis-point precision has already
    been spent and the dashboard wants plain JSON numbers.

    The operator-critical field is ``cost_basis_pct_of_pnl``: how much
    of the *gross* spread PnL the bridge + gas costs eat. > 100 means
    the strategy lost money at the chosen capital level even though the
    raw spread was positive — a structural unviability flag.
    """

    asset: str
    """Underlying asset symbol (e.g. ``"USDC"``)."""

    capital_usd: float
    """Notional capital deployed in the simulation."""

    days: int
    """Simulated horizon in days."""

    initial_spread_bps: float
    """Spread at t=0, in basis points (e.g. 232 for the live USDC obs)."""

    n_rebalances: int
    """Number of rebalance cycles simulated over the horizon."""

    gross_pnl_usd: float
    """Spread-only PnL with NO costs deducted. Always >= 0 by construction
    (spread is non-negative)."""

    total_costs_usd: float
    """Sum of all bridge + gas costs across rebalances."""

    total_pnl_usd: float
    """Net PnL after costs. Can be negative."""

    apr_net_of_costs: float
    """Annualized return on ``capital_usd``, net of costs (decimal
    fraction, e.g. 0.045 == 4.5% APR)."""

    sortino: float
    """Sortino ratio of per-period returns. ``inf`` if no negative
    returns; ``0.0`` if no returns at all."""

    calmar: float
    """Calmar ratio = APR / |max drawdown|. ``inf`` if no drawdown,
    ``0.0`` if no returns."""

    max_drawdown_pct: float
    """Worst peak-to-trough drawdown over the simulation, as a fraction
    (0.05 == 5 %)."""

    cost_basis_pct_of_pnl: float
    """``total_costs_usd / max(1e-9, gross_pnl_usd) * 100``. Headline
    viability metric: > 100 means costs ate the entire gross PnL."""

    period_returns: list[float] = field(default_factory=list)
    """Per-period return fractions (e.g. ``[0.0008, 0.0007, ...]``).
    Exposed so the dashboard can render an equity curve without
    re-running the simulation."""

    def to_dict(self) -> dict[str, Any]:
        """JSON-friendly dict (Python ``inf``/``-inf`` → strings)."""
        def _safe(v: float) -> float | str:
            if math.isinf(v):
                return "inf" if v > 0 else "-inf"
            if math.isnan(v):
                return "nan"
            return v

        return {
            "asset": self.asset,
            "capital_usd": self.capital_usd,
            "days": self.days,
            "initial_spread_bps": self.initial_spread_bps,
            "n_rebalances": self.n_rebalances,
            "gross_pnl_usd": round(self.gross_pnl_usd, 2),
            "total_costs_usd": round(self.total_costs_usd, 2),
            "total_pnl_usd": round(self.total_pnl_usd, 2),
            "apr_net_of_costs": round(self.apr_net_of_costs, 4),
            "sortino": _safe(round(self.sortino, 4) if not math.isinf(self.sortino) else self.sortino),
            "calmar": _safe(round(self.calmar, 4) if not math.isinf(self.calmar) else self.calmar),
            "max_drawdown_pct": round(self.max_drawdown_pct, 4),
            "cost_basis_pct_of_pnl": round(self.cost_basis_pct_of_pnl, 2),
        }


def _spread_at_period(
    initial_bps: float,
    period_idx: int,
    holding_period_hours: float,
    decay_days: float,
) -> float:
    """Linear decay from ``initial_bps`` to 0 over ``decay_days``.

    Returns the spread *during* period ``period_idx`` (i.e. evaluated
    at the period's midpoint so the integral is exact for linear
    decay). When ``decay_days <= 0`` the spread stays constant
    indefinitely (no-decay scenario).
    """
    if decay_days <= 0:
        return initial_bps
    elapsed_days = (period_idx + 0.5) * holding_period_hours / 24.0
    if elapsed_days >= decay_days:
        return 0.0
    return initial_bps * (1.0 - elapsed_days / decay_days)


def _sortino(returns: list[float]) -> float:
    """Sortino against a 0% target. ``inf`` if no negatives, 0 if empty."""
    if not returns:
        return 0.0
    mean = sum(returns) / len(returns)
    downside = [r for r in returns if r < 0]
    if not downside:
        # No negative periods at all → unbounded Sortino. Surface inf
        # rather than a misleading huge finite number; the dashboard
        # serializes this safely.
        return math.inf if mean > 0 else 0.0
    downside_dev = math.sqrt(sum(r * r for r in downside) / len(downside))
    if downside_dev == 0:
        return math.inf if mean > 0 else 0.0
    return mean / downside_dev


def _max_drawdown(cumulative: list[float]) -> float:
    """Max peak-to-trough drawdown of an equity curve, as a fraction."""
    if not cumulative:
        return 0.0
    peak = cumulative[0]
    max_dd = 0.0
    for v in cumulative:
        if v > peak:
            peak = v
        if peak > 0:
            dd = (peak - v) / peak
            if dd > max_dd:
                max_dd = dd
    return max_dd


class CrossChainArbBacktest:
    """Project net PnL for a cross-chain Aave APY arb under realistic costs.

    Construction wires together a live scanner (or a pre-fetched
    signal) with the cost model and horizon. Call :meth:`simulate`
    repeatedly with different assets to compare them under the same
    cost regime.

    The scanner is optional: if you already have a signal in hand
    (e.g. captured during a dashboard tick), call
    :meth:`simulate_from_signal` directly to skip the live RPC roundtrip.
    """

    def __init__(
        self,
        scanner: CrossChainAaveScanner | None = None,
        capital_usd: float = 10_000.0,
        days: int = 30,
        bridge_cost_bps_per_round_trip: float | None = None,
        gas_cost_usd_per_action: float = 2.50,
        holding_period_hours: float = 24.0,
        decay_days: float = 7.0,
    ) -> None:
        if capital_usd <= 0:
            raise ValueError("capital_usd must be positive")
        if days <= 0:
            raise ValueError("days must be positive")
        if holding_period_hours <= 0:
            raise ValueError("holding_period_hours must be positive")
        if (
            bridge_cost_bps_per_round_trip is not None
            and bridge_cost_bps_per_round_trip < 0
        ):
            raise ValueError("bridge_cost_bps_per_round_trip must be non-negative")
        if gas_cost_usd_per_action < 0:
            raise ValueError("gas_cost_usd_per_action must be non-negative")

        self.scanner = scanner
        self.capital_usd = float(capital_usd)
        self.days = int(days)
        # Tiered default: when caller doesn't specify, look up the calibrated
        # cost for this capital level. Explicit overrides still win — the
        # backtester's tests pass synthetic costs (incl. zero) to isolate
        # decay vs cost behavior, and the dashboard's "what-if" panel may
        # want to ask "what bridge cost would make this viable?".
        if bridge_cost_bps_per_round_trip is None:
            self.bridge_cost_bps_per_round_trip = bridge_cost_bps_for_capital(
                self.capital_usd
            )
        else:
            self.bridge_cost_bps_per_round_trip = float(bridge_cost_bps_per_round_trip)
        self.gas_cost_usd_per_action = float(gas_cost_usd_per_action)
        self.holding_period_hours = float(holding_period_hours)
        self.decay_days = float(decay_days)

    # -- public API --------------------------------------------------------

    async def simulate(self, asset: str = "USDC") -> BacktestResult:
        """Fetch the live signal for ``asset`` and project PnL.

        Requires a scanner in the constructor. The signal's larger of
        (supply_spread_bps, borrow_spread_bps) is used as the initial
        spread.

        If the scanner emits no signal (asset below the
        ``MIN_SIGNAL_SPREAD_BPS`` floor or unavailable), returns a
        zero-PnL :class:`BacktestResult` rather than raising — easier
        for the dashboard / agent to render an "all quiet" state.
        """
        if self.scanner is None:
            raise ValueError(
                "simulate() requires a scanner; pass one to the constructor "
                "or call simulate_from_signal() with a pre-fetched signal."
            )
        sig = await self.scanner.scan_asset(asset)
        if sig is None:
            return self._zero_result(asset, initial_spread_bps=0.0)
        return self.simulate_from_signal(sig)

    def simulate_from_signal(self, signal: AaveApyArbSignal) -> BacktestResult:
        """Project PnL from a pre-fetched :class:`AaveApyArbSignal`.

        Pure / synchronous / no I/O — safe to call inside a sync code
        path. Spread used = ``max(supply_spread_bps, borrow_spread_bps)``
        because that's the side an executor would actually rotate
        toward.
        """
        max_spread_bps = float(
            max(signal.max_supply_spread_bps, signal.max_borrow_spread_bps)
        )
        return self._simulate_with_initial_spread(
            asset=signal.asset, initial_spread_bps=max_spread_bps
        )

    def simulate_with_spread(
        self, asset: str, initial_spread_bps: float
    ) -> BacktestResult:
        """Project PnL given an explicit initial spread (bps).

        Public hook used by tests to drive the model with synthetic
        inputs and by callers who want to ask "what if the spread were
        500 bps?" without going through a signal.
        """
        if initial_spread_bps < 0:
            raise ValueError("initial_spread_bps must be non-negative")
        return self._simulate_with_initial_spread(asset, initial_spread_bps)

    # -- internals ---------------------------------------------------------

    def _simulate_with_initial_spread(
        self, asset: str, initial_spread_bps: float
    ) -> BacktestResult:
        """Core simulation loop. Both signal-driven and explicit-spread
        callers funnel through here so the cost model has exactly one
        implementation."""
        if initial_spread_bps == 0:
            return self._zero_result(asset, initial_spread_bps=0.0)

        # Number of rebalance cycles over the horizon.
        n_rebalances = max(1, int(self.days * 24 / self.holding_period_hours))
        period_years = self.holding_period_hours / (24 * 365)

        # Per-rebalance cost is fixed in dollar terms (gas + bridge bps
        # of capital). We deduct it once per period (one rebalance =
        # one round-trip).
        bridge_cost_usd = (
            self.bridge_cost_bps_per_round_trip / 10_000.0 * self.capital_usd
        )
        per_period_cost_usd = bridge_cost_usd + self.gas_cost_usd_per_action

        gross_pnl_usd = 0.0
        total_costs_usd = 0.0
        period_returns: list[float] = []
        equity_curve: list[float] = [self.capital_usd]

        for i in range(n_rebalances):
            spread_bps = _spread_at_period(
                initial_bps=initial_spread_bps,
                period_idx=i,
                holding_period_hours=self.holding_period_hours,
                decay_days=self.decay_days,
            )
            gross_period_pnl = (
                spread_bps / 10_000.0 * self.capital_usd * period_years
            )
            net_period_pnl = gross_period_pnl - per_period_cost_usd

            gross_pnl_usd += gross_period_pnl
            total_costs_usd += per_period_cost_usd
            period_returns.append(net_period_pnl / self.capital_usd)
            equity_curve.append(equity_curve[-1] + net_period_pnl)

        total_pnl_usd = sum(period_returns) * self.capital_usd
        # APR = total return scaled to one year. Use the actual horizon
        # so the projection is honest about its lookback.
        actual_years = (n_rebalances * self.holding_period_hours) / (24 * 365)
        apr = (total_pnl_usd / self.capital_usd) / max(actual_years, 1e-9)

        sortino = _sortino(period_returns)
        max_dd = _max_drawdown(equity_curve)
        # Calmar = APR / |max DD|. Inf when no drawdown (rare under decay
        # + cost model but possible if costs are zero); 0 if no returns.
        if max_dd == 0:
            calmar = math.inf if apr > 0 else 0.0
        else:
            calmar = apr / max_dd

        cost_basis_pct = (
            total_costs_usd / max(1e-9, gross_pnl_usd) * 100.0
            if gross_pnl_usd > 0
            else (math.inf if total_costs_usd > 0 else 0.0)
        )

        return BacktestResult(
            asset=asset,
            capital_usd=self.capital_usd,
            days=self.days,
            initial_spread_bps=initial_spread_bps,
            n_rebalances=n_rebalances,
            gross_pnl_usd=gross_pnl_usd,
            total_costs_usd=total_costs_usd,
            total_pnl_usd=total_pnl_usd,
            apr_net_of_costs=apr,
            sortino=sortino,
            calmar=calmar,
            max_drawdown_pct=max_dd,
            cost_basis_pct_of_pnl=cost_basis_pct,
            period_returns=period_returns,
        )

    def _zero_result(self, asset: str, *, initial_spread_bps: float) -> BacktestResult:
        """Return a flat zero-PnL result (used when there's no signal)."""
        return BacktestResult(
            asset=asset,
            capital_usd=self.capital_usd,
            days=self.days,
            initial_spread_bps=initial_spread_bps,
            n_rebalances=0,
            gross_pnl_usd=0.0,
            total_costs_usd=0.0,
            total_pnl_usd=0.0,
            apr_net_of_costs=0.0,
            sortino=0.0,
            calmar=0.0,
            max_drawdown_pct=0.0,
            cost_basis_pct_of_pnl=0.0,
            period_returns=[],
        )


def project_pnl_for_signal(
    signal: AaveApyArbSignal,
    capital_usd: float = 10_000.0,
    days: int = 30,
    **kwargs: Any,
) -> BacktestResult:
    """Convenience: one-shot PnL projection for a signal at a horizon.

    Wraps :class:`CrossChainArbBacktest` so callers (dashboard tile,
    plugin tool) don't need to instantiate the class explicitly for
    common cases.

    Extra ``**kwargs`` flow through to the constructor so callers can
    still override ``bridge_cost_bps_per_round_trip``, ``decay_days``,
    etc.
    """
    bt = CrossChainArbBacktest(
        capital_usd=capital_usd,
        days=days,
        **kwargs,
    )
    return bt.simulate_from_signal(signal)


# Re-export Decimal for callers building synthetic signals.
__all__ = (
    "BRIDGE_COST_TIERS",
    "BacktestResult",
    "CrossChainArbBacktest",
    "Decimal",
    "bridge_cost_bps_for_capital",
    "project_pnl_for_signal",
)
