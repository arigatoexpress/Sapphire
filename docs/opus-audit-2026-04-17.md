# Opus 4.7 Audit — 2026-04-17

Scope: adversarial code review of Sapphire OS, focused on the files Sonnet has been writing. Severity: **CRITICAL / HIGH / MEDIUM / LOW**. Every finding has file:line, impact, and fix.

Note on scope drift: the user's target list included `services/alpha/signal_pipeline.py`, `lib/chain/*`, `lib/analytics/*`, `services/pipeline/gcp_sync.py`, `agents/market_watchdog.py`, `agents/health_monitor.py`, `lib/core/confirmation_firewall.py`, and `infra/sandbox/command_guard.py`. **None of these files exist in the repo.** This is itself a finding — agents (Sonnet or human) have been writing specs and docs referencing files that were never created, or were renamed/deleted and references never updated. What does exist was audited instead: the inference proxy, dashboard, risk kernel / position sizing / circuit breaker, signal logger, predict, paper trader, signal generator, watchdog, health check, notify, control-plane Kimi bridge, and execution dispatcher.

---

## Summary

**6 CRITICAL** • **15 HIGH** • **12 MEDIUM** • **6 LOW**

| Component | Quality (1–10) | Headline problem |
|---|---|---|
| `services/inference-proxy/app.py` | **3** | Sensitivity classifier is hard-disabled with `return False`, routing any content — including credentials — to cloud LLMs |
| `services/dashboard/app.py` | **3** | Plaintext-compared Basic Auth over HTTP; fabricated "opportunities" / "logs" endpoints |
| `services/control-plane/app/main.py` | **4** | Empty `CONTROL_PLANE_TOKEN` silently disables auth on every write endpoint |
| `services/alpha/src/signal_logger.py` | **4** | No auth on `/api/signals`; sys.path mutated inside request handler |
| `services/alpha/src/execution/dispatcher.py` | **6** | Token-bucket is per-process only; dead-letter reconcile matches by symbol, not ID |
| `plugins/claw-sapphire/tools/notify.py` | **2** | Falls back to `CERT_NONE` (no TLS verification) if `certifi` is missing |
| `plugins/claw-sapphire/tools/predict.py` | **3** | Scores "24h" predictions seconds after they're made — the 58% accuracy number is noise |
| `plugins/claw-sapphire/tools/paper_trader.py` | **5** | No atomic writes; no slippage/fees; trailing stops can fire before hard stops |
| `plugins/claw-sapphire/tools/signal_generator.py` | **5** | No dedupe — cron produces duplicate signals every run |
| `plugins/claw-sapphire/tools/watchdog.py` | **6** | State file written non-atomically; subprocess calls swallowed silently |
| `lib/core/src/sapphire_core/risk_kernel.py` | **7** | Sound logic; not thread-safe, no persistence across restart |
| `lib/core/src/sapphire_core/circuit_breaker.py` | **6** | Not thread-safe; HALF_OPEN admits multiple probes |
| `lib/core/src/sapphire_core/position_sizing.py` | **5** | `stage_multipliers.get(stage, 1.0)` fails OPEN (full size) for unknown stage; Kelly cap breached by confidence×regime multipliers |

**Weighted average: 4.5 / 10.** This is a system with real ambition and a lot of surface area, but the safety-critical paths (auth, TLS, sensitivity gating, atomicity, risk caps) are repeatedly implemented in ways that **fail open**. The pattern: a guard is written, then disabled, weakened, or given a permissive default "until it's tuned."

---

## CRITICAL findings

### C1. Sensitivity classifier is disabled — secrets route to cloud LLM
**File:** `services/inference-proxy/app.py:134-150`

```python
def _is_sensitive(messages: list) -> bool:
    """...
    DISABLED: always returns False until sensitivity rules are tuned.
    ...
    """
    return False  # noqa: disabled — uncomment loop below to re-enable
    for msg in messages:
        ...
```

- **Impact:** The proxy's entire cloud-routing defense — `_is_sensitive()` — is a no-op. CLAUDE.md explicitly states "NEVER route credentials, PnL, customer data, or system internals to Kimi." This function is the only thing enforcing that, and it always returns `False`. So the checks at line 447 (explicit Kimi request) and line 530 (Tier 4 fallback) **always pass**. Any prompt — including raw `.env` content, API keys, chat transcripts — flows to Moonshot/OpenRouter over the network. Note also that the patterns, even when enabled, are weak: `password|api.key|secret|credential|jwt|ssh.key` treats `.` as a regex wildcard, matching `apiXkey`, and is trivially bypassable by paraphrase.
- **Fix:** Remove the early `return False`, tighten the regex (AWS `AKIA[0-9A-Z]{16}`, GitHub `ghp_[A-Za-z0-9]{36}`, Anthropic `sk-ant-…`, PEM headers `-----BEGIN`, etc.), and run sensitivity screening on *both* `messages` and any system prompts. This is fixed below.

### C2. Control-plane auth bypassed when `CONTROL_PLANE_TOKEN` is unset
**File:** `services/control-plane/app/main.py:118-121`

```python
def _require_control_token(token: str) -> None:
    expected = _control_token()
    if expected and token != expected:
        raise HTTPException(status_code=403, detail="invalid control token")
```

- **Impact:** If the env var is not set (which is the current state per `.env.example:13` showing `CONTROL_PLANE_TOKEN=`), `expected` is an empty string, the `if expected and …` short-circuits, and **every endpoint that calls `_require_control_token` accepts any request**. That includes agent registration, task creation, executor policy mutation, and the kimi bridge proxy (lines 1295, 1323, 1342, 1359, 1375, 1390). The sibling `kimi_bridge.verify_token` correctly fails closed ("CONTROL_PLANE_TOKEN not set — all requests denied"), so the two auth surfaces disagree.
- **Fix:** Fail closed — if `expected` is empty, raise 503 ("control token not configured") rather than letting the request through. Also use `hmac.compare_digest` instead of `!=` to prevent timing attacks on a deployed token. Fixed below.

### C3. Signal logger has no auth and trusts any POST
**File:** `services/alpha/src/signal_logger.py:36-109`

- **Impact:** `POST /api/signals` accepts arbitrary JSON from anywhere, writes it to `trading_signals.jsonl`, broadcasts it to Telegram, and feeds it to the downstream signal/paper-trader pipeline. Running on `0.0.0.0:18081`. Anyone on Tailscale — or anyone who ports-forwards this accidentally — can inject fake signals, corrupt the training set for scoring, and spam Telegram. The TradingView webhook source is never verified.
- **Fix:** HMAC the payload with a shared secret from env, validate the signature server-side, reject on mismatch. (Not fixed in this PR — requires webhook-producer coordination; flagged for follow-up.)

### C4. Prediction accuracy number is fake — scoring doesn't wait for the timeframe
**File:** `plugins/claw-sapphire/tools/predict.py:193-239`

```python
for line in lines:
    p = json.loads(line)
    if p.get("correct") is None and p["symbol"] in prices:
        current = prices[p["symbol"]]
        entry = p.get("entry_price") or p["target_price"]
        if p["direction"] == "bullish":
            p["correct"] = current > entry
        ...
```

- **Impact:** Every prediction is tagged `"timeframe": "24h"` but `action_score` scores *any* unscored prediction against the *current* price, regardless of when it was generated. A prediction generated 30 seconds ago is immediately marked correct/incorrect. The published "58% accuracy" in CLAUDE.md is therefore measuring "does the price direction in the next N seconds match the TA consensus at the time of prediction" — essentially noise. The CLAUDE.md paragraph that praises "BTC 75% accuracy" is marketing copy based on a broken metric.
- **Fix:** Parse `timeframe` (`24h`, `4h`, `1h`), skip predictions younger than the window, and only score when `now - timestamp >= timeframe`. Fixed below.

### C5. TLS verification disabled in the Telegram notifier fallback
**File:** `plugins/claw-sapphire/tools/notify.py:20-27`

```python
_SSL_CTX = ssl.create_default_context()
try:
    import certifi
    _SSL_CTX.load_verify_locations(certifi.where())
except ImportError:
    _SSL_CTX.check_hostname = False
    _SSL_CTX.verify_mode = ssl.CERT_NONE
```

- **Impact:** If `certifi` is not installed (which silently happens in minimal Python envs, e.g. a fresh `/usr/local/bin/python3` on Mac), the notifier disables hostname verification and certificate chain validation against `api.telegram.org`. An on-path attacker can MITM the Telegram API call, strip the bearer token from the URL (`https://api.telegram.org/bot<TOKEN>/sendMessage` — the token is in the URL path), and take over the bot. This is called on every system alert.
- **Fix:** Remove the `CERT_NONE` branch. If `certifi` is missing, use the stock system CA bundle (`ssl.create_default_context()` without further weakening). Never disable verification silently. Fixed below.

### C6. Inference proxy has no body-size limit — trivial DoS
**File:** `services/inference-proxy/app.py:423-425`

```python
def do_POST(self):
    content_length = int(self.headers.get("Content-Length", 0))
    body = self.rfile.read(content_length)
```

- **Impact:** A client can send `Content-Length: 100000000000` and the server will block indefinitely in `rfile.read`, or a negative number to trigger `read(-1)` and read until EOF. Combined with the single-threaded `HTTPServer` (not `ThreadingHTTPServer`), one bad request wedges every other request behind it — including health checks, and including the hermes-agent Telegram bot, which is the only path users have to the system when local services are under load.
- **Fix:** Reject `Content-Length` below 0 or above a sane cap (e.g. 1 MB) with 413, and switch to `ThreadingHTTPServer`. Fixed below. (Note: thread-safety for `_endpoint_health` then becomes load-bearing — also fixed with a lock.)

---

## HIGH findings

### H1. Inference proxy `_endpoint_health` is not thread-safe
**File:** `services/inference-proxy/app.py:92-113`

Dict-level reads/writes of `_endpoint_health` and `_last_health_check` happen from the request thread. CPython's GIL makes single dict ops safe, but the read-modify-write pattern in `_is_healthy` / `_mark_failed` / `_mark_ok` is a race. Today it's hidden by the single-threaded `HTTPServer`; once C6 is fixed by switching to `ThreadingHTTPServer`, two concurrent failures can corrupt the cooldown window. Fixed below with a module lock.

### H2. Invalid stage string fails open to full live sizing
**File:** `lib/core/src/sapphire_core/position_sizing.py:247`

```python
stage_mult = cfg.stage_multipliers.get(inp.execution_stage, 1.0)
```

- **Impact:** `execution_stage` is a free-form string (`paper`, `staged_live`, `full_live`). If any caller passes something unexpected — a typo (`"full-live"`), a missing value coerced to the dataclass default `"full_live"` (OK), or an empty string — the sizer returns **`1.0`**, i.e. the most aggressive multiplier. The whole point of the paper/staged/full ladder is that unknown states should behave like paper (`0.0`). Fixed below.

### H3. Kelly cap is breached by downstream multipliers
**File:** `lib/core/src/sapphire_core/position_sizing.py:235-250`

`compute_kelly` caps at `kelly_cap` (0.25 default). Then `adjusted_pct = base_pct * confidence_mult * vol_mult * dd_mult * regime_mult * stage_mult` where `confidence_mult` can be 1.5 and `regime_mult` can be 1.2, so the effective Kelly fraction can reach `0.25 * 1.5 * 1.2 = 0.45`. It is then clamped by `max_position_pct` (10% default), but the Kelly cap is supposed to be a *Kelly*-level safeguard, not a redundancy that happens to be covered by a separate cap. If anyone ever loosens `max_position_pct`, the Kelly bound silently vanishes. Recommend: apply the Kelly cap *after* all multipliers, not just to the base.

### H4. Circuit breaker not thread-safe; HALF_OPEN admits multiple probes
**File:** `lib/core/src/sapphire_core/circuit_breaker.py` (entire)

Two request threads calling `check()` during the `reset_timeout` window both see state transition CLOSED (via the property side-effect at line 68) and both proceed to call the venue. The "one probe" invariant mentioned in the docstring isn't enforced. Recommend: `threading.Lock` around `state` reads and all writes; introduce a `_probe_in_flight` flag cleared on `record_success`/`record_failure`.

### H5. HALF_OPEN transition mutates state from a property getter
**File:** `lib/core/src/sapphire_core/circuit_breaker.py:63-74`

The `state` property has an observable side-effect (writes `self._state = HALF_OPEN`). Reading a property usually shouldn't mutate. Besides the thread-safety issue (H4), this also means *any* introspection call — `status()`, `is_open`, a debug print — can trigger the transition. Move the transition into an explicit method (`_poll_state()`) called from `check()` and `record_*`.

### H6. Inference proxy model whitelist is not enforced
**File:** `services/inference-proxy/app.py:433-434`

```python
raw_model = req_data.get("model", "auto")
model = MODEL_TIERS.get(raw_model, raw_model)
```

- **Impact:** If a client sends `"model": "gpt-4o"` (or any arbitrary string), it's passed through verbatim to the downstream Ollama tier. Since `GPU_ONLY_MODELS` checks for exact-match strings, an attacker can skip the GPU-gate by submitting an unknown model name that happens to exist on Mac — or by submitting something that matches an unexpected passthrough path. Recommend: reject models not in `MODEL_TIERS` ∪ `GPU_ONLY_MODELS` ∪ `PI_MODELS` with 400.

### H7. Kimi Cloud tier is never marked failed
**File:** `services/inference-proxy/app.py:292-319`

`_call_openai_compat` never calls `_mark_failed("kimi-cloud")` on error, and `_call_kimi_cloud` only calls `_mark_ok` on the happy path. Result: the `kimi-cloud` key in `_endpoint_health` stays `True` even after both providers consistently fail, so the health endpoint lies, and there's no cooldown. Add explicit `_mark_failed("kimi-cloud")` inside the `except` of `_call_openai_compat`.

### H8. `recent_signals` loads the entire JSONL file into memory
**File:** `services/alpha/src/signal_logger.py:118`

```python
lines = SIGNALS_PATH.read_text().strip().splitlines()[-20:]
```

- **Impact:** JSONL grows unbounded (every webhook + every scanner run). At 10K signals/day × 1 KB each = 3.6 GB/year. One request reads the whole file to return 20 lines. Use a rolling tail (seek from end, read backwards until 20 newlines) or rotate the file.

### H9. `predict.action_score` rewrites the whole predictions file non-atomically
**File:** `plugins/claw-sapphire/tools/predict.py:229`

```python
PREDICTIONS_FILE.write_text("\n".join(updated) + "\n")
```

- **Impact:** Power loss mid-write → truncated/empty predictions history, all scoring lost. Use `tempfile.NamedTemporaryFile` in the same dir + `os.replace`. Same issue in `paper_trader._save_portfolio`. Fixed below for `predict.py`.

### H10. Signal generator has no dedupe
**File:** `plugins/claw-sapphire/tools/signal_generator.py:45-199`

`scan_for_signals` runs on cron every 15 minutes (per the `market-pulse` task). Every invocation writes new signals with fresh UUIDs; the same TA conditions generate the same signal repeatedly. Downstream consumers (paper trader) then trade the dupe. Add a dedupe key `(symbol, action, date_bucket, price_bucket)` to a small recent-signals set (1h TTL).

### H11. Paper trader: no slippage, no fees, no partial fills
**File:** `plugins/claw-sapphire/tools/paper_trader.py:214-221`

Exit price = `current` (instant, perfect). Real markets eat 5–25 bps on a market order plus fees (0.1% taker is typical). Results will over-estimate win rate and Sortino. Recommend: subtract a fixed `slippage_bps + taker_fee_bps` on both entry and exit, configurable.

### H12. `paper_trader._save_portfolio` is not atomic
**File:** `plugins/claw-sapphire/tools/paper_trader.py:55-57`

Same atomic-write problem as H9. A crash during a portfolio save leaves a truncated JSON and `json.loads` on next load throws — the portfolio is effectively destroyed.

### H13. sys.path mutated inside request handler
**File:** `services/alpha/src/signal_logger.py:88`

```python
sys.path.insert(0, str(Path.home() / "Code" / "Sapphire" / "plugins" / "claw-sapphire" / "tools"))
```

Executed once per request. The list grows unbounded, and `sys.path.insert(0, …)` means every import resolution checks the path first — increasingly expensive over hours of uptime.

### H14. Telegram message has no Markdown escaping
**File:** `plugins/claw-sapphire/tools/notify.py:110`

Telegram API returns 400 when it sees unbalanced `_` or `*` in `parse_mode: Markdown`. Any log message containing them (file paths with `_`, agent names with underscores) fails silently — `except Exception: pass` in callers swallows the error. Either switch to `MarkdownV2` with escaping, or `parse_mode: None` (plain text), or escape the caller-supplied segment.

### H15. Dashboard password compared with `==` (timing attack)
**File:** `services/dashboard/app.py:31-32`

```python
def check_auth(username, password):
    return username == AUTH_USERNAME and password == AUTH_PASSWORD
```

- **Impact:** Basic Auth sent over HTTP already loses to a network observer, but even on HTTPS, `==` on Python strings leaks character-level timing. Use `hmac.compare_digest`.

---

## MEDIUM findings

### M1. Dashboard returns fabricated data
**File:** `services/dashboard/app.py:196-228`

`api_opportunities` returns a hardcoded `ETH buy conf=0.85 z=-2.3` on every call. `api_logs` returns two canned log lines. `api_watchlist` returns static `BTC=65000`, `ETH=3500` prices. A user looking at the dashboard during a real trading day gets misleading data. Either wire these to the real store or return 501.

### M2. Dashboard cache is not thread-safe
**File:** `services/dashboard/app.py:51-68`

Flask is multi-threaded by default; `_cache` and `_cache_time` are plain dicts read-modify-written under concurrent requests. Most operations are single dict ops (OK-ish under GIL) but `now - _cache_time.get(key, 0)` + `_cache[key] = data` is a race. Use `threading.Lock`.

### M3. Dashboard runs with `debug=False` but no prod WSGI server
**File:** `services/dashboard/app.py:237`

`app.run(host='0.0.0.0', ...)` — Flask's built-in server. Documented as not for production. Ship a gunicorn/uvicorn worker in front.

### M4. Dashboard `fetch_from_rari1/2` are async but never awaited
**File:** `services/dashboard/app.py:70-90`

Dead code. Sync fetching is done by `fetch_sync` on line 92. Delete the async variants.

### M5. `_load_kimi_token` is dead code
**File:** `services/inference-proxy/app.py:322-334`

`_call_kimi_cloud` only consults `MOONSHOT_API_KEY` and `OPENROUTER_API_KEY`. The OAuth token loader is imported, referenced in the docstring, and never called. Either wire it as a fallback or delete it.

### M6. `KIMI_API_BASE` is misleading dead config
**File:** `services/inference-proxy/app.py:37`

Advertised in `/health` output as "t4_kimi_cloud" but never used for any outbound call. Rename to `MOONSHOT_API_BASE` (or set `t4_kimi_cloud` to whichever base is actually selected at request time).

### M7. Watchdog loses alerts on subprocess failure
**File:** `plugins/claw-sapphire/tools/watchdog.py:41-47`

```python
try:
    subprocess.run([...], capture_output=True, timeout=15)
except Exception:
    pass
```

If `notify.py` is broken or crashes, the watchdog silently fails to alert. Log to a file-based dead letter queue on exception.

### M8. Watchdog state write is not atomic
**File:** `plugins/claw-sapphire/tools/watchdog.py:60-63`

Mid-write crash corrupts `.watchdog_state.json`; next run starts with an empty state and re-alerts every existing red as "new." Write to temp + `os.replace`.

### M9. Dispatcher rate limiter resets on process restart
**File:** `services/alpha/src/execution/dispatcher.py:13-46`

`_windows` is a plain in-memory deque. If the dispatcher crashes and restarts, the token bucket is empty — previous rate-limiting history is gone. Persist the last-60s window to disk/Redis if restart flapping is a real concern.

### M10. Dispatcher dead-letter reconcile matches by `(venue, symbol)` only
**File:** `services/alpha/src/execution/dispatcher.py:100-111`

If two orders for the same symbol are dispatched back-to-back and only one fills, `reconcile(venue, symbol)` marks the most recent entry regardless of whether it's the one that filled. Use a dispatch-id/signal-id correlation instead.

### M11. Position sizing confidence multiplier is a floor, not a gate
**File:** `lib/core/src/sapphire_core/position_sizing.py:235`

`confidence_mult = 0.5 + inp.confidence` — at `confidence=0`, `mult=0.5`, still sized. Bottom-of-confidence signals should probably size **zero**. Consider `max(0, inp.confidence - 0.4) * 2` or a hard minimum confidence threshold.

### M12. Risk kernel has no persistence across restarts
**File:** `lib/core/src/sapphire_core/risk_kernel.py` (entire)

`HardRiskKernel` tracks consecutive losses, day-peak equity, hold windows, all in memory. Restart the process mid-drawdown → state resets → the 4% daily-loss gate is off until enough equity snapshots arrive to re-prime it. Persist to disk on every update.

---

## LOW findings

### L1. `signal_logger` bare `except`
**File:** `services/alpha/src/signal_logger.py:83, 100`

Swallows every failure including `KeyboardInterrupt` on CPython 3.8+ (actually `Exception` → KI is fine). Use `except Exception:` and log.

### L2. `dashboard.fetch_from_rari1/2` bare `except`
**File:** `services/dashboard/app.py:77, 88, 98`

Same issue.

### L3. Inference proxy `log_message` silence hides access logs entirely
**File:** `services/inference-proxy/app.py:551-552`

OK for debug noise, but we log nothing if a client fails at the HTTP layer before `do_POST` is called. Consider a minimal `$method $path → $status` line.

### L4. `paper_trader.main` imports repeated at bottom of file (unseen here)
Common pattern — defer imports to `action_*` functions so cold startup is fast. Not a bug, but worth noting.

### L5. `predict.action_history` JSON parse errors not handled
**File:** `plugins/claw-sapphire/tools/predict.py:247`

`preds = [json.loads(l) for l in PREDICTIONS_FILE.read_text().strip().split("\n")]` — any malformed line crashes the whole call.

### L6. Signal generator uses `change_24h_pct` from `profile` but variable is derived
**File:** `plugins/claw-sapphire/tools/signal_generator.py:105-114`

If the TA library returns `None` for 24h change (first day of a new symbol), the comparison `profile.change_24h_pct > 0` throws `TypeError`. Guard with `or 0`.

---

## Fixes applied in this PR

Fixing CRITICALs (C1, C2, C5, C6) and the two worst HIGHs that are co-located (H1, H2, H15). Everything else is flagged for follow-up — the fixes are more invasive (persistence, HMAC, rotation) and warrant separate review.

1. `services/inference-proxy/app.py` — re-enable `_is_sensitive`, tighten regex, add body-size cap, switch to `ThreadingHTTPServer`, add module lock around health dict, mark kimi-cloud failed on provider failure. (C1, C6, H1, H7)
2. `services/control-plane/app/main.py` — fail closed when token unset, switch to `hmac.compare_digest`. (C2)
3. `plugins/claw-sapphire/tools/notify.py` — remove `CERT_NONE` fallback. (C5)
4. `plugins/claw-sapphire/tools/predict.py` — skip scoring until `timeframe` has elapsed, atomic rewrite. (C4, H9)
5. `lib/core/src/sapphire_core/position_sizing.py` — invalid stage fails to `0.0`. (H2)
6. `services/dashboard/app.py` — `hmac.compare_digest` for password. (H15)

Re-run the audit after these land; the remaining HIGHs (dedupe, slippage, dispatcher reconcile) are not fixed here.
