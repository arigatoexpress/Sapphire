# GCP Cloud Shell Ultimate Handoff — 2026-08-06

**Audience:** Ari on Google Cloud Shell (away from Mac plant)  
**Goal:** Holistically improve Sapphire via GCP + monorepo work, and advance the masterplan **without** live trading, money movement, or plant-only side effects.  
**Doctrine:** Local plant truth > Cloud Shell. Cloud Shell is a **read / invent / code / dry-run / PR** plane. It is **not** the trading control tower.  
**Generated:** 2026-08-06 · Grok Build (web) after alpha ledger merge + master Opus handoff  
**Repo:** `arigatoexpress/Sapphire` · branch `main`  
**North star (Windows private DC):** [`docs/strategy/WINDOWS-DATACENTER-MASTERPLAN-2026-08-06.md`](../strategy/WINDOWS-DATACENTER-MASTERPLAN-2026-08-06.md)  
**Gemini paste prompt:** [`docs/handoffs/GEMINI-CLOUDSHELL-MASTER-PROMPT-2026-08-06.md`](./GEMINI-CLOUDSHELL-MASTER-PROMPT-2026-08-06.md)  
**Companion bootstrap:** [`scripts/ops/gcp_cloudshell_bootstrap.sh`](../../scripts/ops/gcp_cloudshell_bootstrap.sh)  
**Bridge export:** [`data/grok-web-exports/2026-08-06_gcp-cloudshell-ultimate-handoff.md`](../../data/grok-web-exports/2026-08-06_gcp-cloudshell-ultimate-handoff.md)

---

## 0) Why this exists

You are away from the plant (Mac + Win + Pis). Cloud Shell is the reliable remote operator seat for:

| You can do well here | You must not pretend Cloud Shell can do |
|---|---|
| GCP inventory (BQ, GCS, Cloud Run, Vertex idle posture) | Place / cancel / replace RH or L2 orders |
| Cost posture + idle burn check | Touch MOSS passkey / MegaETH grant UX |
| Schema / SQL / bootstrap idempotency | Mac LaunchAgents / Windows schtasks |
| Code PRs: paper fund-factory, dens, docs, dashboards | Hermes Telegram **sends** |
| Vertex **batch** design + eval harness dry-runs | Prod DNS / website cutover without exact owner phrase |
| Read-only dashboard deploys (`--no-traffic` tags) | Secret values print / rotate / commit |
| Knowledge bridge commits under `data/grok-web-exports/` | Killswitch arm/disarm as ambient authority |

When you reconnect to the plant, densify this folder via:

```bash
# On Mac plant only
bash ~/ops-state/finish-line/scripts/sync_grok_web_exports.sh
# → ~/Knowledge/0-Inbox/grok-web/ → densify / Ralph → :8100
```

---

## 1) Absolute fences (Cloud Shell edition)

### 1.1 Money / trading / messaging

1. **Designated rails only** (even when plant is reachable later): RH Agentic `703758144` (••••8144), RH L2 `0xc2B5…c9EB`, MOSS/MegaETH (grant-gated), paper.  
2. **Models propose only** — coordinator + first-party receipts authorize. No ambient spend/trade authority from Cloud Shell.  
3. **No THO / Project-Go-Forward money.** Project `tho-ai-agent` is a **data + AI complement** project, not a license to touch THO client funds or `texashomeoutlet.com` cutovers.  
4. **No Hermes messaging send** from Cloud Shell. Telegram Central Terminal is plant-side.  
5. **No live order placement** from GCP jobs, Cloud Functions, Cloud Run, or Vertex. Paper/research only.  
6. Dust sleeve: **do not re-place** IBIT/HOOD/PLTR/NVDA buys. Exit order_ids (if still open) are plant/broker truth — Cloud Shell does not manage them.  
7. Dens permanent: SONNY / BINGBONG class + short `0x` prefixes — never re-enable as free-reign spam.

### 1.2 Secrets / credentials

- Use **Cloud Shell ADC / gcloud user login** only.  
- Do **not** download SA JSON into the home disk and leave it.  
- Do **not** `cat` Secret Manager payloads into chat logs.  
- Do **not** commit `.env`, keys, cookies, or token files.  
- `RELAY_READER_TOKEN` rotation is **blocked** until plant-side confirmed — do not retarget LaunchAgents from docs alone.

### 1.3 Deploy / DNS / website

| Action | Cloud Shell default |
|---|---|
| `gcloud run services list/describe` | ✅ read-only |
| `gcloud run deploy … --no-traffic --tag=…` | ✅ preview only if explicitly needed |
| Route 100% traffic / delete old revs | ❌ attended only |
| Edit DNS in **`sapphire-479610`** zone `sapphirealpha-xyz` | ❌ unless exact owner phrase for that change |
| Edit DNS in **`tho-ai-agent`** for `sapphirealpha.xyz` | ❌ **orphan zone** — edits succeed and do nothing (trap) |
| Enable random APIs / create projects | ❌ budget + owner gate |

**DNS trap (verified 2026-07-25):** registrar NS → `ns-cloud-e1..e4` on project **`sapphire-479610`**. The `tho-ai-agent` zone is orphaned. Always:

```bash
dig +short sapphirealpha.xyz NS   # must be e1..e4
```

### 1.4 Git hygiene

- Never `git add -A`. Stage explicit paths.  
- Prefer PR branches for code; direct `main` only for inert docs / `data/grok-web-exports/` bridge files with clear messages.  
- Never archive paths named `RETIRED` without `readlink` / WorkingDirectory check (telegram-bot trap — plant-side).

---

## 2) 60-second bootstrap (copy into Cloud Shell)

```bash
# 1) Auth + project (data plane)
gcloud auth login   # if needed
gcloud config set project tho-ai-agent
gcloud config set run/region us-central1

# 2) Clone or update Sapphire
export SAPPHIRE_DIR="${SAPPHIRE_DIR:-$HOME/Sapphire}"
if [[ -d "$SAPPHIRE_DIR/.git" ]]; then
  git -C "$SAPPHIRE_DIR" pull --ff-only origin main
else
  git clone https://github.com/arigatoexpress/Sapphire.git "$SAPPHIRE_DIR"
fi
cd "$SAPPHIRE_DIR"

# 3) Bootstrap inventory + print this handoff path
bash scripts/ops/gcp_cloudshell_bootstrap.sh

# 4) Open the handoff
less docs/handoffs/GCP-CLOUD-SHELL-ULTIMATE-HANDOFF-2026-08-06.md
```

One-liner after first clone:

```bash
cd ~/Sapphire && git pull --ff-only && bash scripts/ops/gcp_cloudshell_bootstrap.sh
```

---

## 3) System map

### 3.1 Two GCP projects (do not collapse them)

| Project | Number | Role | Cloud Shell default |
|---|---|---|---|
| **`tho-ai-agent`** | `691674245427` | Data lake, BQ `sapphire`, Pub/Sub, GCF loader, Vertex complement, THO Cloud Run (`project-go-forward`) | **Primary work project** for data/AI |
| **`sapphire-479610`** | (website / Mission Control) | `sapphire-alpha-dashboard`, **authoritative DNS** for `sapphirealpha.xyz`, public site | Read inventory; mutate only with owner gate |

Region default: **`us-central1`**. BQ multi-region: **`US`**.

Service account (data plane):  
`sapphire-data-ops@tho-ai-agent.iam.gserviceaccount.com`

### 3.2 Data plane (tho-ai-agent)

```text
Mac plant (local truth)
  ├─ hot:  Pub/Sub topics → BQ subscriptions → sapphire.*
  └─ warm: gcp_sync → gs://sapphire-data-lake/raw/<src>/YYYY-MM-DD/*.ndjson
              → Cloud Function sapphire-gcs-to-bq → BQ append
```

| Resource | Name |
|---|---|
| Bucket | `gs://sapphire-data-lake` |
| Dataset | `tho-ai-agent:sapphire` |
| Topics | `sapphire-signals`, `sapphire-predictions`, `sapphire-regime-changes`, `sapphire-threats`, `sapphire-alerts` |
| GCF | `sapphire-gcs-to-bq` (GCS finalize → BQ) |
| Scheduled queries | `daily_performance`, `weekly_regime`, `daily_threats`, `prediction_accuracy` |

Local sync (plant only): `services/pipeline/gcp_sync.py` + LaunchAgent `com.sapphire.gcp-sync`.  
**Cloud Shell cannot advance Mac watermarks.** You can only verify downstream freshness and fix cloud-side loaders/schemas.

### 3.3 Public / GPU surface

| Name | Notes |
|---|---|
| `sapphirealpha.xyz` / `www` | Cloud Run `sapphire-alpha-dashboard` on **`sapphire-479610`** |
| `gpu.sapphirealpha.xyz` → `34.29.235.86` | Often 401; treat as remote GPU / protected |
| `tho.sapphirealpha.xyz` | **Retired** leftover; THO lives on `texashomeoutlet.com` |
| Dangling DNS | `dashboard`, `gateway`, `pm`, `hack`, `regional`, … — resolve but no mapping |

### 3.4 Plant + monorepo (canonical)

| Surface | Role |
|---|---|
| `~/Code/Sapphire` (this repo) | Monorepo OS + bridge + GCP infra scripts |
| `~/ops-state` (Mac) | Live plant: finish-line, telegram-bot, rh-chain, moss, sovereign-desk |
| `~/Knowledge` (Mac) | Vault + `0-Inbox/grok-web/` densify path |
| `~/Code/Project-Go-Forward` | THO client — **FENCED from fleet bulk** |
| `~/Code/sapphire-alpha-dashboard` | Public Mission Control sibling (if still separate) |

**Authority boundary:** Cloud Shell code + GCP metadata never override plant killswitch, free-reign files, or broker receipts.

### 3.5 Vertex posture

Vertex is a **complement**, not control:

- Prefer **batch** / ephemeral jobs over always-on endpoints.  
- No ambient training, tuning, or endpoint deploy.  
- Inventory: `python3 scripts/ops/gcp_ai_inventory.py --project tho-ai-agent --region us-central1 --format markdown`  
- Plan: `docs/ops/gcp-vertex-ai-complement-plan.md`  
- Production ladder: `docs/ops/google-production-testing-runbook.md`

---

## 4) NOW board — 2026-08-06 (alpha critical path)

Plant truth may have moved; **re-verify on Mac** when home. Until then treat as last known:

| # | Item | Cloud Shell action | Plant action (later) |
|---|---|---|---|
| 1 | **Dust exits** IBIT/HOOD/PLTR/NVDA | Docs only — do not re-place | Confirm fills; no re-buy |
| 2 | **MOSS grant** expired / hours_left ≤ 0 | Document gap; no MegaETH job design that assumes grant | Renew passkey → ONE-CLICK-AFTER-GRANT |
| 3 | **Win fleet** recovery incomplete | Code/docs for parity checks only | Post-boot report → ARM schtasks after green |
| 4 | **AXTI playbook** (only proven +125% pattern) | Encode in paper risk modules / docs / ledger | After exits: 1–2 defined-risk option probes |
| 5 | **Dens permanent** SONNY/BINGBONG class | Keep denylist in repo/tests; never loosen in PR | Mirror free-reign dens on Mac+Win |

### Mandate (sticky when plant free-reign is on)

`free_reign_multi_rail` — RH Agentic easy + options-first + no dust placer; L2 ≤$10 max 1 open + dens; MOSS trade=true **only if** grant hours_left > 0.

### Exit orders (broker — informational; do not re-place)

| Sym | Qty | order_id |
|---|---:|---|
| IBIT | 0.551267 | `6a73b7da-1101-406f-9660-ff252e899336` |
| HOOD | 0.212833 | `6a73b7da-bcbf-41ae-9bf3-b91ebe2ca552` |
| PLTR | 0.123350 | `6a73b7da-41be-464a-ac03-b4b5d9bb62cf` |
| NVDA | 0.092140 | `6a73b7da-df71-44ca-bfa4-d567215cc7af` |

### Alpha ledger index (repo)

- `docs/alpha/GROK-CHAT-ALPHA-2026-08-06.md`  
- `data/alpha/alpha_ledger.json`  
- `data/grok-web-exports/2026-08-06_alpha-scour-merge.md`  
- Master plant handoff: `data/grok-web-exports/2026-08-05_master-handoff-claude-opus.md`

---

## 5) Masterplan phases — GCP-executable only

These phases map the holistic upgrade to work that is **safe and useful from Cloud Shell**. Plant-only steps are marked **PLANT**.

### Phase A — Situational awareness (Day 0, ~30–60 min) ✅ do first

1. Run bootstrap script (§2).  
2. `make google-readiness` (or offline if network APIs fail).  
3. Cost posture: `python3 scripts/ops/cost_posture_report.py --format markdown --hours 24 --log-limit 10`  
4. Cloud Run list both projects (read-only).  
5. BQ table freshness queries (§7.2).  
6. Write a short note under `data/grok-web-exports/YYYY-MM-DD_cloudshell-day0-inventory.md` and commit.

**Exit criteria:** You can state idle vs burning resources, BQ staleness, and dashboard revs without guessing.

### Phase B — Data-plane integrity (Days 1–2)

| Task | How | Gate |
|---|---|---|
| Confirm dataset/tables | `infra/gcp/bootstrap_bigquery.sh` (idempotent) | No destructive schema drops |
| Confirm bucket lifecycle | `infra/gcp/bootstrap_gcs.sh` | Lifecycle only |
| Pub/Sub inventory | `infra/gcp/bootstrap_pubsub.sh` dry mental model; re-run only if missing | No flood publish |
| GCF logs | `gcloud functions logs read sapphire-gcs-to-bq --region=us-central1 --limit=50` | Read-only |
| Scheduled query health | `bq ls --transfer_config --location=US` | Fix SQL via PR if broken |
| Freshness SQL | §7.2 | If stale → document; fix cloud-side only if GCF/schema; plant must re-sync |

**Exit criteria:** Every core table either fresh **or** has a named root cause (plant pause vs GCF vs schema).

### Phase C — Cost & idle posture (Day 2)

1. Identify always-on Cloud Run min-instances > 0 → recommend scale-to-zero unless justified.  
2. Confirm Vertex: **zero** custom jobs / endpoints / indexes (expected).  
3. Label any new resource: `owner=sapphire`, `env=dev|prod`, `lane=…`, `cost_center=…`.  
4. Optional: enable Cloud Scheduler **only** with owner gate (API historically not always on).

**Exit criteria:** Written cost note; no new always-on endpoints.

### Phase D — Paper / research product surfaces (Days 2–4)

Safe code work in branches:

| Workstream | Paths | Notes |
|---|---|---|
| Alpha ledger / dashboards | `docs/alpha/`, `data/alpha/`, `services/dashboard/`, analytics | Public-read-only flags stay on |
| Paper fund-factory | `lib/trading/`, fund-factory paper rails | Killswitch no-op already verified AU-01 |
| Dens / denylist tests | denylist files + unit tests | Never loosen dens |
| Approval bundles (task 053) | `lib/autonomy/` | Immutable hash, expiry, fail-closed |
| Knowledge embed integrity (task 050) | `lib/intel/bq_vector_store.py`, embedders | Fix in branch; no live vector wipe |
| Content / research | `lib/content/` | No auto-publish from Cloud Shell |
| GCP docs | `docs/gcp-data-engineering.md`, runbooks | Keep in sync with reality |

**Exit criteria:** PRs opened with tests; no secrets; CI green.

### Phase E — Vertex complement ladder (Days 3–5, optional)

Follow `docs/ops/gcp-vertex-ai-complement-plan.md` ladder **in order**:

1. Inventory only (already Phase A).  
2. Local dry-run OODA / mission digest artifacts under `data/google/production-readiness/` (gitignored if configured).  
3. **Manual gate** before any batch prediction: sample cap + spend cap + output path + rollback.  
4. BigQuery vector / retrieval design (`docs/products/bq-vector-retrieval-0.1.0.md`) — schema PRs first.  
5. Eval harness before any training.  
6. Training/tuning: **blocked** until evals prove a repeated gap.

### Phase F — Public Mission Control (attended)

- Source of truth build: `cloudbuild-dashboard.yaml` → `sapphire-alpha-dashboard`.  
- Deploy default: **no traffic shift** until owner phrase.  
- DNS only on `sapphire-479610`.  
- Keep `PUBLIC_READ_ONLY=true`, no internal jobs on public surface.

### Phase G — Plant reconnect (when home) **PLANT**

1. `git pull` Sapphire + densify grok-web-exports.  
2. Confirm dust exits / free-reign / dens / MOSS grant.  
3. Win post-boot green before ARM.  
4. Re-run Mac `gcp_sync --dry-run` then live only if pause clear.  
5. AXTI-class probes only after exits + caps.

---

## 6) Day scripts (copy-paste)

### 6.1 Identity + projects

```bash
gcloud auth list
gcloud config get-value project
gcloud projects describe tho-ai-agent --format='value(projectId,projectNumber,lifecycleState)'
gcloud projects describe sapphire-479610 --format='value(projectId,lifecycleState)' 2>/dev/null || true
```

### 6.2 APIs (read)

```bash
gcloud services list --enabled --project=tho-ai-agent \
  --filter='config.name:(bigquery OR storage OR run OR aiplatform OR pubsub OR cloudfunctions OR secretmanager OR cloudbuild)' \
  --format='table(config.name)'
```

### 6.3 BigQuery freshness

```bash
bq ls --project_id=tho-ai-agent sapphire

bq query --project_id=tho-ai-agent --use_legacy_sql=false --format=prettyjson '
SELECT table_id, row_count, ROUND(size_bytes/1024/1024,2) AS mb,
       TIMESTAMP_MILLIS(last_modified_time) AS last_modified
FROM `tho-ai-agent.sapphire.__TABLES__`
ORDER BY last_modified_time DESC
'

# Example hot table
bq query --project_id=tho-ai-agent --use_legacy_sql=false '
SELECT MAX(timestamp) AS max_ts, COUNT(*) AS n
FROM `tho-ai-agent.sapphire.trading_signals`
WHERE timestamp > TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 14 DAY)
'
```

### 6.4 GCS landing zone

```bash
gsutil ls gs://sapphire-data-lake/raw/
gsutil ls -l gs://sapphire-data-lake/raw/** | tail -n 40
# Do not delete objects during investigation
```

### 6.5 Cloud Function + Pub/Sub

```bash
gcloud functions describe sapphire-gcs-to-bq --region=us-central1 --project=tho-ai-agent --format=yaml 2>/dev/null \
  || gcloud functions describe sapphire-gcs-to-bq --gen2 --region=us-central1 --project=tho-ai-agent --format=yaml

gcloud pubsub topics list --project=tho-ai-agent
gcloud pubsub subscriptions list --project=tho-ai-agent --format='table(name,topic)'
```

### 6.6 Cloud Run (both projects)

```bash
gcloud run services list --project=tho-ai-agent --region=us-central1
gcloud run services list --project=sapphire-479610 --region=us-central1

gcloud run services describe sapphire-alpha-dashboard \
  --project=sapphire-479610 --region=us-central1 \
  --format='yaml(status.url,status.traffic,spec.template.spec.containers[0].resources)'
```

### 6.7 Vertex idle check

```bash
gcloud ai custom-jobs list --region=us-central1 --project=tho-ai-agent 2>/dev/null || true
gcloud ai endpoints list --region=us-central1 --project=tho-ai-agent 2>/dev/null || true
gcloud ai models list --region=us-central1 --project=tho-ai-agent 2>/dev/null || true
python3 scripts/ops/gcp_ai_inventory.py --project tho-ai-agent --region us-central1 --format markdown
```

### 6.8 Cost posture + Google readiness

```bash
cd ~/Sapphire
python3 scripts/ops/cost_posture_report.py --format markdown --hours 24 --log-limit 10
make google-readiness || python3 scripts/ops/google_production_test_readiness.py \
  --project tho-ai-agent --region us-central1 --format markdown
make google-readiness-cost || true
```

### 6.9 DNS sanity (read-only)

```bash
dig +short sapphirealpha.xyz NS
dig +short sapphirealpha.xyz A
dig +short gpu.sapphirealpha.xyz A
# Authoritative edits only on sapphire-479610 — do not "fix" the tho-ai-agent zone
```

### 6.10 Idempotent bootstrap (safe re-run)

```bash
cd ~/Sapphire
export PROJECT=tho-ai-agent
bash infra/gcp/bootstrap_gcs.sh
bash infra/gcp/bootstrap_bigquery.sh
# Pub/Sub / scheduled queries: re-run only when inventory shows missing resources
# bash infra/gcp/bootstrap_pubsub.sh
# bash infra/gcp/schedule_queries.sh
```

### 6.11 Preview deploy (no traffic) — optional / gated

```bash
# Analytics dashboard helper defaults may point at sapphire-479610 — read the script first
# Prefer --no-traffic and a tag; never ROUTE_TRAFFIC=1 without owner phrase
# ROUTE_TRAFFIC=0 bash infra/gcp/deploy_cloud_run.sh
```

### 6.12 Branch + PR workflow

```bash
cd ~/Sapphire
git checkout main && git pull --ff-only
git checkout -b cloudshell/$(date +%Y%m%d)-data-plane-hygiene
# edit explicit files …
git add path/to/file1 path/to/file2
git commit -m "fix(gcp): cloudshell data-plane hygiene [2026-08-06]"
git push -u origin HEAD
gh pr create --fill
```

### 6.13 Bridge export template

```bash
STAMP=$(date -u +%Y-%m-%d)
NOTE="data/grok-web-exports/${STAMP}_cloudshell-session.md"
cat > "$NOTE" <<EOF
---
source: cloud-shell
date: ${STAMP}
type: session-note
topics: [gcp, data-plane, handoff]
---

# Cloud Shell session — ${STAMP}

## Inventory summary
- Project: tho-ai-agent
- BQ freshness: …
- Cloud Run: …
- Vertex: idle / …
- Cost notes: …

## Changes pushed
- PRs: …

## Plant follow-ups
- …
EOF
git add "$NOTE"
git commit -m "web-export: cloudshell session notes [${STAMP}]"
git push origin main   # or via PR if policy requires
```

---

## 7) Verification checklist (end of each Cloud Shell day)

Print this and tick:

- [ ] `gcloud config get-value project` is intentional (`tho-ai-agent` vs `sapphire-479610`)  
- [ ] No secret values in shell history / committed files  
- [ ] No live trades / Telegram sends attempted  
- [ ] BQ `__TABLES__` freshness recorded  
- [ ] GCS `raw/` newest objects recorded  
- [ ] Cloud Run traffic not shifted unexpectedly  
- [ ] Vertex still no surprise always-on endpoints  
- [ ] Cost posture skimmed (no surprise min-instances / error storms)  
- [ ] Any code changes are on a branch/PR with explicit `git add` paths  
- [ ] Session note pushed to `data/grok-web-exports/` for densify  
- [ ] Plant follow-ups listed (MOSS, Win, dust fills, gcp_sync) without pretending they are done  

---

## 8) Full masterplan arc (context — not all Cloud Shell)

Compressed from plant handoffs + alpha ledger + SYSTEM_UPGRADE_PLAN history:

| Arc | Intent | Cloud Shell share |
|---|---|---|
| **Windows private DC** | Always-on harnesses, research worker, GPU, designated-rail workers | Specs/PRs only — plant ARMs |
| Multi-tier inference | Win GPU → Pi → Mac → Kimi cloud | Docs / inventory only |
| Free-reign multi-rail | Designated wallets + caps + dens | Policy docs/tests; no broker |
| AXTI options-first | Defined risk, gamma scale-out, TP/SL automation | Paper risk code |
| Chassis + fund-factory | Keep chassis; rebuild trading brain; paper rails | Code PRs |
| Knowledge bridge | Grok web ↔ git ↔ densify | **Primary** Cloud Shell write path |
| Data warehouse | BQ + GCS + Pub/Sub + GCF | **Primary** GCP work |
| Vertex complement | Batch OODA / evals / retrieval | Gated ladder |
| Public Mission Control | sapphirealpha.xyz read-only | Attended deploy |
| THO | Separate client on texashomeoutlet.com | **Fence** — no bulk fleet work |
| Telegram Central Terminal | Away desk UX | Plant deploy only |
| Win fleet recovery | Post-boot before ARM | Plant only |

Historical website R3 / Jul LIVE-STATE cutover phrases: treat as **historical** until re-verified from plant ops-state. Do not assume an unconsumed phrase is still live authority.

---

## 9) What “holistic improvement” means this week

Priority order if time is limited:

1. **See** — inventory + freshness + cost (Phase A–C).  
2. **Harden data plane** — schema/bootstrap/GCF/SQL (Phase B).  
3. **Ship paper/docs/PRs** that encode AXTI + dens + free-reign fences (Phase D).  
4. **Bridge** every session note so the plant densifies when you return.  
5. **Do not** burn time on orphan DNS, THO money paths, or Vertex endpoints.

---

## 10) Reference index (open these in order)

| Priority | Path |
|---|---|
| 1 | This file |
| 2 | `scripts/ops/gcp_cloudshell_bootstrap.sh` |
| 3 | `docs/alpha/GROK-CHAT-ALPHA-2026-08-06.md` |
| 4 | `data/grok-web-exports/2026-08-05_master-handoff-claude-opus.md` |
| 5 | `docs/gcp-data-engineering.md` |
| 6 | `docs/ops/gcp-pipeline-runbook.md` |
| 7 | `docs/ops/gcp-vertex-ai-complement-plan.md` |
| 8 | `docs/ops/google-production-testing-runbook.md` |
| 9 | `docs/DNS_SETUP.md` |
| 10 | `data/grok-web-exports/2026-08-05_alpha-learnings-axti-l2.md` |
| 11 | `data/grok-web-exports/2026-08-05_fleet-win-recovery-handoff.md` |
| 12 | `data/grok-web-exports/2026-08-05_repo-consolidation.md` |
| 13 | `infra/gcp/*` bootstrap + schemas + SQL |
| 14 | `CLAUDE.md` / `AGENTS.md` monorepo map |

---

## 11) Cloud Shell survival notes

- Home disk is **ephemeral** — push branches / web-exports often.  
- Persist via git, not only `~/` scratch.  
- Prefer `tmux` for long inventories.  
- If `gh` auth fails, use HTTPS with a short-lived PAT in env — never commit it.  
- Python deps: use repo `venv` or Cloud Shell pip user installs; prefer stdlib + already-vendored scripts.  
- `gcloud` may prompt re-auth after idle; re-run bootstrap after re-auth.

---

## 12) First 20 minutes on Cloud Shell (strict)

1. Auth + `project=tho-ai-agent`.  
2. Clone/pull Sapphire.  
3. `bash scripts/ops/gcp_cloudshell_bootstrap.sh`.  
4. Read this handoff §1 fences + §4 NOW board.  
5. Run BQ freshness + Cloud Run list + Vertex idle.  
6. Write `data/grok-web-exports/$(date -u +%Y-%m-%d)_cloudshell-day0-inventory.md`.  
7. Pick **one** Phase B or D task; open a branch; no money paths.  
8. End with verification checklist §7.

---

**End of handoff.** When in doubt: inventory, document, PR — never trade, never send, never cut over.
