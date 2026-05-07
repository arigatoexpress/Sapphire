#!/usr/bin/env python3
"""Inventory the Sapphire dashboard routes, page templates, and migration owners.

The dashboard is still a single Flask app during the UI spine migration. This
script gives each current surface an explicit product-module owner, safety mode,
and lifecycle recommendation so new work can collapse pages deliberately instead
of adding another one-off Jinja route.
"""

from __future__ import annotations

import argparse
import ast
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
APP_PATH = ROOT / "services" / "dashboard" / "app.py"
PAGES_DIR = ROOT / "services" / "dashboard" / "templates" / "pages"
DEFAULT_OUTPUT = ROOT / "services" / "dashboard" / "config" / "surface_inventory.json"

PRODUCT_MODULES = (
    "Home / Worldline",
    "Operations",
    "Intelligence",
    "Markets",
    "Security",
    "Products / Diligence",
    "Automation",
    "Settings / Contracts",
)
LIFECYCLES = ("keep", "merge", "redirect", "retire", "hard-stop")
SAFETY_MODES = ("live", "read_only", "paper", "modeled", "stale", "blocked")

KEEP_ROUTES = {
    "/",
    "/app-preview",
    "/app-preview/",
    "/app-preview/assets/<path:filename>",
    "/api/v2/control-plane/summary",
    "/health",
    "/static/<path:filename>",
    "/api/production/readiness",
}
REDIRECT_ROUTES = {
    "/unified",
    "/unified-dashboard",
}
RETIRE_ROUTES: set[str] = set()
HARD_STOP_ROUTES = {
    "/api/x402/market-regime",
    "/api/x402/backtest",
}

OWNER_RULES: tuple[tuple[str, tuple[str, ...], tuple[str, ...]], ...] = (
    (
        "Home / Worldline",
        (
            "/",
            "/app-preview",
            "/app-preview/",
            "/app-preview/assets/<path:filename>",
            "/api/v2/control-plane/summary",
            "/showcase",
            "/unified",
            "/unified-dashboard",
        ),
        (),
    ),
    (
        "Operations",
        (
            "/architecture",
            "/infrastructure",
            "/logs",
            "/metrics",
            "/production-readiness",
            "/system",
            "/health",
            "/health-status",
            "/benchmarks",
            "/inference-telemetry",
        ),
        (
            "/api/health",
            "/api/launchagent",
            "/api/logs",
            "/api/metrics",
            "/api/observability",
            "/api/inference-telemetry",
            "/api/production",
            "/api/readiness",
            "/api/system",
            "/api/test-suite",
            "/api/windows",
            "/observability",
        ),
    ),
    (
        "Security",
        ("/security", "/security/overview", "/soc"),
        ("/api/security", "/api/soc", "/api/threat-timeline"),
    ),
    (
        "Markets",
        (
            "/analytics",
            "/cascade",
            "/chain",
            "/chain/robinhood",
            "/chain/sentinel",
            "/cross-asset",
            "/factors",
            "/investment-intel",
            "/performance",
            "/portfolio",
            "/predictions",
            "/risk",
            "/signals",
            "/sovereign-thesis",
            "/sovereign-thesis/story",
        ),
        (
            "/api/analytics",
            "/api/backtest",
            "/api/brain",
            "/api/cascade",
            "/api/chain",
            "/api/convergence",
            "/api/cross-asset",
            "/api/cross_chain",
            "/api/factors",
            "/api/forecast",
            "/api/hackathon",
            "/api/hyperliquid",
            "/api/investments",
            "/api/performance",
            "/api/perps",
            "/api/portfolio",
            "/api/prediction",
            "/api/predictions",
            "/api/risk",
            "/api/signals",
            "/api/strategy-performance",
            "/api/trading",
            "/api/trading-brain",
            "/api/tradingview",
            "/api/walkforward",
            "/api/watchlist",
        ),
    ),
    (
        "Intelligence",
        (
            "/content",
            "/intel",
            "/intel/leads",
            "/intelligence",
            "/narrative-eval",
            "/organization",
            "/source-quality",
            "/threat-intel",
            "/timetravel",
        ),
        (
            "/api/content",
            "/api/intel",
            "/api/leads",
            "/api/lumo",
            "/api/narrative",
            "/api/source-quality",
            "/api/telegram-history",
            "/api/threat-intel",
            "/api/tho",
            "/api/timetravel",
        ),
    ),
    (
        "Products / Diligence",
        (
            "/customer-dossier",
            "/diligence",
            "/sapphire-book",
        ),
        (
            "/api/customer-dossier",
            "/api/diligence",
            "/api/foundry",
            "/api/provenance",
            "/api/risk-kernel",
            "/api/x402",
        ),
    ),
    (
        "Automation",
        (
            "/activity",
            "/agents",
            "/agents/autonomous",
            "/command-deck",
            "/control",
        ),
        (
            "/api/agents",
            "/api/autonomy",
            "/api/events",
            "/api/gemini",
            "/api/opportunities",
            "/api/proposals",
            "/api/routine-pause",
            "/api/status",
        ),
    ),
    (
        "Settings / Contracts",
        ("/settings", "/static/<path:filename>"),
        (),
    ),
)

TEMPLATE_OWNER_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("Home / Worldline", ("overview", "showcase")),
    (
        "Operations",
        (
            "architecture",
            "benchmarks",
            "health",
            "inference_telemetry",
            "infrastructure",
            "logs",
            "observability",
            "production_readiness",
            "system",
        ),
    ),
    ("Security", ("security", "soc")),
    (
        "Markets",
        (
            "analytics",
            "cascade",
            "chain",
            "cross_asset",
            "factors",
            "investment_intel",
            "performance",
            "portfolio",
            "predictions",
            "risk",
            "robinhood_chain",
            "sentinel",
            "signals",
            "sovereign_thesis",
            "sovereign_thesis_story",
        ),
    ),
    (
        "Intelligence",
        (
            "content",
            "intel",
            "intel_leads",
            "intelligence",
            "narrative_eval",
            "organization",
            "source_quality",
            "threat_intel",
            "timetravel",
        ),
    ),
    (
        "Products / Diligence",
        (
            "customer_dossier",
            "diligence",
            "sapphire_book",
        ),
    ),
    ("Automation", ("activity", "agents", "agents_autonomous", "command_deck", "control")),
    ("Settings / Contracts", ("settings",)),
)


@dataclass(frozen=True)
class RouteEntry:
    rule: str
    endpoint: str
    methods: list[str]
    line: int
    kind: str
    owner_module: str
    safety_mode: str
    lifecycle: str
    requires_auth: bool
    templates: list[str]
    source: str


@dataclass(frozen=True)
class TemplateEntry:
    template: str
    name: str
    owner_module: str
    safety_mode: str
    lifecycle: str
    role: str
    routes: list[str]
    source: str


def _literal_str(node: ast.AST) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def _literal_methods(node: ast.AST | None) -> list[str]:
    if node is None:
        return ["GET"]
    if isinstance(node, (ast.List, ast.Tuple, ast.Set)):
        methods = [_literal_str(item) for item in node.elts]
        return sorted(method for method in methods if method)
    if method := _literal_str(node):
        return [method]
    return ["UNKNOWN"]


def _is_app_route(decorator: ast.AST) -> bool:
    return (
        isinstance(decorator, ast.Call)
        and isinstance(decorator.func, ast.Attribute)
        and decorator.func.attr == "route"
        and isinstance(decorator.func.value, ast.Name)
        and decorator.func.value.id == "app"
    )


def _decorator_name(decorator: ast.AST) -> str | None:
    if isinstance(decorator, ast.Name):
        return decorator.id
    if isinstance(decorator, ast.Call) and isinstance(decorator.func, ast.Name):
        return decorator.func.id
    return None


def _extract_route_decorators(node: ast.FunctionDef) -> list[dict[str, Any]]:
    routes = []
    for decorator in node.decorator_list:
        if not _is_app_route(decorator):
            continue
        rule = _literal_str(decorator.args[0]) if decorator.args else None
        if not rule:
            continue
        methods_node = None
        endpoint = node.name
        for keyword in decorator.keywords:
            if keyword.arg == "methods":
                methods_node = keyword.value
            elif keyword.arg == "endpoint":
                endpoint = _literal_str(keyword.value) or endpoint
        routes.append(
            {
                "rule": rule,
                "methods": _literal_methods(methods_node),
                "endpoint": endpoint,
                "line": decorator.lineno,
            }
        )
    return routes


def _extract_templates(node: ast.FunctionDef) -> list[str]:
    templates: list[str] = []
    for child in ast.walk(node):
        if not isinstance(child, ast.Call):
            continue
        func = child.func
        if not isinstance(func, ast.Name) or func.id != "render_template":
            continue
        if not child.args:
            continue
        template = _literal_str(child.args[0])
        if template:
            templates.append(template)
    return sorted(set(templates))


def extract_routes(app_path: Path = APP_PATH) -> list[dict[str, Any]]:
    tree = ast.parse(app_path.read_text(encoding="utf-8"), filename=str(app_path))
    routes: list[dict[str, Any]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef):
            continue
        decorators = {_decorator_name(decorator) for decorator in node.decorator_list}
        requires_auth = "requires_auth" in decorators
        templates = _extract_templates(node)
        for route in _extract_route_decorators(node):
            route["requires_auth"] = requires_auth
            route["templates"] = templates
            routes.append(route)
    return sorted(routes, key=lambda item: (int(item["line"]), str(item["rule"])))


def owner_for_rule(rule: str) -> str:
    for owner, exact_rules, prefixes in OWNER_RULES:
        if rule in exact_rules or any(rule.startswith(prefix) for prefix in prefixes):
            return owner
    raise ValueError(f"no dashboard product module owns route {rule!r}")


def owner_for_template(name: str) -> str:
    if name.startswith("_"):
        return "Settings / Contracts"
    stem = name.removesuffix(".html")
    for owner, stems in TEMPLATE_OWNER_RULES:
        if stem in stems:
            return owner
    raise ValueError(f"no dashboard product module owns template {name!r}")


def lifecycle_for_rule(rule: str) -> str:
    if rule in HARD_STOP_ROUTES:
        return "hard-stop"
    if rule in REDIRECT_ROUTES:
        return "redirect"
    if rule in RETIRE_ROUTES:
        return "retire"
    if rule in KEEP_ROUTES:
        return "keep"
    return "merge"


def safety_mode_for_rule(rule: str, methods: list[str]) -> str:
    if rule in HARD_STOP_ROUTES:
        return "blocked"
    if rule in {"/health", "/metrics"} or rule.startswith("/api/metrics"):
        return "live"
    if rule.startswith("/api/x402"):
        return "read_only"
    if rule.startswith(("/api/trading", "/api/tradingview", "/api/hyperliquid")):
        return "paper"
    if rule.startswith(("/api/portfolio", "/api/signals")):
        return "paper"
    if any(
        token in rule
        for token in (
            "analytics",
            "backtest",
            "brain",
            "cascade",
            "forecast",
            "gemini",
            "narrative",
            "prediction",
            "strategy",
            "walkforward",
        )
    ):
        return "modeled"
    if "POST" in methods:
        return "read_only"
    return "read_only"


def safety_mode_for_template(template: str, owner: str) -> str:
    if owner == "Markets":
        if any(token in template for token in ("portfolio", "signals")):
            return "paper"
        if any(token in template for token in ("analytics", "cascade", "predictions")):
            return "modeled"
    return "read_only"


def kind_for_rule(rule: str) -> str:
    if rule.startswith("/api/"):
        return "api"
    if rule.startswith("/static/") or rule.startswith("/app-preview/assets/"):
        return "static"
    return "page"


def build_inventory(root: Path = ROOT) -> dict[str, Any]:
    app_path = root / "services" / "dashboard" / "app.py"
    pages_dir = root / "services" / "dashboard" / "templates" / "pages"
    raw_routes = extract_routes(app_path)

    routes: list[RouteEntry] = []
    template_to_routes: dict[str, list[str]] = {}
    for raw in raw_routes:
        rule = str(raw["rule"])
        methods = [str(method) for method in raw["methods"]]
        owner = owner_for_rule(rule)
        lifecycle = lifecycle_for_rule(rule)
        safety_mode = safety_mode_for_rule(rule, methods)
        templates = [str(template) for template in raw["templates"]]
        for template in templates:
            template_to_routes.setdefault(template, []).append(rule)
        routes.append(
            RouteEntry(
                rule=rule,
                endpoint=str(raw["endpoint"]),
                methods=methods,
                line=int(raw["line"]),
                kind=kind_for_rule(rule),
                owner_module=owner,
                safety_mode=safety_mode,
                lifecycle=lifecycle,
                requires_auth=bool(raw["requires_auth"]),
                templates=templates,
                source=app_path.relative_to(root).as_posix(),
            )
        )

    templates: list[TemplateEntry] = []
    for template_path in sorted(pages_dir.glob("*.html")):
        name = template_path.name
        template = f"pages/{name}"
        owner = owner_for_template(name)
        role = "partial" if name.startswith("_") else "page"
        routes_for_template = sorted(template_to_routes.get(template, []))
        templates.append(
            TemplateEntry(
                template=template,
                name=name,
                owner_module=owner,
                safety_mode=safety_mode_for_template(template, owner),
                lifecycle="keep" if role == "partial" else "merge",
                role=role,
                routes=routes_for_template,
                source=template_path.relative_to(root).as_posix(),
            )
        )

    route_dicts = [asdict(route) for route in routes]
    template_dicts = [asdict(template) for template in templates]
    lifecycle_counts = {
        lifecycle: sum(1 for route in routes if route.lifecycle == lifecycle)
        for lifecycle in LIFECYCLES
    }
    module_counts = {
        module: sum(1 for route in routes if route.owner_module == module)
        for module in PRODUCT_MODULES
    }
    mode_counts = {
        mode: sum(1 for route in routes if route.safety_mode == mode) for mode in SAFETY_MODES
    }
    return {
        "schema_version": 1,
        "generated_by": "scripts/ops/dashboard_surface_inventory.py",
        "source": {
            "app": app_path.relative_to(root).as_posix(),
            "templates": pages_dir.relative_to(root).as_posix(),
        },
        "summary": {
            "route_count": len(route_dicts),
            "page_template_count": len(template_dicts),
            "api_route_count": sum(1 for route in routes if route.kind == "api"),
            "page_route_count": sum(1 for route in routes if route.kind == "page"),
            "static_route_count": sum(1 for route in routes if route.kind == "static"),
            "lifecycles": lifecycle_counts,
            "owner_modules": module_counts,
            "safety_modes": mode_counts,
        },
        "routes": route_dicts,
        "templates": template_dicts,
    }


def inventory_json(inventory: dict[str, Any]) -> str:
    return json.dumps(inventory, indent=2, sort_keys=True) + "\n"


def write_inventory(output: Path = DEFAULT_OUTPUT, root: Path = ROOT) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(inventory_json(build_inventory(root)), encoding="utf-8")


def check_inventory(output: Path = DEFAULT_OUTPUT, root: Path = ROOT) -> bool:
    expected = inventory_json(build_inventory(root))
    actual = output.read_text(encoding="utf-8")
    return actual == expected


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help="Inventory JSON path to write or check.",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Exit non-zero if the committed inventory is stale.",
    )
    args = parser.parse_args()

    if args.check:
        if check_inventory(args.output):
            print(f"dashboard surface inventory is current: {args.output}")
            return 0
        print(f"dashboard surface inventory is stale: {args.output}")
        return 1

    write_inventory(args.output)
    print(f"wrote dashboard surface inventory: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
