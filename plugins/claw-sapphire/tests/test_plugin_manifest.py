"""Tests for the claw-sapphire plugin manifest."""

from __future__ import annotations

import json
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parent.parent
MANIFEST_PATH = PLUGIN_ROOT / "plugin.json"


def _load_manifest() -> dict:
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


def test_manifest_registered_tools_are_intentional():
    """The registered plugin surface should stay explicit and stable."""
    manifest = _load_manifest()

    assert manifest["version"] == "0.6.0"

    tools = manifest["tools"]
    # Wave B.5 (2026-04-30) added sapphire_megaeth_protocols, bumping
    # the registered surface from 15 → 16. Salvage PR #615 (2026-05-03)
    # added sapphire_tradingview (read-only orchestrator surface), 16 → 17.
    # Bump this assertion as new registered tools land — keeping the count
    # check explicit catches accidental adds without a deliberate decision.
    assert len(tools) == 17

    expected_permissions = {
        "sapphire_dispatch": "workspace-write",
        "sapphire_verify": "read-only",
        "sapphire_budget": "read-only",
        "sapphire_state": "workspace-write",
        "sapphire_status": "read-only",
        "sapphire_notify": "read-only",
        "sapphire_health_check": "read-only",
        "sapphire_market": "read-only",
        "sapphire_predict_kronos": "workspace-write",
        "sapphire_threat_intel": "workspace-write",
        "sapphire_lumo_research": "read-only",
        "sapphire_starred_repos": "workspace-write",
        "sapphire_macro_data": "read-only",
        "sapphire_lead_engine": "workspace-write",
        "sapphire_trading_brain": "read-only",
        "sapphire_megaeth_protocols": "read-only",
        "sapphire_tradingview": "read-only",
    }

    assert [tool["name"] for tool in tools] == list(expected_permissions)

    for tool in tools:
        assert tool["requiredPermission"] == expected_permissions[tool["name"]]
        assert tool["inputSchema"]["type"] == "object"
        assert tool["inputSchema"]["additionalProperties"] is True
        tool_path = PLUGIN_ROOT.parent.parent / tool["args"][0]
        assert tool_path.exists(), f"Missing tool target for {tool['name']}: {tool_path}"
