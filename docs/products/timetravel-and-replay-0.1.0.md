# Time-Travel + Replay Capability 0.1.0

As of 2026-04-29, Sapphire's intelligence stack writes append-only JSONL
artifacts on every meaningful decision: correlated signals, narrative
theses, cross-asset regimes, macro events, on-chain summaries, and
event-bus envelopes. The data is there; what was missing was a clean
read path that asks two related research questions:

1. **What did Sapphire think at time T?** Loading a coherent slice of
   the system across all six artifact streams, scoped to "rows visible
   at T", without writing the JSONL globs into every dashboard.
2. **What would current code produce at T?** Re-invoking today's
   correlator and narrative engines against that frozen view, so the
   operator can quantify drift between published behaviour and current
   behaviour, even after engine version bumps.

This product surface ships both questions as deliberately small,
read-only modules. It is the foundation for backtesting drift, audit
panels, and any "show me yesterday" research workflow without polluting
live data.

## Surface

The 0.1.0 release ships four connected surfaces:

- A pure analytics package at `lib/timetravel/` (snapshot, replay,
  diff). No live network calls, no subprocesses, no writes to `data/`.
- An index-build script at `services/timetravel/build_index.py`. Scans
  the configured JSONL roots and writes an interval index cached at
  `~/.cache/sapphire/timetravel/index.json`.
- A plugin tool pair at `plugins/claw-sapphire/tools/internal/timetravel.py`
  and `plugins/claw-sapphire/tools/timetravel.py`. Stdin-JSON actions:
  `snapshot`, `replay`, `diff`, `index-status`.
- Provenance envelopes attached to every emitted snapshot, replay
  result, and diff. Each envelope carries the index signature, source
  file SHA-256s, and a `warning` field that explicitly flags the
  output as research-only.

Time-travel never writes to `data/`. It never publishes to the event
bus. It never sends Telegram messages and never places trades. The
trading critical path is treated as sacred: replays are held strictly
in memory and the diff is a pure function over (snapshot, replay).

## Scopes

Six scopes correspond to the six append-only artifact streams Sapphire
already maintains:

| Scope | On-disk root | Producer |
|-------|--------------|----------|
| `correlated_signals` | `data/correlated_signals/<date>/signals.jsonl` | `services/correlator/run.py` |
| `narratives` | `data/narratives/<date>/theses.jsonl` | `services/synthesis/run.py` |
| `cross_asset` | `data/cross_asset/<date>/{regimes,breakdowns}.jsonl` | `services/cross_asset/run.py` |
| `macro` | `data/macro/<date>/{events,calendar}.jsonl` | `services/macro_intel/run.py` |
| `onchain` | `data/onchain/<date>/*.jsonl` | `services/onchain_intel/run.py` |
| `events_bus` | `data/events/bus.jsonl` | `lib/core/event_bus.py` (fallback) |

Scopes can be requested individually (`scope=["correlated_signals"]`)
or as the default sextuple. Unknown scopes raise a clean error from the
plugin tool surface.

## Interval index design

The index is the bookkeeping layer that lets us answer "give me everything
visible at T" without reading every JSONL file in the repo. It is a
JSON map keyed by scope, listing the per-file metadata we need to skip
or open a file:

```json
{
  "schema_version": 1,
  "generator": "lib.timetravel.snapshot",
  "version": "0.1.0",
  "built_at": "2026-04-29T12:00:00+00:00",
  "scopes": {
    "correlated_signals": [
      {
        "path": "/.../data/correlated_signals/2026-04-26/signals.jsonl",
        "first_ts": "2026-04-26T00:01:12+00:00",
        "last_ts": "2026-04-26T23:59:48+00:00",
        "rows": 1083,
        "sha256": "...",
        "mtime": 1714177200.0,
        "size_bytes": 412933
      }
    ]
  },
  "totals": {"files": N, "rows": M, "scopes": 6},
  "signature": "<sha256[:16]>"
}
```

The `first_ts` / `last_ts` window lets `take_snapshot(at=...)` skip any
file whose `first_ts > at`. Files whose window contains `at` get
streamed once with a per-row timestamp filter. This approach is
deliberately simple — no B-trees, no Sapphire-specific column store —
because the volume is on the order of "thousands of files, millions of
rows" and the constant factors here matter less than testability.

The index is **idempotent**: running `build_index` twice writes the
same content. We compute a stable `signature` (SHA-256 of the sorted
scope payload), and we only persist if the signature changes. The
mtime of the cache file is preserved across no-op rebuilds, which
matters for downstream caches and hermetic tests.

Out-of-range requests do not raise. A request for a timestamp before
the earliest indexed row returns an empty snapshot for the affected
scope (callers detect this via `SnapshotEntry.empty`). A request for a
timestamp far in the future returns everything visible up to "now",
which is also the natural definition.

## UTC discipline

Every datetime crossing a public boundary is timezone-aware UTC. Naive
datetimes supplied by callers are coerced (a small ergonomic kindness
for tests and ad-hoc operator runs). On-disk timestamps are ISO-8601
with explicit `+00:00`. The plugin tool accepts both `Z`-suffixed and
offset-suffixed strings.

The reasoning is twofold. First: the entire Sapphire intelligence stack
agreed on UTC at the producer side already, so doing UTC at the consumer
is the cheap consistent choice. Second: any local-time conversion is a
**presentation** concern (dashboards, Telegram), not a snapshot concern.
Time-travel is the storage layer of the audit trail; presentation is
elsewhere.

## Replay semantics

`replay(snapshot)` calls `lib.correlator.engine.correlate_once` for
every `(symbol, timeframe)` pair seen in the snapshot's
`correlated_signals` scope, then calls
`lib.synthesis.narrative_engine.synthesize_thesis` (dry-run mode) on
each replayed correlated signal. The result is a `ReplayResult` with
the same shape as the on-disk artifacts so callers can hand both the
snapshot and the replay to `diff_actual_vs_replay`.

Per-source signals are reconstructed from the latest pre-`at`
correlated row's `bull_sources` / `bear_sources` / `neutral_sources`
buckets. Direction is derived from the bucket the source appears in;
confidence is the absolute edge score; age is `at - row.generated_at`
(clamped to zero). This is a deliberately thin reconstruction —
fidelity to the original input depends on what the row preserves, but
in practice the correlator is monotone enough that replay produces a
near-identical correlated signal when the engine hasn't drifted.

We do **not** re-run the upstream macro / cross-asset / on-chain
pipelines. Their summaries are already on disk, and re-pulling live
data would defeat the purpose of asking "what would current code
produce at T". Replay exercises the **fusion** layer.

A replay never writes to disk. It never publishes to the event bus. It
never places trades. The provenance envelope flags the output with an
explicit `"warning"` field that says so.

## Diff semantics

`diff_actual_vs_replay(snapshot, replay)` is a pure function. It
indexes both inputs by `(symbol, timeframe)`, then for each pair
emits a `SignalDiff` with one of four statuses:

- `unchanged`: every compared field matches within `NUMERIC_EPSILON`
  (1e-6) for floats, and exactly for sets / strings.
- `drifted`: at least one of `edge_score`, `consensus`,
  `contributing`, `corroborated_by` set, `divergent_sources` set,
  narrative `implied_position`, or narrative `confidence` differs.
  When `|edge_actual - edge_replay| > HIGH_DRIFT_THRESHOLD` (0.05) we
  also flag `high_drift=True` so dashboards can sort.
- `actual_only`: pair present in the snapshot but not in the replay.
  Usually means the row was emitted by an older engine on a code path
  the current engine no longer covers.
- `replay_only`: pair present in the replay but not in the snapshot.
  Usually means current code emits a pair the older engine skipped
  (e.g., a new timeframe added to the universe).

Free-text fields (`thesis_one_paragraph`, `evidence_bullets`,
`counter_thesis_one_paragraph`) are intentionally not diffed. The
synthesizer is deterministic in dry-run, so they should match exactly
when reasonable upstream data is present, but they are verbose and
unhelpful to highlight. Operators who want a literal-text diff can
read the snapshot rows + replay rows directly and feed them through
the standard text differ of their choice.

The diff is bounded in size: a snapshot containing N pairs produces
exactly N `SignalDiff` records, and the summary collapses them to
seven integers. The plugin tool returns the full diff plus the summary
on every call, so the agent surface can decide whether to escalate
without re-running.

## Worked example: "What did Sapphire think 3 days ago about BTC?"

Suppose it is 2026-04-29 10:00 UTC and an operator wants to compare
the BTC narrative Sapphire actually produced 72 hours ago (2026-04-26
10:00 UTC) with what the current code would produce given the same
view of disk. The full session looks like:

```bash
# 1. Index the artifact streams (idempotent — first call builds, second is no-op).
python3 services/timetravel/build_index.py
# time-travel index built.
#   cache path:  /Users/sapphire/.cache/sapphire/timetravel/index.json
#   signature:   3f8a01b27c4d9ec1
#   built at:    2026-04-29T10:00:13+00:00
#   scope count: 6
#   file count:  142
#   row count:   29873

# 2. Take a snapshot at 2026-04-26 10:00 UTC.
echo '{"action":"snapshot","at":"2026-04-26T10:00:00+00:00","scope":["correlated_signals","narratives"]}' \
  | python3 plugins/claw-sapphire/tools/timetravel.py
# {"ok":true,"action":"snapshot","at":"2026-04-26T10:00:00+00:00",
#  "snapshot":{"entries":{"correlated_signals":{"row_count":17,...},
#                          "narratives":{"row_count":3,...}}, ...}}

# 3. Replay the same timestamp.
echo '{"action":"replay","at":"2026-04-26T10:00:00+00:00"}' \
  | python3 plugins/claw-sapphire/tools/timetravel.py | jq '.result.correlated_signals[] | select(.symbol == "BTC")'
# {
#   "symbol": "BTC",
#   "timeframe": "1h",
#   "edge_score": 0.412,
#   "consensus": "AGREE_BULL",
#   ...
# }

# 4. Diff actual vs replay.
echo '{"action":"diff","at":"2026-04-26T10:00:00+00:00"}' \
  | python3 plugins/claw-sapphire/tools/timetravel.py | jq '.summary'
# {
#   "total": 5,
#   "unchanged": 4,
#   "drifted": 1,
#   "actual_only": 0,
#   "replay_only": 0,
#   "missing": 0,
#   "high_drift": 0
# }
```

The single drifted pair is BTC/1h. Looking at the per-pair record:

```json
{
  "symbol": "BTC",
  "timeframe": "1h",
  "status": "drifted",
  "actual_edge": 0.395,
  "replay_edge": 0.412,
  "actual_consensus": "AGREE_BULL",
  "replay_consensus": "AGREE_BULL",
  "actual_contributing": 3,
  "replay_contributing": 3,
  "corroborated_set_delta": [],
  "divergent_set_delta": [],
  "narrative_position_actual": "long_mild",
  "narrative_position_replay": "long_mild",
  "narrative_confidence_delta": 0.02,
  "high_drift": false
}
```

Reading this: the consensus, contributing source count, and source set
all match. Edge score moved 0.017 (well under the high-drift bar).
Narrative position is unchanged. Confidence ticked up 0.02. This is
the pattern we expect from a healthy engine: the correlator's scoring
weights have been tuned slightly since 2026-04-26, the narrative
engine's confidence calculation tracks edge magnitude, and the directional
read is unchanged. No operator action required.

A high-drift result, by contrast, would surface immediately in the
summary: `high_drift > 0`. That's the trigger to read the per-pair
record and diagnose whether the engine bump was intentional, or
whether something regressed.

## Caveats

The replay's reconstruction of per-source signals is intentionally
lossy. The original signal source's `confidence` and `age_seconds`
fields are not stored in the correlated row, so we approximate them
from the row's `edge_score` and the elapsed time since the row's
`generated_at`. In practice this matches the original within
floating-point noise when the engine's behaviour is unchanged; if the
scoring weights have moved, the replayed `edge_score` will move with
them, and the diff will reflect that.

Replays of correlated rows that contain *no* sources (`contributing=0`)
get a degenerate `INSUFFICIENT_DATA` consensus, which is the same
result the live correlator would produce. We do not skip them; the
diff records "unchanged" for these pairs, which is correct.

The events_bus scope reads only `data/events/bus.jsonl`. If your
deployment uses Redis Streams as the primary event transport (the
default) and the JSONL fallback never fired, this scope will be empty
and the snapshot will reflect that. The intent is "audit the
JSONL trail when Redis was down or when a tool wants a strict
file-backed view"; live event introspection lives elsewhere.

## Versioning

The index schema version is `1`. The plugin tool, snapshot module,
replay module, and diff module all share `VERSION = "0.1.0"`. Bumping
the index schema is a coordinated change: read both `lib/timetravel/`
and `services/timetravel/build_index.py`, bump the schema version, add
a migration in `load_index`, and update the docs/runbook in lockstep.

## What's not in 0.1.0

- A dashboard surface. The plugin tool is the only UI in 0.1.0.
- A scheduled task that rebuilds the index. The script is run-once;
  the index also rebuilds lazily on the first `take_snapshot` call.
- A pruning policy. The index never grows unbounded because file
  fingerprints are SHA-256s and the per-scope cap is `MAX_INDEX_FILES_PER_SCOPE`,
  but a "drop files older than N days" policy is a future tightening.
- A real-time replay. Streaming would require a different design.

## How to add a new scope

1. Create the new on-disk root (e.g., `data/<new_scope>/<date>/...`).
2. Add the entry to `SCOPE_TO_ROOT` in `lib/timetravel/snapshot.py`.
3. If the producer's filename glob differs from `**/*.jsonl`, add it
   to `SCOPE_GLOBS`.
4. Make sure the producer writes a row-level timestamp under one of
   the keys recognized by `_TIMESTAMP_KEYS` (`generated_at`,
   `timestamp`, `timestamp_iso`, `ts`, `time`, `observed_at`,
   `wrote_at`) or under `payload.{ts,...}` for event-bus-style rows.
5. Append the scope to the docs/runbook table and rebuild the index.

The `take_snapshot` and `replay` flows pick up the new scope
automatically; the `diff` flow is signal-shaped today and would need
its own per-scope diff hooks if the new scope deserves drift tracking.

## Trading-critical-path posture

Time-travel is **strictly read-only over `data/`**. It does not write
to `data/`, does not publish to the event bus, does not send Telegram
messages, does not call OpenBB or any live data provider, and does not
place orders. The replay holds intermediate state in memory only and
does not persist anything beyond the index cache file.

This stance is not negotiable. The trading critical path was hardened
in PRs #340 / #344 (2026-04-28), and any future tightening of the
trading kill switch should not have to think about time-travel as a
side path. If a future feature requires time-travel to write
artifacts, the right place is a separate `data/timetravel_replays/`
root, gated by an explicit `SAPPHIRE_TIMETRAVEL_PERSIST=1` env flag,
behind a separate code review.
