# 04 - Data And Models

Sapphire's model strategy is local-first and externally bounded. The default inference surface is `/Users/aribs/Code/Sapphire/services/inference-proxy/app.py`, which describes a four-tier failover proxy with OpenAI-compatible responses. The tiers are Windows GPU, Raspberry Pi edge nodes, Mac local fallback, and Kimi Cloud fallback. `/Users/aribs/Code/Sapphire/README.md` calls this a `4 + 1` design because Gemini OODA is a complement lane, not a default inference tier.

| Lane | Purpose | Cost Posture | Evidence |
|---|---|---|---|
| Windows GPU | Primary local model throughput | Owned hardware | `/Users/aribs/Code/Sapphire/README.md` |
| Pi tiers | Edge/local fallback and small models | Owned hardware | `/Users/aribs/Code/Sapphire/services/inference-proxy/app.py` |
| Mac local | Commander fallback | Owned hardware | `/Users/aribs/Code/Sapphire/services/inference-proxy/app.py` |
| Kimi Cloud | Last-resort external fallback | Secret-gated, sensitivity-aware | `/Users/aribs/Code/Sapphire/services/inference-proxy/app.py` |
| Gemini OODA | Structured external sanity check | Dry-run default, live manually gated | `/Users/aribs/Code/Sapphire/plugins/claw-sapphire/tools/internal/gemini_ooda.py` |

The inference proxy adds controls that matter to customers. It has per-tenant quota policy and usage accounting, max token caps, prompt-cache controls, and introspection endpoints `/v1/quota` and `/v1/cache-stats`. Those features turn a local router into a product surface: a buyer can imagine packaging inference governance separately from the rest of Sapphire.

The bounded Gemini lane is intentionally small. `/Users/aribs/Code/Sapphire/plugins/claw-sapphire/tools/internal/gemini_ooda.py` defines `MAX_CALLS_PER_HOUR = 8`, `MAX_TOKENS_PER_MONTH = 500_000`, a live gate requiring `SAPPHIRE_GEMINI_LIVE=1`, and safety fallback modes such as `dry-run-blocked-by-env`, `dry-run-safety`, `dry-run-no-key`, and `dry-run-rate-limited`. The daily cadence is now repo-backed by `/Users/aribs/Code/Sapphire/scripts/ops/gemini_ooda_daily.py`, `/Users/aribs/Code/Sapphire/scripts/ops/gemini_ooda_daily.sh`, and `/Users/aribs/Code/Sapphire/infra/launchagents/com.sapphire.gemini-ooda-daily.plist`.

Data provenance is part of the model story. `/Users/aribs/Code/Sapphire/lib/core/provenance.py` stamps payload and file artifacts with deterministic SHA-256 hashes of canonical JSON. Stamped writers include continuous intelligence artifacts, content drafts, report generation, sovereign thesis previews, Foundry sync, and Gemini OODA caches as documented in `/Users/aribs/Code/Sapphire/docs/products/provenance-envelopes-0.1.0.md`. Verification is a production-readiness check through `/Users/aribs/Code/Sapphire/scripts/ops/provenance_verify.py`.

GCP and Vertex are planned as support planes rather than command planes. `/Users/aribs/Code/Sapphire/docs/ops/gcp-vertex-ai-complement-plan.md` states that GCP and Vertex complement the local control tower and do not own trading, Telegram dispatch, Foundry writes, LaunchAgent retargeting, workflow dispatch, or secret material. `/Users/aribs/Code/Sapphire/scripts/ops/gcp_ai_inventory.py` inventories AI/data resources read-only and recommends batch Gemini OODA packets, BigQuery retrieval, Vertex eval harnesses, and only later training. `/Users/aribs/Code/Sapphire/docs/ops/google-production-testing-runbook.md` keeps live Gemini/Vertex calls, BigQuery/GCS writes, and Veo generation behind manual gates.

BigQuery vector retrieval and Vertex evals are roadmap items, not claimed shipped surfaces. The repo contains planning and inventory code for them in `/Users/aribs/Code/Sapphire/docs/ops/gcp-vertex-ai-complement-plan.md`, `/Users/aribs/Code/Sapphire/scripts/ops/gcp_ai_inventory.py`, and `/Users/aribs/Code/Sapphire/docs/ops/google-benefits-utilization-plan.md`. The diligence position is therefore conservative: Sapphire has a functioning local inference mesh, a bounded dry-run Gemini lane, and a documented path to cloud retrieval/evals, but it does not pretend unshipped Vertex/BigQuery products are already production revenue.

## Diligence Readout

The model architecture is attractive because it is economically opinionated. Sapphire does not start from the assumption that the most expensive managed model should answer everything. It routes through owned hardware and only escalates when the task, sensitivity, and budget posture allow. That matters commercially because inference cost can destroy the gross margin of an AI operations product. The proxy's quotas and cache stats are therefore not secondary features; they are unit-economics controls.

The Gemini OODA lane is the clearest example of "bounded complement." It is allowed to produce structure and second opinions, but it is not allowed to trade, send Telegram, or mutate external state. Daily dry-run cadence proves the lane runs operationally without proving a spend habit. If a buyer wants live Gemini or Vertex later, the code already contains the gates and counters needed to make that a deliberate product decision.

The data plane is similarly conservative. Foundry and BigQuery are treated as places to synchronize governed summaries, ontologies, scorecards, and retrieval tables, not raw secrets or uncontrolled prompt dumps. Provenance envelopes then let downstream consumers decide whether an artifact is fresh, who generated it, which sources were hashed, and whether the payload changed. In a diligence room, that is much easier to defend than a folder full of unexplained JSON.

The main gap is that Vertex evals and BigQuery vector retrieval are plans, not completed production systems. That is acceptable if stated plainly. The best next proof would be a fixed golden-case eval set for OODA, Telegram safety replies, trading explanations, and Foundry summaries, with local results stamped by provenance and only then promoted to BigQuery. That would turn the model story from "sensible architecture" into measurable quality governance.

During diligence, the buyer should sample three artifacts: one content or intelligence draft, one continuous-intelligence lease/snapshot, and one Gemini OODA packet. For each, the reviewer should verify the sidecar, source hashes, generated time, and TTL. That exercise tests the entire data/model thesis: generation is useful only if the artifact can be trusted later.

The buyer should also preserve model optionality. Sapphire should not become dependent on any one hosted model provider. The current tiered design lets the system swap local models, route around outages, and keep sensitive prompts away from external APIs.

## Evidence

- `/Users/aribs/Code/Sapphire/services/inference-proxy/app.py`
- `/Users/aribs/Code/Sapphire/plugins/claw-sapphire/tools/internal/gemini_ooda.py`
- `/Users/aribs/Code/Sapphire/scripts/ops/gemini_ooda_daily.py`
- `/Users/aribs/Code/Sapphire/docs/ops/gcp-vertex-ai-complement-plan.md`
- `/Users/aribs/Code/Sapphire/lib/core/provenance.py`
