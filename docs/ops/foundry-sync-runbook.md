# Foundry Sync Runbook

Last reviewed: 2026-04-30

## Triage Quickstart

Failure mode addressed: foundry-sync history shows repeated failures, OR
watermarks are stale, OR the dry-run reports unexpected transform errors.

```bash
launchctl list com.sapphire.foundry-sync
```

```bash
tail -n 200 data/logs/foundry-sync-err.log
```

```bash
/usr/local/bin/python3 -m lib.foundry.sync --dry-run --force
```

The dry-run does not touch credentials and does not upload to Foundry — it
exercises only the transform path. If it succeeds and the LaunchAgent is
failing, the fault is in the credential / write path. Do NOT print credential
contents in incident reports; the readiness helper at `lib/foundry/readiness.py`
returns redacted status.

Live monitors: `data/foundry_sync_history.jsonl` (per-run record);
provenance sidecars under `data/foundry_sync_state.json`.
On-call escalation: data owner / Foundry POC; p3 unless Palantir-side stake-
holders are blocked, then p2. Pre-pilot: do not enable live writes without an
explicit operator-approved PR.

This runbook covers `services/foundry_sync/`,
`infra/launchagents/com.sapphire.foundry-sync.plist`, and
`lib/foundry/sync.py`. The job scans local Sapphire artifacts, transforms
changed files into Foundry ontology or dataset objects, writes per-type
watermarks, appends sync history, and uploads only when Foundry credentials and
write targets are configured.

Foundry sync is production-adjacent. The operator posture is dry-run first,
no credential printing, and no live ontology or dataset writes unless the
destination stack, write mode, and expected object types have been reviewed.

## Ownership

| Item | Path |
|---|---|
| LaunchAgent | `infra/launchagents/com.sapphire.foundry-sync.plist` |
| Service wrapper | `services/foundry_sync/sync.py` |
| Sync engine | `lib/foundry/sync.py` |
| Client | `lib/foundry/client.py` |
| Readiness helper | `lib/foundry/readiness.py` |
| Transform registry | `lib/foundry/ingestion.py` |
| State file | `data/foundry_sync_state.json` |
| History file | `data/foundry_sync_history.jsonl` |
| Watermarks | `~/.cache/sapphire/foundry_sync/*.json` |
| Stdout log | `data/logs/foundry-sync.log` |
| Stderr log | `data/logs/foundry-sync-err.log` |
| Routine pause name | `foundry-sync` |

## Data Flow

```text
data/signals + data/health + data/intelligence + regional Foundry export
  -> lib.foundry.ingestion transforms
  -> object batches by type
  -> ~/.cache/sapphire/foundry_sync/<ObjectType>.json watermark
  -> Foundry action or dataset write when configured
  -> data/foundry_sync_history.jsonl + provenance sidecar
```

Current object families include `PaperTrade`, `Alert`, `ServiceHealth`,
`ThreatIntel`, `DailyBrief`, `Region`, `IntelItem`, `IntelSourceHealth`,
`IntelVectorRecord`, `TelegramIntelMessage`, `HyperliquidSignal`,
`OODAPacket`, and `ThreatIndicator`.

## Normal Operation

Check launchd:

```bash
launchctl list com.sapphire.foundry-sync
```

Inspect logs:

```bash
tail -n 200 data/logs/foundry-sync.log
tail -n 200 data/logs/foundry-sync-err.log
```

Run a no-write transform check:

```bash
/usr/local/bin/python3 -m lib.foundry.sync --dry-run --force
```

Inspect sync status:

```bash
/usr/local/bin/python3 - <<'PY'
from lib.foundry.sync import get_sync_status
import json
print(json.dumps(get_sync_status(), indent=2, sort_keys=True))
PY
```

Inspect recent history:

```bash
tail -n 5 data/foundry_sync_history.jsonl | python3 -m json.tool
```

If `json.tool` cannot parse because several JSONL rows are piped at once, use:

```bash
/usr/local/bin/python3 - <<'PY'
import json
from pathlib import Path
for line in Path("data/foundry_sync_history.jsonl").read_text().splitlines()[-5:]:
    print(json.dumps(json.loads(line), indent=2, sort_keys=True))
PY
```

## Configuration

Configuration resolves first from environment variables, then from files under
`$SAPPHIRE_SECRETS_DIR` or `~/.config/sapphire-secrets`.

| Setting | Environment | Secret file |
|---|---|---|
| Stack URL | `PALANTIR_FOUNDRY_URL` or `FOUNDRY_URL` | `foundry_url` |
| Bearer token | `PALANTIR_FOUNDRY_TOKEN` or `FOUNDRY_TOKEN` | `foundry_token` |
| OAuth client id | `PALANTIR_FOUNDRY_CLIENT_ID` or `FOUNDRY_CLIENT_ID` | `foundry_client_id` |
| OAuth secret | `PALANTIR_FOUNDRY_CLIENT_SECRET` or `FOUNDRY_CLIENT_SECRET` | `foundry_client_secret` |
| Ontology | `PALANTIR_FOUNDRY_ONTOLOGY` or `FOUNDRY_ONTOLOGY` | `foundry_ontology` |
| Upsert action | `PALANTIR_FOUNDRY_UPSERT_ACTION` or `FOUNDRY_UPSERT_ACTION` | `foundry_upsert_action` |
| Write mode | `PALANTIR_FOUNDRY_WRITE_MODE` or `FOUNDRY_WRITE_MODE` | `foundry_write_mode` |
| Dataset map | `PALANTIR_FOUNDRY_DATASET_MAP` or `FOUNDRY_DATASET_MAP` | `foundry_dataset_map` |

Valid write modes are `action` and `dataset`. Dataset mode requires a JSON map
from object type to dataset RID. Do not paste token values into the terminal
history, docs, PRs, or issue comments.

## Routine Pause

Pause before maintenance or before a suspected bad transform:

```bash
mkdir -p ~/.sapphire/routine_pause
date -u +%Y-%m-%dT%H:%M:%SZ > ~/.sapphire/routine_pause/foundry-sync
```

Resume only after dry-run is clean:

```bash
rm ~/.sapphire/routine_pause/foundry-sync
```

The LaunchAgent wrapper calls `abort_if_paused("foundry-sync")`, so a pause
flag exits before the sync engine loads credentials or scans objects.

## Readiness Checks

Run the local readiness helper without writes:

```bash
/usr/local/bin/python3 - <<'PY'
from lib.foundry.readiness import build_readiness_report
import json
print(json.dumps(build_readiness_report(), indent=2, sort_keys=True))
PY
```

Look for:

- Config presence only; no secret values should be printed.
- Required object fields in sampled transforms.
- Regional-intel manifest compatibility for `Region`, `IntelItem`, and
  `IntelSourceHealth`.
- Sync history readback with `ok`, `timestamp`, and `duration_s`.

If readiness reports schema mismatches, fix the transform or ontology mapping
before running live. Do not mutate upstream source data to make a row pass.

## Common Failures

### Dry-Run Finds No Changes

This is normal when state hashes match current files. Use `--force` for a
full transform pass:

```bash
/usr/local/bin/python3 -m lib.foundry.sync --dry-run --force
```

### Foundry Not Configured

When URL or credentials are missing, live sync marks the run as skipped and
`ok=true` to avoid a LaunchAgent restart loop. This is an expected setup state,
not proof that Foundry writes are working.

### Pre-First-Success 404

In action mode, a `404` before the first successful upload usually means the
Foundry ontology action has not been deployed. Finish ontology/action
provisioning, then rerun dry-run and a reviewed live sync. After the first
success, a new `404` is a regression and should page through the normal error
path.

### Auth Failure

Auth failures before first success are rate-limited to avoid 15-minute alert
spam. Confirm URL, token/OAuth pair, write mode, and ontology/action names.
Never echo token values. Rotate credentials if they might have been pasted or
captured.

### Schema Drift

If transforms emit objects missing required fields, `lib.foundry.readiness`
will call it out. Compare the failing object type against
`_OBJECT_REQUIRED_FIELDS` in `lib/foundry/readiness.py`, then update the
transform or the ontology contract in the same PR.

### History or State Corruption

Move corrupt files aside rather than deleting them:

```bash
mv data/foundry_sync_state.json data/foundry_sync_state.json.$(date +%Y%m%dT%H%M%S).bak
mv data/foundry_sync_history.jsonl data/foundry_sync_history.jsonl.$(date +%Y%m%dT%H%M%S).bak
```

Then run a forced dry-run before allowing the LaunchAgent to resume.

## Safety Notes

- Dry-run first, always.
- Do not run live writes while the routine pause flag is present.
- Do not print Foundry bearer tokens, OAuth secrets, or dataset maps containing
  sensitive stack details.
- Do not convert pre-first-success setup warnings into hard LaunchAgent
  failures; the sync intentionally avoids restart spam while provisioning is
  incomplete.
- Do not ignore post-success 404s, auth errors, or schema drift. Those are
  regressions once the stack has worked before.
- Foundry is a downstream data plane. Local Sapphire JSONL and NDJSON artifacts
  remain the source of truth during an outage.

## Escalation

Escalate when:

- Dry-run crashes in a transform.
- Readiness reports missing required fields for production object types.
- A stack that previously synced starts returning 404, auth errors, or schema
  rejections.
- Sync history is unreadable after backup-and-rerun.
- A live run would replay more history than intended.

Include the dry-run command, `get_sync_status()` output, last 200 log lines,
the failing object type, and readiness report excerpts with secret values
redacted.
