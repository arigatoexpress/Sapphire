"""Guardrails for the dashboard surface inventory."""

from __future__ import annotations

import json

from scripts.ops.dashboard_surface_inventory import (
    DEFAULT_OUTPUT,
    LIFECYCLES,
    PRODUCT_MODULES,
    SAFETY_MODES,
    build_inventory,
)


def test_dashboard_surface_inventory_snapshot_is_current() -> None:
    inventory = build_inventory()
    committed = json.loads(DEFAULT_OUTPUT.read_text(encoding="utf-8"))

    assert committed == inventory
    assert inventory["summary"]["route_count"] >= 175
    assert inventory["summary"]["page_template_count"] == 46


def test_every_route_has_migration_owner_lifecycle_and_safety_mode() -> None:
    inventory = build_inventory()

    for route in inventory["routes"]:
        assert route["owner_module"] in PRODUCT_MODULES, route["rule"]
        assert route["lifecycle"] in LIFECYCLES, route["rule"]
        assert route["safety_mode"] in SAFETY_MODES, route["rule"]
        assert route["kind"] in {"api", "page", "static"}, route["rule"]
        assert route["source"] == "services/dashboard/app.py", route["rule"]


def test_every_page_template_has_migration_owner_and_safety_mode() -> None:
    inventory = build_inventory()

    routed_templates = {
        template for route in inventory["routes"] for template in route["templates"]
    }
    for template in inventory["templates"]:
        assert template["owner_module"] in PRODUCT_MODULES, template["template"]
        assert template["safety_mode"] in SAFETY_MODES, template["template"]
        assert template["lifecycle"] in LIFECYCLES, template["template"]
        if template["role"] == "page":
            assert template["template"] in routed_templates, template["template"]


def test_first_spine_classifies_stable_and_sensitive_routes() -> None:
    inventory = build_inventory()
    by_rule = {route["rule"]: route for route in inventory["routes"]}

    assert by_rule["/"]["owner_module"] == "Home / Worldline"
    assert by_rule["/"]["lifecycle"] == "keep"
    assert by_rule["/health"]["lifecycle"] == "keep"
    assert by_rule["/api/production/readiness"]["lifecycle"] == "keep"
    assert by_rule["/unified"]["lifecycle"] == "redirect"
    assert by_rule["/unified-dashboard"]["lifecycle"] == "redirect"
    assert by_rule["/api/x402/market-regime"]["lifecycle"] == "hard-stop"
    assert by_rule["/api/x402/market-regime"]["safety_mode"] == "blocked"
    assert by_rule["/api/trading/order-draft"]["safety_mode"] == "paper"
