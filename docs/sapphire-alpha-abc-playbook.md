# sapphire-alpha — A/B/C decision playbook

**Background.** `sapphire-alpha` is the Cloud Run service that hosts the alpha-engine API (the Vite frontend at `VITE_ALPHA_BASE_URL` talks to it). It was originally deployed to GCP project `sapphire-479610` (project number `267358751314`), reachable at `https://sapphire-alpha-267358751314.us-central1.run.app`. During the 2026-04-18 audit it did **not** show up in the `tho-ai-agent` Cloud Run inventory — meaning the URL is either serving from a different, stale project, or the service is gone and the env var is dangling.

Three cleanup paths. Pick one and run the single command block for that path. All three are safe and reversible.

---

## Recommendation: **Path B** (retarget to `tho-ai-agent`)

One project, one billing account, one place to look when things break. Keeps the deploy script intact and just changes where it lands.

---

## Path A — Delete / decommission (shortest, most aggressive)

Use if: you don't need a separate alpha-engine Cloud Run service right now; the frontend is either not being used or can hit a different backend (e.g., local dev, `sapphire-gateway`, or `agentic-pm-hub`).

```bash
cd ~/Code/Sapphire

# 1. Tear down the old Cloud Run service (no-op if already gone)
gcloud run services delete sapphire-alpha \
    --project sapphire-479610 \
    --region us-central1 \
    --quiet || true

# 2. Remove the stale env var so nothing tries to hit the dead URL
sed -i '' '/VITE_ALPHA_BASE_URL=/d' env.example
# If you have a local .env with it, clear it too:
sed -i '' '/VITE_ALPHA_BASE_URL=/d' .env 2>/dev/null || true

# 3. Park the deploy script so nobody accidentally redeploys
git mv scripts/deploy/deploy_sapphire_alpha.sh scripts/deploy/_deprecated_deploy_sapphire_alpha.sh

# 4. Note in the deprecated-services log
echo "$(date -u +%Y-%m-%d): sapphire-alpha Cloud Run deleted — Path A (decommission)" \
    >> docs/deprecated-services.log

git add -A && git commit -m "retire sapphire-alpha Cloud Run (path A)"
```

**Rollback:** `git revert HEAD` + re-run `scripts/deploy/deploy_sapphire_alpha.sh` against whichever project you want.

---

## Path B — Retarget to `tho-ai-agent` **(recommended)**

Use if: you still want the alpha-engine API live, but want it in the same GCP project as everything else that's actively billing (`tho-ai-agent`, project number `691674245427`).

```bash
cd ~/Code/Sapphire

# 1. Make sure the target project has the same scaffolding sapphire-479610 had
gcloud config set project tho-ai-agent

# 2. Confirm Artifact Registry repo exists (create if not — one-shot)
gcloud artifacts repositories describe sapphire-repo \
    --location=northamerica-northeast1 \
    --project=tho-ai-agent >/dev/null 2>&1 \
  || gcloud artifacts repositories create sapphire-repo \
    --repository-format=docker \
    --location=northamerica-northeast1 \
    --project=tho-ai-agent

# 3. Confirm the runtime + build service accounts exist in tho-ai-agent
#    (These are assumed by the deploy script. If they don't exist, create mirrors.)
gcloud iam service-accounts describe \
    sapphire-main-sa@tho-ai-agent.iam.gserviceaccount.com \
    --project=tho-ai-agent >/dev/null 2>&1 \
  || gcloud iam service-accounts create sapphire-main-sa \
    --project=tho-ai-agent \
    --display-name="Sapphire alpha-engine runtime"

gcloud iam service-accounts describe \
    sapphirev3@tho-ai-agent.iam.gserviceaccount.com \
    --project=tho-ai-agent >/dev/null 2>&1 \
  || gcloud iam service-accounts create sapphirev3 \
    --project=tho-ai-agent \
    --display-name="Sapphire Cloud Build runner"

# 4. Deploy — the existing script already accepts PROJECT_ID as env override
PROJECT_ID=tho-ai-agent \
  bash scripts/deploy/deploy_sapphire_alpha.sh

# 5. Capture the new URL (script prints it at the end; also:)
NEW_URL="$(gcloud run services describe sapphire-alpha \
    --project=tho-ai-agent --region=us-central1 \
    --format='value(status.url)')"
echo "NEW sapphire-alpha URL: $NEW_URL"

# 6. Update env.example to point at the new URL
sed -i '' "s|VITE_ALPHA_BASE_URL=.*|VITE_ALPHA_BASE_URL=$NEW_URL|" env.example

# 7. Smoke the deployment
curl -fsS "$NEW_URL/health" && echo " — OK"

git add env.example && git commit -m "retarget sapphire-alpha to tho-ai-agent (path B)"
```

**Rollback:** `gcloud run services delete sapphire-alpha --project=tho-ai-agent --region=us-central1` + revert the env.example commit. The old `sapphire-479610` service (if it still exists) is untouched.

**What you'll need:** billing enabled on `tho-ai-agent` (it is, $6.20 MTD); IAM roles for the two service accounts (`roles/run.invoker`, `roles/artifactregistry.writer`, etc.) — the first deploy will fail with a clear error if a role is missing, and `gcloud projects add-iam-policy-binding` fixes it in one line.

---

## Path C — Keep on `sapphire-479610`, just enable billing

Use if: you'd rather not move anything and the only reason sapphire-alpha looks dead is that billing got detached from `sapphire-479610`.

```bash
cd ~/Code/Sapphire

# 1. Check billing status on the original project
gcloud beta billing projects describe sapphire-479610

# 2. If billing is disabled (you'll see "billingEnabled: false"),
#    link it to your active billing account. Get the billing account ID first:
gcloud beta billing accounts list
# (copy the ACCOUNT_ID column value for your active account)

gcloud beta billing projects link sapphire-479610 \
    --billing-account=<BILLING_ACCOUNT_ID>

# 3. Redeploy against the original project (restores a fresh revision)
PROJECT_ID=sapphire-479610 \
  bash scripts/deploy/deploy_sapphire_alpha.sh

# 4. Smoke
curl -fsS https://sapphire-alpha-267358751314.us-central1.run.app/health && echo " — OK"
```

**Rollback:** `gcloud beta billing projects unlink sapphire-479610` (stops billing immediately; service keeps running until next charge cycle hits the limit).

**Downside of this path:** you end up with two billable GCP projects instead of one. Easy to forget about and wake up to a surprise charge.

---

## Quick decision table

| If this is true… | Pick |
|------------------|------|
| You don't need alpha-engine as a Cloud Run service right now | **A** |
| You want alpha-engine live and co-located with everything else | **B** (recommended) |
| You're attached to the current URL and just want to fix billing | **C** |

Whichever you pick, tell me which path and I'll strike it off the open-questions list and refresh the punch list.

## After picking a path

Update `docs/ari-punch-list-2026-04-18.md`:
- Remove the `sapphire-alpha` row from the priority queue.
- Remove the matching open question (question #3).
- If you went with **B**, drop the new URL in `env.example` and in any local `.env` files that override it.
- If you went with **A**, also strip `VITE_ALPHA_BASE_URL` from `services/sapphirebook/` frontend configs — grep for it: `grep -rn VITE_ALPHA_BASE_URL services/`.
