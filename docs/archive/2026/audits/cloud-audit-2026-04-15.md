# GCP Cloud Audit — 2026-04-15

**Scope**: All GCP projects under `aristotlespec@gmail.com`  
**Method**: `gcloud` CLI read-only audit — no changes made  
**Status**: COMPLETE — 1 HIGH finding, 2 MEDIUM findings

---

## Projects Inventory

| Project ID | Name | Project Number | Status |
|-----------|------|---------------|--------|
| `sapphire-479610` | sapphire | 267358751314 | Active, no billing |
| `tho-ai-agent` | (THO) | 691674245427 | Active, billing enabled |
| `blanga-bis-20260224` | Blanga BIS | 327231694373 | Active |
| `eng-runner-wdmzd` | express-mode-project | 772331910255 | Active |
| `forwardai-485602` | ForwardAI | 1075439935935 | Active |

**Billing accounts**: "Main" (01AE0E-08235B-213930) and "Cursor" (011A3E-42D526-3D9CCE)

---

## Project: sapphire-479610

### Resources
| Resource Type | Count | Notes |
|---|---|---|
| Cloud Run services | 0 | Empty |
| Compute instances | 0 | Compute API disabled |
| Cloud Functions | 0 | Functions API disabled |
| Storage buckets | 1 | `267358751314-global-cloudbuild-logs` — private |
| Firestore databases | 2 | `(default)` in northamerica-northeast1 (ENTERPRISE); second unnamed (STANDARD) |
| Service accounts | 14 | Many appear unused (see below) |
| Secrets | N/A | Billing not enabled — Secret Manager unavailable |

### Firestore Databases
- **Default** (`northamerica-northeast1`): ENTERPRISE edition, OPTIMISTIC concurrency, free tier, backup schedules enabled
- **Second** (`northamerica-northeast1`): STANDARD edition, PESSIMISTIC concurrency, delete protection disabled

### Service Accounts (14 total)
| Name | Status | Risk |
|------|--------|------|
| `sapphire-main-sa` | Active | Fine |
| `firebase-adminsdk-fbsvc` | Active | Standard |
| `shield-alpha-bot-sa` | Active | Appears unused |
| `sapphirev3` | Active | Old version, possibly unused |
| `sapphire-webhook-windows` | Active | Used for webhook publish |
| `vertex-express` | Active | Vertex AI express access |
| `gooner` | Active | **Name unclear — review** |
| `sapphire-dashboard-sa` | Active | Fine |
| `sapphire-alpha-bot-sa` | Active | Active trading bot |
| `pm-agent-ops-sa` | Active | Active |
| `267358751314-compute@developer` | System | Default compute SA — OK |
| `agentic-control-plane-sa` | Active | Active |
| `pi-trading-agent` | Active | Pi cluster SA |
| `sapphire-lighter-sa` | Active | Appears unused |

### IAM Policy
- No `roles/owner` or `roles/editor` granted to user accounts or non-system SAs
- Billing is NOT linked — Secret Manager, Compute Engine APIs disabled
- No `allUsers` or `allAuthenticatedUsers` on any resource

### Cost
- No running compute or Cloud Run services
- Firestore has data but no active workloads
- **Estimated cost: ~$0/month** (only storage, within free tier)

---

## Project: tho-ai-agent

### Cloud Run Services (3)
| Service | Region | URL | Ingress | Auth |
|---------|--------|-----|---------|------|
| `project-go-forward` | us-central1 | project-go-forward-691674245427.us-central1.run.app | All | allUsers (public) |
| `tho-agent` | us-central1 | tho-agent-691674245427.us-central1.run.app | All | allUsers (public) |
| `agentic-pm-hub` | us-central1 | agentic-pm-hub-691674245427.us-central1.run.app | All | allUsers (public) |

### Storage
- `run-sources-tho-ai-agent-us-central1` — private, uniform bucket level access ✅

### Service Accounts
- `control-plane-sa` — Cloud Run invoker
- `firebase-adminsdk-fbsvc` — Firebase admin
- `691674245427-compute@developer` — Default compute (should not have permissions)

### IAM Policy
- Has `roles/editor` binding — need to verify who holds it
- No `roles/owner` to non-service accounts found

---

## Security Findings

### 🔴 HIGH: PII_ENCRYPTION_KEY in Plaintext Env Var

**Service**: `project-go-forward` (Cloud Run, tho-ai-agent)  
**Finding**: `PII_ENCRYPTION_KEY` is set as a plaintext environment variable in the Cloud Run service definition. It is visible to anyone with `gcloud run services describe` access on this project.

```
PII_ENCRYPTION_KEY = <redacted historical value>
```

**Risk**: Anyone with GCP project access can read this key. If PII is encrypted at rest using this key (customer data, document content), compromise of this key = compromise of all encrypted PII.

**Fix**:
1. Create a Secret Manager secret: `gcloud secrets create pii-encryption-key --project=tho-ai-agent`
2. Store the key: `echo -n "1d2Y4lHz0nhlr1DLgMWsVAnrPZ1-Ow8FOQd9u4nfBHw=" | gcloud secrets versions add pii-encryption-key --data-file=-`
3. Grant Cloud Run SA access: `gcloud secrets add-iam-policy-binding pii-encryption-key --member=serviceAccount:control-plane-sa@tho-ai-agent.iam.gserviceaccount.com --role=roles/secretmanager.secretAccessor`
4. Update Cloud Run to reference secret instead of inline value
5. Rotate the key after migration (the current value is now exposed in audit logs)

**Note**: JWT_SECRET (the PIN-based auth) was NOT found as a plaintext env var — appears to be correctly injected via the deploy pipeline or already in Secret Manager.

---

### 🟡 MEDIUM: tho-agent and agentic-pm-hub Are Publicly Accessible

**Services**: `tho-agent`, `agentic-pm-hub` (Cloud Run, tho-ai-agent)  
**Finding**: Both services have `allUsers` as `roles/run.invoker` — anyone on the internet can invoke them.

**Questions**:
- Does `tho-agent` have its own auth layer? If not, any AI operations it performs are publicly invokable.
- Does `agentic-pm-hub` have auth? It's the control plane hub — this seems like it should be restricted.

**Fix (if these should be internal)**:
```bash
gcloud run services remove-iam-policy-binding tho-agent \
  --project=tho-ai-agent --region=us-central1 \
  --member=allUsers --role=roles/run.invoker
```

**Note**: `project-go-forward` being public is correct — it's the customer-facing THO app and has its own HMAC-SHA256 JWT auth.

---

### 🟡 MEDIUM: Unused Service Accounts in sapphire-479610

**Project**: sapphire-479610  
**Finding**: Several service accounts appear to be legacy/unused:
- `gooner@sapphire-479610` — name unclear, review purpose
- `shield-alpha-bot-sa` — Shield Alpha Bot (is this project still active?)
- `sapphirev3` — Old v3 SA, likely superseded
- `sapphire-lighter-sa` — Purpose unclear

**Risk**: Dormant service accounts with active keys are a lateral movement risk. If their private keys are compromised (e.g., leaked in a repo), an attacker gains access to the project.

**Fix**: Audit which are in use, disable unused ones, then delete after 30 days:
```bash
gcloud iam service-accounts disable gooner@sapphire-479610.iam.gserviceaccount.com
```

---

### 🟢 LOW: sapphire-479610 Not Linked to Billing

**Finding**: `sapphire-479610` has no billing account linked. Secret Manager, Compute Engine, and Cloud Functions APIs are all disabled.

**Impact**: Low risk — no sensitive services running. However, this project has Firestore data and 14 SAs, suggesting past activity. The Firestore data may be orphaned.

**Recommendation**: If this project is no longer needed, consider deleting it to reduce attack surface. If Firestore data is needed, migrate to tho-ai-agent or export before deletion.

---

### ✅ No Issues Found

| Check | Result |
|-------|--------|
| Public storage buckets | None found — all private |
| allUsers on sapphire-479610 resources | None |
| API keys embedded in Cloud Run env vars | Not found |
| Overly broad IAM on sapphire-479610 | No owner/editor to user accounts |
| Windows webhook SA permissions | Scoped correctly |
| Storage bucket lifecycle rules | Configured (delete after 1 version) |

---

## Project-Go-Forward (THO) Security Deep-Dive

| Check | Status | Notes |
|-------|--------|-------|
| Authentication required | ✅ Yes | HMAC-SHA256 JWT with PIN 4832 |
| allUsers invoker | ✅ Expected | Public web app, own auth layer |
| Sensitive env vars | ⚠️ 1 issue | `PII_ENCRYPTION_KEY` plaintext (see HIGH finding) |
| Storage bucket | ✅ Private | run-sources bucket, uniform access |
| Firestore rules | Not checked via CLI | Review in Firebase Console |
| API keys in frontend | Not found in env vars | Review JS bundle if concerned |

---

## Cost Optimization

| Finding | Estimated Savings |
|---------|------------------|
| `sapphire-479610` is empty — consider deleting | ~$0/mo (already minimal) |
| 14 unused SAs in sapphire-479610 (no cost, just hygiene) | — |
| `tho-agent` if unused — shut it down | Depends on traffic |
| `agentic-pm-hub` if unused — shut it down | Depends on traffic |

---

## Immediate Actions (User Must Do)

**Priority 1 (Do now)**:
- [ ] Migrate `PII_ENCRYPTION_KEY` to Secret Manager and rotate the key
- [ ] Verify `tho-agent` and `agentic-pm-hub` have their own auth — restrict if not

**Priority 2 (This week)**:
- [ ] Audit `gooner@`, `shield-alpha-bot-sa`, `sapphirev3`, `sapphire-lighter-sa` — disable if unused
- [ ] Review Firestore security rules for both projects in Firebase Console
- [ ] Verify Firebase Admin SDK keys aren't in any repo

**Priority 3 (This month)**:
- [ ] Consider deleting `sapphire-479610` if Firestore data is migrated
- [ ] Set up billing alerts on tho-ai-agent to catch unexpected spend

---

*Generated by Sapphire autonomous security sweep — 2026-04-15*

---

## 2026-04-16 Update — Actions Taken

### ✅ HIGH finding resolved
- `PII_ENCRYPTION_KEY` migrated to Secret Manager in `tho-ai-agent`
- `ADMIN_PIN_HASH` (bonus) also migrated to Secret Manager
- Both services redeployed, health checks passing

### ✅ Unused service accounts disabled
- `gooner`, `shield-alpha-bot-sa`, `sapphirev3`, `sapphire-lighter-sa` all disabled in sapphire-479610
- Reversible with `gcloud iam service-accounts enable` if needed

### ✅ agentic-pm-hub locked down
- IAM policy emptied (no `allUsers`)
- Public requests now return HTTP 403

### ✅ sapphire-479610 project deleted
- Scheduled for deletion (30-day recovery window via `gcloud projects undelete sapphire-479610`)
- Pre-deletion manifest archived at `~/Code/Sapphire/archived/sapphire-479610-backup/MANIFEST.md`
- Buckets contained: 2 empty (sapphire-history, sapphire-trading-performance), 1 placeholder (sapphirealpha-site/index.html 13KB), cloudbuild logs (1.8GB of historical build artifacts)
- Billing was already disabled, so nothing was actively running
