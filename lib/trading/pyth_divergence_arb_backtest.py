"""Cross-chain Pyth oracle divergence arb PnL backtest module.

Turns the live cross-chain Pyth divergence signal
(:mod:`lib.chains.cross_chain.pyth_divergence`) into a *projected
dollar PnL* under realistic bridge + gas costs and a divergence-
decay model. PnL is king per Sapphire's stated user preference; an
"interesting" 142 bps BTC divergence is just a number until it's
been turned into "$X projected over 30 days at $10K capital, net of
$Y costs."

Why a sibling module instead of bolting onto
:mod:`lib.trading.cross_chain_arb_backtest`:

* The Aave APY arb is a *yield* signal — gross PnL accrues
  continuously over the holding period (interest accrues per second).
* The Pyth divergence is a *price* signal — gross PnL is captured
  *once* per round-trip when the prices converge. That's a different
  shape (point-in-time capture vs. continuous accrual).
* Different decay model: the Aave spread decays as capital chases
  the yield differential; the Pyth divergence decays as the slower
  chain's keeper updates the cache. Different driver, different
  half-life, different shape.

Design pragmatic: we model an arbitrageur who, per cycle, *bridges*
to the cheap chain, captures the spread, then bridges back. Each
cycle pays the round-trip bridge cost + gas at both legs. The
spread compresses linearly toward zero over the configured decay
horizon (default 7 days, faster than Aave's 14 days because Pyth
keepers refresh on a much shorter cadence in normal conditions).

Defaults reflect *small-scale* (Sapphire-typical) conditions:

* ``capital_usd = 10_000`` — Sapphire's actual operating scale; do
  NOT bake in $1M-style assumptions that hide cost dominance.
* ``bridge_cost_bps_per_round_trip = None`` — defaults to a *tiered
  lookup* via :func:`bridge_cost_bps_for_capital` (PR #610 model),
  which returns 3 bps at $10K capital scaling up to 5 bps at $1M+.
* ``gas_cost_usd_per_action = 2.50`` — average of L2 gas for a
  bridge in + bridge out (Optimism cheap, Arbitrum mid).
* ``holding_period_hours = 24`` — daily rebalance frequency.
* ``decay_days = 7.0`` — Pyth divergences typically close within a
  week as off-chain publishers force keeper refreshes; 7 days is
  conservative enough to capture meaningful PnL while not assuming
  an unrealistic "spread persists forever" tail.

The output is a :class:`BacktestResult` dataclass whose key
headline metric is ``cost_basis_pct_of_pnl`` — what fraction of the
*gross* divergence-PnL is eaten by bridge + gas. Above ~50 % at
small capital strongly suggests the strategy needs $100 K+ to be
viable. Above ~100 % the strategy is unviable at the chosen scale —
typical for Pyth divergences at the basis-point levels Sapphire
observes in normal market conditions.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

from lib.chains.cross_chain.pyth_divergence import (
    CrossChainPythScanner,
    PythDivergenceSignal,
)

# ---------------------------------------------------------------------------
# Bridge cost tiers — calibrated 2026-05-03 from live Across/Hop/Stargate/CCTP
# quotes for USDC ARB <-> OP. See PR #610 (bridge-cost-calibration).
#
# Each tier = (max_capital_usd_inclusive, round_trip_bps). Lookup picks the
# *first* tier whose threshold is >= capital_usd. The tail tier (math.inf)
# captures whale-scale capital where Across LP fees creep up to ~2 bps per
# leg (~4 bps round-trip).
#
# Per leg ≈ Across one-way fee (~1.5 bps observed). Round-trip = 2x leg.
# Re-survey monthly. Update tiers if any value shifts more than 0.5 bps.
# ---------------------------------------------------------------------------
BRIDGE_COST_TIERS: tuple[tuple[float, float], ...] = (
    (10_000.0, 3.0),       # <= $10k:    ~1.5 bps x 2 legs (Across)
    (100_000.0, 3.5),      # <= $100k:   ~1.5-1.75 bps x 2 legs (Across)
    (1_000_000.0, 4.0),    # <= $1M:     ~2 bps x 2 legs (LP fee creep)
    (math.inf, 5.0),       # >  $1M:     ~2.5 bps x 2 legs (whale, slippage)
)


def bridge_cost_bps_for_capital(capital_usd: float) -> float:
    """Return calibrated round-trip bridge cost in bps for ``capital_usd``.

    Looks up :data:`BRIDGE_COST_TIERS` and picks the first tier whose
    inclusive threshold is >= ``capital_usd``. The tail tier
    (``math.inf``) guarantees a value is always returned.

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
    return BRIDGE_COST_TIERS[-1][1]


@dataclass(frozen=True)
class BacktestResult:
    """Projected PnL + risk metrics for one cross-chain Pyth-arb scenario.

    All dollar fields are floats (not Decimal) — by the time we
    surface a backtest result the upstream basis-point precision has
    already been spent and the dashboard wants plain JSON numbers.

    The operator-critical field is ``cost_basis_pct_of_pnl``: how
    much of the *gross* divergence PnL the bridge + gas costs eat.
    > 100 means the strategy lost money at the chosen capital level
    even though the raw divergence was positive — a structural
    unviability flag, common for Pyth divergences at small capital.
    """

    asset: str
    """Underlying asset symbol (e.g. ``"BTC"``)."""

    capital_usd: float
    """Notional capital deployed in the simulation."""

    days: int
    """Simulated horizon in days."""

    initial_divergence_bps: float
    """Divergence at t=0, in basis points (e.g. 142 for a live
    BTC observation)."""

    n_rebalances: int
    """Number of rebalance cycles simulated over the horizon."""

    gross_pnl_usd: float
    """Divergence-only PnL with NO costs deducted. Always >= 0 by
    construction (divergence is non-negative)."""

    total_costs_usd: float
    """Sum of all bridge + gas costs across rebalances."""

    total_pnl_usd: float
    """Net PnL after costs. Can be negative (and frequently is for
    Pyth divergences at $10K capital — a common honest result)."""

    apr_net_of_costs: float
    """Annualized return on ``capital_usd``, net of costs (decimal
    fraction, e.g. 0.045 == 4.5 % APR)."""

    sortino: float
    """Sortino ratio of per-period returns. ``inf`` if no negative
    returns; ``0.0`` if no returns at all."""

    calmar: float
    """Calmar ratio = APR / |max drawdown|. ``inf`` if no drawdown,
    ``0.0`` if no returns."""

    max_drawdown_pct: float
    """Worst peak-to-trough drawdown over the simulation, as a
    fraction (0.05 == 5 %)."""

    cost_basis_pct_of_pnl: float
    """``total_costs_usd / max(1e-9, gross_pnl_usd) * 100``. Headline
    viability metric: > 100 means costs ate the entire gross PnL."""

    bridge_cost_bps_used: float
    """Bridge cost (round-trip bps) actually applied in the
    simulation. Surfaced because the default tiered lookup means the
    same capital amount picks different bps at different scales — the
    operator needs to see what the model used."""

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
            "initial_divergence_bps": self.initial_divergence_bps,
            "n_rebalances": self.n_rebalances,
            "gross_pnl_usd": round(self.gross_pnl_usd, 2),
            "total_costs_usd": round(self.total_costs_usd, 2),
            "total_pnl_usd": round(self.total_pnl_usd, 2),
            "apr_net_of_costs": round(self.apr_net_of_costs, 4),
            "sortino": _safe(
                round(self.sortino, 4) if not math.isinf(self.sortino) else self.sortino
            ),
            "calmar": _safe(
                round(self.calmar, 4) if not math.isinf(self.calmar) else self.calmar
            ),
            "max_drawdown_pct": round(self.max_drawdown_pct, 4),
            "cost_basis_pct_of_pnl": round(self.cost_basis_pct_of_pnl, 2),
            "bridge_cost_bps_used": round(self.bridge_cost_bps_used, 4),
        }


def _divergence_at_period(
    initial_bps: float,
    period_idx: int,
    holding_period_hours: float,
    decay_days: float,
) -> float:
    """Linear decay from ``initial_bps`` to 0 over ``decay_days``.

    Returns the divergence *during* period ``period_idx`` (evaluated
    at the period's midpoint so the integral is exact for linear
    decay). When ``decay_days <= 0`` the divergence stays constant
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


class PythArbBacktest:
    """Project net PnL for a cross-chain Pyth divergence arb.

    Construction wires together a live scanner (or a pre-fetched
    signal) with the cost model and horizon. Call :meth:`simulate`
    repeatedly with different assets to compare them under the same
    cost regime.

    The scanner is optional: if you already have a signal in hand
    (e.g. captured during a dashboard tick), call
    :meth:`simulate_from_signal` directly to skip the live RPC
    roundtrip.

    Spread-capture model: per rebalance cycle, the arbitrageur
    bridges to the cheap chain, captures the spread *once* (price
    convergence), then bridges back. Total realized PnL per cycle =
    ``divergence_during_period_bps / 10_000 * capital - bridge_cost
    - 2 * gas_cost``. Two gas costs because each round-trip is two
    bridge actions.
    """

    def __init__(
        self,
        scanner: CrossChainPythScanner | None = None,
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
        # None → tiered lookup at simulation time. Explicit override is
        # preserved as-is so tests can pin a specific bps.
        self._bridge_cost_override = (
            float(bridge_cost_bps_per_round_trip)
            if bridge_cost_bps_per_round_trip is not None
            else None
        )
        self.gas_cost_usd_per_action = float(gas_cost_usd_per_action)
        self.holding_period_hours = float(holding_period_hours)
        self.decay_days = float(decay_days)

    # -- public API --------------------------------------------------------

    @property
    def bridge_cost_bps_per_round_trip(self) -> float:
        """The bridge cost (bps) the simulation will use.

        If an explicit override was passed to the constructor, that's
        returned. Otherwise the tiered model picks the bps appropriate
        for ``capital_usd``.
        """
        if self._bridge_cost_override is not None:
            return self._bridge_cost_override
        return bridge_cost_bps_for_capital(self.capital_usd)

    async def simulate(self, asset: str = "BTC") -> BacktestResult:
        """Fetch the live signal for ``asset`` and project PnL.

        Requires a scanner in the constructor. The signal's
        ``max_divergence_bps`` is used as the initial divergence.

        If the scanner emits no signal (asset below the
        ``MIN_SIGNAL_DIVERGENCE_BPS`` floor or unavailable), returns
        a zero-PnL :class:`BacktestResult` rather than raising —
        easier for the dashboard / agent to render an "all quiet"
        state.
        """
        if self.scanner is None:
            raise ValueError(
                "simulate() requires a scanner; pass one to the constructor "
                "or call simulate_from_signal() with a pre-fetched signal."
            )
        sig = await self.scanner.scan_asset(asset)
        if sig is None:
            return self._zero_result(asset, initial_divergence_bps=0.0)
        return self.simulate_from_signal(sig)

    def simulate_from_signal(self, signal: PythDivergenceSignal) -> BacktestResult:
        """Project PnL from a pre-fetched :class:`PythDivergenceSignal`.

        Pure / synchronous / no I/O — safe to call inside a sync code
        path. Divergence used = ``signal.max_divergence_bps`` because
        that's the gap an executor would actually rotate across.
        """
        return self._simulate_with_initial_divergence(
            asset=signal.asset,
            initial_divergence_bps=float(signal.max_divergence_bps),
        )

    def simulate_with_divergence(
        self, asset: str, initial_divergence_bps: float
    ) -> BacktestResult:
        """Project PnL given an explicit initial divergence (bps).

        Public hook used by tests to drive the model with synthetic
        inputs and by callers who want to ask "what if the divergence
        were 500 bps?" without going through a signal.
        """
        if initial_divergence_bps < 0:
            raise ValueError("initial_divergence_bps must be non-negative")
        return self._simulate_with_initial_divergence(asset, initial_divergence_bps)

    # -- internals ---------------------------------------------------------

    def _simulate_with_initial_divergence(
        self, asset: str, initial_divergence_bps: float
    ) -> BacktestResult:
        """Core simulation loop. Both signal-driven and explicit-
        divergence callers funnel through here so the cost model has
        exactly one implementation."""
        if initial_divergence_bps == 0:
            return self._zero_result(asset, initial_divergence_bps=0.0)

        n_rebalances = max(1, int(self.days * 24 / self.holding_period_hours))
        bridge_bps = self.bridge_cost_bps_per_round_trip

        # Per-rebalance cost: round-trip bridge + 2 gas actions
        # (bridge-out + bridge-back).
        bridge_cost_usd = bridge_bps / 10_000.0 * self.capital_usd
        per_period_cost_usd = bridge_cost_usd + 2 * self.gas_cost_usd_per_action

        gross_pnl_usd = 0.0
        total_costs_usd = 0.0
        period_returns: list[float] = []
        equity_curve: list[float] = [self.capital_usd]

        for i in range(n_rebalances):
            div_bps = _divergence_at_period(
                initial_bps=initial_divergence_bps,
                period_idx=i,
                holding_period_hours=self.holding_period_hours,
                decay_days=self.decay_days,
            )
            # Price-arb: divergence is captured ONCE per cycle (point-
            # in-time convergence), not as continuous accrual. So the
            # gross per-period PnL is just (div_bps / 10000) * capital,
            # *not* scaled by the period length. This is the structural
            # difference vs. the Aave APY-arb model.
            gross_period_pnl = div_bps / 10_000.0 * self.capital_usd
            net_period_pnl = gross_period_pnl - per_period_cost_usd

            gross_pnl_usd += gross_period_pnl
            total_costs_usd += per_period_cost_usd
            period_returns.append(net_period_pnl / self.capital_usd)
            equity_curve.append(equity_curve[-1] + net_period_pnl)

        total_pnl_usd = sum(period_returns) * self.capital_usd
        actual_years = (n_rebalances * self.holding_period_hours) / (24 * 365)
        apr = (total_pnl_usd / self.capital_usd) / max(actual_years, 1e-9)

        sortino = _sortino(period_returns)
        max_dd = _max_drawdown(equity_curve)
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
            initial_divergence_bps=initial_divergence_bps,
            n_rebalances=n_rebalances,
            gross_pnl_usd=gross_pnl_usd,
            total_costs_usd=total_costs_usd,
            total_pnl_usd=total_pnl_usd,
            apr_net_of_costs=apr,
            sortino=sortino,
            calmar=calmar,
            max_drawdown_pct=max_dd,
            cost_basis_pct_of_pnl=cost_basis_pct,
            bridge_cost_bps_used=bridge_bps,
            period_returns=period_returns,
        )

    def _zero_result(
        self, asset: str, *, initial_divergence_bps: float
    ) -> BacktestResult:
        """Flat zero-PnL result (used when there's no signal)."""
        return BacktestResult(
            asset=asset,
            capital_usd=self.capital_usd,
            days=self.days,
            initial_divergence_bps=initial_divergence_bps,
            n_rebalances=0,
            gross_pnl_usd=0.0,
            total_costs_usd=0.0,
            total_pnl_usd=0.0,
            apr_net_of_costs=0.0,
            sortino=0.0,
            calmar=0.0,
            max_drawdown_pct=0.0,
            cost_basis_pct_of_pnl=0.0,
            bridge_cost_bps_used=self.bridge_cost_bps_per_round_trip,
            period_returns=[],
        )


def project_pnl_for_pyth_signal(
    signal: PythDivergenceSignal,
    capital_usd: float = 10_000.0,
    days: int = 30,
    **kwargs: Any,
) -> BacktestResult:
    """Convenience: one-shot PnL projection for a Pyth divergence signal.

    Wraps :class:`PythArbBacktest` so callers (dashboard tile, plugin
    tool) don't need to instantiate the class explicitly for common
    cases.

    Extra ``**kwargs`` flow through to the constructor so callers can
    still override ``bridge_cost_bps_per_round_trip``, ``decay_days``,
    etc.
    """
    bt = PythArbBacktest(capital_usd=capital_usd, days=days, **kwargs)
    return bt.simulate_from_signal(signal)


__all__ = (
    "BRIDGE_COST_TIERS",
    "BacktestResult",
    "PythArbBacktest",
    "bridge_cost_bps_for_capital",
    "project_pnl_for_pyth_signal",
)
