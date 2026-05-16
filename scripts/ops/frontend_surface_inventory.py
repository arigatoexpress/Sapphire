#!/usr/bin/env python3
"""Inventory Sapphire frontend surfaces and their public/operator boundaries."""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
GENERATOR = "scripts/ops/frontend_surface_inventory.py"

PUBLIC_BOUNDARIES = {
    "public_safe",
    "public_buyer",
    "public_demo",
    "public_customer",
}
OPERATOR_BOUNDARIES = {
    "authenticated_admin",
    "local_operator",
    "operator_console",
    "telegram_operator",
}
EXCLUDED_PARTS = {
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".venv",
    "__pycache__",
    "build",
    "dist",
    "node_modules",
}


@dataclass(frozen=True)
class SurfaceDefinition:
    surface_id: str
    label: str
    root: str
    entrypoints: tuple[str, ...]
    stack: tuple[str, ...]
    audience: str
    boundary: str
    owner_module: str
    lifecycle: str
    risk_level: str
    safety_notes: tuple[str, ...]
    verification: tuple[str, ...]
    recommended_next_slice: str


@dataclass(frozen=True)
class SurfaceInventoryEntry:
    surface_id: str
    label: str
    root: str
    exists: bool
    entrypoints: list[str]
    missing_entrypoints: list[str]
    stack: list[str]
    audience: str
    boundary: str
    owner_module: str
    lifecycle: str
    risk_level: str
    operator_sensitive: bool
    publicly_exposable: bool
    file_count: int
    package_scripts: list[str]
    safety_notes: list[str]
    verification: list[str]
    recommended_next_slice: str


@dataclass(frozen=True)
class RouteBoundaryContract:
    path: str
    method: str
    surface_id: str
    boundary: str
    exposure: str
    expected_statuses: tuple[int, ...]
    source: str
    verification: tuple[str, ...]
    frontend_fetch: bool = False


@dataclass(frozen=True)
class PublicTemplateFetch:
    path: str
    template: str
    helper: str
    boundary: str
    contract_present: bool
    admin_route: bool
    same_origin: bool


SURFACE_DEFS: tuple[SurfaceDefinition, ...] = (
    SurfaceDefinition(
        surface_id="analytics_public_site",
        label="Analytics public site",
        root="services/analytics_dashboard",
        entrypoints=(
            "services/analytics_dashboard/app.py",
            "services/analytics_dashboard/templates/index.html",
            "services/analytics_dashboard/templates/p/system.html",
        ),
        stack=("Flask", "Jinja", "CSS"),
        audience="public visitors and buyer-safe demos",
        boundary="public_safe",
        owner_module="Public / Buyer",
        lifecycle="split_public_from_admin",
        risk_level="medium",
        safety_notes=(
            "Public pages must stay redacted and summary-level.",
            "Raw operational evidence and customer/internal controls belong behind admin.",
        ),
        verification=(
            "python3 scripts/ops/public_boundary_smoke.py --help",
            "pytest tests/unit/test_services_analytics_dashboard.py tests/unit/test_analytics_subpages.py -q",
        ),
        recommended_next_slice=(
            "Keep the public route as a concise buyer-safe shell and move raw readiness "
            "detail into authenticated admin templates."
        ),
    ),
    SurfaceDefinition(
        surface_id="analytics_admin",
        label="Analytics admin console",
        root="services/analytics_dashboard",
        entrypoints=(
            "services/analytics_dashboard/app.py",
            "services/analytics_dashboard/templates/admin.html",
            "services/analytics_dashboard/templates/admin_login.html",
        ),
        stack=("Flask", "Jinja", "passkey/admin auth"),
        audience="Ari and authenticated operators",
        boundary="authenticated_admin",
        owner_module="Admin / Operations",
        lifecycle="extract_operator_surface",
        risk_level="high",
        safety_notes=(
            "Do not leak admin-only raw status, controls, customer detail, or local paths.",
            "Public demos should link to summaries, not admin routes.",
        ),
        verification=(
            "pytest tests/unit/test_analytics_admin_auth.py -q",
            "pytest tests/unit/test_services_analytics_dashboard.py -q",
        ),
        recommended_next_slice=(
            "Define a smaller admin information architecture before adding more controls."
        ),
    ),
    SurfaceDefinition(
        surface_id="ops_dashboard_jinja",
        label="Legacy operations dashboard",
        root="services/dashboard",
        entrypoints=(
            "services/dashboard/app.py",
            "services/dashboard/templates/base.html",
            "services/dashboard/templates/pages/overview.html",
        ),
        stack=("Flask", "Jinja", "Chart.js"),
        audience="operators and internal demos",
        boundary="operator_console",
        owner_module="Operations",
        lifecycle="collapse_into_workbench_modules",
        risk_level="high",
        safety_notes=(
            "Trading, Telegram, local runtime, and x402 routes must advertise dry-run/read-only mode.",
            "Do not turn modeled or paper-only data into live-production claims.",
        ),
        verification=(
            "python3 scripts/ops/dashboard_surface_inventory.py --check",
            "pytest tests/unit/test_dashboard_surface_inventory.py -q",
        ),
        recommended_next_slice=(
            "Use the existing route inventory to collapse pages into home, operations, "
            "intelligence, markets, products, automation, and settings modules."
        ),
    ),
    SurfaceDefinition(
        surface_id="ops_dashboard_react_preview",
        label="React operations preview",
        root="services/dashboard/frontend",
        entrypoints=(
            "services/dashboard/frontend/package.json",
            "services/dashboard/frontend/src/App.tsx",
            "services/dashboard/frontend/src/api/controlPlane.ts",
        ),
        stack=("React", "Vite", "TypeScript"),
        audience="operators testing the next dashboard shell",
        boundary="local_operator",
        owner_module="Operations",
        lifecycle="promote_to_primary_shell",
        risk_level="medium",
        safety_notes=(
            "Keep API calls read-only until controls have explicit confirmations.",
            "Browser verification is required before claiming UI quality.",
        ),
        verification=(
            "npm --prefix services/dashboard/frontend run build",
            "python3 scripts/ops/dashboard_surface_inventory.py --check",
        ),
        recommended_next_slice=(
            "Promote this into the canonical workbench shell: left nav, central evidence "
            "canvas, and right provenance/action rail."
        ),
    ),
    SurfaceDefinition(
        surface_id="control_plane_static",
        label="Control-plane static workbench",
        root="services/control-plane/app/frontend",
        entrypoints=(
            "services/control-plane/app/frontend/index.html",
            "services/control-plane/app/frontend/assets/app.js",
            "services/control-plane/app/main.py",
        ),
        stack=("FastAPI static files", "vanilla JS", "CSS"),
        audience="local operators",
        boundary="local_operator",
        owner_module="Runtime / Control Plane",
        lifecycle="keep_operator_only_until_capability_model",
        risk_level="high",
        safety_notes=(
            "This surface can describe local runtimes and agent activity.",
            "Keep it local/operator-only until capability scopes and auth are explicit.",
        ),
        verification=(
            "pytest tests/unit/test_control_plane_event_stream.py -q",
            "pytest tests/unit/test_control_plane_summary.py -q",
        ),
        recommended_next_slice=(
            "Extract local-machine and Telegram runtime state into explicit read-only "
            "capabilities before adding controls."
        ),
    ),
    SurfaceDefinition(
        surface_id="hackathon_frontend",
        label="Hackathon demo frontend",
        root="services/hackathon_frontend",
        entrypoints=(
            "services/hackathon_frontend/app.py",
            "services/hackathon_frontend/templates/index.html",
            "services/hackathon_frontend/static/cards.js",
        ),
        stack=("Flask", "Jinja", "vanilla JS"),
        audience="judges and hackathon reviewers",
        boundary="public_demo",
        owner_module="Hackathon",
        lifecycle="extract_or_retire_after_demo",
        risk_level="medium",
        safety_notes=(
            "Demo copy must be judge-legible and honest about simulated or paper-only paths.",
            "Do not couple this to live Telegram, trading, or local runtime controls.",
        ),
        verification=(
            "pytest tests/unit/test_dashboard_x402_products.py -q",
            "pytest tests/unit/test_dashboard_x402_agentwiki.py -q",
        ),
        recommended_next_slice=(
            "Convert reusable demo cards into static data or a standalone satellite repo."
        ),
    ),
    SurfaceDefinition(
        surface_id="acquirer_public_site",
        label="Acquirer public microsite",
        root="web/acquirer",
        entrypoints=("web/acquirer/index.html", "web/acquirer/assets/styles.css"),
        stack=("static HTML", "CSS"),
        audience="buyers, partners, and external reviewers",
        boundary="public_buyer",
        owner_module="Public / Buyer",
        lifecycle="keep_public_safe",
        risk_level="low",
        safety_notes=(
            "Screenshots and claims must be buyer-safe and sourced from approved captures.",
            "Do not expose operational internals as proof material.",
        ),
        verification=(
            "python3 scripts/ops/dashboard_public_demo_readiness.py --no-write",
            "pytest tests/unit/test_dashboard_public_demo_readiness.py -q",
        ),
        recommended_next_slice=(
            "Refresh screenshots only through the public-demo readiness workflow."
        ),
    ),
    SurfaceDefinition(
        surface_id="customer_static_site",
        label="Customer static landing page",
        root="web/customer",
        entrypoints=("web/customer/index.html", "web/customer/assets/styles.css"),
        stack=("static HTML", "CSS"),
        audience="customer-facing visitors",
        boundary="public_customer",
        owner_module="Public / Customer",
        lifecycle="keep_or_merge_into_public_site",
        risk_level="low",
        safety_notes=(
            "Keep customer copy generic and free of operational/customer record detail.",
        ),
        verification=("python3 -m compileall web/customer",),
        recommended_next_slice=(
            "Decide whether this remains a standalone static page or folds into the "
            "analytics public site navigation."
        ),
    ),
    SurfaceDefinition(
        surface_id="telegram_operator_surface",
        label="PM bot Telegram operator surface",
        root="services/pm_bot",
        entrypoints=("services/pm_bot/server.py",),
        stack=("Python", "FastAPI", "Telegram webhook", "draft queue"),
        audience="Ari in Telegram",
        boundary="telegram_operator",
        owner_module="Runtime / PM Bot",
        lifecycle="canonical_operator_surface",
        risk_level="high",
        safety_notes=(
            "PM bot is the single Telegram ingress owner.",
            "Non-command updates and producer alerts must queue PM-bot-reviewed drafts.",
            "Keep polling and direct live sends disabled outside explicit break-glass windows.",
        ),
        verification=(
            "python3 -m py_compile services/pm_bot/server.py",
            "python3 scripts/ops/telegram_sender_audit.py --json",
        ),
        recommended_next_slice=(
            "Add an operator review UI for queued drafts before broadening agent-group "
            "Telegram participation."
        ),
    ),
)

ROUTE_CONTRACTS: tuple[RouteBoundaryContract, ...] = (
    RouteBoundaryContract(
        path="/",
        method="GET",
        surface_id="analytics_public_site",
        boundary="public_safe",
        exposure="public_html",
        expected_statuses=(200,),
        source="services/analytics_dashboard/app.py",
        verification=("scripts/ops/public_boundary_smoke.py",),
    ),
    RouteBoundaryContract(
        path="/p/brain",
        method="GET",
        surface_id="analytics_public_site",
        boundary="public_safe",
        exposure="public_html",
        expected_statuses=(200,),
        source="services/analytics_dashboard/app.py",
        verification=("scripts/ops/public_boundary_smoke.py",),
    ),
    RouteBoundaryContract(
        path="/p/system",
        method="GET",
        surface_id="analytics_public_site",
        boundary="public_safe",
        exposure="public_html",
        expected_statuses=(200,),
        source="services/analytics_dashboard/app.py",
        verification=("scripts/ops/public_boundary_smoke.py",),
    ),
    RouteBoundaryContract(
        path="/p/0guard",
        method="GET",
        surface_id="analytics_public_site",
        boundary="public_safe",
        exposure="public_html",
        expected_statuses=(200,),
        source="services/analytics_dashboard/app.py",
        verification=("scripts/ops/public_boundary_smoke.py",),
    ),
    RouteBoundaryContract(
        path="/p/wildfire",
        method="GET",
        surface_id="analytics_public_site",
        boundary="public_safe",
        exposure="public_html",
        expected_statuses=(200,),
        source="services/analytics_dashboard/app.py",
        verification=("scripts/ops/public_boundary_smoke.py",),
    ),
    RouteBoundaryContract(
        path="/p/regional",
        method="GET",
        surface_id="analytics_public_site",
        boundary="public_safe",
        exposure="public_html",
        expected_statuses=(200,),
        source="services/analytics_dashboard/app.py",
        verification=("scripts/ops/public_boundary_smoke.py",),
    ),
    RouteBoundaryContract(
        path="/p/help",
        method="GET",
        surface_id="analytics_public_site",
        boundary="public_safe",
        exposure="public_html",
        expected_statuses=(200,),
        source="services/analytics_dashboard/app.py",
        verification=("scripts/ops/public_boundary_smoke.py",),
    ),
    RouteBoundaryContract(
        path="/api/projects",
        method="GET",
        surface_id="analytics_public_site",
        boundary="public_safe",
        exposure="public_json",
        expected_statuses=(200,),
        source="services/analytics_dashboard/app.py",
        verification=("scripts/ops/public_boundary_smoke.py",),
    ),
    RouteBoundaryContract(
        path="/api/summary",
        method="GET",
        surface_id="analytics_public_site",
        boundary="public_safe",
        exposure="public_json",
        expected_statuses=(200,),
        source="services/analytics_dashboard/app.py",
        verification=("scripts/ops/public_boundary_smoke.py",),
        frontend_fetch=True,
    ),
    RouteBoundaryContract(
        path="/api/0guard/progress",
        method="GET",
        surface_id="analytics_public_site",
        boundary="public_safe",
        exposure="public_json",
        expected_statuses=(200,),
        source="services/analytics_dashboard/og_guard.py",
        verification=("tests/unit/test_analytics_subpages.py",),
        frontend_fetch=True,
    ),
    RouteBoundaryContract(
        path="/api/regime",
        method="GET",
        surface_id="analytics_public_site",
        boundary="public_safe",
        exposure="public_json",
        expected_statuses=(200,),
        source="services/analytics_dashboard/app.py",
        verification=("tests/unit/test_services_analytics_dashboard.py",),
        frontend_fetch=True,
    ),
    RouteBoundaryContract(
        path="/api/silos/health",
        method="GET",
        surface_id="analytics_public_site",
        boundary="public_safe",
        exposure="public_json",
        expected_statuses=(200,),
        source="services/analytics_dashboard/app.py",
        verification=("scripts/ops/public_boundary_smoke.py",),
        frontend_fetch=True,
    ),
    RouteBoundaryContract(
        path="/api/threats/live",
        method="GET",
        surface_id="analytics_public_site",
        boundary="public_safe",
        exposure="public_json",
        expected_statuses=(200,),
        source="services/analytics_dashboard/app.py",
        verification=("tests/unit/test_services_analytics_dashboard.py",),
        frontend_fetch=True,
    ),
    RouteBoundaryContract(
        path="/api/timeseries/threats",
        method="GET",
        surface_id="analytics_public_site",
        boundary="public_safe",
        exposure="public_json",
        expected_statuses=(200,),
        source="services/analytics_dashboard/app.py",
        verification=("tests/unit/test_services_analytics_dashboard.py",),
        frontend_fetch=True,
    ),
    RouteBoundaryContract(
        path="/api/brain/synthesis",
        method="GET",
        surface_id="analytics_public_site",
        boundary="public_safe",
        exposure="public_json",
        expected_statuses=(200,),
        source="services/analytics_dashboard/app.py",
        verification=("scripts/ops/public_boundary_smoke.py",),
        frontend_fetch=True,
    ),
    RouteBoundaryContract(
        path="/api/failover/readiness",
        method="GET",
        surface_id="analytics_public_site",
        boundary="public_safe",
        exposure="public_json",
        expected_statuses=(200,),
        source="services/analytics_dashboard/app.py",
        verification=("scripts/ops/public_boundary_smoke.py",),
        frontend_fetch=True,
    ),
    RouteBoundaryContract(
        path="/api/markets/snapshot",
        method="GET",
        surface_id="analytics_public_site",
        boundary="public_safe",
        exposure="public_json",
        expected_statuses=(200,),
        source="services/analytics_dashboard/markets.py",
        verification=("scripts/ops/sapphirealpha_production_smoke.py",),
        frontend_fetch=True,
    ),
    RouteBoundaryContract(
        path="/admin",
        method="GET",
        surface_id="analytics_admin",
        boundary="authenticated_admin",
        exposure="passkey_gate",
        expected_statuses=(302, 401, 403, 503),
        source="services/analytics_dashboard/app.py",
        verification=("scripts/ops/public_boundary_smoke.py",),
    ),
    RouteBoundaryContract(
        path="/api/admin/whoami",
        method="GET",
        surface_id="analytics_admin",
        boundary="authenticated_admin",
        exposure="admin_json",
        expected_statuses=(401, 403, 503),
        source="services/analytics_dashboard/auth.py",
        verification=("scripts/ops/public_boundary_smoke.py",),
    ),
    RouteBoundaryContract(
        path="/api/admin/analysis",
        method="GET",
        surface_id="analytics_admin",
        boundary="authenticated_admin",
        exposure="admin_json",
        expected_statuses=(401, 403, 503),
        source="services/analytics_dashboard/app.py",
        verification=("scripts/ops/public_boundary_smoke.py",),
    ),
    RouteBoundaryContract(
        path="/api/performance",
        method="GET",
        surface_id="analytics_admin",
        boundary="authenticated_admin",
        exposure="admin_json",
        expected_statuses=(401, 403, 503),
        source="services/analytics_dashboard/app.py",
        verification=("scripts/ops/public_boundary_smoke.py",),
    ),
    RouteBoundaryContract(
        path="/api/predictions",
        method="GET",
        surface_id="analytics_admin",
        boundary="authenticated_admin",
        exposure="admin_json",
        expected_statuses=(401, 403, 503),
        source="services/analytics_dashboard/app.py",
        verification=("scripts/ops/public_boundary_smoke.py",),
    ),
    RouteBoundaryContract(
        path="/api/predictions/accuracy",
        method="GET",
        surface_id="analytics_admin",
        boundary="authenticated_admin",
        exposure="admin_json",
        expected_statuses=(401, 403, 503),
        source="services/analytics_dashboard/app.py",
        verification=("scripts/ops/public_boundary_smoke.py",),
    ),
    RouteBoundaryContract(
        path="/api/correlation/matrix",
        method="GET",
        surface_id="analytics_admin",
        boundary="authenticated_admin",
        exposure="admin_json",
        expected_statuses=(401, 403, 503),
        source="services/analytics_dashboard/app.py",
        verification=("scripts/ops/public_boundary_smoke.py",),
    ),
    RouteBoundaryContract(
        path="/api/vpin",
        method="GET",
        surface_id="analytics_admin",
        boundary="authenticated_admin",
        exposure="admin_json",
        expected_statuses=(401, 403, 503),
        source="services/analytics_dashboard/app.py",
        verification=("scripts/ops/public_boundary_smoke.py",),
    ),
    RouteBoundaryContract(
        path="/api/deflated-sharpe/rolling",
        method="GET",
        surface_id="analytics_admin",
        boundary="authenticated_admin",
        exposure="admin_json",
        expected_statuses=(401, 403, 503),
        source="services/analytics_dashboard/app.py",
        verification=("scripts/ops/public_boundary_smoke.py",),
    ),
    RouteBoundaryContract(
        path="/api/timeseries/inference",
        method="GET",
        surface_id="analytics_admin",
        boundary="authenticated_admin",
        exposure="admin_json",
        expected_statuses=(401, 403, 503),
        source="services/analytics_dashboard/app.py",
        verification=("scripts/ops/public_boundary_smoke.py",),
    ),
    RouteBoundaryContract(
        path="/api/timeseries/services",
        method="GET",
        surface_id="analytics_admin",
        boundary="authenticated_admin",
        exposure="admin_json",
        expected_statuses=(401, 403, 503),
        source="services/analytics_dashboard/app.py",
        verification=("scripts/ops/public_boundary_smoke.py",),
    ),
    RouteBoundaryContract(
        path="/api/silos/business",
        method="GET",
        surface_id="analytics_admin",
        boundary="authenticated_admin",
        exposure="admin_json",
        expected_statuses=(401, 403, 503),
        source="services/analytics_dashboard/app.py",
        verification=("scripts/ops/public_boundary_smoke.py",),
    ),
    RouteBoundaryContract(
        path="/api/silos/inference",
        method="GET",
        surface_id="analytics_admin",
        boundary="authenticated_admin",
        exposure="admin_json",
        expected_statuses=(401, 403, 503),
        source="services/analytics_dashboard/app.py",
        verification=("scripts/ops/public_boundary_smoke.py",),
    ),
    RouteBoundaryContract(
        path="/api/signals/recent",
        method="GET",
        surface_id="analytics_admin",
        boundary="authenticated_admin",
        exposure="admin_json",
        expected_statuses=(401, 403, 503),
        source="services/analytics_dashboard/app.py",
        verification=("scripts/ops/public_boundary_smoke.py",),
    ),
    RouteBoundaryContract(
        path="/api/brain/synthesis?persist=1",
        method="GET",
        surface_id="analytics_admin",
        boundary="authenticated_admin",
        exposure="admin_json",
        expected_statuses=(401, 403, 503),
        source="services/analytics_dashboard/app.py",
        verification=("scripts/ops/public_boundary_smoke.py",),
    ),
    RouteBoundaryContract(
        path="/api/brain/synthesis?force_llm=1",
        method="GET",
        surface_id="analytics_admin",
        boundary="authenticated_admin",
        exposure="admin_json",
        expected_statuses=(401, 403, 503),
        source="services/analytics_dashboard/app.py",
        verification=("scripts/ops/public_boundary_smoke.py",),
    ),
    RouteBoundaryContract(
        path="/api/brain/correlate",
        method="GET",
        surface_id="analytics_admin",
        boundary="authenticated_admin",
        exposure="admin_json",
        expected_statuses=(401, 403, 503),
        source="services/analytics_dashboard/app.py",
        verification=("scripts/ops/public_boundary_smoke.py",),
    ),
    RouteBoundaryContract(
        path="/api/brain/history",
        method="GET",
        surface_id="analytics_admin",
        boundary="authenticated_admin",
        exposure="admin_json",
        expected_statuses=(401, 403, 503),
        source="services/analytics_dashboard/app.py",
        verification=("scripts/ops/public_boundary_smoke.py",),
    ),
    RouteBoundaryContract(
        path="/api/asfao/decisions",
        method="GET",
        surface_id="analytics_admin",
        boundary="authenticated_admin",
        exposure="admin_json",
        expected_statuses=(401, 403, 503),
        source="services/analytics_dashboard/asfao.py",
        verification=("scripts/ops/public_boundary_smoke.py",),
    ),
)

FETCH_PATTERN = re.compile(r"(?P<helper>safeFetch|fetch)\(\s*['\"](?P<path>[^'\"]+)['\"]")


def _repo_relative(path: Path, *, root: Path = ROOT) -> str:
    return path.resolve().relative_to(root.resolve()).as_posix()


def _iter_surface_files(path: Path) -> list[Path]:
    if not path.exists():
        return []
    files: list[Path] = []
    for candidate in path.rglob("*"):
        if not candidate.is_file():
            continue
        if any(part in EXCLUDED_PARTS for part in candidate.relative_to(path).parts):
            continue
        files.append(candidate)
    return sorted(files)


def _package_scripts(path: Path) -> list[str]:
    package_json = path / "package.json"
    if not package_json.exists():
        return []
    data = json.loads(package_json.read_text(encoding="utf-8"))
    scripts = data.get("scripts") or {}
    return sorted(str(name) for name in scripts)


def _contract_path(path: str) -> str:
    return path.split("?", 1)[0]


def _contract_lookup() -> dict[str, RouteBoundaryContract]:
    lookup: dict[str, RouteBoundaryContract] = {}
    for contract in ROUTE_CONTRACTS:
        lookup.setdefault(_contract_path(contract.path), contract)
        lookup[contract.path] = contract
    return lookup


def _public_template_fetches(root: Path = ROOT) -> list[PublicTemplateFetch]:
    template_paths = [root / "services/analytics_dashboard/templates/index.html"]
    template_paths.extend(
        sorted((root / "services/analytics_dashboard/templates/p").glob("*.html"))
    )
    lookup = _contract_lookup()
    fetches: list[PublicTemplateFetch] = []
    for template_path in template_paths:
        if not template_path.exists():
            continue
        template = _repo_relative(template_path, root=root)
        for match in FETCH_PATTERN.finditer(template_path.read_text(encoding="utf-8")):
            raw_path = match.group("path")
            same_origin = raw_path.startswith("/")
            path = _contract_path(raw_path) if same_origin else raw_path
            contract = lookup.get(path) if same_origin else None
            fetches.append(
                PublicTemplateFetch(
                    path=path,
                    template=template,
                    helper=match.group("helper"),
                    boundary=contract.boundary
                    if contract
                    else ("unknown" if same_origin else "external_public_fetch"),
                    contract_present=(contract is not None) if same_origin else True,
                    admin_route=same_origin and path.startswith("/api/admin/"),
                    same_origin=same_origin,
                )
            )
    return sorted(fetches, key=lambda item: (item.template, item.path))


def _entry(definition: SurfaceDefinition, *, root: Path = ROOT) -> SurfaceInventoryEntry:
    surface_root = root / definition.root
    missing = [
        entrypoint for entrypoint in definition.entrypoints if not (root / entrypoint).exists()
    ]
    return SurfaceInventoryEntry(
        surface_id=definition.surface_id,
        label=definition.label,
        root=definition.root,
        exists=surface_root.exists(),
        entrypoints=list(definition.entrypoints),
        missing_entrypoints=missing,
        stack=list(definition.stack),
        audience=definition.audience,
        boundary=definition.boundary,
        owner_module=definition.owner_module,
        lifecycle=definition.lifecycle,
        risk_level=definition.risk_level,
        operator_sensitive=definition.boundary in OPERATOR_BOUNDARIES,
        publicly_exposable=definition.boundary in PUBLIC_BOUNDARIES,
        file_count=len(_iter_surface_files(surface_root)),
        package_scripts=_package_scripts(surface_root),
        safety_notes=list(definition.safety_notes),
        verification=list(definition.verification),
        recommended_next_slice=definition.recommended_next_slice,
    )


def build_inventory(root: Path = ROOT) -> dict[str, Any]:
    surfaces = [_entry(definition, root=root) for definition in SURFACE_DEFS]
    route_contracts = list(ROUTE_CONTRACTS)
    public_template_fetches = _public_template_fetches(root=root)
    stacks = sorted({stack for surface in surfaces for stack in surface.stack})
    boundaries = sorted({surface.boundary for surface in surfaces})
    return {
        "schema_version": 1,
        "generated_by": GENERATOR,
        "summary": {
            "surface_count": len(surfaces),
            "missing_surface_count": sum(not surface.exists for surface in surfaces),
            "missing_entrypoint_count": sum(
                len(surface.missing_entrypoints) for surface in surfaces
            ),
            "operator_sensitive_count": sum(surface.operator_sensitive for surface in surfaces),
            "publicly_exposable_count": sum(surface.publicly_exposable for surface in surfaces),
            "route_contract_count": len(route_contracts),
            "public_route_contract_count": sum(
                contract.boundary in PUBLIC_BOUNDARIES for contract in route_contracts
            ),
            "admin_route_contract_count": sum(
                contract.boundary in OPERATOR_BOUNDARIES for contract in route_contracts
            ),
            "public_template_fetch_count": len(public_template_fetches),
            "public_template_fetch_missing_contract_count": sum(
                fetch.same_origin and not fetch.contract_present
                for fetch in public_template_fetches
            ),
            "public_template_admin_fetch_count": sum(
                fetch.admin_route for fetch in public_template_fetches
            ),
            "public_template_external_fetch_count": sum(
                not fetch.same_origin for fetch in public_template_fetches
            ),
            "boundaries": boundaries,
            "stacks": stacks,
        },
        "surfaces": [asdict(surface) for surface in surfaces],
        "route_contracts": [asdict(contract) for contract in route_contracts],
        "public_template_fetches": [asdict(fetch) for fetch in public_template_fetches],
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pretty", action="store_true", help="Pretty-print JSON output.")
    parser.add_argument(
        "--fail-on-missing",
        action="store_true",
        help="Exit non-zero when an inventoried surface or entrypoint is missing.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    inventory = build_inventory()
    indent = 2 if args.pretty else None
    print(json.dumps(inventory, indent=indent, sort_keys=True))
    if args.fail_on_missing and (
        inventory["summary"]["missing_surface_count"]
        or inventory["summary"]["missing_entrypoint_count"]
    ):
        return 1
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
