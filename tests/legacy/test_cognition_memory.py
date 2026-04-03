import pytest; pytestmark = pytest.mark.skip(reason="Legacy test — depends on removed module")
"""
Comprehensive tests for Sapphire AI cognition and memory subsystems.

Covers:
- DualSpeedCognition (dual_speed_cognition.py)
- EpisodicMemoryBank (episodic_memory.py)
- EnhancedMemoryBank (enhanced_episodic_memory.py)

All Gemini/genai calls are mocked — no API keys needed.
"""

import os
import sys
import tempfile
from datetime import UTC, datetime, timedelta
from unittest.mock import patch

import pytest

# Add alpha-engine root to sys.path so `shared.*` imports resolve
sys.path.insert(
    0, os.path.join(os.path.dirname(__file__), "../../services/alpha-engine")
)

# ─── Dual Speed Cognition ───────────────────────────────────────────

from shared.dual_speed_cognition import (
    CognitionRequest,
    CognitionResult,
    CognitionSpeed,
    DualSpeedCognition,
    get_dual_cognition,
)


class TestCognitionSpeedEnum:
    """Tests for the CognitionSpeed enum."""

    def test_enum_values(self):
        assert CognitionSpeed.SYSTEM_1 == "system_1"
        assert CognitionSpeed.SYSTEM_2 == "system_2"
        assert CognitionSpeed.DUAL == "dual"

    def test_enum_is_str(self):
        assert isinstance(CognitionSpeed.SYSTEM_1, str)

    def test_enum_from_value(self):
        assert CognitionSpeed("system_1") == CognitionSpeed.SYSTEM_1
        assert CognitionSpeed("dual") == CognitionSpeed.DUAL


class TestCognitionDataClasses:
    """Tests for CognitionRequest and CognitionResult dataclasses."""

    def test_request_defaults(self):
        req = CognitionRequest(prompt="test")
        assert req.prompt == "test"
        assert req.context == {}
        assert req.speed == CognitionSpeed.DUAL
        assert req.max_latency_ms == 5000.0
        assert req.requires_validation is True

    def test_request_custom_values(self):
        req = CognitionRequest(
            prompt="Should I buy SOL?",
            context={"price": 150.0},
            speed=CognitionSpeed.SYSTEM_1,
            max_latency_ms=1000.0,
            requires_validation=False,
        )
        assert req.speed == CognitionSpeed.SYSTEM_1
        assert req.max_latency_ms == 1000.0
        assert req.context["price"] == 150.0

    def test_result_basic(self):
        result = CognitionResult(
            decision="BUY",
            confidence=0.85,
            reasoning="Strong trend",
            system_used=CognitionSpeed.SYSTEM_1,
            latency_ms=42.0,
        )
        assert result.decision == "BUY"
        assert result.confidence == 0.85
        assert result.system1_decision is None
        assert result.system2_validation is None
        assert result.was_overridden is False

    def test_result_dual_mode(self):
        result = CognitionResult(
            decision="SELL",
            confidence=0.7,
            reasoning="Override",
            system_used=CognitionSpeed.DUAL,
            latency_ms=1500.0,
            system1_decision="BUY",
            system2_validation="SELL",
            was_overridden=True,
        )
        assert result.was_overridden is True
        assert result.system1_decision == "BUY"
        assert result.system2_validation == "SELL"


class TestDualSpeedCognition:
    """Tests for the DualSpeedCognition engine."""

    def test_mock_mode_no_api_key(self):
        """Without API key, should initialize in mock mode."""
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("GEMINI_API_KEY", None)
            os.environ.pop("GOOGLE_API_KEY", None)
            cog = DualSpeedCognition()
            assert cog.system1 is None
            assert cog.system2 is None

    def test_default_model_names(self):
        assert DualSpeedCognition.SYSTEM_1_MODEL_DEFAULT == "gemini-2.5-flash"
        assert DualSpeedCognition.SYSTEM_2_MODEL_DEFAULT == "gemini-2.5-pro"

    def test_env_model_override(self):
        """Model names can be overridden via env vars."""
        with patch.dict(
            os.environ,
            {
                "SAPPHIRE_SYSTEM1_MODEL": "test-flash",
                "SAPPHIRE_SYSTEM2_MODEL": "test-pro",
            },
            clear=False,
        ):
            os.environ.pop("GEMINI_API_KEY", None)
            os.environ.pop("GOOGLE_API_KEY", None)
            cog = DualSpeedCognition()
            assert cog.SYSTEM_1_MODEL == "test-flash"
            assert cog.SYSTEM_2_MODEL == "test-pro"

    def test_threshold_values(self):
        assert DualSpeedCognition.INSTANT_ACTION_THRESHOLD == 0.85
        assert DualSpeedCognition.VALIDATION_REQUIRED_THRESHOLD == 0.70
        assert DualSpeedCognition.COGNITIVE_WINDOW_MS == 2000

    def test_initial_metrics(self):
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("GEMINI_API_KEY", None)
            os.environ.pop("GOOGLE_API_KEY", None)
            cog = DualSpeedCognition()
            assert cog.system1_calls == 0
            assert cog.system2_calls == 0
            assert cog.overrides == 0
            assert cog.avg_system1_latency_ms == 0.0
            assert cog.avg_system2_latency_ms == 0.0


class TestResponseParsing:
    """Tests for _parse_response logic."""

    def setup_method(self):
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("GEMINI_API_KEY", None)
            os.environ.pop("GOOGLE_API_KEY", None)
            self.cog = DualSpeedCognition()

    def test_parse_buy_decision(self):
        text = "DECISION: BUY\nCONFIDENCE: 0.9\nREASON: Strong breakout"
        decision, conf, reasoning = self.cog._parse_response(text)
        assert decision == "BUY"
        assert conf == 0.9
        assert reasoning == text

    def test_parse_sell_decision(self):
        text = "DECISION: SELL\nCONFIDENCE: 0.75\nANALYSIS: Bearish"
        decision, conf, reasoning = self.cog._parse_response(text)
        assert decision == "SELL"
        assert conf == 0.75

    def test_parse_hold_default(self):
        text = "I'm not sure what to do here."
        decision, conf, reasoning = self.cog._parse_response(text)
        assert decision == "HOLD"
        assert conf == 0.5

    def test_parse_malformed_confidence(self):
        text = "DECISION: BUY\nCONFIDENCE: not_a_number"
        decision, conf, reasoning = self.cog._parse_response(text)
        assert decision == "BUY"
        assert conf == 0.5  # Falls back to default

    def test_parse_decision_case_insensitive(self):
        text = "DECISION: buy something\nCONFIDENCE: 0.8"
        decision, conf, reasoning = self.cog._parse_response(text)
        assert decision == "BUY"

    def test_parse_sell_in_mixed_text(self):
        text = "DECISION: STRONG SELL\nCONFIDENCE: 0.88"
        decision, conf, _ = self.cog._parse_response(text)
        assert decision == "SELL"
        assert conf == 0.88

    def test_parse_empty_string(self):
        decision, conf, reasoning = self.cog._parse_response("")
        assert decision == "HOLD"
        assert conf == 0.5
        assert reasoning == ""


class TestOverrideLogic:
    """Tests for _should_override decision logic."""

    def setup_method(self):
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("GEMINI_API_KEY", None)
            os.environ.pop("GOOGLE_API_KEY", None)
            self.cog = DualSpeedCognition()

    def test_override_different_decisions_high_confidence(self):
        """S2 disagrees with high confidence -> override."""
        assert self.cog._should_override("BUY", "SELL", 0.8) is True

    def test_no_override_different_decisions_low_confidence(self):
        """S2 disagrees but low confidence -> no override."""
        assert self.cog._should_override("BUY", "SELL", 0.5) is False

    def test_no_override_same_decisions(self):
        """Both agree -> no override regardless of confidence."""
        assert self.cog._should_override("BUY", "BUY", 0.99) is False
        assert self.cog._should_override("SELL", "SELL", 0.8) is False
        assert self.cog._should_override("HOLD", "HOLD", 0.9) is False

    def test_safety_override_hold_vs_buy(self):
        """S2 says HOLD, S1 wants to BUY with S2 conf >= 0.6 -> override (safety)."""
        assert self.cog._should_override("BUY", "HOLD", 0.6) is True
        assert self.cog._should_override("BUY", "HOLD", 0.65) is True

    def test_safety_override_hold_vs_sell(self):
        """S2 says HOLD, S1 wants to SELL with S2 conf >= 0.6 -> override (safety)."""
        assert self.cog._should_override("SELL", "HOLD", 0.6) is True

    def test_no_safety_override_low_confidence(self):
        """S2 says HOLD but confidence too low -> no override."""
        assert self.cog._should_override("BUY", "HOLD", 0.55) is False

    def test_override_at_exact_threshold(self):
        """At exactly 0.7 confidence with different decisions -> override."""
        assert self.cog._should_override("BUY", "SELL", 0.7) is True

    def test_no_override_just_below_threshold(self):
        """At 0.69 confidence with different decisions -> no override."""
        assert self.cog._should_override("BUY", "SELL", 0.69) is False


class TestMetricsUpdate:
    """Tests for metrics tracking."""

    def setup_method(self):
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("GEMINI_API_KEY", None)
            os.environ.pop("GOOGLE_API_KEY", None)
            self.cog = DualSpeedCognition()

    def test_system1_first_call(self):
        self.cog.system1_calls = 1
        self.cog._update_system1_metrics(100.0)
        assert self.cog.avg_system1_latency_ms == 100.0

    def test_system1_running_average(self):
        self.cog.system1_calls = 1
        self.cog._update_system1_metrics(100.0)
        self.cog.system1_calls = 2
        self.cog._update_system1_metrics(200.0)
        assert self.cog.avg_system1_latency_ms == 150.0

    def test_system2_first_call(self):
        self.cog.system2_calls = 1
        self.cog._update_system2_metrics(500.0)
        assert self.cog.avg_system2_latency_ms == 500.0

    def test_get_metrics_format(self):
        metrics = self.cog.get_metrics()
        assert "system1_calls" in metrics
        assert "system2_calls" in metrics
        assert "overrides" in metrics
        assert "override_rate" in metrics
        assert "avg_system1_latency_ms" in metrics
        assert "avg_system2_latency_ms" in metrics

    def test_override_rate_no_calls(self):
        metrics = self.cog.get_metrics()
        assert metrics["override_rate"] == 0.0

    def test_override_rate_with_calls(self):
        self.cog.system2_calls = 10
        self.cog.overrides = 3
        metrics = self.cog.get_metrics()
        assert metrics["override_rate"] == 0.3


class TestAsyncCognitionMock:
    """Async tests with mocked Gemini -- mock mode only."""

    def setup_method(self):
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("GEMINI_API_KEY", None)
            os.environ.pop("GOOGLE_API_KEY", None)
            self.cog = DualSpeedCognition()

    @pytest.mark.asyncio
    async def test_system1_mock_response(self):
        result = await self.cog._invoke_system1("test prompt")
        assert result == ("HOLD", 0.5, "[MOCK] System 1 response")

    @pytest.mark.asyncio
    async def test_system2_mock_response(self):
        result = await self.cog._invoke_system2("test prompt")
        assert result == ("HOLD", 0.5, "[MOCK] System 2 response")

    @pytest.mark.asyncio
    async def test_process_system1_only(self):
        req = CognitionRequest(prompt="test", speed=CognitionSpeed.SYSTEM_1)
        result = await self.cog.process(req)
        assert result.decision == "HOLD"
        assert result.system_used == CognitionSpeed.SYSTEM_1
        assert result.system1_decision == "HOLD"
        assert result.latency_ms >= 0

    @pytest.mark.asyncio
    async def test_process_system2_only(self):
        req = CognitionRequest(prompt="test", speed=CognitionSpeed.SYSTEM_2)
        result = await self.cog.process(req)
        assert result.decision == "HOLD"
        assert result.system_used == CognitionSpeed.SYSTEM_2
        assert result.system2_validation == "HOLD"

    @pytest.mark.asyncio
    async def test_process_dual_mode(self):
        req = CognitionRequest(prompt="test", speed=CognitionSpeed.DUAL)
        result = await self.cog.process(req)
        assert result.decision == "HOLD"
        assert result.system_used == CognitionSpeed.DUAL
        assert result.system1_decision == "HOLD"
        assert result.system2_validation == "HOLD"
        assert result.was_overridden is False

    @pytest.mark.asyncio
    async def test_dual_no_provisional_below_threshold(self):
        """Mock confidence is 0.5, below 0.85 threshold -> no provisional action."""
        callback_called = False

        async def provisional_cb(decision, confidence, reasoning):
            nonlocal callback_called
            callback_called = True

        req = CognitionRequest(prompt="test", speed=CognitionSpeed.DUAL)
        await self.cog.process(req, on_provisional_decision=provisional_cb)
        assert callback_called is False

    @pytest.mark.asyncio
    async def test_dual_confidence_average(self):
        """When both agree (HOLD/HOLD), confidence should be averaged."""
        req = CognitionRequest(prompt="test", speed=CognitionSpeed.DUAL)
        result = await self.cog.process(req)
        # Both return 0.5, average = 0.5
        assert result.confidence == 0.5


class TestGlobalInstance:
    """Tests for the singleton get_dual_cognition."""

    def test_get_dual_cognition_creates_instance(self):
        import shared.dual_speed_cognition as module

        module._cognition_instance = None
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("GEMINI_API_KEY", None)
            os.environ.pop("GOOGLE_API_KEY", None)
            inst = get_dual_cognition()
            assert inst is not None
            # Second call returns same instance
            inst2 = get_dual_cognition()
            assert inst is inst2
        module._cognition_instance = None


# ─── Episodic Memory ────────────────────────────────────────────────

from shared.episodic_memory import (
    EpisodicMemoryBank,
    MarketEpisode,
    get_episodic_memory,
)


class TestMarketEpisode:
    """Tests for the MarketEpisode dataclass."""

    def test_defaults(self):
        ep = MarketEpisode(
            episode_id="ep-001",
            name="Test Episode",
            start_time=datetime(2026, 1, 15, 10, 0, 0),
        )
        assert ep.regime == "unknown"
        assert ep.total_pnl == 0.0
        assert ep.win_rate == 0.0
        assert ep.trades == []
        assert ep.lesson is None

    def test_serialization_roundtrip(self):
        now = datetime(2026, 1, 15, 10, 0, 0)
        ep = MarketEpisode(
            episode_id="ep-001",
            name="SOL Breakout",
            start_time=now,
            end_time=now + timedelta(hours=4),
            regime="trending_up",
            key_events=["Volume spike"],
            symbols_involved=["SOL"],
            price_change_pct=5.0,
            total_pnl=250.0,
            win_rate=0.75,
            tags=["breakout", "high_vol"],
        )
        data = ep.to_dict()
        ep2 = MarketEpisode.from_dict(data)
        assert ep2.episode_id == ep.episode_id
        assert ep2.name == ep.name
        assert ep2.regime == ep.regime
        assert ep2.total_pnl == ep.total_pnl
        assert ep2.win_rate == ep.win_rate
        assert ep2.tags == ["breakout", "high_vol"]
        assert ep2.end_time == ep.end_time

    def test_to_dict_none_end_time(self):
        ep = MarketEpisode(
            episode_id="ep-001",
            name="In Progress",
            start_time=datetime(2026, 1, 15, 10, 0, 0),
        )
        data = ep.to_dict()
        assert data["end_time"] is None

    def test_from_dict_missing_optional_fields(self):
        data = {
            "episode_id": "ep-001",
            "name": "Minimal",
            "start_time": "2026-01-15T10:00:00",
        }
        ep = MarketEpisode.from_dict(data)
        assert ep.regime == "unknown"
        assert ep.trades == []
        assert ep.lesson is None

    def test_get_summary_with_end_time(self):
        ep = MarketEpisode(
            episode_id="ep-001",
            name="Test",
            start_time=datetime(2026, 1, 15, 10, 0, 0),
            end_time=datetime(2026, 1, 15, 14, 0, 0),
            regime="trending_up",
            total_pnl=100.0,
            win_rate=0.8,
            lesson="Buy on breakouts",
        )
        summary = ep.get_summary()
        assert "Test" in summary
        assert "trending_up" in summary
        assert "4.0h" in summary
        assert "Buy on breakouts" in summary


class TestEpisodicMemoryBank:
    """Tests for the EpisodicMemoryBank lifecycle."""

    def setup_method(self):
        self.tmpdir = tempfile.mkdtemp()
        self.storage_path = os.path.join(self.tmpdir, "test_memory.json")
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("GEMINI_API_KEY", None)
            os.environ.pop("GOOGLE_API_KEY", None)
            self.bank = EpisodicMemoryBank(storage_path=self.storage_path)

    def test_initial_state(self):
        assert len(self.bank.episodes) == 0
        assert self.bank.current_episode is None
        assert self.bank.model is None

    def test_start_episode(self):
        ep = self.bank.start_episode("Test Episode", "trending_up", ["SOL"])
        assert ep is not None
        assert self.bank.current_episode is ep
        assert ep.regime == "trending_up"
        assert "SOL" in ep.symbols_involved
        assert ep.episode_id.startswith("ep-")

    def test_record_trade(self):
        self.bank.start_episode("Test", "ranging", ["BTC"])
        self.bank.record_trade({"symbol": "BTC", "side": "BUY", "pnl": 50.0})
        assert len(self.bank.current_episode.trades) == 1
        assert self.bank.current_episode.trades[0]["pnl"] == 50.0

    def test_record_trade_no_episode(self):
        """Recording with no active episode should be a no-op."""
        self.bank.record_trade({"symbol": "SOL", "side": "BUY", "pnl": 100.0})
        # No error raised

    def test_record_event(self):
        self.bank.start_episode("Test", "ranging")
        self.bank.record_event("Big volume spike")
        assert "Big volume spike" in self.bank.current_episode.key_events

    def test_record_event_no_episode(self):
        self.bank.record_event("Something happened")
        # No error raised

    def test_end_episode(self):
        self.bank.start_episode("Test", "high_volatility", ["SOL"])
        self.bank.record_trade({"pnl": 100.0})
        self.bank.record_trade({"pnl": -30.0})
        self.bank.record_trade({"pnl": 50.0})

        ep = self.bank.end_episode(price_change_pct=5.0, volume_change_pct=200.0)
        assert ep is not None
        assert ep.end_time is not None
        assert ep.total_pnl == 120.0
        assert ep.win_rate == pytest.approx(2 / 3, abs=0.01)
        assert ep.price_change_pct == 5.0
        assert self.bank.current_episode is None
        assert ep.episode_id in self.bank.episodes

    def test_end_episode_no_trades(self):
        self.bank.start_episode("Empty", "ranging")
        ep = self.bank.end_episode()
        assert ep.total_pnl == 0.0
        assert ep.win_rate == 0.0

    def test_end_episode_no_current(self):
        result = self.bank.end_episode()
        assert result is None

    def test_persistence_roundtrip(self):
        self.bank.start_episode("Persist Test", "trending_up", ["ETH"])
        self.bank.record_trade({"pnl": 75.0})
        self.bank.end_episode(price_change_pct=3.0)

        # Create new bank from same storage
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("GEMINI_API_KEY", None)
            os.environ.pop("GOOGLE_API_KEY", None)
            bank2 = EpisodicMemoryBank(storage_path=self.storage_path)
        assert len(bank2.episodes) == 1
        ep = list(bank2.episodes.values())[0]
        assert ep.name == "Persist Test"
        assert ep.total_pnl == 75.0

    def test_find_similar_by_regime(self):
        # Manually create episodes with unique IDs to avoid timestamp collision
        for i, (name, regime, syms) in enumerate([
            ("Trending A", "trending_up", ["SOL"]),
            ("Trending B", "trending_up", ["BTC"]),
            ("Volatile C", "high_volatility", ["SOL"]),
        ]):
            ep = MarketEpisode(
                episode_id=f"ep-find-regime-{i}",
                name=name,
                start_time=datetime(2026, 1, 15, 10 + i, 0),
                end_time=datetime(2026, 1, 15, 11 + i, 0),
                regime=regime,
                symbols_involved=syms,
            )
            self.bank.episodes[ep.episode_id] = ep

        matches = self.bank.find_similar_episodes("trending_up")
        assert len(matches) == 2
        for m in matches:
            assert m.regime == "trending_up"

    def test_find_similar_by_symbol(self):
        for i, (name, syms) in enumerate([
            ("SOL A", ["SOL"]),
            ("BTC A", ["BTC"]),
        ]):
            ep = MarketEpisode(
                episode_id=f"ep-find-sym-{i}",
                name=name,
                start_time=datetime(2026, 1, 15, 10 + i, 0),
                end_time=datetime(2026, 1, 15, 11 + i, 0),
                regime="trending_up",
                symbols_involved=syms,
            )
            self.bank.episodes[ep.episode_id] = ep

        matches = self.bank.find_similar_episodes("trending_up", ["SOL"])
        assert len(matches) == 2
        assert matches[0].symbols_involved == ["SOL"]

    def test_find_similar_no_matches(self):
        ep = MarketEpisode(
            episode_id="ep-no-match",
            name="Only Trending",
            start_time=datetime(2026, 1, 15, 10, 0),
            regime="trending_up",
        )
        self.bank.episodes[ep.episode_id] = ep
        matches = self.bank.find_similar_episodes("mean_reversion")
        assert len(matches) == 0

    def test_find_similar_limit(self):
        for i in range(10):
            ep = MarketEpisode(
                episode_id=f"ep-limit-{i}",
                name=f"Episode {i}",
                start_time=datetime(2026, 1, 15, i, 0),
                regime="ranging",
                symbols_involved=["SOL"],
            )
            self.bank.episodes[ep.episode_id] = ep
        matches = self.bank.find_similar_episodes("ranging", limit=3)
        assert len(matches) == 3

    def test_get_stats(self):
        ep_a = MarketEpisode(
            episode_id="ep-stats-a",
            name="EP A",
            start_time=datetime(2026, 1, 15, 10, 0),
            regime="trending_up",
            symbols_involved=["SOL"],
            trades=[{"pnl": 100.0}],
            total_pnl=100.0,
        )
        ep_b = MarketEpisode(
            episode_id="ep-stats-b",
            name="EP B",
            start_time=datetime(2026, 1, 15, 11, 0),
            regime="ranging",
            symbols_involved=["BTC"],
            trades=[{"pnl": -20.0}, {"pnl": 30.0}],
            total_pnl=10.0,
        )
        self.bank.episodes[ep_a.episode_id] = ep_a
        self.bank.episodes[ep_b.episode_id] = ep_b

        stats = self.bank.get_stats()
        assert stats["total_episodes"] == 2
        assert stats["total_trades"] == 3
        assert stats["total_pnl"] == 110.0
        assert "trending_up" in stats["regimes"]
        assert "ranging" in stats["regimes"]
        assert stats["lessons_extracted"] == 0

    @pytest.mark.asyncio
    async def test_extract_lesson_no_model(self):
        ep = MarketEpisode(
            episode_id="ep-test",
            name="Test",
            start_time=datetime(2026, 1, 15),
        )
        lesson = await self.bank.extract_lesson(ep)
        assert "unavailable" in lesson.lower()

    @pytest.mark.asyncio
    async def test_recall_for_decision_no_episodes(self):
        result = await self.bank.recall_for_decision("SOL", "trending_up")
        assert "No relevant past episodes" in result

    @pytest.mark.asyncio
    async def test_recall_with_episodes_no_lessons(self):
        self.bank.start_episode("Test", "trending_up", ["SOL"])
        self.bank.end_episode()
        result = await self.bank.recall_for_decision("SOL", "trending_up")
        assert "no lessons extracted" in result.lower()

    @pytest.mark.asyncio
    async def test_recall_with_episodes_and_lessons(self):
        self.bank.start_episode("Test", "trending_up", ["SOL"])
        ep = self.bank.end_episode()
        ep.lesson = "Buy on volume spikes during uptrends"
        result = await self.bank.recall_for_decision("SOL", "trending_up")
        assert "Buy on volume spikes" in result


class TestEpisodicGlobalInstance:
    def test_get_episodic_memory(self):
        import shared.episodic_memory as module

        module._memory_instance = None
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("GEMINI_API_KEY", None)
            os.environ.pop("GOOGLE_API_KEY", None)
            inst = get_episodic_memory()
            assert inst is not None
            inst2 = get_episodic_memory()
            assert inst is inst2
        module._memory_instance = None


# ─── Enhanced Episodic Memory ────────────────────────────────────────

from shared.enhanced_episodic_memory import (
    CausalChain,
    EnhancedEpisode,
    EnhancedMemoryBank,
    MarketRegime,
    MarketSnapshot,
    MultiFacetedLesson,
    TemporalPattern,
    auto_detect_regime,
    get_enhanced_memory,
)


class TestMarketRegimeEnum:
    def test_all_values(self):
        assert MarketRegime.TRENDING_UP == "trending_up"
        assert MarketRegime.TRENDING_DOWN == "trending_down"
        assert MarketRegime.HIGH_VOLATILITY == "high_volatility"
        assert MarketRegime.LOW_VOLATILITY == "low_volatility"
        assert MarketRegime.RANGING == "ranging"
        assert MarketRegime.BREAKOUT == "breakout"
        assert MarketRegime.MEAN_REVERSION == "mean_reversion"
        assert MarketRegime.UNKNOWN == "unknown"

    def test_is_str(self):
        assert isinstance(MarketRegime.TRENDING_UP, str)


class TestMarketSnapshot:
    def test_defaults(self):
        snap = MarketSnapshot(timestamp=datetime.now(UTC))
        assert snap.prices == {}
        assert snap.volumes == {}
        assert snap.volatility == {}

    def test_serialization_roundtrip(self):
        now = datetime.now(UTC)
        snap = MarketSnapshot(
            timestamp=now,
            prices={"SOL": 150.0, "BTC": 48000.0},
            volumes={"SOL": 1e9},
            volatility={"SOL": 0.04},
            order_book_imbalance={"SOL": 0.2},
            funding_rates={"SOL": 0.001},
            open_interest={"SOL": 5e8},
            correlations={"SOL:BTC": 0.85},
        )
        data = snap.to_dict()
        snap2 = MarketSnapshot.from_dict(data)
        assert snap2.prices["SOL"] == 150.0
        assert snap2.correlations["SOL:BTC"] == 0.85
        assert snap2.timestamp.year == now.year

    def test_regime_indicators_empty(self):
        snap = MarketSnapshot(timestamp=datetime.now(UTC))
        indicators = snap.get_regime_indicators()
        assert indicators["avg_volatility"] == 0
        assert indicators["avg_imbalance"] == 0
        assert indicators["high_volatility"] is False

    def test_regime_indicators_with_data(self):
        snap = MarketSnapshot(
            timestamp=datetime.now(UTC),
            volatility={"SOL": 0.05, "BTC": 0.04},
            order_book_imbalance={"SOL": 0.2, "BTC": 0.1},
            funding_rates={"SOL": 0.002},
        )
        indicators = snap.get_regime_indicators()
        assert indicators["avg_volatility"] == pytest.approx(0.045)
        assert indicators["high_volatility"] is True
        assert indicators["bullish_pressure"] is True


class TestAutoDetectRegime:
    def test_high_volatility_breakout(self):
        snap = MarketSnapshot(
            timestamp=datetime.now(UTC),
            volatility={"SOL": 0.05},
            order_book_imbalance={"SOL": 0.2},
        )
        regime, conf = auto_detect_regime(snap)
        assert regime == MarketRegime.BREAKOUT
        assert conf == 0.8

    def test_high_volatility_bearish(self):
        snap = MarketSnapshot(
            timestamp=datetime.now(UTC),
            volatility={"SOL": 0.05},
            order_book_imbalance={"SOL": -0.2},
        )
        regime, conf = auto_detect_regime(snap)
        assert regime == MarketRegime.HIGH_VOLATILITY
        assert conf == 0.7

    def test_high_volatility_neutral(self):
        snap = MarketSnapshot(
            timestamp=datetime.now(UTC),
            volatility={"SOL": 0.05},
            order_book_imbalance={"SOL": 0.05},
        )
        regime, conf = auto_detect_regime(snap)
        assert regime == MarketRegime.HIGH_VOLATILITY
        assert conf == 0.6

    def test_trending_up_by_price_change(self):
        snap = MarketSnapshot(
            timestamp=datetime.now(UTC),
            volatility={"SOL": 0.02},
            order_book_imbalance={"SOL": 0.0},
        )
        regime, conf = auto_detect_regime(snap, price_change_1h={"SOL": 3.0})
        assert regime == MarketRegime.TRENDING_UP
        assert conf == 0.75

    def test_trending_down_by_price_change(self):
        snap = MarketSnapshot(
            timestamp=datetime.now(UTC),
            volatility={"SOL": 0.02},
            order_book_imbalance={"SOL": 0.0},
        )
        regime, conf = auto_detect_regime(snap, price_change_1h={"SOL": -3.5})
        assert regime == MarketRegime.TRENDING_DOWN
        assert conf == 0.75

    def test_ranging_low_vol_neutral_imbalance(self):
        snap = MarketSnapshot(
            timestamp=datetime.now(UTC),
            volatility={"SOL": 0.01},
            order_book_imbalance={"SOL": 0.02},
        )
        regime, conf = auto_detect_regime(snap)
        assert regime == MarketRegime.RANGING
        assert conf == 0.65

    def test_low_volatility(self):
        snap = MarketSnapshot(
            timestamp=datetime.now(UTC),
            volatility={"SOL": 0.01},
            order_book_imbalance={"SOL": 0.08},
        )
        regime, conf = auto_detect_regime(snap)
        assert regime == MarketRegime.LOW_VOLATILITY
        assert conf == 0.55

    def test_bullish_pressure(self):
        snap = MarketSnapshot(
            timestamp=datetime.now(UTC),
            volatility={"SOL": 0.02},
            order_book_imbalance={"SOL": 0.15},
        )
        regime, conf = auto_detect_regime(snap)
        assert regime == MarketRegime.TRENDING_UP
        assert conf == 0.6

    def test_bearish_pressure(self):
        snap = MarketSnapshot(
            timestamp=datetime.now(UTC),
            volatility={"SOL": 0.02},
            order_book_imbalance={"SOL": -0.15},
        )
        regime, conf = auto_detect_regime(snap)
        assert regime == MarketRegime.TRENDING_DOWN
        assert conf == 0.6


class TestCausalChain:
    def test_empty_chain(self):
        chain = CausalChain(chain_id="test-chain")
        assert len(chain.events) == 0
        assert chain.get_narrative() == "No events recorded."

    def test_add_single_event(self):
        chain = CausalChain(chain_id="c1")
        event = chain.add_event("market", "Price spike detected", {"pct": 5.0})
        assert len(chain.events) == 1
        assert event.event_type == "market"
        assert event.caused_by is None
        assert event.led_to is None

    def test_chain_linking(self):
        chain = CausalChain(chain_id="c1")
        chain.add_event("market", "Volume spike")
        chain.add_event("action", "Entered long")
        chain.add_event("outcome", "Profit taken")

        assert len(chain.events) == 3
        assert chain.events[0].led_to == "c1-1"
        assert chain.events[1].caused_by == "c1-0"
        assert chain.events[1].led_to == "c1-2"
        assert chain.events[2].caused_by == "c1-1"

    def test_narrative(self):
        chain = CausalChain(chain_id="c1")
        chain.add_event("market", "Volume spike")
        chain.add_event("action", "Entered long")
        narrative = chain.get_narrative()
        assert "[market] Volume spike" in narrative
        assert "[action] Entered long" in narrative

    def test_to_dict(self):
        chain = CausalChain(chain_id="c1")
        chain.add_event("market", "Test event", {"key": "val"})
        data = chain.to_dict()
        assert data["chain_id"] == "c1"
        assert len(data["events"]) == 1
        assert data["events"][0]["data"]["key"] == "val"


class TestMultiFacetedLesson:
    def test_defaults(self):
        lesson = MultiFacetedLesson()
        assert lesson.tactical is None
        assert lesson.strategic is None
        assert lesson.psychological is None
        assert lesson.counter_factual is None
        assert lesson.confidence == 0.5

    def test_full_lesson(self):
        lesson = MultiFacetedLesson(
            tactical="Use tighter stops",
            strategic="Trail in uptrends",
            psychological="Avoid revenge trading",
            counter_factual="Waiting 5 min = 2% better entry",
            confidence=0.85,
        )
        assert lesson.confidence == 0.85

    def test_serialization_roundtrip(self):
        lesson = MultiFacetedLesson(
            tactical="Close half at R1",
            strategic="Trend follow",
            confidence=0.7,
        )
        data = lesson.to_dict()
        lesson2 = MultiFacetedLesson.from_dict(data)
        assert lesson2.tactical == "Close half at R1"
        assert lesson2.confidence == 0.7
        assert lesson2.psychological is None

    def test_get_summary_partial(self):
        lesson = MultiFacetedLesson(tactical="Use stops", strategic="Follow trends")
        summary = lesson.get_summary()
        assert "Tactical" in summary
        assert "Strategic" in summary
        assert "Psychological" not in summary

    def test_get_summary_empty(self):
        lesson = MultiFacetedLesson()
        assert "No lessons" in lesson.get_summary()


class TestTemporalPattern:
    def test_defaults(self):
        tp = TemporalPattern(hour_of_day=14, day_of_week=2)
        assert tp.trades_taken == 0
        assert tp.wins == 0
        assert tp.losses == 0
        assert tp.total_pnl == 0.0

    def test_win_rate_no_trades(self):
        tp = TemporalPattern(hour_of_day=10, day_of_week=0)
        assert tp.win_rate == 0.0

    def test_win_rate_with_trades(self):
        tp = TemporalPattern(hour_of_day=10, day_of_week=0, trades_taken=10, wins=7)
        assert tp.win_rate == 0.7

    def test_to_dict(self):
        tp = TemporalPattern(hour_of_day=14, day_of_week=3, trades_taken=5, wins=3, total_pnl=250.0)
        data = tp.to_dict()
        assert data["hour_of_day"] == 14
        assert data["day_of_week"] == 3
        assert data["total_pnl"] == 250.0


class TestEnhancedEpisode:
    def test_defaults(self):
        ep = EnhancedEpisode(
            episode_id="ep-test",
            name="Test",
            start_time=datetime.now(UTC),
        )
        assert ep.regime == MarketRegime.UNKNOWN
        assert ep.regime_confidence == 0.5
        assert ep.total_pnl == 0.0
        assert ep.lessons is None

    def test_serialization_roundtrip(self):
        now = datetime.now(UTC)
        snap = MarketSnapshot(
            timestamp=now,
            prices={"SOL": 150.0},
            volatility={"SOL": 0.03},
        )
        lesson = MultiFacetedLesson(tactical="Use stops", confidence=0.8)
        ep = EnhancedEpisode(
            episode_id="ep-test",
            name="Roundtrip Test",
            start_time=now,
            end_time=now + timedelta(hours=2),
            start_snapshot=snap,
            regime=MarketRegime.TRENDING_UP,
            regime_confidence=0.75,
            symbols_involved=["SOL"],
            total_pnl=500.0,
            win_rate=0.8,
            lessons=lesson,
            tags=["breakout"],
            hour_of_day=14,
            day_of_week=2,
        )
        data = ep.to_dict()
        ep2 = EnhancedEpisode.from_dict(data)
        assert ep2.episode_id == "ep-test"
        assert ep2.regime == MarketRegime.TRENDING_UP
        assert ep2.regime_confidence == 0.75
        assert ep2.total_pnl == 500.0
        assert ep2.start_snapshot is not None
        assert ep2.start_snapshot.prices["SOL"] == 150.0
        assert ep2.lessons.tactical == "Use stops"
        assert ep2.lessons.confidence == 0.8

    def test_get_summary(self):
        now = datetime.now(UTC)
        lesson = MultiFacetedLesson(tactical="Use stops")
        ep = EnhancedEpisode(
            episode_id="ep-test",
            name="Summary Test",
            start_time=now,
            end_time=now + timedelta(hours=3),
            regime=MarketRegime.BREAKOUT,
            regime_confidence=0.8,
            total_pnl=250.0,
            win_rate=0.75,
            sharpe_ratio=1.5,
            lessons=lesson,
            tags=["momentum"],
        )
        summary = ep.get_summary()
        assert "Summary Test" in summary
        assert "breakout" in summary
        assert "Tactical" in summary
        assert "momentum" in summary


class TestEnhancedMemoryBank:
    def setup_method(self):
        self.tmpdir = tempfile.mkdtemp()
        self.storage_path = os.path.join(self.tmpdir, "test_enhanced_memory.json")
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("GEMINI_API_KEY", None)
            os.environ.pop("GOOGLE_API_KEY", None)
            self.bank = EnhancedMemoryBank(storage_path=self.storage_path)

    def _make_snapshot(self, vol=0.03, imbalance=0.1, prices=None):
        return MarketSnapshot(
            timestamp=datetime.now(UTC),
            prices=prices or {"SOL": 150.0},
            volumes={"SOL": 1e9},
            volatility={"SOL": vol},
            order_book_imbalance={"SOL": imbalance},
            funding_rates={"SOL": 0.001},
        )

    def test_initial_state(self):
        assert len(self.bank.episodes) == 0
        assert self.bank.current_episode is None
        assert self.bank.model is None

    def test_start_episode_auto_regime(self):
        snap = self._make_snapshot(vol=0.05, imbalance=0.2)
        ep = self.bank.start_episode("Breakout Test", snap, ["SOL"])
        assert ep.regime == MarketRegime.BREAKOUT
        assert ep.regime_confidence == 0.8
        assert self.bank.current_episode is ep
        assert len(ep.causal_chain.events) == 1  # Start event recorded

    def test_record_market_event(self):
        snap = self._make_snapshot()
        self.bank.start_episode("Test", snap)
        self.bank.record_market_event("Big volume spike", {"volume": 3e9})
        assert len(self.bank.current_episode.causal_chain.events) == 2

    def test_record_action(self):
        snap = self._make_snapshot()
        self.bank.start_episode("Test", snap)
        self.bank.record_action("Entered long SOL")
        assert len(self.bank.current_episode.causal_chain.events) == 2

    def test_record_outcome(self):
        snap = self._make_snapshot()
        self.bank.start_episode("Test", snap)
        self.bank.record_outcome("TP1 hit")
        assert len(self.bank.current_episode.causal_chain.events) == 2

    def test_record_trade(self):
        snap = self._make_snapshot()
        self.bank.start_episode("Test", snap)
        self.bank.record_trade({"symbol": "SOL", "side": "BUY", "price": 150.0, "pnl": 50.0})
        assert len(self.bank.current_episode.trades) == 1
        assert len(self.bank.current_episode.causal_chain.events) == 2

    def test_record_trade_no_episode(self):
        self.bank.record_trade({"symbol": "SOL", "side": "BUY"})
        # Should not raise

    def test_end_episode_calculations(self):
        snap = self._make_snapshot()
        self.bank.start_episode("Calc Test", snap, ["SOL"])
        self.bank.record_trade({"pnl": 100.0})
        self.bank.record_trade({"pnl": -30.0})
        self.bank.record_trade({"pnl": 80.0})

        end_snap = self._make_snapshot()
        ep = self.bank.end_episode(end_snap)
        assert ep.total_pnl == 150.0
        assert ep.win_rate == pytest.approx(2 / 3, abs=0.01)
        assert ep.end_time is not None
        assert ep.end_snapshot is not None
        assert ep.episode_id in self.bank.episodes
        assert self.bank.current_episode is None

    def test_end_episode_sharpe(self):
        snap = self._make_snapshot()
        self.bank.start_episode("Sharpe Test", snap)
        self.bank.record_trade({"pnl": 100.0})
        self.bank.record_trade({"pnl": 50.0})
        self.bank.record_trade({"pnl": -20.0})
        ep = self.bank.end_episode()
        assert ep.sharpe_ratio > 0

    def test_end_episode_no_current(self):
        assert self.bank.end_episode() is None

    def test_persistence_roundtrip(self):
        snap = self._make_snapshot()
        self.bank.start_episode("Persist", snap, ["SOL"])
        self.bank.record_trade({"pnl": 100.0})
        self.bank.end_episode()

        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("GEMINI_API_KEY", None)
            os.environ.pop("GOOGLE_API_KEY", None)
            bank2 = EnhancedMemoryBank(storage_path=self.storage_path)
        assert len(bank2.episodes) == 1

    def test_find_similar_by_regime(self):
        # Manually create episodes with unique IDs to avoid timestamp collision
        for i, (regime, conf) in enumerate([
            (MarketRegime.BREAKOUT, 0.8),
            (MarketRegime.BREAKOUT, 0.75),
            (MarketRegime.RANGING, 0.65),
        ]):
            ep = EnhancedEpisode(
                episode_id=f"ep-regime-{i}",
                name=f"Test {i}",
                start_time=datetime(2026, 1, 15, 10 + i, 0, tzinfo=UTC),
                regime=regime,
                regime_confidence=conf,
                symbols_involved=["SOL"],
            )
            self.bank.episodes[ep.episode_id] = ep

        matches = self.bank.find_similar_episodes(regime=MarketRegime.BREAKOUT, limit=5)
        assert len(matches) >= 2

    def test_find_similar_limit(self):
        for i in range(10):
            ep = EnhancedEpisode(
                episode_id=f"ep-limit-{i}",
                name=f"EP {i}",
                start_time=datetime(2026, 1, 15, i, 0, tzinfo=UTC),
                symbols_involved=["SOL"],
            )
            self.bank.episodes[ep.episode_id] = ep
        matches = self.bank.find_similar_episodes(symbols=["SOL"], limit=3)
        assert len(matches) == 3

    def test_temporal_pattern_update(self):
        snap = self._make_snapshot()
        self.bank.start_episode("TP Test", snap, ["SOL"])
        self.bank.record_trade({"pnl": 50.0})
        self.bank.end_episode()

        assert len(self.bank.temporal_patterns) > 0
        pattern = list(self.bank.temporal_patterns.values())[0]
        assert pattern.trades_taken >= 1

    def test_get_temporal_insights_empty(self):
        insights = self.bank.get_temporal_insights()
        assert "message" in insights

    def test_get_temporal_insights_with_data(self):
        for i in range(3):
            snap = self._make_snapshot()
            self.bank.start_episode(f"EP {i}", snap, ["SOL"])
            self.bank.record_trade({"pnl": (i + 1) * 10.0})
            self.bank.end_episode()

        insights = self.bank.get_temporal_insights()
        assert "best_hour" in insights
        assert "worst_hour" in insights

    @pytest.mark.asyncio
    async def test_extract_lessons_mock(self):
        ep = EnhancedEpisode(
            episode_id="ep-test",
            name="Mock Test",
            start_time=datetime.now(UTC),
            causal_chain=CausalChain("ep-test"),
        )
        lessons = await self.bank.extract_multi_faceted_lessons(ep)
        assert lessons.tactical is not None
        assert lessons.confidence == 0.3

    @pytest.mark.asyncio
    async def test_recall_no_episodes(self):
        snap = self._make_snapshot()
        result = await self.bank.recall_for_decision("SOL", snap)
        assert "No relevant past" in result

    def test_get_stats(self):
        snap = self._make_snapshot()
        self.bank.start_episode("Stats Test", snap, ["SOL"])
        self.bank.record_trade({"pnl": 100.0})
        self.bank.end_episode()

        stats = self.bank.get_stats()
        assert stats["total_episodes"] == 1
        assert stats["total_trades"] == 1
        assert stats["total_pnl"] == 100.0
        assert "regime_distribution" in stats
        assert "temporal_insights" in stats


class TestEnhancedGlobalInstance:
    def test_get_enhanced_memory(self):
        import shared.enhanced_episodic_memory as module

        module._enhanced_memory = None
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("GEMINI_API_KEY", None)
            os.environ.pop("GOOGLE_API_KEY", None)
            inst = get_enhanced_memory()
            assert inst is not None
            inst2 = get_enhanced_memory()
            assert inst is inst2
        module._enhanced_memory = None
