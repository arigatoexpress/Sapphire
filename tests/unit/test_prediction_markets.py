"""
Unit tests for Phase 8: Prediction Market Intelligence

Covers:
  - PredictionSignal dataclass (properties, serialization)
  - PredictionMarketFeed base class (history tracking, error handling)
  - PolymarketClient (market parsing, relevance classification, symbol extraction)
  - KalshiClient (market parsing, probability extraction, category inference)
  - PredictionAggregator (cross-source consensus, cognition context, forum summaries)
  - Telegram command handlers
"""

import asyncio
import os
import sys
import time
from datetime import datetime, timezone
from typing import Any, Dict, List
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../services/alpha-engine"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../services/alpha-engine/shared"))

import pytest

# ── Signal Dataclass ─────────────────────────────────────────────────

from src.feeds.prediction_signal import (
    PredictionMarketFeed,
    PredictionSignal,
    PredictionSource,
    SignalRelevance,
)


def _make_signal(**overrides) -> PredictionSignal:
    """Helper to create a PredictionSignal with sensible defaults."""
    defaults = {
        "market_id": "poly_test123",
        "source": PredictionSource.POLYMARKET,
        "question": "Will BTC exceed $100K by March 2026?",
        "probability": 0.72,
        "volume_usd": 500_000.0,
        "liquidity_usd": 120_000.0,
        "relevance": SignalRelevance.DIRECT,
        "symbols": ["BTC"],
    }
    defaults.update(overrides)
    return PredictionSignal(**defaults)


class TestPredictionSignal:
    def test_sentiment_strongly_bullish(self):
        sig = _make_signal(probability=0.80)
        assert sig.sentiment == "strongly_bullish"

    def test_sentiment_bullish(self):
        sig = _make_signal(probability=0.65)
        assert sig.sentiment == "bullish"

    def test_sentiment_neutral(self):
        sig = _make_signal(probability=0.50)
        assert sig.sentiment == "neutral"

    def test_sentiment_bearish(self):
        sig = _make_signal(probability=0.35)
        assert sig.sentiment == "bearish"

    def test_sentiment_strongly_bearish(self):
        sig = _make_signal(probability=0.20)
        assert sig.sentiment == "strongly_bearish"

    def test_momentum_with_history(self):
        sig = _make_signal(probability=0.72, probability_1h_ago=0.65)
        assert sig.momentum == pytest.approx(0.07, abs=0.001)

    def test_momentum_none_without_history(self):
        sig = _make_signal()
        assert sig.momentum is None

    def test_momentum_negative(self):
        sig = _make_signal(probability=0.60, probability_1h_ago=0.70)
        assert sig.momentum == pytest.approx(-0.10, abs=0.001)

    def test_is_high_conviction_true(self):
        sig = _make_signal(probability=0.75, volume_usd=100_000)
        assert sig.is_high_conviction is True

    def test_is_high_conviction_false_low_volume(self):
        sig = _make_signal(probability=0.75, volume_usd=10_000)
        assert sig.is_high_conviction is False

    def test_is_high_conviction_false_neutral_prob(self):
        sig = _make_signal(probability=0.50, volume_usd=100_000)
        assert sig.is_high_conviction is False

    def test_is_high_conviction_bearish(self):
        sig = _make_signal(probability=0.25, volume_usd=80_000)
        assert sig.is_high_conviction is True

    def test_to_dict_keys(self):
        sig = _make_signal()
        d = sig.to_dict()
        assert "market_id" in d
        assert "source" in d
        assert "probability" in d
        assert "sentiment" in d
        assert "is_high_conviction" in d
        assert d["source"] == "polymarket"

    def test_to_dict_roundtrip_values(self):
        sig = _make_signal(probability=0.8123, volume_usd=12345.67)
        d = sig.to_dict()
        assert d["probability"] == 0.8123
        assert d["volume_usd"] == 12345.67

    def test_context_string_format(self):
        sig = _make_signal(probability=0.72, volume_usd=500_000)
        ctx = sig.context_string()
        assert "[polymarket]" in ctx
        assert "72.0%" in ctx
        assert "500,000" in ctx

    def test_context_string_with_momentum(self):
        sig = _make_signal(probability=0.72, probability_1h_ago=0.65)
        ctx = sig.context_string()
        assert "↑" in ctx

    def test_context_string_negative_momentum(self):
        sig = _make_signal(probability=0.60, probability_1h_ago=0.70)
        ctx = sig.context_string()
        assert "↓" in ctx


# ── PredictionMarketFeed Base ────────────────────────────────────────

class TestPredictionMarketFeed:
    def test_get_signals_empty(self):
        class DummyFeed(PredictionMarketFeed):
            async def _fetch_markets(self, session):
                return []

        feed = DummyFeed(source=PredictionSource.POLYMARKET)
        assert feed.get_signals() == []

    def test_get_signals_filters_by_volume(self):
        class DummyFeed(PredictionMarketFeed):
            async def _fetch_markets(self, session):
                return []

        feed = DummyFeed(source=PredictionSource.POLYMARKET)
        sig1 = _make_signal(market_id="a", volume_usd=100)
        sig2 = _make_signal(market_id="b", volume_usd=1000)
        feed._signals = {"a": sig1, "b": sig2}

        assert len(feed.get_signals(min_volume=500)) == 1
        assert feed.get_signals(min_volume=500)[0].market_id == "b"

    def test_get_status(self):
        class DummyFeed(PredictionMarketFeed):
            async def _fetch_markets(self, session):
                return []

        feed = DummyFeed(source=PredictionSource.KALSHI)
        status = feed.get_status()
        assert status["source"] == "kalshi"
        assert status["market_count"] == 0
        assert status["running"] is False

    def test_update_history_tracks_probabilities(self):
        class DummyFeed(PredictionMarketFeed):
            async def _fetch_markets(self, session):
                return []

        feed = DummyFeed(source=PredictionSource.POLYMARKET)
        sig = _make_signal(market_id="test1", probability=0.50)
        feed._update_history(sig)
        assert len(feed._history["test1"]) == 1

        sig2 = _make_signal(market_id="test1", probability=0.55)
        feed._update_history(sig2)
        assert len(feed._history["test1"]) == 2

    def test_update_history_sets_1h_ago_when_enough_data(self):
        class DummyFeed(PredictionMarketFeed):
            async def _fetch_markets(self, session):
                return []

        feed = DummyFeed(source=PredictionSource.POLYMARKET)
        # Simulate 60+ data points
        feed._history["test1"] = [0.50] * 59
        sig = _make_signal(market_id="test1", probability=0.72)
        feed._update_history(sig)
        assert sig.probability_1h_ago == 0.50

    def test_update_history_caps_at_120(self):
        class DummyFeed(PredictionMarketFeed):
            async def _fetch_markets(self, session):
                return []

        feed = DummyFeed(source=PredictionSource.POLYMARKET)
        feed._history["test1"] = [0.50] * 120
        sig = _make_signal(market_id="test1", probability=0.72)
        feed._update_history(sig)
        assert len(feed._history["test1"]) == 120  # capped, oldest removed

    def test_log_error_dedup(self):
        class DummyFeed(PredictionMarketFeed):
            async def _fetch_markets(self, session):
                return []

        feed = DummyFeed(source=PredictionSource.POLYMARKET)
        # First call logs
        feed._log_error("test error")
        assert feed._last_error_msg == "test error"
        ts1 = feed._last_error_ts
        # Same message doesn't update timestamp (dedup)
        feed._log_error("test error")
        assert feed._last_error_ts == ts1
        # Different message does
        feed._log_error("different error")
        assert feed._last_error_msg == "different error"

    def test_poll_interval_minimum(self):
        class DummyFeed(PredictionMarketFeed):
            async def _fetch_markets(self, session):
                return []

        feed = DummyFeed(source=PredictionSource.POLYMARKET, poll_interval=1.0)
        assert feed.poll_interval == 10.0  # minimum enforced


# ── Polymarket Client ────────────────────────────────────────────────

from src.feeds.polymarket_client import (
    PolymarketClient,
    _classify_relevance,
    _extract_symbols,
)


class TestPolymarketRelevance:
    def test_direct_bitcoin(self):
        assert _classify_relevance("Will Bitcoin reach $100K?", "") == SignalRelevance.DIRECT

    def test_direct_ethereum(self):
        assert _classify_relevance("ETH price above $5000", "Crypto") == SignalRelevance.DIRECT

    def test_direct_solana(self):
        assert _classify_relevance("Solana ecosystem TVL above $10B", "") == SignalRelevance.DIRECT

    def test_direct_defi(self):
        assert _classify_relevance("DeFi total TVL above $200B", "") == SignalRelevance.DIRECT

    def test_direct_etf(self):
        assert _classify_relevance("Will Bitcoin ETF be approved?", "") == SignalRelevance.DIRECT

    def test_macro_fed_rate(self):
        assert _classify_relevance("Will there be a rate cut in June?", "") == SignalRelevance.MACRO

    def test_macro_cpi(self):
        assert _classify_relevance("CPI above 3% in February", "") == SignalRelevance.MACRO

    def test_macro_recession(self):
        assert _classify_relevance("US recession before 2027?", "") == SignalRelevance.MACRO

    def test_regulatory_sec(self):
        # "SEC crypto" matches DIRECT first (has "crypto" keyword), so use SEC-only
        assert _classify_relevance("SEC enforcement action against exchange", "") == SignalRelevance.REGULATORY

    def test_irrelevant(self):
        assert _classify_relevance("Will it rain tomorrow?", "Weather") is None

    def test_irrelevant_sports(self):
        assert _classify_relevance("Super Bowl winner 2026", "Sports") is None


class TestPolymarketSymbolExtraction:
    def test_extract_btc(self):
        assert "BTC" in _extract_symbols("Will Bitcoin reach $150K?")

    def test_extract_eth(self):
        assert "ETH" in _extract_symbols("Ethereum price prediction")

    def test_extract_sol(self):
        assert "SOL" in _extract_symbols("Solana ecosystem growth")

    def test_extract_multiple(self):
        syms = _extract_symbols("Bitcoin and Ethereum race to new highs")
        assert "BTC" in syms
        assert "ETH" in syms

    def test_default_to_btc(self):
        syms = _extract_symbols("Federal reserve rate cut")
        assert syms == ["BTC"]

    def test_extract_avax(self):
        assert "AVAX" in _extract_symbols("Avalanche mainnet upgrade")


class TestPolymarketClientParsing:
    def test_parse_market_crypto_direct(self):
        client = PolymarketClient(min_volume_usd=0)
        raw = {
            "id": "abc123",
            "question": "Will BTC exceed $100K by March 2026?",
            "category": "Crypto",
            "outcomePrices": ["0.72", "0.28"],
            "volumeNum": 500000,
            "liquidityNum": 120000,
            "slug": "btc-100k-march",
        }
        sig = client._parse_market(raw)
        assert sig is not None
        assert sig.probability == pytest.approx(0.72)
        assert sig.market_id == "poly_abc123"
        assert sig.source == PredictionSource.POLYMARKET
        assert "BTC" in sig.symbols

    def test_parse_market_irrelevant(self):
        client = PolymarketClient(min_volume_usd=0)
        raw = {
            "id": "xyz",
            "question": "Who wins the Oscar for Best Picture?",
            "category": "Entertainment",
            "outcomePrices": ["0.30", "0.70"],
            "volumeNum": 1000000,
            "liquidityNum": 50000,
        }
        sig = client._parse_market(raw)
        assert sig is None

    def test_parse_market_low_volume_filtered(self):
        client = PolymarketClient(min_volume_usd=50_000)
        raw = {
            "id": "low",
            "question": "Will Bitcoin reach $200K?",
            "category": "Crypto",
            "outcomePrices": ["0.10", "0.90"],
            "volumeNum": 1000,
            "liquidityNum": 500,
        }
        sig = client._parse_market(raw)
        assert sig is None

    def test_extract_probability_from_outcome_prices(self):
        assert PolymarketClient._extract_probability({"outcomePrices": ["0.65", "0.35"]}) == pytest.approx(0.65)

    def test_extract_probability_from_last_trade_price(self):
        assert PolymarketClient._extract_probability({"lastTradePrice": 0.82}) == pytest.approx(0.82)

    def test_extract_probability_from_bid_ask(self):
        result = PolymarketClient._extract_probability({"bestBid": 0.70, "bestAsk": 0.74})
        assert result == pytest.approx(0.72)

    def test_extract_probability_none(self):
        assert PolymarketClient._extract_probability({}) is None

    def test_parse_market_with_price_change(self):
        client = PolymarketClient(min_volume_usd=0)
        raw = {
            "id": "pc1",
            "question": "Bitcoin ETF approval by SEC?",
            "category": "Crypto",
            "outcomePrices": ["0.80", "0.20"],
            "volumeNum": 200000,
            "liquidityNum": 50000,
            "oneHourPriceChange": 0.05,
        }
        sig = client._parse_market(raw)
        assert sig is not None
        assert sig.probability_1h_ago == pytest.approx(0.75)

    def test_parse_market_end_date(self):
        client = PolymarketClient(min_volume_usd=0)
        raw = {
            "id": "ed1",
            "question": "Will Ethereum price hit $5000?",
            "category": "Crypto",
            "outcomePrices": ["0.40", "0.60"],
            "volumeNum": 100000,
            "liquidityNum": 30000,
            "endDate": "2026-06-30T00:00:00Z",
        }
        sig = client._parse_market(raw)
        assert sig is not None
        assert sig.end_date is not None
        assert sig.end_date.year == 2026

    @pytest.mark.asyncio
    async def test_fetch_markets_http_error(self):
        client = PolymarketClient()
        mock_session = MagicMock()
        mock_resp = AsyncMock()
        mock_resp.status = 500
        mock_resp.text = AsyncMock(return_value="Server Error")
        mock_session.get = MagicMock(return_value=AsyncContextManager(mock_resp))
        result = await client._fetch_markets(mock_session)
        assert result == []


# ── Kalshi Client ────────────────────────────────────────────────────

from src.feeds.kalshi_client import (
    KalshiClient,
    _classify_kalshi_relevance,
    _extract_symbols_kalshi,
)


class TestKalshiRelevance:
    def test_crypto_direct(self):
        assert _classify_kalshi_relevance("Bitcoin price above $100K", "Crypto") == SignalRelevance.DIRECT

    def test_macro_fed(self):
        assert _classify_kalshi_relevance("Fed rate cut in March", "Economics") == SignalRelevance.MACRO

    def test_macro_cpi(self):
        assert _classify_kalshi_relevance("CPI above 3%", "Inflation") == SignalRelevance.MACRO

    def test_irrelevant(self):
        assert _classify_kalshi_relevance("World Cup winner", "Sports") is None

    def test_relevant_via_category(self):
        assert _classify_kalshi_relevance("Some generic question", "Economics") == SignalRelevance.MACRO


class TestKalshiClientParsing:
    def test_parse_market_crypto(self):
        client = KalshiClient(min_volume=0)
        raw = {
            "ticker": "BTC-100K-MAR26",
            "event_ticker": "CRYPTO-BTC-100K",
            "title": "Bitcoin above $100K",
            "yes_bid": 72,
            "yes_ask": 74,
            "volume": 5000,
            "volume_24h": 200,
            "liquidity_dollars": "50000",
            "expiration_time": "2026-03-31T00:00:00Z",
        }
        sig = client._parse_market(raw)
        assert sig is not None
        assert sig.market_id == "kalshi_BTC-100K-MAR26"
        assert sig.probability == pytest.approx(0.73)
        assert sig.source == PredictionSource.KALSHI
        assert "BTC" in sig.symbols

    def test_parse_market_macro(self):
        client = KalshiClient(min_volume=0)
        raw = {
            "ticker": "FED-RATE-MAR26",
            "event_ticker": "FED-RATE",
            "title": "Fed rate cut in March 2026",
            "yes_bid": 55,
            "yes_ask": 60,
            "volume": 1000,
            "volume_24h": 50,
            "liquidity_dollars": "10000",
        }
        sig = client._parse_market(raw)
        assert sig is not None
        assert sig.relevance == SignalRelevance.MACRO

    def test_parse_market_irrelevant(self):
        client = KalshiClient(min_volume=0)
        raw = {
            "ticker": "WEATHER-RAIN-NYC",
            "event_ticker": "WEATHER",
            "title": "Rain in NYC tomorrow?",
            "yes_bid": 40,
            "yes_ask": 45,
            "volume": 500,
        }
        sig = client._parse_market(raw)
        assert sig is None

    def test_parse_market_low_volume(self):
        client = KalshiClient(min_volume=500)
        raw = {
            "ticker": "BTC-200K",
            "event_ticker": "CRYPTO-BTC",
            "title": "Bitcoin above $200K",
            "yes_bid": 10,
            "yes_ask": 15,
            "volume": 50,
        }
        sig = client._parse_market(raw)
        assert sig is None

    def test_extract_probability_midpoint(self):
        assert KalshiClient._extract_probability({"yes_bid": 70, "yes_ask": 80}) == pytest.approx(0.75)

    def test_extract_probability_last_price(self):
        assert KalshiClient._extract_probability({"last_price": 65}) == pytest.approx(0.65)

    def test_extract_probability_none(self):
        assert KalshiClient._extract_probability({}) is None

    def test_infer_category_crypto(self):
        assert KalshiClient._infer_category("CRYPTO-BTC-100K", "") == "Crypto"

    def test_infer_category_fed(self):
        assert KalshiClient._infer_category("FED-RATE-MAR26", "") == "Fed Funds Rate"

    def test_infer_category_inflation(self):
        assert KalshiClient._infer_category("CPI-FEB26", "") == "Inflation"

    def test_infer_category_economics(self):
        assert KalshiClient._infer_category("JOBS-NFP-MAR26", "") == "Economics"

    def test_infer_category_from_question_text(self):
        assert KalshiClient._infer_category("GENERIC-123", "Will bitcoin reach $100K?") == "Crypto"

    @pytest.mark.asyncio
    async def test_fetch_markets_http_error(self):
        client = KalshiClient()
        mock_session = MagicMock()
        mock_resp = AsyncMock()
        mock_resp.status = 429
        mock_resp.text = AsyncMock(return_value="Rate limited")
        mock_session.get = MagicMock(return_value=AsyncContextManager(mock_resp))
        result = await client._fetch_markets(mock_session)
        assert result == []


# ── Prediction Aggregator ────────────────────────────────────────────

from src.feeds.prediction_aggregator import PredictionAggregator


class TestPredictionAggregator:
    def _make_aggregator(self) -> PredictionAggregator:
        with patch.dict("os.environ", {"SAPPHIRE_PREDICTION_MARKET_ENABLED": "true"}):
            agg = PredictionAggregator()
        return agg

    def _inject_signals(self, agg: PredictionAggregator, signals: List[PredictionSignal]):
        for sig in signals:
            if sig.source == PredictionSource.POLYMARKET:
                agg._polymarket._signals[sig.market_id] = sig
            else:
                agg._kalshi._signals[sig.market_id] = sig

    def test_enabled_flag(self):
        with patch.dict("os.environ", {"SAPPHIRE_PREDICTION_MARKET_ENABLED": "true"}):
            agg = PredictionAggregator()
            assert agg.enabled is True

    def test_disabled_by_default(self):
        with patch.dict("os.environ", {}, clear=True):
            agg = PredictionAggregator()
            assert agg.enabled is False

    def test_get_all_signals_empty(self):
        agg = self._make_aggregator()
        assert agg.get_all_signals() == []

    def test_get_all_signals_combined(self):
        agg = self._make_aggregator()
        poly_sig = _make_signal(market_id="poly_1", source=PredictionSource.POLYMARKET, volume_usd=100_000)
        kalshi_sig = _make_signal(market_id="kalshi_1", source=PredictionSource.KALSHI, volume_usd=50_000)
        self._inject_signals(agg, [poly_sig, kalshi_sig])
        all_sigs = agg.get_all_signals()
        assert len(all_sigs) == 2
        # Sorted by volume desc
        assert all_sigs[0].market_id == "poly_1"

    def test_get_signals_for_symbol(self):
        agg = self._make_aggregator()
        btc_sig = _make_signal(market_id="poly_btc", symbols=["BTC"], volume_usd=200_000)
        eth_sig = _make_signal(market_id="poly_eth", symbols=["ETH"], volume_usd=100_000)
        self._inject_signals(agg, [btc_sig, eth_sig])
        assert len(agg.get_signals_for_symbol("BTC")) == 1
        assert len(agg.get_signals_for_symbol("ETH")) == 1
        assert len(agg.get_signals_for_symbol("SOL")) == 0

    def test_get_high_conviction_signals(self):
        agg = self._make_aggregator()
        high = _make_signal(market_id="high", probability=0.80, volume_usd=100_000)
        low = _make_signal(market_id="low", probability=0.55, volume_usd=100_000)
        self._inject_signals(agg, [high, low])
        hc = agg.get_high_conviction_signals()
        assert len(hc) == 1
        assert hc[0].market_id == "high"

    def test_get_symbol_sentiment_bullish(self):
        agg = self._make_aggregator()
        sig1 = _make_signal(market_id="p1", symbols=["BTC"], probability=0.75, volume_usd=500_000)
        sig2 = _make_signal(
            market_id="k1", source=PredictionSource.KALSHI,
            symbols=["BTC"], probability=0.70, volume_usd=200_000,
        )
        self._inject_signals(agg, [sig1, sig2])
        sent = agg.get_symbol_sentiment("BTC")
        assert sent["sentiment"] in ("bullish", "strongly_bullish")
        assert sent["signal_count"] == 2
        assert sent["confidence"] > 0

    def test_get_symbol_sentiment_no_signals(self):
        agg = self._make_aggregator()
        sent = agg.get_symbol_sentiment("SOL")
        assert sent["sentiment"] == "neutral"
        assert sent["confidence"] == 0.0
        assert sent["signal_count"] == 0

    def test_get_cognition_context_empty_when_disabled(self):
        with patch.dict("os.environ", {}, clear=True):
            agg = PredictionAggregator()
        assert agg.get_cognition_context("BTC") == ""

    def test_get_cognition_context_with_signals(self):
        agg = self._make_aggregator()
        sig = _make_signal(market_id="p1", symbols=["ETH"], probability=0.72, volume_usd=300_000)
        self._inject_signals(agg, [sig])
        ctx = agg.get_cognition_context("ETH")
        assert "Prediction Markets" in ctx
        assert "ETH" in ctx
        assert "Consensus" in ctx

    def test_get_macro_context(self):
        agg = self._make_aggregator()
        macro_sig = _make_signal(
            market_id="macro1", symbols=["BTC"],
            relevance=SignalRelevance.MACRO,
            question="Fed rate cut probability",
            probability=0.60, volume_usd=200_000,
        )
        self._inject_signals(agg, [macro_sig])
        ctx = agg.get_macro_context()
        assert "Macro" in ctx
        assert "Fed rate cut" in ctx

    def test_generate_forum_summary_none_on_cooldown(self):
        agg = self._make_aggregator()
        agg._last_forum_post_ts = time.time()  # Just posted
        sig = _make_signal(market_id="p1", volume_usd=100_000, probability=0.80)
        self._inject_signals(agg, [sig])
        assert agg.generate_forum_summary() is None

    def test_generate_forum_summary_with_signals(self):
        agg = self._make_aggregator()
        agg._last_forum_post_ts = 0  # Never posted
        sig = _make_signal(
            market_id="p1", volume_usd=100_000, probability=0.80,
            question="BTC above $100K?",
        )
        self._inject_signals(agg, [sig])
        summary = agg.generate_forum_summary()
        assert summary is not None
        assert summary["lane"] == "trading"
        assert summary["category"] == "market_analysis"
        assert summary["author"] == "SCOUT"
        assert "Prediction Market" in summary["title"]

    def test_generate_forum_summary_none_when_no_signals(self):
        agg = self._make_aggregator()
        agg._last_forum_post_ts = 0
        assert agg.generate_forum_summary() is None

    def test_format_telegram_status_disabled(self):
        with patch.dict("os.environ", {}, clear=True):
            agg = PredictionAggregator()
        msg = agg.format_telegram_status()
        assert "disabled" in msg.lower()

    def test_format_telegram_status_enabled(self):
        agg = self._make_aggregator()
        msg = agg.format_telegram_status()
        assert "Prediction Market" in msg

    def test_format_telegram_signals_for_symbol(self):
        agg = self._make_aggregator()
        sig = _make_signal(market_id="p1", symbols=["SOL"], probability=0.65, volume_usd=200_000)
        self._inject_signals(agg, [sig])
        msg = agg.format_telegram_signals(symbol="SOL")
        assert "SOL" in msg

    def test_format_telegram_signals_no_match(self):
        agg = self._make_aggregator()
        msg = agg.format_telegram_signals(symbol="DOGE")
        assert "No signals found" in msg

    def test_get_status_structure(self):
        agg = self._make_aggregator()
        status = agg.get_status()
        assert "enabled" in status
        assert "feeds" in status
        assert "total_signals" in status
        assert "high_conviction_signals" in status

    def test_symbol_sentiment_volume_weighted(self):
        agg = self._make_aggregator()
        # High-volume bullish + low-volume bearish → should still be bullish
        bull = _make_signal(market_id="bull", symbols=["BTC"], probability=0.80, volume_usd=1_000_000)
        bear = _make_signal(
            market_id="bear", source=PredictionSource.KALSHI,
            symbols=["BTC"], probability=0.30, volume_usd=10_000,
        )
        self._inject_signals(agg, [bull, bear])
        sent = agg.get_symbol_sentiment("BTC")
        # Weighted heavily toward the high-volume signal
        assert sent["weighted_probability"] > 0.70


# ── Telegram Handler Tests ───────────────────────────────────────────

from src.telegram_handlers import handle_prediction_commands


class TestTelegramPredictionHandlers:
    @pytest.mark.asyncio
    async def test_predictions_status(self):
        engine = MagicMock()
        engine.prediction_aggregator = MagicMock()
        engine.prediction_aggregator.format_telegram_status.return_value = "🔮 test status"
        engine.telegram = MagicMock()
        engine.telegram.send_message = AsyncMock()

        result = await handle_prediction_commands(engine, "", "PREDICTIONS", 0)
        assert result is True
        engine.telegram.send_message.assert_called_once()

    @pytest.mark.asyncio
    async def test_prediction_signal_with_symbol(self):
        engine = MagicMock()
        engine.prediction_aggregator = MagicMock()
        engine.prediction_aggregator.format_telegram_signals.return_value = "🔮 BTC signals"
        engine.telegram = MagicMock()
        engine.telegram.send_message = AsyncMock()

        result = await handle_prediction_commands(engine, "BTC", "PREDICTION", 0)
        assert result is True
        engine.prediction_aggregator.format_telegram_signals.assert_called_once_with(symbol="BTC")

    @pytest.mark.asyncio
    async def test_prediction_sentiment(self):
        engine = MagicMock()
        engine.prediction_aggregator = MagicMock()
        engine.prediction_aggregator.get_symbol_sentiment.return_value = {
            "symbol": "ETH",
            "sentiment": "bullish",
            "weighted_probability": 0.68,
            "confidence": 0.75,
            "signal_count": 3,
            "total_volume_usd": 500000,
            "sources": ["polymarket", "kalshi"],
        }
        engine.telegram = MagicMock()
        engine.telegram.send_message = AsyncMock()

        result = await handle_prediction_commands(engine, "ETH", "PREDICTION_SENTIMENT", 0)
        assert result is True

    @pytest.mark.asyncio
    async def test_prediction_high_conviction(self):
        engine = MagicMock()
        engine.prediction_aggregator = MagicMock()
        engine.prediction_aggregator.get_high_conviction_signals.return_value = []
        engine.telegram = MagicMock()
        engine.telegram.send_message = AsyncMock()

        result = await handle_prediction_commands(engine, "", "PM_HIGH", 0)
        assert result is True
        engine.telegram.send_message.assert_called_once()

    @pytest.mark.asyncio
    async def test_unknown_action_returns_false(self):
        engine = MagicMock()
        result = await handle_prediction_commands(engine, "", "UNKNOWN_ACTION", 0)
        assert result is False


# ── Alpha Scanner Integration ────────────────────────────────────────

from src.signals.alpha_scanner import AlphaSignalScanner


class TestAlphaScannerPredictionIntegration:
    def test_scanner_accepts_prediction_aggregator(self):
        agg = MagicMock()
        scanner = AlphaSignalScanner(
            market_data=MagicMock(),
            cognition=MagicMock(),
            memory=MagicMock(),
            strategy=MagicMock(),
            prediction_aggregator=agg,
        )
        assert scanner.prediction_aggregator is agg

    def test_scanner_prediction_aggregator_default_none(self):
        scanner = AlphaSignalScanner(
            market_data=MagicMock(),
            cognition=MagicMock(),
            memory=MagicMock(),
            strategy=MagicMock(),
        )
        assert scanner.prediction_aggregator is None


# ── Helpers ──────────────────────────────────────────────────────────

class AsyncContextManager:
    """Helper to mock aiohttp context managers."""

    def __init__(self, mock_response):
        self.mock_response = mock_response

    async def __aenter__(self):
        return self.mock_response

    async def __aexit__(self, *args):
        pass
