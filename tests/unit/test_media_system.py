"""Tests for the Sapphire social media system (Phase 6).

Covers:
- ContentGenerator quality scoring, slop detection, interval enforcement
- MediaManager queue management, approval workflows, retry logic
- Platform client initialization
- AgentGate enforcement on media operations
"""

import asyncio
import importlib.util
import sys
import time
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

ROOT_DIR = Path(__file__).resolve().parents[2]
MEDIA_DIR = ROOT_DIR / "services" / "alpha-engine" / "src" / "media"
SECURITY_DIR = ROOT_DIR / "services" / "alpha-engine" / "src" / "security"


def _load_module(path: Path, module_name: str):
    """Load a module from file path."""
    spec = importlib.util.spec_from_file_location(module_name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def _load_media_package():
    """Load the media package with proper parent so relative imports work."""
    src_dir = MEDIA_DIR.parent  # src/
    if str(src_dir) not in sys.path:
        sys.path.insert(0, str(src_dir))

    # Load sub-modules first so relative imports resolve
    twitter_mod = _load_module(MEDIA_DIR / "twitter.py", "media.twitter")
    substack_mod = _load_module(MEDIA_DIR / "substack.py", "media.substack")
    linkedin_mod = _load_module(MEDIA_DIR / "linkedin.py", "media.linkedin")

    # Create a fake package module
    import types
    pkg = types.ModuleType("media")
    pkg.__path__ = [str(MEDIA_DIR)]
    pkg.__package__ = "media"
    pkg.twitter = twitter_mod
    pkg.substack = substack_mod
    pkg.linkedin = linkedin_mod
    pkg.TwitterClient = twitter_mod.TwitterClient
    pkg.SubstackClient = substack_mod.SubstackClient
    pkg.LinkedInClient = linkedin_mod.LinkedInClient
    sys.modules["media"] = pkg

    # Now load manager with the package in place
    manager_mod = _load_module(MEDIA_DIR / "manager.py", "media.manager")
    return manager_mod, twitter_mod


# ── Module loading ──────────────────────────────────────────────

@pytest.fixture(scope="module")
def content_gen_module():
    return _load_module(MEDIA_DIR / "content_generator.py", "sapphire_content_generator")


@pytest.fixture(scope="module")
def manager_module():
    mgr_mod, _ = _load_media_package()
    return mgr_mod


@pytest.fixture(scope="module")
def twitter_module():
    _, tw_mod = _load_media_package()
    return tw_mod


# ── ContentGenerator Tests ──────────────────────────────────────


class TestQualityScoring:
    """Test the quality scoring system."""

    def test_clean_text_scores_high(self, content_gen_module):
        gen = content_gen_module.ContentGenerator()
        result = gen._score_quality(
            "We shipped fill confirmation with 50ms avg latency. "
            "Portfolio tracker shows 3.2% realized PnL this week across 47 trades.",
            "twitter",
        )
        assert result["score"] >= 0.8
        assert len(result["issues"]) == 0

    def test_slop_phrase_penalized(self, content_gen_module):
        gen = content_gen_module.ContentGenerator()
        result = gen._score_quality(
            "Let's dive in to the exciting times ahead. The future is bright for crypto trading.",
            "twitter",
        )
        assert result["score"] < 0.8
        assert any("slop" in issue for issue in result["issues"])

    def test_multiple_slop_phrases_penalized_more(self, content_gen_module):
        gen = content_gen_module.ContentGenerator()
        result = gen._score_quality(
            "Let's dive in! Exciting times! Stay tuned! Game-changer! Without further ado!",
            "twitter",
        )
        assert result["score"] <= 0.6
        assert any("slop" in issue for issue in result["issues"])

    def test_excessive_emojis_penalized(self, content_gen_module):
        gen = content_gen_module.ContentGenerator()
        result = gen._score_quality(
            "🚀🔥💎🌟✨🎉🎊🏆🥇⭐ Great news!",
            "twitter",
        )
        assert result["score"] <= 0.8
        assert any("emoji" in issue for issue in result["issues"])

    def test_over_length_twitter(self, content_gen_module):
        gen = content_gen_module.ContentGenerator()
        result = gen._score_quality("x" * 300, "twitter")
        assert any("over_length" in issue for issue in result["issues"])

    def test_under_length_substack(self, content_gen_module):
        gen = content_gen_module.ContentGenerator()
        result = gen._score_quality("Short article.", "substack")
        assert any("under_length" in issue for issue in result["issues"])

    def test_too_short_penalized(self, content_gen_module):
        gen = content_gen_module.ContentGenerator()
        result = gen._score_quality("Hi", "twitter")
        assert result["score"] <= 0.5
        assert any("too_short" in issue for issue in result["issues"])

    def test_repetition_detected(self, content_gen_module):
        gen = content_gen_module.ContentGenerator()
        result = gen._score_quality(
            "Great progress this week. Great progress this week. More updates coming.",
            "twitter",
        )
        assert any("repetition" in issue for issue in result["issues"])

    def test_score_clamped_to_zero_one(self, content_gen_module):
        gen = content_gen_module.ContentGenerator()
        # Force extremely bad content
        result = gen._score_quality("", "twitter")
        assert 0.0 <= result["score"] <= 1.0

    def test_linkedin_length_validation(self, content_gen_module):
        gen = content_gen_module.ContentGenerator()
        result = gen._score_quality("x" * 3500, "linkedin")
        assert any("over_length" in issue for issue in result["issues"])


class TestIntervalEnforcement:
    """Test min posting interval enforcement."""

    def test_first_post_always_allowed(self, content_gen_module):
        gen = content_gen_module.ContentGenerator()
        assert gen._check_interval("twitter") is True

    def test_interval_blocks_rapid_posts(self, content_gen_module):
        gen = content_gen_module.ContentGenerator()
        gen.last_generation["twitter"] = time.time()
        assert gen._check_interval("twitter") is False

    def test_interval_allows_after_wait(self, content_gen_module):
        gen = content_gen_module.ContentGenerator()
        gen.min_post_interval = 1  # 1 second for test
        gen.last_generation["twitter"] = time.time() - 2
        assert gen._check_interval("twitter") is True

    def test_different_platforms_independent(self, content_gen_module):
        gen = content_gen_module.ContentGenerator()
        gen.last_generation["twitter"] = time.time()
        assert gen._check_interval("twitter") is False
        assert gen._check_interval("substack") is True


class TestContentGeneration:
    """Test AI content generation flow."""

    def test_generate_tweet_no_gemini(self, content_gen_module):
        gen = content_gen_module.ContentGenerator(gemini_guard=None)
        result = asyncio.run(gen.generate_tweet({}, "test"))
        assert result["ok"] is False
        assert result["reason"] == "gemini_unavailable"

    def test_generate_tweet_success(self, content_gen_module):
        mock_gemini = MagicMock()
        mock_gemini.chat_with_owner = AsyncMock(
            return_value="Shipped 50ms fill confirmation. 47 trades, 3.2% realized PnL this week."
        )
        gen = content_gen_module.ContentGenerator(gemini_guard=mock_gemini)
        result = asyncio.run(gen.generate_tweet({"metrics": {"trades": 47}}, "weekly update"))
        assert result["ok"] is True
        assert result["platform"] == "twitter"
        assert "content" in result
        assert result["quality"]["score"] >= 0.6

    def test_generate_tweet_below_threshold(self, content_gen_module):
        mock_gemini = MagicMock()
        mock_gemini.chat_with_owner = AsyncMock(
            return_value="Let's dive in! Exciting times ahead! Stay tuned!"
        )
        gen = content_gen_module.ContentGenerator(gemini_guard=mock_gemini)
        gen.quality_threshold = 0.9
        result = asyncio.run(gen.generate_tweet({}, "test"))
        assert result["ok"] is False
        assert result["reason"] == "below_quality_threshold"
        assert "draft" in result

    def test_generate_tweet_interval_blocked(self, content_gen_module):
        gen = content_gen_module.ContentGenerator()
        gen.last_generation["twitter"] = time.time()
        result = asyncio.run(gen.generate_tweet({}, "test"))
        assert result["ok"] is False
        assert result["reason"] == "min_interval_not_met"

    def test_generate_substack_success(self, content_gen_module):
        long_content = "# Weekly Lab Note\n\n" + "x " * 300
        mock_gemini = MagicMock()
        mock_gemini.chat_with_owner = AsyncMock(return_value=long_content)
        gen = content_gen_module.ContentGenerator(gemini_guard=mock_gemini)
        result = asyncio.run(gen.generate_substack({"metrics": {"wins": 12}}, "progress"))
        assert result["ok"] is True
        assert result["platform"] == "substack"

    def test_generate_linkedin_success(self, content_gen_module):
        mock_gemini = MagicMock()
        mock_gemini.chat_with_owner = AsyncMock(
            return_value=(
                "This week our autonomous trading system processed 47 fills "
                "with a 3.2% realized PnL. The dual-speed cognition system "
                "caught 3 potential bad entries before execution."
            )
        )
        gen = content_gen_module.ContentGenerator(gemini_guard=mock_gemini)
        result = asyncio.run(gen.generate_linkedin({}, "weekly"))
        assert result["ok"] is True
        assert result["platform"] == "linkedin"

    def test_generate_for_platform_routing(self, content_gen_module):
        mock_gemini = MagicMock()
        mock_gemini.chat_with_owner = AsyncMock(return_value="Test content for routing.")
        gen = content_gen_module.ContentGenerator(gemini_guard=mock_gemini)

        result = asyncio.run(gen.generate_for_platform("twitter", {}, "test"))
        assert result["ok"] is True
        assert result["platform"] == "twitter"

    def test_generate_for_unknown_platform(self, content_gen_module):
        gen = content_gen_module.ContentGenerator()
        result = asyncio.run(gen.generate_for_platform("tiktok", {}, "test"))
        assert result["ok"] is False
        assert "unknown_platform" in result["reason"]

    def test_stats_tracking(self, content_gen_module):
        mock_gemini = MagicMock()
        mock_gemini.chat_with_owner = AsyncMock(return_value="Good quality tweet about trading metrics.")
        gen = content_gen_module.ContentGenerator(gemini_guard=mock_gemini)
        gen.min_post_interval = 0  # Disable for test

        asyncio.run(gen.generate_tweet({}, "test1"))
        asyncio.run(gen.generate_tweet({}, "test2"))
        stats = gen.stats()
        assert stats["generation_count"] == 2
        assert "twitter" in stats["last_generation"]


class TestPromptBuilding:
    """Test context formatting for prompts."""

    def test_format_context_with_metrics(self, content_gen_module):
        gen = content_gen_module.ContentGenerator()
        result = gen._format_context_block({
            "metrics": {"total_trades": 47, "win_rate": 68.5},
        })
        assert "total_trades" in result
        assert "47" in result

    def test_format_context_with_forum(self, content_gen_module):
        gen = content_gen_module.ContentGenerator()
        result = gen._format_context_block({
            "forum_topics": [
                {"title": "SOL breakout analysis", "lane": "trade_idea"},
            ],
        })
        assert "SOL breakout" in result
        assert "trade_idea" in result

    def test_format_context_with_events(self, content_gen_module):
        gen = content_gen_module.ContentGenerator()
        result = gen._format_context_block({
            "events": ["Fill confirmed: SOL LONG 2.5 @ $148.30"],
        })
        assert "Fill confirmed" in result

    def test_format_empty_context(self, content_gen_module):
        gen = content_gen_module.ContentGenerator()
        result = gen._format_context_block({})
        assert "no data available" in result

    def test_format_context_with_swarm(self, content_gen_module):
        gen = content_gen_module.ContentGenerator()
        result = gen._format_context_block({
            "swarm": {"active_bots": 3, "consensus_score": 0.85},
        })
        assert "active_bots" in result

    def test_format_context_with_memory(self, content_gen_module):
        gen = content_gen_module.ContentGenerator()
        result = gen._format_context_block({
            "memory_insights": ["High volume breakouts on SOL tend to revert within 4h"],
        })
        assert "High volume" in result


# ── MediaManager Tests ──────────────────────────────────────────


class TestMediaManager:
    """Test the MediaManager queue and workflow logic."""

    def test_request_publish_owner_approval(self, manager_module):
        mgr = manager_module.MediaManager()
        mgr.mode = "owner_approval"
        result = mgr.request_publish(
            topic="weekly", title="Test", body="Body", targets=["twitter"]
        )
        assert result["status"] == "pending_approval"
        assert result["request_id"] in mgr.pending_approvals

    def test_request_publish_auto_post(self, manager_module):
        mgr = manager_module.MediaManager()
        mgr.mode = "auto_post"
        result = mgr.request_publish(
            topic="weekly", title="Test", body="Body", targets=["twitter"]
        )
        assert result["status"] == "queued"
        assert len(mgr.queue) == 1

    def test_request_publish_draft_only(self, manager_module):
        mgr = manager_module.MediaManager()
        mgr.mode = "draft_only"
        result = mgr.request_publish(
            topic="weekly", title="Test", body="Body", targets=["twitter"]
        )
        assert result["status"] == "draft"
        assert len(mgr.queue) == 0

    def test_approve_request(self, manager_module):
        mgr = manager_module.MediaManager()
        mgr.mode = "owner_approval"
        result = mgr.request_publish(
            topic="weekly", title="Test", body="Body", targets=["x"]
        )
        req_id = result["request_id"]
        assert mgr.approve_request(req_id) is True
        assert req_id not in mgr.pending_approvals
        assert len(mgr.queue) == 1

    def test_reject_request(self, manager_module):
        mgr = manager_module.MediaManager()
        mgr.mode = "owner_approval"
        result = mgr.request_publish(
            topic="test", title="Test", body="Body", targets=["twitter"]
        )
        req_id = result["request_id"]
        assert mgr.reject_request(req_id) is True
        assert req_id not in mgr.pending_approvals
        assert len(mgr.queue) == 0

    def test_approve_nonexistent_request(self, manager_module):
        mgr = manager_module.MediaManager()
        assert mgr.approve_request("nonexistent") is False

    def test_reject_nonexistent_request(self, manager_module):
        mgr = manager_module.MediaManager()
        assert mgr.reject_request("nonexistent") is False

    def test_set_mode(self, manager_module):
        mgr = manager_module.MediaManager()
        assert mgr.set_mode("auto") == "auto_post"
        assert mgr.set_mode("draft") == "draft_only"
        assert mgr.set_mode("approval") == "owner_approval"

    def test_normalize_targets(self, manager_module):
        mgr = manager_module.MediaManager()
        assert "twitter" in mgr._normalize_targets(["x"])
        assert "twitter" in mgr._normalize_targets(["twitter"])
        assert "substack" in mgr._normalize_targets(["substack"])
        assert "linkedin" in mgr._normalize_targets(["li"])

    def test_normalize_targets_default(self, manager_module):
        mgr = manager_module.MediaManager()
        result = mgr._normalize_targets([])
        assert "twitter" in result

    def test_status_snapshot(self, manager_module):
        mgr = manager_module.MediaManager()
        snap = mgr.get_status_snapshot()
        assert "mode" in snap
        assert "queue_depth" in snap
        assert "pending_approvals" in snap

    def test_status_report_format(self, manager_module):
        mgr = manager_module.MediaManager()
        report = mgr.get_status_report()
        assert "SAPPHIRE MEDIA STATUS" in report
        assert "Mode:" in report

    def test_latest_resolve(self, manager_module):
        mgr = manager_module.MediaManager()
        mgr.mode = "owner_approval"
        r1 = mgr.request_publish(topic="a", title="A", body="a", targets=["twitter"])
        r2 = mgr.request_publish(topic="b", title="B", body="b", targets=["twitter"])
        resolved = mgr._resolve_id("latest")
        assert resolved == r2["request_id"]

    def test_request_id_increments(self, manager_module):
        mgr = manager_module.MediaManager()
        mgr.mode = "auto_post"
        r1 = mgr.request_publish(topic="a", title="A", body="a", targets=["twitter"])
        r2 = mgr.request_publish(topic="b", title="B", body="b", targets=["twitter"])
        assert r1["request_id"] != r2["request_id"]


class TestMediaManagerPublishLoop:
    """Test the async publish execution."""

    def test_execute_publish_success(self, manager_module):
        mgr = manager_module.MediaManager()
        mgr.twitter = MagicMock()
        mgr.twitter.ready = True
        mgr.twitter.post = AsyncMock(return_value="tweet-123")
        mgr.telegram = AsyncMock()
        mgr.telegram.send_message = AsyncMock()

        item = {
            "request_id": "test-001",
            "targets": ["twitter"],
            "title": "Test",
            "body": "Body",
            "attempts": 0,
        }
        asyncio.run(mgr._execute_publish(item))
        mgr.twitter.post.assert_awaited_once()

    def test_execute_publish_retry_on_failure(self, manager_module):
        mgr = manager_module.MediaManager()
        mgr.twitter = MagicMock()
        mgr.twitter.ready = False
        mgr.telegram = AsyncMock()
        mgr.telegram.send_message = AsyncMock()

        item = {
            "request_id": "test-002",
            "targets": ["twitter"],
            "title": "Test",
            "body": "Body",
            "attempts": 0,
        }
        asyncio.run(mgr._execute_publish(item))
        # Should be re-queued for retry
        assert len(mgr.queue) == 1

    def test_execute_publish_max_attempts_exceeded(self, manager_module):
        mgr = manager_module.MediaManager()
        mgr.max_attempts = 2
        mgr.twitter = MagicMock()
        mgr.twitter.ready = False
        mgr.telegram = AsyncMock()
        mgr.telegram.send_message = AsyncMock()

        item = {
            "request_id": "test-003",
            "targets": ["twitter"],
            "title": "Test",
            "body": "Body",
            "attempts": 2,  # Already at max
        }
        asyncio.run(mgr._execute_publish(item))
        # Should NOT be re-queued — final failure
        assert len(mgr.queue) == 0


# ── Slop Pattern Tests ──────────────────────────────────────────


class TestSlopPatterns:
    """Validate all slop patterns match correctly."""

    @pytest.mark.parametrize("text", [
        "Let's dive in to trading",
        "In this article we explore",
        "In conclusion, the results show",
        "Buckle up for the ride",
        "This is a game-changer",
        "Exciting times in crypto",
        "Stay tuned for updates",
        "Without further ado",
        "The future is bright for DeFi",
        "Unlocking the power of AI",
        "Revolutionizing crypto trading",
        "Transforming the trading landscape",
    ])
    def test_slop_phrase_detected(self, content_gen_module, text):
        gen = content_gen_module.ContentGenerator()
        result = gen._score_quality(text + " " * 50, "linkedin")  # Pad to avoid too_short
        assert any("slop" in issue for issue in result["issues"]), f"Missed slop in: {text}"

    @pytest.mark.parametrize("text", [
        "Shipped fill confirmation loop with 50ms latency target.",
        "Portfolio tracker processed 47 trades this week with 68% win rate.",
        "Dual-speed cognition caught 3 false positives in paper mode.",
        "Lighter WS feed reconnection improved from 3s to exponential backoff.",
    ])
    def test_clean_text_not_flagged(self, content_gen_module, text):
        gen = content_gen_module.ContentGenerator()
        result = gen._score_quality(text, "twitter")
        assert not any("slop" in issue for issue in result["issues"]), f"False positive on: {text}"


# ── Telegram /media generate Command Tests ──────────────────────

TELEGRAM_BOT_PATH = ROOT_DIR / "services" / "alpha-engine" / "shared" / "telegram_bot.py"


@pytest.fixture(scope="module")
def telegram_module():
    return _load_module(TELEGRAM_BOT_PATH, "sapphire_telegram_bot_media")


class TestMediaTelegramCommands:
    """Test /media generate command parsing and dispatch."""

    def test_media_generate_twitter(self, telegram_module):
        """/media generate twitter dispatches MEDIA_GENERATE."""
        callback = AsyncMock()
        bot = telegram_module.TelegramPlatformBot(
            bot_token="token", chat_id="12345", command_callback=callback,
        )
        bot.send_message = AsyncMock()
        bot.send_as = AsyncMock()
        asyncio.run(
            bot._process_update(
                {"message": {"chat": {"id": "12345"}, "text": "/media generate twitter weekly update"}}
            )
        )
        callback.assert_awaited_once()
        _, symbol, action, _ = callback.await_args.args
        assert action == "MEDIA_GENERATE"
        import json
        payload = json.loads(symbol)
        assert payload["platform"] == "twitter"
        assert payload["topic"] == "weekly update"

    def test_media_generate_substack(self, telegram_module):
        """/media generate substack dispatches MEDIA_GENERATE."""
        callback = AsyncMock()
        bot = telegram_module.TelegramPlatformBot(
            bot_token="token", chat_id="12345", command_callback=callback,
        )
        bot.send_message = AsyncMock()
        bot.send_as = AsyncMock()
        asyncio.run(
            bot._process_update(
                {"message": {"chat": {"id": "12345"}, "text": "/media generate substack"}}
            )
        )
        callback.assert_awaited_once()
        _, symbol, action, _ = callback.await_args.args
        assert action == "MEDIA_GENERATE"
        import json
        payload = json.loads(symbol)
        assert payload["platform"] == "substack"

    def test_media_generate_default_platform(self, telegram_module):
        """/media generate with no platform defaults to twitter."""
        callback = AsyncMock()
        bot = telegram_module.TelegramPlatformBot(
            bot_token="token", chat_id="12345", command_callback=callback,
        )
        bot.send_message = AsyncMock()
        bot.send_as = AsyncMock()
        asyncio.run(
            bot._process_update(
                {"message": {"chat": {"id": "12345"}, "text": "/media generate"}}
            )
        )
        callback.assert_awaited_once()
        _, symbol, action, _ = callback.await_args.args
        assert action == "MEDIA_GENERATE"
        import json
        payload = json.loads(symbol)
        assert payload["platform"] == "twitter"

    def test_media_status_still_works(self, telegram_module):
        """/media status dispatches MEDIA_STATUS."""
        callback = AsyncMock()
        bot = telegram_module.TelegramPlatformBot(
            bot_token="token", chat_id="12345", command_callback=callback,
        )
        bot.send_message = AsyncMock()
        bot.send_as = AsyncMock()
        asyncio.run(
            bot._process_update(
                {"message": {"chat": {"id": "12345"}, "text": "/media status"}}
            )
        )
        callback.assert_awaited_once()
        _, _, action, _ = callback.await_args.args
        assert action == "MEDIA_STATUS"

    def test_media_publish_still_works(self, telegram_module):
        """/media publish dispatches MEDIA_PUBLISH."""
        callback = AsyncMock()
        bot = telegram_module.TelegramPlatformBot(
            bot_token="token", chat_id="12345", command_callback=callback,
        )
        bot.send_message = AsyncMock()
        bot.send_as = AsyncMock()
        asyncio.run(
            bot._process_update(
                {"message": {"chat": {"id": "12345"}, "text": "/media publish weekly"}}
            )
        )
        callback.assert_awaited_once()
        _, _, action, _ = callback.await_args.args
        assert action == "MEDIA_PUBLISH"
