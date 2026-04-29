# Inference Mesh Telemetry — Operations Runbook

> **Component:** `lib/inference_telemetry/`, `/inference-telemetry` dashboard page, `inference_telemetry` plugin tool.
> **Owner:** Sapphire (read-only consumer of inference proxy call log).
> **Trading critical path:** **No.** This component is strictly read-only against the proxy's cache files. It cannot affect routing, reliability, or trades.
> **Status:** shipped 2026-04-29 (Tranche 6 Lane 6).

---

## 1. Purpose

This runbook tells the on-call operator how to:

1. Operate the inference-mesh telemetry surface.
2. Diagnose why the report is empty / stale / unrealistic.
3. Tune the cost model for real values once electricity / Kimi rates are measured.
4. Consume the recommendations honestly (they are illustrative, not directives).
5. Cope with each known failure mode.

This component is **read-only** against `~/.cache/sapphire/inference_proxy/calls.jsonl`. There is no live API call, no secret, no privileged operation. If something feels wrong, the worst case is that the dashboard panel shows stale or empty data — never a routing change.

---

## 2. Quick reference

| Action | Command |
|---|---|
| Status probe | `echo '{"action":"status"}' \| python3 plugins/claw-sapphire/tools/inference_telemetry.py` |
| Report (synthetic / real) | `echo '{"action":"report"}' \| python3 plugins/claw-sapphire/tools/inference_telemetry.py` |
| Report with operator-supplied Kimi rates | `echo '{"action":"report","cost_model":{"kimi_input_usd_per_1k_tokens":1.20,"kimi_output_usd_per_1k_tokens":2.40}}' \| python3 plugins/claw-sapphire/tools/inference_telemetry.py` |
| Recommendations | `echo '{"action":"recommendations"}' \| python3 plugins/claw-sapphire/tools/inference_telemetry.py` |
| Cost model | `echo '{"action":"cost-model"}' \| python3 plugins/claw-sapphire/tools/inference_telemetry.py` |
| Dashboard page | open <http://localhost:8080/inference-telemetry> (basic-auth, `AUTH_PASSWORD`) |
| Dashboard API report | `curl -u sapphire:<pwd> http://localhost:8080/api/inference-telemetry-report \| jq .` |

---

## 3. Sources of input

The aggregator reads exactly one file:

```
~/.cache/sapphire/inference_proxy/calls.jsonl
```

**Format (one JSON object per line):**

```json
{
  "ts": "2026-04-29T12:34:56.789012Z",
  "tier": "T1_windows_gpu",
  "model": "hermes3:8b",
  "latency_ms": 412,
  "ok": true,
  "tokens_in": 312,
  "tokens_out": 198,
  "error_class": null
}
```

Permissive: the parser accepts `prompt_tokens` / `completion_tokens`,
`elapsed_ms`, `success`, `endpoint`, and `backend` as alternates. The
production proxy writer now emits the documented `tokens_in` / `tokens_out` /
`latency_ms` shape, while those alternates keep older fixtures and diagnostic
logs readable.

Tier values must be one of:

- `T1_windows_gpu`
- `T2_pi_rari1`
- `T2_pi_rari2`
- `T3_mac_local`
- `T4_kimi_cloud`

Unknown tier values are accepted and surfaced in the report's `notes` field.

If the file is missing, the aggregator falls back to `synthetic_fixture_report()` and clearly flags `has_real_data=False`.

---

## 4. Operating procedures

### 4.1 First-time setup (fresh box)

1. **Verify the calls file path.** `python3 plugins/claw-sapphire/tools/inference_telemetry.py <<< '{"action":"status"}'`. Look at `calls_path_exists`.
2. **If missing**, confirm whether the proxy has handled any logged calls since
   boot. The production proxy now creates the parent directory and appends
   sanitized records on the first per-tier call unless
   `INFERENCE_CALL_LOG_ENABLED=0` is set. To pre-create the path on a fresh box:
   ```bash
   mkdir -p ~/.cache/sapphire/inference_proxy
   touch ~/.cache/sapphire/inference_proxy/calls.jsonl
   ```
   An empty file means "no logged calls yet", "the writer is disabled", or "the
   proxy is writing to a different `INFERENCE_PROXY_CALLS_PATH`".
3. **Pull Kimi rates.** Visit <https://platform.moonshot.cn/docs/pricing/chat> and note the input + output per-million-token rates for whichever Kimi SKU the proxy uses. Convert to per-1k tokens (`rate_per_1m / 1000.0`).
4. **Persist the rates** in `~/.sapphire/secrets.env` if you want a single source of truth, but **never commit them**:
   ```bash
   echo "MOONSHOT_INPUT_USD_PER_1K=1.20" >> ~/.sapphire/secrets.env
   echo "MOONSHOT_OUTPUT_USD_PER_1K=2.40" >> ~/.sapphire/secrets.env
   ```

### 4.2 Daily operation

The dashboard panel auto-refreshes every 60 s. No daily action is required.

If the panel becomes important to a buyer-facing demo:

1. Run `make doctor` to confirm services are healthy.
2. Open `/inference-telemetry`; verify the System Summary numbers look sane.
3. If the page shows `mode = synthetic / no data`, that is correct when the
   proxy has not served any logged calls yet, the call log is disabled, or the
   dashboard is reading a different file. **Do not fabricate data.**

### 4.3 Tuning the cost model

Defaults are conservative placeholders. To tune:

```python
from lib.inference_telemetry.cost_model import with_overrides, with_kimi_rates

cm = with_overrides(t1_per_inference_usd=0.0007, t3_per_inference_usd=0.0005)
cm = with_kimi_rates(input_usd_per_1k_tokens=1.20, output_usd_per_1k_tokens=2.40, base=cm)
```

Pass via the plugin tool:

```bash
echo '{
  "action":"recommendations",
  "cost_model":{
    "t1_per_inference_usd":0.0007,
    "t3_per_inference_usd":0.0005,
    "kimi_input_usd_per_1k_tokens":1.20,
    "kimi_output_usd_per_1k_tokens":2.40
  }
}' | python3 plugins/claw-sapphire/tools/inference_telemetry.py
```

T1 / T3 measurement: Kill-A-Watt → idle wattage → inference wattage → multiply by typical inference duration → divide by household electricity rate. We deliberately do not bake measurements into the default model because they vary per machine.

### 4.4 Consuming a recommendation

Each recommendation has:

- `kind`: `switch_tier` or `routing_health_warning`.
- `from_tier` / `to_tier`: the suggested move.
- `monthly_savings_usd`: projected (illustrative).
- `monthly_volume`: projected calls/mo on that tier.
- `confidence`: `low` / `medium` / `high` (based on sample + window).
- `caveats`: list of plain-text caveats — read all of them.
- `rationale`: one-line summary of how the number was computed.

**Operator rule of thumb:** never act on `confidence: low` recommendations. Wait for at least one hour of real traffic and ≥50 calls.

---

## 5. Failure modes + remediation

### 5.1 Dashboard panel is empty

*Symptom.* `/inference-telemetry` loads but every metric reads `--`.

*Likely cause.* `~/.cache/sapphire/inference_proxy/calls.jsonl` is missing AND the synthetic fallback is failing.

*Diagnosis.*
```bash
echo '{"action":"status"}' | python3 plugins/claw-sapphire/tools/inference_telemetry.py
```

*Remediation.* If `calls_path_exists: false` is the only issue, that's expected on a fresh box. The dashboard should show `mode: synthetic / no data`. If even synthetic mode fails, the JS console will show a fetch error — usually means dashboard auth failed; re-login.

### 5.2 Numbers look fabricated / unrealistically high

*Symptom.* Total cost = $0.04 in 1 hour but the operator thinks the proxy has been running all day.

*Likely cause.* Synthetic-fixture mode. The synthetic fixture deliberately uses small numbers so it isn't mistaken for real data; the dashboard chip shows `mode: synthetic / no data` and `has_real_data: false`. **This is the system being honest, not a bug.**

*Remediation.* The proxy writer exists in `services/inference-proxy/app.py`.
Verify `INFERENCE_CALL_LOG_ENABLED` is not `0`, check
`INFERENCE_PROXY_CALLS_PATH`, confirm the proxy has served a request through a
logged tier, and inspect the call-log file permissions. Until a real call lands,
synthetic mode is expected.

### 5.3 T4 cost is $0 but Kimi has been used

*Symptom.* Per-tier table shows T4 calls but `cost_usd: $0.000000`.

*Likely cause.* `kimi_rates_supplied: false` — operator has not yet supplied Moonshot rates.

*Remediation.* See § 4.3. Pass rates via `cost_model` payload field. Until rates are supplied, **the system honestly refuses to invent a cost** — every recommendation includes a caveat: *"Kimi (T4) rates default to 0 — supply real rates from <https://platform.moonshot.cn/docs/pricing/chat> ..."*.

### 5.4 Aggregator silently truncates

*Symptom.* Report includes a note: `truncated at MAX_LINES_PER_READ=250000`.

*Likely cause.* `calls.jsonl` has grown beyond 250k lines.

*Remediation.* Rotate the log:
```bash
mv ~/.cache/sapphire/inference_proxy/calls.jsonl{,.$(date +%Y%m%d)}
touch ~/.cache/sapphire/inference_proxy/calls.jsonl
```
The aggregator will read the new (small) file. Old files are kept on disk for retroactive analysis.

### 5.5 Unknown tier in input

*Symptom.* Report's `notes` includes `unknown tiers in log: T9_alien`.

*Likely cause.* The proxy started writing a tier label that's not in `KNOWN_TIERS`.

*Remediation.* Either:
- Update the proxy to write a documented tier label, **or**
- Update `lib/inference_telemetry/__init__.py` `KNOWN_TIERS` tuple — **but only if** the new tier is genuinely a new mesh node, not a typo.

### 5.6 Recommender output looks contradictory

*Symptom.* Same recommendation appears twice with different savings.

*Likely cause.* Should not happen. Recommendations are sorted by `(kind, from_tier, to_tier)` and de-duplicated implicitly. If you see this, file a bug with the offending payload.

### 5.7 Plugin tool refuses to write provenance-stamped artifact

*Symptom.* `report` action with `output_path` succeeds but the file lacks a `provenance` field.

*Likely cause.* `lib.core.provenance` import path issue. Provenance stamping is best-effort; the tool returns the unwrapped payload rather than failing.

*Remediation.* Verify `from lib.core.provenance import stamp` works in a fresh Python shell. If not, that's a deeper repo issue (broken `sys.path`).

---

## 6. Capacity planning (when this becomes a continuous metric)

### 6.1 Aggregator runtime cost

`aggregate()` is O(N) in lines read. On a stock M-series Mac, 100k lines parses in ~150 ms. The dashboard fetches every 60 s — at 100k lines that's 0.25% CPU.

### 6.2 Memory

Aggregator holds the full record list in memory during aggregation. At ~200 bytes per `CallRecord`, 100k records = 20 MB. The 250k cap protects against runaway logs.

### 6.3 When to add streaming

If `calls.jsonl` exceeds 1M lines / day, switch to a tail-only aggregator that only reads new lines since the last run. Out of scope for 0.1.0.

---

## 7. Test discipline

| Layer | Test file | Count |
|---|---|---|
| Aggregator | `tests/unit/test_inference_telemetry_aggregator.py` | 25 |
| Cost model | `tests/unit/test_inference_telemetry_cost_model.py` | 17 |
| Recommender | `tests/unit/test_inference_telemetry_recommender.py` | 11 |
| Dashboard routes | `tests/unit/test_dashboard_inference_telemetry_routes.py` | 8 |
| Plugin tool | `plugins/claw-sapphire/tests/test_inference_telemetry.py` | 11 |

Total: **72 tests** for a 0.1.0 lane.

Run:
```bash
/usr/local/bin/python3 -m pytest tests/unit/test_inference_telemetry_*.py tests/unit/test_dashboard_inference_telemetry_routes.py -q
/usr/local/bin/python3 -m pytest plugins/claw-sapphire/tests/test_inference_telemetry.py -q
```

(Run the two pytest blocks separately — pytest's conftest collection can't span the unit / plugin roots in one invocation.)

---

## 8. Coordinating with sister lanes

- **Lane 4 (source quality)**: also adds dashboard routes. Lane 4 appends in the observability-block region; Lane 6 appends at the bottom. Integration-pass merge is mechanical.
- **Lane 9 (integration pass)**: will add a cross-link between the observability dashboard and the inference-telemetry panel, and will add an SLO comparison endpoint.

---

## 9. Decommissioning

To retire this lane (e.g. if the inference proxy adopts an internal telemetry surface):

1. Remove `services/dashboard/app.py` Inference Mesh Telemetry section + nav link.
2. Mark `inference_telemetry` plugin entry as `deprecated` in `infra/tool-registry.yaml` with `replacement: <new tool>` and a sunset window.
3. Add a `_deprecated/inference_telemetry.py` shim that emits `DeprecationWarning`.
4. Leave `lib/inference_telemetry/` untouched until the new surface is fully proven (≥ 30 days soak).

---

## 10. Citations

- Moonshot AI pricing: <https://platform.moonshot.cn/docs/pricing/chat> (retrieved 2026-04-29). The single external citation; per-token rates are operator-supplied at runtime, never baked into the library.
- Tranche 6 megaprompt: `docs/handoffs/tranche-6-excellence-megaprompt-2026-04-29.md` (Lane 6).
- Provenance schema: `lib/core/provenance.py`.
- Inference proxy: `services/inference-proxy/app.py` (untouched by this lane — read-only consumer only).
