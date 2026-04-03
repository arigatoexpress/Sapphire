"""
Unit tests for Phase 8: Prediction Market Intelligence

Covers:
  - PredictionSignal dataclass (properties, serialization)
  - ArbitrageOpportunity dataclass (direction, serialization, context)
  - PredictionMarketFeed base class (history tracking, error handling)
  - PolymarketClient (market parsing, relevance classification, symbol extraction)
  - KalshiClient (market parsing, probability extraction, category inference)
  - PredictionAggregator (cross-source consensus, arbitrage detection, cognition context, forum summaries)
  - Telegram command handlers (including arbitrage)
  - Fuzzy market name normalization
"""

import os
import sys
import time
from typing import List
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../services/alpha-engine"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../services/alpha-engine/shared"))

import pytest
from src.feeds.prediction_aggregator import _normalize_market_name

# ── Signal Dataclass ─────────────────────────────────────────────────
from src.feeds.prediction_signal import (
    ArbitrageOpportunity,
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

    @pytest.mark.asyncio
    async def test_prediction_arbitrage_command(self):
        engine = MagicMock()
        engine.prediction_aggregator = MagicMock()
        engine.prediction_aggregator.format_telegram_arbitrage.return_value = "⚡ test arb"
        engine.telegram = MagicMock()
        engine.telegram.send_message = AsyncMock()

        result = await handle_prediction_commands(engine, "", "PM_ARBITRAGE", 0)
        assert result is True
        engine.prediction_aggregator.format_telegram_arbitrage.assert_called_once()

    @pytest.mark.asyncio
    async def test_prediction_arb_alias(self):
        engine = MagicMock()
        engine.prediction_aggregator = MagicMock()
        engine.prediction_aggregator.format_telegram_arbitrage.return_value = "⚡ arb"
        engine.telegram = MagicMock()
        engine.telegram.send_message = AsyncMock()

        result = await handle_prediction_commands(engine, "", "ARBITRAGE", 0)
        assert result is True


# ── Fuzzy Name Normalization ──────────────────────────────────────────


class TestFuzzyNameNormalization:
    """Tests for cross-venue market name matching — ported from TheOddsDesk."""

    def test_strips_noise_words(self):
        assert _normalize_market_name("Will the price go above 100") == _normalize_market_name("price above 100")

    def test_case_insensitive(self):
        assert _normalize_market_name("Bitcoin Price $100K") == _normalize_market_name("bitcoin price $100k")

    def test_strips_punctuation(self):
        assert _normalize_market_name("Bitcoin > $100,000?") == _normalize_market_name("Bitcoin 100000")

    def test_identical_events_different_phrasing(self):
        poly = "Will Bitcoin exceed $100K by end of year?"
        kalshi = "Bitcoin to exceed $100K by year end"
        assert _normalize_market_name(poly) == _normalize_market_name(kalshi)

    def test_different_events_stay_different(self):
        a = "Bitcoin above $100K"
        b = "Ethereum above $5K"
        assert _normalize_market_name(a) != _normalize_market_name(b)

    def test_empty_string(self):
        assert _normalize_market_name("") == ""

    def test_only_noise_words(self):
        assert _normalize_market_name("will the be at by to") == ""

    def test_fed_rate_variants(self):
        a = "Will the Fed cut rates in March 2026?"
        b = "Will Fed cut rates in March 2026?"
        assert _normalize_market_name(a) == _normalize_market_name(b)


# ── ArbitrageOpportunity Dataclass ────────────────────────────────────


class TestArbitrageOpportunity:
    def _make_arb(self, **overrides) -> ArbitrageOpportunity:
        sig_a = _make_signal(
            market_id="poly_btc100k",
            source=PredictionSource.POLYMARKET,
            probability=0.72,
            volume_usd=500_000,
        )
        sig_b = _make_signal(
            market_id="kalshi_btc100k",
            source=PredictionSource.KALSHI,
            probability=0.65,
            volume_usd=200_000,
        )
        defaults = {
            "id": "arb-poly_btc100k-kalshi_btc100k",
            "market_name": "Bitcoin above $100K by year end",
            "venue_a": "polymarket",
            "price_a": 0.72,
            "signal_a": sig_a,
            "venue_b": "kalshi",
            "price_b": 0.65,
            "signal_b": sig_b,
            "spread": 0.07,
            "spread_pct": 7.0,
            "confidence": 80.0,
            "symbols": ["BTC"],
        }
        defaults.update(overrides)
        return ArbitrageOpportunity(**defaults)

    def test_direction_a_higher(self):
        arb = self._make_arb(price_a=0.80, price_b=0.70)
        assert arb.direction == "polymarket > kalshi"

    def test_direction_b_higher(self):
        arb = self._make_arb(price_a=0.60, price_b=0.75)
        assert arb.direction == "kalshi > polymarket"

    def test_to_dict_has_required_keys(self):
        arb = self._make_arb()
        d = arb.to_dict()
        required_keys = {"id", "market_name", "venue_a", "price_a", "venue_b", "price_b",
                         "spread", "spread_pct", "confidence", "direction", "symbols", "timestamp"}
        assert required_keys == set(d.keys())

    def test_to_dict_values(self):
        arb = self._make_arb()
        d = arb.to_dict()
        assert d["spread_pct"] == 7.0
        assert d["venue_a"] == "polymarket"
        assert d["venue_b"] == "kalshi"

    def test_context_string_format(self):
        arb = self._make_arb()
        ctx = arb.context_string()
        assert "[ARB]" in ctx
        assert "polymarket=" in ctx
        assert "kalshi=" in ctx
        assert "spread=" in ctx
        assert "conf=" in ctx

    def test_spread_pct_rounding(self):
        arb = self._make_arb(spread=0.0333, spread_pct=3.33)
        d = arb.to_dict()
        assert d["spread_pct"] == 3.33


# ── Arbitrage Detection ──────────────────────────────────────────────


class TestArbitrageDetection:
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

    def test_no_signals_returns_empty(self):
        agg = self._make_aggregator()
        assert agg.find_arbitrage_opportunities() == []

    def test_single_venue_no_arb(self):
        agg = self._make_aggregator()
        self._inject_signals(agg, [
            _make_signal(market_id="poly_1", source=PredictionSource.POLYMARKET,
                         question="Bitcoin above 100K", probability=0.72, volume_usd=100_000),
            _make_signal(market_id="poly_2", source=PredictionSource.POLYMARKET,
                         question="Bitcoin above 100K", probability=0.70, volume_usd=80_000),
        ])
        # Same venue — should not detect arb
        arbs = agg.find_arbitrage_opportunities()
        assert len(arbs) == 0

    def test_cross_venue_spread_detected(self):
        agg = self._make_aggregator()
        self._inject_signals(agg, [
            _make_signal(market_id="poly_btc100k", source=PredictionSource.POLYMARKET,
                         question="Bitcoin above 100K", probability=0.72, volume_usd=200_000),
            _make_signal(market_id="kalshi_btc100k", source=PredictionSource.KALSHI,
                         question="Bitcoin above 100K", probability=0.60, volume_usd=100_000),
        ])
        arbs = agg.find_arbitrage_opportunities()
        assert len(arbs) == 1
        assert arbs[0].spread_pct == pytest.approx(12.0, abs=0.1)
        assert arbs[0].venue_a == "polymarket"
        assert arbs[0].venue_b == "kalshi"

    def test_below_min_spread_filtered(self):
        agg = self._make_aggregator()
        self._inject_signals(agg, [
            _make_signal(market_id="poly_1", source=PredictionSource.POLYMARKET,
                         question="Bitcoin above 100K", probability=0.72, volume_usd=200_000),
            _make_signal(market_id="kalshi_1", source=PredictionSource.KALSHI,
                         question="Bitcoin above 100K", probability=0.71, volume_usd=100_000),
        ])
        # 1% spread < default 2% threshold
        arbs = agg.find_arbitrage_opportunities()
        assert len(arbs) == 0

    def test_custom_min_spread(self):
        agg = self._make_aggregator()
        self._inject_signals(agg, [
            _make_signal(market_id="poly_1", source=PredictionSource.POLYMARKET,
                         question="Bitcoin above 100K", probability=0.72, volume_usd=200_000),
            _make_signal(market_id="kalshi_1", source=PredictionSource.KALSHI,
                         question="Bitcoin above 100K", probability=0.71, volume_usd=100_000),
        ])
        # Lower threshold to 0.5%
        arbs = agg.find_arbitrage_opportunities(min_spread=0.005)
        assert len(arbs) == 1

    def test_fuzzy_matching_across_venues(self):
        agg = self._make_aggregator()
        self._inject_signals(agg, [
            _make_signal(market_id="poly_btc", source=PredictionSource.POLYMARKET,
                         question="Will Bitcoin exceed $100K by end of year?",
                         probability=0.75, volume_usd=300_000),
            _make_signal(market_id="kalshi_btc", source=PredictionSource.KALSHI,
                         question="Bitcoin to exceed $100K by year end",
                         probability=0.62, volume_usd=150_000),
        ])
        arbs = agg.find_arbitrage_opportunities()
        assert len(arbs) == 1
        assert arbs[0].spread_pct == pytest.approx(13.0, abs=0.1)

    def test_different_markets_not_matched(self):
        agg = self._make_aggregator()
        self._inject_signals(agg, [
            _make_signal(market_id="poly_btc", source=PredictionSource.POLYMARKET,
                         question="Bitcoin above 100K", probability=0.75, volume_usd=300_000),
            _make_signal(market_id="kalshi_eth", source=PredictionSource.KALSHI,
                         question="Ethereum above 5K", probability=0.50, volume_usd=150_000),
        ])
        arbs = agg.find_arbitrage_opportunities()
        assert len(arbs) == 0

    def test_sorted_by_spread_descending(self):
        agg = self._make_aggregator()
        self._inject_signals(agg, [
            _make_signal(market_id="poly_btc", source=PredictionSource.POLYMARKET,
                         question="Bitcoin 100K", probability=0.72, volume_usd=200_000),
            _make_signal(market_id="kalshi_btc", source=PredictionSource.KALSHI,
                         question="Bitcoin 100K", probability=0.65, volume_usd=100_000),
            _make_signal(market_id="poly_eth", source=PredictionSource.POLYMARKET,
                         question="Ethereum 5K", probability=0.80, volume_usd=200_000),
            _make_signal(market_id="kalshi_eth", source=PredictionSource.KALSHI,
                         question="Ethereum 5K", probability=0.55, volume_usd=100_000),
        ])
        arbs = agg.find_arbitrage_opportunities()
        assert len(arbs) == 2
        assert arbs[0].spread >= arbs[1].spread

    def test_confidence_high_volume(self):
        agg = self._make_aggregator()
        self._inject_signals(agg, [
            _make_signal(market_id="poly_1", source=PredictionSource.POLYMARKET,
                         question="Bitcoin 100K", probability=0.80, volume_usd=800_000),
            _make_signal(market_id="kalshi_1", source=PredictionSource.KALSHI,
                         question="Bitcoin 100K", probability=0.65, volume_usd=600_000),
        ])
        arbs = agg.find_arbitrage_opportunities()
        assert len(arbs) == 1
        # Total volume > $1M → base 90 + bonuses
        assert arbs[0].confidence >= 90

    def test_confidence_low_volume(self):
        agg = self._make_aggregator()
        self._inject_signals(agg, [
            _make_signal(market_id="poly_1", source=PredictionSource.POLYMARKET,
                         question="Bitcoin 100K", probability=0.80, volume_usd=3_000),
            _make_signal(market_id="kalshi_1", source=PredictionSource.KALSHI,
                         question="Bitcoin 100K", probability=0.65, volume_usd=2_000),
        ])
        arbs = agg.find_arbitrage_opportunities()
        assert len(arbs) == 1
        # Low volume + min_vol penalty
        assert arbs[0].confidence <= 40

    def test_min_confidence_filter(self):
        agg = self._make_aggregator()
        self._inject_signals(agg, [
            _make_signal(market_id="poly_1", source=PredictionSource.POLYMARKET,
                         question="Bitcoin 100K", probability=0.80, volume_usd=3_000),
            _make_signal(market_id="kalshi_1", source=PredictionSource.KALSHI,
                         question="Bitcoin 100K", probability=0.60, volume_usd=2_000),
        ])
        arbs = agg.find_arbitrage_opportunities(min_confidence=50.0)
        assert len(arbs) == 0

    def test_symbols_merged_from_both_signals(self):
        agg = self._make_aggregator()
        self._inject_signals(agg, [
            _make_signal(market_id="poly_1", source=PredictionSource.POLYMARKET,
                         question="Bitcoin 100K", probability=0.80, volume_usd=200_000,
                         symbols=["BTC"]),
            _make_signal(market_id="kalshi_1", source=PredictionSource.KALSHI,
                         question="Bitcoin 100K", probability=0.65, volume_usd=100_000,
                         symbols=["BTC", "ETH"]),
        ])
        arbs = agg.find_arbitrage_opportunities()
        assert len(arbs) == 1
        assert "BTC" in arbs[0].symbols
        assert "ETH" in arbs[0].symbols

    def test_arb_id_format(self):
        agg = self._make_aggregator()
        self._inject_signals(agg, [
            _make_signal(market_id="poly_x", source=PredictionSource.POLYMARKET,
                         question="Bitcoin 100K", probability=0.80, volume_usd=200_000),
            _make_signal(market_id="kalshi_y", source=PredictionSource.KALSHI,
                         question="Bitcoin 100K", probability=0.65, volume_usd=100_000),
        ])
        arbs = agg.find_arbitrage_opportunities()
        assert arbs[0].id == "arb-poly_x-kalshi_y"


# ── Arbitrage Context & Formatting ───────────────────────────────────


class TestArbitrageFormatting:
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

    def test_get_arbitrage_context_empty(self):
        agg = self._make_aggregator()
        assert agg.get_arbitrage_context() == ""

    def test_get_arbitrage_context_disabled(self):
        with patch.dict("os.environ", {}, clear=True):
            agg = PredictionAggregator()
        assert agg.get_arbitrage_context() == ""

    def test_get_arbitrage_context_with_arbs(self):
        agg = self._make_aggregator()
        self._inject_signals(agg, [
            _make_signal(market_id="poly_1", source=PredictionSource.POLYMARKET,
                         question="Bitcoin 100K", probability=0.80, volume_usd=200_000),
            _make_signal(market_id="kalshi_1", source=PredictionSource.KALSHI,
                         question="Bitcoin 100K", probability=0.65, volume_usd=100_000),
        ])
        ctx = agg.get_arbitrage_context()
        assert "Cross-Venue Arbitrage" in ctx
        assert "[ARB]" in ctx

    def test_format_telegram_arbitrage_empty(self):
        agg = self._make_aggregator()
        msg = agg.format_telegram_arbitrage()
        assert "No arbitrage" in msg

    def test_format_telegram_arbitrage_disabled(self):
        with patch.dict("os.environ", {}, clear=True):
            agg = PredictionAggregator()
        msg = agg.format_telegram_arbitrage()
        assert "disabled" in msg

    def test_format_telegram_arbitrage_with_arbs(self):
        agg = self._make_aggregator()
        self._inject_signals(agg, [
            _make_signal(market_id="poly_1", source=PredictionSource.POLYMARKET,
                         question="Bitcoin 100K", probability=0.80, volume_usd=200_000),
            _make_signal(market_id="kalshi_1", source=PredictionSource.KALSHI,
                         question="Bitcoin 100K", probability=0.65, volume_usd=100_000),
        ])
        msg = agg.format_telegram_arbitrage()
        assert "Cross-Venue Arbitrage" in msg
        assert "Spread:" in msg

    def test_cognition_context_includes_arb(self):
        agg = self._make_aggregator()
        self._inject_signals(agg, [
            _make_signal(market_id="poly_1", source=PredictionSource.POLYMARKET,
                         question="Bitcoin 100K", probability=0.80, volume_usd=200_000,
                         symbols=["BTC"]),
            _make_signal(market_id="kalshi_1", source=PredictionSource.KALSHI,
                         question="Bitcoin 100K", probability=0.65, volume_usd=100_000,
                         symbols=["BTC"]),
        ])
        ctx = agg.get_cognition_context("BTC")
        assert "Arbitrage" in ctx
        assert "[ARB]" in ctx

    def test_forum_summary_includes_arb(self):
        agg = self._make_aggregator()
        agg._last_forum_post_ts = 0  # Allow posting
        self._inject_signals(agg, [
            _make_signal(market_id="poly_1", source=PredictionSource.POLYMARKET,
                         question="Bitcoin 100K", probability=0.80, volume_usd=200_000,
                         symbols=["BTC"]),
            _make_signal(market_id="kalshi_1", source=PredictionSource.KALSHI,
                         question="Bitcoin 100K", probability=0.65, volume_usd=100_000,
                         symbols=["BTC"]),
        ])
        summary = agg.generate_forum_summary()
        assert summary is not None
        assert "Cross-Venue Arbitrage" in summary["body"]

    def test_status_includes_arb_count(self):
        agg = self._make_aggregator()
        self._inject_signals(agg, [
            _make_signal(market_id="poly_1", source=PredictionSource.POLYMARKET,
                         question="Bitcoin 100K", probability=0.80, volume_usd=200_000),
            _make_signal(market_id="kalshi_1", source=PredictionSource.KALSHI,
                         question="Bitcoin 100K", probability=0.65, volume_usd=100_000),
        ])
        status = agg.get_status()
        assert "arbitrage_opportunities" in status
        assert status["arbitrage_opportunities"] >= 1


# ── Kalshi API Key ───────────────────────────────────────────────────


class TestKalshiApiKey:
    def test_api_key_from_constructor(self):
        client = KalshiClient(api_key="test-key-123")
        assert client._api_key == "test-key-123"

    def test_api_key_from_env(self):
        with patch.dict("os.environ", {"KALSHI_API_KEY": "env-key-456"}):
            client = KalshiClient()
            assert client._api_key == "env-key-456"

    def test_api_key_empty_default(self):
        with patch.dict("os.environ", {}, clear=True):
            client = KalshiClient()
            assert client._api_key == ""


# ── Confidence Scoring ───────────────────────────────────────────────


class TestArbitrageConfidence:
    def test_high_volume_high_confidence(self):
        sig_a = _make_signal(volume_usd=800_000, liquidity_usd=100_000)
        sig_b = _make_signal(volume_usd=600_000, liquidity_usd=80_000)
        conf = PredictionAggregator._calculate_arb_confidence(sig_a, sig_b)
        assert conf >= 90  # Total >$1M

    def test_medium_volume(self):
        sig_a = _make_signal(volume_usd=300_000, liquidity_usd=50_000)
        sig_b = _make_signal(volume_usd=250_000, liquidity_usd=40_000)
        conf = PredictionAggregator._calculate_arb_confidence(sig_a, sig_b)
        assert 75 <= conf <= 95

    def test_low_volume_low_confidence(self):
        sig_a = _make_signal(volume_usd=3_000, liquidity_usd=500)
        sig_b = _make_signal(volume_usd=2_000, liquidity_usd=300)
        conf = PredictionAggregator._calculate_arb_confidence(sig_a, sig_b)
        assert conf <= 40

    def test_one_sided_volume_penalty(self):
        # One-sided: high total but one venue is thin
        sig_a = _make_signal(volume_usd=800_000, liquidity_usd=100_000)
        sig_b = _make_signal(volume_usd=2_000, liquidity_usd=500)
        conf = PredictionAggregator._calculate_arb_confidence(sig_a, sig_b)
        # Balanced: same bracket but both sides are strong
        sig_c = _make_signal(volume_usd=400_000, liquidity_usd=80_000)
        sig_d = _make_signal(volume_usd=400_000, liquidity_usd=80_000)
        conf_balanced = PredictionAggregator._calculate_arb_confidence(sig_c, sig_d)
        assert conf_balanced > conf  # Balanced volume is higher confidence

    def test_confidence_capped_at_100(self):
        sig_a = _make_signal(volume_usd=5_000_000, liquidity_usd=1_000_000)
        sig_b = _make_signal(volume_usd=5_000_000, liquidity_usd=1_000_000)
        conf = PredictionAggregator._calculate_arb_confidence(sig_a, sig_b)
        assert conf == 100.0

    def test_confidence_floor_at_zero(self):
        sig_a = _make_signal(volume_usd=0, liquidity_usd=0)
        sig_b = _make_signal(volume_usd=0, liquidity_usd=0)
        conf = PredictionAggregator._calculate_arb_confidence(sig_a, sig_b)
        assert conf >= 0


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


# ── Swarm PM Integration ────────────────────────────────────────────

from src.collaboration.reputation import BotReputationService
from src.collaboration.swarm import SwarmAggregator
from src.feeds.prediction_accuracy import PredictionAccuracyTracker


class TestSwarmPMIntegration:
    """Test prediction market sentiment injection into swarm consensus."""

    def _make_swarm_with_pm(self, sentiment_result=None):
        """Create a SwarmAggregator with a mocked prediction aggregator."""
        rep = BotReputationService()
        pm_agg = MagicMock()
        pm_agg.enabled = True
        if sentiment_result:
            pm_agg.get_symbol_sentiment.return_value = sentiment_result
        swarm = SwarmAggregator(reputation=rep, prediction_aggregator=pm_agg)
        return swarm, rep, pm_agg

    def test_swarm_pm_aggregator_stored(self):
        rep = BotReputationService()
        pm_agg = MagicMock()
        swarm = SwarmAggregator(reputation=rep, prediction_aggregator=pm_agg)
        assert swarm._prediction_aggregator is pm_agg

    def test_swarm_pm_aggregator_none_by_default(self):
        rep = BotReputationService()
        swarm = SwarmAggregator(reputation=rep)
        assert swarm._prediction_aggregator is None

    def test_pm_adjustment_bullish(self):
        swarm, _, pm_agg = self._make_swarm_with_pm({
            "sentiment": "bullish",
            "confidence": 0.8,
            "weighted_probability": 0.65,
            "signal_count": 3,
        })
        adj = swarm._get_pm_adjustment("BTC")
        assert adj is not None
        assert adj["direction"] == "LONG"
        assert adj["long_boost"] > 0
        assert adj["short_boost"] == 0.0

    def test_pm_adjustment_strongly_bullish(self):
        swarm, _, pm_agg = self._make_swarm_with_pm({
            "sentiment": "strongly_bullish",
            "confidence": 0.9,
            "weighted_probability": 0.85,
            "signal_count": 5,
        })
        adj = swarm._get_pm_adjustment("BTC")
        assert adj["direction"] == "LONG"
        # strength = (0.85 - 0.5) * 2 = 0.7, boost = 0.25 * 0.7 * 0.9 = 0.1575
        assert adj["long_boost"] == pytest.approx(0.1575, abs=0.01)

    def test_pm_adjustment_bearish(self):
        swarm, _, pm_agg = self._make_swarm_with_pm({
            "sentiment": "bearish",
            "confidence": 0.7,
            "weighted_probability": 0.35,
            "signal_count": 2,
        })
        adj = swarm._get_pm_adjustment("ETH")
        assert adj is not None
        assert adj["direction"] == "SHORT"
        assert adj["short_boost"] > 0
        assert adj["long_boost"] == 0.0

    def test_pm_adjustment_strongly_bearish(self):
        swarm, _, pm_agg = self._make_swarm_with_pm({
            "sentiment": "strongly_bearish",
            "confidence": 0.85,
            "weighted_probability": 0.15,
            "signal_count": 4,
        })
        adj = swarm._get_pm_adjustment("SOL")
        assert adj["direction"] == "SHORT"
        # strength = (0.5 - 0.15) * 2 = 0.7, boost = 0.25 * 0.7 * 0.85 = 0.14875
        assert adj["short_boost"] == pytest.approx(0.1488, abs=0.01)

    def test_pm_adjustment_neutral_returns_none(self):
        swarm, _, pm_agg = self._make_swarm_with_pm({
            "sentiment": "neutral",
            "confidence": 0.5,
            "weighted_probability": 0.50,
            "signal_count": 2,
        })
        adj = swarm._get_pm_adjustment("BTC")
        assert adj is None

    def test_pm_adjustment_no_signals_returns_none(self):
        swarm, _, pm_agg = self._make_swarm_with_pm({
            "sentiment": "neutral",
            "confidence": 0.0,
            "weighted_probability": 0.5,
            "signal_count": 0,
        })
        adj = swarm._get_pm_adjustment("BTC")
        assert adj is None

    def test_pm_adjustment_disabled_aggregator(self):
        rep = BotReputationService()
        pm_agg = MagicMock()
        pm_agg.enabled = False
        swarm = SwarmAggregator(reputation=rep, prediction_aggregator=pm_agg)
        adj = swarm._get_pm_adjustment("BTC")
        assert adj is None

    def test_pm_adjustment_no_aggregator(self):
        rep = BotReputationService()
        swarm = SwarmAggregator(reputation=rep)
        adj = swarm._get_pm_adjustment("BTC")
        assert adj is None

    def test_pm_adjustment_exception_returns_none(self):
        swarm, _, pm_agg = self._make_swarm_with_pm()
        pm_agg.get_symbol_sentiment.side_effect = RuntimeError("API down")
        adj = swarm._get_pm_adjustment("BTC")
        assert adj is None

    def test_aggregate_includes_pm_boost_long(self):
        swarm, rep, pm_agg = self._make_swarm_with_pm({
            "sentiment": "bullish",
            "confidence": 0.8,
            "weighted_probability": 0.65,
            "signal_count": 3,
        })
        # Submit two LONG ideas
        swarm.submit_idea("BOT_A", "BTC", "LONG", confidence=0.7)
        swarm.submit_idea("BOT_B", "BTC", "LONG", confidence=0.6)

        result = swarm.aggregate("BTC")
        assert result["ok"] is True
        assert result["pm_adjustment"] is not None
        assert result["pm_adjustment"]["direction"] == "LONG"
        # PM virtual voter should be in contributors
        pm_voters = [c for c in result["contributors"] if c["bot_id"] == "__PREDICTION_MARKET__"]
        assert len(pm_voters) == 1
        assert pm_voters[0]["direction"] == "LONG"

    def test_aggregate_includes_pm_boost_short(self):
        swarm, rep, pm_agg = self._make_swarm_with_pm({
            "sentiment": "bearish",
            "confidence": 0.75,
            "weighted_probability": 0.30,
            "signal_count": 2,
        })
        swarm.submit_idea("BOT_A", "ETH", "SHORT", confidence=0.8)

        result = swarm.aggregate("ETH")
        assert result["ok"] is True
        assert result["pm_adjustment"] is not None
        assert result["pm_adjustment"]["direction"] == "SHORT"
        assert result["weighted_short"] > 0

    def test_aggregate_no_pm_when_neutral(self):
        swarm, rep, pm_agg = self._make_swarm_with_pm({
            "sentiment": "neutral",
            "confidence": 0.5,
            "weighted_probability": 0.50,
            "signal_count": 2,
        })
        swarm.submit_idea("BOT_A", "BTC", "LONG", confidence=0.6)
        result = swarm.aggregate("BTC")
        assert result["pm_adjustment"] is None

    def test_aggregate_pm_weight_constant(self):
        assert SwarmAggregator.PM_WEIGHT == 0.25


# ── Prediction Accuracy Tracker ─────────────────────────────────────

class TestPredictionAccuracyTracker:
    """Test prediction accuracy tracking and Brier score calculation."""

    def test_record_signal_first_time(self):
        tracker = PredictionAccuracyTracker(max_snapshots=100)
        sig = _make_signal(market_id="test1")
        tracker.record_signal(sig)
        assert "test1" in tracker._snapshots
        snap = tracker._snapshots["test1"]
        assert snap.probability == 0.72
        assert snap.resolved is False

    def test_record_signal_deduplication(self):
        tracker = PredictionAccuracyTracker(max_snapshots=100)
        sig = _make_signal(market_id="test1")
        tracker.record_signal(sig)
        # Record again — should not overwrite
        sig2 = _make_signal(market_id="test1", probability=0.99)
        tracker.record_signal(sig2)
        assert tracker._snapshots["test1"].probability == 0.72  # Original value

    def test_record_outcome_correct_yes(self):
        tracker = PredictionAccuracyTracker()
        sig = _make_signal(market_id="test_yes", probability=0.80)
        tracker.record_signal(sig)
        result = tracker.record_outcome("test_yes", outcome=True)
        assert result is not None
        assert result["correct"] is True
        # Brier: (0.8 - 1.0)^2 = 0.04
        assert result["brier_score"] == pytest.approx(0.04, abs=0.001)

    def test_record_outcome_correct_no(self):
        tracker = PredictionAccuracyTracker()
        sig = _make_signal(market_id="test_no", probability=0.30)
        tracker.record_signal(sig)
        result = tracker.record_outcome("test_no", outcome=False)
        assert result is not None
        assert result["correct"] is True
        # Brier: (0.3 - 0.0)^2 = 0.09
        assert result["brier_score"] == pytest.approx(0.09, abs=0.001)

    def test_record_outcome_wrong(self):
        tracker = PredictionAccuracyTracker()
        sig = _make_signal(market_id="test_wrong", probability=0.80)
        tracker.record_signal(sig)
        result = tracker.record_outcome("test_wrong", outcome=False)
        assert result["correct"] is False
        # Brier: (0.8 - 0.0)^2 = 0.64
        assert result["brier_score"] == pytest.approx(0.64, abs=0.001)

    def test_record_outcome_unknown_market(self):
        tracker = PredictionAccuracyTracker()
        result = tracker.record_outcome("nonexistent", outcome=True)
        assert result is None

    def test_record_outcome_already_resolved(self):
        tracker = PredictionAccuracyTracker()
        sig = _make_signal(market_id="test_dup")
        tracker.record_signal(sig)
        tracker.record_outcome("test_dup", outcome=True)
        result2 = tracker.record_outcome("test_dup", outcome=False)
        assert result2 is None  # Cannot re-resolve

    def test_accuracy_stats_empty(self):
        tracker = PredictionAccuracyTracker()
        stats = tracker.get_accuracy_stats()
        assert stats["total_tracked"] == 0
        assert stats["total_resolved"] == 0
        assert stats["overall_accuracy_pct"] == 0.0
        assert stats["overall_brier"] == 0.0

    def test_accuracy_stats_with_outcomes(self):
        tracker = PredictionAccuracyTracker()
        # Add 3 signals, resolve 2
        for i, (prob, outcome) in enumerate([(0.80, True), (0.30, False), (0.60, None)]):
            sig = _make_signal(market_id=f"s{i}", probability=prob)
            tracker.record_signal(sig)
            if outcome is not None:
                tracker.record_outcome(f"s{i}", outcome=outcome)

        stats = tracker.get_accuracy_stats()
        assert stats["total_tracked"] == 3
        assert stats["total_resolved"] == 2
        assert stats["total_pending"] == 1
        assert stats["overall_accuracy_pct"] == 100.0  # Both correct

    def test_accuracy_stats_per_source(self):
        tracker = PredictionAccuracyTracker()
        sig_poly = _make_signal(market_id="poly1", source=PredictionSource.POLYMARKET, probability=0.80)
        sig_kalshi = _make_signal(market_id="kalshi1", source=PredictionSource.KALSHI, probability=0.30)
        tracker.record_signal(sig_poly)
        tracker.record_signal(sig_kalshi)
        tracker.record_outcome("poly1", outcome=True)
        tracker.record_outcome("kalshi1", outcome=False)

        stats = tracker.get_accuracy_stats()
        assert "polymarket" in stats["by_source"]
        assert "kalshi" in stats["by_source"]
        assert stats["by_source"]["polymarket"]["correct"] == 1
        assert stats["by_source"]["kalshi"]["correct"] == 1

    def test_accuracy_high_conviction_tracking(self):
        tracker = PredictionAccuracyTracker()
        # High conviction: volume >= 50K and prob >= 0.70
        hc_sig = _make_signal(market_id="hc1", probability=0.85, volume_usd=100_000)
        lc_sig = _make_signal(market_id="lc1", probability=0.55, volume_usd=5_000)
        tracker.record_signal(hc_sig)
        tracker.record_signal(lc_sig)
        tracker.record_outcome("hc1", outcome=True)
        tracker.record_outcome("lc1", outcome=True)

        stats = tracker.get_accuracy_stats()
        assert stats["high_conviction_resolved"] == 1
        assert stats["high_conviction_accuracy_pct"] == 100.0

    def test_pending_markets(self):
        tracker = PredictionAccuracyTracker()
        sig = _make_signal(market_id="pending1")
        tracker.record_signal(sig)
        pending = tracker.get_pending_markets()
        assert len(pending) == 1
        assert pending[0]["market_id"] == "pending1"

    def test_pending_excludes_resolved(self):
        tracker = PredictionAccuracyTracker()
        sig = _make_signal(market_id="resolved1")
        tracker.record_signal(sig)
        tracker.record_outcome("resolved1", outcome=True)
        pending = tracker.get_pending_markets()
        assert len(pending) == 0

    def test_eviction_at_capacity(self):
        tracker = PredictionAccuracyTracker(max_snapshots=3)
        for i in range(4):
            sig = _make_signal(market_id=f"evict{i}", probability=0.5 + i * 0.1)
            tracker.record_signal(sig)
            # Resolve the first one so it gets evicted first
            if i == 0:
                tracker.record_outcome(f"evict{i}", outcome=True)

        # Should have evicted one to stay at max
        assert len(tracker._snapshots) <= 3

    def test_eviction_prefers_resolved(self):
        tracker = PredictionAccuracyTracker(max_snapshots=2)
        sig1 = _make_signal(market_id="keep_pending")
        sig2 = _make_signal(market_id="remove_resolved")
        tracker.record_signal(sig1)
        tracker.record_signal(sig2)
        tracker.record_outcome("remove_resolved", outcome=True)
        # Now add a third — should evict the resolved one
        sig3 = _make_signal(market_id="new_one")
        tracker.record_signal(sig3)
        assert "keep_pending" in tracker._snapshots
        assert "new_one" in tracker._snapshots

    def test_brier_score_perfect_yes(self):
        """prob=1.0, outcome=True → Brier=0.0 (perfect)."""
        tracker = PredictionAccuracyTracker()
        sig = _make_signal(market_id="perfect", probability=1.0)
        tracker.record_signal(sig)
        result = tracker.record_outcome("perfect", outcome=True)
        assert result["brier_score"] == 0.0

    def test_brier_score_perfect_no(self):
        """prob=0.0, outcome=False → Brier=0.0 (perfect)."""
        tracker = PredictionAccuracyTracker()
        sig = _make_signal(market_id="perfect_no", probability=0.0)
        tracker.record_signal(sig)
        result = tracker.record_outcome("perfect_no", outcome=False)
        assert result["brier_score"] == 0.0

    def test_brier_score_worst_case(self):
        """prob=1.0, outcome=False → Brier=1.0 (worst)."""
        tracker = PredictionAccuracyTracker()
        sig = _make_signal(market_id="worst", probability=1.0)
        tracker.record_signal(sig)
        result = tracker.record_outcome("worst", outcome=False)
        assert result["brier_score"] == 1.0

    def test_format_telegram_empty(self):
        tracker = PredictionAccuracyTracker()
        text = tracker.format_telegram_accuracy()
        assert "Prediction Accuracy" in text
        assert "No resolved predictions" in text

    def test_format_telegram_with_data(self):
        tracker = PredictionAccuracyTracker()
        sig = _make_signal(market_id="fmt1", probability=0.75)
        tracker.record_signal(sig)
        tracker.record_outcome("fmt1", outcome=True)
        text = tracker.format_telegram_accuracy()
        assert "Resolved:" in text
        assert "accuracy" in text.lower()


# ── Aggregator Accuracy Integration ─────────────────────────────────

class TestAggregatorAccuracyIntegration:
    """Test accuracy tracker integration in PredictionAggregator."""

    def test_aggregator_has_accuracy_tracker(self):
        from src.feeds.prediction_aggregator import PredictionAggregator
        agg = PredictionAggregator()
        assert agg._accuracy_tracker is not None
        assert isinstance(agg._accuracy_tracker, PredictionAccuracyTracker)

    def test_aggregator_accuracy_tracker_property(self):
        from src.feeds.prediction_aggregator import PredictionAggregator
        agg = PredictionAggregator()
        assert agg.accuracy_tracker is agg._accuracy_tracker

    def test_record_signals_for_accuracy(self):
        from src.feeds.prediction_aggregator import PredictionAggregator
        agg = PredictionAggregator()
        # Mock the feeds to return signals
        sig1 = _make_signal(market_id="rec1")
        sig2 = _make_signal(market_id="rec2")
        agg._polymarket.get_signals = MagicMock(return_value=[sig1])
        agg._kalshi.get_signals = MagicMock(return_value=[sig2])
        recorded = agg.record_signals_for_accuracy()
        assert recorded == 2
        assert "rec1" in agg._accuracy_tracker._snapshots
        assert "rec2" in agg._accuracy_tracker._snapshots

    def test_record_signals_dedup(self):
        from src.feeds.prediction_aggregator import PredictionAggregator
        agg = PredictionAggregator()
        sig1 = _make_signal(market_id="dup1")
        agg._polymarket.get_signals = MagicMock(return_value=[sig1])
        agg._kalshi.get_signals = MagicMock(return_value=[])
        agg.record_signals_for_accuracy()
        count2 = agg.record_signals_for_accuracy()
        assert count2 == 0  # Already recorded

    def test_format_telegram_accuracy(self):
        from src.feeds.prediction_aggregator import PredictionAggregator
        agg = PredictionAggregator()
        text = agg.format_telegram_accuracy()
        assert "Prediction Accuracy" in text

    def test_status_includes_accuracy(self):
        from src.feeds.prediction_aggregator import PredictionAggregator
        agg = PredictionAggregator()
        status = agg.get_status()
        assert "accuracy_tracked" in status
        assert "accuracy_resolved" in status

    def test_format_telegram_status_includes_accuracy(self):
        from src.feeds.prediction_aggregator import PredictionAggregator
        with patch.dict(os.environ, {"SAPPHIRE_PREDICTION_MARKET_ENABLED": "true"}):
            agg = PredictionAggregator()
        text = agg.format_telegram_status()
        assert "Accuracy tracked:" in text

    def test_dashboard_data_structure(self):
        from src.feeds.prediction_aggregator import PredictionAggregator
        agg = PredictionAggregator()
        agg._polymarket.get_signals = MagicMock(return_value=[])
        agg._kalshi.get_signals = MagicMock(return_value=[])
        data = agg.get_prediction_dashboard_data()
        assert "status" in data
        assert "accuracy" in data
        assert "signals" in data
        assert "high_conviction" in data
        assert "arbitrage" in data
        assert "sentiments" in data
        assert "pending_accuracy" in data

    def test_dashboard_data_with_signals(self):
        from src.feeds.prediction_aggregator import PredictionAggregator
        agg = PredictionAggregator()
        sig = _make_signal(market_id="dash1", volume_usd=100_000)
        agg._polymarket.get_signals = MagicMock(return_value=[sig])
        agg._kalshi.get_signals = MagicMock(return_value=[])
        data = agg.get_prediction_dashboard_data()
        assert len(data["signals"]) == 1
        assert data["signals"][0]["market_id"] == "dash1"
        assert "BTC" in data["sentiments"]


# ── Telegram Accuracy Command ───────────────────────────────────────

# ── Whale Activity & Manipulation Detection ─────────────────────────

class TestWhaleActivityDetection:
    """Test whale activity and volume spike detection on PredictionSignal."""

    def test_volume_change_calculated(self):
        sig = _make_signal(volume_usd=300_000, volume_1h_ago=100_000)
        assert sig.volume_change == pytest.approx(3.0)

    def test_volume_change_none_without_history(self):
        sig = _make_signal(volume_usd=300_000)
        assert sig.volume_change is None

    def test_volume_change_none_when_zero(self):
        sig = _make_signal(volume_usd=300_000, volume_1h_ago=0)
        assert sig.volume_change is None

    def test_is_volume_spike_true(self):
        sig = _make_signal(volume_usd=400_000, volume_1h_ago=100_000)
        assert sig.is_volume_spike is True  # 4x

    def test_is_volume_spike_false(self):
        sig = _make_signal(volume_usd=200_000, volume_1h_ago=100_000)
        assert sig.is_volume_spike is False  # 2x < 3x threshold

    def test_is_volume_spike_exactly_3x(self):
        sig = _make_signal(volume_usd=300_000, volume_1h_ago=100_000)
        assert sig.is_volume_spike is True

    def test_whale_activity_big_volume_big_move(self):
        sig = _make_signal(
            probability=0.80, probability_1h_ago=0.70,
            volume_usd=300_000, volume_1h_ago=100_000,
        )
        assert sig.is_whale_activity is True  # 3x vol, 10% move

    def test_whale_activity_big_volume_small_move(self):
        sig = _make_signal(
            probability=0.72, probability_1h_ago=0.70,
            volume_usd=300_000, volume_1h_ago=100_000,
        )
        assert sig.is_whale_activity is False  # 2% move < 5% threshold

    def test_whale_activity_small_volume(self):
        sig = _make_signal(
            probability=0.80, probability_1h_ago=0.70,
            volume_usd=150_000, volume_1h_ago=100_000,
        )
        assert sig.is_whale_activity is False  # 1.5x vol < 2x threshold

    def test_whale_activity_no_history(self):
        sig = _make_signal(probability=0.80)
        assert sig.is_whale_activity is False


class TestManipulationRisk:
    """Test manipulation risk classification."""

    def test_clean_market(self):
        sig = _make_signal(
            probability=0.72, probability_1h_ago=0.70,
            volume_usd=200_000, volume_1h_ago=150_000,
            liquidity_usd=120_000,
        )
        assert sig.manipulation_risk == "clean"

    def test_wash_trading_volume_spike_no_price_move(self):
        sig = _make_signal(
            probability=0.72, probability_1h_ago=0.72,
            volume_usd=400_000, volume_1h_ago=100_000,
            liquidity_usd=120_000,
        )
        assert sig.manipulation_risk == "wash_trading"

    def test_wash_trading_tiny_move(self):
        sig = _make_signal(
            probability=0.725, probability_1h_ago=0.72,
            volume_usd=500_000, volume_1h_ago=100_000,
            liquidity_usd=120_000,
        )
        assert sig.manipulation_risk == "wash_trading"  # 0.5% move < 1% threshold

    def test_low_liquidity_pump(self):
        sig = _make_signal(
            volume_usd=500_000,
            liquidity_usd=10_000,  # vol/liq = 50x
        )
        assert sig.manipulation_risk == "low_liquidity_pump"

    def test_low_liquidity_not_triggered(self):
        sig = _make_signal(
            volume_usd=500_000,
            liquidity_usd=120_000,  # vol/liq = ~4x < 10x threshold
        )
        # No other flags set, no momentum history
        assert sig.manipulation_risk == "clean"

    def test_insider_pattern_big_jump_no_volume(self):
        sig = _make_signal(
            probability=0.85, probability_1h_ago=0.65,
            volume_usd=100_000, volume_1h_ago=80_000,
            liquidity_usd=120_000,
        )
        # 20% prob jump, only 1.25x volume = suspicious
        assert sig.manipulation_risk == "insider_pattern"

    def test_insider_pattern_not_triggered_with_volume(self):
        sig = _make_signal(
            probability=0.85, probability_1h_ago=0.65,
            volume_usd=200_000, volume_1h_ago=80_000,
            liquidity_usd=120_000,
        )
        # 20% jump but 2.5x volume (catalyst-driven, not insider)
        assert sig.manipulation_risk != "insider_pattern"

    def test_no_history_is_clean(self):
        sig = _make_signal()
        assert sig.manipulation_risk == "clean"


class TestSignalContextStringFlags:
    """Test that context_string includes whale/manipulation flags."""

    def test_context_whale_flag(self):
        sig = _make_signal(
            probability=0.80, probability_1h_ago=0.70,
            volume_usd=300_000, volume_1h_ago=100_000,
        )
        ctx = sig.context_string()
        assert "WHALE" in ctx

    def test_context_spike_flag(self):
        sig = _make_signal(
            volume_usd=400_000, volume_1h_ago=100_000,
        )
        ctx = sig.context_string()
        assert "SPIKE" in ctx

    def test_context_wash_trading_flag(self):
        sig = _make_signal(
            probability=0.72, probability_1h_ago=0.72,
            volume_usd=400_000, volume_1h_ago=100_000,
        )
        ctx = sig.context_string()
        assert "WASH_TRADING" in ctx

    def test_context_clean_no_flags(self):
        sig = _make_signal()
        ctx = sig.context_string()
        assert "WHALE" not in ctx
        assert "SPIKE" not in ctx
        assert "⚠️" not in ctx

    def test_to_dict_includes_manipulation_fields(self):
        sig = _make_signal(
            probability=0.80, probability_1h_ago=0.70,
            volume_usd=300_000, volume_1h_ago=100_000,
        )
        d = sig.to_dict()
        assert "is_volume_spike" in d
        assert "is_whale_activity" in d
        assert "manipulation_risk" in d
        assert "volume_change" in d
        assert d["volume_change"] == pytest.approx(3.0)


class TestAggregatorWhaleDetection:
    """Test whale/manipulation detection in aggregator."""

    def test_detect_whale_with_signals(self):
        from src.feeds.prediction_aggregator import PredictionAggregator
        agg = PredictionAggregator()
        # Create a whale signal
        whale_sig = _make_signal(
            market_id="whale1",
            probability=0.80, probability_1h_ago=0.65,
            volume_usd=500_000, volume_1h_ago=100_000,
        )
        agg._polymarket.get_signals = MagicMock(return_value=[whale_sig])
        agg._kalshi.get_signals = MagicMock(return_value=[])

        alerts = agg._detect_whale_and_manipulation("BTC")
        assert len(alerts) > 0
        assert any("WHALE" in a for a in alerts)

    def test_detect_wash_trading(self):
        from src.feeds.prediction_aggregator import PredictionAggregator
        agg = PredictionAggregator()
        wash_sig = _make_signal(
            market_id="wash1",
            probability=0.72, probability_1h_ago=0.72,
            volume_usd=600_000, volume_1h_ago=100_000,
        )
        agg._polymarket.get_signals = MagicMock(return_value=[wash_sig])
        agg._kalshi.get_signals = MagicMock(return_value=[])

        alerts = agg._detect_whale_and_manipulation("BTC")
        assert any("WASH" in a for a in alerts)

    def test_detect_no_alerts_clean(self):
        from src.feeds.prediction_aggregator import PredictionAggregator
        agg = PredictionAggregator()
        clean_sig = _make_signal(market_id="clean1")
        agg._polymarket.get_signals = MagicMock(return_value=[clean_sig])
        agg._kalshi.get_signals = MagicMock(return_value=[])

        alerts = agg._detect_whale_and_manipulation("BTC")
        assert len(alerts) == 0

    def test_format_telegram_whale_alerts_empty(self):
        from src.feeds.prediction_aggregator import PredictionAggregator
        with patch.dict(os.environ, {"SAPPHIRE_PREDICTION_MARKET_ENABLED": "true"}):
            agg = PredictionAggregator()
        agg._polymarket.get_signals = MagicMock(return_value=[])
        agg._kalshi.get_signals = MagicMock(return_value=[])
        text = agg.format_telegram_whale_alerts()
        assert "No suspicious activity" in text

    def test_format_telegram_whale_alerts_with_data(self):
        from src.feeds.prediction_aggregator import PredictionAggregator
        with patch.dict(os.environ, {"SAPPHIRE_PREDICTION_MARKET_ENABLED": "true"}):
            agg = PredictionAggregator()
        whale_sig = _make_signal(
            market_id="whale_fmt",
            probability=0.80, probability_1h_ago=0.65,
            volume_usd=500_000, volume_1h_ago=100_000,
        )
        agg._polymarket.get_signals = MagicMock(return_value=[whale_sig])
        agg._kalshi.get_signals = MagicMock(return_value=[])
        text = agg.format_telegram_whale_alerts()
        assert "Whale & Manipulation Monitor" in text
        assert "WHALE" in text

    def test_dashboard_includes_whale_alerts(self):
        from src.feeds.prediction_aggregator import PredictionAggregator
        agg = PredictionAggregator()
        agg._polymarket.get_signals = MagicMock(return_value=[])
        agg._kalshi.get_signals = MagicMock(return_value=[])
        data = agg.get_prediction_dashboard_data()
        assert "whale_alerts" in data

    def test_cognition_context_includes_whale_alerts(self):
        from src.feeds.prediction_aggregator import PredictionAggregator
        with patch.dict(os.environ, {"SAPPHIRE_PREDICTION_MARKET_ENABLED": "true"}):
            agg = PredictionAggregator()
        whale_sig = _make_signal(
            market_id="cog_whale",
            probability=0.80, probability_1h_ago=0.65,
            volume_usd=500_000, volume_1h_ago=100_000,
        )
        agg._polymarket.get_signals = MagicMock(return_value=[whale_sig])
        agg._kalshi.get_signals = MagicMock(return_value=[])
        ctx = agg.get_cognition_context("BTC")
        assert "Market Intelligence Alerts" in ctx


class TestTelegramWhaleCommand:
    """Test Telegram /pm_whale command."""

    @pytest.mark.asyncio
    async def test_pm_whale_command(self):
        engine = MagicMock()
        engine.prediction_aggregator.format_telegram_whale_alerts.return_value = "🐋 Alerts"
        engine.telegram.send_message = AsyncMock()

        from src.telegram_handlers import handle_prediction_commands
        result = await handle_prediction_commands(engine, "", "PM_WHALE", 0.0)
        assert result is True
        engine.telegram.send_message.assert_called_once()
        assert "Alerts" in engine.telegram.send_message.call_args[0][0]

    @pytest.mark.asyncio
    async def test_pm_manipulation_command(self):
        engine = MagicMock()
        engine.prediction_aggregator.format_telegram_whale_alerts.return_value = "⚠️ Check"
        engine.telegram.send_message = AsyncMock()

        from src.telegram_handlers import handle_prediction_commands
        result = await handle_prediction_commands(engine, "", "PM_MANIPULATION", 0.0)
        assert result is True


class TestVolumeHistoryTracking:
    """Test that PredictionMarketFeed tracks volume history."""

    def test_feed_has_volume_history(self):
        from src.feeds.prediction_signal import PredictionMarketFeed
        # Can't instantiate ABC, so test the init attributes
        class FakeFeed(PredictionMarketFeed):
            async def _fetch_markets(self, session):
                return []
        feed = FakeFeed(source=PredictionSource.POLYMARKET)
        assert hasattr(feed, '_volume_history')
        assert feed._volume_history == {}

    def test_update_history_tracks_volume(self):
        class FakeFeed(PredictionMarketFeed):
            async def _fetch_markets(self, session):
                return []
        feed = FakeFeed(source=PredictionSource.POLYMARKET)
        sig = _make_signal(market_id="vol_test", volume_usd=100_000)
        feed._update_history(sig)
        assert "vol_test" in feed._volume_history
        assert len(feed._volume_history["vol_test"]) == 1

    def test_update_history_sets_volume_1h_ago(self):
        class FakeFeed(PredictionMarketFeed):
            async def _fetch_markets(self, session):
                return []
        feed = FakeFeed(source=PredictionSource.POLYMARKET)
        # Simulate 60 data points (indices 0-59)
        for i in range(60):
            sig = _make_signal(market_id="vol_hist", volume_usd=100_000 + i * 1000)
            feed._update_history(sig)
        # 61st entry: history[-60] = entry at index 1 (vol=101_000)
        final_sig = _make_signal(market_id="vol_hist", volume_usd=200_000)
        feed._update_history(final_sig)
        assert final_sig.volume_1h_ago is not None
        assert final_sig.volume_1h_ago == 101_000


class TestTelegramAccuracyCommand:
    """Test Telegram /pm_accuracy command handler."""

    @pytest.mark.asyncio
    async def test_pm_accuracy_command(self):
        engine = MagicMock()
        engine.prediction_aggregator.format_telegram_accuracy.return_value = "📊 Accuracy"
        engine.telegram.send_message = AsyncMock()

        from src.telegram_handlers import handle_prediction_commands
        result = await handle_prediction_commands(engine, "", "PM_ACCURACY", 0.0)
        assert result is True
        engine.telegram.send_message.assert_called_once()
        assert "Accuracy" in engine.telegram.send_message.call_args[0][0]

    @pytest.mark.asyncio
    async def test_prediction_accuracy_command(self):
        engine = MagicMock()
        engine.prediction_aggregator.format_telegram_accuracy.return_value = "📊 Stats"
        engine.telegram.send_message = AsyncMock()

        from src.telegram_handlers import handle_prediction_commands
        result = await handle_prediction_commands(engine, "", "PREDICTION_ACCURACY", 0.0)
        assert result is True


# ── Helpers ──────────────────────────────────────────────────────────

class AsyncContextManager:
    """Helper to mock aiohttp context managers."""

    def __init__(self, mock_response):
        self.mock_response = mock_response

    async def __aenter__(self):
        return self.mock_response

    async def __aexit__(self, *args):
        pass
