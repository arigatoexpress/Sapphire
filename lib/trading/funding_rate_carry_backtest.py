"""Funding-rate carry PnL backtest module.

Companion to :mod:`lib.trading.cross_chain_arb_backtest` (PR #606). Where
that module turns a *cross-chain Aave APY spread* into projected dollar
PnL, this one turns a *GMX V2 perp market funding rate* into projected
dollar PnL — both projectors live in the same neighbourhood (cost model
+ Sortino + Calmar + headline cost-basis metric) so the dashboard can
compare carry vs. arb under apples-to-apples assumptions.

The carry mental model:

* Funding APR is a *signed* annualized rate. Positive funding → longs
  pay shorts at every funding settlement. Negative → shorts pay longs.
* A **carry** position takes the side that COLLECTS funding: short when
  funding is positive, long when funding is negative. The position's
  size is a fixed dollar notional (``capital_usd × leverage``) on a
  perp DEX (GMX V2 in our case).
* Per-period gross PnL = ``funding_rate_during_period × notional ×
  period_years`` (i.e. the rate accrues continuously and settles each
  funding period — keeper updates settle one bucket of accrued funding).
* Per-period costs = a fixed-USD keeper cost (``$0.50`` default —
  GMX-V2-funding-period keeper updates), amortized one per period.
* Round-trip costs (open + close) = ``open_close_bps`` of *notional*
  (NOT capital — leverage scales the position you're paying fees on),
  paid once at t=0 and once at horizon. Spread evenly across all
  periods so the headline ``cost_basis_pct_of_pnl`` is honest.
* Funding decay model = linear decay from ``current_funding_apr`` to 0
  over ``decay_days`` (default 7d). Mirrors the empirical reality that
  an extreme funding rate compresses as more capital takes the carry.
* Negative funding for a long-side carry decays toward 0 (which is
  worse for the long), positive funding for a short-side carry also
  decays toward 0 (worse for the short).

Output is :class:`FundingCarryBacktestResult` — same shape as
:class:`lib.trading.cross_chain_arb_backtest.BacktestResult` so the
dashboard can swap between them. The headline operator-critical field is
``cost_basis_pct_of_pnl``: > 100 means costs ate the whole gross funding
collected even though the rate looked attractive.

Defaults reflect *small-scale* (Sapphire-typical) GMX V2 conditions:

* ``capital_usd = 10_000`` — Sapphire's actual operating scale.
* ``gmx_open_close_bps = 30`` — round-trip (~5–15bps each side on GMX V2
  per Mar/Apr 2026 fee schedule; conservative).
* ``gmx_keeper_cost_per_funding_period_usd = 0.50`` — funding-period
  keeper updates run roughly hourly under load.
* ``leverage = 1.0`` — start unleveraged. Scenarios sweep 2x / 5x.
* ``funding_period_hours = 1.0`` — GMX V2 settles continuously but
  keeper-cost accounting buckets accrual hourly.
* ``decay_days = 7.0`` — same horizon as the arb backtester for
  apples-to-apples comparisons.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class FundingCarryBacktestResult:
    """Projected PnL + risk metrics for one funding-carry scenario.

    Mirrors :class:`lib.trading.cross_chain_arb_backtest.BacktestResult`
    field-for-field where the concept is shared so the dashboard can
    render either result with the same template; carry-specific fields
    (``side``, ``leverage``, ``initial_funding_apr``) are added at the
    front.

    The operator-critical field is ``cost_basis_pct_of_pnl``: how much
    of the gross funding collected is eaten by keeper + open/close
    costs. > 100 means the strategy lost money at the chosen capital +
    leverage even though the funding rate was attractive — a structural
    unviability flag at this scale.
    """

    market_addr: str
    """GMX V2 market token address (used as the market identifier)."""

    chain_id: int
    """EVM chain ID — 42161 for Arbitrum, 6342 for MegaETH testnet."""

    asset: str
    """Underlying asset symbol (e.g. ``"ETH"``, ``"BTC"``)."""

    side: str
    """``"short"`` if funding > 0 (collects from longs), ``"long"`` if
    funding < 0 (collects from shorts), ``"flat"`` if funding ≈ 0."""

    leverage: float
    """Position notional multiple of capital. 1.0 = unleveraged."""

    capital_usd: float
    """Notional capital deployed (the "margin" — notional = capital × leverage)."""

    days: int
    """Simulated horizon in days."""

    initial_funding_apr: float
    """Funding APR at t=0 as a signed decimal fraction (e.g. ``0.56`` =
    +56% APR; ``-0.434`` = -43.40% APR)."""

    n_funding_periods: int
    """Number of funding settlement periods over the horizon."""

    gross_pnl_usd: float
    """Funding collected with NO costs deducted. Always >= 0 by
    construction — the side is chosen to collect, not pay."""

    open_close_costs_usd: float
    """Round-trip open + close fees, in USD. Scales with notional."""

    keeper_costs_usd: float
    """Sum of per-funding-period keeper costs over the horizon."""

    total_costs_usd: float
    """Sum of ``open_close_costs_usd + keeper_costs_usd``."""

    total_pnl_usd: float
    """Net PnL after ALL costs. Can be negative."""

    apr_net_of_costs: float
    """Annualized return on ``capital_usd`` (NOT notional — operator
    cares about return on margin), net of costs (decimal fraction)."""

    sortino: float
    """Sortino ratio of per-period returns. ``inf`` if no negatives;
    ``0.0`` if no returns at all."""

    calmar: float
    """Calmar ratio = APR / |max drawdown|. ``inf`` if no drawdown,
    ``0.0`` if no returns."""

    max_drawdown_pct: float
    """Worst peak-to-trough drawdown over the simulation, as a fraction
    (0.05 == 5 %)."""

    cost_basis_pct_of_pnl: float
    """``total_costs_usd / max(1e-9, gross_pnl_usd) * 100``. Headline
    viability metric — > 100 means costs ate the entire gross funding
    collected at this capital + leverage."""

    viable: bool
    """``True`` iff ``total_pnl_usd > 0``. Convenience flag for the
    dashboard's red/green pill."""

    period_returns: list[float] = field(default_factory=list)
    """Per-period return fractions on capital (e.g. ``[0.0008, ...]``).
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
            "market_addr": self.market_addr,
            "chain_id": self.chain_id,
            "asset": self.asset,
            "side": self.side,
            "leverage": self.leverage,
            "capital_usd": self.capital_usd,
            "days": self.days,
            "initial_funding_apr": round(self.initial_funding_apr, 6),
            "n_funding_periods": self.n_funding_periods,
            "gross_pnl_usd": round(self.gross_pnl_usd, 2),
            "open_close_costs_usd": round(self.open_close_costs_usd, 2),
            "keeper_costs_usd": round(self.keeper_costs_usd, 2),
            "total_costs_usd": round(self.total_costs_usd, 2),
            "total_pnl_usd": round(self.total_pnl_usd, 2),
            "apr_net_of_costs": round(self.apr_net_of_costs, 4),
            "sortino": _safe(
                round(self.sortino, 4) if not math.isinf(self.sortino) else self.sortino
            ),
            "calmar": _safe(round(self.calmar, 4) if not math.isinf(self.calmar) else self.calmar),
            "max_drawdown_pct": round(self.max_drawdown_pct, 4),
            "cost_basis_pct_of_pnl": round(self.cost_basis_pct_of_pnl, 2),
            "viable": self.viable,
        }


@dataclass(frozen=True)
class PortfolioBacktestResult:
    """Aggregate result across multiple markets.

    Preserves per-market results so the dashboard can drill down, plus
    portfolio-level totals so the operator gets one viability number for
    a basket trade.
    """

    capital_usd_per_market: float
    days: int
    leverage: float
    n_markets: int
    n_viable: int
    total_gross_pnl_usd: float
    total_costs_usd: float
    total_net_pnl_usd: float
    portfolio_apr_net_of_costs: float
    per_market: list[FundingCarryBacktestResult] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "capital_usd_per_market": self.capital_usd_per_market,
            "days": self.days,
            "leverage": self.leverage,
            "n_markets": self.n_markets,
            "n_viable": self.n_viable,
            "total_gross_pnl_usd": round(self.total_gross_pnl_usd, 2),
            "total_costs_usd": round(self.total_costs_usd, 2),
            "total_net_pnl_usd": round(self.total_net_pnl_usd, 2),
            "portfolio_apr_net_of_costs": round(self.portfolio_apr_net_of_costs, 4),
            "per_market": [r.to_dict() for r in self.per_market],
        }


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------


def _funding_at_period(
    initial_apr: float,
    period_idx: int,
    funding_period_hours: float,
    decay_days: float,
) -> float:
    """Linear decay of funding APR from ``initial_apr`` toward 0.

    Returns the funding rate *during* period ``period_idx`` (evaluated
    at the period's midpoint so the integral is exact for linear
    decay). When ``decay_days <= 0`` the funding stays constant
    indefinitely (no-decay scenario).

    Decay magnitude only — sign is preserved. So a -43% APR funding
    rate decays toward 0 from below; a +56% APR rate decays from above.
    """
    if decay_days <= 0:
        return initial_apr
    elapsed_days = (period_idx + 0.5) * funding_period_hours / 24.0
    if elapsed_days >= decay_days:
        return 0.0
    sign = 1.0 if initial_apr >= 0 else -1.0
    magnitude = abs(initial_apr) * (1.0 - elapsed_days / decay_days)
    return sign * magnitude


def _sortino(returns: list[float]) -> float:
    """Sortino against a 0% target. ``inf`` if no negatives, 0 if empty."""
    if not returns:
        return 0.0
    mean = sum(returns) / len(returns)
    downside = [r for r in returns if r < 0]
    if not downside:
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


def _decide_side(funding_apr: float, *, flat_threshold_apr: float = 1e-4) -> str:
    """Pick the carry side. ``flat`` if funding magnitude is below noise."""
    if abs(funding_apr) < flat_threshold_apr:
        return "flat"
    return "short" if funding_apr > 0 else "long"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


@dataclass
class _MarketSpec:
    """Market spec for portfolio simulation. Used only as input shape."""

    market_addr: str
    chain_id: int
    asset: str
    current_funding_apr: float


class FundingCarryBacktest:
    """Project net PnL for a GMX V2 funding-rate carry under realistic costs.

    Constructed once with cost + horizon assumptions, then called with
    one or more (market, funding) tuples. Pure / synchronous / no I/O —
    callers fetch the live funding APR upstream and feed it in.

    The deliberate I/O-free design lets the dashboard / agent / tests
    share exactly one cost-model implementation regardless of where the
    funding rate came from (live RPC, cached snapshot, synthetic).
    """

    def __init__(
        self,
        protocols_per_chain: dict[int, Any] | None = None,
        capital_usd: float = 10_000.0,
        days: int = 30,
        gmx_open_close_bps: float = 30.0,
        gmx_keeper_cost_per_funding_period_usd: float = 0.50,
        leverage: float = 1.0,
        funding_period_hours: float = 1.0,
        decay_days: float = 7.0,
    ) -> None:
        if capital_usd <= 0:
            raise ValueError("capital_usd must be positive")
        if days <= 0:
            raise ValueError("days must be positive")
        if leverage <= 0:
            raise ValueError("leverage must be positive")
        if funding_period_hours <= 0:
            raise ValueError("funding_period_hours must be positive")
        if gmx_open_close_bps < 0:
            raise ValueError("gmx_open_close_bps must be non-negative")
        if gmx_keeper_cost_per_funding_period_usd < 0:
            raise ValueError("gmx_keeper_cost_per_funding_period_usd must be non-negative")

        # ``protocols_per_chain`` is reserved for the live-fetch caller; the
        # backtester core never reads it. Stored so callers can introspect.
        self.protocols_per_chain = protocols_per_chain or {}
        self.capital_usd = float(capital_usd)
        self.days = int(days)
        self.gmx_open_close_bps = float(gmx_open_close_bps)
        self.gmx_keeper_cost_per_funding_period_usd = float(gmx_keeper_cost_per_funding_period_usd)
        self.leverage = float(leverage)
        self.funding_period_hours = float(funding_period_hours)
        self.decay_days = float(decay_days)

    def simulate(
        self,
        market_addr: str,
        chain_id: int,
        asset: str,
        current_funding_apr: float,
    ) -> FundingCarryBacktestResult:
        """Project PnL for one market given its current funding APR.

        Decides side: short if funding > 0, long if funding < 0,
        flat (zero PnL) if funding ≈ 0. Net PnL = funding collected
        - open/close costs - keeper costs.
        """
        side = _decide_side(current_funding_apr)
        notional = self.capital_usd * self.leverage

        if side == "flat":
            return self._zero_result(
                market_addr=market_addr,
                chain_id=chain_id,
                asset=asset,
                initial_funding_apr=current_funding_apr,
            )

        # Number of funding settlement periods over the horizon.
        n_periods = max(1, int(self.days * 24 / self.funding_period_hours))
        period_years = self.funding_period_hours / (24 * 365)

        # Round-trip cost: open + close, paid in bps of NOTIONAL (leverage
        # scales the position you're paying GMX fees on). Spread evenly
        # across periods so the per-period return series reflects the
        # true amortized burden — operator's equity curve doesn't show a
        # huge step at t=0 / t=horizon, and Sortino isn't artificially
        # punished by two outliers.
        open_close_costs_usd = self.gmx_open_close_bps / 10_000.0 * notional
        per_period_open_close = open_close_costs_usd / n_periods
        per_period_keeper = self.gmx_keeper_cost_per_funding_period_usd
        per_period_cost = per_period_open_close + per_period_keeper

        gross_pnl_usd = 0.0
        keeper_costs_usd = 0.0
        period_returns: list[float] = []
        equity_curve: list[float] = [self.capital_usd]

        for i in range(n_periods):
            funding_apr_period = _funding_at_period(
                initial_apr=current_funding_apr,
                period_idx=i,
                funding_period_hours=self.funding_period_hours,
                decay_days=self.decay_days,
            )
            # The carry side is fixed at t=0 by ``side``. If funding flips
            # sign mid-horizon (decay overshoots to opposite sign — should
            # never happen with linear-toward-zero decay, but defensively)
            # the carry side now PAYS funding, so the per-period gross is
            # negative.
            if side == "short":
                # Short collects funding when funding > 0.
                gross_period_pnl = funding_apr_period * notional * period_years
            else:
                # Long collects funding when funding < 0; flip sign so
                # collected is positive when funding is negative.
                gross_period_pnl = -funding_apr_period * notional * period_years

            net_period_pnl = gross_period_pnl - per_period_cost

            gross_pnl_usd += gross_period_pnl
            keeper_costs_usd += per_period_keeper
            period_returns.append(net_period_pnl / self.capital_usd)
            equity_curve.append(equity_curve[-1] + net_period_pnl)

        total_costs_usd = open_close_costs_usd + keeper_costs_usd
        total_pnl_usd = sum(period_returns) * self.capital_usd
        actual_years = (n_periods * self.funding_period_hours) / (24 * 365)
        apr = (total_pnl_usd / self.capital_usd) / max(actual_years, 1e-9)

        sortino = _sortino(period_returns)
        max_dd = _max_drawdown(equity_curve)
        if max_dd == 0:
            calmar = math.inf if apr > 0 else 0.0
        else:
            calmar = apr / max_dd

        # Cost-basis ratio uses |gross| because a short-side carry's
        # ``gross_pnl_usd`` can go negative if funding flips and decay
        # overshoots. Operator wants "what fraction of the funding income
        # was eaten by costs" — sign-agnostic.
        if abs(gross_pnl_usd) > 1e-9:
            cost_basis_pct = total_costs_usd / abs(gross_pnl_usd) * 100.0
        else:
            cost_basis_pct = math.inf if total_costs_usd > 0 else 0.0

        return FundingCarryBacktestResult(
            market_addr=market_addr,
            chain_id=chain_id,
            asset=asset,
            side=side,
            leverage=self.leverage,
            capital_usd=self.capital_usd,
            days=self.days,
            initial_funding_apr=current_funding_apr,
            n_funding_periods=n_periods,
            gross_pnl_usd=gross_pnl_usd,
            open_close_costs_usd=open_close_costs_usd,
            keeper_costs_usd=keeper_costs_usd,
            total_costs_usd=total_costs_usd,
            total_pnl_usd=total_pnl_usd,
            apr_net_of_costs=apr,
            sortino=sortino,
            calmar=calmar,
            max_drawdown_pct=max_dd,
            cost_basis_pct_of_pnl=cost_basis_pct,
            viable=total_pnl_usd > 0,
            period_returns=period_returns,
        )

    def simulate_portfolio(
        self,
        markets: list[dict[str, Any]],
    ) -> PortfolioBacktestResult:
        """Run all markets independently, aggregate.

        Each entry in ``markets`` must have keys ``market_addr``,
        ``chain_id``, ``asset``, ``current_funding_apr``. Each market is
        simulated with the SAME ``capital_usd`` (basket-equal-weight).
        Portfolio APR is computed against total deployed capital, NOT
        per-market capital — i.e. operator cares about return on the
        whole basket bankroll.
        """
        per_market: list[FundingCarryBacktestResult] = []
        total_gross = 0.0
        total_costs = 0.0
        total_net = 0.0

        for spec in markets:
            r = self.simulate(
                market_addr=spec["market_addr"],
                chain_id=spec["chain_id"],
                asset=spec["asset"],
                current_funding_apr=float(spec["current_funding_apr"]),
            )
            per_market.append(r)
            total_gross += r.gross_pnl_usd
            total_costs += r.total_costs_usd
            total_net += r.total_pnl_usd

        n_viable = sum(1 for r in per_market if r.viable)
        n_markets = len(per_market)
        # Portfolio APR uses TOTAL capital across the basket, so each
        # market dilutes the others' returns at fixed bankroll size —
        # honest reflection of equal-weight basket economics.
        total_capital = self.capital_usd * max(n_markets, 1)
        actual_years = self.days / 365.0
        portfolio_apr = (
            (total_net / total_capital) / max(actual_years, 1e-9) if total_capital > 0 else 0.0
        )

        return PortfolioBacktestResult(
            capital_usd_per_market=self.capital_usd,
            days=self.days,
            leverage=self.leverage,
            n_markets=n_markets,
            n_viable=n_viable,
            total_gross_pnl_usd=total_gross,
            total_costs_usd=total_costs,
            total_net_pnl_usd=total_net,
            portfolio_apr_net_of_costs=portfolio_apr,
            per_market=per_market,
        )

    # -- internals ---------------------------------------------------------

    def _zero_result(
        self,
        *,
        market_addr: str,
        chain_id: int,
        asset: str,
        initial_funding_apr: float,
    ) -> FundingCarryBacktestResult:
        """Flat result when funding is too close to zero to carry."""
        return FundingCarryBacktestResult(
            market_addr=market_addr,
            chain_id=chain_id,
            asset=asset,
            side="flat",
            leverage=self.leverage,
            capital_usd=self.capital_usd,
            days=self.days,
            initial_funding_apr=initial_funding_apr,
            n_funding_periods=0,
            gross_pnl_usd=0.0,
            open_close_costs_usd=0.0,
            keeper_costs_usd=0.0,
            total_costs_usd=0.0,
            total_pnl_usd=0.0,
            apr_net_of_costs=0.0,
            sortino=0.0,
            calmar=0.0,
            max_drawdown_pct=0.0,
            cost_basis_pct_of_pnl=0.0,
            viable=False,
            period_returns=[],
        )


def project_carry_pnl(
    market_addr: str,
    chain_id: int,
    asset: str,
    current_funding_apr: float,
    capital_usd: float = 10_000.0,
    days: int = 30,
    **kwargs: Any,
) -> FundingCarryBacktestResult:
    """Convenience: one-shot carry PnL projection.

    Wraps :class:`FundingCarryBacktest` so callers (dashboard tile,
    plugin tool) don't need to instantiate the class explicitly for
    common cases.
    """
    bt = FundingCarryBacktest(
        capital_usd=capital_usd,
        days=days,
        **kwargs,
    )
    return bt.simulate(
        market_addr=market_addr,
        chain_id=chain_id,
        asset=asset,
        current_funding_apr=current_funding_apr,
    )


__all__ = (
    "FundingCarryBacktest",
    "FundingCarryBacktestResult",
    "PortfolioBacktestResult",
    "project_carry_pnl",
)
