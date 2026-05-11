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

## PM Bot Webhook Readiness

Webhook registration is now plan-first and explicit-apply:

```bash
python3 scripts/ops/pm_bot_webhook_readiness.py \
  --url "https://YOUR-PUBLIC-URL/telegram/webhook" \
  --json
```

The dry-run plan prints the Bot API `setWebhook` payload shape without secret
material and without calling Telegram. To apply, the operator must pass
`--apply` and set `SAPPHIRE_PM_BOT_REGISTER_WEBHOOK_APPLY=1`.

Set `SAPPHIRE_PM_BOT_WEBHOOK_URL` once a public URL is chosen. PM bot health
then distinguishes:

- `webhook_missing`
- `webhook_url_mismatch`
- `webhook_registered`

This prevents a stale webhook URL from looking group-ready.

## Kimi Handoff

Kimi Claw should treat this file and `config/agent_runtime_next.yaml` as the new runtime baseline. The webhook readiness lane is owned here; Kimi should avoid duplicating it and can focus on source adapters such as GDELT from fresh `origin/main`. Kimi should not run a long-poller, hold the Telegram bot token, send Telegram messages, or revive deprecated local gateway services.
