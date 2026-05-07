"""Tests for the v2 dashboard Control Plane summary."""

from __future__ import annotations

from datetime import UTC, datetime

from services.dashboard.control_plane_summary import build_control_plane_summary


def test_control_plane_summary_uses_real_cards_without_live_settlement() -> None:
    summary = build_control_plane_summary(
        probe_services=False,
        now=datetime(2026, 5, 6, 23, 59, tzinfo=UTC),
    )

    assert summary["schema_version"] == 1
    assert summary["mode"] == "read_only"
    assert summary["safety"]["live_settlement_allowed"] is False
    assert summary["safety"]["real_trading_enabled"] is False
    assert summary["summary"]["card_count"] >= 6
    cards = {card["title"]: card for card in summary["cards"]}
    assert cards["x402 Product Spine"]["value"].startswith("9 products")
    assert "0 live settlement" in cards["x402 Product Spine"]["value"]
    assert cards["AgentWiki Builder Briefs"]["value"].startswith("4 briefs")
    assert cards["Commercial Safety Contract"]["mode"] == "blocked"
    assert cards["Dashboard Surface"]["source"]["path_or_url"].endswith(
        "services/dashboard/config/surface_inventory.json"
    )


def test_control_plane_summary_cards_follow_envelope_contract() -> None:
    summary = build_control_plane_summary(
        probe_services=False,
        now=datetime(2026, 5, 6, 23, 59, tzinfo=UTC),
    )

    for card in summary["cards"]:
        assert card["status"] in {"ok", "warn", "fail", "unknown"}
        assert card["mode"] in {"live", "read_only", "paper", "modeled", "stale", "blocked"}
        assert card["module"]
        assert card["title"]
        assert card["value"]
        assert card["summary"]
        assert card["source"]["kind"] in {"probe", "file", "script", "service", "manual"}
        assert "path_or_url" in card["source"]
        assert isinstance(card["actions"], list)


def test_control_plane_summary_rolls_up_all_product_modules() -> None:
    summary = build_control_plane_summary(
        probe_services=False,
        now=datetime(2026, 5, 6, 23, 59, tzinfo=UTC),
    )

    module_names = {module["name"] for module in summary["modules"]}
    assert {
        "Home / Worldline",
        "Operations",
        "Intelligence",
        "Markets",
        "Security",
        "Products / Diligence",
        "Automation",
        "Settings / Contracts",
    } <= module_names
