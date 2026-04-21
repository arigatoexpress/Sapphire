# LaunchAgents & Scheduled Tasks Audit — 2026-04-21

Holistic review of the agent routines the system depends on. Written
autonomously during overnight work; Ari to review + execute recommendations.

## TL;DR

| Surface | Count on Mac | Count in Repo (before) | Count in Repo (after this audit) |
|---|---|---|---|
| Sapphire LaunchAgents (active) | 23 | 11 | **21** |
| Sapphire LaunchAgents (disabled) | 2 | 1 | 1 |
| Hermes LaunchAgent | 1 | 0 | 0 (lives in `~/.hermes/`) |
| Claude scheduled tasks | 21 | 21 (under `~/.claude/`) | 21 |

**Before this audit**: 12 of the 23 active production LaunchAgents were
running on Ari's Mac with zero version control — a direct durability /
reproducibility risk. If the Mac disk fails, those 12 agents (and their
cron cadences, env vars, log-path conventions) vanish.

**After this audit**: 10 of the 12 un-versioned plists are copied into
`infra/launchagents/` verbatim (they had no embedded secrets — just paths
and non-secret config). The remaining 2 that embed live secrets are
flagged below with sanitized templates to produce in a follow-up.

## Critical findings

### F1. Live Telegram bot token in `com.sapphire.inference-proxy.plist` (Mac only)
The plist currently embeds a `RELAY_READER_TOKEN` (Telegram bot token)
and `KIMI_RELAY_CHAT_ID` as plaintext `<string>` values inside
`EnvironmentVariables`. The actual values are intentionally **not
included in this doc** — they're on the Mac only.

**Risk**: compromised Mac → token usable anywhere. Not in git (fine) but
also not versioned (bad).

**Fix**: move both to `~/.sapphire/secrets.env` (mode 0600). Rewrite the
plist to source them via a shell wrapper. CLAUDE.md already describes
this pattern for `MOONSHOT_API_KEY`.

Not applied in this commit — requires Mac state change + a token rotation
(the token has appeared in a Claude session transcript; rotate as a
precaution).

### F2. `AUTH_PASSWORD=sapphire` in `com.sapphire.dashboard.plist` (Mac only)
Documented in CLAUDE.md, so not a secret — but still better as env. Same
sanitization approach as F1.

### F3. Two repo plists never installed on Mac
- `com.sapphire.alpha-agent.plist` — in repo, not in `~/Library/LaunchAgents/`.
- `com.sapphire.content-publisher.plist` — same.

Either install them (`launchctl bootstrap gui/$UID ...`) or remove them
from the repo if they're no longer wanted.

### F4. Duplicate-intent agents
- `com.sapphire.morning-brief.plist` (LaunchAgent, 7 AM CT, 12 sections, sends via Telegram)
- `~/.claude/scheduled-tasks/sapphire-morning-briefing/` (Claude scheduled task, 8 AM, 7 sections, sends via Telegram)

These overlap. Morning brief is the canonical production path
(LaunchAgent runs even when Claude Code is closed). The scheduled task
duplicates ~80% of its work one hour later and only runs while Claude
Code is open — this is drift, not intent. Recommend either:
  - **consolidate**: delete the scheduled task, extend the LaunchAgent
    to cover the extra sections (threat-intel, github, regional);
  - **specialize**: rename the scheduled task to
    `sapphire-afternoon-deep-dive` with non-overlapping work.

Similar overlap candidates to check:
- `com.sapphire.daily-brief.plist` (06:00 LaunchAgent) vs
  `com.sapphire.morning-brief.plist` (07:00 LaunchAgent) — two near-
  identical agents 60 min apart, both generating briefs.
- `com.sapphire.security-pipeline.plist` (daily 3 AM) vs
  `~/.claude/scheduled-tasks/dependency-security-scan/` (Wed 4 AM) —
  the weekly is a narrower subset; keep both only if the narrower check
  actually catches more (unlikely).

## Clean plists now version-controlled (this commit)

Copied verbatim from `~/Library/LaunchAgents/` — each verified to contain
no embedded secret values (only paths + non-secret config):

1. `com.sapphire.control-plane.plist` — uvicorn on `:8082`, in-memory store
2. `com.sapphire.signal-logger.plist` — uvicorn on `:18081`, paper trading
3. `com.sapphire.openbb-api.plist` — OpenBB REST on `:6900`
4. `com.sapphire.chain-refresh.plist` — chain intel every 15 min
5. `com.sapphire.threat-refresh.plist` — threat feed every 4 h
6. `com.sapphire.correlation-refresh.plist` — hourly at :17
7. `com.sapphire.daily-brief.plist` — 06:00 daily
8. `com.sapphire.telemetry-collector.plist` — every 5 min
9. `com.sapphire.logrotate.plist` — 03:30 daily
10. `com.sapphire.gcp-sync.plist` — hourly at :05

## Not versioned (by design or pending secret extraction)

| Plist | Status | Reason |
|---|---|---|
| `com.sapphire.dashboard.plist` | pending | Embeds `AUTH_PASSWORD` (F2) |
| `com.sapphire.inference-proxy.plist` | pending | Embeds Telegram token (F1) |
| `ai.hermes.gateway.plist` | skip | Lives at `~/.hermes/`, not under Sapphire repo scope |
| `com.sapphire.cloudflare-tunnel.plist` | skip | User-specific cert paths; not reproducible across machines |
| `com.sapphire.kronos-daily.plist` | skip | Points to `~/Code/Kronos/.venv/bin/python3` — separate repo |
| `com.sapphire.regional-intel.plist` | skip | Points to `~/Code/regional-intel-workbench/` — separate repo |
| `com.sapphire.nemotron-bot.plist.disabled` | skip | Disabled; no longer in use |
| `com.sapphire.sync-eu-proxy-firewall.plist.disabled` | skip | Disabled |

## Scheduled tasks — cadence map

| Task | Cadence | Delivers to |
|---|---|---|
| sapphire-morning-briefing | 08:00 daily | Telegram |
| trading-research | 05:42 daily | logs + Telegram |
| market-pulse | 08/12/16 M–F | Telegram |
| threat-intel-sweep | 06:30 + 14:00 daily | logs |
| github-discovery | 07:00 daily | logs |
| tho-production-healthcheck | every 2 h | Telegram on red |
| tho-test-writer | 11:00 + 23:00 daily | PR |
| creative-experimenter | 02:00 daily | logs |
| factory-test-guardian | 03:00 + 15:00 daily | PR on failure |
| factory-repo-fixer | every 6 h | PR |
| code-quality-sweep | 13:00 daily | PR |
| evening-digest | 18:00 daily | Telegram |
| sapphire-self-improvement | 20:53 daily | logs |
| sapphire-ci-monitor | every 3 h | alert on red |
| factory-client-delivery | 10:00 M–F | logs |
| vote-monitor-collector | every 4 h | Firestore |
| dependency-security-scan | 04:00 Wed | alert |
| sapphire-weekly-review | 09:00 Sun | report |
| backtest-sweep | weekly | artifact |
| lead-generation | daily | CRM |
| pull-gcp-secrets | on-demand | — |

Observation: **morning brief, trading research, market pulse, GitHub
discovery, and threat intel all run between 5:42 and 08:00** —
near-simultaneous bursts. If any depend on each other's output,
serializing would help; if not, this is fine but the Ollama tier sees
a load spike right before markets open.

## Recommendations (for human review)

### Quick wins (safe to do now)
1. ✅ **Version the 10 clean plists** — done in this commit.
2. **Rotate the Telegram bot token in F1** — assume burned.
3. **Decide F3**: install or delete `alpha-agent.plist` and
   `content-publisher.plist`.

### Medium effort
4. Sanitize + version the 2 secret-carrying plists (F1/F2) with a
   shell-wrapper that sources `~/.sapphire/secrets.env`.
5. Consolidate the duplicated morning-brief surfaces (F4).
6. Remove the two `.disabled` plists entirely once confirmed dead.

### Optimization
7. Spread out the 5:42–08:00 burst onto a staggered schedule if any
   task-graph dependencies make the current near-simultaneous run
   fragile (run `sapphire-ci-monitor` around that window to see if
   anything times out).
8. Add an **install script** (`infra/install-launchagents.sh`) that
   copies everything in `infra/launchagents/*.plist` to
   `~/Library/LaunchAgents/` and `launchctl bootstrap` them — one
   command to reproduce production from repo state.
