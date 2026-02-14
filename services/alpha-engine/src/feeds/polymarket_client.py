"""
Polymarket Prediction Market Client

Fetches prediction market data from Polymarket's Gamma API (public, no auth).
Filters for crypto-relevant markets and normalizes to PredictionSignal format.

Endpoints:
  - Gamma API: https://gamma-api.polymarket.com
  - Markets: GET /markets?active=true&limit=100
  - Events: GET /events?active=true&limit=100
"""

import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import aiohttp
from loguru import logger

from .prediction_signal import (
    PredictionMarketFeed,
    PredictionSignal,
    PredictionSource,
    SignalRelevance,
)

# Keywords that indicate crypto-relevant prediction markets
_CRYPTO_DIRECT_PATTERNS = re.compile(
    r"\b(bitcoin|btc|ethereum|eth|solana|sol|crypto|bnb|xrp|"
    r"cardano|ada|dogecoin|doge|polygon|matic|avalanche|avax|"
    r"chainlink|link|uniswap|uni|litecoin|ltc|polkadot|dot|"
    r"near|aptos|apt|sui|sei|stx|celestia|tia|ton|"
    r"defi|nft|stablecoin|usdc|usdt|tether|coinbase|binance|"
    r"sec.{0,8}crypto|cftc.{0,8}crypto|bitcoin.{0,8}etf|"
    r"ethereum.{0,8}etf|spot.{0,8}etf)\b",
    re.IGNORECASE,
)

_MACRO_PATTERNS = re.compile(
    r"\b(federal reserve|fed.{0,12}rate|interest rate|"
    r"cpi|inflation|gdp|recession|jobs report|unemployment|"
    r"treasury|yield curve|rate cut|cut.{0,4}rate|rate hike|fomc|"
    r"tariff|trade war|sanctions|s&p.{0,3}500|nasdaq|"
    r"dow jones|stock market crash)\b",
    re.IGNORECASE,
)

_REGULATORY_PATTERNS = re.compile(
    r"\b(sec |gensler|atkins|cftc |crypto.{0,8}regulat|"
    r"crypto.{0,8}ban|stablecoin.{0,8}bill|"
    r"digital asset|cbdc|crypto.{0,8}executive order|"
    r"crypto.{0,8}legislation|bitcoin.{0,8}legal)\b",
    re.IGNORECASE,
)

# Map known Polymarket categories to crypto symbols
_SYMBOL_EXTRACTION = {
    r"\bbitcoin\b|\bbtc\b": "BTC",
    r"\bethereum\b|\beth\b": "ETH",
    r"\bsolana\b|\bsol\b": "SOL",
    r"\bbnb\b": "BNB",
    r"\bxrp\b": "XRP",
    r"\bdogecoin\b|\bdoge\b": "DOGE",
    r"\bcardano\b|\bada\b": "ADA",
    r"\bavalanch\w*\b|\bavax\b": "AVAX",
    r"\bchainlink\b|\blink\b": "LINK",
    r"\bpolkadot\b|\bdot\b": "DOT",
    r"\bnear\b": "NEAR",
    r"\baptos\b|\bapt\b": "APT",
    r"\bsui\b": "SUI",
}

GAMMA_API_BASE = "https://gamma-api.polymarket.com"


def _classify_relevance(question: str, category: str) -> Optional[SignalRelevance]:
    """Classify how relevant a market is to crypto trading."""
    text = f"{question} {category}".lower()
    if _CRYPTO_DIRECT_PATTERNS.search(text):
        return SignalRelevance.DIRECT
    if _REGULATORY_PATTERNS.search(text):
        return SignalRelevance.REGULATORY
    if _MACRO_PATTERNS.search(text):
        return SignalRelevance.MACRO
    return None


def _extract_symbols(question: str) -> List[str]:
    """Extract crypto symbols from a market question."""
    symbols = []
    text = question.lower()
    for pattern, symbol in _SYMBOL_EXTRACTION.items():
        if re.search(pattern, text, re.IGNORECASE):
            symbols.append(symbol)
    return symbols or ["BTC"]  # Default to BTC for macro events


class PolymarketClient(PredictionMarketFeed):
    """Polymarket Gamma API client for crypto-relevant prediction markets."""

    def __init__(
        self,
        poll_interval: float = 60.0,
        min_volume_usd: float = 10_000.0,
        max_markets: int = 50,
    ):
        super().__init__(source=PredictionSource.POLYMARKET, poll_interval=poll_interval)
        self.min_volume_usd = min_volume_usd
        self.max_markets = max_markets
        self._api_base = GAMMA_API_BASE

    async def _fetch_markets(self, session: aiohttp.ClientSession) -> List[PredictionSignal]:
        """Fetch active Polymarket markets and filter for crypto relevance."""
        signals: List[PredictionSignal] = []

        try:
            params = {
                "active": "true",
                "closed": "false",
                "limit": "100",
                "order": "volumeNum",
                "ascending": "false",
            }
            timeout = aiohttp.ClientTimeout(total=15, connect=5)
            async with session.get(
                f"{self._api_base}/markets",
                params=params,
                timeout=timeout,
            ) as resp:
                if resp.status != 200:
                    body = await resp.text()
                    self._log_error(f"Polymarket API {resp.status}: {body[:200]}")
                    return []
                markets = await resp.json(content_type=None)
        except (aiohttp.ClientError, Exception) as exc:
            self._log_error(f"Polymarket fetch error: {exc}")
            return []

        if not isinstance(markets, list):
            return []

        for market in markets:
            signal = self._parse_market(market)
            if signal:
                signals.append(signal)
            if len(signals) >= self.max_markets:
                break

        return signals

    def _parse_market(self, raw: Dict[str, Any]) -> Optional[PredictionSignal]:
        """Parse a Polymarket market into a PredictionSignal if crypto-relevant."""
        question = str(raw.get("question", "")).strip()
        category = str(raw.get("category", "")).strip()
        if not question:
            return None

        relevance = _classify_relevance(question, category)
        if relevance is None:
            return None

        # Parse probability from outcomePrices
        probability = self._extract_probability(raw)
        if probability is None:
            return None

        volume_usd = float(raw.get("volumeNum", 0) or 0)
        if volume_usd < self.min_volume_usd:
            return None

        liquidity_usd = float(raw.get("liquidityNum", 0) or 0)
        symbols = _extract_symbols(question)

        # Parse dates
        end_date = None
        end_str = raw.get("endDate") or raw.get("endDateIso")
        if end_str:
            try:
                end_date = datetime.fromisoformat(str(end_str).replace("Z", "+00:00"))
            except (ValueError, TypeError):
                pass

        # Price changes
        prob_1h_ago = None
        one_hour_change = raw.get("oneHourPriceChange")
        if one_hour_change is not None:
            try:
                prob_1h_ago = probability - float(one_hour_change)
            except (ValueError, TypeError):
                pass

        tags = []
        if raw.get("competitive"):
            tags.append("competitive")
        if volume_usd >= 1_000_000:
            tags.append("high-volume")

        return PredictionSignal(
            market_id=f"poly_{raw.get('id', '')}",
            source=PredictionSource.POLYMARKET,
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
            raw_data={"slug": raw.get("slug", ""), "clob_token_ids": raw.get("clobTokenIds", [])},
        )

    @staticmethod
    def _extract_probability(raw: Dict[str, Any]) -> Optional[float]:
        """Extract YES probability from market data."""
        # outcomePrices is an array of string floats: ["0.72", "0.28"]
        prices = raw.get("outcomePrices")
        if isinstance(prices, list) and len(prices) >= 1:
            try:
                return float(prices[0])
            except (ValueError, TypeError):
                pass

        # Fallback to lastTradePrice
        last_price = raw.get("lastTradePrice")
        if last_price is not None:
            try:
                return float(last_price)
            except (ValueError, TypeError):
                pass

        # Fallback to bestBid/bestAsk midpoint
        best_bid = raw.get("bestBid")
        best_ask = raw.get("bestAsk")
        if best_bid is not None and best_ask is not None:
            try:
                return (float(best_bid) + float(best_ask)) / 2
            except (ValueError, TypeError):
                pass

        return None
