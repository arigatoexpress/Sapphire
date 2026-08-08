"""Catalog of Grok-related automations (inventory only — no mutations)."""

from __future__ import annotations

from typing import Any

AUTOMATIONS: list[dict[str, Any]] = [
    {
        "id": "grok-drive-pack",
        "surface": "monorepo+drive",
        "path": "scripts/ops/grok_drive_pack.py",
        "cadence": "on densify or hourly (plant optional)",
        "owner": "grok-web",
        "status": "live",
        "action": "Build sanitized Drive pack → Sapphire/Grok Bridge folders",
    },
    {
        "id": "grok-system-streamline",
        "surface": "script",
        "path": "scripts/ops/grok_system_streamline.py",
        "cadence": "each loop tick / densify",
        "owner": "grok-project",
        "status": "live",
        "action": "compose alpha+policy+bridge brief; --write --export",
    },
    {
        "id": "grok-mac-bridge-http",
        "surface": "mac-service",
        "path": "services/grok-bridge/",
        "cadence": "always (LaunchAgent)",
        "owner": "claude-plant",
        "status": "live",
        "action": "LaunchAgent optional; ensure start.sh + GROK_BRIDGE_URL in zshrc",
    },
    {
        "id": "grok-web-bridge-launchagent",
        "surface": "mac-launchagent",
        "path": "infra/launchagents/com.sapphire.grok-web-bridge.plist",
        "cadence": "30m densify beat",
        "owner": "claude-plant",
        "status": "live",
        "action": "keep; wraps scripts/ops/sync_grok_web_exports.sh",
    },
    {
        "id": "grok-web-export-store",
        "surface": "git",
        "path": "data/grok-web-exports/",
        "cadence": "on commit",
        "owner": "grok-web + plant local-export",
        "status": "live",
        "action": "keep; enforce frontmatter via grok_bridge_status",
    },
    {
        "id": "sync-grok-web-exports",
        "surface": "script",
        "path": "scripts/ops/sync_grok_web_exports.sh",
        "cadence": "15–60m plant densify",
        "owner": "claude-plant wire",
        "status": "monorepo_ready_plant_pending",
        "action": "Claude: wrap in ops-state finish-line + LaunchAgent",
    },
    {
        "id": "grok-bridge-status",
        "surface": "script",
        "path": "scripts/ops/grok_bridge_status.py",
        "cadence": "on demand / loop tick",
        "owner": "grok-project",
        "status": "live",
        "action": "keep; write MANIFEST.json",
    },
    {
        "id": "grok-loop-tick",
        "surface": "script",
        "path": "scripts/ops/grok_loop_tick.py",
        "cadence": "each Grok chat turn / cron optional",
        "owner": "grok-project",
        "status": "live",
        "action": "steer TASKBOARD from signals",
    },
    {
        "id": "gcp-cloudshell-bootstrap",
        "surface": "script",
        "path": "scripts/ops/gcp_cloudshell_bootstrap.sh",
        "cadence": "Cloud Shell session start",
        "owner": "gemini+grok",
        "status": "live",
        "action": "keep fences + master plan pointers",
    },
    {
        "id": "win-research-worker",
        "surface": "windows-schtask",
        "path": "scripts/windows_setup/run_research_worker.ps1",
        "cadence": "daily after smoke",
        "owner": "windows-dc",
        "status": "paper_only_not_armed_until_p0",
        "action": "validate manifests; do not ARM until P0",
    },
    {
        "id": "win-tv-agent",
        "surface": "windows-schtask",
        "path": "scripts/windows_setup/start_tv_agent.ps1",
        "cadence": "logon / always",
        "owner": "windows-dc",
        "status": "read_only",
        "action": "keep read-only; no mutate without gate",
    },
    {
        "id": "gemini-ooda-daily",
        "surface": "mac-launchagent",
        "path": "infra/launchagents/com.sapphire.gemini-ooda-daily.plist",
        "cadence": "daily 06:30",
        "owner": "mac-commander",
        "status": "dry_run_default",
        "action": "keep SAPPHIRE_GEMINI_LIVE=0 unless gated",
    },
    {
        "id": "ralph-densify",
        "surface": "plant",
        "path": "ops-state densify/Ralph loops",
        "cadence": "30–60m",
        "owner": "claude-plant",
        "status": "plant",
        "action": "ingest grok-web-exports after sync",
    },
    {
        "id": "free-reign-multi-rail",
        "surface": "plant",
        "path": "ops-state free-reign.json + lib/grok/policy.py",
        "cadence": "continuous when armed",
        "owner": "plant + grok policy",
        "status": "policy_in_monorepo",
        "action": "wire evaluate_proposal before sole writer",
    },
]


def catalog() -> list[dict[str, Any]]:
    return list(AUTOMATIONS)


def summary() -> dict[str, Any]:
    by_status: dict[str, int] = {}
    for a in AUTOMATIONS:
        by_status[a["status"]] = by_status.get(a["status"], 0) + 1
    return {"count": len(AUTOMATIONS), "by_status": by_status}
