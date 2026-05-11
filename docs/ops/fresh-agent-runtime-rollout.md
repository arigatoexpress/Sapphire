# Fresh Agent Runtime Rollout

Status: draft-only, no-send, local fallback installed separately.

## Current Direction

Sapphire's Telegram system is moving to a fresh runtime:

- Sapphire PM bot remains the single Telegram Bot API ingress owner.
- Kimi K2.6 is the long-context operator lane.
- Gemini on Vertex handles structured triage, extraction, clustering, cited synthesis, and evals.
- Google ADK is the preferred GCP-native harness for future deployable agent workflows.
- Local Ollama is fallback-only for sensitive or offline work, with `gemma4:latest` as the fresh default fallback and `qwen3.6:27b` as the heavy local backup.

## Deprecated Local Services

These local bot and tunnel LaunchAgents should stay disabled or quarantined:

- `ai.hermes.gateway`
- `ai.openclaw.gateway`
- `com.sapphire.healthz-watcher`
- `com.sapphire.mac-to-windows-tunnel`

Rollback is intentionally simple: move the archived plist back into `~/Library/LaunchAgents`, then run `launchctl enable gui/$(id -u)/<label>` and `launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/<label>.plist`.

## Readiness Check

Run:

```bash
python3 scripts/ops/fresh_agent_runtime_status.py --json
```

The report is read-only. It does not call Telegram, hosted model APIs, or `launchctl` mutating commands.

Expected result after local setup:

- deprecated LaunchAgents unloaded
- `gemma4:latest` and `qwen3.6:27b` installed in Ollama
- Google ADK installed or explicitly marked pending
- PM bot and draft queue remain the only Telegram path for future sends

## PM Bot Draft Queue

Agentic Telegram update types now leave local dry-run records instead of
disappearing into logs:

- callback queries
- message reactions and reaction counts
- guest and business messages
- inline queries
- blocked payment or high-risk callback updates

Default queue path:

```bash
~/.cache/sapphire/telegram/pm_bot_drafts.jsonl
```

Runtime overrides:

```bash
SAPPHIRE_PM_BOT_DRAFT_QUEUE_PATH=/path/to/pm_bot_drafts.jsonl
SAPPHIRE_PM_BOT_DRAFT_QUEUE_ENABLED=1
SAPPHIRE_PM_BOT_AGENTIC_DRY_RUN=1
```

The queue is still no-send. Callback updates do not call
`answerCallbackQuery`, inline queries do not call `answerInlineQuery`, and no
non-command route calls `sendMessage`.

## Kimi Handoff

Kimi Claw should treat this file and `config/agent_runtime_next.yaml` as the new runtime baseline. The next PR should integrate PM bot webhook handling with the draft queue behind dry-run flags only. Kimi should not run a long-poller, hold the Telegram bot token, send Telegram messages, or revive deprecated local gateway services.
