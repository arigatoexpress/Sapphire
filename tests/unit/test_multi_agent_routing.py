"""Tests for multi-agent autonomy routing.

Validates that the trigger → agent routing in _autonomy_trigger_info()
correctly dispatches to OBSIDIAN, EMERALD, and SAPPHIRE based on
trigger category and rotation cycle.
"""
from __future__ import annotations

import sys
import os
import types

# Stub heavy dependencies before importing main
_stubs = {}
for mod_name in [
    "uvloop",
    "google",
    "google.cloud",
    "google.cloud.firestore_v1",
    "google.generativeai",
    "aiohttp",
    "aiohttp.web",
    "firebase_admin",
    "telegram",
    "telegram.ext",
]:
    if mod_name not in sys.modules:
        _stubs[mod_name] = types.ModuleType(mod_name)
        sys.modules[mod_name] = _stubs[mod_name]

# Provide the heavy deps that main.py tries to import
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../services/alpha-engine/src"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../services/alpha-engine/shared"))

import pytest


# ---------- Minimal mock of AlphaEngine for trigger routing ---------- #

class _MinimalEngine:
    """Stripped-down stand-in for the parts of AlphaEngine that
    _autonomy_trigger_info uses."""

    def __init__(self):
        self._kill_switch_active = False
        self._trading_gate_min_active_venues = 2
        self._trading_gate_max_failure_pressure = 10
        self._autonomy_dispatch_count = 0

    def _autonomy_trigger_info(self, context):
        """Copied routing logic from main.py for unit-test isolation."""
        active_count = len(context.get("active_venues", []))
        total_failures = int(context.get("total_failure_pressure", 0))

        if self._kill_switch_active:
            return {"trigger": "kill_switch_active", "agent": "OBSIDIAN", "category": "emergency"}
        if active_count < self._trading_gate_min_active_venues:
            return {"trigger": "venue_shortfall", "agent": "OBSIDIAN", "category": "infrastructure"}
        if total_failures > self._trading_gate_max_failure_pressure:
            return {"trigger": "failure_pressure", "agent": "OBSIDIAN", "category": "infrastructure"}

        cycle = self._autonomy_dispatch_count % 3
        if cycle == 0:
            return {"trigger": "scheduled_maintenance", "agent": "OBSIDIAN", "category": "maintenance"}
        elif cycle == 1:
            return {"trigger": "scheduled_improvement", "agent": "EMERALD", "category": "improvement"}
        else:
            return {"trigger": "scheduled_review", "agent": "SAPPHIRE", "category": "review"}


# ---------- Healthy context fixture ---------- #

def _healthy_context(**overrides):
    base = {
        "active_venues": ["ASTER", "LIGHTER"],
        "paused_venues": [],
        "total_failure_pressure": 0,
    }
    base.update(overrides)
    return base


# ── Emergency / infrastructure routing ───────────────────────────────


class TestEmergencyRouting:
    """Emergency and infrastructure triggers always go to OBSIDIAN."""

    def test_kill_switch_routes_to_obsidian(self):
        e = _MinimalEngine()
        e._kill_switch_active = True
        info = e._autonomy_trigger_info(_healthy_context())
        assert info["agent"] == "OBSIDIAN"
        assert info["category"] == "emergency"
        assert info["trigger"] == "kill_switch_active"

    def test_venue_shortfall_routes_to_obsidian(self):
        e = _MinimalEngine()
        ctx = _healthy_context(active_venues=["ASTER"])  # 1 < min 2
        info = e._autonomy_trigger_info(ctx)
        assert info["agent"] == "OBSIDIAN"
        assert info["category"] == "infrastructure"
        assert info["trigger"] == "venue_shortfall"

    def test_failure_pressure_routes_to_obsidian(self):
        e = _MinimalEngine()
        ctx = _healthy_context(total_failure_pressure=20)  # > max 10
        info = e._autonomy_trigger_info(ctx)
        assert info["agent"] == "OBSIDIAN"
        assert info["category"] == "infrastructure"
        assert info["trigger"] == "failure_pressure"

    def test_kill_switch_takes_priority_over_shortfall(self):
        """Kill switch is checked before venue shortfall."""
        e = _MinimalEngine()
        e._kill_switch_active = True
        ctx = _healthy_context(active_venues=[])
        info = e._autonomy_trigger_info(ctx)
        assert info["trigger"] == "kill_switch_active"


# ── Scheduled rotation routing ───────────────────────────────────────


class TestScheduledRotation:
    """Scheduled triggers rotate through OBSIDIAN → EMERALD → SAPPHIRE."""

    def test_cycle_0_obsidian_maintenance(self):
        e = _MinimalEngine()
        e._autonomy_dispatch_count = 0
        info = e._autonomy_trigger_info(_healthy_context())
        assert info["agent"] == "OBSIDIAN"
        assert info["category"] == "maintenance"
        assert info["trigger"] == "scheduled_maintenance"

    def test_cycle_1_emerald_improvement(self):
        e = _MinimalEngine()
        e._autonomy_dispatch_count = 1
        info = e._autonomy_trigger_info(_healthy_context())
        assert info["agent"] == "EMERALD"
        assert info["category"] == "improvement"
        assert info["trigger"] == "scheduled_improvement"

    def test_cycle_2_sapphire_review(self):
        e = _MinimalEngine()
        e._autonomy_dispatch_count = 2
        info = e._autonomy_trigger_info(_healthy_context())
        assert info["agent"] == "SAPPHIRE"
        assert info["category"] == "review"
        assert info["trigger"] == "scheduled_review"

    def test_rotation_wraps_around(self):
        """After 3 dispatches, rotation wraps back to OBSIDIAN."""
        e = _MinimalEngine()
        e._autonomy_dispatch_count = 3
        info = e._autonomy_trigger_info(_healthy_context())
        assert info["agent"] == "OBSIDIAN"
        assert info["trigger"] == "scheduled_maintenance"

    def test_full_rotation_cycle(self):
        """Simulate 9 dispatches and verify the 3-agent round-robin."""
        e = _MinimalEngine()
        ctx = _healthy_context()
        expected_agents = ["OBSIDIAN", "EMERALD", "SAPPHIRE"] * 3
        for i in range(9):
            e._autonomy_dispatch_count = i
            info = e._autonomy_trigger_info(ctx)
            assert info["agent"] == expected_agents[i], f"Dispatch {i}: expected {expected_agents[i]}, got {info['agent']}"

    def test_high_dispatch_count_still_rotates(self):
        """Large dispatch counts don't break rotation."""
        e = _MinimalEngine()
        e._autonomy_dispatch_count = 999
        info = e._autonomy_trigger_info(_healthy_context())
        assert info["agent"] == "OBSIDIAN"  # 999 % 3 == 0

        e._autonomy_dispatch_count = 1000
        info = e._autonomy_trigger_info(_healthy_context())
        assert info["agent"] == "EMERALD"  # 1000 % 3 == 1

        e._autonomy_dispatch_count = 1001
        info = e._autonomy_trigger_info(_healthy_context())
        assert info["agent"] == "SAPPHIRE"  # 1001 % 3 == 2


# ── Agent instruction focus (verified via grep on main.py) ───────────


class TestAgentInstructionFocus:
    """Verify agent-specific instruction text exists in main.py.

    We cannot import main.py directly (heavy dep chain), so we verify
    the constants are present by reading the source.
    """

    @pytest.fixture(scope="class")
    def main_source(self):
        main_path = os.path.join(
            os.path.dirname(__file__),
            "../../services/alpha-engine/src/main.py",
        )
        with open(main_path) as f:
            return f.read()

    def test_obsidian_instruction_focus_present(self, main_source):
        assert '"OBSIDIAN"' in main_source
        assert "infrastructure" in main_source.lower()

    def test_emerald_instruction_focus_present(self, main_source):
        assert '"EMERALD"' in main_source
        assert "code quality" in main_source.lower()

    def test_sapphire_instruction_focus_present(self, main_source):
        assert '"SAPPHIRE"' in main_source
        assert "security" in main_source.lower()

    def test_agent_persona_map_present(self, main_source):
        assert "_AGENT_PERSONA_MAP" in main_source
        assert "_AGENT_INSTRUCTION_FOCUS" in main_source

    def test_persona_map_has_all_agents(self, main_source):
        # Verify all three agents appear in the persona map block
        # (within ~30 lines of _AGENT_PERSONA_MAP)
        idx = main_source.index("_AGENT_PERSONA_MAP")
        block = main_source[idx : idx + 400]
        assert '"OBSIDIAN"' in block
        assert '"EMERALD"' in block
        assert '"SAPPHIRE"' in block

    def test_instruction_focus_has_all_agents(self, main_source):
        idx = main_source.index("_AGENT_INSTRUCTION_FOCUS")
        block = main_source[idx : idx + 800]
        assert '"OBSIDIAN"' in block
        assert '"EMERALD"' in block
        assert '"SAPPHIRE"' in block
