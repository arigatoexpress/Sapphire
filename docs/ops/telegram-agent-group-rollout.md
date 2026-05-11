# Telegram Agent Group Rollout

Sapphire's private Telegram operator group should be created only after the
Bot API ownership path is boring. The PM bot is the single ingress owner.
Kimi and Nemotron can collaborate in the group, but they must not run competing
long-pollers or use the shared bot token to send free-form relay chatter.

## Current gates

Run these read-only probes from the Mac:

```bash
curl -fsS http://127.0.0.1:18082/telegram/ownership | python3 -m json.tool
curl -fsS http://127.0.0.1:11435/failover/status | python3 -m json.tool
```

Expected before group creation:

- `agent_group_ready=true` on PM bot ownership, or a clearly accepted blocker.
- `mode=webhook`; polling is not active for the shared bot token.
- `telegram_delivery_ready=true` after the webhook is registered.
- `telegram_relay_enabled=false` in inference-proxy unless Ari explicitly
  confirms a relay test in the private group.
- Windows GPU being offline is acceptable only if Mac local fallback is healthy
  and model aliases preserve Nemotron's local equivalent.

## Rollout order

1. Register the PM bot webhook with the secret-token header.
2. Create the private supergroup and topics: `ops`, `markets`, `crypto`,
   `macro`, `cyber`, `research`, `drafts`.
3. Invite Kimi Claw after its Sapphire deploy key and repo clone are confirmed.
4. Keep Nemotron as a read-only/draft participant until the relay and mock-data
   paths are quiet for a full test window.
5. Enable `KIMI_RELAY_ENABLED=1` only for a named, time-boxed relay smoke test.
6. Disable the relay again after the smoke test unless it has a dedicated
   queue, provenance envelope, and Ari confirmation path.

## Never do this

- Do not run two long-pollers against one Telegram bot token.
- Do not let inference-proxy use Telegram as an implicit fallback just because
  cloud API keys are missing.
- Do not send public/customer/external Telegram messages from this rollout.
- Do not invite a new agent into the group while it is still emitting mock
  observations, dry-run baselines, or unstamped sample data as if they were
  live intelligence.

## Operator status template

```text
Status:
Changed:
Verified:
Blocked:
Next:
```
