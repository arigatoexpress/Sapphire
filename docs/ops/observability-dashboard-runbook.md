# Observability Dashboard Runbook

> Status: live as of Tranche 3, Lane 2 (2026-04-28)
> Surface: `/observability` (HTML), `/api/observability-system-summary`,
> `/api/observability-stream-rates`, `/api/observability-launchagents`
> Owner: Sapphire Operator (Ari)

## What this dashboard answers

`/observability` is the single-pane-of-glass view of Sapphire's running
state. A buyer's lead engineer (Palantir / Robinhood corp-dev) — or the
operator on a tired Saturday — should be able to load this page and form
an accurate picture of system health in under 30 seconds, without leaning
on Slack, Telegram, or `tail -f`.

It folds six previously-disjoint surfaces into one panel-grid:

1. **System Heartbeat** — every macOS LaunchAgent declared by the repo
   (`infra/launchagents/*.plist` + `services/*/launchagent/*.plist`),
   with live PID, last exit code, last-fire time (from log mtime), and
   restart count from `data/supervisor_state.json` when present.
2. **Inference Proxy** — 4-tier health (T1 Windows GPU, T2 Pi, T3 Mac,
   T4 Kimi) and lifetime token consumption, sourced from
   `~/.cache/sapphire/inference_proxy/{tier_health,token_consumption}.json`
   when the proxy daemon emits them. Falls back to a deterministic
   placeholder when the cache is absent.
3. **Signal Streams** — per-source rates (1h and 24h) and freshness for
   TradingView, Telegram intel, Hyperliquid, threat-intel, and
   convergence-watchlist. Each row is a count of JSONL records inside
   `data/<source_dir>/*.jsonl` with timestamps ≥ the cutoff.
4. **Provenance Coverage** — sidecar verification stats from
   `scripts/ops/provenance_verify.py`. Reports `checked`,
   `missing_or_invalid`, last verify timestamp, and a sample of the
   most-recent invalid artifacts.
5. **Routine Pause Status** — every flag file under
   `~/.sapphire/routine_pause/` (skipping dotfiles and non-routine
   names), with the operator-set timestamp.
6. **Event Bus** — topic distribution from the tail of
   `data/events/bus.jsonl`, capped at 256 KB / 200 events to keep the
   page snappy even if Redis went out and the JSONL fallback grew.

The page polls every 15 seconds. The HTTP endpoints are stateless GET-only
and inherit dashboard auth (`AUTH_PASSWORD` basic auth).

## Architecture

```
                 +-------------------------+
                 |  /observability (HTML)  |
                 +-----------+-------------+
                             | fetch()  every 15s
              +--------------+----------------+
              |              |                |
   /api/observability-   /api/observability-  /api/observability-
     system-summary      stream-rates         launchagents
              \              |                /
               \             v               /
                +-> services/dashboard/app.py +
                |       (Flask, auth-gated)   |
                |                             |
                v                             v
       lib/observability/aggregator.py        lib/security/pii_redactor.py
       (pure logic; mocked in tests)          (idempotent paste-safe scrub)
                |
                +---- subprocess: launchctl list (5s timeout)
                +---- fs: data/<source>/*.jsonl (newest 8 files / 2 MB tail)
                +---- fs: data/events/bus.jsonl (256 KB tail)
                +---- fs: ~/.sapphire/routine_pause/*
                +---- fs: ~/.cache/sapphire/inference_proxy/*.json
                +---- in-process: scripts/ops/provenance_verify.build_report()
```

`lib/observability/aggregator.py` is pure: every external dependency
(subprocess, filesystem root, clock) is overridable, which is what
lets the unit suite mock the entire surface without touching real
`launchctl` or the operator's home directory.

## Operating procedures

### Read the page

1. From your Mac:
   `open http://localhost:8080/observability`
   Auth: `AUTH_USERNAME` / `AUTH_PASSWORD` from `~/.sapphire/secrets.env`.
2. From a remote machine on the Tailnet:
   `curl -u sapphire:<password> http://100.x.x.w:8080/api/observability-system-summary | jq .`

### Read just the LaunchAgent table (no proxy / no streams):

```bash
curl -s -u sapphire:$AUTH_PASSWORD \
    http://localhost:8080/api/observability-launchagents | jq .
```

### Read just the per-stream rate counters:

```bash
curl -s -u sapphire:$AUTH_PASSWORD \
    http://localhost:8080/api/observability-stream-rates | jq .totals
```

### Reset / debug a stale section

Each section degrades independently. If the heartbeat section reports
`status: unknown`, check:

- Is `launchctl list` itself responsive? `time launchctl list >/dev/null`
- Was the dashboard process started outside the user's GUI session? On
  a system service, `launchctl list` returns a different bootstrap
  context than the operator's session. Restart the dashboard via the
  operator GUI shell to confirm.

If the inference-proxy section reports `available: false`, it means
`~/.cache/sapphire/inference_proxy/` does not exist. The proxy itself
is healthy — it just hasn't written the optional health-cache files
yet. The dashboard will switch to mock-tier display until the proxy
writes the next snapshot. To opt in to live tier health, run:

```bash
mkdir -p ~/.cache/sapphire/inference_proxy
# and have the proxy daemon emit tier_health.json + token_consumption.json
```

If the signal-streams section shows zero rates everywhere, confirm the
expected directories exist:

```bash
ls data/signals/ data/telegram_intel/ data/hyperliquid/ \
   data/threat_intel/ data/convergence_watchlist/
```

Missing directories report `note: directory_absent` per source — that's
fine and expected for sources that haven't been wired in yet (e.g.
`data/hyperliquid/` ships dormant in the repo).

### Diagnose a failing endpoint

The three endpoints all wrap the aggregator call in a fail-soft `try`
so a single broken probe never returns 5xx. If the JSON contains
`status: unknown` and an `error` field with a Python exception name,
that's the aggregator catching a bug — file an issue with the JSON
attached. Live network calls in tests are forbidden, so reproducing
the failure in `tests/unit/test_observability_aggregator.py` is the
fastest path to a fix.

### Apply PII redaction in custom callers

If you build a custom consumer that re-uses
`lib.observability.build_system_snapshot()`, always pipe the result
through `lib.security.pii_redactor.redact_record(...)` before logging
or sending it off-host. The aggregator already abbreviates absolute
paths and avoids secrets at rest, but `redact_record` is idempotent
and provides a second layer of paste-safety.

## Caps and constraints

| Surface | Cap |
|---------|-----|
| `launchctl list` timeout | 5 seconds |
| Bus tail | 256 KB / 200 events |
| Per-source rate file count | newest 8 files |
| Per-rate-file read size | 2 MB tail |
| Refresh cadence | 15 seconds (browser side) |
| Network calls in production | 0 (no Prometheus, no Grafana, no remote APIs) |
| Network calls in tests | 0 (every probe mocked) |

These caps are enforced inside `lib/observability/aggregator.py`. The
goal is "the aggregator must never block the dashboard": even if the
event bus log grows to multi-megabyte, the heartbeat section is
expected to render in under 100 ms and never starve the polling loop.

## Verification

```bash
ruff check .
/usr/local/bin/python3 -m pytest tests/unit/test_observability_aggregator.py -q
/usr/local/bin/python3 -m pytest tests/unit/test_dashboard_observability_routes.py -q
/usr/local/bin/python3 -m pytest tests/unit/ -q
/usr/local/bin/python3 -m pytest plugins/claw-sapphire/tests/ -q
/usr/local/bin/python3 scripts/validate_tool_registry.py
/usr/local/bin/python3 scripts/ops/production_readiness_sweep.py --no-external | tail -5
```

The two new test files live at:

- `tests/unit/test_observability_aggregator.py` (≥ 25 cases) — every
  subprocess and filesystem probe is mocked; no real `launchctl`, no
  real network.
- `tests/unit/test_dashboard_observability_routes.py` (≥ 10 cases for
  the new endpoints, on top of the existing pause-status cases).

## Acquirer relevance

This page is one of two URLs an acquirer's lead engineer is expected to
open before reading any code (the other is `/diligence`). The acquirer
question it answers is "is this thing actually running?" — and the
answer is read in seconds, with no operator-supplied narrative.

Pair this runbook with `docs/security/kill-switch-invariants.md`
(Lane 5, sibling tranche): observability shows you the live state,
kill-switch invariants describe the guardrails. Together they tell a
buyer that Sapphire is both visible and safe.
