from __future__ import annotations

import math
import re
from datetime import datetime, timezone
from typing import Dict, Iterable, List, Sequence, Set

from app.models import ChatConfig, NewsItem, ScoredNews

POSITIVE_TERMS = {
    "approval",
    "approves",
    "adoption",
    "beat",
    "beats",
    "bullish",
    "growth",
    "inflow",
    "partnership",
    "rally",
    "surge",
    "upgrade",
    "record high",
    "launch",
}

NEGATIVE_TERMS = {
    "ban",
    "bearish",
    "crackdown",
    "downgrade",
    "exploit",
    "hack",
    "liquidation",
    "lawsuit",
    "miss",
    "outflow",
    "recession",
    "fraud",
    "outage",
    "defaults",
}

ASSET_ALIASES: Dict[str, Set[str]] = {
    "BTC": {"btc", "bitcoin"},
    "ETH": {"eth", "ethereum", "ether"},
    "SOL": {"sol", "solana"},
    "ARB": {"arb", "arbitrum"},
    "OP": {"op", "optimism"},
    "BNB": {"bnb", "binance coin"},
    "XRP": {"xrp", "ripple"},
    # Lighter-style symbols / common DeFi majors
    "WETH": {"weth", "eth", "ethereum", "ether"},
    "WBTC": {"wbtc", "btc", "bitcoin"},
    "LINK": {"link", "chainlink"},
    "UNI": {"uni", "uniswap"},
    # Aster Shield: tokenized equities + commodities
    "AAPL": {"aapl", "apple"},
    "TSLA": {"tsla", "tesla"},
    "NVDA": {"nvda", "nvidia"},
    "GOLD": {"gold", "xau"},
    "SILVER": {"silver", "xag"},
    # Common perp-formatted symbols (in case users paste them)
    "AAPLUSDT": {"aapl", "apple"},
    "TSLAUSDT": {"tsla", "tesla"},
    "NVDAUSDT": {"nvda", "nvidia"},
    "XAUUSDT": {"gold", "xau"},
    "XAGUSDT": {"silver", "xag"},
}


def _normalize_asset(asset: str) -> str:
    return re.sub(r"\s+", "", asset.strip().upper())


def _tokenize(text: str) -> str:
    return re.sub(r"\s+", " ", text.lower())


def _asset_terms(assets: Sequence[str]) -> Dict[str, Set[str]]:
    result: Dict[str, Set[str]] = {}
    for asset in assets:
        normalized = _normalize_asset(asset)
        if not normalized:
            continue
        aliases = set(ASSET_ALIASES.get(normalized, set()))
        aliases.add(normalized.lower())
        result[normalized] = aliases
    return result


def _find_term_hits(text: str, terms: Iterable[str]) -> List[str]:
    hits: List[str] = []
    for term in terms:
        escaped = re.escape(term.lower())
        pattern = rf"\b{escaped}\b"
        if re.search(pattern, text):
            hits.append(term)
    return hits


def _sentiment_score(text: str) -> int:
    score = 0
    for term in POSITIVE_TERMS:
        if term in text:
            score += 1
    for term in NEGATIVE_TERMS:
        if term in text:
            score -= 1
    return score


def _confidence(alpha_score: int) -> str:
    if alpha_score >= 75:
        return "high"
    if alpha_score >= 55:
        return "medium"
    return "low"


def _bias(sentiment: int) -> str:
    if sentiment >= 2:
        return "Bullish"
    if sentiment <= -2:
        return "Bearish"
    return "Two-sided"


def _age_hours(now: datetime, published_at: datetime) -> float:
    return max(0.0, (now - published_at).total_seconds() / 3600.0)


def score_news(
    items: Sequence[NewsItem],
    chat_config: ChatConfig,
    macro_keywords: Sequence[str],
    min_alpha_score: int,
    max_news_age_hours: int,
    now: datetime | None = None,
) -> List[ScoredNews]:
    now = now or datetime.now(tz=timezone.utc)
    assets = list(dict.fromkeys(chat_config.aster_assets + chat_config.lighter_assets))
    asset_map = _asset_terms(assets)
    keyword_terms = [k.strip().lower() for k in list(macro_keywords) + chat_config.extra_keywords if k.strip()]

    scored: List[ScoredNews] = []
    for item in items:
        text = _tokenize(f"{item.title} {item.summary}")
        item_age = _age_hours(now, item.published_at)
        if item_age > max_news_age_hours:
            continue

        asset_hits: List[str] = []
        for asset, aliases in asset_map.items():
            if _find_term_hits(text, aliases):
                asset_hits.append(asset)

        keyword_hits = _find_term_hits(text, keyword_terms)
        if not asset_hits and not keyword_hits:
            continue

        relevance = min(45, len(asset_hits) * 13 + len(keyword_hits) * 6)
        sentiment = _sentiment_score(text)
        sentiment_component = max(-18, min(18, sentiment * 4))
        recency_component = max(0, 22 - int(math.floor(item_age * 1.2)))
        reliability_component = int(round(item.source.reliability * 15))

        alpha_score = max(0, min(100, relevance + recency_component + reliability_component + sentiment_component))
        if alpha_score < min_alpha_score:
            continue

        details: List[str] = []
        if asset_hits:
            details.append(f"assets: {', '.join(asset_hits)}")
        if keyword_hits:
            details.append(f"macro: {', '.join(keyword_hits[:4])}")
        details.append(f"sentiment={sentiment}")

        scored.append(
            ScoredNews(
                item=item,
                alpha_score=alpha_score,
                sentiment=sentiment,
                bias=_bias(sentiment),
                confidence=_confidence(alpha_score),
                asset_hits=asset_hits,
                keyword_hits=keyword_hits,
                rationale="; ".join(details),
            )
        )

    scored.sort(key=lambda s: (s.alpha_score, s.item.published_at), reverse=True)
    return scored
