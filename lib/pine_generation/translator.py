"""Python strategy → Pine Script v5 translator.

Pure functions only. No I/O outside template loading. No network calls. No
imports from `lib.portfolio`, `lib.trading`, or `lib.analytics.strategies`
(strategies.py is read-only context — we model its parameter shape via a
parallel dataclass, not by importing it, so this module is regression-isolated
from the trading critical path).

Translation map
---------------
The 5 production strategy classes plus the base-strategy and params-only
forms map onto matching Jinja templates under :mod:`lib.pine_generation.templates`:

    RegimeAwareRSI         → regime_aware_rsi.pine.j2
    FundingRateContrarian  → funding_rate_contrarian.pine.j2
    CorrelationBreakout    → correlation_breakout.pine.j2
    MultiTFMomentum        → multi_tf_momentum.pine.j2
    SapphireComposite      → sapphire_composite.pine.j2
    BaseStrategy           → base_strategy.pine.j2  (RSI mean-reversion only)
    StrategyParams         → params_only.pine.j2    (renders inputs scaffold)

The translator does NOT execute the Python strategy or import strategies.py.
Strategy semantics are encoded in the templates plus the per-strategy spec
helpers below — this keeps the lane safely insulated from any future change to
strategies.py and makes the Pine output reviewable as a static artifact.

How regime, funding, and correlation indicators map
---------------------------------------------------
- Regime detection (RegimeAwareRSI / SapphireComposite): the Python uses
  `aux["btc"]` for cross-symbol regime context. In Pine, we use
  `request.security("CRYPTOCAP:BTC", timeframe.period, close)` to read the BTC
  reference series, then compute the same `regime_period`-bar return and
  classify against the same `regime_on_threshold` / `regime_off_threshold`.
  The aux series is only fetched when the strategy actually needs it; otherwise
  we use the chart symbol's own bars.
- Funding-rate proxy (FundingRateContrarian / SapphireComposite): the Python
  uses 3-day momentum as a proxy for crowded positioning. We translate that
  literally — `(close - close[3]) / close[3]` — keeping the Python's
  `funding_high` / `funding_low` thresholds verbatim.
- Correlation (CorrelationBreakout / SapphireComposite): the Python uses
  `aux["spy"]` for SPY bars. In Pine, we use
  `request.security("AMEX:SPY", timeframe.period, close)` for the SPY reference
  series and then build `corr_period`-window Pearson correlation between
  symbol and SPY daily returns using `ta.correlation`. This is the Pine native
  rolling correlation function, which matches the Python `_pearson` semantics
  for log-returns over the same window.
- Multi-TF momentum (MultiTFMomentum / SapphireComposite): the Python uses
  RSI(7) as a 4H proxy, 20-SMA as daily trend, and 5-day return as a weekly
  proxy. The Pine version reads from the chart's native timeframe and uses
  `ta.rsi(close, tf_fast)`, `ta.sma(close, 20)`, and `(close - close[5])` for
  the same three components.
- Composite gating (SapphireComposite): the Python builds a 0–100 score from
  five components. The Pine template builds the identical score and only
  enters when `score >= composite_threshold`. The quarter-Kelly sizing is
  approximated via `default_qty_value` set to `kelly_size * 100` percent.

Aux-symbol lookups in Pine
--------------------------
`request.security` is the Pine v5 way to reference a different symbol. We pin
the timeframe to `timeframe.period` (matches the chart) so the aux series
aligns with the chart bars. The translator never embeds API keys, never reads
`/data/`, and never makes HTTP calls.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

# Jinja2 is available transitively via Flask in requirements-test.txt and is
# already imported by services/dashboard. Importing it lazily keeps the unit
# suite collectable even on a clean checkout.
try:
    from jinja2 import Environment, FileSystemLoader, StrictUndefined

    _JINJA_AVAILABLE = True
except ImportError:  # pragma: no cover - tested via fallback path
    _JINJA_AVAILABLE = False
    Environment = None  # type: ignore[assignment,misc]
    FileSystemLoader = None  # type: ignore[assignment,misc]
    StrictUndefined = None  # type: ignore[assignment,misc]

TEMPLATE_DIR = Path(__file__).parent / "templates"

SUPPORTED_STRATEGIES: list[str] = [
    "RegimeAwareRSI",
    "FundingRateContrarian",
    "CorrelationBreakout",
    "MultiTFMomentum",
    "SapphireComposite",
    "BaseStrategy",
    "StrategyParams",
]

# Strategy → template-file map. The 7 supported strategies have one template
# file each, all under templates/.
STRATEGY_TEMPLATE_MAP: dict[str, str] = {
    "RegimeAwareRSI": "regime_aware_rsi.pine.j2",
    "FundingRateContrarian": "funding_rate_contrarian.pine.j2",
    "CorrelationBreakout": "correlation_breakout.pine.j2",
    "MultiTFMomentum": "multi_tf_momentum.pine.j2",
    "SapphireComposite": "sapphire_composite.pine.j2",
    "BaseStrategy": "base_strategy.pine.j2",
    "StrategyParams": "params_only.pine.j2",
}

# TradingView ticker prefix mapping. Sapphire backtests use names like "BTC"
# or "BTC-USD"; Pine `strategy()` symbols use exchange-prefixed names. The
# translator rewrites unknown tickers as-is; known crypto/equity aliases get
# mapped to canonical Pine symbols.
SYMBOL_PREFIX_MAP: dict[str, str] = {
    # Crypto (CoinMarketCap caps tickers via TradingView's CRYPTOCAP feed)
    "BTC": "CRYPTOCAP:BTC",
    "BTC-USD": "BINANCE:BTCUSDT",
    "BTCUSD": "BINANCE:BTCUSDT",
    "BTCUSDT": "BINANCE:BTCUSDT",
    "ETH": "CRYPTOCAP:ETH",
    "ETH-USD": "BINANCE:ETHUSDT",
    "ETHUSD": "BINANCE:ETHUSDT",
    "ETHUSDT": "BINANCE:ETHUSDT",
    "SOL": "CRYPTOCAP:SOL",
    "SOL-USD": "BINANCE:SOLUSDT",
    "SOLUSD": "BINANCE:SOLUSDT",
    "SOLUSDT": "BINANCE:SOLUSDT",
    # Equities
    "SPY": "AMEX:SPY",
    "QQQ": "NASDAQ:QQQ",
    "TSLA": "NASDAQ:TSLA",
    "AAPL": "NASDAQ:AAPL",
    "NVDA": "NASDAQ:NVDA",
}

# Default reference-symbol mapping used for aux-data Pine `request.security`
# calls. Strategy templates reference these via Jinja vars: `btc_ref_symbol`,
# `spy_ref_symbol`.
DEFAULT_BTC_REF = "CRYPTOCAP:BTC"
DEFAULT_SPY_REF = "AMEX:SPY"


# ---------------------------------------------------------------------------
# Parameter dataclass
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PineParams:
    """Parameter bundle for one Pine generation run.

    Mirrors :class:`lib.analytics.strategies.StrategyParams` field-for-field
    but is a parallel dataclass. We DO NOT import StrategyParams to avoid
    coupling pine_generation to the trading critical path.
    """

    # ── swept dimensions ──────────────────────────────────────────────────
    rsi_period: int = 14
    sl_pct: float = 0.05
    tp_pct: float = 0.10

    # ── regime ────────────────────────────────────────────────────────────
    regime_period: int = 20
    regime_on_threshold: float = 0.05
    regime_off_threshold: float = -0.05

    # ── funding proxy ─────────────────────────────────────────────────────
    funding_high: float = 0.020
    funding_low: float = -0.015

    # ── correlation ───────────────────────────────────────────────────────
    corr_period: int = 20
    corr_threshold: float = 0.30

    # ── multi-TF ──────────────────────────────────────────────────────────
    tf_fast: int = 7
    tf_slow: int = 5

    # ── composite gate ────────────────────────────────────────────────────
    composite_threshold: float = 55.0

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PineParams:
        """Construct from a partial dict; unknown fields are dropped."""
        if not isinstance(data, dict):
            raise TypeError(f"PineParams.from_dict expects dict, got {type(data).__name__}")
        valid_fields = {f.name for f in cls.__dataclass_fields__.values()}
        kwargs = {k: v for k, v in data.items() if k in valid_fields}
        return cls(**kwargs)


@dataclass(frozen=True)
class PineSpec:
    """One Pine generation request.

    Attributes:
        strategy: One of :data:`SUPPORTED_STRATEGIES`.
        symbol: Canonical Sapphire symbol (e.g. "BTC", "BTC-USD"); the
            translator maps this to a TradingView-prefixed ticker.
        params: Parameters for the strategy.
        title: Optional human-readable title; defaults to
            "Sapphire {strategy} – {symbol}".
        initial_capital: Pine `strategy(initial_capital=...)`. Defaults to 1000.
        commission_pct: Pine commission percent. Defaults to 0.05 (5 bps).
        kelly_size_pct: Optional override for the SapphireComposite default
            `default_qty_value`; if None, the template computes a quarter-Kelly
            from sl_pct / tp_pct ratio.
        btc_ref_symbol: Override for the BTC reference symbol.
        spy_ref_symbol: Override for the SPY reference symbol.
        meta: Optional metadata dict embedded as a Pine comment header.
    """

    strategy: str
    symbol: str
    params: PineParams = field(default_factory=PineParams)
    title: str | None = None
    initial_capital: float = 1000.0
    commission_pct: float = 0.05
    kelly_size_pct: float | None = None
    btc_ref_symbol: str = DEFAULT_BTC_REF
    spy_ref_symbol: str = DEFAULT_SPY_REF
    meta: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.strategy not in SUPPORTED_STRATEGIES:
            raise ValueError(
                f"Unsupported strategy '{self.strategy}'. "
                f"Must be one of: {', '.join(SUPPORTED_STRATEGIES)}"
            )
        if not self.symbol or not isinstance(self.symbol, str):
            raise ValueError(f"symbol must be a non-empty string; got {self.symbol!r}")
        if self.initial_capital <= 0:
            raise ValueError(f"initial_capital must be > 0; got {self.initial_capital}")
        if not 0 <= self.commission_pct <= 1.0:
            raise ValueError(
                f"commission_pct must be in [0, 1.0]; got {self.commission_pct}"
            )

    @property
    def resolved_title(self) -> str:
        if self.title:
            return self.title
        return f"Sapphire {self.strategy} – {self.symbol}"

    @property
    def tv_symbol(self) -> str:
        """The TradingView-prefixed ticker for this symbol."""
        return SYMBOL_PREFIX_MAP.get(self.symbol.upper(), self.symbol)


def available_strategies() -> list[str]:
    """Return the list of strategy class names this lane supports."""
    return list(SUPPORTED_STRATEGIES)


# ---------------------------------------------------------------------------
# Backtest-row → spec conversion
# ---------------------------------------------------------------------------


def spec_from_backtest_row(row: dict[str, Any]) -> PineSpec:
    """Construct a PineSpec from a `best_per_symbol_*.json` row.

    The expected row shape comes from
    :func:`lib.analytics.strategies.SweepResult.to_dict`:
        {
          "strategy_cls": "SapphireComposite",
          "symbol": "BTC-USD",
          "params": {"rsi_period": 14, "sl_pct": 0.05, "tp_pct": 0.10},
          ...
        }
    """
    if not isinstance(row, dict):
        raise TypeError(f"spec_from_backtest_row expects dict, got {type(row).__name__}")
    strategy = row.get("strategy_cls")
    if not strategy:
        raise ValueError("backtest row missing 'strategy_cls'")
    if strategy not in SUPPORTED_STRATEGIES:
        raise ValueError(
            f"backtest row strategy '{strategy}' is not a supported pine_generation "
            f"target (supported: {', '.join(SUPPORTED_STRATEGIES)})"
        )
    symbol = row.get("symbol")
    if not symbol:
        raise ValueError("backtest row missing 'symbol'")

    params_raw = row.get("params") or {}
    params = PineParams.from_dict(params_raw)

    meta = {
        "sortino": row.get("sortino"),
        "sharpe": row.get("sharpe"),
        "win_rate": row.get("win_rate"),
        "profit_factor": row.get("profit_factor"),
        "total_trades": row.get("total_trades"),
        "max_drawdown_pct": row.get("max_drawdown_pct"),
        "total_return_pct": row.get("total_return_pct"),
    }
    return PineSpec(strategy=strategy, symbol=symbol, params=params, meta=meta)


# ---------------------------------------------------------------------------
# Helpers used by templates (pre-rendered context)
# ---------------------------------------------------------------------------


def _kelly_size(sl_pct: float, tp_pct: float, win_prob: float = 0.55) -> float:
    """Quarter-Kelly fraction using tp/sl as reward:risk proxy.

    Mirrors :meth:`lib.analytics.strategies.SapphireComposite._kelly_size`
    so the generated Pine percent matches the Python sizing.
    """
    if sl_pct <= 0:
        b = 2.0
    else:
        b = tp_pct / sl_pct
    f = win_prob - (1.0 - win_prob) / b
    return max(0.05, min(0.50, round(f * 0.25, 3)))


def _format_pct(value: float) -> str:
    """Format a fraction for human consumption in Pine comments."""
    return f"{value:+.2%}"


def _build_template_context(spec: PineSpec) -> dict[str, Any]:
    """Materialise the per-strategy template variables.

    Centralises the float-to-Pine conversions so templates stay declarative.
    """
    p = spec.params
    if spec.kelly_size_pct is not None:
        kelly_pct = spec.kelly_size_pct
    else:
        kelly_pct = _kelly_size(p.sl_pct, p.tp_pct) * 100.0

    # Pine `default_qty_value` for percent_of_equity is in [0, 100].
    default_qty_value = max(1.0, min(100.0, kelly_pct))

    generated_at = datetime.now(UTC).replace(microsecond=0).isoformat()

    return {
        "strategy_cls": spec.strategy,
        "symbol": spec.symbol,
        "tv_symbol": spec.tv_symbol,
        "title": spec.resolved_title,
        "initial_capital": spec.initial_capital,
        "commission_pct": spec.commission_pct,
        "default_qty_value": default_qty_value,
        "kelly_pct": kelly_pct,
        "btc_ref_symbol": spec.btc_ref_symbol,
        "spy_ref_symbol": spec.spy_ref_symbol,
        "generated_at": generated_at,
        "version": "0.1.0",
        "meta": spec.meta,
        # Parameter scalars rendered into Pine `input.*` defaults
        "rsi_period": p.rsi_period,
        "sl_pct": p.sl_pct,
        "tp_pct": p.tp_pct,
        "sl_pct_str": f"{p.sl_pct * 100:.2f}",
        "tp_pct_str": f"{p.tp_pct * 100:.2f}",
        "regime_period": p.regime_period,
        "regime_on_threshold": p.regime_on_threshold,
        "regime_off_threshold": p.regime_off_threshold,
        "regime_on_threshold_str": f"{p.regime_on_threshold:.4f}",
        "regime_off_threshold_str": f"{p.regime_off_threshold:.4f}",
        "funding_high": p.funding_high,
        "funding_low": p.funding_low,
        "funding_high_str": f"{p.funding_high:.4f}",
        "funding_low_str": f"{p.funding_low:.4f}",
        "corr_period": p.corr_period,
        "corr_threshold": p.corr_threshold,
        "corr_threshold_str": f"{p.corr_threshold:.4f}",
        "tf_fast": p.tf_fast,
        "tf_slow": p.tf_slow,
        "composite_threshold": p.composite_threshold,
        "composite_threshold_str": f"{p.composite_threshold:.2f}",
    }


# ---------------------------------------------------------------------------
# Stdlib-only fallback renderer (used when Jinja2 is unavailable)
# ---------------------------------------------------------------------------


_VAR_PATTERN = re.compile(r"\{\{\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*\}\}")


def _stdlib_render(template_text: str, context: dict[str, Any]) -> str:
    """Render the simple `{{var}}` substitutions our templates rely on.

    The templates intentionally avoid Jinja control flow (no `{% if %}`,
    no `{% for %}`) so this stdlib fallback is sufficient and identical to
    the Jinja output for every supported template.
    """

    def _replace(match: re.Match[str]) -> str:
        key = match.group(1)
        if key not in context:
            raise KeyError(f"template variable '{key}' missing from context")
        return str(context[key])

    return _VAR_PATTERN.sub(_replace, template_text)


def _jinja_env() -> Any:
    """Return a Jinja2 Environment bound to the templates dir."""
    if not _JINJA_AVAILABLE:
        return None
    return Environment(
        loader=FileSystemLoader(str(TEMPLATE_DIR)),
        undefined=StrictUndefined,
        keep_trailing_newline=True,
        autoescape=False,
    )


# ---------------------------------------------------------------------------
# Public entrypoint
# ---------------------------------------------------------------------------


def generate_pine(spec: PineSpec) -> str:
    """Translate a PineSpec into Pine v5 source string.

    The output always starts with a comment header documenting the spec, then
    `//@version=5` on its own line, then the `strategy(...)` declaration, then
    the strategy logic.

    Raises:
        ValueError: if the strategy template cannot be loaded.
    """
    if not isinstance(spec, PineSpec):
        raise TypeError(f"generate_pine expects PineSpec, got {type(spec).__name__}")

    template_name = STRATEGY_TEMPLATE_MAP[spec.strategy]
    template_path = TEMPLATE_DIR / template_name
    if not template_path.exists():
        raise ValueError(
            f"template not found for strategy '{spec.strategy}': {template_path}"
        )

    context = _build_template_context(spec)

    if _JINJA_AVAILABLE:
        env = _jinja_env()
        template = env.get_template(template_name)
        rendered = template.render(**context)
    else:  # pragma: no cover - exercised when jinja2 is absent
        rendered = _stdlib_render(template_path.read_text(), context)

    # Final post-processing: ensure trailing newline, strip CR.
    rendered = rendered.replace("\r\n", "\n")
    if not rendered.endswith("\n"):
        rendered = rendered + "\n"
    return rendered
