#!/usr/bin/env python3
"""Read-only status for the fresh Kimi/Gemini-first agent runtime.

The script does not call hosted model APIs, send Telegram messages, load or
unload LaunchAgents, or mutate local model state. It checks whether the new
runtime profile is coherent, deprecated bot services are absent/disabled, and
the explicit local fallback models are installed.
"""

from __future__ import annotations

import argparse
import json
import platform
import shutil
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from lib.agents.runtime_profile import (  # noqa: E402
    deprecated_launchagent_labels,
    load_runtime_profile,
    required_local_models,
)
from scripts.ops.telegram_sender_audit import (  # noqa: E402
    parse_disabled,
    parse_launchctl_list,
    run_command,
)


def collect_report(
    *,
    profile_path: str | Path | None = None,
    archive_dir: str | Path | None = None,
) -> dict[str, Any]:
    """Collect a sanitized local readiness report."""

    profile = load_runtime_profile(profile_path)
    required_models = required_local_models(profile)
    installed_models = list_ollama_models()
    deprecated_labels = deprecated_launchagent_labels(profile)
    launch_report = check_deprecated_launchagents(
        deprecated_labels,
        archive_dir=Path(archive_dir).expanduser() if archive_dir else None,
    )
    harness_report = check_harnesses(profile)

    checks = [
        check(
            "runtime_profile_loaded",
            "ok",
            "Fresh runtime profile loaded and validated.",
            {
                "path": str(Path(profile_path).expanduser()) if profile_path else "default",
                "model_lanes": len(profile.get("model_lanes", [])),
                "harnesses": len(profile.get("harnesses", [])),
            },
        ),
        check(
            "deprecated_launchagents_disabled",
            "fail" if launch_report["loaded"] else "ok",
            "Deprecated bot/tunnel LaunchAgents must stay unloaded.",
            launch_report,
        ),
        check(
            "required_local_models_installed",
            "fail" if missing_models(required_models, installed_models) else "ok",
            "The inventory-pinned local fallback models must be installed before relying on local fallback.",
            {
                "required": required_models,
                "installed_matches": [
                    model
                    for model in required_models
                    if model_inventory_has(installed_models, model)
                ],
                "missing": missing_models(required_models, installed_models),
            },
        ),
        check(
            "google_adk_harness_available",
            "ok" if harness_report["google_adk_installed"] else "warn",
            "Google ADK is the preferred GCP agent harness; warning means install is still pending.",
            harness_report,
        ),
    ]
    return {
        "status": overall_status(item["status"] for item in checks),
        "platform": platform.system(),
        "policy": profile.get("policy", {}),
        "checks": checks,
    }


def list_ollama_models() -> list[str]:
    """Return locally installed Ollama model names."""

    result = run_command(["ollama", "list"], timeout=10)
    if result.returncode != 0:
        return []
    names: list[str] = []
    for line in result.stdout.splitlines()[1:]:
        parts = line.split()
        if parts:
            names.append(parts[0])
    return sorted(names)


def check_deprecated_launchagents(
    labels: list[str],
    *,
    archive_dir: Path | None = None,
) -> dict[str, Any]:
    """Check deprecated LaunchAgents without changing launchd state."""

    loaded: list[str] = []
    disabled: list[str] = []
    archived: list[str] = []
    if platform.system() != "Darwin":
        return {
            "labels": labels,
            "loaded": loaded,
            "disabled": disabled,
            "archived": archived,
            "platform": platform.system(),
        }

    launch = run_command(["launchctl", "list"])
    agents = parse_launchctl_list(launch.stdout) if launch.returncode == 0 else {}
    uid = run_command(["id", "-u"])
    disabled_labels: set[str] = set()
    if uid.returncode == 0 and uid.stdout.strip():
        raw_disabled = run_command(["launchctl", "print-disabled", f"gui/{uid.stdout.strip()}"])
        disabled_labels = (
            parse_disabled(raw_disabled.stdout) if raw_disabled.returncode == 0 else set()
        )

    for label in labels:
        if label in agents:
            loaded.append(label)
        if label in disabled_labels:
            disabled.append(label)
        if archive_dir and (archive_dir / f"{label}.plist").exists():
            archived.append(label)

    return {
        "labels": labels,
        "loaded": sorted(loaded),
        "disabled": sorted(disabled),
        "archived": sorted(archived),
        "archive_dir": str(archive_dir) if archive_dir else None,
    }


def check_harnesses(profile: dict[str, Any]) -> dict[str, Any]:
    """Return optional harness availability without importing SDKs."""

    adk_harness = next(
        (row for row in profile.get("harnesses", []) if row.get("id") == "google_adk"),
        {},
    )
    pip_show = run_command([sys.executable, "-m", "pip", "show", "google-adk"], timeout=10)
    return {
        "google_adk_configured": bool(adk_harness),
        "google_adk_installed": pip_show.returncode == 0 or shutil.which("adk") is not None,
        "adk_cli": shutil.which("adk"),
        "package": adk_harness.get("package"),
        "env_contract": adk_harness.get("env_contract", []),
    }


def model_inventory_has(model_names: list[str], required_model: str) -> bool:
    """Return whether ``required_model`` is represented in an Ollama model list."""

    if required_model in model_names:
        return True
    if ":" in required_model:
        return False
    prefix = f"{required_model}:"
    return any(name.startswith(prefix) for name in model_names)


def missing_models(required_models: list[str], installed_models: list[str]) -> list[str]:
    """Return required models not present in the installed model list."""

    return [model for model in required_models if not model_inventory_has(installed_models, model)]


def check(name: str, status: str, message: str, data: dict[str, Any]) -> dict[str, Any]:
    """Build a status check row."""

    return {"name": name, "status": status, "message": message, "data": data}


def overall_status(statuses: Any) -> str:
    """Aggregate check statuses."""

    seen = set(statuses)
    if "fail" in seen:
        return "fail"
    if "warn" in seen:
        return "warn"
    return "ok"


def format_markdown(report: dict[str, Any]) -> str:
    """Render the report as a compact operator table."""

    lines = [
        f"Status: {report['status']}",
        "",
        "| Check | Status | Detail |",
        "|---|---:|---|",
    ]
    for item in report["checks"]:
        data = item.get("data") or {}
        detail = item["message"]
        if item["name"] == "deprecated_launchagents_disabled":
            detail += f" loaded={data.get('loaded', [])} archived={data.get('archived', [])}"
        elif item["name"] == "required_local_models_installed":
            detail += f" missing={data.get('missing', [])}"
        elif item["name"] == "google_adk_harness_available":
            detail += f" installed={data.get('google_adk_installed')}"
        lines.append(f"| `{item['name']}` | `{item['status']}` | {detail} |")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="Emit JSON instead of markdown.")
    parser.add_argument("--profile", default=None, help="Runtime profile path override.")
    parser.add_argument("--archive-dir", default=None, help="Deprecated plist archive dir.")
    args = parser.parse_args(argv)

    report = collect_report(profile_path=args.profile, archive_dir=args.archive_dir)
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(format_markdown(report))
    return 1 if report["status"] == "fail" else 0


if __name__ == "__main__":
    raise SystemExit(main())
