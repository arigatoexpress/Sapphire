# 07 - Roadmap

Main today contains four buyer-relevant product surfaces: the local dashboard and runtime, Foundry SDK 0.1.0, Risk Kernel 0.1.0, and Provenance Envelopes 0.1.0. The dashboard and runtime are implemented in `/Users/aribs/Code/Sapphire/services/dashboard/app.py`, `/Users/aribs/Code/Sapphire/services/inference-proxy/app.py`, and `/Users/aribs/Code/Sapphire/infra/launchagents/`. The Foundry SDK is documented in `/Users/aribs/Code/Sapphire/docs/foundry-sdk-0.1.0.md` and implemented under `/Users/aribs/Code/Sapphire/lib/foundry/`. Risk and provenance are documented in `/Users/aribs/Code/Sapphire/docs/products/risk-kernel-0.1.0.md` and `/Users/aribs/Code/Sapphire/docs/products/provenance-envelopes-0.1.0.md`.

In flight after this packet are the remaining Wave 4 and Wave 5 items that should not be claimed as shipped: Vertex evals, BigQuery vector retrieval, Telegram operator console hardening, threat-intel-as-product, customer dossier, and Hyperliquid signal subscription. Planning evidence exists in `/Users/aribs/Code/Sapphire/docs/ops/gcp-vertex-ai-complement-plan.md`, `/Users/aribs/Code/Sapphire/docs/ops/google-benefits-utilization-plan.md`, `/Users/aribs/Code/Sapphire/lib/autonomy/continuous_intelligence.py`, and internal plugin tools under `/Users/aribs/Code/Sapphire/plugins/claw-sapphire/tools/internal/`.

Thirty days: turn shipped safety into sales motion. The 30-day plan is to harden package boundaries for Risk Kernel and Provenance, add docs examples for three buyer personas, add a dashboard read-only risk verdict explorer, and make the OODA daily delta panel screenshot-ready. Revenue tie: these are separately demoable components. Retention tie: they make ongoing operator use easier. Risk-reduction tie: docs and tests make the safety claims less dependent on Ari's memory.

Sixty days: move the best artifact lanes into repeatable customer pilots. That means threat intel as a product surface, customer dossier generation, and Foundry synchronization with clear dry-run/apply gates. The source paths are already present: `/Users/aribs/Code/Sapphire/plugins/claw-sapphire/tools/internal/threat_intel.py`, `/Users/aribs/Code/Sapphire/lib/foundry/sync.py`, `/Users/aribs/Code/Sapphire/docs/foundry-ontology-schema.md`, and `/Users/aribs/Code/Sapphire/docs/palantir-foundry-strategy-2026-04-19.md`. Revenue tie: customer-facing intelligence packets. Retention tie: recurring dossier updates. Risk-reduction tie: provenance and Foundry schemas prevent untraceable output.

Ninety days: prove cloud complement without surrendering cost control. Build the Vertex eval harness and BigQuery retrieval layer described in `/Users/aribs/Code/Sapphire/docs/ops/gcp-vertex-ai-complement-plan.md`, keeping local artifacts first and BigQuery summaries only after review. Revenue tie: scalable research/eval workflows. Retention tie: better retrieval and model quality. Risk-reduction tie: fixed eval sets before tuning/training.

One year: convert Sapphire from one-operator autonomy into a small acquired platform. That means buyer-grade packaging, reduced operator key-person risk, clearer satellite repo boundaries, and selected live operator consoles that remain read-only until a confirmation firewall approves mutation. The foundation is the control-tower model in `/Users/aribs/Code/Sapphire/docs/org/control-tower.md`, no-spend CI strategy in `/Users/aribs/Code/Sapphire/docs/org/no-spend-github-actions-strategy.md`, and routine migration process in `/Users/aribs/Code/Sapphire/scripts/ops/routine_soak_status.py`.

The roadmap is deliberately conservative about live trading. Hyperliquid and Robinhood surfaces should continue as read-only, paper, or order-draft flows until the Risk Kernel, confirmation firewall, and kill-switch contracts are wired end-to-end into every mutation path. That posture reduces near-term "wow" but increases acquisition quality: buyers can diligence a system that knows the difference between insight, recommendation, draft, and action.

## Diligence Readout

The roadmap should be judged by whether each item improves revenue, retention, or risk reduction. Risk Kernel packaging improves revenue because it can be sold as a standalone safety component; it improves risk reduction because it forces policy-by-policy verdicts. Provenance improves revenue because it lets artifacts move into buyer systems; it improves retention because trustable outputs become recurring. Gemini OODA daily improves retention because the system keeps producing inspectable deltas without paid calls.

The 30-day plan is mostly packaging, not invention. That is good. Buyers do not need a bigger idea every week; they need a reliable demo, clean docs, and fewer hidden assumptions. The 60-day plan turns existing threat, Foundry, and dossier code into customer-shaped artifacts. The 90-day plan puts evaluation and retrieval under measurable controls. The one-year plan reduces Ari key-person risk by creating ownership boundaries and deciding which mutation paths should exist at all.

The roadmap's biggest trap is live trading glamour. It is tempting to claim the value of Sapphire is autonomous execution. The better claim is autonomous diligence: find opportunities, explain risks, draft actions, require confirmation, and emit evidence. Live execution may come later, but it should be the last mile of a safety platform, not the first proof point. That framing is more likely to survive legal, security, and corp-dev review.

The acquisition-specific recommendation is to keep the next two quarters focused on buyer-demo surfaces: risk verdict explorer, provenance verifier UI, Foundry sync demo, threat-intel packet, and Gemini OODA daily screenshot. Those are the surfaces a colleague can understand without knowing Ari's entire workstation.

Prioritization should be ruthless. If an item does not make Sapphire easier to buy, easier to operate, or safer to run, it should wait. That means more docs and verification before more model novelty, more read-only panels before mutation, and more packaging before new surface area. The first tranche made the repo safe and clean; this tranche makes it explainable. The next tranche should make it repeatable by someone other than Ari.

The roadmap should also keep a "no claim before proof" rule. Vertex evals are not shipped until tests and artifacts exist. BigQuery retrieval is not shipped until a queryable table and retention plan exist. Telegram hardening is not shipped until the operator console can prove no send occurs without confirmation. That discipline protects buyer trust.

## Evidence

- `/Users/aribs/Code/Sapphire/docs/products/risk-kernel-0.1.0.md`
- `/Users/aribs/Code/Sapphire/docs/products/provenance-envelopes-0.1.0.md`
- `/Users/aribs/Code/Sapphire/docs/ops/gcp-vertex-ai-complement-plan.md`
- `/Users/aribs/Code/Sapphire/docs/org/control-tower.md`
- `/Users/aribs/Code/Sapphire/lib/autonomy/continuous_intelligence.py`
