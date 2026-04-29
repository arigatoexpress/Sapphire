# Time-Travel + Replay Runbook

As of 2026-04-29, the time-travel + replay capability is a read-only
research tool layered over Sapphire's append-only JSONL artifacts. It
does not place trades, does not publish events, does not send Telegram
messages, and does not require live network access. This runbook is
the operator handbook for running, debugging, and extending it.

## Components

- `lib/timetravel/snapshot.py`: interval index + `take_snapshot(at)`.
- `lib/timetravel/replay.py`: re-invokes `lib.correlator.engine` and
  `lib.synthesis.narrative_engine` against snapshot data.
- `lib/timetravel/diff.py`: pure function comparing actual vs replay
  on `(symbol, timeframe)` rows.
- `services/timetravel/build_index.py`: scans the configured roots
  and writes the index cache to disk.
- `plugins/claw-sapphire/tools/internal/timetravel.py` (real impl) +
  `plugins/claw-sapphire/tools/timetravel.py` (compat shim).

## Where the artifacts live

```
~/.cache/sapphire/timetravel/
└── index.json                     # interval index (idempotent rebuilds)
```

```
data/
├── correlated_signals/<date>/signals.jsonl
├── narratives/<date>/theses.jsonl
├── cross_asset/<date>/{regimes,breakdowns}.jsonl
├── macro/<date>/{events,calendar}.jsonl
├── onchain/<date>/*.jsonl
└── events/bus.jsonl
```

The index file is the single piece of state time-travel writes. Delete
it whenever you want a clean rebuild; the next `take_snapshot` call
recreates it lazily.

## Routine operations

### Build the index manually

```bash
python3 services/timetravel/build_index.py
```

The script scans every configured root, builds an interval index, and
writes it to `~/.cache/sapphire/timetravel/index.json`. The build is
idempotent: a second invocation produces an unchanged file (we hash
the body before persisting).

To force a rescan even when the cache already exists:

```bash
python3 services/timetravel/build_index.py --rebuild
```

### Inspect the index without rebuilding

```bash
python3 services/timetravel/build_index.py --status --json
```

```json
{
  "exists": true,
  "path": "/Users/sapphire/.cache/sapphire/timetravel/index.json",
  "scopes": ["correlated_signals", "cross_asset", "events_bus", "macro", "narratives", "onchain"],
  "files": 142,
  "rows": 29873,
  "signature": "3f8a01b27c4d9ec1",
  "built_at": "2026-04-29T10:00:13+00:00"
}
```

### Take a snapshot at a specific time

```bash
echo '{"action":"snapshot","at":"2026-04-26T10:00:00+00:00"}' \
  | python3 plugins/claw-sapphire/tools/timetravel.py
```

The default scope set is all six. Restrict to one or more scopes via
`"scope": ["correlated_signals"]` or a comma-separated string.

For very wide snapshots, the plugin tool truncates each scope's `rows`
to 500 by default. Override with `"max_rows_per_scope": <N>` (or `0`
to disable, though that may produce a payload too large for some
agent runtimes).

### Replay current code against a frozen snapshot

```bash
echo '{"action":"replay","at":"2026-04-26T10:00:00+00:00"}' \
  | python3 plugins/claw-sapphire/tools/timetravel.py
```

This calls `correlate_once` for every `(symbol, timeframe)` pair in
the snapshot's `correlated_signals` scope, then synthesises a dry-run
narrative thesis per replayed signal. The result has the same shape
as the on-disk artifacts.

### Diff actual vs replay

```bash
echo '{"action":"diff","at":"2026-04-26T10:00:00+00:00"}' \
  | python3 plugins/claw-sapphire/tools/timetravel.py | jq '.summary'
```

The summary collapses to seven integers:

```
total           — pairs compared
unchanged       — actual + replay match within NUMERIC_EPSILON
drifted         — at least one tracked field differs
actual_only     — pair was in actual, missing from replay
replay_only     — pair was in replay, missing from actual
missing         — neither side has the pair (defensive default)
high_drift      — drifted AND |edge_actual - edge_replay| > 0.05
```

`high_drift > 0` is the only tier that warrants operator attention by
default. Everything else is research telemetry.

## Validation gates

Before merging changes that touch any module in `lib/timetravel/`,
`services/timetravel/`, or the plugin tool:

```bash
# 1. Module-level unit tests.
python3 -m pytest tests/unit/test_timetravel_snapshot.py \
  tests/unit/test_timetravel_replay.py \
  tests/unit/test_timetravel_diff.py -q

# 2. Plugin tool tests.
python3 -m pytest plugins/claw-sapphire/tests/test_timetravel.py -q

# 3. Full lint.
ruff check lib/timetravel/ services/timetravel/ \
  plugins/claw-sapphire/tools/internal/timetravel.py \
  plugins/claw-sapphire/tools/timetravel.py

# 4. Tool-registry validator.
python3 scripts/validate_tool_registry.py

# 5. Cross-module smoke test.
echo '{"action":"index-status"}' | python3 plugins/claw-sapphire/tools/timetravel.py
```

If any check fails, do **not** merge. Fix the failure first; the
trading critical path's audit posture depends on the index being
correct and idempotent.

## Common questions / failure modes

### "I built the index but `take_snapshot` returns empty entries."

Check the index status. If `files == 0`, the scope roots are empty
(your data dirs don't have any JSONL yet). If `files > 0` but row
counts are zero, the producer's row schema doesn't match any of the
keys recognized by `_TIMESTAMP_KEYS` in
`lib/timetravel/snapshot.py`. Add the missing key or fix the producer.

### "Replay returns fewer pairs than the snapshot."

Replay only acts on the `correlated_signals` scope. Pairs without a
`symbol` or `timeframe` field are filtered out, which is correct.
If you see this for rows that *do* have both fields, check that the
correlator engine's import path resolves cleanly inside the replay
process (the engine never raises in normal use, but a `ModuleNotFoundError`
during reconstruction would manifest as missing pairs).

### "Diff shows `actual_only` for everything."

The replay produced zero rows. Most often this means:

- The snapshot's `correlated_signals` scope is empty (date too far
  in the past, before any artifacts existed).
- The replay engine raised; check `services/timetravel` logs.

A clean reproduction is to call `replay` directly via the plugin tool
and inspect the response.

### "My drift summary shows `high_drift > 0` after a routine engine
bump."

Expected. Pull the per-pair record (`diff.pairs[]`) and look at
`actual_edge`, `replay_edge`, and the corroborated/divergent set
deltas. If the bump is intentional (a scoring weight tuning, a new
source, a freshness change), record the expected drift in the engine
bump's PR description so future audits don't re-flag it.

If the bump was *not* intentional, treat it as a regression: bisect
the change set, identify the engine commit that introduced the drift,
and confirm with the engine maintainers before publishing the bump.

### "Build_index hangs."

Check the largest file under any scope. The script enforces
`MAX_BYTES_PER_FILE = 64 MiB` at the snapshot module level and skips
oversized files with a warning. If a file slips past that gate (a
production log that's been growing for weeks without rotation), the
right move is to rotate the file in the producer, not bump the cap.

### "I need to track drift on a non-signal scope."

The diff is signal-shaped today. Per-scope drift hooks for
`cross_asset`, `macro`, and `onchain` are explicitly out of scope for
0.1.0 — those scopes don't share the `(symbol, timeframe)` key shape
and would need their own diff vocabulary. Open an issue describing
the dimensions you'd want to diff (per-asset volatility regime, per-
event sentiment classification, per-address whale movement, etc.) and
we'll scope a follow-up release.

## Provenance discipline

Every emitted snapshot, replay result, and diff has a
`provenance_envelope` field. Verify it on any output you intend to
preserve outside the agent runtime:

- `generator`: the module that produced the payload.
- `version`: 0.1.0 for this release.
- `index_signature`: the index's stable SHA-256[:16] fingerprint at
  the time of the snapshot.
- `source_files_sha256`: per-file fingerprints of every JSONL file
  visited during the snapshot (only on snapshot envelopes).
- `warning`: explicit string flagging the output as research-only.

If any envelope's `index_signature` doesn't match the current
`index_status().signature`, the index has been rebuilt since the
snapshot was taken — replays from that snapshot are still valid (the
data is the same; only the cache fingerprints changed) but you may
want to re-take the snapshot to refresh the chain of custody.

## Capacity and performance

- **Index size**: roughly 200–500 bytes per indexed file. A repo with
  10,000 JSONL files yields a ~5 MB index. Loading is sub-second.
- **Snapshot time**: dominated by file I/O. Per-file scan is one
  pass; `take_snapshot` opens only the files whose `first_ts <= at`.
  A typical "snapshot at T over the past week" reads tens of
  megabytes in well under a second on local disk.
- **Replay time**: dominated by `correlate_once` calls. Per-pair cost
  is microseconds; per-narrative cost is sub-millisecond in dry-run.
  A snapshot with 50 pairs replays in under 100 ms.
- **Diff time**: pure in-memory compare. Bounded by the snapshot row
  count.

If you find any of these climbing into seconds, profile first; the
shapes above are what we tested at 0.1.0 release time.

## Trading-critical-path posture

Time-travel is **strictly read-only**:

- It does not write to `data/`. The only persistent on-disk state is
  the index cache at `~/.cache/sapphire/timetravel/index.json`.
- It does not publish to the event bus. The Sapphire event bus is
  reserved for live signal flow.
- It does not place trades. The replay's correlate_once + synthesize_thesis
  invocations operate on in-memory dicts and return frozen dataclasses;
  none of the trading or order management code paths are touched.
- It does not call OpenBB, Robinhood, Hyperliquid, or any live
  network endpoint. Replay is a pure function of (snapshot, current
  code).

This posture is not negotiable. If a future feature requires time-travel
to mutate `data/` or publish events, route it through a new module
behind an explicit env gate (`SAPPHIRE_TIMETRAVEL_PERSIST=1`) and
have it reviewed by the trading critical-path owners.

## Extending: adding a new scope

1. Define the on-disk root and producer (e.g., `data/<new>/<date>/X.jsonl`).
2. Add the new scope to `SCOPE_TO_ROOT` in `lib/timetravel/snapshot.py`.
3. If the glob is non-default, add it to `SCOPE_GLOBS`.
4. Confirm that the producer writes a recognized timestamp field on
   every row. If it doesn't, fix the producer first (this is cheaper
   than adding scope-specific timestamp shims to time-travel).
5. Update `docs/products/timetravel-and-replay-0.1.0.md` and this
   runbook in lockstep.
6. Run the validation gates above. If any of the unit tests need new
   scope-specific cases, add them under `tests/unit/test_timetravel_snapshot.py`.

If the new scope warrants drift tracking in the diff, add a
per-scope hook to `lib/timetravel/diff.py` and bump the version to
0.2.0 with a documented migration note.

## Schema versioning

The index has `schema_version = 1`. To bump the schema:

1. Bump the constant in `lib/timetravel/snapshot.py`.
2. Add a migration branch in `load_index` that detects an old version
   and rebuilds (or in-place migrates) the cache file.
3. Update both docs in lockstep.
4. Add a unit test under `tests/unit/test_timetravel_snapshot.py`
   that asserts the migration path produces a valid current-version
   index from an old fixture.

The bump is a coordinated change. Don't ship a snapshot module on
schema 2 without the matching migration code or tests.

## Related runbooks

- `docs/ops/cross-asset-runbook.md` — the producer for the
  `cross_asset` scope.
- `docs/ops/counterparty-intel-runbook.md` — read-only intel surface
  with similar provenance discipline.
- `docs/ops/audit-panel-runbook.md` — system-wide audit posture; the
  time-travel index is one of the artifacts the audit panel can rely
  on for "show me the chain of custody at T".

## Operator escalation

If the diff surfaces a `high_drift` count above 5 across a single
snapshot, that is a signal an engine bump may have shifted behaviour
in a way that wasn't expected. Page the engine owners (correlator or
synthesis) before the next live trading-critical change. Time-travel
itself does not place trades, but it is the audit surface most likely
to catch a behaviour regression before it reaches production.
