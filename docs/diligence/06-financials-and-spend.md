# 06 - Financials And Spend

Sapphire's repo-side spend posture is no-spend by default. That is not the same as zero possible spend; it means automation does not assume permission to consume paid services. The controlling evidence is `/Users/aribs/Code/Sapphire/scripts/ops/local_ci_verify.py`, `/Users/aribs/Code/Sapphire/.github/workflows/`, `/Users/aribs/Code/Sapphire/docs/org/no-spend-github-actions-strategy.md`, `/Users/aribs/Code/Sapphire/docs/ops/google-production-testing-runbook.md`, and `/Users/aribs/Code/Sapphire/docs/ops/google-benefits-utilization-plan.md`.

Provider monthly spend should be read as follows:

| Provider | Current Diligence Number | Confidence | Evidence / Control |
|---|---:|---|---|
| GitHub Actions hosted runners | $0 intended | High | `[skip ci]` commits and `/Users/aribs/Code/Sapphire/scripts/ops/local_ci_verify.py` |
| Gemini daily OODA | $0 | High | `/Users/aribs/Code/Sapphire/scripts/ops/gemini_ooda_daily.sh` forces `SAPPHIRE_GEMINI_LIVE=0` |
| Vertex AI endpoints | $0 observed from readiness inventory | Medium | `/Users/aribs/Code/Sapphire/docs/ops/gcp-vertex-ai-complement-plan.md` says no endpoints/jobs listed in inventory |
| GCP data plane | Estimated, operator billing required | Medium | `/Users/aribs/Code/Sapphire/scripts/ops/cost_posture_report.py` and `/Users/aribs/Code/Sapphire/scripts/ops/gcp_ai_inventory.py` are read-only |
| Moonshot/Kimi | Estimated, key rotation still owed | Low | `/Users/aribs/Code/Sapphire/docs/security/credential-rotation-runbook.md` |
| Anthropic | Estimated, external account | Low | `/Users/aribs/Code/Sapphire/docs/security/credential-rotation-runbook.md` |
| OpenAI | Estimated or absent | Low | `/Users/aribs/Code/Sapphire/docs/security/credential-rotation-runbook.md` lists key path only when present |
| Foundry | Estimated, integration not fully successful | Low | `/Users/aribs/Code/Sapphire/lib/foundry/sync.py`, `/Users/aribs/Code/Sapphire/docs/foundry-sdk-0.1.0.md` |

The exact dollar amounts for Anthropic, Moonshot/Kimi, OpenAI, GCP, and Foundry are intentionally not invented here. They live in provider billing dashboards and local secret/account state, not in the repo. The repo provides controls to keep those bills bounded: local CI instead of hosted CI, local inference before cloud fallback, no Vertex endpoint deployments by default, dry-run Gemini OODA by default, and explicit manual gates before GCP/BigQuery/GCS writes.

Cost-cap mechanisms are concrete. The Gemini OODA tool at `/Users/aribs/Code/Sapphire/plugins/claw-sapphire/tools/internal/gemini_ooda.py` enforces `MAX_CALLS_PER_HOUR = 8` and `MAX_TOKENS_PER_MONTH = 500_000`, refuses live calls unless `SAPPHIRE_GEMINI_LIVE=1`, and falls back to dry-run for sensitivity, missing key, rate-limit, or live SDK errors. The daily LaunchAgent at `/Users/aribs/Code/Sapphire/infra/launchagents/com.sapphire.gemini-ooda-daily.plist` and wrapper at `/Users/aribs/Code/Sapphire/scripts/ops/gemini_ooda_daily.sh` set the live flag to zero.

Inference spend is bounded by routing. `/Users/aribs/Code/Sapphire/services/inference-proxy/app.py` uses local tiers first, denies over-quota requests, caps max tokens per request, and exposes quota/cache introspection. Kimi Cloud is a fallback, not the first call, and the code avoids cloud fallback for sensitive prompts when local tiers are exhausted. That is the difference between "cheap until it breaks" and an actual cost-control surface.

GCP/Vertex spend is controlled by process. `/Users/aribs/Code/Sapphire/docs/ops/google-production-testing-runbook.md` forbids live Gemini/Vertex calls, BigQuery/GCS writes, training/tuning, endpoints, and Veo generation without manual gate, budget cap, sample cap, output path, rollback, and retention plan. `/Users/aribs/Code/Sapphire/scripts/ops/gcp_ai_inventory.py` is read-only and recommends BigQuery retrieval before dedicated vector infra and batch/evals before training.

The acquirer should therefore underwrite Sapphire as a low fixed-cost system with potentially valuable optional spend lanes. The recurring cost base is operator hardware, local electricity, existing subscriptions, and any manually approved provider usage. The risk is not hidden cloud burn; the risk is that exact external spend must be confirmed in billing dashboards during diligence.

## Diligence Readout

The right way to diligence Sapphire spend is to separate code-enforced spend controls from account-level bills. The repo can prove it avoids hosted CI, defaults Gemini OODA to dry-run, routes local inference first, and keeps GCP/Vertex write paths behind manual gates. It cannot prove Ari's external subscription invoices without billing dashboard exports. This packet therefore gives estimated or control-based numbers rather than pretending to know account statements.

For Palantir, the spend-relevant upside is that Sapphire already thinks in governed artifacts and Foundry-style synchronization rather than high-volume model calls. Provenance, local CI, and readiness sweeps are cheap. Foundry or BigQuery costs would appear only when summaries and datasets are promoted. For Robinhood, the relevant upside is that trading intelligence can remain read-only or paper for a long time while still producing value through risk dashboards, market universe analysis, and order-draft controls.

The main financial risk is cloud enthusiasm after acquisition. A buyer could accidentally ruin Sapphire's economics by deploying always-on Vertex endpoints, running unmanaged vector search, or turning every OODA packet into a live model call. The repo's own docs recommend the opposite: batch before endpoint, BigQuery retrieval before dedicated vector infrastructure, evals before tuning, and explicit budget caps before any live experiment. Those recommendations should become policy, not just docs.

The second risk is historical key rotation. If exposed Moonshot/Kimi credentials are still live, spend and account-abuse risk persist outside the repo. That is why this packet keeps the incident open. A buyer should make rotation evidence part of the diligence close checklist, alongside local CI reports and readiness sweeps.

The spend upside is that many buyer-visible improvements are not expensive: documentation, provenance verification, risk verdict UI, readiness snapshots, and Foundry schema hardening are mostly engineering time. The expensive work - live model calls, cloud retrieval, endpoints, and training - is specifically deferred until there is a budget and quality reason. That sequencing is rare and valuable.

The diligence request to Ari should be simple: export provider billing summaries for the last 90 days, redact account identifiers, and compare them against the repo's expected no-spend posture. Any unexplained provider line becomes a follow-up.

## Evidence

- `/Users/aribs/Code/Sapphire/scripts/ops/local_ci_verify.py`
- `/Users/aribs/Code/Sapphire/plugins/claw-sapphire/tools/internal/gemini_ooda.py`
- `/Users/aribs/Code/Sapphire/services/inference-proxy/app.py`
- `/Users/aribs/Code/Sapphire/docs/ops/google-production-testing-runbook.md`
- `/Users/aribs/Code/Sapphire/scripts/ops/cost_posture_report.py`
