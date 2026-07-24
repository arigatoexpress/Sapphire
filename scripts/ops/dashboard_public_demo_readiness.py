#!/usr/bin/env python3
"""Validate and prepare buyer-safe dashboard public-demo artifacts.

The default path is dry-run and stdlib-only: it scans public-demo source
documents, applies the configured redaction patterns in-memory, verifies that
committed screenshot files are placeholders, and writes JSON readiness reports
under ``build/dashboard-public-demo/``.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MANIFEST = REPO_ROOT / "config" / "dashboard_public_demo_redactions.json"
DEFAULT_OUTPUT_DIR = REPO_ROOT / "build" / "dashboard-public-demo"
GENERATOR = "scripts.ops.dashboard_public_demo_readiness"


@dataclass(frozen=True)
class RedactionRule:
    name: str
    pattern: str
    replacement: str


def _now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def _repo_relative(path: Path) -> str:
    """Repo-relative path, always with forward slashes.

    These strings land in committed JSON artifacts, so they must not vary by the
    host that generated them. `str()` on a Path yields backslashes on Windows,
    which would make an artifact generated there differ from the same artifact
    generated on macOS — and, for provenance, change the dict keys.
    """
    try:
        return path.resolve().relative_to(REPO_ROOT.resolve()).as_posix()
    except ValueError:
        return f"[outside-repo]/{path.name}"


def load_manifest(path: Path = DEFAULT_MANIFEST) -> dict[str, Any]:
    """Load and lightly validate the JSON redaction manifest."""
    data = json.loads(path.read_text(encoding="utf-8"))
    if int(data.get("schema_version") or 0) != 1:
        raise ValueError("manifest schema_version must be 1")
    if not data.get("safe_routes"):
        raise ValueError("manifest must list safe_routes")
    if not data.get("sensitive_patterns"):
        raise ValueError("manifest must list sensitive_patterns")
    return data


def _rules(manifest: dict[str, Any]) -> list[RedactionRule]:
    return [
        RedactionRule(
            name=str(item["name"]),
            pattern=str(item["pattern"]),
            replacement=str(item["replacement"]),
        )
        for item in manifest.get("sensitive_patterns", [])
    ]


def redact_text(text: str, manifest: dict[str, Any]) -> tuple[str, dict[str, int]]:
    """Apply manifest redactions and return replacement counts by rule name."""
    counts: dict[str, int] = {}
    redacted = text
    for rule in _rules(manifest):
        redacted, count = re.subn(rule.pattern, rule.replacement, redacted)
        counts[rule.name] = count
    return redacted, counts


def forbidden_residue(text: str, manifest: dict[str, Any]) -> list[str]:
    """Return forbidden literals still present after redaction."""
    return [
        literal
        for literal in manifest.get("forbidden_after_redaction", [])
        if literal and literal in text
    ]


def _scan_file(path: Path, manifest: dict[str, Any]) -> dict[str, Any]:
    try:
        raw = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        raw = path.read_bytes().decode("utf-8", errors="replace")
    redacted, counts = redact_text(raw, manifest)
    residue = forbidden_residue(redacted, manifest)
    return {
        "path": _repo_relative(path),
        "exists": path.exists(),
        "bytes": path.stat().st_size,
        "redactions": counts,
        "redaction_total": sum(counts.values()),
        "forbidden_after_redaction": residue,
        "status": "fail" if residue else "pass",
        "preview": " ".join(redacted.split())[:220],
    }


def _missing_source_row(raw: str) -> dict[str, Any]:
    return {
        "path": raw,
        "exists": False,
        "bytes": 0,
        "redactions": {},
        "redaction_total": 0,
        "forbidden_after_redaction": [],
        "status": "fail",
        "preview": "",
    }


def scan_sources(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    """Scan configured text sources and return paste-safe rows."""
    rows: list[dict[str, Any]] = []
    for raw in manifest.get("scan_sources", []):
        path = (REPO_ROOT / str(raw)).resolve()
        if not path.exists():
            rows.append(_missing_source_row(str(raw)))
            continue
        rows.append(_scan_file(path, manifest))
    return rows


def inspect_screenshot_placeholders(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    """Ensure committed screenshot artifacts are placeholders, not real captures."""
    rows: list[dict[str, Any]] = []
    for raw_dir in manifest.get("placeholder_screenshot_dirs", []):
        directory = REPO_ROOT / str(raw_dir)
        if not directory.exists():
            rows.append(
                {
                    "path": str(raw_dir),
                    "exists": False,
                    "status": "fail",
                    "reason": "missing_directory",
                }
            )
            continue
        for path in sorted(directory.glob("*")):
            if path.name == ".gitkeep":
                continue
            if path.suffix.lower() not in {".png", ".jpg", ".jpeg", ".webp"}:
                continue
            size = path.stat().st_size
            rows.append(
                {
                    "path": _repo_relative(path),
                    "exists": True,
                    "bytes": size,
                    "status": "pass" if size == 0 else "fail",
                    "reason": "placeholder" if size == 0 else "nonempty_screenshot",
                }
            )
    return rows


def build_export_plan(
    manifest: dict[str, Any],
    *,
    manifest_path: Path = DEFAULT_MANIFEST,
) -> dict[str, Any]:
    """Build a deterministic dry-run export plan for public-demo routes."""
    routes = []
    for item in manifest.get("safe_routes", []):
        routes.append(
            {
                "route": item["path"],
                "label": item["label"],
                "planned_static_filename": item["filename"],
                "requires_auth": True,
                "capture_mode": "operator_local_only",
            }
        )
    return {
        "schema_version": 1,
        "mode": "dry-run",
        "generator": GENERATOR,
        "generated_at": _now_iso(),
        "routes": routes,
        "redaction_manifest": _repo_relative(manifest_path),
        "browser_required": False,
        "live_dashboard_required": False,
        "notes": [
            "No browser is launched by this script.",
            "No real screenshots are written or committed.",
            "Run render_acquirer_screenshots.py separately only after local operator review.",
        ],
    }


def build_report(
    *,
    manifest_path: Path = DEFAULT_MANIFEST,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    write: bool = True,
) -> dict[str, Any]:
    """Build and optionally write the demo-readiness report."""
    manifest = load_manifest(manifest_path)
    source_rows = scan_sources(manifest)
    screenshot_rows = inspect_screenshot_placeholders(manifest)
    failures = [f"source:{row['path']}" for row in source_rows if row.get("status") != "pass"] + [
        f"screenshot:{row['path']}" for row in screenshot_rows if row.get("status") != "pass"
    ]
    totals = {
        "routes": len(manifest.get("safe_routes", [])),
        "sources_scanned": len(source_rows),
        "screenshot_placeholders": len(screenshot_rows),
        "redactions_applied": sum(int(row.get("redaction_total") or 0) for row in source_rows),
        "failures": len(failures),
    }
    plan = build_export_plan(manifest, manifest_path=manifest_path)
    report = {
        "schema_version": 1,
        "mode": "dry-run",
        "ok": not failures,
        "generated_at": plan["generated_at"],
        "manifest": _repo_relative(manifest_path),
        "totals": totals,
        "failures": failures,
        "sources": source_rows,
        "screenshots": screenshot_rows,
        "export_plan": plan,
    }
    if write:
        output_dir.mkdir(parents=True, exist_ok=True)
        files = manifest.get("output_files", {})
        plan_path = output_dir / files.get("plan", "dashboard-public-demo-plan.json")
        report_path = output_dir / files.get(
            "redaction_report",
            "dashboard-public-demo-redaction-report.json",
        )
        plan_path.write_text(json.dumps(plan, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        report_path.write_text(
            json.dumps(report, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        report["written"] = {
            "plan": _repo_relative(plan_path),
            "redaction_report": _repo_relative(report_path),
        }
    return report


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument(
        "--no-write",
        action="store_true",
        help="Print report only; do not write build/ JSON artifacts.",
    )
    parser.add_argument("--pretty", action="store_true", help="Pretty-print JSON output.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    report = build_report(
        manifest_path=args.manifest,
        output_dir=args.output_dir,
        write=not args.no_write,
    )
    indent = 2 if args.pretty else None
    sys.stdout.write(json.dumps(report, indent=indent, sort_keys=True) + "\n")
    return 0 if report["ok"] else 20


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
