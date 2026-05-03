# Stack-wide error triage — 2026-05-03 (B1+B2)

**Scope.** Pass-1 read-only scan of `data/system_events.jsonl`,
`~/autonomy-status/logs/*.err`, the inference proxy `/health` and
`/metrics` surface, the brain-silo modules (`lib/agents/`,
`src/sapphire_core/cognitive_agent.py`), and `data/events/bus.jsonl`.
Pass-2 fixes were limited to in-scope, non-trivial bugs reproducible
from the live logs. Critical-path code (`services/hyperliquid/`,
`services/alpha/`, `lib/portfolio/robinhood.py`, `data/`, secrets,
infra plists, `kill_switch`, `confirmation_firewall`, `security/`)
was left untouched.

## Triage table

| # | Issue | Location | Class | Note |
|--|--|--|--|--|
| 1 | `BrokenPipeError` / `ConnectionResetError` thread-level traceback when client disconnects mid-response | `services/inference-proxy/app.py::_respond_raw` and the x402 402-response branch | **real** | Fixed in PR linked below. Latent on the x402 path (gate is currently `enabled=False`). |
| 2 | `NameError: name 'ipaddress'` from `services/alpha/src/signal_logger.py` | log only | drift | Already fixed on disk (`import ipaddress` is line 19). 99 historical occurrences in `signal_logger.err`; service is currently up on `:18081` and import is clean. |
| 3 | `redis-py not installed — event bus running in fallback mode` | `lib/core/event_bus.py:176` | env | `redis` is intentionally optional; the JSONL fallback at `data/events/bus.jsonl` is the supported steady state when Redis isn't installed. One log per process is expected. |
| 4 | Cloudflared tunnel: `failed to serve tunnel connection` retry storm | `~/autonomy-status/logs/cloudflare-tunnel.err` | env | Network-side retries to `198.41.192.77`. Operator-tracked. |
| 5 | OpenBB Yahoo HTTP 404 on `SOL` and "delisted" warnings on `ASTER-USD` / `LIT-USD` | `~/autonomy-status/logs/openbb_api.err` | drift | Provider-side symbol map drift; not a Sapphire code bug. |
| 6 | Robinhood `HTTP 400: Invalid symbol: CC-USD` on every `_get_best_bid_ask` batch | `lib/portfolio/robinhood.py` | out-of-scope | Trading critical-path file (operator approval required). The `CC` asset_code comes back from `/api/v2/crypto/trading/holdings/`; needs a server-side allowlist or client-side filter. Tracked for operator review. |
| 7 | `regional_intel.err` Pydantic / SSL `cafile` exceptions | `~/Code/regional-intel-workbench/.venv` (Python 3.14) | out-of-scope | Different repo; not Sapphire. |
| 8 | TradingView Pine batch: `unrecognized arguments: --out` | `~/autonomy-status/logs/tradingview-pine-batch.err` | drift | LaunchAgent invocation passes `--out` but `tradingview_ta_capture.py` doesn't accept that flag. Operator-controlled plist; not in critical-path list, but stack-wide flag-drift fix is its own PR. |
| 9 | `threat-refresh.err` DNS resolution failure for `cisa.gov` + 120s subprocess timeout | `~/autonomy-status/logs/threat-refresh.err` | env | DNS / outbound network; not a Sapphire code bug. |
| 10 | `telemetry-collector.err` `urlopen` connection refused on proxy `/metrics` | `~/autonomy-status/logs/telemetry-collector.err` | env | Last entry 2026-04-21 — collector re-attached after proxy restart. No recent occurrences. |
| 11 | `tradingview-ta-capture.err` 21x `redis-py not installed` warning | log only | env | One warning per scheduled run (every 4 h) — same root as #3. |
| 12 | Inference proxy windows-gpu probe time-outs followed by "recovered" | `inference_proxy.err` | env | Documented WARN row `local/inference_proxy_health` in `docs/ops/readiness-warn-state-2026-04-30.md`. Probe-cycle behaves as designed. |
| 13 | Inference proxy `OSError: [Errno 48] Address already in use` on bind | `inference_proxy.err` | env | LaunchAgent restart races; resolved on retry. Last 2026-04-29. |
| 14 | Dashboard `401` on `GET /` from anonymous probes | `dashboard.err` | env | `AUTH_PASSWORD` is intentional; 401 is the correct response to unauthenticated requests. |
| 15 | 1,386 `security.kill_switch.engaged` events in last 2 k events of `system_events.jsonl` | `data/system_events.jsonl` | env | Operator drills (462 each: `Manual CLI invocation`, `ops drill`, `forced`) spread across 2026-04-27 → 2026-05-03. Test fixture (`tests/unit/test_security_kill_switch.py`) already isolates `_EVENTS_PATH` via `monkeypatch`. |
| 16 | `src/sapphire_core/cognitive_agent.py` and `lib/agents/{runner,alpha_agent}.py` review | code | clean | Walked all three; no unhandled-exception paths or dead-letter routes. `lib/agents/alpha_agent.py:57` does instantiate a fresh `EventBus` instead of `get_bus()`, but that is by design (per-agent `source` tag) and not a bug. |
| 17 | `data/events/bus.jsonl` last 100 lines | data | clean | 100/100 are payment-gate test events from 2026-05-01 (`payment.required`, `payment.received`, `payment.rejected`); no stuck signals. |

## Fix PRs

- **#632** — `fix(inference-proxy): swallow ConnectionResetError + reuse _respond_raw on x402` — addresses row 1.

## What was deliberately *not* fixed in this triage

- Row 6 (`CC-USD`) — needs an edit to `lib/portfolio/robinhood.py` (critical path); operator must approve.
- Row 8 (`tradingview-pine-batch --out` flag) — LaunchAgent plists are operator-controlled per the megaprompt rules.
- Rows 4, 5, 7, 9 — environmental / external repos.

## Verification

```
ruff check services/inference-proxy/app.py tests/unit/test_inference_proxy_app.py
pytest tests/unit/test_inference_proxy_app.py
# 77/77 pass (75 prior + 2 new BrokenPipe/ConnectionReset parametrised)
```
