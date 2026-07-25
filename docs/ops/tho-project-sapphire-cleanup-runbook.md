# Runbook — remove Sapphire from the THO production project

**Status:** prepared, **not executed**. Every destructive step is gated on Ari.
**Target project:** `tho-ai-agent` (THO production — fenced).
**Prepared:** 2026-07-25.

## Why this is not a delete-first job

Sapphire's live code **hardcodes `tho-ai-agent`** as its GCP project. Deleting
the resources before repointing the code breaks the Sapphire pipeline rather
than cleaning it up. The order below is mandatory.

Call sites that must move first:

| File | Reference |
|---|---|
| `services/pipeline/gcp_sync.py:44,46` | `PROJECT = "tho-ai-agent"`, `BUCKET = "sapphire-data-lake"` |
| `services/pipeline/pubsub_publisher.py:27` | `GCP_PROJECT` default |
| `services/pipeline/check_routines.py:33` | `GCP_PROJECT` constant |
| `infra/gcp/bootstrap_{gcs,bigquery,pubsub}.sh` | `PROJECT` default |
| `infra/gcp/schedule_queries.sh`, `deploy_cloud_function.sh` | `PROJECT` default |
| `infra/gcp/cloud_functions/gcs_to_bq/main.py:28` | `GCP_PROJECT` default |
| `infra/launchagents/com.sapphire.gcp-sync.plist:36` | env `tho-ai-agent` |
| `plugins/claw-sapphire/tools/{service_supervisor,sapphire_pm_bot,dev_pulse}.py` | `THO_FIRESTORE_PROJECT` default |

Note `dev_pulse.py:53` also *monitors* `sapphire-analytics` in `tho-ai-agent`;
that probe must be retargeted or dropped.

## Inventory to remove (verified 2026-07-25)

| Resource | Detail | Notes |
|---|---|---|
| `gs://sapphire-data-lake` | 1,571 objects / 278 MB / US-CENTRAL1 | writes stopped 2026-05-14 |
| BigQuery dataset `sapphire` | 27 tables, location `US`, labels `env:prod` | includes `brain_synthesis`, `decisions`, `anomaly_log` |
| Cloud Run `sapphire-analytics` | public ingress | |
| Cloud Run `sapphire-gcs-to-bq` | public ingress | the data-lake → BQ loader |
| Cloud Run `sapphire-os-terminal` | public ingress | |
| DNS zone `sapphirealpha-xyz` | NS `ns-cloud-c1..c4` | **orphan — not authoritative** |
| Domain mapping `tho.sapphirealpha.xyz` | → `project-go-forward` | THO testing-phase leftover |

`texashomeoutlet.com` and `www.texashomeoutlet.com` are **THO production and
must not be touched.**

## Phase 0 — snapshot (reversible)

```bash
mkdir -p ~/ops-state/tho-cleanup-2026-07-25 && cd ~/ops-state/tho-cleanup-2026-07-25
gcloud run services list --project tho-ai-agent --format=json > run-services.json
gcloud dns record-sets list --zone sapphirealpha-xyz --project tho-ai-agent --format=json > orphan-zone.json
gcloud beta run domain-mappings list --project tho-ai-agent --region us-central1 --format=json > mappings.json
bq --project_id=tho-ai-agent ls -n 1000 sapphire > bq-tables.txt
gcloud storage ls -lr "gs://sapphire-data-lake/**" > gcs-manifest.txt
```

## Phase 1 — repoint code (reversible, normal PR)

Replace every hardcoded `tho-ai-agent` above with `sapphire-479610`, preferring
an env var with a `sapphire-479610` default. Land via PR with tests green. **Do
not delete anything yet.**

## Phase 2 — migrate data (additive, non-destructive)

```bash
# Bucket — create in the personal project, then copy
gcloud storage buckets create gs://sapphire-data-lake-479610 \
    --project=sapphire-479610 --location=US-CENTRAL1
gcloud storage cp -r "gs://sapphire-data-lake/*" gs://sapphire-data-lake-479610/

# BigQuery — dataset copy (US → US, so a straight transfer works)
bq --project_id=sapphire-479610 mk --dataset --location=US sapphire
bq mk --transfer_config --project_id=sapphire-479610 --data_source=cross_region_copy \
    --target_dataset=sapphire --display_name="sapphire dataset migration" \
    --params='{"source_project_id":"tho-ai-agent","source_dataset_id":"sapphire"}'
```

Verify object counts and per-table row counts match before proceeding.

## Phase 3 — cutover and soak

Point the LaunchAgent and services at the new bucket/dataset, run for **at least
7 days**, and confirm the pipeline writes to `sapphire-479610` only. Nothing in
`tho-ai-agent` should receive new Sapphire writes.

## Phase 4 — DELETE (⚠️ GATED — requires Ari's explicit approval)

Do not run any of this without sign-off. Each command is irreversible and lands
in THO production.

```bash
# 4a. Orphan DNS zone — safe: not authoritative, holds no live records.
gcloud dns record-sets delete terminal.sapphirealpha.xyz. --type=CNAME \
    --zone=sapphirealpha-xyz --project=tho-ai-agent
gcloud dns record-sets delete sapphirealpha.xyz. --type=A \
    --zone=sapphirealpha-xyz --project=tho-ai-agent
gcloud dns record-sets delete sapphirealpha.xyz. --type=AAAA \
    --zone=sapphirealpha-xyz --project=tho-ai-agent
gcloud dns record-sets delete www.sapphirealpha.xyz. --type=CNAME \
    --zone=sapphirealpha-xyz --project=tho-ai-agent
gcloud dns managed-zones delete sapphirealpha-xyz --project=tho-ai-agent

# 4b. THO testing-phase domain mapping (confirm texashomeoutlet.com is serving first)
curl -sSI https://texashomeoutlet.com | head -1     # expect 200/301
gcloud beta run domain-mappings delete --domain=tho.sapphirealpha.xyz \
    --project=tho-ai-agent --region=us-central1

# 4c. Sapphire Cloud Run services
for s in sapphire-analytics sapphire-gcs-to-bq sapphire-os-terminal; do
    gcloud run services delete "$s" --project=tho-ai-agent --region=us-central1 --quiet
done

# 4d. Data — only after Phase 2 verification and the soak
bq --project_id=tho-ai-agent rm -r -f sapphire
gcloud storage rm -r gs://sapphire-data-lake
```

Also remove the `tho` CNAME from the **authoritative** zone once 4b is done:

```bash
gcloud dns record-sets delete tho.sapphirealpha.xyz. --type=CNAME \
    --zone=sapphirealpha-xyz --project=sapphire-479610
```

## Rollback

Phases 1-3 are revertable by reverting the PR and repointing the LaunchAgent.
Phase 4 is **not** — restoration depends entirely on the Phase 0 snapshot and
the Phase 2 copies. Do not start 4d until 4a-4c have soaked cleanly.

## Guard-rails

- Never `gcloud config set project tho-ai-agent`; pass `--project` explicitly.
- `guard-bash.sh` gates mutating gcloud and DNS — a block here is the gate
  working. Surface it, do not route around it.
- THO production surfaces (`texashomeoutlet.com`, `project-go-forward`,
  `tho-agent`, `docuseal`, the `tho-*` buckets and secrets) are out of scope.
