#!/usr/bin/env python3
"""Read-only audit for legacy Telegram sender surfaces.

This script does not call Telegram, mutate launchd, register webhooks, or send
messages. It checks the local Mac runtime for the old sender paths that can
compete with the Sapphire PM bot: Hermes polling, the THO health watcher direct
send path, SOC direct Telegram alerting, inference-proxy relay enablement, and
non-desktop Telegram sockets.
"""

from __future__ import annotations

import argparse
import json
import platform
import re
import subprocess
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

TELEGRAM_NETWORK_PATTERNS = (
    "api.telegram.org",
    "149.154.",
    "91.108.",
    "194.221.250.",
)
ALLOWED_TELEGRAM_PROCESS_RE = re.compile(r"^Telegram\s+")
EXPECTED_PM_DRAFT_QUEUE = str(
    Path.home() / ".cache" / "sapphire" / "telegram" / "pm_bot_drafts.jsonl"
)


@dataclass(frozen=True)
class CommandResult:
    returncode: int
    stdout: str
    stderr: str


def run_command(args: list[str], *, timeout: float = 5.0) -> CommandResult:
    """Run a local read-only command and capture text output."""
    try:
        proc = subprocess.run(
            args,
            capture_output=True,
            check=False,
            text=True,
            timeout=timeout,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return CommandResult(1, "", f"{type(exc).__name__}: {exc}")
    return CommandResult(proc.returncode, proc.stdout, proc.stderr)


def parse_launchctl_list(output: str) -> dict[str, dict[str, str | int | None]]:
    """Parse ``launchctl list`` output keyed by label."""
    agents: dict[str, dict[str, str | int | None]] = {}
    for raw in output.splitlines():
        line = raw.strip()
        if not line or line.startswith("PID"):
            continue
        parts = line.split(None, 2)
        if len(parts) != 3:
            continue
        pid_s, status_s, label = parts
        agents[label] = {
            "pid": None if pid_s == "-" else _to_int(pid_s),
            "status": None if status_s == "-" else _to_int(status_s),
            "label": label,
        }
    return agents


def parse_disabled(output: str) -> set[str]:
    """Parse labels marked disabled by ``launchctl print-disabled``."""
    disabled: set[str] = set()
    for raw in output.splitlines():
        match = re.search(r'"([^"]+)"\s*=>\s*disabled', raw)
        if match:
            disabled.add(match.group(1))
    return disabled


def parse_launchctl_environment(output: str) -> dict[str, str]:
    """Parse the explicit ``environment =`` block from ``launchctl print``."""
    env: dict[str, str] = {}
    in_environment = False
    for raw in output.splitlines():
        line = raw.strip()
        if line == "environment = {":
            in_environment = True
            continue
        if in_environment and line == "}":
            break
        if not in_environment:
            continue
        key, sep, value = line.partition("=>")
        if not sep:
            continue
        env[key.strip()] = value.strip()
    return env


def find_non_desktop_telegram_sockets(lsof_output: str) -> list[str]:
    """Return socket lines that look Telegram-owned but not Telegram Desktop."""
    offenders: list[str] = []
    for raw in lsof_output.splitlines():
        line = raw.rstrip()
        if not line or line.startswith("COMMAND"):
            continue
        if not any(pattern in line for pattern in TELEGRAM_NETWORK_PATTERNS):
            continue
        if ALLOWED_TELEGRAM_PROCESS_RE.search(line):
            continue
        offenders.append(line)
    return offenders


def load_json_url(url: str, *, timeout: float = 2.0) -> tuple[dict[str, Any] | None, str | None]:
    """Load JSON from a local HTTP endpoint without raising."""
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:  # nosec B310 - local audit URLs only
            payload = json.loads(resp.read().decode("utf-8"))
            if isinstance(payload, dict):
                return payload, None
            return None, "payload_not_dict"
    except (OSError, urllib.error.URLError, json.JSONDecodeError) as exc:
        return None, f"{type(exc).__name__}: {exc}"


def build_report(
    *,
    launch_agents: dict[str, dict[str, str | int | None]],
    disabled_labels: set[str],
    telegram_socket_offenders: list[str],
    pm_bot_ownership: dict[str, Any] | None,
    pm_bot_error: str | None,
    inference_status: dict[str, Any] | None,
    inference_error: str | None,
    soc_launch_env: dict[str, str] | None = None,
    soc_launch_error: str | None = None,
) -> dict[str, Any]:
    """Build a sanitized Telegram sender ownership report."""
    checks: list[dict[str, Any]] = []

    hermes = launch_agents.get("ai.hermes.gateway")
    checks.append(
        _check(
            "hermes_gateway_polling_disabled",
            "fail" if hermes else "ok",
            "ai.hermes.gateway must stay disabled until PM bot owns ingress.",
            {
                "loaded": bool(hermes),
                "pid": hermes.get("pid") if hermes else None,
                "disabled": "ai.hermes.gateway" in disabled_labels,
            },
        )
    )

    healthz = launch_agents.get("com.sapphire.healthz-watcher")
    checks.append(
        _check(
            "healthz_watcher_direct_send_paused",
            "fail" if healthz else "ok",
            "The legacy health watcher has a direct sendMessage branch and should not run during Telegram agent rollout.",
            {
                "loaded": bool(healthz),
                "pid": healthz.get("pid") if healthz else None,
                "disabled": "com.sapphire.healthz-watcher" in disabled_labels,
            },
        )
    )

    soc = launch_agents.get("com.sapphire.soc-dashboard")
    if soc and soc_launch_env is None:
        checks.append(
            _check(
                "soc_dashboard_alerts_routed_to_pm_drafts",
                "warn",
                "Could not read SOC LaunchAgent environment; verify SOC is not using direct Telegram sends.",
                {
                    "loaded": True,
                    "pid": soc.get("pid"),
                    "error": soc_launch_error,
                },
            )
        )
    elif soc:
        live_telegram_enabled = _env_enabled(
            soc_launch_env.get("SOC_TELEGRAM_ALERTS_ENABLED"), default=False
        )
        draft_queue_enabled = _env_enabled(
            soc_launch_env.get("SOC_ALERT_DRAFT_QUEUE_ENABLED"), default=True
        )
        draft_queue_path = soc_launch_env.get("SOC_ALERT_DRAFT_QUEUE_PATH") or ""
        routed_to_pm_drafts = draft_queue_path == EXPECTED_PM_DRAFT_QUEUE
        status = "ok"
        if live_telegram_enabled or not draft_queue_enabled or not routed_to_pm_drafts:
            status = "fail"
        checks.append(
            _check(
                "soc_dashboard_alerts_routed_to_pm_drafts",
                status,
                "SOC should write local PM bot drafts and keep direct Telegram sends disabled.",
                {
                    "loaded": True,
                    "pid": soc.get("pid"),
                    "live_telegram_enabled": live_telegram_enabled,
                    "draft_queue_enabled": draft_queue_enabled,
                    "draft_queue_path": draft_queue_path,
                    "expected_draft_queue_path": EXPECTED_PM_DRAFT_QUEUE,
                },
            )
        )

    pm_bot = launch_agents.get("com.sapphire.pm-bot")
    checks.append(
        _check(
            "pm_bot_loaded",
            "ok" if pm_bot else "warn",
            "PM bot should remain the single Bot API owner.",
            {"loaded": bool(pm_bot), "pid": pm_bot.get("pid") if pm_bot else None},
        )
    )

    if pm_bot_ownership:
        polling_active = bool(pm_bot_ownership.get("polling_active"))
        checks.append(
            _check(
                "pm_bot_not_polling_shared_token",
                "fail" if polling_active else "ok",
                "Shared token must not be consumed by local polling.",
                {
                    "mode": pm_bot_ownership.get("mode"),
                    "polling_active": polling_active,
                    "single_ingress_owner": pm_bot_ownership.get("single_ingress_owner"),
                    "agent_group_ready": pm_bot_ownership.get("agent_group_ready"),
                    "agent_group_blockers": pm_bot_ownership.get("agent_group_blockers", []),
                },
            )
        )
    else:
        checks.append(
            _check(
                "pm_bot_ownership_probe",
                "warn",
                "Could not read PM bot ownership endpoint.",
                {"error": pm_bot_error},
            )
        )

    if inference_status:
        relay_enabled = bool(inference_status.get("telegram_relay_enabled"))
        checks.append(
            _check(
                "inference_telegram_relay_disabled",
                "fail" if relay_enabled else "ok",
                "Inference proxy Telegram relay must stay disabled outside a confirmed private-group smoke test.",
                {
                    "telegram_relay_available": inference_status.get("telegram_relay_available"),
                    "telegram_relay_enabled": relay_enabled,
                    "active_route": inference_status.get("active_route"),
                    "mode": inference_status.get("mode"),
                },
            )
        )
    else:
        checks.append(
            _check(
                "inference_failover_probe",
                "warn",
                "Could not read inference proxy failover endpoint.",
                {"error": inference_error},
            )
        )

    checks.append(
        _check(
            "non_desktop_telegram_sockets_absent",
            "fail" if telegram_socket_offenders else "ok",
            "Only Telegram Desktop should have Telegram network sockets before the PM bot webhook is registered.",
            {
                "offender_count": len(telegram_socket_offenders),
                "offenders": telegram_socket_offenders,
            },
        )
    )

    status = _overall_status(check["status"] for check in checks)
    return {
        "status": status,
        "platform": platform.system(),
        "checks": checks,
    }


def collect_report(
    *,
    pm_bot_ownership_url: str,
    inference_status_url: str,
    include_lsof: bool,
) -> dict[str, Any]:
    launch_agents: dict[str, dict[str, str | int | None]] = {}
    disabled_labels: set[str] = set()
    telegram_socket_offenders: list[str] = []
    soc_launch_env: dict[str, str] | None = None
    soc_launch_error: str | None = None

    if platform.system() == "Darwin":
        launch = run_command(["launchctl", "list"])
        launch_agents = parse_launchctl_list(launch.stdout) if launch.returncode == 0 else {}

        uid_result = run_command(["id", "-u"])
        uid_text = uid_result.stdout.strip() if uid_result.returncode == 0 else ""
        if uid_text:
            disabled = run_command(["launchctl", "print-disabled", f"gui/{uid_text}"])
            disabled_labels = parse_disabled(disabled.stdout) if disabled.returncode == 0 else set()
            soc_print = run_command(
                ["launchctl", "print", f"gui/{uid_text}/com.sapphire.soc-dashboard"]
            )
            if soc_print.returncode == 0:
                soc_launch_env = parse_launchctl_environment(soc_print.stdout)
            else:
                soc_launch_error = soc_print.stderr or soc_print.stdout or "launchctl_print_failed"

        if include_lsof:
            lsof = run_command(["lsof", "-nP", "-iTCP"], timeout=8.0)
            telegram_socket_offenders = (
                find_non_desktop_telegram_sockets(lsof.stdout) if lsof.returncode == 0 else []
            )

    pm_bot_ownership, pm_bot_error = load_json_url(pm_bot_ownership_url)
    inference_status, inference_error = load_json_url(inference_status_url)
    return build_report(
        launch_agents=launch_agents,
        disabled_labels=disabled_labels,
        telegram_socket_offenders=telegram_socket_offenders,
        pm_bot_ownership=pm_bot_ownership,
        pm_bot_error=pm_bot_error,
        inference_status=inference_status,
        inference_error=inference_error,
        soc_launch_env=soc_launch_env,
        soc_launch_error=soc_launch_error,
    )


def format_markdown(report: dict[str, Any]) -> str:
    lines = [
        f"Status: {report['status']}",
        "",
        "| Check | Status | Detail |",
        "|---|---:|---|",
    ]
    for check in report["checks"]:
        detail = check["message"]
        data = check.get("data") or {}
        if check["name"] == "pm_bot_not_polling_shared_token":
            detail += f" owner={data.get('single_ingress_owner')} blockers={data.get('agent_group_blockers')}"
        elif check["name"] == "inference_telegram_relay_disabled":
            detail += f" relay_enabled={data.get('telegram_relay_enabled')} route={data.get('active_route')}"
        elif check["name"] == "soc_dashboard_alerts_routed_to_pm_drafts":
            detail += (
                f" live_enabled={data.get('live_telegram_enabled')} "
                f"queue_enabled={data.get('draft_queue_enabled')}"
            )
        elif check["name"] == "non_desktop_telegram_sockets_absent":
            detail += f" offenders={data.get('offender_count')}"
        elif "loaded" in data:
            detail += f" loaded={data.get('loaded')} disabled={data.get('disabled')}"
        lines.append(f"| `{check['name']}` | `{check['status']}` | {detail} |")
    return "\n".join(lines)


def _check(name: str, status: str, message: str, data: dict[str, Any]) -> dict[str, Any]:
    return {"name": name, "status": status, "message": message, "data": data}


def _overall_status(statuses: Any) -> str:
    seen = set(statuses)
    if "fail" in seen:
        return "fail"
    if "warn" in seen:
        return "warn"
    return "ok"


def _env_enabled(value: str | None, *, default: bool) -> bool:
    if value is None:
        return default
    return str(value).strip().lower() not in {"0", "false", "no", "off"}


def _to_int(value: str) -> int | str:
    try:
        return int(value)
    except ValueError:
        return value


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="Emit JSON instead of markdown.")
    parser.add_argument("--no-lsof", action="store_true", help="Skip the local socket owner check.")
    parser.add_argument(
        "--pm-bot-ownership-url",
        default="http://127.0.0.1:18082/telegram/ownership",
    )
    parser.add_argument(
        "--inference-status-url",
        default="http://127.0.0.1:11435/failover/status",
    )
    args = parser.parse_args(argv)

    report = collect_report(
        pm_bot_ownership_url=args.pm_bot_ownership_url,
        inference_status_url=args.inference_status_url,
        include_lsof=not args.no_lsof,
    )
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(format_markdown(report))
    return 1 if report["status"] == "fail" else 0


if __name__ == "__main__":
    raise SystemExit(main())
