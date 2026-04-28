# Telegram Channel Curation Runbook

As of 2026-04-28, this workflow is strictly read-only and no-send. It is for
operator evaluation of candidate Telegram channels and false-positive review of
bot-pumped detections before any channel is added to the local runtime config.

## Safety Boundary

- Do not contact Telegram from this workflow.
- Do not send test messages, join channels, invite bots, or register webhooks.
- Do not commit real private handles, invite links, session files, chat IDs,
  phone numbers, tokens, or operator notes that reveal a private source.
- Do not change trading execution, alerting, or Telegram send paths.
- Keep real channel inventory only in `~/.sapphire/telegram_channels.yaml`.
- Any generated config stub from this workflow must keep `enabled: false`.

The existing Telegram intel reader remains gated separately by
`SAPPHIRE_TELEGRAM_INTEL_LIVE=1`, a local MTProto session, and an enabled local
config. This curation runbook does not satisfy those live gates.

## Inputs

Use the paste-safe schema at
`docs/templates/telegram-channel-curation.schema.json` and the example packet at
`docs/templates/telegram-channel-curation.example.json`.

Candidate records should use local aliases, not real handles:

```json
{
  "candidate_id": "security-feed-alpha",
  "source_ref": "local-alias-only",
  "category": "security",
  "operator_notes": "Public research feed; representative samples only.",
  "sample_messages": [
    {
      "message_id": "sample-001",
      "published_at": "2026-04-28T15:00:00+00:00",
      "author_ref": "analyst-a",
      "text": "CVE-2026-0001 exploit activity observed against edge VPN devices; vendor mitigation and IOCs published."
    }
  ]
}
```

Collect at least three representative samples before considering a channel
eligible for a disabled watchlist entry. Samples should cover normal posts,
edge cases, and at least one recent item. Paste only short excerpts that are
safe to commit.

## Dry-Run Scoring

Run the scorer against a local JSON packet:

```bash
/usr/local/bin/python3 scripts/ops/telegram_channel_curation.py \
  --input docs/templates/telegram-channel-curation.example.json \
  --pretty
```

The scorer is deterministic and local-only. It uses:

- `services.telegram_intel.quality_filter.quality_filter` for text quality,
  redaction, URL defanging, domain tags, and spam checks.
- `lib.security.adversarial_detectors.BotPumpedChannelDetector` for pump
  language, unrealistic profit claims, bot/sniper language, coordination calls,
  repeated cashtags, and burst patterns.

The report always includes safety flags:

- `telegram_contacted: false`
- `telegram_sends_enabled: false`
- `live_collection_enabled: false`
- `trading_critical_path_touched: false`
- `raw_handles_redacted: true`

Treat any different value as a blocker.

## Decision Meanings

- `eligible_for_disabled_watchlist_entry`: The candidate has enough local
  samples, quality is acceptable, and the sample set did not trigger the
  bot-pump detector. This is not live approval. It only means an operator can
  consider copying the disabled config stub into the local home config.
- `manual_review`: Quality is mixed or context is incomplete. Gather more
  samples and source notes.
- `hold_insufficient_samples`: Fewer than three local samples were provided.
- `hold_invalid_category`: Category is outside the runtime set:
  `crypto`, `macro`, `ai`, `security`, `trading`, `governance`.
- `hold_bot_pump_review`: Bot-pump evidence exists. Do not ingest until the
  false-positive review checklist is complete.
- `reject_or_research_more`: The sample set is too weak or too risky for
  near-term ingestion.

## False-Positive Review For Bot-Pumped Detections

Do not dismiss a bot-pump finding from tone alone. A dismissal requires all of
the following evidence in the `bot_pump_reviews` block:

- Independent source links or source aliases supporting the underlying claim.
- `no_profit_claim: true`.
- `no_coordination_burst: true`.
- `no_bot_execution_language: true`.
- Sample message IDs reviewed by the operator.

If any item is missing, the scorer returns `cannot_dismiss_yet`. The safe action
is to quarantine the channel output or keep the candidate disabled while the
operator gathers more context. If all evidence is present, the scorer returns
`eligible_for_false_positive_label`; this labels the review outcome only and
does not enable live collection.

## Promotion Path

1. Create or update a local packet using aliases and safe excerpts.
2. Run `scripts/ops/telegram_channel_curation.py --input <packet> --pretty`.
3. Check that all safety flags are false/disabled except
   `raw_handles_redacted: true`.
4. For any `hold_bot_pump_review`, complete the false-positive checklist or
   keep the channel quarantined.
5. If a candidate is eligible, copy only the disabled config stub into
   `~/.sapphire/telegram_channels.yaml` and replace the placeholder source with
   the real local-only handle.
6. Leave `enabled: false` until a separate live-readiness change explicitly
   authorizes Telegram collection.

## Rollback

This workflow writes no runtime state. To roll back a candidate decision, delete
the local packet or remove the disabled local entry from
`~/.sapphire/telegram_channels.yaml`. If a later live collection lane enabled a
channel, set `enabled: false` and `SAPPHIRE_TELEGRAM_INTEL_LIVE=0` first, then
revert that later PR.

## Local Verification

Focused checks for this workflow:

```bash
/usr/local/bin/python3 -m pytest tests/unit/test_telegram_channel_curation.py -q
/usr/local/bin/python3 scripts/ops/telegram_channel_curation.py \
  --input docs/templates/telegram-channel-curation.example.json \
  --pretty >/tmp/telegram-channel-curation-report.json
git diff --check
```

For a broader Telegram intel sanity check, add:

```bash
/usr/local/bin/python3 -m pytest \
  tests/unit/test_telegram_intel_reader.py \
  tests/unit/test_telegram_intel_quality.py \
  tests/unit/test_adversarial_detectors.py -q
```
