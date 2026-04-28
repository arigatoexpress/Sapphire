"""
Kalshi Prediction Market Client

Fetches prediction market data from Kalshi's public REST API v2.
Filters for crypto-relevant and macro markets, normalizes to PredictionSignal format.

Endpoints:
  - REST API v2: https://api.elections.kalshi.com/trade-api/v2
  - Events: GET /events?status=open&limit=100
  - Markets: GET /markets?status=open&limit=200
"""

import contextlib
import os
import re
from datetime import datetime
from typing import Any

import aiohttp

from .prediction_signal import (
    PredictionMarketFeed,
    PredictionSignal,
    PredictionSource,
    SignalRelevance,
)

KALSHI_API_BASE = "https://api.elections.kalshi.com/trade-api/v2"

# Kalshi categories that are relevant to crypto trading
_RELEVANT_CATEGORIES = {
    "Crypto",
    "Economics",
    "Financial Markets",
    "Fed Funds Rate",
    "Inflation",
    "Tech",
}

# Patterns for crypto-relevant Kalshi markets
_CRYPTO_PATTERNS = re.compile(
    r"\b(bitcoin|btc|ethereum|eth|solana|sol|crypto|"
    r"coinbase|binance|sec.{0,8}crypto|"
    r"bitcoin.{0,8}price|ethereum.{0,8}price|"
    r"bitcoin.{0,8}etf|ethereum.{0,8}etf|"
    r"digital.{0,8}asset|stablecoin)\b",
    re.IGNORECASE,
)

_MACRO_PATTERNS = re.compile(
    r"\b(fed.{0,6}rate|interest.{0,6}rate|"
    r"cpi|inflation|gdp|recession|"
    r"unemployment|jobs.{0,6}report|nonfarm|"
    r"treasury.{0,6}yield|yield.{0,6}curve|"
    r"rate.{0,4}cut|rate.{0,4}hike|fomc|"
    r"s.?p.{0,3}500|nasdaq|dow.{0,4}jones|"
    r"stock.{0,6}market|tariff|trade.{0,4}war)\b",
    re.IGNORECASE,
)

# Map titles to crypto symbols
_SYMBOL_EXTRACTION = {
    r"\bbitcoin\b|\bbtc\b": "BTC",
    r"\bethereum\b|\beth\b": "ETH",
    r"\bsolana\b|\bsol\b": "SOL",
}


def _classify_kalshi_relevance(title: str, category: str) -> SignalRelevance | None:
    """Classify market relevance to crypto trading."""
    text = f"{title} {category}".lower()
    if _CRYPTO_PATTERNS.search(text):
        return SignalRelevance.DIRECT
    if category in _RELEVANT_CATEGORIES or _MACRO_PATTERNS.search(text):
        return SignalRelevance.MACRO
    return None


def _extract_symbols_kalshi(title: str) -> list[str]:
    """Extract crypto symbols mentioned in market title."""
    symbols = []
    text = title.lower()
    for pattern, symbol in _SYMBOL_EXTRACTION.items():
        if re.search(pattern, text, re.IGNORECASE):
            symbols.append(symbol)
    return symbols or ["BTC"]


class KalshiClient(PredictionMarketFeed):
    """Kalshi REST API v2 client for crypto-relevant prediction markets."""

    def __init__(
        self,
        poll_interval: float = 90.0,
        min_volume: int = 100,
        max_markets: int = 50,
        api_key: str | None = None,
    ):
        super().__init__(source=PredictionSource.KALSHI, poll_interval=poll_interval)
        self.min_volume = min_volume
        self.max_markets = max_markets
        self._api_base = KALSHI_API_BASE
        self._api_key = api_key or os.getenv("KALSHI_API_KEY", "")

    async def _fetch_markets(self, session: aiohttp.ClientSession) -> list[PredictionSignal]:
        """Fetch active Kalshi markets and filter for crypto/macro relevance."""
        signals: list[PredictionSignal] = []

        try:
            params = {
                "status": "open",
                "limit": "200",
            }
            headers = {}
            if self._api_key:
                headers["Authorization"] = f"Bearer {self._api_key}"
            timeout = aiohttp.ClientTimeout(total=15, connect=5)
            async with session.get(
                f"{self._api_base}/markets",
                params=params,
                headers=headers if headers else None,
                timeout=timeout,
            ) as resp:
                if resp.status != 200:
                    body = await resp.text()
                    self._log_error(f"Kalshi API {resp.status}: {body[:200]}")
                    return []
                data = await resp.json(content_type=None)
        except (aiohttp.ClientError, Exception) as exc:
            self._log_error(f"Kalshi fetch error: {exc}")
            return []

        markets = data.get("markets", [])
        if not isinstance(markets, list):
            return []

        for market in markets:
            signal = self._parse_market(market)
            if signal:
                signals.append(signal)
            if len(signals) >= self.max_markets:
                break

        return signals

    def _parse_market(self, raw: dict[str, Any]) -> PredictionSignal | None:
        """Parse a Kalshi market into a PredictionSignal if relevant."""
        ticker = str(raw.get("ticker", "")).strip()
        event_ticker = str(raw.get("event_ticker", "")).strip()
        title = str(raw.get("title") or raw.get("subtitle", "")).strip()
        if not title and not ticker:
            return None

        # Use ticker as question if title is empty
        question = title or ticker

        # Kalshi doesn't have a top-level category on markets,
        # so we check event_ticker prefixes and the title text
        category = self._infer_category(event_ticker, question)
        relevance = _classify_kalshi_relevance(question, category)
        if relevance is None:
            return None

        # Extract probability from yes_bid/yes_ask (in cents, 0-100)
        probability = self._extract_probability(raw)
        if probability is None:
            return None

        volume = int(raw.get("volume", 0) or 0)
        if volume < self.min_volume:
            return None

        volume_24h = int(raw.get("volume_24h", 0) or 0)

        # Kalshi prices are in cents; liquidity is in dollars string
        liquidity_str = (
            str(raw.get("liquidity_dollars", "0") or "0").replace("$", "").replace(",", "")
        )
        try:
            liquidity_usd = float(liquidity_str)
        except (ValueError, TypeError):
            liquidity_usd = 0.0

        # Estimate USD volume (each contract is ~$1 notional)
        volume_usd = float(volume)

        symbols = _extract_symbols_kalshi(question)

        # Parse end/expiration date
        end_date = None
        for date_field in ("expiration_time", "close_time", "expected_expiration_time"):
            val = raw.get(date_field)
            if val:
                try:
                    end_date = datetime.fromisoformat(str(val).replace("Z", "+00:00"))
                    break
                except (ValueError, TypeError):
                    continue

        # Price change as proxy for 1h momentum
        prob_1h_ago = None
        prev_price = raw.get("previous_price")
        if prev_price is not None and probability is not None:
            with contextlib.suppress(ValueError, TypeError):
                prob_1h_ago = float(prev_price) / 100.0

        tags = []
        if volume_24h >= 1000:
            tags.append("active-24h")
        if relevance == SignalRelevance.DIRECT:
            tags.append("crypto-direct")

        return PredictionSignal(
            market_id=f"kalshi_{ticker}",
            source=PredictionSource.KALSHI,
            question=question,
            probability=probability,
            volume_usd=volume_usd,
            liquidity_usd=liquidity_usd,
            relevance=relevance,
            symbols=symbols,
            probability_1h_ago=prob_1h_ago,
            end_date=end_date,
            category=category,
            tags=tags,
            raw_data={"ticker": ticker, "event_ticker": event_ticker},
        )

    @staticmethod
    def _extract_probability(raw: dict[str, Any]) -> float | None:
        """Extract YES probability from Kalshi market data (prices in cents 0-100)."""
        # Use yes_bid and yes_ask midpoint
        yes_bid = raw.get("yes_bid")
        yes_ask = raw.get("yes_ask")
        if yes_bid is not None and yes_ask is not None:
            try:
                bid = float(yes_bid)
                ask = float(yes_ask)
                if bid > 0 or ask > 0:
                    return ((bid + ask) / 2) / 100.0
            except (ValueError, TypeError):
                pass

        # Fallback to last_price
        last_price = raw.get("last_price")
        if last_price is not None:
            try:
                return float(last_price) / 100.0
            except (ValueError, TypeError):
                pass

        return None

    @staticmethod
    def _infer_category(event_ticker: str, question: str) -> str:
        """Infer category from Kalshi event ticker prefix."""
        ticker_upper = event_ticker.upper()
        if any(k in ticker_upper for k in ("CRYPTO", "BTC", "ETH", "COIN")):
            return "Crypto"
        if any(k in ticker_upper for k in ("FED", "FOMC", "RATE")):
            return "Fed Funds Rate"
        if any(k in ticker_upper for k in ("CPI", "INFL")):
            return "Inflation"
        if any(k in ticker_upper for k in ("GDP", "ECON", "JOBS", "UNEMP", "NFP")):
            return "Economics"
        if any(k in ticker_upper for k in ("SP500", "NASDAQ", "DJI", "STOCK")):
            return "Financial Markets"
        if any(k in ticker_upper for k in ("TECH", "AI")):
            return "Tech"
        # Fall back to question text analysis
        text = question.lower()
        if any(w in text for w in ("bitcoin", "ethereum", "crypto")):
            return "Crypto"
        if any(w in text for w in ("federal reserve", "interest rate", "fomc")):
            return "Fed Funds Rate"
        if any(w in text for w in ("inflation", "cpi")):
            return "Inflation"
        return ""
