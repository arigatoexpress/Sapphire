"""
Cognition & Memory Test Suite — 2.3

Covers:
  - EnhancedMemoryBank  (shared/enhanced_episodic_memory.py)
  - DualSpeedCognition   (shared/dual_speed_cognition.py)
  - EpisodicMemory       (cloud_trader/memory/episodic_memory.py)
  - ReflectionAgent      (cloud_trader/memory/reflection_agent.py)
  - Episode / TradeOutcome helpers (cloud_trader/memory/episode.py)
"""

import asyncio
import json
import os
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Add alpha-engine to path for shared/ imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../services/alpha-engine"))

# ── Episode & TradeOutcome ──────────────────────────────────────

from cloud_trader.memory.episode import Episode, TradeOutcome, create_episode


class TestTradeOutcome:
    def test_defaults(self):
        o = TradeOutcome()
        assert o.success is False
        assert o.pnl == 0.0
        assert o.exit_reason == ""

    def test_to_dict(self):
        o = TradeOutcome(success=True, pnl=50.0, exit_reason="take_profit")
        d = o.to_dict()
        assert d["success"] is True
        assert d["pnl"] == 50.0
        assert d["exit_reason"] == "take_profit"


class TestEpisode:
    def _make_episode(self, **kw):
        defaults = dict(
            symbol="SOL",
            signal_type="LONG",
            entry_price=145.0,
            market_state_text="SOL trending up with high volume",
            confidence=0.8,
        )
        defaults.update(kw)
        return create_episode(**defaults)

    def test_auto_id_generation(self):
        ep = self._make_episode()
        assert ep.episode_id  # non-empty
        assert len(ep.episode_id) == 16

    def test_is_complete_requires_outcome_and_lesson(self):
        ep = self._make_episode()
        assert ep.is_complete() is False
        ep.outcome = TradeOutcome(success=True, pnl=10)
        assert ep.is_complete() is False
        ep.lesson = "Ride the momentum"
        assert ep.is_complete() is True

    def test_was_profitable(self):
        ep = self._make_episode()
        assert ep.was_profitable() is False
        ep.outcome = TradeOutcome(pnl=-5)
        assert ep.was_profitable() is False
        ep.outcome = TradeOutcome(pnl=10)
        assert ep.was_profitable() is True

    def test_round_trip_dict(self):
        ep = self._make_episode()
        ep.outcome = TradeOutcome(success=True, pnl=42.5, exit_reason="take_profit")
        ep.lesson = "Don't chase"
        d = ep.to_dict()
        restored = Episode.from_dict(d)
        assert restored.episode_id == ep.episode_id
        assert restored.outcome.pnl == 42.5
        assert restored.lesson == "Don't chase"

    def test_round_trip_json(self):
        ep = self._make_episode()
        j = ep.to_json()
        restored = Episode.from_json(j)
        assert restored.symbol == "SOL"

    def test_to_context_text_contains_key_fields(self):
        ep = self._make_episode()
        ep.outcome = TradeOutcome(success=True, pnl=50, pnl_percent=3.4)
        ep.lesson = "Trail stops"
        text = ep.to_context_text()
        assert "SOL" in text
        assert "LONG" in text
        assert "Trail stops" in text

    def test_to_reflection_prompt_context(self):
        ep = self._make_episode()
        ep.outcome = TradeOutcome(pnl=20, pnl_percent=1.5, exit_reason="stop_loss", max_drawdown=5)
        text = ep.to_reflection_prompt_context()
        assert "stop_loss" in text
        assert "SOL" in text


# ── Enhanced Episodic Memory ────────────────────────────────────

from shared.enhanced_episodic_memory import (
    CausalChain,
    CausalEvent,
    EnhancedEpisode,
    EnhancedMemoryBank,
    MarketRegime,
    MarketSnapshot,
    MultiFacetedLesson,
    TemporalPattern,
    auto_detect_regime,
)


class TestMarketSnapshot:
    def _make_snapshot(self, **overrides):
        defaults = dict(
            timestamp=datetime.now(timezone.utc),
            prices={"SOL": 145},
            volumes={"SOL": 800_000_000},
            volatility={"SOL": 0.025},
            order_book_imbalance={"SOL": 0.05},
            funding_rates={"SOL": 0.001},
        )
        defaults.update(overrides)
        return MarketSnapshot(**defaults)

    def test_round_trip_dict(self):
        s = self._make_snapshot()
        d = s.to_dict()
        restored = MarketSnapshot.from_dict(d)
        assert restored.prices == s.prices
        assert restored.volumes == s.volumes

    def test_get_regime_indicators(self):
        s = self._make_snapshot(volatility={"SOL": 0.04})
        indicators = s.get_regime_indicators()
        assert indicators["avg_volatility"] == 0.04
        assert indicators["high_volatility"] is True  # > 0.03

    def test_empty_fields(self):
        s = MarketSnapshot(timestamp=datetime.now(timezone.utc))
        indicators = s.get_regime_indicators()
        assert indicators["avg_volatility"] == 0
        assert indicators["high_volatility"] is False


class TestAutoDetectRegime:
    def _snapshot(self, vol=0.02, imbalance=0.0):
        return MarketSnapshot(
            timestamp=datetime.now(timezone.utc),
            volatility={"X": vol},
            order_book_imbalance={"X": imbalance},
            funding_rates={"X": 0.001},
        )

    def test_high_volatility_bullish_breakout(self):
        snap = self._snapshot(vol=0.05, imbalance=0.2)
        regime, conf = auto_detect_regime(snap)
        assert regime == MarketRegime.BREAKOUT
        assert conf >= 0.7

    def test_high_volatility_bearish(self):
        snap = self._snapshot(vol=0.05, imbalance=-0.2)
        regime, _ = auto_detect_regime(snap)
        assert regime == MarketRegime.HIGH_VOLATILITY

    def test_trending_up_via_price_change(self):
        snap = self._snapshot(vol=0.02, imbalance=0.0)
        regime, _ = auto_detect_regime(snap, price_change_1h={"X": 3.0})
        assert regime == MarketRegime.TRENDING_UP

    def test_trending_down_via_price_change(self):
        snap = self._snapshot(vol=0.02, imbalance=0.0)
        regime, _ = auto_detect_regime(snap, price_change_1h={"X": -3.0})
        assert regime == MarketRegime.TRENDING_DOWN

    def test_bullish_pressure(self):
        snap = self._snapshot(vol=0.02, imbalance=0.15)
        regime, _ = auto_detect_regime(snap)
        assert regime == MarketRegime.TRENDING_UP

    def test_bearish_pressure(self):
        snap = self._snapshot(vol=0.02, imbalance=-0.15)
        regime, _ = auto_detect_regime(snap)
        assert regime == MarketRegime.TRENDING_DOWN

    def test_ranging_market(self):
        snap = self._snapshot(vol=0.01, imbalance=0.02)
        regime, _ = auto_detect_regime(snap)
        assert regime == MarketRegime.RANGING

    def test_low_volatility(self):
        snap = self._snapshot(vol=0.01, imbalance=0.08)
        regime, _ = auto_detect_regime(snap)
        assert regime == MarketRegime.LOW_VOLATILITY


class TestCausalChain:
    def test_add_event_links_to_previous(self):
        chain = CausalChain(chain_id="test-chain")
        e1 = chain.add_event("market", "Price spike")
        e2 = chain.add_event("action", "Entered long")
        assert e2.caused_by == "test-chain-0"
        assert e1.led_to == "test-chain-1"

    def test_get_narrative_empty(self):
        chain = CausalChain(chain_id="empty")
        assert chain.get_narrative() == "No events recorded."

    def test_get_narrative_multiple(self):
        chain = CausalChain(chain_id="c")
        chain.add_event("market", "Volume spike")
        chain.add_event("action", "Bought SOL")
        narrative = chain.get_narrative()
        assert "Volume spike" in narrative
        assert "→" in narrative  # second event prefixed

    def test_to_dict(self):
        chain = CausalChain(chain_id="c")
        chain.add_event("market", "Event 1")
        d = chain.to_dict()
        assert d["chain_id"] == "c"
        assert len(d["events"]) == 1


class TestMultiFacetedLesson:
    def test_round_trip(self):
        lesson = MultiFacetedLesson(
            tactical="Trail stops",
            strategic="Follow momentum",
            psychological="Stay calm",
            counter_factual="Could have waited",
            confidence=0.8,
        )
        d = lesson.to_dict()
        restored = MultiFacetedLesson.from_dict(d)
        assert restored.tactical == "Trail stops"
        assert restored.confidence == 0.8

    def test_get_summary_empty(self):
        lesson = MultiFacetedLesson()
        assert lesson.get_summary() == "No lessons extracted."

    def test_get_summary_partial(self):
        lesson = MultiFacetedLesson(tactical="Use trailing stops")
        summary = lesson.get_summary()
        assert "Tactical" in summary
        assert "trailing stops" in summary


class TestTemporalPattern:
    def test_win_rate_zero_trades(self):
        p = TemporalPattern(hour_of_day=14, day_of_week=2)
        assert p.win_rate == 0.0

    def test_win_rate_calculation(self):
        p = TemporalPattern(hour_of_day=14, day_of_week=2, trades_taken=10, wins=7)
        assert p.win_rate == 0.7


class TestEnhancedEpisode:
    def test_round_trip_dict(self):
        ep = EnhancedEpisode(
            episode_id="test-001",
            name="SOL Breakout",
            start_time=datetime.now(timezone.utc),
            regime=MarketRegime.BREAKOUT,
            regime_confidence=0.85,
            symbols_involved=["SOL"],
            total_pnl=150.0,
            win_rate=0.75,
            tags=["momentum"],
        )
        ep.lessons = MultiFacetedLesson(tactical="Trail stops", confidence=0.9)
        d = ep.to_dict()
        restored = EnhancedEpisode.from_dict(d)
        assert restored.episode_id == "test-001"
        assert restored.regime == MarketRegime.BREAKOUT
        assert restored.lessons.tactical == "Trail stops"

    def test_get_summary(self):
        ep = EnhancedEpisode(
            episode_id="t",
            name="Test Episode",
            start_time=datetime.now(timezone.utc),
            end_time=datetime.now(timezone.utc) + timedelta(hours=2),
            regime=MarketRegime.TRENDING_UP,
            total_pnl=100.0,
            win_rate=0.8,
        )
        summary = ep.get_summary()
        assert "Test Episode" in summary
        assert "trending_up" in summary


class TestEnhancedMemoryBank:
    def _make_bank(self, tmp_path):
        path = os.path.join(str(tmp_path), "test_memory.json")
        with patch.dict(os.environ, {"GEMINI_API_KEY": ""}, clear=False):
            return EnhancedMemoryBank(storage_path=path)

    def _make_snapshot(self, vol=0.025, imbalance=0.05):
        return MarketSnapshot(
            timestamp=datetime.now(timezone.utc),
            prices={"SOL": 145},
            volumes={"SOL": 800_000_000},
            volatility={"SOL": vol},
            order_book_imbalance={"SOL": imbalance},
            funding_rates={"SOL": 0.001},
        )

    def test_start_and_end_episode(self, tmp_path):
        bank = self._make_bank(tmp_path)
        snap = self._make_snapshot()
        ep = bank.start_episode("Test EP", snap, symbols=["SOL"])
        assert bank.current_episode is not None
        assert ep.regime != MarketRegime.UNKNOWN

        ended = bank.end_episode(snap)
        assert ended is not None
        assert bank.current_episode is None
        assert ended.episode_id in bank.episodes

    def test_record_trade_adds_to_causal_chain(self, tmp_path):
        bank = self._make_bank(tmp_path)
        snap = self._make_snapshot()
        bank.start_episode("Trade Test", snap)
        bank.record_trade({"symbol": "SOL", "side": "BUY", "price": 145.5, "pnl": 25})
        assert len(bank.current_episode.trades) == 1
        # Start event + trade event = at least 2 events
        assert len(bank.current_episode.causal_chain.events) >= 2

    def test_record_events(self, tmp_path):
        bank = self._make_bank(tmp_path)
        bank.start_episode("Event Test", self._make_snapshot())
        bank.record_market_event("Volume spike")
        bank.record_action("Entered long")
        bank.record_outcome("Hit TP")
        assert len(bank.current_episode.causal_chain.events) >= 4

    def test_no_op_when_no_current_episode(self, tmp_path):
        bank = self._make_bank(tmp_path)
        # Should not raise
        bank.record_market_event("Test")
        bank.record_action("Test")
        bank.record_outcome("Test")
        bank.record_trade({"symbol": "X"})

    def test_end_episode_calculates_outcomes(self, tmp_path):
        bank = self._make_bank(tmp_path)
        snap = self._make_snapshot()
        bank.start_episode("PnL Test", snap, symbols=["SOL"])
        bank.record_trade({"symbol": "SOL", "side": "BUY", "price": 145, "pnl": 50})
        bank.record_trade({"symbol": "SOL", "side": "BUY", "price": 146, "pnl": -10})
        bank.record_trade({"symbol": "SOL", "side": "BUY", "price": 147, "pnl": 30})

        ep = bank.end_episode(snap)
        assert ep.total_pnl == 70.0
        assert 0 < ep.win_rate <= 1.0
        assert ep.sharpe_ratio != 0  # 3 trades with variance

    def test_persistence_round_trip(self, tmp_path):
        path = os.path.join(str(tmp_path), "persist_test.json")
        with patch.dict(os.environ, {"GEMINI_API_KEY": ""}, clear=False):
            bank1 = EnhancedMemoryBank(storage_path=path)
            snap = self._make_snapshot()
            bank1.start_episode("Persist Test", snap)
            bank1.end_episode(snap)
            assert os.path.exists(path)

            # Load in a new bank
            bank2 = EnhancedMemoryBank(storage_path=path)
            assert len(bank2.episodes) == 1

    def test_find_similar_episodes(self, tmp_path):
        bank = self._make_bank(tmp_path)
        snap = self._make_snapshot()

        # Store two episodes (manually set IDs to avoid same-second collision)
        bank.start_episode("EP1", snap, symbols=["SOL"])
        bank.current_episode.episode_id = "ep-find-001"
        bank.current_episode.regime = MarketRegime.BREAKOUT
        bank.current_episode.regime_confidence = 0.9
        bank.current_episode.causal_chain.chain_id = "ep-find-001"
        bank.end_episode(snap)

        bank.start_episode("EP2", snap, symbols=["BTC"])
        bank.current_episode.episode_id = "ep-find-002"
        bank.current_episode.regime = MarketRegime.RANGING
        bank.current_episode.causal_chain.chain_id = "ep-find-002"
        bank.end_episode(snap)

        results = bank.find_similar_episodes(regime=MarketRegime.BREAKOUT, symbols=["SOL"])
        assert len(results) >= 1
        assert results[0].name == "EP1"

    def test_get_temporal_insights_no_data(self, tmp_path):
        bank = self._make_bank(tmp_path)
        insights = bank.get_temporal_insights()
        assert "message" in insights

    def test_get_stats(self, tmp_path):
        bank = self._make_bank(tmp_path)
        snap = self._make_snapshot()
        bank.start_episode("Stats Test", snap)
        bank.record_trade({"pnl": 100})
        bank.end_episode(snap)
        stats = bank.get_stats()
        assert stats["total_episodes"] == 1

    @pytest.mark.asyncio
    async def test_extract_lessons_mock_mode(self, tmp_path):
        """Without API key, returns mock lesson."""
        bank = self._make_bank(tmp_path)
        snap = self._make_snapshot()
        bank.start_episode("Lesson Test", snap)
        bank.record_trade({"pnl": 50})
        ep = bank.end_episode(snap)
        lesson = await bank.extract_multi_faceted_lessons(ep)
        assert lesson.confidence == 0.3  # mock confidence
        assert lesson.tactical is not None

    @pytest.mark.asyncio
    async def test_recall_for_decision_no_episodes(self, tmp_path):
        bank = self._make_bank(tmp_path)
        snap = self._make_snapshot()
        result = await bank.recall_for_decision("SOL", snap)
        assert "No relevant" in result


# ── Dual-Speed Cognition ────────────────────────────────────────

from shared.dual_speed_cognition import (
    CognitionRequest,
    CognitionResult,
    CognitionSpeed,
    DualSpeedCognition,
)


class TestCognitionDataclasses:
    def test_cognition_request_defaults(self):
        req = CognitionRequest(prompt="Should I buy SOL?")
        assert req.speed == CognitionSpeed.DUAL
        assert req.max_latency_ms == 5000.0

    def test_cognition_result(self):
        res = CognitionResult(
            decision="BUY",
            confidence=0.9,
            reasoning="Strong momentum",
            system_used=CognitionSpeed.SYSTEM_1,
            latency_ms=45.0,
        )
        assert res.was_overridden is False


class TestDualSpeedCognitionMockMode:
    """Tests DualSpeedCognition when no API key is set (mock mode)."""

    def _make_cognition(self):
        with patch.dict(os.environ, {"GEMINI_API_KEY": "", "GOOGLE_API_KEY": ""}, clear=False):
            return DualSpeedCognition()

    @pytest.mark.asyncio
    async def test_system1_only_mock(self):
        cog = self._make_cognition()
        req = CognitionRequest(prompt="Test", speed=CognitionSpeed.SYSTEM_1)
        result = await cog.process(req)
        assert result.decision == "HOLD"
        assert result.system_used == CognitionSpeed.SYSTEM_1
        assert result.latency_ms >= 0

    @pytest.mark.asyncio
    async def test_system2_only_mock(self):
        cog = self._make_cognition()
        req = CognitionRequest(prompt="Test", speed=CognitionSpeed.SYSTEM_2)
        result = await cog.process(req)
        assert result.decision == "HOLD"
        assert result.system_used == CognitionSpeed.SYSTEM_2

    @pytest.mark.asyncio
    async def test_dual_mode_mock(self):
        cog = self._make_cognition()
        req = CognitionRequest(prompt="Test", speed=CognitionSpeed.DUAL)
        result = await cog.process(req)
        assert result.decision == "HOLD"
        assert result.system_used == CognitionSpeed.DUAL
        assert result.system1_decision == "HOLD"
        assert result.system2_validation == "HOLD"
        assert result.was_overridden is False

    @pytest.mark.asyncio
    async def test_metrics_tracked_mock_mode(self):
        """In mock mode, system1/2 are None so call counters stay at 0;
        but latency metrics are still updated."""
        cog = self._make_cognition()
        req = CognitionRequest(prompt="Test", speed=CognitionSpeed.DUAL)
        await cog.process(req)
        m = cog.get_metrics()
        # Mock mode doesn't increment call counters (system1/2 are None)
        assert m["system1_calls"] == 0
        assert m["system2_calls"] == 0
        # But latency updates still fire
        assert m["avg_system1_latency_ms"] >= 0
        assert m["avg_system2_latency_ms"] >= 0

    @pytest.mark.asyncio
    async def test_provisional_callback_not_called_at_low_confidence(self):
        cog = self._make_cognition()
        callback = AsyncMock()
        req = CognitionRequest(prompt="Test", speed=CognitionSpeed.DUAL)
        await cog.process(req, on_provisional_decision=callback)
        callback.assert_not_called()  # mock mode returns 0.5 confidence < 0.85 threshold


class TestParseResponse:
    def _make_cognition(self):
        with patch.dict(os.environ, {"GEMINI_API_KEY": "", "GOOGLE_API_KEY": ""}, clear=False):
            return DualSpeedCognition()

    def test_parse_buy(self):
        cog = self._make_cognition()
        decision, conf, _ = cog._parse_response("DECISION: BUY\nCONFIDENCE: 0.85\nREASON: Strong")
        assert decision == "BUY"
        assert conf == 0.85

    def test_parse_sell(self):
        cog = self._make_cognition()
        decision, _, _ = cog._parse_response("DECISION: SELL\nCONFIDENCE: 0.7")
        assert decision == "SELL"

    def test_parse_hold_default(self):
        cog = self._make_cognition()
        decision, conf, _ = cog._parse_response("I think we should wait and see.")
        assert decision == "HOLD"
        assert conf == 0.5

    def test_parse_invalid_confidence(self):
        cog = self._make_cognition()
        _, conf, _ = cog._parse_response("DECISION: BUY\nCONFIDENCE: not-a-number")
        assert conf == 0.5  # fallback


class TestShouldOverride:
    def _make_cognition(self):
        with patch.dict(os.environ, {"GEMINI_API_KEY": "", "GOOGLE_API_KEY": ""}, clear=False):
            return DualSpeedCognition()

    def test_different_decision_high_confidence_overrides(self):
        cog = self._make_cognition()
        assert cog._should_override("BUY", "SELL", 0.8) is True

    def test_same_decision_no_override(self):
        cog = self._make_cognition()
        assert cog._should_override("BUY", "BUY", 0.9) is False

    def test_hold_overrides_buy_at_moderate_confidence(self):
        cog = self._make_cognition()
        assert cog._should_override("BUY", "HOLD", 0.65) is True

    def test_hold_does_not_override_buy_at_low_confidence(self):
        cog = self._make_cognition()
        assert cog._should_override("BUY", "HOLD", 0.5) is False

    def test_different_decision_low_confidence_no_override(self):
        cog = self._make_cognition()
        assert cog._should_override("BUY", "SELL", 0.5) is False


# ── Episodic Memory (cloud_trader) ─────────────────────────────

from cloud_trader.memory.episodic_memory import EpisodicMemory


class TestEpisodicMemory:
    def _make_memory(self, tmp_path=None):
        path = str(tmp_path) if tmp_path else None
        return EpisodicMemory(storage_path=path, max_memory_episodes=50, max_recent_episodes=20)

    def _make_episode(self, symbol="SOL", pnl=None, lesson=None, text="trending up"):
        ep = create_episode(
            symbol=symbol,
            signal_type="LONG",
            entry_price=145.0,
            market_state_text=text,
            confidence=0.8,
        )
        if pnl is not None:
            ep.outcome = TradeOutcome(success=pnl > 0, pnl=pnl)
        if lesson:
            ep.lesson = lesson
        return ep

    @pytest.mark.asyncio
    async def test_store_and_retrieve(self):
        mem = self._make_memory()
        ep = self._make_episode()
        eid = await mem.store(ep)
        assert mem.get_by_id(eid) is ep

    @pytest.mark.asyncio
    async def test_symbol_index(self):
        mem = self._make_memory()
        await mem.store(self._make_episode(symbol="SOL"))
        await mem.store(self._make_episode(symbol="BTC"))
        assert "SOL" in mem._by_symbol
        assert "BTC" in mem._by_symbol

    @pytest.mark.asyncio
    async def test_profitable_index(self):
        mem = self._make_memory()
        await mem.store(self._make_episode(pnl=50))
        await mem.store(self._make_episode(pnl=-10))
        assert len(mem._profitable_ids) == 1
        assert len(mem._unprofitable_ids) == 1

    @pytest.mark.asyncio
    async def test_update_outcome(self):
        mem = self._make_memory()
        ep = self._make_episode()
        eid = await mem.store(ep)
        result = await mem.update_outcome(eid, TradeOutcome(success=True, pnl=100))
        assert result is True
        assert mem.get_by_id(eid).outcome.pnl == 100

    @pytest.mark.asyncio
    async def test_update_outcome_missing_id(self):
        mem = self._make_memory()
        result = await mem.update_outcome("nonexistent", TradeOutcome())
        assert result is False

    @pytest.mark.asyncio
    async def test_add_reflection(self):
        mem = self._make_memory()
        ep = self._make_episode()
        eid = await mem.store(ep)
        result = await mem.add_reflection(eid, "Good entry", "Bad exit", "Use trailing stops")
        assert result is True
        assert mem.get_by_id(eid).lesson == "Use trailing stops"

    @pytest.mark.asyncio
    async def test_add_reflection_missing_id(self):
        mem = self._make_memory()
        result = await mem.add_reflection("nope", "", "", "")
        assert result is False

    @pytest.mark.asyncio
    async def test_recall_similar(self):
        mem = self._make_memory()
        await mem.store(self._make_episode(symbol="SOL", text="SOL trending up breakout volume"))
        await mem.store(self._make_episode(symbol="BTC", text="BTC ranging low volume"))

        results = await mem.recall_similar("SOL breakout volume trending", symbol="SOL")
        assert len(results) >= 1
        assert results[0].symbol == "SOL"

    @pytest.mark.asyncio
    async def test_recall_prefers_profitable(self):
        mem = self._make_memory()
        await mem.store(self._make_episode(pnl=-10, text="SOL breakout"))
        await mem.store(self._make_episode(pnl=50, text="SOL breakout"))
        results = await mem.recall_similar("SOL breakout", prefer_profitable=True)
        # Profitable one should rank higher
        assert results[0].was_profitable()

    @pytest.mark.asyncio
    async def test_get_lessons_for_context(self):
        mem = self._make_memory()
        ep = self._make_episode(symbol="SOL", pnl=50, lesson="Ride momentum", text="SOL LONG")
        await mem.store(ep)
        lessons_text = await mem.get_lessons_for_context("SOL", "LONG")
        assert "Ride momentum" in lessons_text

    @pytest.mark.asyncio
    async def test_get_lessons_empty(self):
        mem = self._make_memory()
        result = await mem.get_lessons_for_context("SOL", "LONG")
        assert result == ""

    def test_get_recent(self):
        mem = self._make_memory()
        # Store synchronously for simplicity
        ep = self._make_episode()
        mem._episodes[ep.episode_id] = ep
        mem._recent_queue.append(ep.episode_id)
        recent = mem.get_recent(5)
        assert len(recent) == 1

    def test_get_stats(self):
        mem = self._make_memory()
        stats = mem.get_stats()
        assert stats["total_stored"] == 0
        assert stats["in_memory"] == 0

    @pytest.mark.asyncio
    async def test_prune_old_episodes(self):
        mem = EpisodicMemory(max_memory_episodes=3, max_recent_episodes=3)
        for i in range(5):
            ep = self._make_episode(text=f"episode {i}")
            ep.timestamp = datetime.now() - timedelta(days=5 - i)
            await mem.store(ep)
        # Should have pruned to 3
        assert len(mem._episodes) <= 3

    @pytest.mark.asyncio
    async def test_persistence(self, tmp_path):
        mem = self._make_memory(tmp_path)
        await mem.store(self._make_episode())
        # Check file was written
        files = list(Path(str(tmp_path)).glob("*.json"))
        assert len(files) == 1

    def test_calculate_similarity(self):
        mem = self._make_memory()
        assert mem._calculate_similarity("", "") == 0.0
        assert mem._calculate_similarity("hello world", "hello world") == 1.0
        sim = mem._calculate_similarity("SOL trending up breakout", "SOL breakout volume")
        assert 0 < sim < 1


# ── Reflection Agent ────────────────────────────────────────────

from cloud_trader.memory.reflection_agent import ReflectionAgent


class TestReflectionAgent:
    def _make_episode(self, outcome_kw=None, signal_type="LONG"):
        ep = create_episode(
            symbol="SOL",
            signal_type=signal_type,
            entry_price=145.0,
            market_state_text="SOL trending up",
        )
        if outcome_kw:
            ep.outcome = TradeOutcome(**outcome_kw)
        return ep

    @pytest.mark.asyncio
    async def test_reflect_no_outcome_returns_empty(self):
        agent = ReflectionAgent()
        ep = self._make_episode()
        result = await agent.reflect(ep)
        assert result["lesson"] == ""

    @pytest.mark.asyncio
    async def test_rule_based_profitable_trade(self):
        agent = ReflectionAgent()
        ep = self._make_episode(
            outcome_kw=dict(
                success=True,
                pnl=100,
                pnl_percent=6.0,
                exit_reason="take_profit",
                hold_duration_seconds=300,
                max_drawdown=20,
                max_profit=110,
            )
        )
        result = await agent.reflect(ep)
        assert "profitable" in result["what_worked"].lower() or "TP" in result["what_worked"]
        assert result["lesson"]

    @pytest.mark.asyncio
    async def test_rule_based_stop_loss_hit(self):
        agent = ReflectionAgent()
        ep = self._make_episode(
            outcome_kw=dict(
                success=False,
                pnl=-50,
                pnl_percent=-3.0,
                exit_reason="stop_loss",
                hold_duration_seconds=600,
                max_drawdown=60,
                max_profit=10,
            )
        )
        result = await agent.reflect(ep)
        assert "SL" in result["what_failed"] or "stop" in result["lesson"].lower()

    @pytest.mark.asyncio
    async def test_rule_based_exited_too_quickly(self):
        agent = ReflectionAgent()
        ep = self._make_episode(
            outcome_kw=dict(
                success=False,
                pnl=-5,
                hold_duration_seconds=30,
                max_drawdown=5,
                max_profit=2,
            )
        )
        result = await agent.reflect(ep)
        assert "quickly" in result["what_failed"].lower()

    @pytest.mark.asyncio
    async def test_rule_based_held_too_long(self):
        agent = ReflectionAgent()
        ep = self._make_episode(
            outcome_kw=dict(
                success=False,
                pnl=-20,
                hold_duration_seconds=7200,
                max_drawdown=30,
                max_profit=5,
            )
        )
        result = await agent.reflect(ep)
        assert "long" in result["what_failed"].lower()

    @pytest.mark.asyncio
    async def test_rule_based_gave_back_profit(self):
        agent = ReflectionAgent()
        ep = self._make_episode(
            outcome_kw=dict(
                success=False,
                pnl=5,
                max_profit=50,
                hold_duration_seconds=300,
                max_drawdown=10,
            )
        )
        result = await agent.reflect(ep)
        assert "profit" in result["what_failed"].lower()

    @pytest.mark.asyncio
    async def test_rule_based_short_signal(self):
        agent = ReflectionAgent()
        ep = self._make_episode(
            signal_type="SHORT",
            outcome_kw=dict(
                success=True,
                pnl=50,
                hold_duration_seconds=300,
                max_drawdown=5,
                max_profit=55,
                exit_reason="take_profit",
            ),
        )
        result = await agent.reflect(ep)
        assert "Shorting" in result["lesson"] or "SHORT" in result["lesson"].upper()

    @pytest.mark.asyncio
    async def test_batch_reflect(self):
        agent = ReflectionAgent()
        ep1 = self._make_episode(
            outcome_kw=dict(success=True, pnl=50, hold_duration_seconds=300, max_drawdown=5, max_profit=55)
        )
        ep2 = self._make_episode()  # no outcome
        count = await agent.batch_reflect([ep1, ep2])
        assert count == 1
        assert ep1.lesson  # should be filled

    def test_get_stats(self):
        agent = ReflectionAgent()
        stats = agent.get_stats()
        assert stats["total_reflections"] == 0
