"""Read-only investment intelligence mesh for Sapphire.

This module turns Ari's thematic research packs, curated watchlists, public
equity/macro/energy sources, and existing crypto feeds into one normalized
report. It intentionally does not place orders, write live datasets, or expose
secrets; downstream callers decide when to materialize snapshots.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

try:
    import certifi

    _SSL_CTX = ssl.create_default_context(cafile=certifi.where())
except ImportError:
    _SSL_CTX = ssl.create_default_context()


ROOT = Path(__file__).resolve().parents[2]
RESEARCH_DIR = ROOT / "world_knowledge" / "research" / "kimi-p1-sun-drone"
STATIC_WATCHLIST_FILE = RESEARCH_DIR / "convergence_watchlist.json"
RESEARCH_ZIP_ENV = "SAPPHIRE_INVESTMENT_RESEARCH_ZIP"
SEC_USER_AGENT_ENV = "SAPPHIRE_SEC_USER_AGENT"
USER_AGENT = "sapphire-os/0.4 (+investment-intel; read-only)"
DEFAULT_TIMEOUT = 15

ASSET_CLASS_EQUITY = "equity"
ASSET_CLASS_ETF = "etf"
ASSET_CLASS_CRYPTO = "crypto"
ASSET_CLASS_PRIVATE = "private"


@dataclass(frozen=True)
class InvestmentAsset:
    symbol: str
    name: str
    asset_class: str
    risk_tier: str
    watch_level: str
    themes: tuple[str, ...]
    thesis: str
    source_note: str = "curated"

    def to_dict(self) -> dict[str, Any]:
        return {
            **asdict(self),
            "themes": list(self.themes),
        }


@dataclass(frozen=True)
class SourceConnector:
    id: str
    label: str
    category: str
    asset_classes: tuple[str, ...]
    docs_url: str
    endpoint_templates: tuple[str, ...]
    auth_envs: tuple[str, ...] = ()
    cadence: str = "on-demand"
    fields: tuple[str, ...] = ()
    mutation: bool = False
    local_module: str | None = None

    def to_dict(self) -> dict[str, Any]:
        configured = all(bool(os.environ.get(env)) for env in self.auth_envs)
        return {
            **asdict(self),
            "asset_classes": list(self.asset_classes),
            "endpoint_templates": list(self.endpoint_templates),
            "auth_envs": list(self.auth_envs),
            "fields": list(self.fields),
            "configured": configured if self.auth_envs else True,
            "status": "ready" if configured or not self.auth_envs else "needs_key",
            "mode": "read-only" if not self.mutation else "mutation-gated",
        }


@dataclass(frozen=True)
class SeriesSignal:
    id: str
    label: str
    provider: str
    provider_series: str
    themes: tuple[str, ...]
    assets: tuple[str, ...]
    cadence: str
    purpose: str
    auth_env: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            **asdict(self),
            "themes": list(self.themes),
            "assets": list(self.assets),
            "configured": bool(os.environ.get(self.auth_env)) if self.auth_env else True,
        }


@dataclass(frozen=True)
class SourceProbe:
    id: str
    label: str
    status: str
    detail: str
    latency_ms: float | None = None
    observed_count: int | None = None
    checked_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ResearchPack:
    available: bool
    source_label: str
    source_kind: str
    files: list[str] = field(default_factory=list)
    sections: list[dict[str, Any]] = field(default_factory=list)
    top_ideas: list[dict[str, Any]] = field(default_factory=list)
    csv_assets: list[dict[str, Any]] = field(default_factory=list)
    mindset_principles: list[str] = field(default_factory=list)
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


DEFAULT_ASSETS: tuple[InvestmentAsset, ...] = (
    InvestmentAsset(
        "NEE",
        "NextEra Energy",
        ASSET_CLASS_EQUITY,
        "conservative",
        "core",
        ("solar", "renewables", "ai-power", "utility"),
        "Renewable infrastructure compounder with AI-load-linked backlog.",
    ),
    InvestmentAsset(
        "BEP",
        "Brookfield Renewable",
        ASSET_CLASS_EQUITY,
        "conservative",
        "core",
        ("renewables", "hydro", "global-infrastructure", "ai-power"),
        "Diversified renewable infrastructure with global development pipeline.",
    ),
    InvestmentAsset(
        "HEI",
        "HEICO",
        ASSET_CLASS_EQUITY,
        "moderate",
        "core",
        ("aerospace", "defense", "picks-and-shovels"),
        "Aerospace component supplier with qualification-moat economics.",
    ),
    InvestmentAsset(
        "FSLR",
        "First Solar",
        ASSET_CLASS_EQUITY,
        "moderate",
        "satellite",
        ("solar", "domestic-manufacturing", "ai-power"),
        "U.S. thin-film solar manufacturer insulated from polysilicon overcapacity.",
    ),
    InvestmentAsset(
        "CEG",
        "Constellation Energy",
        ASSET_CLASS_EQUITY,
        "moderate",
        "core",
        ("nuclear", "ai-power", "grid"),
        "Nuclear baseload exposure for data-center power demand.",
    ),
    InvestmentAsset(
        "KTOS",
        "Kratos Defense",
        ASSET_CLASS_EQUITY,
        "moderate",
        "core",
        ("drones", "space", "hypersonics", "defense-ai"),
        "Defense-tech crossover across drones, space communications, and hypersonics.",
    ),
    InvestmentAsset(
        "PLTR",
        "Palantir",
        ASSET_CLASS_EQUITY,
        "moderate",
        "satellite",
        ("ai", "defense-ai", "ops-intelligence"),
        "AI command and decision layer for defense and enterprise operations.",
    ),
    InvestmentAsset(
        "RKLB",
        "Rocket Lab",
        ASSET_CLASS_EQUITY,
        "aggressive",
        "satellite",
        ("space", "launch", "defense-space"),
        "Public launch and space-systems proxy with key execution milestones.",
    ),
    InvestmentAsset(
        "ENPH",
        "Enphase Energy",
        ASSET_CLASS_EQUITY,
        "aggressive",
        "satellite",
        ("solar", "inverters", "storage"),
        "Solar inverter and storage platform with demand-cycle sensitivity.",
    ),
    InvestmentAsset(
        "JOBY",
        "Joby Aviation",
        ASSET_CLASS_EQUITY,
        "aggressive",
        "moonshot",
        ("evtol", "aviation", "platform-risk"),
        "eVTOL leader with certification and commercialization milestones.",
    ),
    InvestmentAsset(
        "BWXT",
        "BWX Technologies",
        ASSET_CLASS_EQUITY,
        "moderate",
        "core",
        ("nuclear", "defense", "space"),
        "Nuclear components and fuel exposure across defense and commercial markets.",
    ),
    InvestmentAsset(
        "CCJ",
        "Cameco",
        ASSET_CLASS_EQUITY,
        "moderate",
        "satellite",
        ("uranium", "nuclear", "ai-power"),
        "Uranium fuel-cycle exposure tied to nuclear power demand.",
    ),
    InvestmentAsset(
        "GEV",
        "GE Vernova",
        ASSET_CLASS_EQUITY,
        "moderate",
        "core",
        ("grid", "gas-power", "nuclear", "ai-power"),
        "Grid, gas turbine, and nuclear services exposure for power build-out.",
    ),
    InvestmentAsset(
        "FLNC",
        "Fluence Energy",
        ASSET_CLASS_EQUITY,
        "speculative",
        "moonshot",
        ("storage", "grid", "solar", "ai-power"),
        "Grid-scale storage convergence point for solar and data centers.",
    ),
    InvestmentAsset(
        "LNG",
        "Cheniere Energy",
        ASSET_CLASS_EQUITY,
        "moderate",
        "satellite",
        ("natural-gas", "lng", "ai-power"),
        "LNG export infrastructure with gas-demand leverage.",
    ),
    InvestmentAsset(
        "VST",
        "Vistra",
        ASSET_CLASS_EQUITY,
        "moderate",
        "core",
        ("nuclear", "gas-power", "ai-power"),
        "Independent power producer exposed to rising capacity values.",
    ),
    InvestmentAsset(
        "WMB",
        "Williams Companies",
        ASSET_CLASS_EQUITY,
        "conservative",
        "core",
        ("natural-gas", "midstream", "ai-power"),
        "Natural gas infrastructure and data-center power adjacency.",
    ),
    InvestmentAsset(
        "SHLD",
        "Global X Defense Tech ETF",
        ASSET_CLASS_ETF,
        "moderate",
        "hedge",
        ("defense", "drones", "international"),
        "Diversified defense-tech basket for reduced single-name risk.",
    ),
    InvestmentAsset(
        "BTC",
        "Bitcoin",
        ASSET_CLASS_CRYPTO,
        "core",
        "core",
        ("crypto", "macro-liquidity", "store-of-value"),
        "Primary crypto risk benchmark and liquidity regime anchor.",
        "existing crypto integration",
    ),
    InvestmentAsset(
        "ETH",
        "Ethereum",
        ASSET_CLASS_CRYPTO,
        "core",
        "core",
        ("crypto", "smart-contracts", "defi"),
        "Smart-contract and DeFi activity benchmark.",
        "existing crypto integration",
    ),
    InvestmentAsset(
        "SOL",
        "Solana",
        ASSET_CLASS_CRYPTO,
        "aggressive",
        "satellite",
        ("crypto", "high-beta", "consumer-chain"),
        "High-beta chain exposure for on-chain activity and market breadth.",
        "existing crypto integration",
    ),
    InvestmentAsset(
        "HYPE",
        "Hyperliquid",
        ASSET_CLASS_CRYPTO,
        "aggressive",
        "satellite",
        ("crypto", "perps", "venue-token"),
        "Venue-token lens for funded Hyperliquid market structure.",
        "existing crypto integration",
    ),
    InvestmentAsset(
        "LINK",
        "Chainlink",
        ASSET_CLASS_CRYPTO,
        "moderate",
        "satellite",
        ("crypto", "oracles", "infrastructure"),
        "Oracle infrastructure proxy across DeFi and tokenized assets.",
        "existing crypto integration",
    ),
    InvestmentAsset(
        "ONDO",
        "Ondo",
        ASSET_CLASS_CRYPTO,
        "aggressive",
        "moonshot",
        ("crypto", "rwa", "tokenized-treasuries"),
        "RWA tokenization watch item for macro/crypto convergence.",
        "existing crypto integration",
    ),
)


SOURCE_CONNECTORS: tuple[SourceConnector, ...] = (
    SourceConnector(
        id="kimi_research_pack",
        label="Kimi Investment Research Pack",
        category="research",
        asset_classes=(ASSET_CLASS_EQUITY, ASSET_CLASS_ETF, ASSET_CLASS_PRIVATE),
        docs_url="local://SAPPHIRE_INVESTMENT_RESEARCH_ZIP",
        endpoint_templates=(f"${RESEARCH_ZIP_ENV}", str(STATIC_WATCHLIST_FILE)),
        auth_envs=(),
        cadence="operator drop / on-demand",
        fields=("risk tiers", "theses", "catalysts", "CSV fundamentals", "mindset"),
        local_module="lib.intel.investment_intel.load_research_pack",
    ),
    SourceConnector(
        id="sec_submissions",
        label="SEC EDGAR Submissions",
        category="filings",
        asset_classes=(ASSET_CLASS_EQUITY, ASSET_CLASS_ETF),
        docs_url="https://www.sec.gov/search-filings/edgar-application-programming-interfaces",
        endpoint_templates=("https://data.sec.gov/submissions/CIK{cik10}.json",),
        cadence="real-time filing dissemination",
        fields=("CIK", "forms", "filing dates", "accession numbers", "ticker metadata"),
    ),
    SourceConnector(
        id="sec_companyfacts",
        label="SEC XBRL Company Facts",
        category="fundamentals",
        asset_classes=(ASSET_CLASS_EQUITY,),
        docs_url="https://www.sec.gov/search-filings/edgar-application-programming-interfaces",
        endpoint_templates=("https://data.sec.gov/api/xbrl/companyfacts/CIK{cik10}.json",),
        cadence="near-real-time after filings",
        fields=("revenue", "net income", "cash", "debt", "EPS", "shares"),
    ),
    SourceConnector(
        id="fred_macro",
        label="FRED Macro Series",
        category="macro",
        asset_classes=(ASSET_CLASS_EQUITY, ASSET_CLASS_ETF, ASSET_CLASS_CRYPTO),
        docs_url="https://fred.stlouisfed.org/docs/api/fred/v2/",
        endpoint_templates=("https://api.stlouisfed.org/fred/series/observations",),
        auth_envs=("FRED_API_KEY",),
        cadence="daily / release-dependent",
        fields=("rates", "inflation", "industrial production", "liquidity proxies"),
    ),
    SourceConnector(
        id="eia_energy",
        label="EIA Energy Data",
        category="energy",
        asset_classes=(ASSET_CLASS_EQUITY, ASSET_CLASS_ETF),
        docs_url="https://www.eia.gov/opendata/documentation.php",
        endpoint_templates=("https://api.eia.gov/v2/{route}/data",),
        auth_envs=("EIA_API_KEY",),
        cadence="daily / weekly / monthly",
        fields=("electricity demand", "natural gas", "generation mix", "retail prices"),
    ),
    SourceConnector(
        id="coingecko_market",
        label="CoinGecko Market + Trending",
        category="crypto-market",
        asset_classes=(ASSET_CLASS_CRYPTO,),
        docs_url="https://docs.coingecko.com/reference/endpoint-overview",
        endpoint_templates=(
            "https://api.coingecko.com/api/v3/simple/price",
            "https://api.coingecko.com/api/v3/search/trending",
        ),
        cadence="minutes / on-demand",
        fields=("spot prices", "market cap", "volume", "trending tokens", "token metadata"),
        local_module="lib.chain.sources.CoinGeckoClient",
    ),
    SourceConnector(
        id="hyperliquid_info",
        label="Hyperliquid Info Endpoint",
        category="crypto-venue",
        asset_classes=(ASSET_CLASS_CRYPTO,),
        docs_url="https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/api/info-endpoint",
        endpoint_templates=("POST https://api.hyperliquid.xyz/info",),
        cadence="near-real-time / on-demand",
        fields=("mark price", "funding", "open interest", "volume", "portfolio state"),
        local_module="lib.chain.sources.HyperliquidClient",
    ),
    SourceConnector(
        id="defillama_defi",
        label="DeFiLlama TVL + Stablecoins",
        category="crypto-defi",
        asset_classes=(ASSET_CLASS_CRYPTO,),
        docs_url="https://defillama.com/docs/api",
        endpoint_templates=(
            "https://api.llama.fi/protocols",
            "https://stablecoins.llama.fi/stablecoins",
        ),
        cadence="minutes / daily",
        fields=("TVL", "stablecoin supply", "DEX volume", "protocol category"),
        local_module="lib.chain.sources.DefiLlamaClient",
    ),
    SourceConnector(
        id="robinhood_crypto_readonly",
        label="Robinhood Crypto Read-Only",
        category="portfolio",
        asset_classes=(ASSET_CLASS_CRYPTO,),
        docs_url="https://docs.robinhood.com/crypto/trading/",
        endpoint_templates=(
            "https://trading.robinhood.com/api/v2/crypto/trading/holdings/",
            "https://trading.robinhood.com/api/v2/crypto/marketdata/best_bid_ask/",
        ),
        cadence="operator dashboard / on-demand",
        fields=("holdings", "best bid/ask", "orders", "cash", "buying power"),
        local_module="lib.portfolio.robinhood.RobinhoodReader",
    ),
    SourceConnector(
        id="tradingview_signal_research",
        label="TradingView Alert Research",
        category="signal-ingress",
        asset_classes=(ASSET_CLASS_EQUITY, ASSET_CLASS_ETF, ASSET_CLASS_CRYPTO),
        docs_url="https://www.tradingview.com/support/solutions/43000529348-how-to-configure-webhook-alerts/",
        endpoint_templates=("Sapphire webhook alert payloads",),
        cadence="alert-driven",
        fields=("symbol", "strategy", "direction", "timeframe", "confidence"),
        local_module="services.alpha.src.main",
    ),
)

SERIES_CATALOG: tuple[SeriesSignal, ...] = (
    SeriesSignal(
        id="fed_funds",
        label="Effective Federal Funds Rate",
        provider="FRED",
        provider_series="FEDFUNDS",
        themes=("macro", "rates", "growth-valuation"),
        assets=("FSLR", "RKLB", "JOBY", "BTC", "ETH", "SOL"),
        cadence="monthly",
        purpose="Discount-rate pressure on long-duration growth and crypto risk appetite.",
        auth_env="FRED_API_KEY",
    ),
    SeriesSignal(
        id="treasury_10y",
        label="10-Year Treasury Constant Maturity",
        provider="FRED",
        provider_series="DGS10",
        themes=("macro", "rates", "ai-power"),
        assets=("NEE", "BEP", "CEG", "FSLR", "VST", "WMB"),
        cadence="daily",
        purpose="Rates lens for utilities, infrastructure, and speculative duration risk.",
        auth_env="FRED_API_KEY",
    ),
    SeriesSignal(
        id="industrial_production",
        label="Industrial Production Index",
        provider="FRED",
        provider_series="INDPRO",
        themes=("macro", "industrial-demand", "defense"),
        assets=("GEV", "HEI", "KTOS", "BWXT", "WMB"),
        cadence="monthly",
        purpose="Cyclical demand backdrop for industrial and defense supply-chain names.",
        auth_env="FRED_API_KEY",
    ),
    SeriesSignal(
        id="electricity_retail_sales",
        label="Electricity Retail Sales",
        provider="EIA",
        provider_series="electricity/retail-sales",
        themes=("ai-power", "grid", "utility"),
        assets=("NEE", "CEG", "VST", "GEV", "WMB"),
        cadence="monthly",
        purpose="Track realized electricity demand across AI-power beneficiary lanes.",
        auth_env="EIA_API_KEY",
    ),
    SeriesSignal(
        id="electricity_operational_generation",
        label="Electricity Operational Generation",
        provider="EIA",
        provider_series="electricity/electricity-power-operational-data",
        themes=("ai-power", "nuclear", "natural-gas", "solar"),
        assets=("CEG", "VST", "GEV", "FSLR", "NEE", "LNG", "WMB"),
        cadence="daily/monthly",
        purpose="Generation mix signal for nuclear, gas, solar, and grid equipment theses.",
        auth_env="EIA_API_KEY",
    ),
    SeriesSignal(
        id="natural_gas_storage",
        label="Natural Gas Storage",
        provider="EIA",
        provider_series="natural-gas/stor/wkly",
        themes=("natural-gas", "ai-power"),
        assets=("LNG", "WMB", "GEV", "VST"),
        cadence="weekly",
        purpose="Gas supply pressure lens for LNG, midstream, and power generation.",
        auth_env="EIA_API_KEY",
    ),
    SeriesSignal(
        id="coingecko_trending",
        label="CoinGecko Trending Search",
        provider="CoinGecko",
        provider_series="search/trending",
        themes=("crypto", "attention", "breadth"),
        assets=("BTC", "ETH", "SOL", "HYPE", "LINK", "ONDO"),
        cadence="minutes",
        purpose="Attention and breadth pulse for the crypto watchlist.",
    ),
    SeriesSignal(
        id="hyperliquid_market_context",
        label="Hyperliquid Market Context",
        provider="Hyperliquid",
        provider_series="metaAndAssetCtxs",
        themes=("crypto", "perps", "venue-risk"),
        assets=("BTC", "ETH", "SOL", "HYPE", "LINK"),
        cadence="near-real-time",
        purpose="Funding, open-interest, and volume context for funded venue oversight.",
    ),
)


THEME_CONNECTORS: dict[str, tuple[str, ...]] = {
    "ai-power": ("fred_macro", "eia_energy"),
    "solar": ("eia_energy", "fred_macro"),
    "renewables": ("eia_energy", "fred_macro"),
    "nuclear": ("eia_energy", "fred_macro"),
    "uranium": ("eia_energy", "fred_macro"),
    "natural-gas": ("eia_energy", "fred_macro"),
    "grid": ("eia_energy", "fred_macro"),
    "storage": ("eia_energy", "fred_macro"),
    "drones": ("sec_submissions", "sec_companyfacts"),
    "space": ("sec_submissions", "sec_companyfacts"),
    "defense": ("sec_submissions", "sec_companyfacts"),
    "defense-ai": ("sec_submissions", "sec_companyfacts"),
    "crypto": ("coingecko_market", "hyperliquid_info", "defillama_defi"),
}

COINGECKO_IDS_BY_SYMBOL: dict[str, str] = {
    "BTC": "bitcoin",
    "ETH": "ethereum",
    "SOL": "solana",
    "HYPE": "hyperliquid",
    "LINK": "chainlink",
    "ONDO": "ondo-finance",
}


class SourceHTTPError(RuntimeError):
    """Raised by optional public-source client helpers."""


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _today_stamp() -> str:
    return datetime.now(UTC).date().isoformat()


def _run_stamp() -> str:
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")


def _request_json(
    url: str,
    *,
    headers: dict[str, str] | None = None,
    params: dict[str, Any] | None = None,
    timeout: int = DEFAULT_TIMEOUT,
) -> Any:
    if params:
        query = urllib.parse.urlencode({k: v for k, v in params.items() if v is not None})
        sep = "&" if urllib.parse.urlparse(url).query else "?"
        url = f"{url}{sep}{query}"
    req_headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}
    if headers:
        req_headers.update(headers)
    req = urllib.request.Request(url, headers=req_headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=_SSL_CTX) as response:
            return json.loads(response.read())
    except urllib.error.HTTPError as exc:
        raise SourceHTTPError(f"GET {url} -> HTTP {exc.code}: {exc.reason}") from exc
    except json.JSONDecodeError as exc:
        raise SourceHTTPError(f"GET {url} -> invalid JSON: {exc}") from exc
    except Exception as exc:
        raise SourceHTTPError(f"GET {url} -> {type(exc).__name__}: {exc}") from exc


class SecEdgarClient:
    """Small official SEC EDGAR JSON client for future scheduled collectors."""

    BASE = "https://data.sec.gov"

    def __init__(self, user_agent: str | None = None):
        self.user_agent = user_agent or os.environ.get(SEC_USER_AGENT_ENV) or USER_AGENT

    def submissions(self, cik: str) -> dict[str, Any]:
        cik10 = str(cik).strip().zfill(10)
        return _request_json(
            f"{self.BASE}/submissions/CIK{cik10}.json",
            headers={"User-Agent": self.user_agent},
        )

    def companyfacts(self, cik: str) -> dict[str, Any]:
        cik10 = str(cik).strip().zfill(10)
        return _request_json(
            f"{self.BASE}/api/xbrl/companyfacts/CIK{cik10}.json",
            headers={"User-Agent": self.user_agent},
        )


class FredClient:
    """FRED observations client. Requires FRED_API_KEY for live reads."""

    BASE = "https://api.stlouisfed.org/fred"

    def __init__(self, api_key: str | None = None):
        self.api_key = api_key or os.environ.get("FRED_API_KEY")

    def series_observations(
        self,
        series_id: str,
        *,
        observation_start: str | None = None,
        limit: int = 100,
    ) -> dict[str, Any]:
        if not self.api_key:
            raise SourceHTTPError("FRED_API_KEY is required for FRED live reads")
        return _request_json(
            f"{self.BASE}/series/observations",
            params={
                "series_id": series_id,
                "api_key": self.api_key,
                "file_type": "json",
                "observation_start": observation_start,
                "limit": limit,
                "sort_order": "desc",
            },
        )


class EiaClient:
    """EIA v2 data client. Requires EIA_API_KEY for live reads."""

    BASE = "https://api.eia.gov/v2"

    def __init__(self, api_key: str | None = None):
        self.api_key = api_key or os.environ.get("EIA_API_KEY")

    def route_data(
        self,
        route: str,
        *,
        data: tuple[str, ...] = ("value",),
        facets: dict[str, tuple[str, ...]] | None = None,
        length: int = 100,
    ) -> dict[str, Any]:
        if not self.api_key:
            raise SourceHTTPError("EIA_API_KEY is required for EIA live reads")
        params: dict[str, Any] = {"api_key": self.api_key, "length": length}
        for idx, column in enumerate(data):
            params[f"data[{idx}]"] = column
        for facet, values in (facets or {}).items():
            for idx, value in enumerate(values):
                params[f"facets[{facet}][{idx}]"] = value
        clean_route = route.strip("/")
        return _request_json(f"{self.BASE}/{clean_route}/data", params=params)


def _clean_markdown_line(line: str) -> str:
    line = re.sub(r"\[\^[^\]]+\^\]", "", line)
    line = re.sub(r"[*_`>#-]+", " ", line)
    return re.sub(r"\s+", " ", line).strip()


def _parse_markdown_sections(text: str, limit: int = 60) -> list[dict[str, Any]]:
    sections: list[dict[str, Any]] = []
    for line in text.splitlines():
        if not line.startswith("#"):
            continue
        level = len(line) - len(line.lstrip("#"))
        title = _clean_markdown_line(line.lstrip("#"))
        if not title or title.lower() in {"references"}:
            continue
        sections.append({"level": level, "title": title})
        if len(sections) >= limit:
            break
    return sections


def _extract_top_ideas(text: str, limit: int = 20) -> list[dict[str, str]]:
    lines = text.splitlines()
    start = next((idx for idx, line in enumerate(lines) if "Top 10 Conviction" in line), -1)
    if start < 0:
        return []
    table_lines = [line for line in lines[start : start + 80] if line.strip().startswith("|")]
    if len(table_lines) < 3:
        return []
    header = [
        cell.strip().lower().replace(" ", "_") for cell in table_lines[0].strip("|").split("|")
    ]
    out: list[dict[str, str]] = []
    for line in table_lines[2:]:
        cells = [cell.strip() for cell in line.strip("|").split("|")]
        if len(cells) != len(header):
            continue
        row = dict(zip(header, cells, strict=False))
        ticker = (row.get("ticker") or "").upper()
        if ticker and re.fullmatch(r"[A-Z0-9.\-]{1,12}", ticker):
            out.append(row)
        if len(out) >= limit:
            break
    return out


def _extract_mindset(text: str, limit: int = 12) -> list[str]:
    phrases = (
        "multi-theme",
        "picks & shovels",
        "risk tier",
        "capital allocation",
        "position sizing",
        "catalyst",
        "quarterly",
        "qualification moat",
        "convergence premium",
        "drawdown",
        "counter-arguments",
        "source",
    )
    out: list[str] = []
    for raw_line in text.splitlines():
        line = _clean_markdown_line(raw_line)
        if len(line) < 45 or len(line) > 260:
            continue
        lower = line.lower()
        if any(phrase in lower for phrase in phrases):
            if line not in out:
                out.append(line)
        if len(out) >= limit:
            break

    fallback = [
        "Favor multi-theme exposure where independent secular drivers reinforce one thesis.",
        "Use picks-and-shovels suppliers to reduce binary platform risk in early markets.",
        "Keep risk tiers explicit so speculative names cannot quietly become core positions.",
        "Track catalysts and disconfirming evidence with the same discipline as upside cases.",
        "Refresh theses from filings, macro, energy, and crypto source data rather than stale notes.",
    ]
    for principle in fallback:
        if len(out) >= limit:
            break
        if principle not in out:
            out.append(principle)
    return out[:limit]


def _float_or_none(value: Any) -> float | None:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _parse_csv_assets(zf: zipfile.ZipFile, names: list[str]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for name in names:
        if not name.endswith("_info.csv"):
            continue
        try:
            raw = zf.read(name)[:512_000].decode("utf-8", errors="replace")
            rows = list(csv.DictReader(raw.splitlines()))
        except Exception as exc:
            out.append({"source_file": name, "error": str(exc)})
            continue
        if not rows:
            continue
        row = rows[0]
        ticker = str(row.get("symbol") or Path(name).name.replace("_info.csv", "")).upper()
        out.append(
            {
                "symbol": ticker,
                "source_file": name,
                "name": row.get("longName") or row.get("shortName") or row.get("displayName"),
                "sector": row.get("sectorDisp") or row.get("sector"),
                "industry": row.get("industryDisp") or row.get("industry"),
                "currency": row.get("currency"),
                "current_price": _float_or_none(row.get("currentPrice")),
                "target_mean_price": _float_or_none(row.get("targetMeanPrice")),
                "recommendation": row.get("recommendationKey"),
                "market_cap": _float_or_none(row.get("marketCap")),
                "total_revenue": _float_or_none(row.get("totalRevenue")),
                "gross_margins": _float_or_none(row.get("grossMargins")),
                "headers": len(row.keys()),
            }
        )
    return out


def load_static_watchlist() -> dict[str, Any]:
    if not STATIC_WATCHLIST_FILE.exists():
        return {}
    try:
        return json.loads(STATIC_WATCHLIST_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def load_research_pack(zip_path: str | Path | None = None) -> ResearchPack:
    """Load the optional Kimi research ZIP without materializing it into the repo."""

    raw_path = zip_path or os.environ.get(RESEARCH_ZIP_ENV)
    if not raw_path:
        static = load_static_watchlist()
        principles = list(static.get("key_insights") or [])[:8]
        return ResearchPack(
            available=bool(static),
            source_label="static convergence watchlist" if static else "not configured",
            source_kind="static-watchlist" if static else "missing",
            files=[str(STATIC_WATCHLIST_FILE.relative_to(ROOT))] if static else [],
            mindset_principles=principles,
        )

    path = Path(raw_path).expanduser()
    if not path.exists():
        return ResearchPack(
            available=False,
            source_label=path.name,
            source_kind="zip",
            error=f"{RESEARCH_ZIP_ENV} path does not exist",
        )

    try:
        with zipfile.ZipFile(path) as zf:
            names = sorted(zf.namelist())
            markdown_name = next(
                (
                    name
                    for name in (
                        "investment_research.agent.final.md",
                        "investment_research.agent.final.converted.md",
                        "asymmetric_bets.agent.final.md",
                    )
                    if name in names
                ),
                None,
            )
            markdown = (
                zf.read(markdown_name).decode("utf-8", errors="replace") if markdown_name else ""
            )
            return ResearchPack(
                available=True,
                source_label=path.name,
                source_kind="zip",
                files=names,
                sections=_parse_markdown_sections(markdown),
                top_ideas=_extract_top_ideas(markdown),
                csv_assets=_parse_csv_assets(zf, names),
                mindset_principles=_extract_mindset(markdown),
            )
    except Exception as exc:
        return ResearchPack(
            available=False,
            source_label=path.name,
            source_kind="zip",
            error=str(exc),
        )


def _asset_from_position(position: dict[str, Any], tier: str) -> InvestmentAsset | None:
    ticker = str(position.get("ticker") or "").upper().strip()
    if not ticker:
        return None
    asset_class = (
        ASSET_CLASS_ETF if "ETF" in str(position.get("name") or "") else ASSET_CLASS_EQUITY
    )
    return InvestmentAsset(
        symbol=ticker,
        name=str(position.get("name") or ticker),
        asset_class=asset_class,
        risk_tier=tier.replace("_", "-"),
        watch_level="watchlist",
        themes=tuple(filter(None, str(position.get("sector") or "").split("-"))),
        thesis=str(position.get("thesis") or "Kimi convergence watchlist position."),
        source_note="static convergence watchlist",
    )


def build_universe(research_pack: ResearchPack | None = None) -> list[dict[str, Any]]:
    """Build a deduped universe from defaults, repo watchlist, and optional ZIP CSVs."""

    assets: dict[str, InvestmentAsset] = {asset.symbol: asset for asset in DEFAULT_ASSETS}

    static = load_static_watchlist()
    for tier, payload in (static.get("tiers") or {}).items():
        positions = payload.get("positions") if isinstance(payload, dict) else None
        if not isinstance(positions, list):
            continue
        for position in positions:
            if not isinstance(position, dict):
                continue
            asset = _asset_from_position(position, tier)
            if asset is not None and asset.symbol not in assets:
                assets[asset.symbol] = asset

    if research_pack:
        for csv_asset in research_pack.csv_assets:
            symbol = str(csv_asset.get("symbol") or "").upper()
            if not symbol or symbol in assets:
                continue
            assets[symbol] = InvestmentAsset(
                symbol=symbol,
                name=str(csv_asset.get("name") or symbol),
                asset_class=ASSET_CLASS_EQUITY,
                risk_tier="research",
                watch_level="watchlist",
                themes=tuple(
                    filter(
                        None,
                        [
                            str(csv_asset.get("sector") or "").lower().replace(" ", "-"),
                            str(csv_asset.get("industry") or "").lower().replace(" ", "-"),
                        ],
                    )
                ),
                thesis="Imported from attached Kimi CSV fundamentals snapshot.",
                source_note="attached research CSV",
            )

    out = [asset.to_dict() for asset in assets.values()]
    for item in out:
        item["connectors"] = applicable_connector_ids(item)
    return sorted(out, key=lambda row: (row["asset_class"], row["watch_level"], row["symbol"]))


def applicable_connector_ids(asset: dict[str, Any]) -> list[str]:
    asset_class = asset.get("asset_class")
    connector_ids: set[str] = {"kimi_research_pack", "tradingview_signal_research"}
    if asset_class in {ASSET_CLASS_EQUITY, ASSET_CLASS_ETF}:
        connector_ids.add("sec_submissions")
    if asset_class == ASSET_CLASS_EQUITY:
        connector_ids.add("sec_companyfacts")
    if asset_class == ASSET_CLASS_CRYPTO:
        connector_ids.update(
            {
                "coingecko_market",
                "defillama_defi",
                "hyperliquid_info",
                "robinhood_crypto_readonly",
            }
        )
    for theme in asset.get("themes") or []:
        connector_ids.update(THEME_CONNECTORS.get(str(theme), ()))
    ordered = [connector.id for connector in SOURCE_CONNECTORS if connector.id in connector_ids]
    return ordered


def build_source_mesh(universe: list[dict[str, Any]]) -> dict[str, Any]:
    connector_rows = [connector.to_dict() for connector in SOURCE_CONNECTORS]
    connector_by_id = {row["id"]: row for row in connector_rows}

    coverage: list[dict[str, Any]] = []
    for asset in universe:
        ids = applicable_connector_ids(asset)
        coverage.append(
            {
                "symbol": asset["symbol"],
                "name": asset["name"],
                "asset_class": asset["asset_class"],
                "risk_tier": asset["risk_tier"],
                "themes": asset.get("themes") or [],
                "connectors": ids,
                "connector_count": len(ids),
                "ready_connectors": sum(
                    1 for connector_id in ids if connector_by_id[connector_id]["status"] == "ready"
                ),
            }
        )

    missing_envs = sorted(
        {
            env
            for connector in SOURCE_CONNECTORS
            for env in connector.auth_envs
            if not os.environ.get(env)
        }
    )
    return {
        "connectors": connector_rows,
        "coverage": coverage,
        "totals": {
            "assets": len(universe),
            "connectors": len(connector_rows),
            "configured_connectors": sum(1 for row in connector_rows if row["configured"]),
            "missing_envs": len(missing_envs),
        },
        "missing_envs": missing_envs,
    }


def _robinhood_readiness() -> dict[str, Any]:
    secret_dir = Path.home() / ".config" / "sapphire-secrets"
    key_file = secret_dir / "robinhood_api_key"
    private_file = secret_dir / "robinhood_ed25519_private.b64"
    return {
        "configured": key_file.exists() and private_file.exists(),
        "required_files_present": {
            "robinhood_api_key": key_file.exists(),
            "robinhood_ed25519_private.b64": private_file.exists(),
        },
        "mode": "read-only portfolio snapshot",
    }


def build_ops_queue(research_pack: ResearchPack, mesh: dict[str, Any]) -> list[dict[str, Any]]:
    rh = _robinhood_readiness()
    return [
        {
            "id": "research-pack-ingest",
            "lane": "intel",
            "status": "ready" if research_pack.available else "needs_config",
            "title": "Attach Kimi research pack to source mesh",
            "detail": "Parse markdown sections, thesis principles, top ideas, and ticker CSVs.",
            "dry_run": f"export {RESEARCH_ZIP_ENV}=/path/to/research.zip",
        },
        {
            "id": "sec-equity-baseline",
            "lane": "tracking",
            "status": "ready",
            "title": "Backfill SEC filings and XBRL fundamentals for equity universe",
            "detail": "Use SEC submissions + companyfacts as official filing layer.",
            "dry_run": "python3 - <<'PY'\nfrom lib.intel.investment_intel import SecEdgarClient\nprint(SecEdgarClient().submissions('320193').get('name'))\nPY",
        },
        {
            "id": "macro-energy-series",
            "lane": "analysis",
            "status": "needs_key" if mesh["missing_envs"] else "ready",
            "title": "Wire FRED + EIA series into energy and AI-power lenses",
            "detail": "Track rates, inflation, electricity demand, generation mix, and gas prices.",
            "dry_run": "FRED_API_KEY=... EIA_API_KEY=... python3 -m pytest tests/unit/test_investment_intel.py -q",
        },
        {
            "id": "crypto-source-bridge",
            "lane": "crypto",
            "status": "ready",
            "title": "Keep crypto factors in the same source mesh",
            "detail": "CoinGecko, Hyperliquid, DeFiLlama, Robinhood read-only, and TradingView signals.",
            "dry_run": "curl -u sapphire:test http://127.0.0.1:5058/api/investments/sources",
        },
        {
            "id": "robinhood-readonly-audit",
            "lane": "portfolio",
            "status": "ready" if rh["configured"] else "needs_secret_presence",
            "title": "Audit Robinhood read-only credential presence",
            "detail": "Portfolio and best-bid/ask reads only; no order endpoints are invoked here.",
            "dry_run": "python3 - <<'PY'\nfrom lib.portfolio.robinhood import RobinhoodReader\nprint(RobinhoodReader().is_configured())\nPY",
        },
        {
            "id": "foundry-materialization-plan",
            "lane": "ops",
            "status": "planned",
            "title": "Materialize normalized intel snapshots after review",
            "detail": "Next PR can emit NDJSON under data lake staging without live trading side effects.",
            "dry_run": "python3 scripts/ops/org_status.py --no-external --markdown",
        },
    ]


def build_analysis_lenses(universe: list[dict[str, Any]]) -> list[dict[str, Any]]:
    symbols_by_theme: dict[str, list[str]] = {}
    for asset in universe:
        for theme in asset.get("themes") or []:
            symbols_by_theme.setdefault(theme, []).append(asset["symbol"])
    return [
        {
            "id": "ai-power",
            "label": "AI Power",
            "symbols": sorted(set(symbols_by_theme.get("ai-power", []))),
            "metrics": ["electricity demand", "PJM/capacity stress", "nuclear fleet", "gas price"],
            "sources": [
                "eia_energy",
                "fred_macro",
                "sec_companyfacts",
                "tradingview_signal_research",
            ],
        },
        {
            "id": "defense-space",
            "label": "Defense + Space",
            "symbols": sorted(
                set(
                    symbols_by_theme.get("defense", [])
                    + symbols_by_theme.get("drones", [])
                    + symbols_by_theme.get("space", [])
                    + symbols_by_theme.get("defense-ai", [])
                )
            ),
            "metrics": ["backlog", "program awards", "cash runway", "margin progression"],
            "sources": ["sec_submissions", "sec_companyfacts", "kimi_research_pack"],
        },
        {
            "id": "solar-storage",
            "label": "Solar + Storage",
            "symbols": sorted(
                set(
                    symbols_by_theme.get("solar", [])
                    + symbols_by_theme.get("storage", [])
                    + symbols_by_theme.get("renewables", [])
                )
            ),
            "metrics": ["domestic content", "backlog", "module pricing", "interconnection delays"],
            "sources": ["eia_energy", "sec_companyfacts", "fred_macro"],
        },
        {
            "id": "crypto-liquidity",
            "label": "Crypto Liquidity",
            "symbols": sorted(
                asset["symbol"] for asset in universe if asset["asset_class"] == ASSET_CLASS_CRYPTO
            ),
            "metrics": ["spot price", "funding", "open interest", "stablecoin supply", "trending"],
            "sources": ["coingecko_market", "hyperliquid_info", "defillama_defi"],
        },
    ]


def build_crypto_bridge(
    universe: list[dict[str, Any]],
    *,
    fetch_live: bool = False,
) -> dict[str, Any]:
    tokens = [
        {
            "symbol": asset["symbol"],
            "name": asset["name"],
            "risk_tier": asset["risk_tier"],
            "watch_level": asset["watch_level"],
            "coingecko_id": COINGECKO_IDS_BY_SYMBOL.get(asset["symbol"]),
            "connectors": asset.get("connectors") or [],
        }
        for asset in universe
        if asset["asset_class"] == ASSET_CLASS_CRYPTO
    ]
    bridge: dict[str, Any] = {
        "tokens_we_like": tokens,
        "live_requested": fetch_live,
        "prices": {},
        "trending": [],
        "errors": {},
        "sources": [
            "coingecko_market",
            "hyperliquid_info",
            "defillama_defi",
            "robinhood_crypto_readonly",
        ],
    }
    if not fetch_live:
        return bridge

    try:
        from lib.chain.sources import CoinGeckoClient

        client = CoinGeckoClient()
        ids = [row["coingecko_id"] for row in tokens if row.get("coingecko_id")]
        raw_prices = client.simple_prices(ids)
        bridge["prices"] = {
            row["symbol"]: raw_prices.get(row["coingecko_id"], {})
            for row in tokens
            if row.get("coingecko_id")
        }
        bridge["trending"] = [asdict(coin) for coin in client.trending(limit=12)]
    except Exception as exc:
        bridge["errors"]["coingecko"] = f"{type(exc).__name__}: {exc}"
    return bridge


def build_series_catalog() -> list[dict[str, Any]]:
    return [series.to_dict() for series in SERIES_CATALOG]


def _probe(
    probe_id: str,
    label: str,
    callback,
    *,
    live: bool,
) -> SourceProbe:
    if not live:
        return SourceProbe(
            id=probe_id,
            label=label,
            status="not_requested",
            detail="Live probe not requested; source remains mapped for dry-run planning.",
        )
    started = time.perf_counter()
    try:
        detail, count = callback()
        return SourceProbe(
            id=probe_id,
            label=label,
            status="ready",
            detail=detail,
            latency_ms=round((time.perf_counter() - started) * 1000, 2),
            observed_count=count,
        )
    except Exception as exc:
        return SourceProbe(
            id=probe_id,
            label=label,
            status="error",
            detail=f"{type(exc).__name__}: {exc}",
            latency_ms=round((time.perf_counter() - started) * 1000, 2),
        )


def probe_source_mesh(
    zip_path: str | Path | None = None,
    *,
    live: bool = False,
) -> dict[str, Any]:
    """Probe source readiness without mutating external state."""

    research_pack = load_research_pack(zip_path)
    rh = _robinhood_readiness()
    probes: list[SourceProbe] = [
        SourceProbe(
            id="kimi_research_pack",
            label="Kimi research pack",
            status="ready" if research_pack.available else "needs_config",
            detail=(
                f"{research_pack.source_kind}: {len(research_pack.files)} files, "
                f"{len(research_pack.csv_assets)} CSV assets"
                if research_pack.available
                else research_pack.error or f"Set {RESEARCH_ZIP_ENV} to attach the latest pack."
            ),
            observed_count=len(research_pack.csv_assets),
        ),
        SourceProbe(
            id="robinhood_crypto_readonly",
            label="Robinhood Crypto read-only",
            status="ready" if rh["configured"] else "needs_secret_presence",
            detail="Credential files present; no portfolio request was made."
            if rh["configured"]
            else "Credential file presence missing or partial.",
            observed_count=sum(1 for present in rh["required_files_present"].values() if present),
        ),
        SourceProbe(
            id="fred_macro",
            label="FRED macro",
            status="ready" if os.environ.get("FRED_API_KEY") else "needs_key",
            detail="FRED_API_KEY configured."
            if os.environ.get("FRED_API_KEY")
            else "FRED_API_KEY absent; catalog is mapped but live reads are disabled.",
            observed_count=sum(1 for row in SERIES_CATALOG if row.provider == "FRED"),
        ),
        SourceProbe(
            id="eia_energy",
            label="EIA energy",
            status="ready" if os.environ.get("EIA_API_KEY") else "needs_key",
            detail="EIA_API_KEY configured."
            if os.environ.get("EIA_API_KEY")
            else "EIA_API_KEY absent; catalog is mapped but live reads are disabled.",
            observed_count=sum(1 for row in SERIES_CATALOG if row.provider == "EIA"),
        ),
    ]

    sec_probe = (
        _probe(
            "sec_company_tickers",
            "SEC company ticker map",
            lambda: (
                "official SEC company_tickers.json reachable",
                len(
                    _request_json(
                        "https://www.sec.gov/files/company_tickers.json",
                        headers={"User-Agent": os.environ[SEC_USER_AGENT_ENV]},
                    )
                ),
            ),
            live=live,
        )
        if not live or os.environ.get(SEC_USER_AGENT_ENV)
        else SourceProbe(
            id="sec_company_tickers",
            label="SEC company ticker map",
            status="needs_config",
            detail=f"Set {SEC_USER_AGENT_ENV} to a contact user-agent before probing SEC.",
        )
    )

    probes.extend(
        [
            sec_probe,
            _probe(
                "coingecko_market",
                "CoinGecko trending + spot",
                lambda: (
                    "CoinGecko simple-price/trending reachable",
                    len(
                        build_crypto_bridge(build_universe(research_pack), fetch_live=True)[
                            "trending"
                        ]
                    ),
                ),
                live=live,
            ),
            _probe(
                "hyperliquid_info",
                "Hyperliquid market context",
                lambda: _probe_hyperliquid(),
                live=live,
            ),
            _probe(
                "defillama_defi",
                "DeFiLlama stablecoins",
                lambda: _probe_defillama(),
                live=live,
            ),
        ]
    )

    rows = [probe.to_dict() for probe in probes]
    return {
        "timestamp": _now_iso(),
        "mode": "read-only",
        "live_requested": live,
        "probes": rows,
        "summary": {
            "total": len(rows),
            "ready": sum(1 for row in rows if row["status"] == "ready"),
            "needs_key": sum(1 for row in rows if row["status"] == "needs_key"),
            "needs_config": sum(1 for row in rows if row["status"] == "needs_config"),
            "errors": sum(1 for row in rows if row["status"] == "error"),
            "not_requested": sum(1 for row in rows if row["status"] == "not_requested"),
        },
        "series_catalog": build_series_catalog(),
    }


def _probe_hyperliquid() -> tuple[str, int]:
    from lib.chain.sources import HyperliquidClient

    assets = HyperliquidClient().meta_and_asset_ctxs()
    return "Hyperliquid metaAndAssetCtxs reachable", len(assets)


def _probe_defillama() -> tuple[str, int]:
    from lib.chain.sources import DefiLlamaClient

    stablecoins = DefiLlamaClient().stablecoins()
    return (
        f"DeFiLlama stablecoins reachable (${stablecoins.total_usd:,.0f} total)",
        stablecoins.count,
    )


def build_materialization_rows(report: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    """Build normalized rows for GCS/BQ staging without writing by default."""

    timestamp = report.get("timestamp") or _now_iso()
    assets = report.get("universe") or []
    mesh = report.get("source_mesh") or {}
    research = report.get("research_pack") or {}
    crypto = (report.get("crypto_bridge") or {}).get("tokens_we_like") or []

    return {
        "investment_assets": [
            {
                "timestamp": timestamp,
                "symbol": asset["symbol"],
                "name": asset["name"],
                "asset_class": asset["asset_class"],
                "risk_tier": asset["risk_tier"],
                "watch_level": asset["watch_level"],
                "themes": asset.get("themes") or [],
                "connectors": asset.get("connectors") or [],
                "thesis": asset.get("thesis"),
                "source_note": asset.get("source_note"),
            }
            for asset in assets
        ],
        "investment_source_coverage": [
            {
                "timestamp": timestamp,
                "symbol": coverage["symbol"],
                "asset_class": coverage["asset_class"],
                "connector_id": connector_id,
                "connector_count": coverage["connector_count"],
                "ready_connectors": coverage["ready_connectors"],
            }
            for coverage in mesh.get("coverage") or []
            for connector_id in coverage.get("connectors") or []
        ],
        "investment_ops_queue": [
            {
                "timestamp": timestamp,
                "id": row["id"],
                "lane": row["lane"],
                "status": row["status"],
                "title": row["title"],
                "detail": row["detail"],
            }
            for row in report.get("ops_queue") or []
        ],
        "investment_crypto_watchlist": [
            {
                "timestamp": timestamp,
                "symbol": row["symbol"],
                "name": row["name"],
                "risk_tier": row["risk_tier"],
                "watch_level": row["watch_level"],
                "coingecko_id": row.get("coingecko_id"),
                "connectors": row.get("connectors") or [],
            }
            for row in crypto
        ],
        "investment_research_pack": [
            {
                "timestamp": timestamp,
                "available": bool(research.get("available")),
                "source_label": research.get("source_label"),
                "source_kind": research.get("source_kind"),
                "file_count": len(research.get("files") or []),
                "csv_asset_count": len(research.get("csv_assets") or []),
                "top_idea_count": len(research.get("top_ideas") or []),
                "section_count": len(research.get("sections") or []),
            }
        ],
    }


def build_materialization_plan(
    report: dict[str, Any], *, out_dir: str | Path | None = None
) -> dict[str, Any]:
    rows = build_materialization_rows(report)
    base_dir = Path(out_dir) if out_dir else ROOT / "data" / ".gcp_stage" / "investment_intel"
    today = _today_stamp()
    run_id = _run_stamp()
    tables = [
        {
            "table": table,
            "rows": len(table_rows),
            "target": str(base_dir / "raw" / table / today / f"{run_id}.ndjson"),
        }
        for table, table_rows in rows.items()
    ]
    return {
        "mode": "dry-run-preview",
        "writes_by_default": False,
        "base_dir": str(base_dir),
        "tables": tables,
        "total_rows": sum(table["rows"] for table in tables),
    }


def write_materialization_preview(
    out_dir: str | Path,
    *,
    zip_path: str | Path | None = None,
    fetch_live_crypto: bool = False,
) -> dict[str, Any]:
    """Explicit dry-run writer for ignored local staging paths."""

    report = build_investment_intel_report(zip_path, fetch_live_crypto=fetch_live_crypto)
    rows = build_materialization_rows(report)
    base_dir = Path(out_dir)
    today = _today_stamp()
    run_id = _run_stamp()
    written: list[dict[str, Any]] = []
    for table, table_rows in rows.items():
        target = base_dir / "raw" / table / today / f"{run_id}.ndjson"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            "".join(json.dumps(row, sort_keys=True) + "\n" for row in table_rows),
            encoding="utf-8",
        )
        written.append({"table": table, "rows": len(table_rows), "path": str(target)})
    return {
        "timestamp": _now_iso(),
        "mode": "dry-run-write",
        "base_dir": str(base_dir),
        "written": written,
        "total_rows": sum(row["rows"] for row in written),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Sapphire investment intel source mesh")
    parser.add_argument("--zip", dest="zip_path", help="Optional Kimi research ZIP path")
    parser.add_argument(
        "--live-crypto", action="store_true", help="Fetch read-only CoinGecko preview"
    )
    parser.add_argument("--probe-live", action="store_true", help="Probe public live sources")
    parser.add_argument(
        "--write-preview",
        metavar="DIR",
        help="Write ignored NDJSON staging files under DIR/raw/* (explicit dry-run materialization)",
    )
    args = parser.parse_args(argv)

    if args.write_preview:
        payload = write_materialization_preview(
            args.write_preview,
            zip_path=args.zip_path,
            fetch_live_crypto=args.live_crypto,
        )
    elif args.probe_live:
        payload = probe_source_mesh(args.zip_path, live=True)
    else:
        payload = build_investment_intel_report(
            args.zip_path,
            fetch_live_crypto=args.live_crypto,
        )
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


def build_investment_intel_report(
    zip_path: str | Path | None = None,
    *,
    fetch_live_crypto: bool = False,
) -> dict[str, Any]:
    started = time.perf_counter()
    research_pack = load_research_pack(zip_path)
    universe = build_universe(research_pack)
    mesh = build_source_mesh(universe)
    ops_queue = build_ops_queue(research_pack, mesh)
    static = load_static_watchlist()

    report = {
        "timestamp": _now_iso(),
        "mode": "read-only",
        "disclaimer": "Research and operations intelligence only; not financial advice or trade execution.",
        "research_pack": research_pack.to_dict(),
        "universe": universe,
        "source_mesh": mesh,
        "source_probes": probe_source_mesh(zip_path, live=False),
        "ops_queue": ops_queue,
        "analysis_lenses": build_analysis_lenses(universe),
        "series_catalog": build_series_catalog(),
        "crypto_bridge": build_crypto_bridge(universe, fetch_live=fetch_live_crypto),
        "mindset": research_pack.mindset_principles,
        "catalyst_calendar_highlights": static.get("catalyst_calendar_highlights") or [],
        "source_docs": [
            {"label": connector.label, "url": connector.docs_url}
            for connector in SOURCE_CONNECTORS
            if connector.docs_url.startswith("http")
        ],
        "latency_ms": round((time.perf_counter() - started) * 1000, 2),
    }
    report["materialization_plan"] = build_materialization_plan(report)
    return report


def build_source_report(zip_path: str | Path | None = None) -> dict[str, Any]:
    research_pack = load_research_pack(zip_path)
    universe = build_universe(research_pack)
    mesh = build_source_mesh(universe)
    return {
        "timestamp": _now_iso(),
        "mode": "read-only",
        "research_pack": research_pack.to_dict(),
        "source_mesh": mesh,
        "source_probes": probe_source_mesh(zip_path, live=False),
        "series_catalog": build_series_catalog(),
        "robinhood": _robinhood_readiness(),
    }


__all__ = [
    "EiaClient",
    "FredClient",
    "ResearchPack",
    "SecEdgarClient",
    "SourceConnector",
    "SourceHTTPError",
    "SourceProbe",
    "build_investment_intel_report",
    "build_crypto_bridge",
    "build_materialization_plan",
    "build_materialization_rows",
    "build_series_catalog",
    "build_source_report",
    "build_source_mesh",
    "build_universe",
    "load_research_pack",
    "load_static_watchlist",
    "probe_source_mesh",
    "write_materialization_preview",
]


if __name__ == "__main__":
    raise SystemExit(main())
