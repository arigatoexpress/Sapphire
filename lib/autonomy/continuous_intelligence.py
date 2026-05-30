"""Read-only continuous-intelligence task planner.

This module gives Sapphire a concrete contract for "always working" without
turning on live execution. It composes the existing market universe, sovereign
thesis, strategy-performance, and backtest artifacts into claimable tasks for
Mac, Windows GPU inference, GitHub Actions, and human review.
"""

from __future__ import annotations

import argparse
import json
import os
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SYMBOLS = ("ETH", "BTC", "ZEC", "XMR", "AAVE", "LINK", "UNI", "ENS")
DEFAULT_BACKTEST_SYMBOLS = ("ETH-USD", "BTC-USD", "ZEC-USD")
TOKENIZATION_AGENTIC_SYMBOLS = ("ETH", "LINK", "ONDO", "COIN", "JPM", "AAVE", "UNI", "TAO")
TOKENIZATION_AGENTIC_SOURCE_DOCS = (
    "https://docs.cdp.coinbase.com/x402/docs/welcome",
    "https://docs.base.org/ai-agents/payments/pay-for-services-with-x402",
    "https://docs.base.org/ai-agents/payments/accepting-payments",
    "https://www.base.org/agents",
    "https://chain.link/smartdata",
    "https://www.dtcc.com/-/media/Files/Downloads/DTCC-Connection/Smart_NAV-Report.pdf",
    "https://www.jpmorgan.com/kinexys/digital-assets/tokenized-collateral-network",
    "https://www.franklintempleton.com/about-us/our-teams/specialist-investment-managers/digital-assets/digital-assets-technology",
    "https://securitize.io/learn/press/blackrock-launches-first-tokenized-fund-buidl-on-the-ethereum-network",
    "https://docs.ondo.finance/ondo-global-markets",
)
SAFE_MODES = {"read_only", "paper", "dry_run"}
PRIORITY_ORDER = {"P1": 0, "P2": 1, "P3": 2}


@dataclass(frozen=True)
class IntelligenceTask:
    """A claimable, non-executing unit of continuous intelligence work."""

    id: str
    lane: str
    priority: str
    title: str
    description: str
    target_runtime: str
    model_tier: str
    cadence: str
    safe_mode: str
    symbols: tuple[str, ...] = ()
    inputs: tuple[str, ...] = ()
    command: str | None = None
    python_api: str | None = None
    prompt: str | None = None
    ooda_packet: dict[str, Any] | None = None
    expected_artifacts: tuple[str, ...] = ()
    acceptance: tuple[str, ...] = ()
    blocked_by: tuple[str, ...] = ()
    source_docs: tuple[str, ...] = ()
    notes: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        row = asdict(self)
        for key in (
            "symbols",
            "inputs",
            "expected_artifacts",
            "acceptance",
            "blocked_by",
            "source_docs",
            "notes",
        ):
            row[key] = list(row[key])
        return {key: value for key, value in row.items() if value not in (None, [], {})}


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _safe_error(exc: Exception) -> str:
    return f"{type(exc).__name__}: {exc}"


def _call_market_universe(fetch_live: bool, trend_limit: int) -> tuple[dict[str, Any], list[str]]:
    try:
        from lib.trading.strategy_lab import build_market_universe

        try:
            return build_market_universe(fetch_live=fetch_live, trend_limit=trend_limit), []
        except TypeError:
            return build_market_universe(fetch_live=fetch_live), []
    except Exception as exc:
        return {
            "generated_at": _now_iso(),
            "source": "fallback",
            "stale": True,
            "liked_tokens": [
                {"symbol": symbol, "yfinance_symbol": f"{symbol}-USD"} for symbol in DEFAULT_SYMBOLS
            ],
            "trending_tokens": [],
            "combined_tokens": [],
            "venue_matrix": [
                {"symbol": symbol, "backtest": f"{symbol}-USD"} for symbol in DEFAULT_SYMBOLS
            ],
            "source_docs": [],
        }, [f"market_universe:{_safe_error(exc)}"]


def _call_sovereign_thesis() -> tuple[dict[str, Any], list[str]]:
    try:
        from lib.intel.sovereign_thesis import build_sovereign_thesis_report

        return build_sovereign_thesis_report(), []
    except Exception as exc:
        return {
            "generated_at": _now_iso(),
            "mode": "research_intel_only",
            "assets": [{"symbol": symbol, "fit": "watch"} for symbol in DEFAULT_SYMBOLS],
            "lenses": [],
            "ops_queue": [],
            "source_requirements": [],
            "source_docs": [],
            "totals": {"assets": len(DEFAULT_SYMBOLS), "lenses": 0},
            "evidence_summary": {"coverage_pct": 0.0, "wired_pct": 0.0, "needs_wiring": 0},
        }, [f"sovereign_thesis:{_safe_error(exc)}"]


def _call_strategy_performance() -> tuple[dict[str, Any], list[str]]:
    try:
        from lib.analytics.strategy_performance import report

        return report(), []
    except Exception as exc:
        return {
            "generated_at": _now_iso(),
            "trade_count": 0,
            "strategies": [],
            "by_symbol": {},
            "overall": {"trades": 0, "win_rate": None, "total_pnl_usd": 0.0},
            "note": "Strategy performance unavailable.",
        }, [f"strategy_performance:{_safe_error(exc)}"]


def _call_backtest_state() -> tuple[dict[str, Any], list[str]]:
    try:
        from lib.analytics.backtest_results import load_latest_best, load_latest_sweep, summary

        return {
            "summary": summary(),
            "latest_sweep": load_latest_sweep(),
            "latest_best": load_latest_best(),
        }, []
    except Exception as exc:
        return {
            "summary": {"have_results": False, "total_backtests": 0, "best_per_symbol": []},
            "latest_sweep": None,
            "latest_best": None,
        }, [f"backtest_results:{_safe_error(exc)}"]


def _runtime_targets() -> list[dict[str, Any]]:
    windows_url = os.getenv("WINDOWS_GPU_URL", "http://100.x.x.z:11434")
    return [
        {
            "id": "windows-gpu",
            "host": "desktop-hfck6u9",
            "tailscale_ip": "100.x.x.z",
            "url": windows_url,
            "role": "deep local inference, strategy mutation, confluence synthesis",
            "allowed_modes": ["read_only", "dry_run"],
            "forbidden_modes": ["order_signing", "order_submission", "telegram_send"],
        },
        {
            "id": "mac-local",
            "host": "macbook-pro-8",
            "role": "commander, source collection, artifact review, dashboard API",
            "allowed_modes": ["read_only", "dry_run", "paper"],
            "forbidden_modes": ["live_trading_without_human_confirm"],
        },
        {
            "id": "github-actions",
            "role": "deterministic scheduled backtests and artifact comparisons",
            "allowed_modes": ["read_only", "dry_run"],
            "forbidden_modes": ["secrets_printing", "external_mutation"],
        },
        {
            "id": "human-review",
            "role": "promotion gate for strategy or thesis changes",
            "allowed_modes": ["approve", "reject", "request_more_evidence"],
            "forbidden_modes": ["implicit_approval"],
        },
    ]


def _liked_symbols(market: dict[str, Any], limit: int = 8) -> list[str]:
    rows = market.get("liked_tokens") or []
    symbols = [str(row.get("symbol") or "").upper() for row in rows if row.get("symbol")]
    return (symbols or list(DEFAULT_SYMBOLS))[:limit]


def _backtest_symbols(market: dict[str, Any], limit: int = 5) -> list[str]:
    rows = market.get("venue_matrix") or market.get("liked_tokens") or []
    symbols: list[str] = []
    for row in rows:
        symbol = row.get("backtest") or row.get("yfinance_symbol")
        if symbol:
            symbols.append(str(symbol))
    if not symbols:
        symbols = list(DEFAULT_BACKTEST_SYMBOLS)
    return list(dict.fromkeys(symbols))[:limit]


def _top_thesis_assets(thesis: dict[str, Any], limit: int = 8) -> list[str]:
    rows = thesis.get("assets") or []
    symbols = [str(row.get("symbol") or "").upper() for row in rows if row.get("symbol")]
    return (symbols or list(DEFAULT_SYMBOLS))[:limit]


def _source_docs(market: dict[str, Any], thesis: dict[str, Any]) -> list[str]:
    docs: list[str] = []
    docs.extend(str(doc) for doc in market.get("source_docs") or [])
    docs.extend(str(doc) for doc in thesis.get("source_docs") or [])
    docs.extend(TOKENIZATION_AGENTIC_SOURCE_DOCS)
    return list(dict.fromkeys(docs))


def _has_cpcv_csv(symbol: str) -> bool:
    sym_dir = ROOT / "data" / "backtests" / symbol / "1d"
    return sym_dir.exists() and any(sym_dir.glob("*.csv"))


def _cpcv_gap(backtest_symbols: list[str]) -> tuple[bool, list[str]]:
    missing = [symbol for symbol in backtest_symbols[:3] if not _has_cpcv_csv(symbol)]
    return bool(missing), missing


def _task(**kwargs: Any) -> IntelligenceTask:
    task = IntelligenceTask(**kwargs)
    if task.safe_mode not in SAFE_MODES:
        raise ValueError(f"unsafe task mode {task.safe_mode!r} for {task.id}")
    if task.priority not in PRIORITY_ORDER:
        raise ValueError(f"unknown priority {task.priority!r} for {task.id}")
    return task


def _build_tasks(
    *,
    market: dict[str, Any],
    thesis: dict[str, Any],
    performance: dict[str, Any],
    backtests: dict[str, Any],
) -> list[IntelligenceTask]:
    liked = _liked_symbols(market)
    thesis_symbols = _top_thesis_assets(thesis)
    backtest_symbols = _backtest_symbols(market)
    docs = _source_docs(market, thesis)
    missing_cpcv, missing_symbols = _cpcv_gap(backtest_symbols)
    trade_count = int(performance.get("trade_count") or 0)
    backtest_summary = backtests.get("summary") or {}
    have_backtests = bool(backtest_summary.get("have_results"))

    cpcv_symbol_arg = ",".join(backtest_symbols[:3])
    cpcv_blockers = ("stage_cpcv_ohlcv:" + ",".join(missing_symbols),) if missing_cpcv else ()
    tasks = [
        _task(
            id="stage-cpcv-ohlcv-preferred-crypto",
            lane="data_staging",
            priority="P1" if missing_cpcv else "P2",
            title="Stage deterministic OHLCV for preferred crypto CPCV",
            description=(
                "Materialize daily OHLCV CSVs under data/backtests/<symbol>/1d/ "
                "for the preferred thesis symbols so the CPCV harness can run "
                "without live yfinance drift."
            ),
            target_runtime="mac-local",
            model_tier="none",
            cadence="daily_until_ready",
            safe_mode="read_only",
            symbols=tuple(backtest_symbols[:5]),
            inputs=("market_universe", "backtest_harness"),
            expected_artifacts=(
                "data/backtests/ETH-USD/1d/*.csv",
                "data/backtests/BTC-USD/1d/*.csv",
                "data/backtests/ZEC-USD/1d/*.csv",
            ),
            acceptance=(
                "CSV rows cover 2025-04-01 through 2026-04-25",
                "No live order, wallet, or Telegram path is invoked",
                "Harness missing-data warning clears for staged symbols",
            ),
            blocked_by=(),
        ),
        _task(
            id="run-cpcv-regime-aware-rsi",
            lane="strategy_backtest",
            priority="P1",
            title="Run CPCV gate for RegimeAwareRSI on preferred assets",
            description=(
                "Use the section 4.5 harness to test the current RegimeAwareRSI "
                "strategy across ETH-first preferred assets before proposing "
                "any promotion or mutation."
            ),
            target_runtime="github-actions",
            model_tier="none",
            cadence="on_data_arrival",
            safe_mode="dry_run",
            symbols=tuple(backtest_symbols[:3]),
            inputs=("backtest_harness", "strategy_lab", "sovereign_thesis"),
            command=(
                "python3 -m lib.analytics.backtest_harness "
                "--strategy lib.analytics.strategies:RegimeAwareRSI "
                "--start 2025-04-01 --end 2026-04-25 "
                f"--symbols {cpcv_symbol_arg}"
            ),
            expected_artifacts=("data/backtests/strategies/*.json",),
            acceptance=(
                "passes_section_4_5 is true or all failure reasons are recorded",
                "Deflated Sharpe, Sortino, drawdown, and trade count are present",
                "No strategy code changes are promoted from this task alone",
            ),
            blocked_by=cpcv_blockers,
        ),
        _task(
            id="run-cpcv-sapphire-composite",
            lane="strategy_backtest",
            priority="P1" if have_backtests else "P2",
            title="Run CPCV gate for SapphireComposite",
            description=(
                "Compare SapphireComposite against the ETH-centered thesis basket "
                "and record whether it actually improves the current leaderboard."
            ),
            target_runtime="github-actions",
            model_tier="none",
            cadence="weekly",
            safe_mode="dry_run",
            symbols=tuple(backtest_symbols[:3]),
            inputs=("backtest_harness", "backtest_results"),
            command=(
                "python3 -m lib.analytics.backtest_harness "
                "--strategy lib.analytics.strategies:SapphireComposite "
                "--start 2025-04-01 --end 2026-04-25 "
                f"--symbols {cpcv_symbol_arg}"
            ),
            expected_artifacts=("data/backtests/strategies/*.json",),
            acceptance=(
                "Results are compared against latest best_per_symbol artifact",
                "Any drawdown regression is flagged before review",
                "No live execution setting changes",
            ),
            blocked_by=cpcv_blockers,
        ),
        _task(
            id="regional-intel-ooda-readiness-review",
            lane="regional_ooda",
            priority="P1",
            title="Review regional-intel manifest v2 readiness",
            description=(
                "Use the regional-intel manifest v2 contract to review exported "
                "Region, IntelItem, and IntelSourceHealth coverage, provenance "
                "dropped-row counts, and safe export follow-ups."
            ),
            target_runtime="mac-local",
            model_tier="none",
            cadence="daily_on_export",
            safe_mode="read_only",
            inputs=(
                "data/foundry/regional-intel/manifest.json",
                "infra/gcp/regional_intel_mapping.json",
                "docs/foundry-ontology-schema.md",
            ),
            python_api="lib.foundry.readiness.build_foundry_schema_audit",
            ooda_packet={
                "observe": (
                    "Read local manifest metadata and row counts only; do not inspect "
                    "or copy source payload bodies."
                ),
                "orient": (
                    "Compare manifest schema_version=2, object type row/hash metadata, "
                    "source_health_summary, policy keys, and dropped-row count buckets."
                ),
                "decide": (
                    "Classify readiness as ready, absent, or schema_warning using the "
                    "paste-safe regional_manifest audit."
                ),
                "act": [
                    "Review /api/foundry/readiness for local manifest status.",
                    "Export fresh regional NDJSON from regional-intel-workbench if row/hash counts drift.",
                    "Open a PR for schema or mapping metadata changes before any GCP or Foundry write.",
                ],
            },
            expected_artifacts=(
                "local /api/foundry/readiness regional_manifest readout",
                "optional docs/research/regional-intel-readiness-*.md",
            ),
            acceptance=(
                "Act items are review/export recommendations only",
                "No GCP, Foundry, workflow dispatch, Telegram, or trading write is invoked",
                "Dropped-row reporting includes counts by reason/object/kind but no source payloads",
            ),
            source_docs=(
                "docs/foundry-ontology-schema.md",
                "docs/gcp-data-engineering.md",
                "infra/gcp/regional_intel_mapping.json",
            ),
        ),
        _task(
            id="gemini-ooda-synthesis-dry-run",
            lane="ai_complement",
            priority="P2",
            title="Bounded Gemini OODA synthesis on the latest thesis snapshot",
            description=(
                "Use the Sapphire-bounded gemini_ooda plugin tool to draft an "
                "OODA packet from the current thesis + market state. Default mode "
                "is dry-run, which produces a deterministic mock packet without "
                "contacting Gemini; live mode requires SAPPHIRE_GEMINI_LIVE=1, the "
                "sensitivity gate, and the per-hour + per-month token caps to be "
                "below the breaker."
            ),
            target_runtime="mac-local",
            model_tier="gemini-flash-bounded",
            cadence="daily_dry_run",
            safe_mode="dry_run",
            symbols=tuple(dict.fromkeys([*thesis_symbols[:4], *liked[:4]])),
            inputs=(
                "sovereign_thesis",
                "market_universe",
                "strategy_performance",
                "plugins/claw-sapphire/tools/gemini_ooda.py",
            ),
            command=(
                'echo \'{"action":"synthesize","topic":"Sapphire daily thesis OODA",'
                '"mode":"dry-run"}\' | python3 plugins/claw-sapphire/tools/gemini_ooda.py'
            ),
            ooda_packet={
                "observe": (
                    "Read sovereign_thesis, market_universe, and strategy_performance "
                    "snapshots. Do not include secret values, customer PINs, mesh IPs, "
                    "or position sizes in the prompt; the sensitivity gate will block "
                    "them in live mode anyway."
                ),
                "orient": (
                    "Frame the synthesis as a paste-safe topic + context the OODA tool "
                    "can hand to Gemini Flash. Live mode is reserved for moments where "
                    "the local 4-tier mesh underperforms on structured output."
                ),
                "decide": (
                    "Stay in dry-run unless an operator has reviewed the per-call cap, "
                    "set SAPPHIRE_GEMINI_LIVE=1, and confirmed there is room in the "
                    "monthly token budget."
                ),
                "act": [
                    "Run the dry-run command above; cache the resulting JSON.",
                    "Diff the OODA packet against yesterday's; surface deltas only.",
                    "Open a PR if the runbook caps need to change before promoting "
                    "the tool to a higher cadence or skill.",
                ],
            },
            expected_artifacts=(
                "data/.autonomy/continuous_intelligence/gemini-ooda-*.json",
                "~/.cache/sapphire/gemini_ooda/<topic-hash>.json (live mode only)",
            ),
            acceptance=(
                "Dry-run mode produces a deterministic mock OODA packet without contacting Google",
                "Live mode is gated by SAPPHIRE_GEMINI_LIVE=1, the sensitivity classifier, and rate/cost caps",
                "No Telegram send, trading action, GCS/BigQuery write, or LaunchAgent retarget happens",
            ),
            source_docs=(
                "docs/ops/gemini-ooda-synthesizer-runbook.md",
                "docs/ops/gcp-vertex-ai-complement-plan.md",
                "docs/ops/google-benefits-utilization-plan.md",
            ),
            notes=(
                "Per-call output capped at MAX_OUTPUT_TOKENS_HARD=4096; per-hour cap MAX_CALLS_PER_HOUR=8;"
                " per-month cap MAX_TOKENS_PER_MONTH=500_000.",
            ),
        ),
        _task(
            id="windows-confluence-scan-preferred-assets",
            lane="confluence_scan",
            priority="P1",
            title="Windows confluence scan across thesis, market, and strategy state",
            description=(
                "Ask the Windows GPU to synthesize where thesis conviction, venue "
                "coverage, strategy performance, catalyst freshness, and invalidation "
                "watches agree or conflict."
            ),
            target_runtime="windows-gpu",
            model_tier="reason",
            cadence="hourly",
            safe_mode="read_only",
            symbols=tuple(dict.fromkeys([*liked[:6], *thesis_symbols[:6]])),
            inputs=(
                "market_universe",
                "sovereign_thesis",
                "strategy_performance",
                "backtest_results",
                "investment_news_queue",
            ),
            prompt=(
                "Return JSON only. Rank ETH-first preferred assets by confluence; "
                "include bullish thesis, bearish invalidation, data gaps, and the "
                "next testable strategy hypothesis. Do not suggest order placement."
            ),
            expected_artifacts=("data/.autonomy/continuous_intelligence/confluence-*.ndjson",),
            acceptance=(
                "Every claim cites an input surface or source doc",
                "Conflicts and invalidations are listed before recommendations",
                "No trade instruction or order draft is emitted",
            ),
            source_docs=tuple(docs[:8]),
        ),
        _task(
            id="windows-strategy-variant-hypotheses",
            lane="strategy_mutation",
            priority="P2",
            title="Generate strategy variants as hypotheses only",
            description=(
                "Use the Windows GPU for creative strategy research: threshold "
                "variants, confluence features, short-branch candidates, and ETH "
                "economic-zone specific filters. Output hypotheses, not patches."
            ),
            target_runtime="windows-gpu",
            model_tier="code",
            cadence="daily",
            safe_mode="read_only",
            symbols=tuple(backtest_symbols[:5]),
            inputs=("strategy_source", "backtest_harness", "sovereign_thesis"),
            prompt=(
                "Return hypothesis JSON with strategy_name, diff_summary, required_data, "
                "expected_edge, overfit_risk, and cpcv_command. Do not edit files."
            ),
            expected_artifacts=(
                "data/.autonomy/continuous_intelligence/strategy-hypotheses-*.json",
            ),
            acceptance=(
                "Each hypothesis includes a falsifiable backtest command",
                "Overfit and regime risks are explicit",
                "File edits require a separate PR task",
            ),
            blocked_by=cpcv_blockers,
        ),
        _task(
            id="eth-privacy-quantum-research-refresh",
            lane="thesis_research",
            priority="P1",
            title="Refresh ETH privacy, quantum-risk, and economic-zone research",
            description=(
                "Deepen the thesis ledger around Ethereum preference: privacy roadmap, "
                "account abstraction, post-quantum planning, L2 economics, MEV, and "
                "staking monetary policy."
            ),
            target_runtime="windows-gpu",
            model_tier="reason",
            cadence="daily",
            safe_mode="read_only",
            symbols=("ETH", "ZEC", "XMR", "AAVE", "UNI", "ENS", "ARB", "OP"),
            inputs=("sovereign_thesis", "source_requirements", "official_docs"),
            prompt=(
                "Research official/primary sources first. Return ledger-ready claims "
                "with source_url, claim, confidence, stale_after, invalidation, and "
                "which lens it supports."
            ),
            expected_artifacts=(
                "data/.autonomy/continuous_intelligence/eth-thesis-refresh-*.json",
            ),
            acceptance=(
                "Primary sources preferred over commentary",
                "Privacy and quantum claims include explicit uncertainty",
                "No financial advice or execution recommendation",
            ),
            source_docs=tuple(docs[:8]),
        ),
        _task(
            id="institutional-tokenization-agentic-payments-refresh",
            lane="thesis_research",
            priority="P1",
            title="Refresh institutional tokenization and agentic payment rails",
            description=(
                "Track the convergence of tokenized collateral, tokenized money-market "
                "funds, RWA oracles, Base/USDC agent wallets, and x402 pay-per-request "
                "APIs as a core ETH economic-zone and productive-capital thesis."
            ),
            target_runtime="windows-gpu",
            model_tier="reason",
            cadence="daily",
            safe_mode="read_only",
            symbols=TOKENIZATION_AGENTIC_SYMBOLS,
            inputs=(
                "sovereign_thesis",
                "x402_middleware",
                "source_requirements",
                "institutional_tokenization_sources",
                "agentic_payment_sources",
            ),
            prompt=(
                "Research official/primary sources first. Return ledger-ready JSON "
                "for institutional tokenization, agent wallets, x402, and tokenized "
                "collateral. For each claim include source_url, affected_symbol, "
                "thesis_lens, adoption_signal, custody_or_permissioning_risk, "
                "invalidation, confidence, and stale_after."
            ),
            expected_artifacts=(
                "data/.autonomy/continuous_intelligence/tokenization-agentic-payments-*.json",
            ),
            acceptance=(
                "Primary sources are used for every adoption claim",
                "Permissioned collateral rails are separated from self-custody/open-protocol rails",
                "x402 tasks remain dry-run unless a later human-approved payment PR enables testnet",
                "No financial advice or order recommendation is emitted",
            ),
            source_docs=TOKENIZATION_AGENTIC_SOURCE_DOCS,
        ),
        _task(
            id="investment-news-catalyst-scan",
            lane="thesis_research",
            priority="P2",
            title="Scan investment news for thesis catalysts and invalidations",
            description=(
                "Collect fresh public catalysts for crypto and aligned equities, then "
                "sort them into thesis-supporting, neutral, and invalidating evidence."
            ),
            target_runtime="mac-local",
            model_tier="balanced",
            cadence="daily",
            safe_mode="read_only",
            symbols=tuple(thesis_symbols[:8]),
            inputs=("investment_intel", "sovereign_thesis", "source_mesh"),
            expected_artifacts=("data/.autonomy/continuous_intelligence/news-catalysts-*.json",),
            acceptance=(
                "Every catalyst has source_url, published_at, and affected symbols",
                "Invalidations are kept even when they hurt the thesis",
                "No paywalled or secret content is copied into artifacts",
            ),
        ),
        _task(
            id="x402-agent-market-dry-run-plan",
            lane="ops_validation",
            priority="P2",
            title="Design dry-run x402 agent market smoke tests",
            description=(
                "Turn Sapphire's existing x402 middleware into a testable agent-market "
                "surface: paid research endpoints, paid inference endpoints, event-bus "
                "accounting, replay protection, and facilitator cutover gates."
            ),
            target_runtime="mac-local",
            model_tier="code",
            cadence="weekly",
            safe_mode="dry_run",
            symbols=("X402", "USDC", "BASE", "COIN"),
            inputs=("x402_middleware", "event_bus", "inference_proxy", "dashboard_api"),
            expected_artifacts=(
                "docs/research/x402-agent-market-smoke-*.md",
                "data/.autonomy/continuous_intelligence/x402-smoke-*.json",
            ),
            acceptance=(
                "X402_ENABLED stays disabled by default",
                "Mock verifier and Base Sepolia paths are separated from mainnet",
                "No wallet seed, private key, or payment credential is written to artifacts",
                "Event-bus payment.required/received/rejected traces are covered in dry-run",
            ),
            source_docs=TOKENIZATION_AGENTIC_SOURCE_DOCS[:4],
        ),
        _task(
            id="closed-trade-labeling-gap",
            lane="strategy_backtest",
            priority="P1" if trade_count == 0 else "P3",
            title="Close the strategy-performance feedback loop",
            description=(
                "Strategy intelligence improves only when signals become labeled "
                "outcomes. Verify closed trades or paper fills are normalized into "
                "strategy_performance before relying on live confluence scores."
            ),
            target_runtime="mac-local",
            model_tier="none",
            cadence="daily",
            safe_mode="read_only",
            symbols=tuple(liked[:6]),
            inputs=("strategy_performance", "paper_portfolio", "signal_history"),
            expected_artifacts=("data/performance/signals.jsonl", "data/signals/*.jsonl"),
            acceptance=(
                "trade_count increases or a data-gap reason is documented",
                "PnL labels are sourced from paper or historical backtest data only",
                "No real broker write path is touched",
            ),
        ),
        _task(
            id="tradingview-alert-parity-probe",
            lane="ops_validation",
            priority="P2",
            title="Validate TradingView alert schema parity in dry-run",
            description=(
                "Keep TradingView functionality deep by validating placeholder parsing, "
                "HMAC expectations, and paper-route payload shape against the strategy lab."
            ),
            target_runtime="mac-local",
            model_tier="none",
            cadence="weekly",
            safe_mode="dry_run",
            symbols=tuple(liked[:4]),
            inputs=("tradingview_capabilities", "webhook_receiver", "order_drafts"),
            expected_artifacts=(
                "data/.autonomy/continuous_intelligence/tradingview-parity-*.json",
            ),
            acceptance=(
                "Dry-run payloads parse without order submission",
                "HMAC failure and success cases are both covered",
                "Paper route remains execution_enabled=false",
            ),
        ),
        _task(
            id="promotion-gate-readout",
            lane="promotion_gate",
            priority="P1",
            title="Promote only evidence-backed strategy improvements",
            description=(
                "Summarize backtests, confluence scans, thesis changes, and risk deltas "
                "into a human-review packet before any strategy, scheduler, or executor "
                "behavior can change."
            ),
            target_runtime="human-review",
            model_tier="none",
            cadence="on_candidate_ready",
            safe_mode="read_only",
            symbols=tuple(liked[:6]),
            inputs=(
                "backtest_harness",
                "strategy_performance",
                "sovereign_thesis",
                "risk_engine",
                "audit_log",
            ),
            expected_artifacts=("docs/research/*strategy-promotion*.md",),
            acceptance=(
                "Human approval is required before code promotion",
                "Rollback notes and safety gates are included",
                "Live trading, order signing, and Telegram sends remain disabled",
            ),
        ),
    ]
    return _sort_tasks(tasks)


def _sort_tasks(tasks: list[IntelligenceTask]) -> list[IntelligenceTask]:
    return sorted(tasks, key=lambda task: (PRIORITY_ORDER[task.priority], task.lane, task.id))


def _input_summary(
    *,
    market: dict[str, Any],
    thesis: dict[str, Any],
    performance: dict[str, Any],
    backtests: dict[str, Any],
    input_errors: list[str],
) -> dict[str, Any]:
    backtest_summary = backtests.get("summary") or {}
    evidence_summary = thesis.get("evidence_summary") or {}
    return {
        "market_universe": {
            "source": market.get("source"),
            "stale": bool(market.get("stale")),
            "liked_symbols": _liked_symbols(market, limit=12),
            "trending_count": len(market.get("trending_tokens") or []),
            "venue_rows": len(market.get("venue_matrix") or []),
        },
        "sovereign_thesis": {
            "mode": thesis.get("mode"),
            "asset_count": (thesis.get("totals") or {}).get(
                "assets", len(thesis.get("assets") or [])
            ),
            "lens_count": (thesis.get("totals") or {}).get(
                "lenses", len(thesis.get("lenses") or [])
            ),
            "top_symbols": _top_thesis_assets(thesis, limit=8),
            "evidence_coverage_pct": evidence_summary.get("coverage_pct"),
            "evidence_wired_pct": evidence_summary.get("wired_pct"),
            "needs_wiring": evidence_summary.get("needs_wiring"),
        },
        "strategy_performance": {
            "trade_count": int(performance.get("trade_count") or 0),
            "strategies": list(performance.get("strategies") or [])[:10],
            "symbols": list((performance.get("by_symbol") or {}).keys())[:10],
            "note": performance.get("note"),
        },
        "backtests": {
            "have_results": bool(backtest_summary.get("have_results")),
            "total_backtests": int(backtest_summary.get("total_backtests") or 0),
            "computed_at": backtest_summary.get("computed_at"),
            "source_file": backtest_summary.get("source_file"),
        },
        "errors": input_errors,
    }


def _totals(tasks: list[IntelligenceTask]) -> dict[str, Any]:
    lanes = Counter(task.lane for task in tasks)
    priorities = Counter(task.priority for task in tasks)
    runtimes = Counter(task.target_runtime for task in tasks)
    blocked = sum(1 for task in tasks if task.blocked_by)
    return {
        "tasks": len(tasks),
        "blocked": blocked,
        "lanes": dict(sorted(lanes.items())),
        "priorities": dict(sorted(priorities.items())),
        "runtimes": dict(sorted(runtimes.items())),
    }


def build_continuous_intelligence_plan(
    *,
    fetch_live: bool = False,
    trend_limit: int = 12,
) -> dict[str, Any]:
    """Build a read-only plan for continuous strategy and thesis work."""
    market, market_errors = _call_market_universe(fetch_live, trend_limit)
    thesis, thesis_errors = _call_sovereign_thesis()
    performance, performance_errors = _call_strategy_performance()
    backtests, backtest_errors = _call_backtest_state()
    input_errors = [*market_errors, *thesis_errors, *performance_errors, *backtest_errors]
    tasks = _build_tasks(
        market=market,
        thesis=thesis,
        performance=performance,
        backtests=backtests,
    )
    p1_tasks = [task for task in tasks if task.priority == "P1"]
    next_dispatch = [task.to_dict() for task in p1_tasks[:6]]

    return {
        "generated_at": _now_iso(),
        "mode": "read_only_task_planning",
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
            "guards": [
                "read_only_task_generation",
                "dry_run_dispatch_only",
                "no_order_signing",
                "no_order_submission",
                "no_telegram_send",
                "human_promotion_gate_required",
            ],
        },
        "runtime_targets": _runtime_targets(),
        "totals": _totals(tasks),
        "inputs": _input_summary(
            market=market,
            thesis=thesis,
            performance=performance,
            backtests=backtests,
            input_errors=input_errors,
        ),
        "tasks": [task.to_dict() for task in tasks],
        "next_dispatch": next_dispatch,
        "operating_loop": [
            "observe market/thesis/performance/backtest inputs",
            "generate claimable read-only tasks",
            "dispatch dry-run work to Windows GPU, Mac local, or GitHub Actions",
            "store artifacts for review",
            "promote only through human-reviewed PR and safety gates",
        ],
        "source_docs": _source_docs(market, thesis),
    }


def cli(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--live", action="store_true", help="Allow live read-only market fetches where supported."
    )
    parser.add_argument("--trend-limit", type=int, default=12)
    parser.add_argument("--pretty", action="store_true")
    args = parser.parse_args(argv)

    payload = build_continuous_intelligence_plan(
        fetch_live=bool(args.live),
        trend_limit=max(1, args.trend_limit),
    )
    indent = 2 if args.pretty else None
    print(json.dumps(payload, indent=indent, sort_keys=bool(args.pretty)))
    return 0


if __name__ == "__main__":
    raise SystemExit(cli())


__all__ = ["build_continuous_intelligence_plan", "cli", "IntelligenceTask"]
