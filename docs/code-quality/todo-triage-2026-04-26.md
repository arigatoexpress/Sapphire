# TODO / FIXME / XXX / HACK Triage — 2026-04-26

Doc-only sweep to surface deferred work and prune stale annotations. No
production code is touched in this PR; any code change is a separate,
single-line follow-up.

## Method

From the worktree root:

```bash
grep -rn -E "TODO|FIXME|XXX|HACK" \
  --include="*.py" --include="*.ts" --include="*.tsx" --include="*.sol" \
  --include="*.md" --include="*.yml" --include="*.yaml" \
  --exclude-dir=.git --exclude-dir=node_modules \
  --exclude-dir=.claude --exclude-dir=data .
```

Results were filtered to remove out-of-scope paths
(`pine/standalone/legacy/`, `services/scout-sandbox/`,
`services/aster/`, lock files); none of the 25 raw matches fell into
those paths so the visible list is the full set. Each match was
classified by reading 5–10 lines of surrounding context.

## Tally

| Bucket | Count |
|--------|------:|
| A — ACTIVE, needs work       |  4 |
| B — STALE, can be removed    |  5 |
| C — TRACKED elsewhere        |  4 |
| D — CONVENTION, not actionable | 12 |
| **Total**                    | **25** |

## Bucket A — needs work

Real shortcomings the code admits, not yet tracked elsewhere as a
GitHub issue or design doc. Sorted by criticality (impact on shipped
behaviour first).

| File:line | Description | Owner area |
|-----------|-------------|------------|
| `services/alpha/src/media/linkedin.py:48` | `publish()` is a mock that logs and returns `"mock-linkedin-urn"`; the real LinkedIn POST is unimplemented. Content engine LinkedIn route is effectively a no-op. | content |
| `services/hyperliquid/src/hyperliquid_bot/main.py:65` | `_run_loop` polls a `while self.running: sleep(5)` body; pubsub subscribe to `trading-signals` is missing, so the bot never receives signals to execute. | trading |
| `lib/agents/alpha_agent.py:394` | `_todo_close_hook` returns a `pending_hook` placeholder instead of mutating the paper portfolio when an `Action` resolves a close. Paper-close path is dangling. | analytics |
| `docs/web-integrations.md:100` | Inline note `see docs/oauth-linkedin.md TODO` references a file that does not exist; LinkedIn refresh-token flow is undocumented (token expires in 60 days). | content / docs |

## Bucket B — stale, can be removed

Annotations that point to behaviour or code that no longer exists.
Recommend a single follow-up sweep PR to delete them.

| File:line | Why stale |
|-----------|-----------|
| `results/end_of_day_status_2026-04-18.md:188` | Cites `lib/chain/providers/dune.py` TODO; the file no longer contains any TODO. |
| `results/end_of_day_status_2026-04-18.md:189` | Cites `lib/content/auto_publish.py` TODO; resolved upstream — file no longer contains it. |
| `results/end_of_day_status_2026-04-18.md:190` | Cites `lib/content/publishers/substack.py` TODO; resolved upstream. |
| `results/end_of_day_status_2026-04-18.md:191` | Cites `lib/analytics/cpcv.py` TODO; resolved upstream. |
| `scripts/archived/monitor_and_alert.py:145` | `# TODO: Send to Telegram bot, email, etc.` inside `scripts/archived/` — file is archived; not on any live path. Hermes/notify pipeline supersedes it. |

The four `end_of_day_status_2026-04-18.md` entries are inside a dated
status snapshot, so a "delete the bullets" sweep would alter a
historical artifact. The defensible alternative is a small
clarification banner above that block ("verified resolved 2026-04-26")
rather than deletion. Either way it is one tiny PR.

## Bucket C — tracked elsewhere

Cross-references and section headings; the work is captured in the
audit/tracking doc that contains the marker itself.

| File:line | Tracking artifact |
|-----------|-------------------|
| `docs/audit.md:72` | `## Still TODO (not done)` — section header in `docs/audit.md` enumerating 4 follow-ups (opus-audit re-verify, retire/wire decisions, plugin-surface stabilization, Tailscale route flakes). The doc IS the tracker. |
| `results/audit-2026-04-18.md:100` | `### TODO Inventory (complete)` — heading introducing the cross-references that follow. |
| `results/audit-2026-04-18.md:102` | Cross-reference to `services/alpha/src/media/linkedin.py:48` (Bucket A item). |
| `results/audit-2026-04-18.md:103` | Cross-reference to `services/hyperliquid/.../main.py:65` (Bucket A item). |

## Bucket D — conventions / not actionable

12 hits, all string literals, log format placeholders, usage examples,
or quoted documentation. No action required.

Examples (full list omitted for noise reduction):
- `TOPIC-XXXXX`, `pipeline_XXXX.json`, `CVE-XXXX-NNNN`, `?symbol=XXX`
  in usage strings or log format placeholders.
- The `frontend-audit-v2.md` line that quotes `Linear writes "Todo",
  not "TODO"` to make a UI-style argument.
- `| TODO comments | 2 |` cells in audit metric tables.

## Recommended top-3 actions

Each bullet is intended as its own single-purpose PR.

1. **Bucket B sweep PR** — annotate the four stale lines in
   `results/end_of_day_status_2026-04-18.md` with a single
   "(resolved 2026-04-26)" suffix per row, and delete the dead
   `# TODO: Send to Telegram bot, email, etc.` line in
   `scripts/archived/monitor_and_alert.py`. ~5 lines of doc edit + 1
   line of comment removal in archived code; zero behavioural risk.

2. **Document LinkedIn refresh-token flow** — create
   `docs/oauth-linkedin.md` (referenced from `web-integrations.md:100`)
   with the 3-legged OAuth refresh path. Owner area: content. This is
   the prerequisite for retiring the mock `publish()` in
   `services/alpha/src/media/linkedin.py`. Doc-only PR.

3. **Wire `alpha_agent._todo_close_hook` to the paper portfolio** —
   the `pending_hook` placeholder in `lib/agents/alpha_agent.py:394`
   currently silently no-ops position closes. Touches an
   analytics/agents code path so it needs a proper PR with tests in
   `tests/unit/test_alpha_agent.py` (or the equivalent), not a casual
   inline change. Owner area: analytics / agents.

Bucket A items 2 and 4 (Hyperliquid pubsub subscribe, mock LinkedIn
publish) are both substantial product features rather than triage
follow-ups; flag them on the roadmap rather than auto-spawning PRs
from this triage.
