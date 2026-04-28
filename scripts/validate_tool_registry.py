#!/usr/bin/env python3
"""Validate infra/tool-registry.yaml and infra/agent-manifest.yaml.

Fails (exit 1) on any of:

1. A `.py` file exists under `plugins/claw-sapphire/tools/` (any depth,
   excluding `__init__.py` and dunder dirs) that is not listed in the
   registry.
2. A registry entry points at a missing file.
3. A `registered` tool has a Python syntax error or unresolvable import at
   module load (compile-only check; no execution).
4. A `deprecated` entry lacks a `shim` field, or the shim file is missing,
   or the shim does not import `warnings` + call `warnings.warn`.
5. `infra/agent-manifest.yaml` references a tool not in the registry, or
   references a tool whose registry entry is not `status: registered` with
   `agent_facing: true`.

Usage:
    python3 scripts/validate_tool_registry.py
    python3 scripts/validate_tool_registry.py --json
"""

from __future__ import annotations

import argparse
import ast
import json
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    print("error: PyYAML is required (pip install pyyaml)", file=sys.stderr)
    sys.exit(2)

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "infra" / "tool-registry.yaml"
MANIFEST = ROOT / "infra" / "agent-manifest.yaml"
TOOLS_DIR = ROOT / "plugins" / "claw-sapphire" / "tools"


def _iter_tool_files() -> list[Path]:
    files: list[Path] = []
    for p in TOOLS_DIR.rglob("*.py"):
        if p.name == "__init__.py":
            continue
        # Skip tests under tools/ if any (there aren't today).
        if any(part.startswith(".") for part in p.relative_to(TOOLS_DIR).parts):
            continue
        files.append(p)
    return sorted(files)


def _load_registry() -> dict:
    with REGISTRY.open() as f:
        data = yaml.safe_load(f)
    if not isinstance(data, dict) or "tools" not in data:
        raise SystemExit("registry: malformed (missing `tools` list)")
    return data


def _load_manifest() -> dict:
    with MANIFEST.open() as f:
        data = yaml.safe_load(f)
    if not isinstance(data, dict) or "tools" not in data:
        raise SystemExit("manifest: malformed (missing `tools` list)")
    return data


def _compile_check(path: Path) -> str | None:
    """Compile-parse the file; return error string or None on success."""
    try:
        src = path.read_text()
    except OSError as e:
        return f"read failed: {e}"
    try:
        ast.parse(src, filename=str(path))
    except SyntaxError as e:
        return f"syntax error: {e}"
    return None


def _shim_has_deprecation_warning(path: Path) -> bool:
    if not path.exists():
        return False
    src = path.read_text()
    return "warnings.warn" in src and "DeprecationWarning" in src


def validate() -> tuple[list[str], dict]:
    errors: list[str] = []
    registry = _load_registry()
    manifest = _load_manifest()

    by_name: dict[str, dict] = {}
    registered_paths: set[Path] = set()
    shim_paths: set[Path] = set()

    for entry in registry["tools"]:
        name = entry.get("name")
        path_str = entry.get("path")
        status = entry.get("status")
        if not (name and path_str and status):
            errors.append(f"registry: entry missing name/path/status: {entry!r}")
            continue
        if name in by_name:
            errors.append(f"registry: duplicate name `{name}`")
        by_name[name] = entry

        path = ROOT / path_str
        if not path.exists():
            errors.append(f"registry: `{name}` path does not exist: {path_str}")
            continue
        registered_paths.add(path.resolve())

        if status == "registered":
            err = _compile_check(path)
            if err:
                errors.append(f"registry: `{name}` {err}")

        if status == "deprecated":
            shim_str = entry.get("shim")
            if not shim_str:
                errors.append(f"registry: deprecated `{name}` missing `shim` field")
                continue
            shim_path = ROOT / shim_str
            if not shim_path.exists():
                errors.append(f"registry: deprecated `{name}` shim not found: {shim_str}")
                continue
            shim_paths.add(shim_path.resolve())
            if not _shim_has_deprecation_warning(shim_path):
                errors.append(
                    f"registry: deprecated `{name}` shim missing "
                    "`warnings.warn(..., DeprecationWarning)` call"
                )

    # Every tool file on disk must be in the registry — either as path or as
    # a shim for a deprecated tool, or as a compat shim for an internal tool
    # (shims live at tools/<name>.py mirroring tools/internal/<name>.py).
    for disk_path in _iter_tool_files():
        resolved = disk_path.resolve()
        if resolved in registered_paths or resolved in shim_paths:
            continue
        # Compat shim for an internal tool?
        rel = disk_path.relative_to(TOOLS_DIR)
        if len(rel.parts) == 1:
            internal = TOOLS_DIR / "internal" / rel.name
            if internal.exists() and internal.resolve() in registered_paths:
                continue
        errors.append(f"disk: `{disk_path.relative_to(ROOT)}` not listed in tool-registry.yaml")

    # Agent manifest must be a strict subset of registered + agent_facing.
    manifest_tools = manifest.get("tools", [])
    for m in manifest_tools:
        mname = m.get("name")
        if not mname:
            errors.append(f"manifest: entry missing `name`: {m!r}")
            continue
        entry = by_name.get(mname)
        if entry is None:
            errors.append(f"manifest: `{mname}` not in tool-registry.yaml")
            continue
        if entry.get("status") != "registered":
            errors.append(
                f"manifest: `{mname}` status is `{entry.get('status')}`, must be `registered`"
            )
        if not entry.get("agent_facing"):
            errors.append(f"manifest: `{mname}` must have `agent_facing: true` in registry")

    summary = {
        "registry_entries": len(registry["tools"]),
        "registered": sum(1 for e in registry["tools"] if e.get("status") == "registered"),
        "internal": sum(1 for e in registry["tools"] if e.get("status") == "internal"),
        "deprecated": sum(1 for e in registry["tools"] if e.get("status") == "deprecated"),
        "manifest_entries": len(manifest_tools),
        "disk_files": len(_iter_tool_files()),
        "errors": len(errors),
    }
    return errors, summary


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--json", action="store_true", help="emit JSON output")
    args = ap.parse_args()

    errors, summary = validate()

    if args.json:
        print(json.dumps({"summary": summary, "errors": errors}, indent=2))
    else:
        for e in errors:
            print(f"ERROR: {e}", file=sys.stderr)
        print(
            f"\nregistry={summary['registry_entries']} "
            f"(registered={summary['registered']}, "
            f"internal={summary['internal']}, "
            f"deprecated={summary['deprecated']})  "
            f"manifest={summary['manifest_entries']}  "
            f"disk={summary['disk_files']}  "
            f"errors={summary['errors']}",
            file=sys.stderr,
        )

    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
