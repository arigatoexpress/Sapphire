"""Unit tests for the Agent Capability Permission System."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../services/alpha-engine"))

import pytest
from src.security.agent_permissions import (
    CAPABILITY_RISK_TIER,
    EMERALD_CAPABILITIES,
    OBSIDIAN_CAPABILITIES,
    SAPPHIRE_CAPABILITIES,
    SCOUT_CAPABILITIES,
    AgentGate,
    ApprovalPolicy,
    Capability,
    PermissionDenied,
)


def _gate():
    return AgentGate()


# ── Sapphire Capabilities ───────────────────────────────────────


def test_sapphire_can_execute_trades():
    g = _gate()
    assert g.check("SAPPHIRE", Capability.TRADE_EXECUTE) is True


def test_sapphire_can_access_secrets():
    g = _gate()
    assert g.check("SAPPHIRE", Capability.SECRET_ACCESS) is True


def test_sapphire_can_kill_switch():
    g = _gate()
    assert g.check("SAPPHIRE", Capability.KILL_SWITCH) is True


def test_sapphire_can_dispatch_autonomy():
    """SAPPHIRE needs AUTONOMY_DISPATCH for scheduled_review cycles."""
    g = _gate()
    assert g.check("SAPPHIRE", Capability.AUTONOMY_DISPATCH) is True


# ── Obsidian Capabilities ────────────────────────────────────────


def test_obsidian_can_dispatch_autonomy():
    g = _gate()
    assert g.check("OBSIDIAN", Capability.AUTONOMY_DISPATCH) is True


def test_obsidian_cannot_execute_trades():
    g = _gate()
    assert g.check("OBSIDIAN", Capability.TRADE_EXECUTE) is False


def test_obsidian_can_venue_control():
    g = _gate()
    assert g.check("OBSIDIAN", Capability.VENUE_CONTROL) is True


# ── Emerald Capabilities ─────────────────────────────────────────


def test_emerald_can_audit_skills():
    g = _gate()
    assert g.check("EMERALD", Capability.SKILL_AUDIT) is True


def test_emerald_can_moderate_forum():
    g = _gate()
    assert g.check("EMERALD", Capability.FORUM_MODERATE) is True


def test_emerald_cannot_access_secrets():
    g = _gate()
    assert g.check("EMERALD", Capability.SECRET_ACCESS) is False


def test_emerald_cannot_execute_trades():
    g = _gate()
    assert g.check("EMERALD", Capability.TRADE_EXECUTE) is False


# ── Scout Capabilities (MOST RESTRICTED) ─────────────────────────


def test_scout_can_read_forum():
    g = _gate()
    assert g.check("SCOUT", Capability.FORUM_READ) is True


def test_scout_can_write_forum():
    g = _gate()
    assert g.check("SCOUT", Capability.FORUM_WRITE) is True


def test_scout_can_access_moltbook():
    g = _gate()
    assert g.check("SCOUT", Capability.MOLTBOOK_READ) is True
    assert g.check("SCOUT", Capability.MOLTBOOK_WRITE) is True


def test_scout_cannot_execute_trades():
    g = _gate()
    assert g.check("SCOUT", Capability.TRADE_EXECUTE) is False


def test_scout_cannot_read_portfolio():
    g = _gate()
    assert g.check("SCOUT", Capability.PORTFOLIO_READ) is False


def test_scout_cannot_access_secrets():
    g = _gate()
    assert g.check("SCOUT", Capability.SECRET_ACCESS) is False


def test_scout_cannot_send_telegram():
    g = _gate()
    assert g.check("SCOUT", Capability.TELEGRAM_SEND) is False


def test_scout_cannot_access_ai_prompt():
    g = _gate()
    assert g.check("SCOUT", Capability.AI_PROMPT) is False


def test_scout_cannot_kill_switch():
    g = _gate()
    assert g.check("SCOUT", Capability.KILL_SWITCH) is False


def test_scout_cannot_control_venues():
    g = _gate()
    assert g.check("SCOUT", Capability.VENUE_CONTROL) is False


def test_scout_cannot_config_system():
    g = _gate()
    assert g.check("SCOUT", Capability.SYSTEM_CONFIG) is False


def test_scout_cannot_dispatch_autonomy():
    g = _gate()
    assert g.check("SCOUT", Capability.AUTONOMY_DISPATCH) is False


def test_scout_cannot_read_memory():
    g = _gate()
    assert g.check("SCOUT", Capability.MEMORY_READ) is False


def test_scout_cannot_read_cognition():
    g = _gate()
    assert g.check("SCOUT", Capability.COGNITION_READ) is False


# ── Require (Exception) ──────────────────────────────────────────


def test_require_raises_permission_denied():
    g = _gate()
    with pytest.raises(PermissionDenied) as exc_info:
        g.require("SCOUT", Capability.TRADE_EXECUTE)
    assert "SCOUT" in str(exc_info.value)
    assert "TRADE_EXECUTE" in str(exc_info.value)


def test_require_passes_for_valid_capability():
    g = _gate()
    g.require("SAPPHIRE", Capability.TRADE_EXECUTE)  # should not raise


def test_require_with_detail_message():
    g = _gate()
    with pytest.raises(PermissionDenied) as exc_info:
        g.require("SCOUT", Capability.SECRET_ACCESS, detail="attempted to read .env")
    assert "attempted to read .env" in str(exc_info.value)


# ── Unknown Agents ────────────────────────────────────────────────


def test_unknown_agent_has_no_capabilities():
    g = _gate()
    assert g.check("UNKNOWN_BOT", Capability.FORUM_READ) is False
    assert g.check("UNKNOWN_BOT", Capability.TRADE_EXECUTE) is False


def test_unknown_agent_require_raises():
    g = _gate()
    with pytest.raises(PermissionDenied):
        g.require("MALICIOUS_BOT", Capability.SECRET_ACCESS)


# ── Case Insensitivity ───────────────────────────────────────────


def test_agent_id_case_insensitive():
    g = _gate()
    assert g.check("sapphire", Capability.TRADE_EXECUTE) is True
    assert g.check("Sapphire", Capability.TRADE_EXECUTE) is True
    assert g.check("SAPPHIRE", Capability.TRADE_EXECUTE) is True


# ── Audit Log and Stats ──────────────────────────────────────────


def test_stats_tracking():
    g = _gate()
    g.check("SAPPHIRE", Capability.TRADE_EXECUTE)  # granted
    g.check("SCOUT", Capability.TRADE_EXECUTE)  # denied
    g.check("SCOUT", Capability.SECRET_ACCESS)  # denied

    stats = g.stats()
    assert stats["total_checks"] == 3
    assert stats["granted"] == 1
    assert stats["denied"] == 2


def test_recent_denials():
    g = _gate()
    try:
        g.require("SCOUT", Capability.SECRET_ACCESS, detail="test denial")
    except PermissionDenied:
        pass

    denials = g.recent_denials()
    assert len(denials) >= 1
    assert denials[-1]["agent_id"] == "SCOUT"
    assert denials[-1]["capability"] == "SECRET_ACCESS"


# ── Custom Agent Registration ─────────────────────────────────────


def test_register_custom_agent():
    g = _gate()
    g.register_agent("CUSTOM_BOT", frozenset({Capability.FORUM_READ}))
    assert g.check("CUSTOM_BOT", Capability.FORUM_READ) is True
    assert g.check("CUSTOM_BOT", Capability.TRADE_EXECUTE) is False


def test_agent_capabilities_returns_frozenset():
    g = _gate()
    caps = g.agent_capabilities("SCOUT")
    assert isinstance(caps, frozenset)
    assert Capability.FORUM_READ in caps
    assert Capability.TRADE_EXECUTE not in caps


# ── Completeness Checks ──────────────────────────────────────────


def test_scout_has_minimal_capabilities():
    """Scout should have the fewest capabilities of any agent."""
    assert len(SCOUT_CAPABILITIES) < len(EMERALD_CAPABILITIES)
    assert len(SCOUT_CAPABILITIES) < len(OBSIDIAN_CAPABILITIES)
    assert len(SCOUT_CAPABILITIES) < len(SAPPHIRE_CAPABILITIES)


def test_no_agent_has_all_capabilities():
    """No single agent should have every capability."""
    all_caps = set(Capability)
    for name, caps in [
        ("SAPPHIRE", SAPPHIRE_CAPABILITIES),
        ("OBSIDIAN", OBSIDIAN_CAPABILITIES),
        ("EMERALD", EMERALD_CAPABILITIES),
        ("SCOUT", SCOUT_CAPABILITIES),
    ]:
        assert caps < all_caps, f"{name} has ALL capabilities — violates least-privilege"


# ── Code & Infrastructure Capabilities (Full Autonomy) ─────────────


def test_obsidian_can_write_code():
    g = _gate()
    assert g.check("OBSIDIAN", Capability.CODE_WRITE) is True


def test_obsidian_can_deploy_code():
    g = _gate()
    assert g.check("OBSIDIAN", Capability.CODE_DEPLOY) is True


def test_obsidian_can_modify_infrastructure():
    g = _gate()
    assert g.check("OBSIDIAN", Capability.INFRASTRUCTURE_MODIFY) is True


def test_obsidian_can_trigger_ci():
    g = _gate()
    assert g.check("OBSIDIAN", Capability.CI_CD_TRIGGER) is True


def test_emerald_can_write_code():
    g = _gate()
    assert g.check("EMERALD", Capability.CODE_WRITE) is True


def test_emerald_can_review_code():
    g = _gate()
    assert g.check("EMERALD", Capability.CODE_REVIEW) is True


def test_emerald_cannot_deploy():
    g = _gate()
    assert g.check("EMERALD", Capability.CODE_DEPLOY) is False


def test_emerald_cannot_modify_infrastructure():
    g = _gate()
    assert g.check("EMERALD", Capability.INFRASTRUCTURE_MODIFY) is False


def test_sapphire_can_read_code():
    g = _gate()
    assert g.check("SAPPHIRE", Capability.CODE_READ) is True


def test_sapphire_can_review_code():
    g = _gate()
    assert g.check("SAPPHIRE", Capability.CODE_REVIEW) is True


def test_sapphire_cannot_write_code():
    g = _gate()
    assert g.check("SAPPHIRE", Capability.CODE_WRITE) is False


def test_sapphire_cannot_deploy_code():
    g = _gate()
    assert g.check("SAPPHIRE", Capability.CODE_DEPLOY) is False


def test_scout_cannot_write_code():
    g = _gate()
    assert g.check("SCOUT", Capability.CODE_WRITE) is False


def test_scout_cannot_deploy_code():
    g = _gate()
    assert g.check("SCOUT", Capability.CODE_DEPLOY) is False


def test_scout_cannot_monitor_health():
    g = _gate()
    assert g.check("SCOUT", Capability.HEALTH_MONITOR) is False


def test_scout_has_no_new_capabilities():
    """Scout should still have exactly 6 capabilities — unchanged from pre-autonomy."""
    assert len(SCOUT_CAPABILITIES) == 6


# ── Risk Tier Mapping ──────────────────────────────────────────────


def test_risk_tier_covers_all_capabilities():
    """Every capability should have a risk tier assigned."""
    for cap in Capability:
        assert cap in CAPABILITY_RISK_TIER, f"{cap.name} missing from CAPABILITY_RISK_TIER"


def test_risk_tier_values_valid():
    """All risk tier values should be one of the three valid tiers."""
    valid = {"low", "medium", "high"}
    for cap, tier in CAPABILITY_RISK_TIER.items():
        assert tier in valid, f"{cap.name} has invalid tier '{tier}'"


def test_code_deploy_is_high_risk():
    assert CAPABILITY_RISK_TIER[Capability.CODE_DEPLOY] == "high"


def test_infrastructure_modify_is_high_risk():
    assert CAPABILITY_RISK_TIER[Capability.INFRASTRUCTURE_MODIFY] == "high"


def test_code_write_is_medium_risk():
    assert CAPABILITY_RISK_TIER[Capability.CODE_WRITE] == "medium"


def test_code_read_is_low_risk():
    assert CAPABILITY_RISK_TIER[Capability.CODE_READ] == "low"


def test_health_monitor_is_low_risk():
    assert CAPABILITY_RISK_TIER[Capability.HEALTH_MONITOR] == "low"


# ── Approval Policy ───────────────────────────────────────────────


def test_approval_policy_low_risk_auto_approves():
    policy = ApprovalPolicy()
    assert policy.evaluate("OBSIDIAN", Capability.CODE_READ) == "auto_approve"


def test_approval_policy_medium_risk_notify_proceed():
    policy = ApprovalPolicy()
    assert policy.evaluate("OBSIDIAN", Capability.CODE_WRITE) == "notify_proceed"


def test_approval_policy_high_risk_require_approval():
    policy = ApprovalPolicy()
    assert policy.evaluate("OBSIDIAN", Capability.CODE_DEPLOY) == "require_approval"


def test_approval_policy_kill_switch_require_approval():
    policy = ApprovalPolicy()
    assert policy.evaluate("SAPPHIRE", Capability.KILL_SWITCH) == "require_approval"
