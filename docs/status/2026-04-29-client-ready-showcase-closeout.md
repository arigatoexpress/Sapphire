# Client-Ready Showcase Closeout — 2026-04-29

Status window: 2026-04-29 MDT / 2026-04-30 UTC.

This closeout records the safe production-readiness and showcase work completed
after the Windows machine came back online. It is intentionally paste-safe:
no secret payloads, plaintext PINs, live trading toggles, or Telegram sends are
included.

## Shipped PRs

| Repo | PR | Result |
|---|---:|---|
| Project-Go-Forward | #32 | `/healthz` now reports email readiness, document output directories are created before writes, and production docs were updated. |
| regional-intel-workbench | #13 | README/showcase demo commands now use `uv run`, demo-safe read-only surfaces are documented, and client-view/OODA tests were hardened. |
| Sapphire | #495 | Frontend endpoint drift guard now resolves the real repo root and fails on missing scan roots. |
| Sapphire | #496 | Unified dashboard metrics now derive from live Flask routes, tool-registry validation, readiness sweep output, and satellite list length. |
| Sapphire | #497 | Unified dashboard satellite cards now use paste-safe metadata from `infra/org-repos.yaml`. |

## Production UAT

THO production at `https://sapphirealpha.xyz` passed a read-only browser and API
boundary pass:

| Surface | Result |
|---|---|
| `/` | HTTP 200, title `Browse Homes | Texas Home Outlet` |
| `/documents` | HTTP 200, title `Documents | Texas Home Outlet` |
| `/studio` | HTTP 200, title `Ad Studio | Texas Home Outlet` |
| `/crm` | HTTP 200, title `CRM Dashboard | Texas Home Outlet` |
| `/analytics` | HTTP 200, title `Analytics | Texas Home Outlet` |
| `/api/inventory` | HTTP 401, admin authentication required |
| `/api/deals` | HTTP 401, admin authentication required |
| `/api/leads` | HTTP 401, admin authentication required |

The production smoke script also passed `11/11`, and fresh Cloud Run ERROR logs
for `project-go-forward` were empty after the deploy window.

Current `/healthz/` posture:

```text
status=ok
sha=970cb931dfacc421081c670af120786f5a166310
dependencies=db:configured,drive:configured,secrets:configured,email:missing
warnings=email_not_configured
```

The email warning is expected until a real Resend key is created and bound.

## Screenshot Pack

Real screenshots are intentionally kept out of git per
`docs/diligence/screenshots/README.md`. The current local capture bundle is:

```text
/Users/aribs/Code/Sapphire/output/playwright/client-ready-2026-04-29/
```

Captured files:

| File | Surface |
|---|---|
| `tho-home.png` | THO production inventory home |
| `tho-home-mobile.png` | THO production inventory home, mobile viewport |
| `tho-documents.png` | THO production Document Center |
| `regional-intel-console.png` | Local Regional Intel analyst console |
| `regional-blanga-austin.png` | Local Blanga Austin client feed |
| `sapphire-unified-dashboard.png` | Local authenticated Sapphire unified dashboard |

Note: the local Sapphire screenshot was captured from a test dashboard on port
`18080`. The local no-external readiness metric in that screenshot can show a
dashboard-auth mismatch because the sweep probes the canonical dashboard on
port `8080`. Canonical Sapphire readiness was separately verified at `0 FAIL`.

## Verification

| Repo | Command | Result |
|---|---|---|
| Project-Go-Forward | `python3 scripts/production_smoke.py --base-url https://sapphirealpha.xyz` | `ok=true`, `11` probes |
| Project-Go-Forward | Cloud Run ERROR log query after deploy | `[]` |
| regional-intel-workbench | `uv run --no-project --python 3.11 --with-editable . python -m unittest discover -s tests -v` | `37` tests OK |
| Sapphire | `AUTH_PASSWORD=test-password X402_ENABLED=0 PYTHONDONTWRITEBYTECODE=1 /usr/local/bin/python3 -m pytest tests/unit/test_dashboard_showcase_routes.py tests/unit/test_dashboard_public_demo_readiness.py -q` | `25` passed |
| Sapphire | `bash scripts/ops/check_frontend_endpoint_drift.sh` | passed |
| Sapphire | `/usr/local/bin/python3 scripts/ops/production_readiness_sweep.py --no-external --format json` | `0` fail, `45` pass, `7` warn, `2` skip |

## Remaining Operator Item

Transactional email is the only known live THO health warning. Secret Manager
does not currently expose a `resend-api-key` secret, and Cloud Run is not bound
to `RESEND_API_KEY`.

Safe operator flow:

```bash
THO_PROJECT=tho-ai-agent
THO_REGION=us-central1
THO_SERVICE=project-go-forward

printf '%s' "$RESEND_API_KEY" | gcloud secrets create resend-api-key \
  --project "$THO_PROJECT" \
  --replication-policy=automatic \
  --data-file=-

gcloud run services update "$THO_SERVICE" \
  --project "$THO_PROJECT" \
  --region "$THO_REGION" \
  --update-secrets=RESEND_API_KEY=resend-api-key:latest

curl -fsS https://sapphirealpha.xyz/healthz/ | python3 -m json.tool
python3 scripts/production_smoke.py --base-url https://sapphirealpha.xyz
```

If the secret already exists in a future run, use
`gcloud secrets versions add resend-api-key --data-file=-` instead of
`gcloud secrets create`.

## Draft PR Triage

Sapphire PR #469 remains the only open PR, and it should not be merged as-is.
It is a draft with `224` changed files (`+4125/-2275`), mostly formatter churn,
and has failing `pytest` plus test-inventory checks. The safe path is to split
any still-useful fixes into focused branches, account for the deflated Sharpe
and inventory failures separately, then close or regenerate the broad draft.

## Current Clean State

| Repo | State |
|---|---|
| Sapphire | clean on `origin/main` |
| Project-Go-Forward | clean on `origin/main` |
| regional-intel-workbench | clean on `origin/main` |

Active Sapphire worktrees are the canonical checkout plus the pre-existing
`.claude` worktrees. No real trading, live Telegram sends, secret reads,
permission broadening, or destructive infrastructure changes were performed.
