# 00 - Executive Summary

**Value proposition:** Sapphire is a production-graded autonomy control plane that turns one operator, local compute, and strict safety gates into an auditable intelligence, trading, and operations system that an acquirer can inspect before it is allowed to act.

Sapphire matters because it is not a chatbot wrapped around a dashboard. It is a continuously running operating system for intelligence work, risk-gated trading research, inference routing, content generation, security monitoring, and operator routines. The control plane is implemented in the repo at `/Users/aribs/Code/Sapphire`, with the architecture summarized in `/Users/aribs/Code/Sapphire/README.md`, the event spine in `/Users/aribs/Code/Sapphire/lib/core/event_bus.py`, the dashboard in `/Users/aribs/Code/Sapphire/services/dashboard/app.py`, and the production-readiness verifier in `/Users/aribs/Code/Sapphire/scripts/ops/production_readiness_sweep.py`.

The moat is the combination of safety surface plus operating cadence. The public Risk Kernel 0.1.0 at `/Users/aribs/Code/Sapphire/lib/core/risk_kernel/` exposes versioned decision envelopes and verdict trees; its product contract is documented in `/Users/aribs/Code/Sapphire/docs/products/risk-kernel-0.1.0.md`. Provenance 0.1.0 at `/Users/aribs/Code/Sapphire/lib/core/provenance.py` stamps artifacts with generator, source hashes, prompt hash, model, time, and TTL; its migration and verification paths live at `/Users/aribs/Code/Sapphire/scripts/ops/provenance_backfill.py` and `/Users/aribs/Code/Sapphire/scripts/ops/provenance_verify.py`. The bounded Gemini lane is intentionally dry-run by default in `/Users/aribs/Code/Sapphire/plugins/claw-sapphire/tools/internal/gemini_ooda.py` and now runs daily through `/Users/aribs/Code/Sapphire/infra/launchagents/com.sapphire.gemini-ooda-daily.plist`.

It runs on a Mac commander, Windows GPU tier, Raspberry Pi edge tiers, local Ollama/Mac fallback, Kimi Cloud fallback, and a bounded Gemini complement lane. The inference proxy contract is in `/Users/aribs/Code/Sapphire/services/inference-proxy/app.py`; the Google/Vertex posture is documented in `/Users/aribs/Code/Sapphire/docs/ops/gcp-vertex-ai-complement-plan.md` and `/Users/aribs/Code/Sapphire/docs/ops/google-production-testing-runbook.md`. The repo is operated no-spend by default: commits include `[skip ci]`, GitHub hosted runners are intentionally avoided, and local CI verification is the merge gate through `/Users/aribs/Code/Sapphire/scripts/ops/local_ci_verify.py`.

The cost posture is deliberately boring: use owned/local compute first, free-tier-aware cloud metadata second, and explicit budget gates before paid Gemini, Vertex, BigQuery, Foundry, Telegram, or trading mutation. Known unknowns remain documented rather than hand-waved: provider spend exacts belong in operator billing dashboards, while the repo-side control mechanisms are in `/Users/aribs/Code/Sapphire/scripts/ops/cost_posture_report.py`, `/Users/aribs/Code/Sapphire/scripts/ops/google_benefits_inventory.py`, `/Users/aribs/Code/Sapphire/docs/ops/google-benefits-utilization-plan.md`, and `/Users/aribs/Code/Sapphire/docs/security/credential-rotation-runbook.md`. The diligence thesis is simple: Sapphire is buyable because its differentiators are now separable, tested, provenance-stamped, scheduled, and documented.

## Evidence

- `/Users/aribs/Code/Sapphire/README.md`
- `/Users/aribs/Code/Sapphire/docs/products/risk-kernel-0.1.0.md`
- `/Users/aribs/Code/Sapphire/docs/products/provenance-envelopes-0.1.0.md`
- `/Users/aribs/Code/Sapphire/docs/ops/gemini-ooda-daily-runbook.md`
- `/Users/aribs/Code/Sapphire/scripts/ops/local_ci_verify.py`
