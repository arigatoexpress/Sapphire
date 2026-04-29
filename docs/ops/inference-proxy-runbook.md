# Inference Proxy Runbook

> **Component:** `services/inference-proxy/`
> **LaunchAgent:** `com.sapphire.inference-proxy`
> **Local URL:** `http://127.0.0.1:11435`
> **Trading critical path:** yes, as an inference dependency. It does not place
> trades, send Telegram messages, or mutate broker state.

This runbook covers day-2 operation of Sapphire's local OpenAI-compatible
inference proxy: health checks, tier routing, model aliases, sensitivity gates,
tenant quotas, prompt cache behavior, call-log telemetry, and safe recovery.

The proxy is a router and policy layer. Treat routing changes as production
adjacent: use tests and local probes first, and do not retarget live services
or unload LaunchAgents without explicit operator intent.

## 1. Safety Posture

- No real trading is performed by this service.
- No Telegram messages are sent by this service.
- Sensitive prompts are blocked from cloud fallback.
- Quotas and prompt cache are local in-process controls.
- The call-log writer stores sanitized metadata only: tier, model, latency,
  outcome, token counts, and error class.
- Prompt text, completion text, raw messages, API keys, and credentials must
  never be written to `calls.jsonl`, logs, PR bodies, or issues.

## 2. Quick Checks

Run from `/Users/aribs/Code/Sapphire`:

```bash
curl -fsS http://127.0.0.1:11435/health | python3 -m json.tool
curl -fsS http://127.0.0.1:11435/metrics | python3 -m json.tool
curl -fsS http://127.0.0.1:11435/v1/quota | python3 -m json.tool
```

These three checks are read-only. They do not call any model, spend money,
write cache records, or touch a trading venue.

For code changes, run the focused test slice:

```bash
python3 -m pytest tests/unit/test_inference_proxy_app.py -q
python3 -m pytest tests/unit/test_inference_telemetry_*.py -q
python3 scripts/validate_tool_registry.py
```

If a change touches LaunchAgent packaging, also run:

```bash
python3 -m pytest tests/unit/test_launchagent_plists.py -q
plutil -lint services/inference-proxy/launchagent/com.sapphire.inference-proxy.plist
```

## 3. Runtime Layout

| Path | Purpose |
|---|---|
| `services/inference-proxy/app.py` | Router, health, quota, cache, sensitivity, x402, and telemetry writer. |
| `services/inference-proxy/start.sh` | LaunchAgent wrapper; loads `~/.sapphire/secrets.env` and selects Python. |
| `services/inference-proxy/launchagent/com.sapphire.inference-proxy.plist` | Versioned service-local LaunchAgent. |
| `docs/ops/inference-tenant-quotas.md` | Quota and prompt-cache policy reference. |
| `docs/ops/inference-mesh-telemetry-runbook.md` | Read-only telemetry consumer and cost-analysis runbook. |
| `lib/inference_telemetry/` | Pure reader/aggregator for the proxy call log. |
| `tests/unit/test_inference_proxy_app.py` | Main behavior contract. |

Live logs:

```bash
tail -n 100 /Users/aribs/autonomy-status/logs/inference_proxy.log
tail -n 100 /Users/aribs/autonomy-status/logs/inference_proxy.err
```

Telemetry call log:

```bash
tail -n 20 ~/.cache/sapphire/inference_proxy/calls.jsonl
```

Do not paste raw log lines into public issues unless you have checked that they
contain only sanitized metadata.

## 4. Routing Model

The proxy exposes OpenAI-compatible routes and forwards to four tiers:

| Tier | Backend | Primary use |
|---|---|---|
| T1 | Windows GPU Ollama at `WINDOWS_GPU_URL` | fast general, code, reason, large models |
| T2 | Pi Ollama via `PI_RARI1_URL` / `PI_RARI2_URL` | small-model low-power fallback |
| T3 | Mac local Ollama at `MAC_LOCAL_URL` | always-on local fallback |
| T4 | Kimi / Moonshot cloud | non-sensitive research fallback only |

Important defaults:

- `MODEL_TIERS` maps aliases such as `fast`, `balanced`, `code`, `reason`,
  `qwen3.6`, and `cloud` to concrete backends.
- `GPU_ONLY_MODELS` must stay Windows-only. If T1 is down, these should fail
  closed or exact-fallback only where explicitly allowed.
- `PI_SERVE_MODELS` is intentionally narrow. Do not route large prompts or
  GPU-only models to Pi.
- `MAC_EXACT_FALLBACK_MODELS` permits exact local fallback where the Mac has
  the requested model.

Before changing alias behavior, add or update tests in
`tests/unit/test_inference_proxy_app.py` under the model-alias or tier-membership
sections.

## 5. Request Surface

Main routes:

| Route | Method | Notes |
|---|---|---|
| `/v1/chat/completions` | POST | OpenAI-compatible chat route. May call local/cloud models. |
| `/v1/completions` | POST | Completion compatibility route. |
| `/v1/embeddings` | POST | x402-priced route when x402 is enabled. |
| `/v1/models` | GET | Model list. |
| `/v1/quota` | GET | Current tenant policy and usage. |
| `/v1/cache-stats` | GET | Prompt-cache aggregate statistics. |
| `/health` | GET | Service and tier health. |
| `/metrics` | GET | In-process per-tier request counters. |

Do not use a real prompt smoke test in a docs, CI, or PR lane unless the
operator explicitly asks for one. Prefer unit tests and GET probes.

## 6. Sensitivity And Cloud Fallback

`_is_sensitive()` blocks sensitive content from Kimi/Moonshot fallback. The
classifier checks API keys, bearer tokens, JWTs, passwords, private keys, access
tokens, refresh tokens, SSNs, payment-card-like strings, Slack bot tokens, and
database URLs.

Expected behavior:

- Benign prompts can use local tiers and, when explicitly routed, cloud tiers.
- Sensitive prompts must never reach T4.
- Sensitive prompts also bypass prompt cache.
- A blocked cloud route should return a clear error instead of silently
  downgrading policy.

Regression tests live in `TestSensitivityGate` and cloud-fallback tests in
`tests/unit/test_inference_proxy_app.py`.

## 7. Quotas And Prompt Cache

Default configuration is documented in
`docs/ops/inference-tenant-quotas.md`.

Key facts:

- `INFERENCE_REQUIRE_API_KEY=0` keeps local compatibility by default.
- `INFERENCE_REQUIRE_API_KEY=1` rejects unknown or missing keys.
- Accepted key headers: `X-API-Key`, `X-Sapphire-API-Key`, and
  `Authorization: Bearer`.
- Keys are hashed for matching and are not returned by `/v1/quota` or
  `/v1/cache-stats`.
- Cache hits count against request quota but avoid an additional model call.
- Sensitive prompts bypass cache.

If a caller reports unexpected `429` responses, check `/v1/quota`, confirm the
tenant id, and inspect the configured per-day request and token limits. Do not
raise quotas globally when a per-key policy is the correct fix.

## 8. Call-Log Telemetry

The production request path appends sanitized records to:

```text
~/.cache/sapphire/inference_proxy/calls.jsonl
```

Environment controls:

| Variable | Meaning |
|---|---|
| `INFERENCE_CALL_LOG_ENABLED=0` | Disable call-log writes. Default is enabled. |
| `INFERENCE_PROXY_CALLS_PATH=/path/to/calls.jsonl` | Override the output path for tests or isolated runs. |

Allowed record fields:

```json
{
  "ts": "2026-04-29T12:34:56.789Z",
  "tier": "T1_windows_gpu",
  "model": "hermes3:8b",
  "latency_ms": 412,
  "ok": true,
  "tokens_in": 312,
  "tokens_out": 198,
  "error_class": null
}
```

If `calls.jsonl` is missing, the telemetry dashboard falls back to synthetic
mode and marks `has_real_data=false`. Do not fabricate traffic for a demo.

If the file grows too large, rotate it manually:

```bash
mv ~/.cache/sapphire/inference_proxy/calls.jsonl{,.$(date +%Y%m%d)}
touch ~/.cache/sapphire/inference_proxy/calls.jsonl
```

## 9. LaunchAgent Operations

Inspect status:

```bash
launchctl list | grep com.sapphire.inference-proxy
plutil -lint services/inference-proxy/launchagent/com.sapphire.inference-proxy.plist
```

The tracked plist uses:

- `ProgramArguments`: `/bin/bash`, `services/inference-proxy/start.sh`
- `WorkingDirectory`: `/Users/aribs/Code/Sapphire`
- `RunAtLoad`: true
- `KeepAlive`: true
- `StandardOutPath`: `/Users/aribs/autonomy-status/logs/inference_proxy.log`
- `StandardErrorPath`: `/Users/aribs/autonomy-status/logs/inference_proxy.err`

Agent lanes should not unload or retarget the live LaunchAgent as a first move.
If a restart is required, capture the current health output and log tail first,
then ask the operator or prepare an explicit rollback note.

## 10. Common Incidents

### `/health` reports degraded Windows GPU

1. Confirm T3 Mac local is healthy.
2. Check whether the requested model is GPU-only.
3. If GPU-only requests are failing closed, that is expected. Do not reroute
   GPU-only models to cloud or Pi.
4. Check Windows/Tailscale state outside the proxy lane.

### Pi tier times out

1. Confirm `PI_RARI1_ENABLED` / `PI_RARI2_ENABLED` in the plist or environment.
2. Verify the model is in `PI_SERVE_MODELS`.
3. Leave `PI_DEFAULT_MODEL` small unless benchmark evidence supports a change.
4. Treat repeated timeouts as a tier-health problem, not a reason to broaden
   model routing.

### Sensitive prompt reaches cloud

This is a severity-one policy bug.

1. Stop and preserve the failing payload privately.
2. Add a unit test in `TestSensitivityGate` or the cloud-routing section.
3. Patch `_is_sensitive()` or routing order.
4. Do not paste the sensitive prompt into GitHub.

### `/v1/quota` looks wrong

1. Check `INFERENCE_QUOTAS_JSON` or `INFERENCE_QUOTAS_FILE` presence, not raw
   values.
2. Confirm `INFERENCE_REQUIRE_API_KEY`.
3. Use `/v1/cache-stats` to see whether cache hits are changing traffic shape.
4. Prefer a per-key policy over raising the global default.

### Telemetry dashboard shows synthetic mode

1. Confirm the proxy has served at least one logged per-tier request.
2. Confirm `INFERENCE_CALL_LOG_ENABLED` is not `0`.
3. Confirm the dashboard and proxy agree on `INFERENCE_PROXY_CALLS_PATH`.
4. Keep synthetic mode visible until real records exist.

## 11. Change Checklist

Before opening a PR that touches `services/inference-proxy/`:

- [ ] Identify whether the change affects routing, sensitivity, quotas, cache,
  telemetry, x402, or LaunchAgent packaging.
- [ ] Add focused unit coverage in `tests/unit/test_inference_proxy_app.py`.
- [ ] Run the focused inference-proxy test slice.
- [ ] Run `python3 scripts/validate_tool_registry.py`.
- [ ] Update this runbook, `docs/ops/inference-tenant-quotas.md`, or
  `docs/ops/inference-mesh-telemetry-runbook.md` if operator behavior changed.
- [ ] State rollback clearly in the PR.

## 12. Rollback

Code rollback is a normal git revert of the PR. Runtime rollback is to keep the
existing LaunchAgent loaded and revert only the tracked source or plist change.

If a bad routing change reaches the live proxy:

1. Revert the PR or hotfix the routing table in a new branch.
2. Confirm `/health` and `/metrics` recover.
3. Run `tests/unit/test_inference_proxy_app.py`.
4. Check `calls.jsonl` for a spike in failures after the change window.

Do not delete telemetry, cache, or log files during rollback unless the operator
explicitly asks for rotation.
