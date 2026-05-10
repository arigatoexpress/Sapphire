from __future__ import annotations

from scripts.ops.frontend_surface_inventory import SURFACE_DEFS, build_inventory


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
