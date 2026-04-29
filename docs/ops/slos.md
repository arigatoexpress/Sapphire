# Sapphire Service-Level Objectives (SLOs)

This document defines the SLOs for every Sapphire operational surface.
SLOs are written in the **format** Google's SRE book uses
(availability + latency + error rate + freshness, where applicable),
but Sapphire is a single-operator system and the targets are calibrated
accordingly: not five-nines, not pager-driven, but honest.

**Where the SLO exceeds current measurement, the cell is marked
`aspirational` explicitly.** Aspirational SLOs document what we want
to commit to once the measurement infrastructure exists; they are
not load-bearing today. The Tranche 6 Lane 6 inference-mesh telemetry
work, when it lands, will collapse a number of `aspirational` markers
to `measured`.

**Definitions**:

- **Availability**: percentage of time the surface returns a non-error
  response within the latency target. Measured over a 30-day rolling
  window unless otherwise noted.
- **Latency p99**: 99th-percentile wall-clock latency for one
  successful request / one successful tick of a daemon's main loop.
- **Error rate**: percentage of requests / ticks that return a 5xx,
  raise an unhandled exception, or fail their post-condition.
- **Freshness**: maximum age of the most recently emitted artifact /
  data row. Applicable to daemons / scheduled jobs only.

**Status**:

- `measured` — SLO is monitored automatically; alerts fire on breach.
- `manual` — SLO is checked by the operator on a cadence (daily,
  weekly).
- `aspirational` — SLO is the target; no monitoring exists yet.

---

## Trading-critical-path services

These have the **strictest** SLOs because PnL depends on them. CODEOWNERS
gate (ADR 0003) covers code changes; SLO breach triggers operator
review immediately.

| Service | Availability | Latency p99 | Error rate | Freshness | Status |
|---|---|---|---|---|---|
| `services/alpha/` (signal logger :18081) | 99.9% | 250 ms | < 0.1% | < 60 s for new TradingView signals | manual |
| `services/webhook/` (TradingView receiver, Win :9090) | 99.5% | 500 ms | < 0.5% | n/a (synchronous) | manual |
| `services/hyperliquid/` (live executor) | 99.0% (when `HYPERLIQUID_TRADING_ENABLED=1`) | 2000 ms | < 1% | < 5 s for queue processing | manual |
| `lib/portfolio/robinhood.py` (REST client) | 99.0% | 1500 ms | < 1% | n/a (on-demand) | manual |
| `services/heartbeat/` (60s state machine) | 99.95% | 100 ms | < 0.1% | < 60 s heartbeat tick | aspirational |

**Notes**:

- The signal-logger 99.9% is conservative; observed uptime over the
  last 30 days appears closer to 99.7% based on operator telegram
  alerts (no formal measurement). The Lane 6 inference-mesh telemetry
  work is the path to making this `measured`.
- Hyperliquid's 99.0% is gated by `HYPERLIQUID_TRADING_ENABLED=1`;
  the default-off posture means this SLO is effectively dormant most
  of the time.
- Robinhood client SLO is per-call, not per-day; bursts are bounded
  by upstream rate limits.

## Intelligence services

| Service | Availability | Latency p99 | Error rate | Freshness | Status |
|---|---|---|---|---|---|
| `services/correlator/` | 99% | 5 s | < 2% | < 15 min for new correlated views | manual |
| `services/synthesis/` (narrative engine) | 99% | 30 s (mock) / 60 s (live) | < 2% | < 30 min for new narratives | manual |
| `services/cross_asset/` | 99% | 10 s | < 2% | < 60 min | manual |
| `services/event_impact/` | 99% | 10 s | < 2% | < 60 min | manual |
| `services/macro_intel/` | 99% | 10 s | < 2% | < 60 min | manual |
| `services/onchain_intel/` | 99% | 30 s | < 2% | < 60 min for chain refresh | manual |
| `services/counterparty/` | 95% | 10 s | < 5% | < 4 h | manual |
| `services/narrative_evaluation/` | 95% | 10 s | < 5% | < 24 h | manual |
| `services/intelligence/` (daily brief) | 99% per day | 5 min total run | < 1% | < 24 h | manual |
| `services/audit_panel/` | 95% | 5 s | < 5% | < 24 h | manual |
| `services/telegram_intel/` (channel reader) | 95% | 30 s | < 5% | < 5 min for new messages | aspirational |
| `services/research_notes/` | 90% | 10 s | < 10% | < 7 d | manual |

**Notes**:

- Correlator and synthesis SLOs are tied: synthesis cannot exceed
  correlator's freshness because synthesis consumes correlator output.
- Counterparty intel and narrative-evaluation are scored at 95% rather
  than 99% because their upstream sources (Twitter, RSS, public
  filings) have observable variability that we don't fully control.
- Research notes 90% / < 7d freshness reflects a deliberate "weekly
  cadence" posture; not a quality issue.

## Platform / control surfaces

| Service | Availability | Latency p99 | Error rate | Freshness | Status |
|---|---|---|---|---|---|
| `services/control-plane/` | 99% | 200 ms | < 1% | n/a (synchronous) | manual |
| `services/dashboard/` | 99% | 500 ms | < 1% | < 60 s for SSE event stream | manual |
| `services/inference-proxy/` (4-tier failover) | 99.5% | 30 s p99 (T3 mac local) / 1 s p99 (T1 GPU) | < 0.5% | n/a | aspirational |
| `services/openbb_api/` (REST :6900) | 99% | 1000 ms | < 1% | < 60 s for quote refresh | manual |
| `services/pipeline/` (GCS + BigQuery sync) | 99% per hour | 5 min total run | < 1% | < 60 min watermark | manual |
| `services/foundry_sync/` | 99% per cycle | 2 min total run | < 1% | < 15 min sync delta | manual |
| `services/customer_api/` | 99% (mock-default mode) / 95% (live) | 200 ms | < 1% | n/a | manual |
| `services/security_pipeline/` | 95% per cycle | 10 min total run | < 5% | < 24 h scan freshness | manual |
| `services/pm_bot/` (Telegram operator console) | 99.5% | 500 ms | < 0.5% | < 5 s for command response | manual |
| `services/morning_digest/` (LaunchAgent) | 99% per day | 2 min total run | < 1% | < 24 h | manual |
| `services/service_supervisor/` | 99.9% | 5 s tick | < 0.1% | < 30 s tick cadence | aspirational |
| `services/live_portfolio_daemon/` | 99% | 5 s tick | < 1% | < 60 s | manual |

**Notes**:

- The inference-proxy SLO is `aspirational` because per-tier latency
  is not measured today. Lane 6 of Tranche 6 (inference mesh telemetry)
  is the path to making this `measured` with real p50/p99/p999 numbers.
- Dashboard SSE freshness is bounded by event-bus latency (Redis
  primary, JSONL fallback). When Redis is down, freshness can degrade
  to ~5 s.
- Control-plane fail-closed (HTTP 503) when `CONTROL_PLANE_TOKEN`
  unset is **not** an availability breach — it's the security posture.

## LaunchAgent-only surfaces (no service module)

These are scheduled or background processes that don't have their own
`services/<name>/` directory. SLOs are measured per-tick or per-cycle.

| LaunchAgent | Cadence | Latency p99 (per cycle) | Error rate | Freshness | Status |
|---|---|---|---|---|---|
| `com.sapphire.backtest-weekly` | weekly | 30 min | < 5% | < 7 d since last sweep | manual |
| `com.sapphire.chain-refresh` | hourly | 5 min | < 5% | < 60 min | manual |
| `com.sapphire.content-engine` | weekly | 10 min | < 5% | < 7 d | manual |
| `com.sapphire.content-publisher` | per-publish | 60 s | < 5% | < 60 s for queue drain | manual |
| `com.sapphire.correlation-refresh` | every 15 min | 5 min | < 5% | < 15 min | manual |
| `com.sapphire.gcp-sync` | hourly | 5 min | < 1% | < 60 min watermark | manual |
| `com.sapphire.gemini-ooda-daily` | daily | 5 min | < 5% | < 24 h | manual |
| `com.sapphire.logrotate` | daily 03:30 | 60 s | < 0.1% | < 24 h | manual |
| `com.sapphire.market-intel` | every 30 min | 5 min | < 5% | < 45 min | manual |
| `com.sapphire.morning-brief` | daily 06:00 | 5 min | < 5% | < 24 h | manual |
| `com.sapphire.security-pipeline` | daily 04:00 | 10 min | < 5% | < 24 h | manual |
| `com.sapphire.self-optimization` | Sunday 23:00 | 5 min | < 10% | < 7 d | manual |
| `com.sapphire.telemetry-collector` | every 60 s | 5 s | < 5% | < 60 s | aspirational |
| `com.sapphire.threat-refresh` | twice daily | 5 min | < 5% | < 12 h | manual |
| `com.sapphire.trading-shadow-controller` | every 30 min | 30 s | < 5% | < 2 h | manual |
| `com.sapphire.tradingview-cdp` | continuous | n/a (long-running) | < 1% (when TV desktop is up) | n/a | manual |

## Cloud routines (Anthropic claude.ai/code/routines)

These run on Anthropic infrastructure on cron, regardless of operator
machine state. SLOs are per-routine, per-fire.

| Routine | Cron (UTC) | Availability | Cycle latency p99 | Error rate | Freshness | Status |
|---|---|---|---|---|---|---|
| Mission status digest | `0 14 * * 1` | 99% per fire | 10 min | < 5% | < 7 d (weekly) | manual |
| Content-engine soak collector | `0 13 * * *` | 99% per fire | 10 min | < 5% | < 24 h | manual |
| Factory test guardian | `0 4 * * *` | 99% per fire | 30 min | < 5% | < 24 h | manual |
| Factory repo fixer | `0 5 * * *` | 99% per fire | 10 min | < 5% | < 24 h | manual |
| Dependency drift digest | `0 12 * * 3` | 99% per fire | 5 min | < 5% | < 7 d | manual |
| Threat intel sweep | `0 11 * * *` | 99% per fire | 10 min | < 5% | < 24 h | manual |
| Github discovery | `0 13 * * 1` | 99% per fire | 10 min | < 5% | < 7 d | manual |
| Evening digest | `0 0 * * *` | 99% per fire | 10 min | < 5% | < 24 h | manual |

**Notes**:

- Cloud routine SLOs are tighter than LaunchAgent SLOs because
  Anthropic's infrastructure is more reliable than the operator's
  Mac. Soak-window observation since 2026-04-27 supports 99% per fire.
- Each routine produces exactly one GitHub side effect (issue or
  draft PR); freshness is measured on the side effect, not the
  internal compute.

---

## Compound SLOs

Some SLOs are compositional — the trading-pipeline SLO is bounded by
the worst link. We track these explicitly:

- **Trading pipeline end-to-end (TradingView → webhook → signal-logger
  → Telegram alert)**: 99% per signal, p99 latency 5 s. Computed as
  `min(webhook avail, signal-logger avail, alert delivery)`.
- **Intelligence end-to-end (sources → correlator → synthesis →
  dashboard)**: 99% per cycle, freshness < 30 min for the freshest
  story. Computed as `max(correlator freshness, synthesis freshness,
  dashboard SSE freshness)`.
- **Live capital ledger end-to-end (Robinhood fill → ramp gate →
  audit panel)**: 99% per fill, freshness < 5 min from fill timestamp
  to audit-panel ingestion.

These compound SLOs are all `manual` today. Tranche 6 Lane 6 is the
path to making them `measured`.

---

## Chaos-tested SLOs (Tranche 6 Lane 8 — landed)

Tranche 6 Lane 8 (chaos engineering on event bus + Redis fallback)
landed 5 canonical scenarios with deterministic invariants verified
in CI under `tests/integration/test_event_bus_chaos.py`. The
placeholders previously in this section are replaced with the
**chaos-tested SLOs** below. Status `chaos-verified` means: the
invariant is asserted by ≥ 1 test in `tests/integration/test_event_bus_chaos.py`,
the test passes today on `main`, and the chaos runbook
(`docs/ops/chaos-engineering-runbook.md`) is the audit reference.

| Scenario | Invariant | Status | Test reference |
|---|---|---|---|
| Redis dies mid-publish | Zero events lost; pre-trip in Redis, post-trip in JSONL fallback | chaos-verified | `test_redis_dies_mid_publish_zero_loss`, `test_redis_dies_mid_publish_pre_in_redis_post_in_jsonl` |
| Redis dies mid-publish | Ordering preserved across the trip boundary | chaos-verified | `test_redis_dies_mid_publish_ordering_preserved` |
| Redis dies mid-publish | No duplicates | chaos-verified | `test_redis_dies_mid_publish_no_duplicates` |
| Redis dies mid-subscribe | Subscriber sees the JSONL tail after Redis dies | chaos-verified | scenario 2 cases in `test_event_bus_chaos.py` |
| Redis recovers after N seconds | Dual-write reconciliation, zero loss | chaos-verified | `test_redis_recovers_zero_loss`, `test_redis_recovers_phases_partition_correctly` |
| Redis recovers after N seconds | Ordering preserved across the heal boundary | chaos-verified | `test_redis_recovers_ordering_preserved_across_boundary` |
| Disk-full on JSONL fallback | Loss is *quantified* (not silent), not a retry storm | chaos-verified | `test_jsonl_fallback_disk_full_quantifies_loss` |
| Dual-write mismatch | Duplicate is *flagged* (allowed), total publish count correct | chaos-verified | `test_dual_write_mismatch_flags_duplicate`, `test_dual_write_mismatch_total_published_correct` |
| All canonical scenarios | Zero-loss invariant holds across all 5 scenarios | chaos-verified | `test_zero_loss_invariant_across_all_canonical_scenarios` |

The full canonical scenario list (5) is exercised by
`test_list_scenarios_returns_five_canonical_names`; each is
parametrised by `RedisDiesMidPublishScenario`,
`RedisDiesMidSubscribeScenario`, `RedisRecoversAfterScenario`,
`DualWriteMismatchScenario`, and `JsonlDiskFullScenario`.

**Latency targets** (measured against a `FakeRedis` clock on the
chaos lab; production may differ but the qualitative bound holds):

- Redis-dies-mid-publish → JSONL fallback engages within the same
  publish call (no inter-call retry; the fallback is in the publish
  path itself, not a separate worker).
- Redis-recovers-after → dual-write reconciliation completes on the
  next event published after recovery (single-call cost; zero
  background reconciliation thread).
- Disk-full on JSONL → fail-fast, no retry storm (the test asserts a
  bounded number of write attempts before quantifying loss).

The inference-proxy `calls.jsonl` writer now exists in the production request
path. These chaos-tested SLOs can be promoted from `chaos-verified` (CI
assertion) to `measured` when the telemetry dashboard consumes enough real
call-log volume and alert thresholds are agreed.

---

## SLO measurement gaps

The honest list of what we do not measure today:

1. **Per-tier inference-proxy latency** (Lane 6 of Tranche 6 will fix).
2. **Heartbeat tick freshness** (Lane 6 telemetry could surface this).
3. **Telemetry-collector own-availability** (meta: who watches the
   watcher?).
4. **Trading-shadow-controller per-candidate decision latency**
   (artifact freshness is tracked; p99 decision latency is not instrumented).
5. **Service-supervisor restart latency** (no instrumentation).

This list is the work-stream for Tranche 7 if Tranche 6 doesn't get
to all of it.

---

## Review cadence

- **Monthly**: re-walk this document; downgrade or upgrade SLOs based
  on observed behavior.
- **Per-tranche**: when a new service ships, add its SLO row.
- **Per-incident**: any operator-noticed SLO breach (signal-logger
  outage, Robinhood client failure, dashboard 5xx) is recorded in a
  short post-mortem and the SLO is reviewed.

**Owner**: Sapphire ops (single operator currently — `@arigatoexpress`).

**Last reviewed**: 2026-04-29 (Tranche 6 Lane 2; first version).
