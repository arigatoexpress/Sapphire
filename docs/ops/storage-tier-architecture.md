# Sapphire Storage Tier Architecture

Sapphire uses five storage tiers. The rule is simple: code and reproducible
contracts live in git; operational data moves through hot, warm, queryable, and
cold stores with explicit retention.

## T1 — Sapphire Git Monorepo

Path: `/Users/aribs/Code/Sapphire`

Purpose:
- Source code, tests, schemas, operator runbooks, LaunchAgent templates, and
  reproducible generators.
- Versioned product contracts such as Foundry schemas, risk-kernel policy, and
  CI guardrails.

Policy:
- No secrets, customer files, hot runtime data, or large binaries.
- `tools/` is source-only; build output must be ignored or moved.
- Top-level drift is blocked by `scripts/ops/check_repo_structure.py`.

## T2 — Local Data Lake

Path: `/Users/aribs/Code/Sapphire/data/`

Purpose:
- Local runtime observations and reproducibility artifacts that are useful near
  the operator but should not become permanent git history.

Partitions:
- Hot: `data/system_events.jsonl`, `data/events/`, `data/health/`,
  `data/metrics/`, `data/chain/`, `data/intelligence/latest`,
  `data/.gcp_stage/`, `data/logs/`, `data/ci/`.
- Warm: `data/backtests/`, `data/content/`, `data/intelligence/runs/`,
  `data/security/`, `data/performance/`, `data/media/`.
- Cold candidates: `data/benchmarks/`, old generated reports, and any artifact
  older than 30 days that has either been synced or is no longer operational.

Policy:
- Hot data ages out after 7 days once promoted or superseded.
- Warm data ages out after 30-90 days.
- Cold candidates are gzipped and promoted to T3/T4 before local pruning.
- Apply-mode pruning requires an explicit `--i-mean-it` gate.

## T3 — GCP Data Lake

Primary resources:
- `gs://sapphire-data-lake`
- BigQuery dataset `sapphire.*`
- Project references: `tho-ai-agent`, `sapphire-479610`

Purpose:
- Analyst-grade query history, Foundry sync staging, event sync, threat-intel
  facts, service health, and durable operational metrics.

Policy:
- Lifecycle policies enforce free-tier discipline.
- BigQuery writes require reviewed sync windows or dry-run evidence.
- Every promoted artifact should carry provenance: generator, source path,
  hash, generated timestamp, and stale-after timestamp.

## T4 — Proton Drive Cold Backup

Path:
`/Users/aribs/Library/CloudStorage/ProtonDrive-aribspector@proton.me-folder`

Purpose:
- Quarterly tarballed repo snapshots, campaign material, planning docs, and
  incident artifacts that should be encrypted at rest outside the git repo.

Policy:
- Incident artifacts are redacted before promotion when possible.
- Proton deletion remains an operator action, not an automation default.
- Cold snapshots should include a manifest and SHA-256 hashes.

## T5 — Google Drive Active Workspace

Purpose:
- THO operational documents, customer files, contracts, customer PDFs, meeting
  notes, and active business spreadsheets.

Policy:
- Not synced into Sapphire git.
- Read-only integration surfaces must redact PII by default and should write
  derived intelligence into T3/T4 only after explicit approval.

## Current Known Pressure Points

- `tools/pm-commander/.build` is tracked and accounts for roughly 445 MB of the
  repo footprint. It should be removed from git in a dedicated cleanup PR after
  source/build reproducibility is confirmed.
- `data/` mixes tracked reference/config files with ignored hot runtime state.
  The storage sync planner documents this distinction and keeps apply mode
  explicit.
- `results/` remains a deprecated git resident. It should move to cold storage
  with a manifest before deletion from `main`.
- `legacy_code/` was cold-copied to Proton Drive on 2026-04-28 and removed from
  git in the follow-up cleanup PR.

## Promotion Rules

| From | To | Gate |
|---|---|---|
| T2 hot | T3 BigQuery/GCS | dry-run plan, hash manifest, no secret findings |
| T2 warm | T3/T4 | artifact age threshold plus operator-visible manifest |
| T1 deprecated source | T4 | reproducibility note and cold backup proof |
| T5 Drive | T3/T4 | explicit operator approval and PII redaction |

`scripts/ops/storage_tier_sync.py --plan` is the canonical local planner. It
prints every read/write candidate before any apply-capable action is available.
