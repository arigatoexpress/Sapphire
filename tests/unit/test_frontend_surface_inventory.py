from __future__ import annotations

from scripts.ops.frontend_surface_inventory import (
    ROUTE_CONTRACTS,
    SURFACE_DEFS,
    build_inventory,
)


def _surfaces_by_id() -> dict[str, dict[str, object]]:
    inventory = build_inventory()
    return {str(surface["surface_id"]): surface for surface in inventory["surfaces"]}


def test_frontend_surface_inventory_covers_known_sapphire_surfaces() -> None:
    inventory = build_inventory()
    surfaces = _surfaces_by_id()

    assert inventory["summary"]["surface_count"] == len(SURFACE_DEFS)
    assert inventory["summary"]["missing_surface_count"] == 0
    assert inventory["summary"]["missing_entrypoint_count"] == 0
    assert {
        "analytics_public_site",
        "analytics_admin",
        "ops_dashboard_jinja",
        "ops_dashboard_react_preview",
        "control_plane_static",
        "hackathon_frontend",
        "acquirer_public_site",
        "customer_static_site",
        "telegram_operator_surface",
    } <= set(surfaces)


def test_frontend_surface_inventory_separates_public_and_operator_boundaries() -> None:
    surfaces = _surfaces_by_id()

    assert surfaces["analytics_public_site"]["publicly_exposable"] is True
    assert surfaces["analytics_public_site"]["operator_sensitive"] is False
    assert surfaces["analytics_admin"]["boundary"] == "authenticated_admin"
    assert surfaces["analytics_admin"]["operator_sensitive"] is True
    assert surfaces["control_plane_static"]["boundary"] == "local_operator"
    assert surfaces["telegram_operator_surface"]["boundary"] == "telegram_operator"
    assert surfaces["telegram_operator_surface"]["operator_sensitive"] is True
    assert surfaces["telegram_operator_surface"]["root"] == "services/pm_bot"
    assert surfaces["telegram_operator_surface"]["entrypoints"] == ["services/pm_bot/server.py"]
    assert surfaces["telegram_operator_surface"]["lifecycle"] == "canonical_operator_surface"


def test_frontend_surface_inventory_marks_react_preview_as_primary_shell_candidate() -> None:
    react_preview = _surfaces_by_id()["ops_dashboard_react_preview"]

    assert react_preview["lifecycle"] == "promote_to_primary_shell"
    assert react_preview["package_scripts"] == ["build", "dev", "preview"]
    assert "React" in react_preview["stack"]
    assert "Vite" in react_preview["stack"]


def test_frontend_surface_inventory_records_safe_next_slices() -> None:
    for surface in build_inventory()["surfaces"]:
        assert surface["recommended_next_slice"]
        assert surface["verification"]
        assert surface["safety_notes"]


def test_frontend_surface_inventory_records_public_admin_route_contracts() -> None:
    inventory = build_inventory()
    contracts = {str(contract["path"]): contract for contract in inventory["route_contracts"]}

    assert inventory["summary"]["route_contract_count"] == len(ROUTE_CONTRACTS)
    assert inventory["summary"]["public_route_contract_count"] >= 10
    assert inventory["summary"]["admin_route_contract_count"] >= 10
    assert contracts["/api/summary"]["boundary"] == "public_safe"
    assert contracts["/api/summary"]["frontend_fetch"] is True
    assert contracts["/api/markets/snapshot"]["boundary"] == "public_safe"
    assert contracts["/api/admin/analysis"]["boundary"] == "authenticated_admin"
    assert contracts["/api/admin/analysis"]["expected_statuses"] == (401, 403, 503)
    assert contracts["/api/brain/synthesis?persist=1"]["boundary"] == ("authenticated_admin")


def test_public_homepage_fetches_have_public_contracts_only() -> None:
    inventory = build_inventory()
    fetches = {str(fetch["path"]): fetch for fetch in inventory["public_template_fetches"]}

    assert inventory["summary"]["public_template_fetch_count"] >= 15
    assert inventory["summary"]["public_template_fetch_missing_contract_count"] == 0
    assert inventory["summary"]["public_template_admin_fetch_count"] == 0
    assert inventory["summary"]["public_template_external_fetch_count"] == 0
    assert {
        "/api/summary",
        "/api/regime",
        "/api/silos/health",
        "/api/threats/live",
        "/api/timeseries/threats",
        "/api/brain/synthesis",
        "/api/failover/readiness",
        "/api/markets/snapshot",
    } <= set(fetches)
    assert all(
        fetch["boundary"] == "public_safe"
        for fetch in inventory["public_template_fetches"]
        if fetch["same_origin"]
    )
    assert {
        "services/analytics_dashboard/templates/p/brain.html",
        "services/analytics_dashboard/templates/p/markets.html",
        "services/analytics_dashboard/templates/p/system.html",
        "services/analytics_dashboard/templates/p/threats.html",
    } <= {str(fetch["template"]) for fetch in inventory["public_template_fetches"]}
