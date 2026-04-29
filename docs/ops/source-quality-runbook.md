# Source Quality Measurement — Operator Runbook

> **Operator-facing companion to** `docs/products/source-quality-measurement-0.1.0.md`.
> This runbook covers day-2 operations: enabling the daemon, interpreting the
> artefacts, debugging stale reports, recalibrating thresholds, and disabling
> in an incident.

---

## 1. Quick reference

| Item | Value |
|------|-------|
| Daemon entry point | `services/source_quality/run.py` |
| LaunchAgent label | `com.sapphire.source-quality` (template at `services/source_quality/launchagent/com.sapphire.source-quality.plist.template`) |
| RunAtLoad default | **`false`** (operator opt-in) |
| Schedule when enabled | daily at 06:30 local (after threat-intel-sweep) |
| Output root | `data/source_quality/<YYYY-MM-DD>/report.json` |
| Aggregates | `data/source_quality/aggregates/rolling.json` |
| Provenance sidecar | `data/source_quality/<YYYY-MM-DD>/report.json.provenance.json` |
| Live-write env gate | `SAPPHIRE_SOURCE_QUALITY_LIVE` (only honoured by the daemon, never the plugin tool) |
| Plugin tool | `plugins/claw-sapphire/tools/source_quality.py` (stdin JSON, read-only) |
| Dashboard page | `/source-quality` (basic auth) |
| API routes | `/api/source-quality-snr`, `/api/source-quality-correlation`, `/api/source-quality-decay` |

---

## 2. Bring-up: first run

The daemon does not run automatically out of the box. The recommended
bring-up flow:

1. **Inspect what's on disk.** `ls data/` should show some subset of:
   `signals/`, `correlated_signals/`, `telegram_intel/`, `hyperliquid/`,
   `cross_asset/`, `onchain/`, `macro/`. Missing directories are fine — the
   daemon walks each and skips silently.

2. **Provide an outcomes file (optional but recommended).** Drop a JSONL
   file at `data/source_quality_outcomes.jsonl` with one row per realised
   outcome:

   ```json
   {"symbol": "BTC", "timestamp": "2026-04-29T18:00:00+00:00", "realised_return": 0.0125}
   ```

   `symbol` is required; `timestamp` and `realised_return` are required;
   anything else is ignored. Without this file the daemon still emits a
   report but every source's `samples` will be 0 (we have no truth signal
   to score against).

3. **Manual dry-run.** `--no-write` builds the report in memory and prints
   the JSON to stdout:

   ```bash
   /usr/local/bin/python3 -m services.source_quality.run --no-write
   ```

   Inspect the `summary` block: `sources_count`, `samples_total`,
   `near_duplicate_pairs`, `decayed_sources_count`. If any is unexpected,
   stop here and investigate before persisting.

4. **First persistent run.**

   ```bash
   /usr/local/bin/python3 -m services.source_quality.run
   ```

   Confirm the artefacts:

   ```bash
   ls data/source_quality/$(date +%Y-%m-%d)/
   # report.json
   # report.json.provenance.json
   ```

5. **Inspect the dashboard.** With the dashboard service running:

   ```bash
   AUTH_PASSWORD=sapphire python3 services/dashboard/app.py
   open http://127.0.0.1:8080/source-quality
   ```

   You should see three panels populated. If a panel says "No SNR report
   on disk yet," step 4 didn't write the file — re-check write permissions.

6. **Enable the LaunchAgent.** Copy the template and flip `RunAtLoad`:

   ```bash
   cp services/source_quality/launchagent/com.sapphire.source-quality.plist.template \
      ~/Library/LaunchAgents/com.sapphire.source-quality.plist
   sed -i '' 's|<false/>|<true/>|' ~/Library/LaunchAgents/com.sapphire.source-quality.plist
   launchctl load -w ~/Library/LaunchAgents/com.sapphire.source-quality.plist
   ```

   Verify:

   ```bash
   launchctl list | grep com.sapphire.source-quality
   ```

---

## 3. Reading the artefacts

The daily `report.json` is the source of truth. Top-level keys:

```json
{
  "schema_version": 1,
  "generated_at": "2026-04-29T06:30:12+00:00",
  "report_date": "2026-04-29",
  "snr": { "tradingview": {...}, "telegram_intel": {...}, ... },
  "correlation": { "sources": [...], "pairs": [...], "near_duplicates": [...] },
  "near_duplicates": [...],
  "decay": { "alerts": [...], "decayed_sources": [...] },
  "summary": {
    "sources_count": 7,
    "samples_total": 412,
    "near_duplicate_pairs": 1,
    "decayed_sources_count": 1,
    "low_sample_sources_count": 2
  },
  "read_only": true
}
```

Key fields per `snr` row:

- `samples` — number of `(signal, outcome)` matches inside the lookahead
  window.
- `precision`, `recall`, `f1` — standard classification metrics.
- `low_sample` — `true` when `samples < 5`. Treat as preliminary; do not
  feed into automated decisions.
- `notes` — human-readable hints (sample-size warnings, unmatched-signal
  count, etc.).

Key fields per `correlation.pairs` row:

- `overlap` — shared cells between the two sources.
- `agreements`, `conflicts` — split of the overlap.
- `agreement_rate`, `conflict_rate` — `null` when overlap < 5.
- `near_duplicate` — `true` iff `agreement_rate >= 0.87`.

Key fields per `decay.alerts` row:

- `baseline_f1`, `recent_f1`, `delta` — baseline minus recent.
- `decay` — `true` iff `delta >= 0.15`.
- `low_sample` — too few recent matches to trust.

---

## 4. Common operator workflows

### 4.1 "Which sources are decaying?"

```bash
/usr/local/bin/python3 -c "
import json
report = json.load(open('data/source_quality/$(date +%Y-%m-%d)/report.json'))
for a in report['decay']['alerts']:
    if a['decay']:
        print(a['source'], 'delta=', a['delta'])
"
```

Or via the plugin tool:

```bash
echo '{"action":"decay"}' | /usr/local/bin/python3 plugins/claw-sapphire/tools/source_quality.py
```

### 4.2 "Show me the near-duplicate pairs"

```bash
echo '{"action":"near-duplicates"}' | /usr/local/bin/python3 plugins/claw-sapphire/tools/source_quality.py
```

The output JSON's `near_duplicates` array contains every pair ≥ 87%. For
each, the operator should consider:

- Are they really independent? (Different upstream feeds, different
  collection methods, different operators.)
- If yes, the high agreement is genuine corroboration → leave the weights
  alone.
- If no, downweight one or remove from the correlator's source set.

The correlator weights live at `~/.sapphire/correlator_weights.yaml`. This
lane does **not** auto-modify them; the operator does.

### 4.3 "I want to recompute without disturbing the file on disk"

```bash
echo '{"action":"recompute"}' | /usr/local/bin/python3 plugins/claw-sapphire/tools/source_quality.py
```

The plugin tool always runs in memory-only mode regardless of env vars.
This is intentional — only the daemon writes.

### 4.4 "Why is `samples_total: 0`?"

Most likely you don't have an outcomes file at
`data/source_quality_outcomes.jsonl`, or your outcomes are outside the 24h
lookahead window from any of your signals. Check:

```bash
ls -la data/source_quality_outcomes.jsonl
wc -l data/source_quality_outcomes.jsonl
```

If the file is present but the lookahead doesn't cover, set a wider window
in a manual run by editing the outcomes file's timestamps to be within 24h
of recent signals (or wait for new data).

---

## 5. Recalibration

### 5.1 Adjusting the near-duplicate threshold

The 87% threshold is calibrated to Sapphire's current Telegram feed. If
the operator wants to be more aggressive (catch more candidates) or more
permissive (only flag obvious copies), pass a custom threshold to the
correlation API:

```python
from lib.source_quality.correlation import flag_near_duplicates
flagged = flag_near_duplicates(report, threshold=0.80)
```

The daemon does not currently take a threshold flag — open an issue or
ask for a future config knob if 0.87 systematically misfires.

### 5.2 Adjusting the decay threshold

Same pattern; `lib.source_quality.decay.detect_decay(threshold=0.10)` for
a more sensitive flag, `0.20` for a more conservative one.

### 5.3 Per-source lookahead windows

Currently a single 24-hour window. To experiment with per-source windows
in a one-off analysis, call `compute_source_snr` directly for each source
with a custom `window_hours` and merge the dicts. The daemon's daily
report uses the default for now.

---

## 6. Incident response

### 6.1 Daemon writing oversized reports

If a JSONL feed gets corrupted with billions of rows (unlikely; we cap
upstream feeds), the daemon could OOM. Mitigations already in place:

- Each feed walk uses a sorted glob and the per-row `_safe_iter_jsonl`
  silently drops malformed rows.
- The plugin tool's `MAX_RESPONSE_BYTES = 256 KiB` truncates payloads on
  the way out; the daemon's on-disk file has no equivalent cap because
  the dashboard streams a slice, not the whole thing.

If you observe `data/source_quality/<date>/report.json` exceeding ~ 5 MB,
investigate the upstream feed (most likely a runaway Telegram channel).

### 6.2 Disable the daemon

```bash
launchctl unload ~/Library/LaunchAgents/com.sapphire.source-quality.plist
```

Optionally delete the plist so it won't re-load on next OS boot:

```bash
rm ~/Library/LaunchAgents/com.sapphire.source-quality.plist
```

The dashboard routes will continue to serve the last good report on disk
until the operator deletes the `data/source_quality/` tree.

### 6.3 Wipe the artefacts

```bash
rm -rf data/source_quality/
```

The dashboard routes degrade to `status: no_data` and continue serving.

### 6.4 Stuck on a bad report

If a manual run wrote a report that pollutes the dashboard:

```bash
rm -rf data/source_quality/$(date +%Y-%m-%d)
/usr/local/bin/python3 -m services.source_quality.run --no-write
```

Re-inspect; once happy, drop `--no-write` to re-persist.

---

## 7. CI + verification

Local pre-merge gate (matches what the megaprompt's verification protocol
runs):

```bash
ruff check lib/source_quality services/source_quality plugins/claw-sapphire/tools/source_quality.py plugins/claw-sapphire/tools/internal/source_quality.py
/usr/local/bin/python3 -m pytest tests/unit/test_source_quality_*.py tests/unit/test_dashboard_source_quality_routes.py -q
/usr/local/bin/python3 -m pytest plugins/claw-sapphire/tests/test_source_quality.py -q
/usr/local/bin/python3 scripts/validate_tool_registry.py
```

CI runs the same on every PR via `.github/workflows/ci.yml` — there is no
new workflow specific to this lane.

---

## 8. Schema-version policy

The daily report's `schema_version` is `1`. Future schema changes:

- **Backward-compatible additions** (new fields) → keep `schema_version: 1`.
- **Backward-incompatible changes** (renamed fields, changed semantics) →
  bump to `schema_version: 2` and update every dashboard route + plugin
  tool to handle both versions, or deprecate v1 with a 30-day window.

The provenance envelope's `schema_version` is independent (currently 1)
and lives in `lib/core/provenance.py`.

---

## 9. Known gaps + future work

- **No outcomes auto-derivation.** Operator-supplied outcomes file is the
  current contract.
- **No per-source lookahead.** A single 24h window across all sources.
- **No alerting.** A near-duplicate or decay alert does not currently page
  the operator; they only see it on the dashboard or via the plugin tool.
  Tranche 7+ candidate: hook the daemon's summary into the morning digest.
- **No Foundry ontology object yet.** `lib/foundry/ingestion.py` could pick
  up `data/source_quality/<date>/report.json` once the schema stabilises.
- **No README counts touched.** Per the megaprompt, no README test counts
  during multi-lane work; Lane 9 (integration pass) updates them once.

---

## 10. Pointers

- Lane spec: `docs/handoffs/tranche-6-excellence-megaprompt-2026-04-29.md`
- Product doc: `docs/products/source-quality-measurement-0.1.0.md`
- Provenance helper: `lib/core/provenance.py`
- Tool registry: `infra/tool-registry.yaml` (entry: `source_quality`)
- Dashboard end-of-file region: `services/dashboard/app.py` (search for
  `Tranche 6 Lane 4`)
