"""Tests that AgentGate enforcement is wired into critical engine operations.

These tests verify that the gate.require() calls are in the right places
and that PermissionDenied propagates correctly.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../services/alpha-engine"))

import pytest
from src.security.agent_permissions import (
    Capability,
    PermissionDenied,
    gate,
)

# ── Kill Switch ─────────────────────────────────────────────────


def test_kill_switch_allowed_for_sapphire():
    """SAPPHIRE has KILL_SWITCH capability."""
    assert gate.check("SAPPHIRE", Capability.KILL_SWITCH) is True


def test_kill_switch_allowed_for_obsidian():
    """OBSIDIAN has KILL_SWITCH capability."""
    assert gate.check("OBSIDIAN", Capability.KILL_SWITCH) is True


def test_kill_switch_denied_for_emerald():
    """EMERALD does NOT have KILL_SWITCH."""
    assert gate.check("EMERALD", Capability.KILL_SWITCH) is False


def test_kill_switch_denied_for_scout():
    """SCOUT does NOT have KILL_SWITCH."""
    assert gate.check("SCOUT", Capability.KILL_SWITCH) is False


def test_kill_switch_require_raises_for_scout():
    with pytest.raises(PermissionDenied) as exc_info:
        gate.require("SCOUT", Capability.KILL_SWITCH, "test_kill_switch")
    assert exc_info.value.agent_id == "SCOUT"
    assert exc_info.value.capability == Capability.KILL_SWITCH


# ── Trade Execution ─────────────────────────────────────────────


def test_trade_execute_allowed_for_sapphire():
    assert gate.check("SAPPHIRE", Capability.TRADE_EXECUTE) is True


def test_trade_execute_denied_for_obsidian():
    assert gate.check("OBSIDIAN", Capability.TRADE_EXECUTE) is False


def test_trade_execute_denied_for_emerald():
    assert gate.check("EMERALD", Capability.TRADE_EXECUTE) is False


def test_trade_execute_denied_for_scout():
    assert gate.check("SCOUT", Capability.TRADE_EXECUTE) is False


def test_trade_execute_require_raises_for_scout():
    with pytest.raises(PermissionDenied):
        gate.require("SCOUT", Capability.TRADE_EXECUTE, "manual_trade")


# ── Venue Control ───────────────────────────────────────────────


def test_venue_control_allowed_for_sapphire():
    assert gate.check("SAPPHIRE", Capability.VENUE_CONTROL) is True


def test_venue_control_allowed_for_obsidian():
    assert gate.check("OBSIDIAN", Capability.VENUE_CONTROL) is True


def test_venue_control_denied_for_emerald():
    assert gate.check("EMERALD", Capability.VENUE_CONTROL) is False


def test_venue_control_denied_for_scout():
    assert gate.check("SCOUT", Capability.VENUE_CONTROL) is False


# ── Autonomy Dispatch ───────────────────────────────────────────


def test_autonomy_dispatch_allowed_for_obsidian():
    assert gate.check("OBSIDIAN", Capability.AUTONOMY_DISPATCH) is True


def test_autonomy_dispatch_allowed_for_sapphire():
    """SAPPHIRE needs AUTONOMY_DISPATCH for scheduled_review cycles."""
    assert gate.check("SAPPHIRE", Capability.AUTONOMY_DISPATCH) is True


def test_autonomy_dispatch_denied_for_scout():
    assert gate.check("SCOUT", Capability.AUTONOMY_DISPATCH) is False


# ── System Config ───────────────────────────────────────────────


def test_system_config_allowed_for_obsidian():
    assert gate.check("OBSIDIAN", Capability.SYSTEM_CONFIG) is True


def test_system_config_allowed_for_sapphire():
    assert gate.check("SAPPHIRE", Capability.SYSTEM_CONFIG) is True


def test_system_config_denied_for_emerald():
    assert gate.check("EMERALD", Capability.SYSTEM_CONFIG) is False


def test_system_config_denied_for_scout():
    assert gate.check("SCOUT", Capability.SYSTEM_CONFIG) is False


# ── Forum Write ─────────────────────────────────────────────────


def test_forum_write_allowed_for_emerald():
    assert gate.check("EMERALD", Capability.FORUM_WRITE) is True


def test_forum_write_allowed_for_scout():
    """Scout CAN write to the forum — it's their communication channel."""
    assert gate.check("SCOUT", Capability.FORUM_WRITE) is True


def test_forum_write_allowed_for_sapphire():
    assert gate.check("SAPPHIRE", Capability.FORUM_WRITE) is True


# ── Skill Audit ─────────────────────────────────────────────────


def test_skill_audit_allowed_for_emerald():
    assert gate.check("EMERALD", Capability.SKILL_AUDIT) is True


def test_skill_audit_allowed_for_scout():
    assert gate.check("SCOUT", Capability.SKILL_AUDIT) is True


def test_skill_audit_denied_for_obsidian():
    """OBSIDIAN does not have SKILL_AUDIT — it's an Emerald/Scout job."""
    assert gate.check("OBSIDIAN", Capability.SKILL_AUDIT) is False


# ── AI Prompt ───────────────────────────────────────────────────


def test_ai_prompt_allowed_for_sapphire():
    assert gate.check("SAPPHIRE", Capability.AI_PROMPT) is True


def test_ai_prompt_allowed_for_obsidian():
    assert gate.check("OBSIDIAN", Capability.AI_PROMPT) is True


def test_ai_prompt_allowed_for_emerald():
    assert gate.check("EMERALD", Capability.AI_PROMPT) is True


def test_ai_prompt_denied_for_scout():
    """Scout CANNOT invoke AI prompts — prevents prompt injection amplification."""
    assert gate.check("SCOUT", Capability.AI_PROMPT) is False
    with pytest.raises(PermissionDenied):
        gate.require("SCOUT", Capability.AI_PROMPT, "chat_with_owner")


# ── Secret Access ───────────────────────────────────────────────


def test_secret_access_allowed_for_sapphire():
    assert gate.check("SAPPHIRE", Capability.SECRET_ACCESS) is True


def test_secret_access_allowed_for_obsidian():
    assert gate.check("OBSIDIAN", Capability.SECRET_ACCESS) is True


def test_secret_access_denied_for_emerald():
    assert gate.check("EMERALD", Capability.SECRET_ACCESS) is False


def test_secret_access_denied_for_scout():
    assert gate.check("SCOUT", Capability.SECRET_ACCESS) is False


# ── Cross-Cutting: Scout Can Do Nothing Dangerous ──────────────


def test_scout_total_lockout_from_dangerous_ops():
    """Scout must be denied ALL dangerous capabilities."""
    dangerous = [
        Capability.TRADE_EXECUTE,
        Capability.PORTFOLIO_READ,
        Capability.PORTFOLIO_WRITE,
        Capability.VENUE_CONTROL,
        Capability.KILL_SWITCH,
        Capability.SECRET_ACCESS,
        Capability.SYSTEM_CONFIG,
        Capability.AUTONOMY_DISPATCH,
        Capability.TELEGRAM_SEND,
        Capability.AI_PROMPT,
        Capability.MEMORY_WRITE,
        Capability.COGNITION_WRITE,
        Capability.MEDIA_PUBLISH,
    ]
    for cap in dangerous:
        assert gate.check("SCOUT", cap) is False, f"Scout should NOT have {cap.name}"


# ── Unknown Agent Has Zero Capabilities ────────────────────────


def test_unknown_agent_denied_everything():
    """An unregistered agent ID gets zero capabilities."""
    for cap in Capability:
        assert gate.check("ROGUE_AGENT", cap) is False, f"Unknown agent should lack {cap.name}"


def test_unknown_agent_require_raises():
    with pytest.raises(PermissionDenied):
        gate.require("ROGUE_AGENT", Capability.TRADE_EXECUTE, "rogue_trade")
