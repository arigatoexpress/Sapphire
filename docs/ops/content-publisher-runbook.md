# Content Publisher Runbook

Last reviewed: 2026-04-30

## Triage Quickstart

Failure mode addressed: drafts are not being published, OR the ledger shows
duplicate `(platform, kind)` entries, OR a stuck publish is repeatedly retrying
the same payload.

```bash
launchctl print gui/$(id -u)/com.sapphire.content-publisher
```

```bash
tail -n 200 /Users/aribs/Library/Logs/sapphire/content-publisher.err
```

```bash
test -f data/content/published_ledger.json && \
  jq 'group_by(.platform + .kind) | map(select(length > 1))' \
  data/content/published_ledger.json
```

The third command flags duplicate ledger entries that should not exist with the
idempotency contract — non-empty output means the ledger has drifted and needs
a manual review before unblocking. To rerun a stuck publish, drop the pause
flag at `/Users/aribs/.sapphire/routine_pause/content-publisher` first.

Live monitors: dashboard `/observability` content-publisher tile;
`content.published` event stream.
On-call escalation: content owner; p3 unless live posts go out unintentionally
(SAPPHIRE_PUBLISH_LIVE=1) — that is p1 since it is a public-surface mistake.

This runbook covers `com.sapphire.content-publisher`, the scheduled local
publisher that reads rendered content from `data/content/ready/`, dispatches it
through platform clients, writes an idempotency ledger, emits `content.published`
events, and can optionally send a Telegram run summary.

The publisher is dry-run by default in source control, but it is still a
production-adjacent surface. Live mode can post to LinkedIn, send Substack
draft email through Resend, create X posts, or schedule Typefully drafts. Treat
manual runs as write-capable unless the environment is explicitly forced to
dry-run and Telegram summaries are disabled.

## Ownership

| Item | Path |
|---|---|
| LaunchAgent | `infra/launchagents/com.sapphire.content-publisher.plist` |
| Orchestrator | `lib/content/auto_publish.py` |
| Offline draft writer | `lib/content/publisher.py` |
| Platform clients | `lib/content/publishers/` |
| Unit tests | `tests/unit/test_content_publishers.py` |
| Input queue | `data/content/ready/{linkedin,substack,x}/` |
| Draft manifests | `data/content/drafts/` |
| Idempotency ledger | `data/content/published_ledger.json` |
| Stdout log | `/Users/aribs/Library/Logs/sapphire/content-publisher.log` |
| Stderr log | `/Users/aribs/Library/Logs/sapphire/content-publisher.err` |
| Routine pause name | `content-publisher` |

## Runtime Shape

The LaunchAgent runs daily at 06:15 local, 15 minutes after
`com.sapphire.content-engine` writes drafts. It executes:

```bash
/usr/local/bin/python3 -m lib.content.auto_publish
```

The committed plist sets:

| Variable | Value | Meaning |
|---|---|---|
| `SAPPHIRE_PUBLISH_LIVE` | `0` | Platform clients stay dry-run. |
| `SAPPHIRE_CONTENT_TELEGRAM_SUMMARY` | `1` | Local scheduled runs may send a summary. |
| `PYTHONPATH` | `/Users/aribs/Code/Sapphire` | Imports local repo code. |

The orchestrator discovers the newest unpublished rendering per
`(platform, kind)` from the last 48 hours. A successful live publish appends the
ledger so later runs do not repost the same platform/kind pair.

## Destinations

| Platform | Client | Live destination |
|---|---|---|
| LinkedIn | `lib/content/publishers/linkedin.py` | `https://api.linkedin.com/v2/ugcPosts` |
| Substack | `lib/content/publishers/substack.py` | Resend API to `SUBSTACK_POST_EMAIL`; lands as a draft for manual review. |
| X | `lib/content/publishers/x.py` | `https://api.x.com/2/tweets` |
| Typefully | `lib/content/publishers/typefully.py` | `https://api.typefully.com/v1/drafts/` fallback for X. |

Live credentials are read from environment variables only. They must not be
stored in plist files, repo files, screenshots, or PR comments.

## Normal Operation

Check launchd state:

```bash
launchctl list com.sapphire.content-publisher
```

Inspect logs:

```bash
tail -n 200 /Users/aribs/Library/Logs/sapphire/content-publisher.log
tail -n 200 /Users/aribs/Library/Logs/sapphire/content-publisher.err
```

Validate the plist:

```bash
plutil -lint infra/launchagents/com.sapphire.content-publisher.plist
```

Run the safe test path:

```bash
/usr/local/bin/python3 -m pytest \
  tests/unit/test_content_publishers.py \
  tests/unit/test_launchagent_plists.py -q
```

Inspect the queue without writing the ledger or contacting platforms:

```bash
SAPPHIRE_PUBLISH_LIVE=0 SAPPHIRE_CONTENT_TELEGRAM_SUMMARY=0 \
/usr/local/bin/python3 - <<'PY'
from lib.content.auto_publish import discover
for item in discover():
    print(f"{item.platform}/{item.kind}: {item.path}")
PY
```

Avoid `auto_publish.run()` as a strict read-only check: even in dry-run mode it
writes the ledger file. Avoid `launchctl kickstart` as a casual smoke test
because the committed plist enables Telegram summaries.

## Live Publish Gate

Live mode requires all of the following:

1. The operator explicitly approves a live publish window.
2. `SAPPHIRE_PUBLISH_LIVE=1` is set only for that window.
3. The target platform credentials are present and known-current.
4. The queue contents have been reviewed from `data/content/ready/`.
5. The ledger has been backed up if duplicate posting risk exists.
6. Telegram summary behavior is intentionally chosen.

Never use `launchctl setenv SAPPHIRE_PUBLISH_LIVE 1` as a convenience toggle.
If live mode is needed, prefer a one-shot shell with an explicit command and a
clear rollback note.

## Routine Pause

Pause before credential work, queue cleanup, or any suspected duplicate-post
risk:

```bash
mkdir -p ~/.sapphire/routine_pause
date -u +%Y-%m-%dT%H:%M:%SZ > ~/.sapphire/routine_pause/content-publisher
```

Resume after tests and queue inspection are clean:

```bash
rm ~/.sapphire/routine_pause/content-publisher
```

The orchestrator calls `abort_if_paused("content-publisher")` before running.
The global `~/.sapphire/routine_pause/all` pause can also stop the run.

## Common Failures

### No Items Discovered

This is normal when there are no recent files under `data/content/ready/` or
when all current `(platform, kind)` pairs are already in the ledger. Inspect
queue timestamps and the ledger before treating this as a failure.

### Ledger Corruption

`_load_ledger()` logs a warning and resets to an empty ledger on invalid JSON.
That avoids blocking the run, but in live mode it can duplicate posts. Pause the
routine, copy the corrupt ledger aside, reconstruct the published keys from
platform history if needed, and run tests before resuming.

### Missing Credentials

Live clients fail closed with `ok=False` when required env vars are absent:

- LinkedIn: `LINKEDIN_ACCESS_TOKEN`, `LINKEDIN_AUTHOR_URN`
- Substack/Resend: `RESEND_API_KEY`, `SUBSTACK_POST_EMAIL`,
  `RESEND_FROM_EMAIL`
- X: `X_API_KEY`, `X_API_SECRET`, `X_ACCESS_TOKEN`, `X_ACCESS_SECRET`
- Typefully: `TYPEFULLY_API_KEY`

Do not paste token values into logs or issue comments while debugging.

### X Partially Posts a Thread

The X client posts one tweet at a time. A later tweet can fail after earlier
tweets are live. The ledger only records full live success, so an immediate
rerun can duplicate the beginning of a thread. Pause, record the remote IDs,
and decide manually whether to delete, complete, or mark the ledger.

### Typefully Auto-Publishes Unexpectedly

The Typefully client defaults to `schedule="next-free-slot"` and
`auto_publish=True` when used live as the X fallback. Treat a live Typefully
call as a scheduled publish, not as a harmless draft creation.

### Telegram Summary Sends During a Test

The committed local LaunchAgent sets `SAPPHIRE_CONTENT_TELEGRAM_SUMMARY=1`.
Tests and manual inspections should override it to `0`. If a summary fires
unexpectedly, save the output/logs, confirm whether live platform posts were
made, and reset the environment before rerunning.

## Recovery

Back up the ledger before manual live work:

```bash
test -f data/content/published_ledger.json && cp \
  data/content/published_ledger.json \
  data/content/published_ledger.json.$(date -u +%Y%m%dT%H%M%SZ).bak
```

Back up logs before truncating or rotating:

```bash
cp /Users/aribs/Library/Logs/sapphire/content-publisher.log \
  /Users/aribs/Library/Logs/sapphire/content-publisher.log.$(date -u +%Y%m%dT%H%M%SZ).bak
cp /Users/aribs/Library/Logs/sapphire/content-publisher.err \
  /Users/aribs/Library/Logs/sapphire/content-publisher.err.$(date -u +%Y%m%dT%H%M%SZ).bak
```

Then run:

```bash
SAPPHIRE_PUBLISH_LIVE=0 SAPPHIRE_CONTENT_TELEGRAM_SUMMARY=0 \
/usr/local/bin/python3 -m pytest tests/unit/test_content_publishers.py -q
```

Resume the routine only after the queue, ledger, and intended environment are
understood.

## Safety Notes

- Do not set `SAPPHIRE_PUBLISH_LIVE=1` without explicit operator approval.
- Do not use `launchctl kickstart` as a dry-run smoke test while Telegram
  summaries are enabled.
- Do not edit or delete `data/content/published_ledger.json` casually.
- Do not run `python3 -m lib.content --publish` without forcing
  `SAPPHIRE_PUBLISH_LIVE=0` and `SAPPHIRE_CONTENT_TELEGRAM_SUMMARY=0`.
- Do not publish to LinkedIn, X, Typefully, Resend, or Substack outside an
  approved live window.
- Do not commit generated queue, draft, or ledger changes from manual tests.

## Escalation

Escalate when:

- A live platform post or Telegram summary fires unexpectedly.
- The ledger is corrupt before or after a live run.
- A platform returns partial success.
- Duplicate-post risk exists.
- Content quality or approval state is unclear for a queued item.

Include launchd status, queue item paths, ledger backup path, platform result
metadata with tokens redacted, last 200 log lines, and whether
`SAPPHIRE_PUBLISH_LIVE` or `SAPPHIRE_CONTENT_TELEGRAM_SUMMARY` was set.
