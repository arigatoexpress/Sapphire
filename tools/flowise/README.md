# Flowise Visual Agent Workbench (Sapphire)

This folder adds a secure, reproducible Flowise workspace for visual agent building against Sapphire APIs.

## Goals

- Build and iterate agents visually (chatflows + multi-agent pipelines).
- Keep production controls private and read-only on public surfaces.
- Reuse Sapphire telemetry and strategy context through one stable endpoint.

## Included

- `docker-compose.flowise.yml`: Local Flowise studio stack.
- `.env.example`: Secure baseline env vars for local studio.
- `SAPPHIRE_FLOWISE_PLAYBOOK.md`: Recommended chatflow patterns and node wiring.

## Quick Start (Local)

1. Copy env and set credentials:

```bash
cp /Users/aribs/Sapphire/tools/flowise/env.example /Users/aribs/Sapphire/tools/flowise/.env
```

2. Start studio:

```bash
bash /Users/aribs/Sapphire/scripts/bootstrap_flowise_local.sh
```

3. Open:

- `http://localhost:3001`

## Sapphire Endpoints for Flowise

Use these read-only endpoints in Flowise HTTP nodes:

- `GET https://sapphirealpha.xyz/api/platform/agent-context?hours=24`
- `GET https://sapphirealpha.xyz/api/platform/strategy-ops?days=7`
- `GET https://sapphirealpha.xyz/api/platform/intel-summary?hours=24`
- `GET https://sapphirealpha.xyz/api/platform/metrics`

## Security Notes

- Never use Flowise for direct trade execution credentials in public mode.
- Keep Flowise behind IAM or private network when deployed in cloud.
- If you enable custom JS/function tools, treat it as privileged code execution.
