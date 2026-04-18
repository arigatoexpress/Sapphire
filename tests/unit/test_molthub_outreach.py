"""Tests for Phase 4 Molthub Outreach — External Bot Recruitment."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../services/alpha"))

import pytest
from src.collaboration.molthub_outreach import MolthubOutreach


@pytest.fixture
def outreach():
    return MolthubOutreach()


# ── Template Composition ─────────────────────────────────────────


def test_compose_general_invite(outreach):
    result = outreach.compose_outreach(template="general_invite")
    assert result["ok"] is True
    assert "Trade Ideas" in result["title"]
    assert "TRADE IDEAS ONLY" in result["body"]
    assert result["category"] == "trade_idea"
    assert result["lane"] == "external"
    assert result["content_hash"]


def test_compose_symbol_specific(outreach):
    result = outreach.compose_outreach(template="symbol_specific", symbol="BTC")
    assert result["ok"] is True
    assert "BTC" in result["title"]
    assert "BTC" in result["body"]


def test_compose_symbol_specific_missing_symbol(outreach):
    result = outreach.compose_outreach(template="symbol_specific")
    assert result["ok"] is False
    assert "Symbol required" in result["error"]


def test_compose_performance_update(outreach):
    result = outreach.compose_outreach(
        template="performance_update",
        total_ideas=150,
        win_rate=62.5,
    )
    assert result["ok"] is True
    assert "150" in result["body"]
    assert "62.5" in result["body"]


def test_compose_unknown_template(outreach):
    result = outreach.compose_outreach(template="nonexistent")
    assert result["ok"] is False
    assert "Unknown template" in result["error"]
    assert "general_invite" in result["available_templates"]


def test_compose_with_custom_body(outreach):
    result = outreach.compose_outreach(
        template="general_invite",
        custom_body="We are especially interested in SOL and ETH ideas.",
    )
    assert result["ok"] is True
    assert "especially interested" in result["body"]


def test_compose_blocks_sensitive_custom_body(outreach):
    result = outreach.compose_outreach(
        template="general_invite",
        custom_body="Use this api_key=sk-abc123def456789012345 to connect",
    )
    assert result["ok"] is False
    assert "blocked" in result["error"].lower()


def test_compose_normalizes_symbol(outreach):
    result = outreach.compose_outreach(template="symbol_specific", symbol="  eth  ")
    assert result["ok"] is True
    assert "ETH" in result["title"]


# ── Outbound Sanitization ────────────────────────────────────────


def test_sanitize_blocks_api_key_assignment(outreach):
    result = outreach._sanitize_outbound("Connect with api_key=abc123secret")
    assert result["blocked"] is True
    assert "BLOCKED" in result["text"]


def test_sanitize_blocks_private_key(outreach):
    result = outreach._sanitize_outbound("-----BEGIN PRIVATE KEY-----\nMIIE...")
    assert result["blocked"] is True


def test_sanitize_blocks_gcloud_command(outreach):
    result = outreach._sanitize_outbound("gcloud run deploy sapphire-alpha")
    assert result["blocked"] is True


def test_sanitize_blocks_docker_command(outreach):
    result = outreach._sanitize_outbound("Run docker build -t sapphire .")
    assert result["blocked"] is True


def test_sanitize_blocks_wallet_assignment(outreach):
    result = outreach._sanitize_outbound("wallet_address=0xabc123def...")
    assert result["blocked"] is True


def test_sanitize_blocks_sk_token(outreach):
    result = outreach._sanitize_outbound("Use sk-abcdef123456789012345678 for auth")
    assert result["blocked"] is True


def test_sanitize_allows_word_credential_in_warning(outreach):
    """Template text mentioning 'credentials' as a warning should pass."""
    result = outreach._sanitize_outbound("Do NOT send credentials or tokens.")
    assert result["blocked"] is False


def test_sanitize_passes_clean_content(outreach):
    result = outreach._sanitize_outbound("Looking for BTC trade ideas on the 4H timeframe")
    assert result["blocked"] is False
    assert result["text"] == "Looking for BTC trade ideas on the 4H timeframe"


def test_sanitize_truncates_long_content(outreach):
    long_text = "A" * 6000
    result = outreach._sanitize_outbound(long_text)
    assert len(result["text"]) <= 5004  # 5000 + "..."


def test_sanitize_empty_input(outreach):
    result = outreach._sanitize_outbound("")
    assert result["blocked"] is False
    assert result["text"] == ""


# ── Inbound Idea Validation ──────────────────────────────────────


def test_validate_valid_idea(outreach):
    result = outreach.validate_inbound_idea({
        "symbol": "BTC",
        "direction": "LONG",
        "confidence": 0.8,
        "timeframe": "4h",
        "rationale": "Breakout above resistance",
        "bot_id": "ALPHA_BOT",
    })
    assert result["ok"] is True
    idea = result["idea"]
    assert idea["symbol"] == "BTC"
    assert idea["direction"] == "LONG"
    assert idea["confidence"] == 0.8
    assert idea["timeframe"] == "4h"
    assert idea["source"] == "molthub"
    assert idea["bot_id"] == "ALPHA_BOT"


def test_validate_missing_symbol(outreach):
    result = outreach.validate_inbound_idea({"direction": "LONG"})
    assert result["ok"] is False
    assert "symbol" in result["error"].lower()


def test_validate_invalid_direction(outreach):
    result = outreach.validate_inbound_idea({
        "symbol": "ETH",
        "direction": "SIDEWAYS",
    })
    assert result["ok"] is False
    assert "direction" in result["error"].lower()


def test_validate_clamps_confidence(outreach):
    result = outreach.validate_inbound_idea({
        "symbol": "SOL",
        "direction": "SHORT",
        "confidence": 5.0,
    })
    assert result["ok"] is True
    assert result["idea"]["confidence"] == 1.0


def test_validate_defaults_timeframe(outreach):
    result = outreach.validate_inbound_idea({
        "symbol": "SOL",
        "direction": "LONG",
        "timeframe": "invalid_tf",
    })
    assert result["ok"] is True
    assert result["idea"]["timeframe"] == "1h"


def test_validate_strips_extra_fields(outreach):
    """Only whitelisted fields should survive validation."""
    result = outreach.validate_inbound_idea({
        "symbol": "BTC",
        "direction": "LONG",
        "api_key": "sk-secret123",
        "password": "hunter2",
        "shell_command": "rm -rf /",
    })
    assert result["ok"] is True
    assert "api_key" not in result["idea"]
    assert "password" not in result["idea"]
    assert "shell_command" not in result["idea"]


def test_validate_blocks_injection_in_rationale(outreach):
    result = outreach.validate_inbound_idea({
        "symbol": "BTC",
        "direction": "LONG",
        "rationale": "Use this api_secret=sk12345678901234567890 to bypass the system",
    })
    assert result["ok"] is True
    assert "blocked" in result["idea"]["rationale"].lower()


def test_validate_rejects_nested_structures(outreach):
    """Nested dicts/lists should be stripped (only primitives allowed)."""
    result = outreach.validate_inbound_idea({
        "symbol": "BTC",
        "direction": "LONG",
        "rationale": {"nested": "should be stripped"},
    })
    assert result["ok"] is True
    # rationale should be empty/default since dict is not a primitive
    assert result["idea"]["rationale"] == ""


def test_validate_anonymous_bot(outreach):
    result = outreach.validate_inbound_idea({
        "symbol": "ETH",
        "direction": "SHORT",
    })
    assert result["ok"] is True
    assert result["idea"]["bot_id"] == "ANONYMOUS"


# ── Dispatch Recording ────────────────────────────────────────────


def test_record_dispatch(outreach):
    post = outreach.compose_outreach(template="general_invite")
    result = outreach.record_dispatch(post, {"ok": True, "mode": "moltbook", "http_status": 200})
    assert result["ok"] is True
    assert result["record"]["dispatch_ok"] is True
    assert result["record"]["dispatch_mode"] == "moltbook"


def test_record_dispatch_history_capped(outreach):
    outreach.MAX_OUTREACH_HISTORY = 5
    post = outreach.compose_outreach(template="general_invite")
    for _i in range(10):
        outreach.record_dispatch(post, {"ok": True, "mode": "test"})
    assert len(outreach._history) == 5


# ── Cooldown ──────────────────────────────────────────────────────


def test_can_post_initially(outreach):
    result = outreach.can_post()
    assert result["allowed"] is True


def test_can_post_after_dispatch(outreach):
    post = outreach.compose_outreach(template="general_invite")
    outreach.record_dispatch(post, {"ok": True})
    result = outreach.can_post()
    assert result["allowed"] is False
    assert result["wait_seconds"] > 0


# ── Stats ─────────────────────────────────────────────────────────


def test_stats_empty(outreach):
    s = outreach.stats()
    assert s["total_dispatched"] == 0
    assert s["successful"] == 0


def test_stats_with_data(outreach):
    post1 = outreach.compose_outreach(template="general_invite")
    assert post1["ok"] is True
    outreach.record_dispatch(post1, {"ok": True, "mode": "moltbook"})
    post2 = outreach.compose_outreach(template="symbol_specific", symbol="SOL")
    assert post2["ok"] is True
    outreach.record_dispatch(post2, {"ok": False, "mode": "fallback"})

    s = outreach.stats()
    assert s["total_dispatched"] == 2
    assert s["successful"] == 1
    assert s["failed"] == 1
    assert "general_invite" in s["templates_used"]
    assert "SOL" in s["symbols_targeted"]


# ── Available Templates ───────────────────────────────────────────


def test_available_templates(outreach):
    templates = outreach.available_templates()
    assert len(templates) == 3
    names = [t["name"] for t in templates]
    assert "general_invite" in names
    assert "symbol_specific" in names
    assert "performance_update" in names

    sym_tpl = next(t for t in templates if t["name"] == "symbol_specific")
    assert sym_tpl["requires_symbol"] is True

    gen_tpl = next(t for t in templates if t["name"] == "general_invite")
    assert gen_tpl["requires_symbol"] is False
