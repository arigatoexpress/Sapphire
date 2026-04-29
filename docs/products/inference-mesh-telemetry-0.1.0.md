# Inference Mesh Telemetry & Cost Analysis 0.1.0

> **Status:** shipped 2026-04-29 (Tranche 6 Lane 6).
> **Audience:** institutional-diligence reviewers; SRE / SecOps; operators tuning routing policy.
> **Provenance:** every artifact emitted by this stack is wrapped in a Sapphire schema-v1 provenance envelope (`lib/core/provenance.py`).

---

## 1. Why this exists

A buyer's diligence question — *"What does it cost to run, and is it efficient?"* — is one of the five compound-edge questions Tranche 6 is built to answer. Sapphire runs a **4-tier inference mesh**:

| Tier | Hardware | Models served | Typical latency | Cost basis |
|------|----------|---------------|-----------------|------------|
| **T1 Windows GPU** | RTX 5070 Ti (16 GB VRAM, ~285 W TBP) | hermes3:8b, qwen3:14b, gemma4, deepseek-r1, qwen3.5:9b, qwen3.6:27b, qwen2.5:32b, nemotron-cascade-2 | ~0.4 s | electricity-only proxy ($0.001/inference default) |
| **T2 Pi (rari1, rari2)** | Raspberry Pi 5 cluster on Tailscale | nemotron-mini, smollm2:1.7b, qwen2.5:0.5b, gemma2:2b | ~1–3 s | negligible (~5 W ARM SBC) |
| **T3 Mac local** | M-series mini, always-on | hermes3:8b, gemma2 | ~80–95 s (CPU inference) | electricity-only proxy ($0.0008/inference default) |
| **T4 Kimi Cloud (Moonshot)** | Moonshot AI hosted | kimi-cloud (k1.5 / k2 SKUs) | ~2–3 s | per-token, operator-supplied from <https://platform.moonshot.cn/docs/pricing/chat> (retrieved 2026-04-29) |

Until this lane shipped, "How much is each tier costing us?" had no empirical answer. It does now.

The telemetry stack is split deliberately:

- `services/inference-proxy/app.py` appends sanitized per-tier call records in
  the existing `_record()` path.
- `lib/inference_telemetry/` is a **read-only consumer** of that call log.

The writer stores tier, model, latency, outcome, token counts, and error class.
It does **not** store prompts, completions, message content, or credentials.
That keeps the trading critical path narrow while making cost analysis
independently verifiable.

---

## 2. What ships in this lane

### 2.1 Library — `lib/inference_telemetry/`
Three pure modules:

- **`aggregator.py`** — reads `~/.cache/sapphire/inference_proxy/calls.jsonl` (or a fixture path) and produces a `TelemetryReport`:
  - per-tier latency p50 / p95 / p99 / p999 (linear-interpolation percentile, exact),
  - throughput (calls/min, calls/hour),
  - error rate (failures / total),
  - token consumption (in, out, total),
  - cost (USD, per `cost_model.estimate_cost_record`).
- **`cost_model.py`** — the `CostModel` dataclass + helpers (`with_kimi_rates`, `with_overrides`). T1 + T3 default to electricity-only proxies; T2 = $0; T4 defaults to **zero rates with `kimi_rates_supplied=False`** so we never silently fabricate a cost. Operators populate Kimi rates from Moonshot's published pricing page (cited above).
- **`recommender.py`** — surfaces "switch X→Y to save $Z/mo" recommendations honestly. Every recommendation includes:
  - capability caveats (T4 cannot be replaced for sensitive prompts),
  - latency caveats (destination tier latency p99 vs source),
  - sample-size caveats (window <1h, calls <50 → confidence "low"),
  - operator-decision caveats ("recommendations are illustrative; operator owns the actual decision").

### 2.2 Dashboard — `/inference-telemetry`
Four-panel observability page (auth-gated, paste-safe):

1. **System Summary** — totals (calls, error rate, cost, window, tokens, mode).
2. **Per-Tier Metrics** — table of tier × calls × p50 × p99 × error × cost.
3. **Cost Projection** — monthly cost + monthly call projection + Kimi-rates supplied state.
4. **Recommendations** — illustrative tier-switch suggestions with caveats.

Three new API endpoints:

- `GET /api/inference-telemetry-report`
- `GET /api/inference-telemetry-recommendations`
- `GET /api/inference-telemetry-cost-model`

All three are auth-gated (`requires_auth`) and exception-safe (return `{"ok": false, ...}` on any error rather than crashing the dashboard).

### 2.3 Plugin tool — `inference_telemetry`
Standard internal tool layout (`plugins/claw-sapphire/tools/internal/inference_telemetry.py` + 1-line shim at `tools/inference_telemetry.py`). Stdin-JSON contract.

Actions:
- `report` — full telemetry report; optional `output_path` writes a provenance-stamped artifact to `data/inference_telemetry/`.
- `recommendations` — recommendation bundle + top-N.
- `cost-model` — emit the active cost model + Moonshot pricing citation.
- `status` — lightweight probe (does `calls.jsonl` exist?).

### 2.4 Tests
- `tests/unit/test_inference_telemetry_aggregator.py` — 25 cases (parsing, percentiles, aggregation, missing-file handling, throughput, ordering, serialization).
- `tests/unit/test_inference_telemetry_cost_model.py` — 17 cases (T1/T2/T3/T4 cost paths, rate-supplied state, Moonshot citation).
- `tests/unit/test_inference_telemetry_recommender.py` — 11 cases (empty/full reports, capability caveats, error-rate warnings, confidence heuristic).
- `tests/unit/test_dashboard_inference_telemetry_routes.py` — 8 cases (auth, JSON shape, paste-safety, nav presence).
- `plugins/claw-sapphire/tests/test_inference_telemetry.py` — 11 cases (stdin contract, provenance stamping, cost model overrides).

**72 tests total** (54 unit + 11 plugin + 7 cross-cutting).

---

## 3. Architectural choices

### 3.1 Read-only, side-effect-free aggregator
The aggregator never writes anywhere. The proxy writes `calls.jsonl`, the aggregator reads it, the dashboard renders it, the plugin tool emits a provenance-stamped artifact only if the operator passes `output_path`. This keeps the trading critical path untouched: even a misbehaving aggregator cannot interfere with the proxy.

### 3.2 Honest cost model
Every dollar figure has a defensible source:

- **T1 / T3 proxies** are documented as electricity-only proxies. The default `$0.001/inference` and `$0.0008/inference` are illustrative — operators tune them with `with_overrides()` after measuring real wattage and duty cycle.
- **T2 is zero** by default — Pi power draw is so low (~5 W) that ascribing per-call cost would be misleading.
- **T4 (Kimi) defaults to zero rates with `kimi_rates_supplied=False`.** This is the most important architectural choice in the lane. The library *cannot* invent Kimi's per-token rate; it forces the operator to supply rates from Moonshot's pricing page (<https://platform.moonshot.cn/docs/pricing/chat>, retrieved 2026-04-29). Until rates are supplied, every Kimi cost cell is `$0` and every recommendation surfaces a "Kimi rates default to 0" caveat.

This means the first run on a fresh box prints honest *zero* cost for T4 — instead of a fabricated number. The recommender's top-level `caveats` list calls this out plainly.

### 3.3 Synthetic fallback when no real call log exists
When `~/.cache/sapphire/inference_proxy/calls.jsonl` is absent, empty, or
pointed elsewhere via `INFERENCE_PROXY_CALLS_PATH`,
`aggregator.synthetic_fixture_report()` produces a deterministic synthetic
report whose `has_real_data=False` flag is surfaced everywhere — dashboard
chip, plugin tool output, recommender bundle. **Synthetic data is never
silently treated as real data.** This is the same posture Tranche 4's
correlator and Tranche 5's customer surface adopted.

### 3.4 Permissive parsing
The proxy writer emits `tokens_in` / `tokens_out` / `latency_ms`, while the
aggregator's `parse_record()` also accepts alternate keys such as
`prompt_tokens` / `completion_tokens` / `elapsed_ms`. This keeps the contract
loose enough for older fixtures, one-off diagnostics, or future adapters
without breaking the dashboard.

### 3.5 Stable ordering for tests + provenance
Tiers in the report appear in canonical order (T1, T2 rari1, T2 rari2, T3, T4) followed by lexically-sorted unknown tiers. This makes test assertions robust and provenance hashes stable across re-runs. Recommendations are sorted by `(kind, from_tier, to_tier)` so two re-runs against the same input data produce byte-identical reports (and thus byte-identical provenance envelopes).

### 3.6 Dashboard isolation from sister Lane 4
Sister Wave 1 Lane 4 (source quality) also adds dashboard routes. To avoid a merge conflict, this lane appends all four routes (`/inference-telemetry`, three `/api/*`) to the **bottom** of `services/dashboard/app.py` in a clearly-labelled section. Lane 4 appends in the observability-block region. The integration-pass PR (Lane 9) will merge them mechanically.

---

## 4. Three worked examples of where this catches real cost issues

### 4.1 Silent T4 spend
*Scenario.* Operator flips `MOONSHOT_API_KEY` on for "deep research" calls. Three weeks later, monthly spend has grown by $40/mo without anyone noticing — Kimi calls are routed at the LLM-decision layer, not the operator's intent layer.

*What this lane catches.* `recommend()` emits a `switch_tier` recommendation `T4_kimi_cloud → T1_windows_gpu` with the projected monthly savings. Even if the savings number is conservative (because operator hasn't supplied rates), the recommendation surfaces the *volume* — "projecting 740 calls/mo on T4" — which is the actual signal: *we have 740 cloud calls/mo and we did not intentionally choose to.*

### 4.2 Mac CPU fallback masquerading as healthy
*Scenario.* Windows GPU goes unhealthy at 3 AM. T3 Mac local picks up traffic. CPU inference is ~80 s/call. Tooling that depends on inference (e.g. the nightly content engine) becomes glacially slow but the proxy's healthcheck reports green because *something* is responding.

*What this lane catches.* `T3_mac_local` shows up in the per-tier latency table with `p99 ≈ 90,000 ms`. The recommender emits a `T3 → T1` recommendation flagged with a fallback caveat: *"if T3 calls are happening because T1 was down, switching the routing without addressing T1 reliability does NOT help."* Operator gets the right diagnostic instead of mistaking the latency for a routing-policy bug.

### 4.3 Pi over-routing
*Scenario.* `PI_RARI1_ENABLED=1` is flipped on. Some traffic that was T1 is now T2. The Pi serves smaller models, but agent-side prompts have grown — token counts averaged 1,500 tokens/call. The Pi falls behind, errors climb to 25%.

*What this lane catches.* The recommender's error-rate threshold (>10%) emits a `routing_health_warning` for `T2_pi_rari1` with the top error class (e.g. `TimeoutError=42`). It does **not** emit a cost recommendation — because fixing the tier is cheaper than rerouting around it. This is the recommender's most important honest framing: not every signal is a recommendation to switch.

---

## 5. Provenance + paste-safety

Every artifact written to `data/inference_telemetry/` is wrapped via `lib.core.provenance.stamp()` with:

- `generator: "plugins.claw_sapphire.inference_telemetry"`
- `version: "0.1.0"`
- `source_paths`: the calls.jsonl path that was read
- `payload_hash`: deterministic SHA-256 of canonical-JSON of the report

Paste-safety:
- The dashboard never bleeds `/Users/<name>` paths into rendered HTML.
- The plugin tool `cost-model` action emits the Moonshot citation but never any Sapphire secret material.
- All caveats are plain text — safe to paste into a buyer-facing diligence doc.

---

## 6. Operator-owed actions

1. **Collect enough real call volume.** The proxy writer now exists, but SLO
   promotion should wait for representative traffic, agreed alert thresholds,
   and a clear retention/rotation expectation for `calls.jsonl`.
2. **Supply Kimi rates.** Pull the latest rates from
   <https://platform.moonshot.cn/docs/pricing/chat> and pass them to
   `with_kimi_rates()` (or via the plugin tool's `cost_model` payload field).
3. **Tune T1 / T3 electricity proxies.** Default values are illustrative. Real
   numbers come from a Kill-A-Watt + duty-cycle measurement.
4. **Decide on T4 → T1 trade-offs.** Recommendations are illustrative; operator
   decides.

---

## 7. Caveats (collected here so they live in one place)

- Sample size <50 calls = "low" confidence on every recommendation.
- Window <1 hour = monthly extrapolation is unreliable (not stationary).
- Kimi rates default to $0 — every dollar figure is conservative until rates are supplied.
- Failures still cost cycles on T1/T2/T3; T4 charges only on success (Moonshot's behavior in practice).
- Pi can only serve ≤4B-param models — recommender knows this and flags any T1 → T2 rec accordingly.
- This is read-only intelligence. **It does not change the routing.** The operator decides whether to flip flags.

---

## 8. Future enhancements (Tranche 7 backlog)

- **Streaming aggregator.** Today, `aggregate()` reads the entire JSONL in one pass. For 250k+ line logs we cap reading at `MAX_LINES_PER_READ = 250_000` and surface a truncation note. A streaming variant that only re-reads the tail since the last aggregation could turn this into a continuous metrics pipeline.
- **Anomaly detection.** Currently, `recommender` surfaces switch-tier and error-rate warnings. A future iteration could surface latency-distribution shift alerts (KS-test against a rolling baseline).
- **SLO link.** Lane 2's SLO doc references "T1 latency p99 < 1s" as an aspirational target. The integration pass should add a `/api/inference-telemetry-slo-status` endpoint that compares observed p99 against the SLO target.
- **Drift detection across models.** Today the aggregator groups by tier. A model-aware mode would let operators see "hermes3:8b on T1 vs T3" — useful when planning capacity.

---

## 9. Citations

- Moonshot AI pricing: <https://platform.moonshot.cn/docs/pricing/chat> (retrieved 2026-04-29). This is the only external citation in the lane; the rest of the cost model is internally documented.
- RTX 5070 Ti TBP: NVIDIA spec sheet (285 W).
- Tranche 6 megaprompt: `docs/handoffs/tranche-6-excellence-megaprompt-2026-04-29.md`.
- Sister-lane integration plan: same megaprompt, Lane 9 (integration pass).

---

## 10. One-paragraph version

> Sapphire's 4-tier inference mesh now has empirical telemetry. The inference
> proxy appends sanitized per-tier call records, and a pure-data library
> (`lib/inference_telemetry/`) reads that call log, aggregates per-tier latency
> / throughput / error / token / cost, and emits honest "switch X→Y to save
> $Z/mo" recommendations with capability + latency + sample-size caveats. The
> cost model uses electricity-only proxies for T1/T3, zero for T2, and
> operator-supplied per-token rates for T4 Kimi Cloud — never fabricated, always
> cited to Moonshot's published pricing page
> (<https://platform.moonshot.cn/docs/pricing/chat>, retrieved 2026-04-29).
> Every optional report artifact is provenance-stamped. Recommendations are
> illustrative; the operator owns the actual routing decision.
