#!/usr/bin/env python3
"""Read-only Hermes runtime readiness probe for Sapphire operations.

**ARCHIVED 2026-05-12:** hermes-agent has been archived. The ai.hermes.gateway
LaunchAgent must remain disabled. This script is retained as a historical
artifact but will report paths as missing since ~/Code/hermes-agent and
~/.hermes/hermes-agent no longer exist at their old locations.

This script compared the live Hermes gateway checkout used by the
``ai.hermes.gateway`` LaunchAgent with the development clone tracked by
Sapphire's org manifest. It never restarts Hermes, edits configs, sends
Telegram messages, or prints command bodies from Hermes config.
"""

from __future__ import annotations

import argparse
import json
import plistlib
import re
import subprocess
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

try:  # PyYAML is available in Sapphire, but keep the probe import-safe.
    import yaml
except Exception:  # pragma: no cover - fallback for stripped environments
    yaml = None

DEFAULT_RUNTIME_PATH = Path.home() / ".hermes" / "hermes-agent"
DEFAULT_DEV_PATH = Path.home() / "Code" / "hermes-agent"
DEFAULT_LAUNCHAGENT_PLIST = Path.home() / "Library" / "LaunchAgents" / "ai.hermes.gateway.plist"
DEFAULT_CONFIG_PATH = Path.home() / ".hermes" / "config.yaml"

QUICK_GUARD_NEEDLES = (
    "_check_sapphire_quick_exec_command",
    "_is_production_adjacent_quick_exec",
    "Sapphire CommandGuard",
    "sapphire_confirmation_required",
)
CONFIRMATION_REPLY_NEEDLES = (
    "_handle_sapphire_confirmation_reply_text",
    "handle_confirmation_reply",
)
PRODUCTION_ADJACENT_QUICK_EXEC_RE = re.compile(
    r"""
    \b(?:launchctl|systemctl|service|terraform|kubectl|helm|gcloud|aws|az|wrangler|vercel|netlify|flyctl|render|pm2|supervisorctl)\b
    |\bdocker(?:\s+compose)?\s+(?:up|down|restart|stop|rm|rmi|run|exec|push|pull|build|login|tag|service|stack)\b
    |\b(?:git\s+push|git\s+reset\s+--hard|git\s+clean\s+-[^\s]*f|gh\s+(?:workflow|release|pr\s+merge))\b
    |\bhermes\s+(?:gateway|update)\b
    |\b(?:deploy|production|prod|live|trading|tradingview|sapphire|telegram|sendmessage)\b
    |api\.telegram\.org
    |tradingview_execution_enabled|live_trading|sapphire_repo_path
    |\b(?:tee|sed\s+-[^\s]*i|>>?|cp|mv|install)\b[^\n]*(?:\.env|config\.yaml|/etc/|launchagents|secrets?)
    """,
    re.IGNORECASE | re.VERBOSE,
)


Runner = Callable[[list[str], Path], dict[str, Any]]


def _utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _run(args: list[str], cwd: Path) -> dict[str, Any]:
    try:
        proc = subprocess.run(
            args,
            cwd=cwd,
            check=False,
            capture_output=True,
            text=True,
            timeout=8,
        )
    except Exception as exc:
        return {"ok": False, "stdout": "", "stderr": type(exc).__name__}
    return {
        "ok": proc.returncode == 0,
        "stdout": proc.stdout.strip(),
        "stderr": proc.stderr.strip(),
    }


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return ""


def _has_all(text: str, needles: tuple[str, ...]) -> bool:
    return all(needle in text for needle in needles)


def _git_summary(path: Path, runner: Runner = _run) -> dict[str, Any]:
    if not (path / ".git").exists():
        return {"available": False, "head": None, "branch": None, "status": "not a git checkout"}
    head = runner(["git", "rev-parse", "--short=12", "HEAD"], path)
    branch = runner(["git", "branch", "--show-current"], path)
    status = runner(["git", "status", "--short", "--branch"], path)
    return {
        "available": True,
        "head": head["stdout"] if head["ok"] else None,
        "branch": branch["stdout"] if branch["ok"] else None,
        "status": status["stdout"].splitlines()[0] if status["ok"] and status["stdout"] else None,
    }


def _checkout_guard_summary(path: Path, runner: Runner = _run) -> dict[str, Any]:
    run_py = path / "gateway" / "run.py"
    text = _read_text(run_py)
    return {
        "path": str(path),
        "exists": path.exists(),
        "run_py_exists": run_py.is_file(),
        "git": _git_summary(path, runner),
        "confirmation_reply_patch": _has_all(text, CONFIRMATION_REPLY_NEEDLES),
        "quick_exec_command_guard": _has_all(text, QUICK_GUARD_NEEDLES),
    }


def _load_plist(path: Path) -> dict[str, Any]:
    try:
        data = plistlib.loads(path.read_bytes())
    except (OSError, plistlib.InvalidFileException):
        return {}
    return data if isinstance(data, dict) else {}


def _launchagent_summary(path: Path, runtime_path: Path) -> dict[str, Any]:
    data = _load_plist(path)
    env = (
        data.get("EnvironmentVariables")
        if isinstance(data.get("EnvironmentVariables"), dict)
        else {}
    )
    program_args = (
        data.get("ProgramArguments") if isinstance(data.get("ProgramArguments"), list) else []
    )
    working_directory = str(data.get("WorkingDirectory") or "")
    runtime_str = str(runtime_path)
    return {
        "path": str(path),
        "exists": path.is_file(),
        "label": data.get("Label"),
        "working_directory": working_directory,
        "program_uses_runtime": any(runtime_str in str(item) for item in program_args),
        "working_directory_is_runtime": working_directory == runtime_str,
        "sapphire_repo_path_env_present": bool(env.get("SAPPHIRE_REPO_PATH")),
        "non_secret_env_keys": sorted(str(key) for key in env),
    }


def _config_quick_command_summary(path: Path) -> dict[str, Any]:
    summary = {
        "path": str(path),
        "exists": path.is_file(),
        "quick_command_count": 0,
        "exec_quick_command_count": 0,
        "production_adjacent_exec_count": 0,
    }
    if not path.is_file() or yaml is None:
        return summary
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except Exception:
        return {**summary, "read_error": True}
    quick_commands = data.get("quick_commands") if isinstance(data, dict) else None
    if not isinstance(quick_commands, dict):
        return summary
    exec_count = 0
    production_adjacent = 0
    for value in quick_commands.values():
        if not isinstance(value, dict):
            continue
        if value.get("type") != "exec":
            continue
        exec_count += 1
        command = str(value.get("command") or "")
        production_adjacent += int(bool(PRODUCTION_ADJACENT_QUICK_EXEC_RE.search(command)))
    summary.update(
        {
            "quick_command_count": len(quick_commands),
            "exec_quick_command_count": exec_count,
            "production_adjacent_exec_count": production_adjacent,
        }
    )
    return summary


def collect_readiness(
    *,
    runtime_path: Path = DEFAULT_RUNTIME_PATH,
    dev_path: Path = DEFAULT_DEV_PATH,
    launchagent_plist: Path = DEFAULT_LAUNCHAGENT_PLIST,
    config_path: Path = DEFAULT_CONFIG_PATH,
    runner: Runner = _run,
) -> dict[str, Any]:
    runtime = _checkout_guard_summary(runtime_path, runner)
    dev = _checkout_guard_summary(dev_path, runner)
    launchagent = _launchagent_summary(launchagent_plist, runtime_path)
    quick_commands = _config_quick_command_summary(config_path)

    required = {
        "launchagent_points_to_runtime": bool(
            launchagent["program_uses_runtime"] and launchagent["working_directory_is_runtime"]
        ),
        "runtime_confirmation_reply_patch": bool(runtime["confirmation_reply_patch"]),
        "runtime_quick_exec_command_guard": bool(runtime["quick_exec_command_guard"]),
        "launchagent_sapphire_repo_path_env": bool(launchagent["sapphire_repo_path_env_present"]),
    }
    if all(required.values()):
        status = "pass"
        next_action = "Hermes runtime quick exec is Sapphire-guarded; keep approval tests green before changing skills."
    elif dev["quick_exec_command_guard"] and not runtime["quick_exec_command_guard"]:
        status = "warn"
        next_action = (
            "Promote the Ari/dev Hermes quick-exec guard into the runtime checkout with a backup, "
            "then restart ai.hermes.gateway through an explicit LaunchAgent gate."
        )
    else:
        status = "warn"
        next_action = "Add or repair Sapphire CommandGuard quick-exec coverage before expanding Hermes production commands."

    if (
        quick_commands["production_adjacent_exec_count"]
        and not required["runtime_quick_exec_command_guard"]
    ):
        status = "warn"
    if not launchagent["exists"] or not runtime["exists"]:
        status = "fail"
        next_action = "Restore the Hermes runtime checkout or LaunchAgent before relying on Telegram gateway operations."

    return {
        "schema_version": 1,
        "generated_at": _utc_now(),
        "status": status,
        "guardrails": [
            "Read-only: no Hermes restart, config edit, Telegram send, secret read, or LaunchAgent mutation.",
            "Command bodies from Hermes config are counted but never printed.",
        ],
        "runtime": runtime,
        "development_clone": dev,
        "launchagent": launchagent,
        "quick_commands": quick_commands,
        "required_runtime_controls": required,
        "next_action": next_action,
    }


def render_markdown(report: dict[str, Any]) -> str:
    req = report["required_runtime_controls"]
    runtime = report["runtime"]
    dev = report["development_clone"]
    la = report["launchagent"]
    quick = report["quick_commands"]
    lines = [
        "# Hermes Runtime Readiness",
        "",
        f"- Generated: `{report['generated_at']}`",
        f"- Status: `{report['status']}`",
        f"- Runtime: `{runtime['path']}`",
        f"- Development clone: `{dev['path']}`",
        "",
        "## Guardrails",
        "",
    ]
    lines.extend(f"- {item}" for item in report["guardrails"])
    lines.extend(
        [
            "",
            "## Runtime Controls",
            "",
            "| Control | Ready |",
            "|---|:---:|",
        ]
    )
    labels = {
        "launchagent_points_to_runtime": "LaunchAgent points at runtime checkout",
        "runtime_confirmation_reply_patch": "Runtime intercepts Sapphire confirmation replies",
        "runtime_quick_exec_command_guard": "Runtime gates quick exec through Sapphire CommandGuard",
        "launchagent_sapphire_repo_path_env": "LaunchAgent sets SAPPHIRE_REPO_PATH",
    }
    for key, label in labels.items():
        lines.append(f"| {label} | {'yes' if req[key] else 'no'} |")
    lines.extend(
        [
            "",
            "## Evidence",
            "",
            f"- LaunchAgent exists: `{'yes' if la['exists'] else 'no'}`",
            f"- LaunchAgent working directory is runtime: `{'yes' if la['working_directory_is_runtime'] else 'no'}`",
            f"- Runtime head: `{runtime['git'].get('head') or 'unknown'}` on `{runtime['git'].get('branch') or 'unknown'}`",
            f"- Dev clone head: `{dev['git'].get('head') or 'unknown'}` on `{dev['git'].get('branch') or 'unknown'}`",
            f"- Quick commands: `{quick['quick_command_count']}` total, `{quick['exec_quick_command_count']}` exec, `{quick['production_adjacent_exec_count']}` production-adjacent exec",
            "",
            "## Next Action",
            "",
            report["next_action"],
            "",
        ]
    )
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime-path", type=Path, default=DEFAULT_RUNTIME_PATH)
    parser.add_argument("--dev-path", type=Path, default=DEFAULT_DEV_PATH)
    parser.add_argument("--launchagent-plist", type=Path, default=DEFAULT_LAUNCHAGENT_PLIST)
    parser.add_argument("--config-path", type=Path, default=DEFAULT_CONFIG_PATH)
    parser.add_argument("--format", choices=("markdown", "json"), default="markdown")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    report = collect_readiness(
        runtime_path=args.runtime_path,
        dev_path=args.dev_path,
        launchagent_plist=args.launchagent_plist,
        config_path=args.config_path,
    )
    if args.format == "json":
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(render_markdown(report), end="")
    return 0 if report["status"] != "fail" else 20


if __name__ == "__main__":
    raise SystemExit(main())
