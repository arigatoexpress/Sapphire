#!/usr/bin/env python3
"""Fail-closed source guard for deploying the Sapphire analytics service."""

from __future__ import annotations

import argparse
import ast
import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SOURCE = ROOT / "services" / "analytics_dashboard"

REQUIRED_FILES = (
    "app.py",
    "Dockerfile",
    "requirements.txt",
    "templates/index.html",
    "templates/admin.html",
    "data_engineering.py",
)

FORBIDDEN_PATHS = (
    "package.json",
    "package-lock.json",
    "pnpm-lock.yaml",
    "yarn.lock",
    "tsconfig.json",
    "vite.config.ts",
    "next.config.js",
    "src/server.ts",
    "src/app.ts",
)

REQUIRED_ROUTES = (
    "/health",
    "/api/admin/data-engineering",
    "/api/projects",
    "/api/brain/synthesis",
    "/api/markets/snapshot",
)


@dataclass(frozen=True)
class SourceGuardReport:
    ok: bool
    source_dir: str
    required_files_present: list[str]
    missing_required_files: list[str]
    forbidden_paths_present: list[str]
    discovered_routes: list[str]
    missing_required_routes: list[str]
    dockerfile_ok: bool
    errors: list[str]


def _literal_route_arg(node: ast.AST) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def _decorator_route(node: ast.AST) -> str | None:
    if not isinstance(node, ast.Call) or not node.args:
        return None
    func = node.func
    if not isinstance(func, ast.Attribute):
        return None
    if func.attr not in {"get", "post", "put", "delete", "patch", "route"}:
        return None
    return _literal_route_arg(node.args[0])


def _discover_routes(source_dir: Path) -> tuple[set[str], list[str]]:
    routes: set[str] = set()
    errors: list[str] = []
    for path in sorted(source_dir.glob("*.py")):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except (OSError, SyntaxError, UnicodeDecodeError) as exc:
            errors.append(f"{path.name}: {type(exc).__name__}: {exc}")
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
                continue
            for decorator in node.decorator_list:
                if route := _decorator_route(decorator):
                    routes.add(route)
    return routes, errors


def build_report(source_dir: Path) -> SourceGuardReport:
    source_dir = source_dir.expanduser().resolve()
    required_present = [rel for rel in REQUIRED_FILES if (source_dir / rel).is_file()]
    missing_required = [rel for rel in REQUIRED_FILES if rel not in required_present]
    forbidden_present = [rel for rel in FORBIDDEN_PATHS if (source_dir / rel).exists()]
    routes, errors = _discover_routes(source_dir)

    dockerfile = source_dir / "Dockerfile"
    try:
        dockerfile_text = dockerfile.read_text(encoding="utf-8")
    except OSError:
        dockerfile_text = ""
    dockerfile_ok = "gunicorn" in dockerfile_text and "app:app" in dockerfile_text
    missing_routes = [route for route in REQUIRED_ROUTES if route not in routes]
    ok = not (
        missing_required or forbidden_present or missing_routes or errors or not dockerfile_ok
    )
    return SourceGuardReport(
        ok=ok,
        source_dir=str(source_dir),
        required_files_present=required_present,
        missing_required_files=missing_required,
        forbidden_paths_present=forbidden_present,
        discovered_routes=sorted(routes),
        missing_required_routes=missing_routes,
        dockerfile_ok=dockerfile_ok,
        errors=errors,
    )


def _render_text(report: SourceGuardReport) -> str:
    lines = [
        "# Sapphire analytics deploy source guard",
        f"- source_dir: `{report.source_dir}`",
        f"- ok: `{str(report.ok).lower()}`",
        f"- dockerfile_ok: `{str(report.dockerfile_ok).lower()}`",
    ]
    if report.missing_required_files:
        lines.append(f"- missing_required_files: `{', '.join(report.missing_required_files)}`")
    if report.forbidden_paths_present:
        lines.append(f"- forbidden_paths_present: `{', '.join(report.forbidden_paths_present)}`")
    if report.missing_required_routes:
        lines.append(f"- missing_required_routes: `{', '.join(report.missing_required_routes)}`")
    if report.errors:
        lines.append(f"- errors: `{'; '.join(report.errors)}`")
    if report.ok:
        lines.append("- result: analytics Flask source identity verified")
    return "\n".join(lines) + "\n"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-dir", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--json", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    report = build_report(args.source_dir)
    if args.json:
        print(json.dumps(asdict(report), indent=2, sort_keys=True))
    else:
        print(_render_text(report), end="")
    return 0 if report.ok else 22


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
