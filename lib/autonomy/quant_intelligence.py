"""Read-only quant intelligence flywheel.

This module turns Sapphire's existing market, TradingView, backtest,
walk-forward, source-quality, and paper-shadow surfaces into a single
machine-readable operating loop. It is intentionally non-executing: the output
can rank work, assign research lanes, and define promotion gates, but it cannot
sign orders, place trades, mutate TradingView, or send Telegram messages.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
SCHEMA_VERSION = 1
SAFE_MODES = frozenset({"read_only", "dry_run", "paper"})
PRIORITY_ORDER = {"P1": 0, "P2": 1, "P3": 2}

SOURCE_DOCS = (
    "https://www.aqr.com/Insights/Research/Journal-Article/Time-Series-Momentum",
    "https://papers.ssrn.com/sol3/papers.cfm?abstract_id=3386035",
    "https://skfolio.org/generated/skfolio.model_selection.CombinatorialPurgedCV.html",
    "https://fred.stlouisfed.org/docs/api/fred/",
    "https://api-docs.defillama.com/",
    "https://docs.coingecko.com/",
    "https://www.sec.gov/search-filings/edgar-application-programming-interfaces",
    "https://www.cftc.gov/MarketReports/index.htm",
    "https://www.cboe.com/tradable-products/vix/",
    "https://www.cmegroup.com/tools-information/quikstrike/cme-fedwatch-tool-user-guide.html",
    "https://www.tradingview.com/support/solutions/43000529348-how-to-configure-webhook-alerts/",
)


@dataclass(frozen=True)
class QuantWorkOrder:
    """One non-executing unit in the quant intelligence loop."""

    id: str
    lane: str
    priority: str
    title: str
    description: str
    target_runtime: str
    safe_mode: str
    cadence: str
    symbols: tuple[str, ...] = ()
    inputs: tuple[str, ...] = ()
    local_surfaces: tuple[str, ...] = ()
    command: str | None = None
    expected_artifacts: tuple[str, ...] = ()
    acceptance: tuple[str, ...] = ()
    blocked_by: tuple[str, ...] = ()
    source_docs: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        row = asdict(self)
        for key in (
            "symbols",
            "inputs",
            "local_surfaces",
            "expected_artifacts",
            "acceptance",
            "blocked_by",
            "source_docs",
        ):
            row[key] = list(row[key])
        return {key: value for key, value in row.items() if value not in (None, [], {})}


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _exists(*parts: str) -> bool:
    return (ROOT / Path(*parts)).exists()


def _safe_error(exc: Exception) -> str:
    return f"{type(exc).__name__}: {exc}"


def _call_market_universe(fetch_live: bool) -> tuple[dict[str, Any], list[str]]:
    try:
        from lib.trading.strategy_lab import build_market_universe

        return build_market_universe(fetch_live=fetch_live, trend_limit=12), []
    except Exception as exc:
        return {
            "generated_at": _now_iso(),
            "source": "fallback",
            "stale": True,
            "liked_tokens": [
                {"symbol": symbol, "name": symbol, "priority": "core"}
                for symbol in ("ETH", "BTC", "SOL", "LINK", "AAVE", "UNI", "ONDO", "ZEC")
            ],
            "trending_tokens": [],
            "combined_tokens": [],
            "venue_matrix": [],
            "source_docs": [],
        }, [f"market_universe:{_safe_error(exc)}"]


def _call_continuous_plan(fetch_live: bool) -> tuple[dict[str, Any], list[str]]:
    try:
        from lib.autonomy.continuous_intelligence import build_continuous_intelligence_plan

        return build_continuous_intelligence_plan(fetch_live=fetch_live), []
    except Exception as exc:
        return {
            "mode": "read_only_task_planning",
            "totals": {"tasks": 0, "blocked": 0, "lanes": {}, "runtimes": {}},
            "tasks": [],
            "next_dispatch": [],
        }, [f"continuous_intelligence:{_safe_error(exc)}"]


def _call_shadow_report(
    *,
    market_universe: dict[str, Any],
    fetch_live: bool,
) -> tuple[dict[str, Any], list[str]]:
    try:
        from lib.trading.shadow_controller import build_shadow_trading_report

        return build_shadow_trading_report(
            market_universe=market_universe,
            fetch_live=fetch_live,
        ), []
    except Exception as exc:
        return {
            "mode": "paper_shadow",
            "live_execution_enabled": False,
            "candidates": [],
            "watchlist": [],
            "promotion_gates": [],
        }, [f"shadow_controller:{_safe_error(exc)}"]


def _symbols_from_market(market: dict[str, Any]) -> list[str]:
    rows = market.get("liked_tokens") or []
    symbols = [
        str(row.get("symbol") or "").upper()
        for row in rows
        if isinstance(row, dict) and row.get("symbol")
    ]
    return _dedupe([*symbols, "ETH", "BTC", "SOL", "LINK", "AAVE", "UNI", "ONDO", "ZEC"])


def _dedupe(symbols: list[str] | tuple[str, ...]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for symbol in symbols:
        value = str(symbol or "").strip().upper()
        if not value or value in seen:
            continue
        seen.add(value)
        out.append(value)
    return out


def _source_row(
    *,
    id: str,
    title: str,
    status: str,
    priority: str,
    current_surface: str,
    next_step: str,
    docs: tuple[str, ...],
    cadence: str,
) -> dict[str, Any]:
    return {
        "id": id,
        "title": title,
        "status": status,
        "priority": priority,
        "current_surface": current_surface,
        "next_step": next_step,
        "cadence": cadence,
        "source_docs": list(docs),
    }


def _data_source_roadmap() -> list[dict[str, Any]]:
    def status(path: str, *, ready: str = "wired", missing: str = "gap") -> str:
        return ready if _exists(path) else missing

    return [
        _source_row(
            id="coingecko_market_universe",
            title="CoinGecko market universe and trending tokens",
            status=status("lib/trading/strategy_lab.py"),
            priority="P1",
            current_surface="lib.trading.strategy_lab.build_market_universe",
            next_step="Keep as the fast crypto price/trending seed, but cache all pulls and compare to DeFiLlama liquidity before ranking.",
            docs=("https://docs.coingecko.com/",),
            cadence="5m_to_15m_cache_first",
        ),
        _source_row(
            id="defillama_defi_fundamentals",
            title="DeFiLlama TVL, fees, stablecoins, DEX volume, yields, and open interest",
            status=status("lib/sources/defillama.py", ready="source_ready"),
            priority="P1",
            current_surface="lib.sources.defillama.DeFiLlamaSource",
            next_step="Promote TVL, revenue, stablecoin float, DEX volume, and open-interest deltas into the strategy feature matrix.",
            docs=("https://api-docs.defillama.com/",),
            cadence="15m_to_1h_cache_first",
        ),
        _source_row(
            id="fred_macro_regime",
            title="FRED macro regime series",
            status=status(
                "plugins/claw-sapphire/tools/internal/macro_data.py", ready="partial_wired"
            ),
            priority="P1",
            current_surface="plugins/claw-sapphire/tools/internal/macro_data.py",
            next_step="Graduate DGS2, DGS10, T10YIE, DFF, M2SL, CPIAUCSL, VIXCLS, and dollar/liquidity proxies into a point-in-time macro feature store.",
            docs=("https://fred.stlouisfed.org/docs/api/fred/",),
            cadence="daily_after_release_or_hourly_for_market_series",
        ),
        _source_row(
            id="sec_edgar_events",
            title="SEC EDGAR filings and XBRL events",
            status=status("lib/sources/sec_edgar.py", ready="source_ready"),
            priority="P1",
            current_surface="lib.sources.sec_edgar.SECEdgarSource",
            next_step="Attach 8-K, 10-Q, 10-K, Form 4, and 13F event features to aligned equities and crypto-exposed public companies.",
            docs=("https://www.sec.gov/search-filings/edgar-application-programming-interfaces",),
            cadence="15m_cache_first_with_sec_user_agent",
        ),
        _source_row(
            id="cftc_cot_positioning",
            title="CFTC COT and official regulatory feeds",
            status=status("lib/macro/sources.py", ready="partial_wired"),
            priority="P2",
            current_surface="lib.macro.sources.CFTCRSSSource plus CFTC public reports",
            next_step="Add COT positioning deltas for FX, rates, equity index, energy, metals, and grains as slow-moving crowding features.",
            docs=("https://www.cftc.gov/MarketReports/index.htm",),
            cadence="weekly_after_friday_release",
        ),
        _source_row(
            id="cboe_vix_complex",
            title="Cboe VIX complex and volatility term structure",
            status=status("lib/cross_asset/sources.py", ready="proxy_wired"),
            priority="P1",
            current_surface="lib.cross_asset.sources uses VIX proxy symbols",
            next_step="Track VIX, VIX9D, VIX3M, VVIX, SKEW, and VX1/VX2 curve states where licensed data is available.",
            docs=("https://www.cboe.com/tradable-products/vix/",),
            cadence="market_hours_cache_first",
        ),
        _source_row(
            id="cme_fedwatch_rates_probabilities",
            title="CME FedWatch rate probability scenarios",
            status="research_gap",
            priority="P2",
            current_surface="not yet first-class in Sapphire",
            next_step="Ingest or reconstruct meeting-probability deltas from Fed Funds futures as a macro shock feature.",
            docs=(
                "https://www.cmegroup.com/tools-information/quikstrike/cme-fedwatch-tool-user-guide.html",
                "https://www.cmegroup.com/articles/2023/understanding-the-cme-group-fedwatch-tool-methodology.html",
            ),
            cadence="daily_plus_after_macro_events",
        ),
        _source_row(
            id="tradingview_readback_and_alerts",
            title="TradingView charts, alerts, Pine scripts, and TA readback",
            status=status("lib/trading/tradingview_orchestrator.py"),
            priority="P1",
            current_surface="TradingView TA machine, orchestrator, webhook receiver, Pine templates",
            next_step="Run readback-driven parity probes and replay alert payloads into paper only; mutation remains operator gated.",
            docs=(
                "https://www.tradingview.com/support/solutions/43000529348-how-to-configure-webhook-alerts/",
            ),
            cadence="hourly_readback_or_on_alert",
        ),
    ]


def _watch_universes(market: dict[str, Any]) -> list[dict[str, Any]]:
    liked = _symbols_from_market(market)
    return [
        {
            "id": "core_crypto_liquidity",
            "rank": 1,
            "priority": "P1",
            "title": "Core crypto liquidity and beta",
            "symbols": _dedupe([*liked[:10], "BTC", "ETH", "SOL", "BNB", "XRP", "LINK", "HYPE"]),
            "role": "primary risk-on crypto beta and venue-liquidity sensors",
            "signals": [
                "trend",
                "realized_volatility",
                "funding",
                "open_interest",
                "basis",
                "liquidity",
            ],
            "data_sources": ["CoinGecko", "TradingView", "Hyperliquid", "DeFiLlama"],
        },
        {
            "id": "eth_defi_rwa_agentic",
            "rank": 2,
            "priority": "P1",
            "title": "ETH, DeFi, RWA, and agentic payment rails",
            "symbols": [
                "ETH",
                "LINK",
                "AAVE",
                "UNI",
                "ONDO",
                "ENA",
                "ENS",
                "ARB",
                "OP",
                "COIN",
                "HOOD",
            ],
            "role": "productive-capital thesis, tokenization adoption, oracle demand, and ETH economic-zone breadth",
            "signals": [
                "tvl_growth",
                "fees_revenue",
                "stablecoin_float",
                "sec_events",
                "relative_strength",
            ],
            "data_sources": ["DeFiLlama", "SEC EDGAR", "CoinGecko", "TradingView"],
        },
        {
            "id": "privacy_resilience",
            "rank": 3,
            "priority": "P2",
            "title": "Privacy and resilience basket",
            "symbols": ["ZEC", "XMR", "BTC", "ETH", "TAO"],
            "role": "privacy, censorship-resistance, local inference, and non-consensus crisis hedges",
            "signals": [
                "relative_strength",
                "liquidity_shock",
                "social_volume",
                "regulatory_event",
                "drawdown_resilience",
            ],
            "data_sources": ["CoinGecko", "TradingView", "macro feeds", "official source ledger"],
        },
        {
            "id": "macro_risk_sensors",
            "rank": 4,
            "priority": "P1",
            "title": "Macro risk sensors",
            "symbols": [
                "SPY",
                "QQQ",
                "IWM",
                "RSP",
                "TLT",
                "IEF",
                "SHY",
                "TIP",
                "HYG",
                "LQD",
                "DXY",
                "USDJPY",
                "USDCNH",
                "GLD",
                "VIX",
                "VIX9D",
                "VIX3M",
                "VVIX",
                "MOVE",
            ],
            "role": "regime, volatility, dollar, rates, credit, and breadth context for every crypto signal",
            "signals": [
                "yield_curve",
                "real_rates",
                "credit_spread",
                "vol_term_structure",
                "breadth",
                "correlation_break",
            ],
            "data_sources": ["FRED", "Cboe", "CME", "CFTC", "cross_asset"],
        },
        {
            "id": "commodities_power_and_inflation",
            "rank": 5,
            "priority": "P2",
            "title": "Commodities, power, and inflation pressure",
            "symbols": [
                "GLD",
                "SLV",
                "CPER",
                "USO",
                "DBO",
                "UNG",
                "URA",
                "DBA",
                "WEAT",
                "CORN",
                "XLE",
                "XLU",
            ],
            "role": "inflation impulse, power-demand, geopolitical stress, and AI-infrastructure bottlenecks",
            "signals": [
                "trend",
                "carry",
                "term_structure",
                "inventory_proxy",
                "event_shock",
                "rates_sensitivity",
            ],
            "data_sources": ["FRED", "CFTC COT", "TradingView", "macro RSS"],
        },
        {
            "id": "ai_security_infrastructure_equities",
            "rank": 6,
            "priority": "P3",
            "title": "AI, cyber, compute, and market-infrastructure equities",
            "symbols": [
                "SMH",
                "SOXX",
                "XLK",
                "IGV",
                "CIBR",
                "GRID",
                "NVDA",
                "AMD",
                "MSFT",
                "GOOGL",
                "AMZN",
                "PLTR",
            ],
            "role": "equity expression of inference, cyber, power, and data-center capex cycles",
            "signals": [
                "earnings_event",
                "sec_filing_change",
                "relative_strength",
                "sector_breadth",
                "volatility",
            ],
            "data_sources": ["SEC EDGAR", "FRED", "TradingView", "source-quality"],
        },
    ]


def _signal_families() -> list[dict[str, Any]]:
    return [
        {
            "id": "multi_horizon_trend",
            "evidence_grade": "robust",
            "title": "Multi-horizon trend and time-series momentum",
            "hypothesis": "Assets with positive own-past returns across several horizons tend to keep trending before longer-horizon reversal risk appears.",
            "features": [
                "1m/3m/6m/12m return",
                "moving-average slope",
                "breakout distance",
                "vol-adjusted momentum",
            ],
            "local_surfaces": [
                "lib.analytics.strategies",
                "lib.analytics.walkforward",
                "lib.trading.tradingview_ta_machine",
            ],
            "validation_gate": "walk-forward plus CPCV, DSR >= 0, drawdown not worse than baseline",
            "source_docs": [
                "https://www.aqr.com/Insights/Research/Journal-Article/Time-Series-Momentum",
                "https://papers.ssrn.com/sol3/papers.cfm?abstract_id=3386035",
            ],
        },
        {
            "id": "cross_sectional_relative_strength",
            "evidence_grade": "robust",
            "title": "Cross-sectional relative strength",
            "hypothesis": "Within a liquid universe, the strongest assets should earn higher paper allocations than weaker peers only after liquidity and regime filters agree.",
            "features": [
                "ranked returns",
                "sector/basket residual return",
                "breadth",
                "dispersion",
            ],
            "local_surfaces": [
                "lib.analytics.correlation",
                "lib.cross_asset",
                "lib.trading.strategy_lab",
            ],
            "validation_gate": "out-of-sample basket ranking beats equal-weight and BTC/ETH/SOL baseline",
            "source_docs": [],
        },
        {
            "id": "volatility_and_risk_regime",
            "evidence_grade": "robust",
            "title": "Volatility, credit, dollar, and rate regime",
            "hypothesis": "Trend signals need smaller paper risk budgets when VIX/MOVE/credit/dollar stress and correlation spikes disagree with risk-on entries.",
            "features": [
                "VIX level",
                "VIX term structure",
                "MOVE",
                "DXY impulse",
                "2s10s curve",
                "HYG/TLT stress",
            ],
            "local_surfaces": [
                "lib.cross_asset.regime_detector",
                "lib.analytics.risk_engine",
                "lib.core.decision_engine",
            ],
            "validation_gate": "regime decomposition shows reduced drawdown without killing all positive expectancy",
            "source_docs": [
                "https://www.cboe.com/tradable-products/vix/",
                "https://fred.stlouisfed.org/docs/api/fred/",
            ],
        },
        {
            "id": "carry_funding_basis",
            "evidence_grade": "moderate",
            "title": "Funding, carry, basis, and crowding",
            "hypothesis": "Extreme perp funding, OI growth, and spot/perp basis can detect crowded continuation or reversal setups.",
            "features": [
                "perp funding",
                "open interest delta",
                "basis",
                "liquidations",
                "volume/OI divergence",
            ],
            "local_surfaces": [
                "services/hyperliquid",
                "lib.trading.funding_rate_carry_backtest",
                "lib.analytics.vpin",
            ],
            "validation_gate": "event-study by funding percentile and no lookahead in liquidation/OI snapshots",
            "source_docs": ["https://api-docs.defillama.com/"],
        },
        {
            "id": "onchain_defi_liquidity",
            "evidence_grade": "moderate",
            "title": "On-chain and DeFi liquidity impulse",
            "hypothesis": "Stablecoin supply, TVL, DEX volume, fees, yield, and bridge flows help separate durable crypto breadth from price-only false starts.",
            "features": [
                "stablecoin float",
                "chain TVL",
                "DEX volume",
                "fees/revenue",
                "bridge flow",
                "yield spread",
            ],
            "local_surfaces": [
                "lib.sources.defillama",
                "lib.chain.intelligence",
                "lib.onchain_aggregator",
            ],
            "validation_gate": "source-quality SNR and lag study before weighting any DeFi metric above trend",
            "source_docs": ["https://api-docs.defillama.com/"],
        },
        {
            "id": "official_event_intelligence",
            "evidence_grade": "moderate",
            "title": "Official event intelligence",
            "hypothesis": "SEC filings, CFTC/Fed/BLS/Treasury releases, and macro calendars explain regime shifts and reduce false attribution.",
            "features": [
                "8-K/Form 4",
                "FOMC event",
                "CFTC enforcement",
                "payroll/CPI release",
                "Treasury auction",
            ],
            "local_surfaces": [
                "lib.sources.sec_edgar",
                "lib.macro.sources",
                "services.macro_intel",
            ],
            "validation_gate": "event windows, placebo windows, and negative controls required",
            "source_docs": [
                "https://www.sec.gov/search-filings/edgar-application-programming-interfaces",
                "https://www.cftc.gov/MarketReports/index.htm",
                "https://www.cmegroup.com/tools-information/quikstrike/cme-fedwatch-tool-user-guide.html",
            ],
        },
        {
            "id": "llm_narrative_and_anomaly_overlay",
            "evidence_grade": "experimental",
            "title": "LLM narrative, anomaly, and contradiction overlay",
            "hypothesis": "Local inference should summarize sources, detect contradictions, and propose hypotheses; numeric promotion still requires deterministic validation.",
            "features": [
                "source summaries",
                "claim ledger",
                "narrative regime",
                "contradiction flags",
                "novel hypothesis proposals",
            ],
            "local_surfaces": [
                "inference proxy",
                "lib.autonomy.continuous_intelligence",
                "lib.research_notes",
            ],
            "validation_gate": "every LLM claim must cite a source and create a falsifiable numeric test",
            "source_docs": [],
        },
    ]


def _validation_stack() -> list[dict[str, Any]]:
    return [
        {
            "id": "walk_forward_oos",
            "title": "Walk-forward out-of-sample testing",
            "local_surface": "lib.analytics.walkforward",
            "why": "Prevents the system from trusting a parameter set that only worked in one historical slice.",
            "pass_gate": "rolling windows show stable OOS return, drawdown, trade count, and per-regime attribution",
        },
        {
            "id": "cpcv_embargo",
            "title": "Purged and embargoed CPCV",
            "local_surface": "lib.analytics.cpcv and lib.analytics.backtest_harness",
            "why": "Reduces leakage when labels overlap in time and when features have serial correlation.",
            "pass_gate": "all test paths are embargoed; candidate passes with transaction costs and slippage",
            "source_docs": [
                "https://skfolio.org/generated/skfolio.model_selection.CombinatorialPurgedCV.html"
            ],
        },
        {
            "id": "deflated_sharpe",
            "title": "Deflated Sharpe and multiple-testing control",
            "local_surface": "lib.analytics.deflated_sharpe and lib.analytics.walkforward.deflated_sharpe",
            "why": "Penalizes the system for trying many variants until one looks good by chance.",
            "pass_gate": "DSR is non-negative and better than the registered baseline after costs",
        },
        {
            "id": "source_quality_decay",
            "title": "Source-quality SNR, correlation, and decay",
            "local_surface": "lib.source_quality and services.source_quality",
            "why": "Forces the system to retire stale signals instead of accumulating decorative indicators.",
            "pass_gate": "source weight rises only after predictive SNR survives time-travel checks",
        },
        {
            "id": "paper_forward_incubation",
            "title": "Paper-forward incubation",
            "local_surface": "lib.trading.shadow_controller and paper trader artifacts",
            "why": "Keeps the final mile honest by observing real-time behavior without real orders.",
            "pass_gate": "paper signals get labels, attribution, and enough sample size before human promotion",
        },
    ]


def _autonomy_gaps(
    *,
    continuous_plan: dict[str, Any],
    shadow_report: dict[str, Any],
) -> list[dict[str, Any]]:
    totals = continuous_plan.get("totals") or {}
    shadow_candidates = shadow_report.get("candidates") or []
    return [
        {
            "id": "tools_exist_but_need_single_ranked_loop",
            "severity": "high",
            "finding": "Sapphire has many capable surfaces, but the operating loop needs one ranked quant flywheel that agents can lease, run, and close daily.",
            "evidence": {
                "continuous_tasks": int(totals.get("tasks") or 0),
                "continuous_blocked": int(totals.get("blocked") or 0),
            },
            "next_step": "Use this endpoint as the daily dispatch source for quant research, validation, and source-wiring lanes.",
        },
        {
            "id": "paper_labels_are_the_bottleneck",
            "severity": "high",
            "finding": "Strategy intelligence cannot improve autonomously unless every paper signal gets outcome labels and source attribution.",
            "evidence": {
                "shadow_candidates": len(shadow_candidates),
                "shadow_mode": shadow_report.get("mode"),
            },
            "next_step": "Prioritize the closed-trade-labeling and paper-forward incubation work orders.",
        },
        {
            "id": "macro_and_defi_features_need_first_class_weights",
            "severity": "medium",
            "finding": "FRED, DeFiLlama, SEC/CFTC, VIX, and FedWatch are the right source families, but only some are first-class numeric features today.",
            "evidence": {
                "source_ready_count": sum(
                    1
                    for row in _data_source_roadmap()
                    if row["status"] in {"wired", "source_ready", "partial_wired", "proxy_wired"}
                )
            },
            "next_step": "Promote the P1 data-source roadmap rows into deterministic feature snapshots before adding more model complexity.",
        },
        {
            "id": "tradingview_is_a_readback_and_alert_surface",
            "severity": "medium",
            "finding": "TradingView can drive chart intelligence and paper alert replay, but live mutation and execution must stay gated.",
            "evidence": {
                "live_execution_enabled": False,
                "telegram_sends_enabled": False,
            },
            "next_step": "Keep TradingView work orders in readback/replay mode and verify every mutation with readback before any operator-gated apply.",
        },
    ]


def _work_order(**kwargs: Any) -> QuantWorkOrder:
    work_order = QuantWorkOrder(**kwargs)
    if work_order.priority not in PRIORITY_ORDER:
        raise ValueError(f"unknown priority {work_order.priority!r}")
    if work_order.safe_mode not in SAFE_MODES:
        raise ValueError(f"unsafe mode {work_order.safe_mode!r}")
    return work_order


def _build_work_orders(watch_universes: list[dict[str, Any]]) -> list[QuantWorkOrder]:
    core_symbols = tuple(watch_universes[0]["symbols"][:8]) if watch_universes else ()
    macro_symbols = tuple(
        next(row for row in watch_universes if row["id"] == "macro_risk_sensors")["symbols"][:8]
    )
    return _sort_work_orders(
        [
            _work_order(
                id="build-feature-registry-p1-sources",
                lane="data_fusion",
                priority="P1",
                title="Build the first-class P1 quant feature registry",
                description="Unify CoinGecko, DeFiLlama, FRED, SEC EDGAR, CFTC, and VIX proxy fields into cache-first point-in-time feature snapshots.",
                target_runtime="mac-local",
                safe_mode="read_only",
                cadence="daily_until_ready",
                symbols=core_symbols,
                inputs=(
                    "market_universe",
                    "defillama",
                    "fred_macro",
                    "sec_edgar",
                    "cftc",
                    "cross_asset",
                ),
                local_surfaces=(
                    "lib.trading.strategy_lab",
                    "lib.sources.defillama",
                    "plugins/claw-sapphire/tools/internal/macro_data.py",
                    "lib.sources.sec_edgar",
                    "lib.cross_asset",
                ),
                expected_artifacts=("data/.autonomy/quant_features/*.json",),
                acceptance=(
                    "All fields include generated_at, source_id, stale_after, and point-in-time timestamp",
                    "No live orders, Telegram sends, wallet reads, or TradingView mutations",
                    "Missing keys degrade to explicit gaps instead of mock values",
                ),
                source_docs=SOURCE_DOCS[3:9],
            ),
            _work_order(
                id="run-oos-gauntlet-top-strategies",
                lane="validation",
                priority="P1",
                title="Run OOS gauntlet for top strategies and baskets",
                description="Evaluate RegimeAwareRSI, SapphireComposite, funding/carry, and cross-asset overlays with walk-forward, CPCV, DSR, costs, and regime decomposition.",
                target_runtime="github-actions",
                safe_mode="dry_run",
                cadence="on_feature_snapshot",
                symbols=core_symbols[:5],
                inputs=("feature_registry", "backtest_harness", "walkforward", "source_quality"),
                local_surfaces=(
                    "lib.analytics.backtest_harness",
                    "lib.analytics.walkforward",
                    "lib.analytics.deflated_sharpe",
                    "lib.source_quality",
                ),
                command=(
                    "python3 -m services.walkforward.build --symbols BTC-USD,ETH-USD,SOL-USD "
                    "--strategy RegimeAwareRSI --dry-run"
                ),
                expected_artifacts=("data/backtests/walkforward/<date>/*.json",),
                acceptance=(
                    "Walk-forward results include OOS windows and per-regime decomposition",
                    "CPCV/embargo parameters are recorded",
                    "Deflated Sharpe and drawdown gates are evaluated after fees/slippage",
                ),
                source_docs=SOURCE_DOCS[:3],
            ),
            _work_order(
                id="paper-forward-labeling-and-attribution",
                lane="paper_feedback",
                priority="P1",
                title="Close paper signal labels and attribution",
                description="Normalize every paper signal and shadow candidate into a labeled outcome table with source contribution, confidence, and realized paper PnL.",
                target_runtime="mac-local",
                safe_mode="paper",
                cadence="hourly",
                symbols=core_symbols,
                inputs=(
                    "paper_trading",
                    "shadow_controller",
                    "signal_logger",
                    "strategy_performance",
                ),
                local_surfaces=(
                    "data/paper_trading.jsonl",
                    "lib.trading.shadow_controller",
                    "lib.analytics.strategy_performance",
                ),
                expected_artifacts=("data/performance/signals.jsonl",),
                acceptance=(
                    "Outcome labels are paper/backtest only",
                    "Attribution names source families and rejects unverified LLM claims",
                    "No real broker write path is invoked",
                ),
            ),
            _work_order(
                id="tradingview-readback-alert-replay",
                lane="tradingview_autonomy",
                priority="P1",
                title="TradingView readback and alert replay parity",
                description="Use TradingView as the chart, Pine, and alert surface: read charts, export watchlists, replay alert JSON into paper, and verify readback.",
                target_runtime="mac-local",
                safe_mode="dry_run",
                cadence="hourly",
                symbols=core_symbols[:6],
                inputs=(
                    "tradingview_ta_machine",
                    "orchestrator_sessions",
                    "webhook_receiver",
                    "paper_routes",
                ),
                local_surfaces=(
                    "lib.trading.tradingview_ta_machine",
                    "lib.trading.tradingview_orchestrator",
                    "services/webhook/src/receiver.py",
                ),
                expected_artifacts=("data/.autonomy/tradingview_replay/*.json",),
                acceptance=(
                    "Alert payloads parse with HMAC success and failure fixtures",
                    "TradingView mutation remains disabled unless a separate operator-gated apply is requested",
                    "Replay routes end at paper/shadow candidates only",
                ),
                source_docs=(SOURCE_DOCS[-1],),
            ),
            _work_order(
                id="macro-volatility-regime-board",
                lane="regime_intelligence",
                priority="P2",
                title="Build macro volatility regime board",
                description="Track rates, dollar, credit, VIX complex, FedWatch scenario deltas, and CFTC positioning as regime context for every crypto signal.",
                target_runtime="mac-local",
                safe_mode="read_only",
                cadence="daily_plus_event_refresh",
                symbols=macro_symbols,
                inputs=("fred_macro", "cboe_vix", "cme_fedwatch", "cftc_cot", "cross_asset"),
                local_surfaces=(
                    "lib.macro.sources",
                    "plugins/claw-sapphire/tools/internal/macro_data.py",
                    "lib.cross_asset",
                ),
                expected_artifacts=("data/.autonomy/macro_regime/*.json",),
                acceptance=(
                    "All macro rows carry source URL and release timestamp",
                    "Slow macro features are not upsampled into fake high-frequency signals",
                    "Regime output is advisory until validated by walk-forward decomposition",
                ),
                source_docs=SOURCE_DOCS[3:10],
            ),
            _work_order(
                id="llm-hypothesis-factory-with-falsification",
                lane="inference_research",
                priority="P2",
                title="Local LLM hypothesis factory with falsification contract",
                description="Use Windows/Mac inference to propose new signal hypotheses, but require every hypothesis to include data requirements, invalidation, and a deterministic backtest command.",
                target_runtime="windows-gpu",
                safe_mode="read_only",
                cadence="daily",
                symbols=core_symbols,
                inputs=("feature_registry", "source_docs", "walkforward_results", "market_notes"),
                local_surfaces=(
                    "inference_proxy",
                    "lib.autonomy.continuous_intelligence",
                    "lib.research_notes",
                ),
                expected_artifacts=("data/.autonomy/quant_hypotheses/*.json",),
                acceptance=(
                    "Every hypothesis is JSON with source_url, feature_set, expected_edge, overfit_risk, and test_command",
                    "No generated patch or parameter promotion happens from this lane alone",
                    "Claims without sources are marked unsupported",
                ),
            ),
            _work_order(
                id="portfolio-risk-budget-simulation",
                lane="portfolio_risk",
                priority="P2",
                title="Simulate risk budgets before any strategy promotion",
                description="Compare equal-weight, volatility-targeted, shrinkage covariance, and HRP-style paper risk budgets across the watch universes.",
                target_runtime="mac-local",
                safe_mode="dry_run",
                cadence="weekly",
                symbols=tuple(_dedupe([*core_symbols, *macro_symbols[:4]])),
                inputs=("walkforward_results", "correlation_matrix", "risk_engine"),
                local_surfaces=(
                    "lib.analytics.risk_engine",
                    "lib.cross_asset.correlation_matrix",
                    "lib.analytics.walkforward",
                ),
                expected_artifacts=("data/.autonomy/portfolio_risk/*.json",),
                acceptance=(
                    "Output is a simulation only and cannot resize live positions",
                    "Risk budgets include max drawdown, turnover, concentration, and stale-data kill-switch behavior",
                    "Promotion requires a human-reviewed PR",
                ),
            ),
        ]
    )


def _sort_work_orders(work_orders: list[QuantWorkOrder]) -> list[QuantWorkOrder]:
    return sorted(work_orders, key=lambda item: (PRIORITY_ORDER[item.priority], item.lane, item.id))


def _totals(
    *,
    watch_universes: list[dict[str, Any]],
    signal_families: list[dict[str, Any]],
    source_rows: list[dict[str, Any]],
    work_orders: list[QuantWorkOrder],
) -> dict[str, Any]:
    priorities = Counter(item.priority for item in work_orders)
    lanes = Counter(item.lane for item in work_orders)
    source_statuses = Counter(row["status"] for row in source_rows)
    return {
        "watch_universes": len(watch_universes),
        "unique_watch_symbols": len(
            {symbol for universe in watch_universes for symbol in universe.get("symbols", [])}
        ),
        "signal_families": len(signal_families),
        "data_sources": len(source_rows),
        "source_statuses": dict(sorted(source_statuses.items())),
        "work_orders": len(work_orders),
        "lanes": dict(sorted(lanes.items())),
        "priorities": dict(sorted(priorities.items())),
    }


def _source_docs(
    *,
    market: dict[str, Any],
    continuous_plan: dict[str, Any],
    work_orders: list[QuantWorkOrder],
) -> list[str]:
    docs: list[str] = list(SOURCE_DOCS)
    docs.extend(str(doc) for doc in market.get("source_docs") or [])
    docs.extend(str(doc) for doc in continuous_plan.get("source_docs") or [])
    for order in work_orders:
        docs.extend(order.source_docs)
    return list(dict.fromkeys(doc for doc in docs if doc))


def build_quant_intelligence_flywheel(*, fetch_live: bool = False) -> dict[str, Any]:
    """Build a read-only quant autonomy flywheel payload."""

    market, market_errors = _call_market_universe(fetch_live)
    continuous_plan, plan_errors = _call_continuous_plan(fetch_live)
    shadow_report, shadow_errors = _call_shadow_report(
        market_universe=market,
        fetch_live=fetch_live,
    )

    watch_universes = _watch_universes(market)
    signal_families = _signal_families()
    source_rows = _data_source_roadmap()
    validation_stack = _validation_stack()
    work_orders = _build_work_orders(watch_universes)
    p1_orders = [order for order in work_orders if order.priority == "P1"]

    input_errors = [*market_errors, *plan_errors, *shadow_errors]
    source_ready = sum(
        1
        for row in source_rows
        if row["status"] in {"wired", "source_ready", "partial_wired", "proxy_wired"}
    )

    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": _now_iso(),
        "mode": "quant_intelligence_flywheel",
        "live_requested": bool(fetch_live),
        "execution_enabled": False,
        "live_trading_enabled": False,
        "telegram_sends_enabled": False,
        "writes_by_default": False,
        "safety": {
            "execution_enabled": False,
            "live_trading_enabled": False,
            "telegram_sends_enabled": False,
            "writes_by_default": False,
            "allowed_modes": sorted(SAFE_MODES),
            "guards": [
                "read_only_quant_planning",
                "paper_forward_only",
                "no_order_signing",
                "no_order_submission",
                "no_tradingview_mutation",
                "no_telegram_send",
                "human_promotion_gate_required",
            ],
        },
        "current_state": {
            "market_source": market.get("source"),
            "market_stale": bool(market.get("stale")),
            "liked_symbol_count": len(market.get("liked_tokens") or []),
            "continuous_tasks": int((continuous_plan.get("totals") or {}).get("tasks") or 0),
            "continuous_blocked": int((continuous_plan.get("totals") or {}).get("blocked") or 0),
            "shadow_mode": shadow_report.get("mode"),
            "shadow_candidates": len(shadow_report.get("candidates") or []),
            "source_ready_count": source_ready,
            "source_gap_count": len(source_rows) - source_ready,
            "errors": input_errors,
        },
        "watch_universes": watch_universes,
        "signal_families": signal_families,
        "validation_stack": validation_stack,
        "data_source_roadmap": source_rows,
        "autonomy_gaps": _autonomy_gaps(
            continuous_plan=continuous_plan,
            shadow_report=shadow_report,
        ),
        "work_orders": [order.to_dict() for order in work_orders],
        "dispatch_now": [order.to_dict() for order in p1_orders[:5]],
        "operating_loop": [
            "observe cache-first market, macro, DeFi, event, TradingView, and paper state",
            "orient into watch universes, signal families, source-quality scores, and regime context",
            "decide by running CPCV, walk-forward, DSR, source-quality, and paper-forward gates",
            "act only by writing reviewable artifacts and opening PRs for human-promoted changes",
            "learn from labeled paper outcomes and retire decayed sources or overfit strategies",
        ],
        "totals": _totals(
            watch_universes=watch_universes,
            signal_families=signal_families,
            source_rows=source_rows,
            work_orders=work_orders,
        ),
        "source_docs": _source_docs(
            market=market,
            continuous_plan=continuous_plan,
            work_orders=work_orders,
        ),
    }


def cli(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--live",
        action="store_true",
        help="Allow live read-only source fetches where the underlying source supports it.",
    )
    parser.add_argument("--pretty", action="store_true")
    args = parser.parse_args(argv)

    payload = build_quant_intelligence_flywheel(fetch_live=bool(args.live))
    print(json.dumps(payload, indent=2 if args.pretty else None, sort_keys=bool(args.pretty)))
    return 0


if __name__ == "__main__":
    raise SystemExit(cli())


__all__ = ["build_quant_intelligence_flywheel", "cli", "QuantWorkOrder"]
