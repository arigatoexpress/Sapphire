# Grok-related automations

_Count: 13 · by_status: {'live': 7, 'monorepo_ready_plant_pending': 1, 'paper_only_not_armed_until_p0': 1, 'read_only': 1, 'dry_run_default': 1, 'plant': 1, 'policy_in_monorepo': 1}_

| id | surface | status | action |
|---|---|---|---|
| `grok-system-streamline` | script | live | compose alpha+policy+bridge brief; --write --export |
| `grok-mac-bridge-http` | mac-service | live | LaunchAgent optional; ensure start.sh + GROK_BRIDGE_URL in zshrc |
| `grok-web-bridge-launchagent` | mac-launchagent | live | keep; wraps scripts/ops/sync_grok_web_exports.sh |
| `grok-web-export-store` | git | live | keep; enforce frontmatter via grok_bridge_status |
| `sync-grok-web-exports` | script | monorepo_ready_plant_pending | Claude: wrap in ops-state finish-line + LaunchAgent |
| `grok-bridge-status` | script | live | keep; write MANIFEST.json |
| `grok-loop-tick` | script | live | steer TASKBOARD from signals |
| `gcp-cloudshell-bootstrap` | script | live | keep fences + master plan pointers |
| `win-research-worker` | windows-schtask | paper_only_not_armed_until_p0 | validate manifests; do not ARM until P0 |
| `win-tv-agent` | windows-schtask | read_only | keep read-only; no mutate without gate |
| `gemini-ooda-daily` | mac-launchagent | dry_run_default | keep SAPPHIRE_GEMINI_LIVE=0 unless gated |
| `ralph-densify` | plant | plant | ingest grok-web-exports after sync |
| `free-reign-multi-rail` | plant | policy_in_monorepo | wire evaluate_proposal before sole writer |
