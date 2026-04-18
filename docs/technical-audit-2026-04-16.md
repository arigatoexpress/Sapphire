# Sapphire OS — Technical Audit
**Date:** 2026-04-16  
**Auditor:** Claude Sonnet 4.6 (automated deep review)  
**Scope:** All production services, libs, infra configs  
**Files reviewed:** 9 source files, 10 LaunchAgent plists, 1 policy JSON

---

## Overall Technical Debt Score: **6 / 10**

Core architecture is sound. The 4-tier failover proxy is well-designed and reasonably thread-safe. The confirmation firewall concept is solid. The debt is concentrated in three areas: credentials management, a few non-atomic file operations, and one broken health-tracking path in the inference proxy.

---

## Findings Summary

| # | Severity | Component | Issue |
|---|----------|-----------|-------|
| 1 | **CRITICAL** | LaunchAgent plist | API credentials in plaintext XML |
| 2 | **CRITICAL** | Inference proxy | Unbounded request body — OOM/DoS |
| 3 | **CRITICAL** | Confirmation firewall | `_record_spend` race — financial limit bypass |
| 4 | **HIGH** | Inference proxy | `kimi-cloud` never marked failed — always retried |
| 5 | **HIGH** | Inference proxy | Background probe thread: no outer guard |
| 6 | **HIGH** | Signal pipeline | `update_signal_outcome` non-atomic write |
| 7 | **HIGH** | Signal pipeline | `signal_stats()` unprotected file read |
| 8 | **HIGH** | Command guard | `${IFS}` and tab bypass of dangerous patterns |
| 9 | **HIGH** | Kimi relay | No response size limit — OOM via relay |
| 10 | **MEDIUM** | Confirmation firewall | `classify_action` misses `long`, `short` financial actions |
| 11 | **MEDIUM** | Dashboard | `fetch_sync` no response size limit |
| 12 | **MEDIUM** | Signal pipeline | `_active` dict not protected in `update_signal_outcome` |
| 13 | **MEDIUM** | Sensitivity filter | `access_token`, `refresh_token`, `private_key` not caught |
| 14 | **MEDIUM** | Signal logger | Binds `0.0.0.0:18081` — unauthenticated webhook injection |
| 15 | **LOW** | Inference proxy | `_mark_ok` logs recovery outside lock (cosmetic race) |
| 16 | **LOW** | Task classifier | Empty/whitespace messages routed to `balanced` silently |
| 17 | **LOW** | LaunchAgent | Python version split (3.12 vs 3.14) across services |
| 18 | **LOW** | Confirmation firewall | Console fallback prints exact approval path to stdout |

---

## Detailed Findings

### CRITICAL-1: API Credentials in Plaintext LaunchAgent Plist
**File:** `~/Library/LaunchAgents/com.sapphire.inference-proxy.plist`  
**Lines:** EnvironmentVariables block

```xml
<key>MOONSHOT_API_KEY</key>
<string>sk-5nj0SZyyuunOxtCB6oazogC67TcVqDetYj8VH0B50ijIBAe9</string>
<key>KIMI_CLAW_BOT_TOKEN</key>
<string>7950001873:AAFoTWEcZOBJtNlpnEThUcLSWNNNyQrL5aM</string>
```

**Impact:** LaunchAgent plists are readable by any process running as `aribs`. If the Sapphire repo is ever pushed to GitHub (or included in any backup/sync tool like iCloud), both keys are exposed publicly and permanently. The Moonshot API key grants paid cloud inference access; the Telegram bot token grants control of the relay bot.

**Fix:** Move secrets to `~/.sapphire/secrets.env` (git-ignored, mode 0600). Load at process startup. Plist holds only an empty placeholder comment.

---

### CRITICAL-2: Unbounded Request Body in Inference Proxy
**File:** `services/inference-proxy/app.py:596-597`

```python
content_length = int(self.headers.get("Content-Length", 0))
body = self.rfile.read(content_length)
```

**Impact:** An attacker on the local network (or any process on the Mac) can send `Content-Length: 2147483647` (2 GB). The proxy attempts to read 2 GB into a `bytes` object, triggering OOM. The ThreadedHTTPServer spawns a new thread per request, so a burst of such requests exhausts memory rapidly. There is no maximum body size check anywhere in the `do_POST` path.

**Fix:** Add `MAX_REQUEST_BODY = 4 * 1024 * 1024` (4 MB) and reject requests exceeding it before reading.

---

### CRITICAL-3: `_record_spend` Race Condition — Financial Limit Bypass
**File:** `lib/core/confirmation_firewall.py:143-155`

```python
def _record_spend(amount: float) -> None:
    try:
        data = json.loads(LIMITS_FILE.read_text()) if LIMITS_FILE.exists() else {}
    except (json.JSONDecodeError, OSError):
        data = {}
    if data.get("date") != today:
        data = {"date": today, "spent": 0.0}
    data["spent"] = float(data.get("spent", 0.0)) + amount
    LIMITS_FILE.write_text(json.dumps(data, indent=2))
```

**Impact:** Two concurrent FINANCIAL actions (e.g., two Telegram-confirmed trades arriving milliseconds apart) both read `spent = $0`, both compute `$0 + $85 = $85 < $100`, both auto-approve, and then both write `$85` as the final balance. Net effect: `$170` authorized against a `$100` daily limit. The confirmation firewall's primary financial safety net is defeated.

**Fix:** Use `fcntl.flock` (POSIX advisory lock) around the read-modify-write sequence.

---

### HIGH-4: `kimi-cloud` Health Tracking Broken — Always Retried
**File:** `services/inference-proxy/app.py:437-504`

```python
def _call_kimi_cloud(...) -> dict | None:
    if not _is_healthy("kimi-cloud"):  # ← This condition is NEVER True
        return None
    # Moonshot fails → returns None (no _mark_failed)
    # OpenRouter fails → returns None (no _mark_failed)
    # Relay fails → _record(..., False) but NO _mark_failed("kimi-cloud")
```

**Impact:** `kimi-cloud` starts healthy and is never marked failed. Every request that falls through to T4 makes 3 sequential API calls (Moonshot → OpenRouter → Telegram relay), each with up to 120s timeout. Under sustained cloud unavailability, every non-GPU request wastes 10–360 seconds before returning 503. The `HEALTH_COOLDOWN` mechanism — the whole point of the health tracking system — has zero effect on the cloud tier.

**Fix:** Call `_mark_failed("kimi-cloud")` when all three sub-paths fail. Call `_mark_ok("kimi-cloud")` on any success.

---

### HIGH-5: Background Probe Thread Has No Outer Exception Guard
**File:** `services/inference-proxy/app.py:522-537`

```python
def _background_health_probe():
    probes = [...]
    while True:
        time.sleep(30)          # ← If SystemExit/BaseException escapes here...
        for name, url in probes:
            with _health_lock:
                is_failed = not _endpoint_health.get(name, True)
            if is_failed:
                _probe_endpoint(name, url)   # ← This catches exceptions internally
```

**Impact:** `_probe_endpoint` properly catches exceptions. But the outer `while True` loop has no guard. An unexpected `BaseException` (or a bug introduced in future changes to the probe list) would silently kill the daemon thread. After that, failed endpoints would never be re-probed for recovery; they stay failed for the remainder of the process lifetime, forcing all traffic to lower tiers permanently until the process restarts.

**Fix:** Wrap the `while True` body in `try/except Exception` to log and continue.

---

### HIGH-6: `update_signal_outcome` Non-Atomic File Write
**File:** `services/alpha/signal_pipeline.py:297-319`

```python
lines = path.read_text().splitlines()
# ... modify in memory ...
path.write_text("\n".join(new_lines) + "\n")  # ← overwrites entire file
```

**Impact:** Two concurrent `update_signal_outcome` calls for different `pipeline_id`s on the same date file will race: both read the same file content, both modify their respective line, and one write overwrites the other. The earlier write is lost. In a burst of TradingView webhooks triggering closes simultaneously, signal records silently disappear from the audit trail.

**Fix:** Write to a `path.with_suffix('.tmp')` file first, then `os.replace(tmp, path)` (atomic on POSIX).

---

### HIGH-7: `signal_stats()` Unprotected File Read
**File:** `services/alpha/signal_pipeline.py:334-336`

```python
for f in files[-30:]:  # last 30 days
    for line in f.read_text().strip().splitlines():  # ← no try/except
```

**Impact:** `f.read_text()` is outside any try/except block. If a signal file has a permission error, is deleted between the `glob()` and the `read_text()`, or is being written to (partially flushed), this raises and the entire `signal_stats()` call propagates an exception. The dashboard's `/api/signals` endpoint calls this and would return a 500 error until the issue self-resolves. The inner `except Exception: pass` only guards JSON parsing, not the I/O.

**Fix:** Wrap `f.read_text()` in a try/except, continue on error.

---

### HIGH-8: CommandGuard `${IFS}` Bypass
**File:** `infra/sandbox/command_guard.py:75-85`

```python
def _normalize_command(cmd: str) -> str:
    return " ".join(cmd.strip().split()).lower()   # ← does not strip ${IFS} etc.

def _matches_pattern(command: str, pattern: str) -> bool:
    return bool(re.search(re.escape(pattern.lower()), command, re.IGNORECASE))
```

**Impact:** The dangerous pattern `"rm -rf"` is normalized to a literal match. A shell command like `rm${IFS}-rf${IFS}/` collapses whitespace correctly but `${IFS}` is not expanded — the normalized command becomes `"rm${ifs}-rf${ifs}/"`. This does not match `"rm -rf"`. Similarly, `r\m -rf` (with a backslash), `rm	-rf` (tab-separated), or `$(printf 'rm -rf')` all bypass the check.

Other uncaught dangerous patterns:
- `eval` and backtick execution (`` `cmd` ``) not in policy
- `bash -c 'rm -rf'` — `bash` not in the dangerous list
- `python3 -c 'import os; os.system("rm -rf /")'` — not caught

**Fix:** Expand `_normalize_command` to strip `${...}` and `$VAR` references. Add `eval`, `bash -c`, `python3 -c`, and backtick execution to the policy.

---

### HIGH-9: Kimi Relay No Response Size Limit
**File:** `lib/telegram/kimi_relay.py:141-146`

```python
text = msg.get("text", "")
if not text:
    continue
cleaned = INBOUND_TAG_RE.sub("", text).strip()
return cleaned   # ← No size limit
```

**Impact:** Telegram allows messages up to 4096 characters, but a bot could technically send multiple messages or a crafted response. More importantly: if @rarikimibot is compromised or misconfigured, it could respond with a 4096-char message containing prompt injection text that gets returned verbatim to the inference proxy caller. Additionally, the relay has no mechanism to distinguish responses meant for different concurrent relay sessions — if two requests fire simultaneously, both will see the other's response.

**Fix:** Add `MAX_RESPONSE_CHARS = 16000` truncation and a per-request tag (`[SAPPHIRE→KIMI:{unique_id}]`) to disambiguate concurrent sessions.

---

### MEDIUM-10: `classify_action` Missing Financial Keywords
**File:** `lib/core/confirmation_firewall.py:83-88`

```python
_FINANCIAL_PATTERNS = re.compile(
    r"(trade|order|buy|sell|swap|transfer|withdraw|deposit|send.*\$|..."
```

**Missing:** `long`, `short`, `leverage`, `position size`, `liquidate`, `margin call`. The command "go long 0.5 BTC at market" would not trigger `FINANCIAL` classification and would fall through to `READ_ONLY` (the default). This means high-confidence directional signals using `long`/`short` terminology bypass the financial gate.

---

### MEDIUM-11: `fetch_sync` No Response Size Limit
**File:** `services/dashboard/app.py` (fetch_sync function)

```python
with urllib.request.urlopen(req, timeout=5) as r:
    return json.loads(r.read())  # ← reads entire response
```

If the signal-logger's recent signals endpoint or the threats JSON grows large (e.g., 1000+ signals accumulated), `r.read()` loads the entire thing into memory on every 10-second cache miss. This is a soft memory leak under high-volume signal days.

---

### MEDIUM-12: `_active` Signal Dict Not Protected in `update_signal_outcome`
**File:** `services/alpha/signal_pipeline.py:321-326`

The `update_signal_outcome` method modifies `self._active` while `process()` also modifies it. If called concurrently (e.g., from FastAPI thread pool), this can result in a `KeyError` or silent data loss in the active position index.

---

### MEDIUM-13: Sensitivity Filter Missing Common Token Patterns
**File:** `services/inference-proxy/app.py:205-218`

Not caught by `_SENSITIVE_PATTERNS`:
- `access_token`, `refresh_token`, `id_token` (OAuth)
- `private_key` as a JSON field name (service account credentials)
- `client_secret` (OAuth app secrets)
- `DATABASE_URL` containing credentials (`postgres://user:pass@host`)
- Slack tokens (`xoxb-`, `xoxp-`)

If any of these appear in a message routed to `kimi-cloud`, they would reach the Moonshot API.

---

### MEDIUM-14: Signal Logger Binds to `0.0.0.0` Without Authentication
**File:** `~/Library/LaunchAgents/com.sapphire.signal-logger.plist`

The signal logger binds to `0.0.0.0:18081` to receive TradingView webhooks from the Windows machine. There is no authentication on the webhook endpoint (by design — TradingView webhooks don't support Bearer tokens). Any host reachable to the Mac's IP can inject fake trading signals.

**Mitigation in place:** TradingView webhooks send a `secret` field in the payload that could be validated. Current implementation should verify this.

---

### LOW-15: `_mark_ok` Logs Recovery Outside Lock
**File:** `services/inference-proxy/app.py:176-179`

```python
def _mark_ok(name: str):
    with _health_lock:
        was_failed = not _endpoint_health[name]
        _endpoint_health[name] = True
    if was_failed:          # ← outside lock — two threads could log "recovered" simultaneously
        log.info("Endpoint %s recovered", name)
```

Functional behavior is correct (the write is locked). The log message may appear twice in rapid succession. Cosmetic only.

---

### LOW-16: Task Classifier — Empty Messages Silent Fallback
**File:** `services/inference-proxy/task_classifier.py`

`classify_messages([])` or `classify_messages([{"role":"user","content":""}])` returns `CHAT → balanced`. This is correct behavior but not logged. A misconfigured client sending empty messages always consumes a balanced/hermes3 inference request. Consider logging a warning.

---

### LOW-17: Python Version Split Across Services
- `com.sapphire.inference-proxy.plist`: uses `/opt/homebrew/bin/python3` = **3.14.3**
- `com.sapphire.dashboard.plist`: uses `/usr/local/bin/python3` = **3.12.8**
- `com.sapphire.signal-logger.plist`: uses `/usr/local/bin/python3` = **3.12.8**

The proxy uses `dict | None` union type hints (3.10+) and `from datetime import UTC` (3.11+) — both fine on 3.12/3.14. `signal_pipeline.py` uses `from datetime import UTC` and is executed via the 3.12 signal-logger — compatible. No current breakage, but any code addition using 3.13+ features in proxy will silently fail when tested on 3.12 signal-logger.

Recommendation: Standardize on one interpreter path system-wide.

---

### LOW-18: Console Fallback Prints Approval Path
**File:** `lib/core/confirmation_firewall.py:265`

```python
print(f"Approve: echo 'approved' > {PENDING_DIR}/{code}.json")
```

When Telegram is unavailable, the fallback prints the exact file path and content needed to approve any pending action. Anyone with access to the terminal or log files where stdout is redirected can approve arbitrary DESTRUCTIVE/FINANCIAL actions without Telegram confirmation.

---

## Architecture Notes

### What's Working Well
- **Inference proxy circuit breaker logic**: The `_is_healthy` / `_mark_failed` / `_mark_ok` pattern for T1–T3 is correctly implemented and thread-safe. The `HEALTH_COOLDOWN` prevents rapid retry storms.
- **Sensitivity classifier**: The `_SENSITIVE_PATTERNS` regex is correctly compiled in VERBOSE mode. The comment/alternation interaction is valid. No false positives observed in the pattern design.
- **Signal scoring math**: The composite score formula (confidence 40 + kernel 25 + RR 20 + position 15 = 100) is reasonable and correctly implemented. Position scaling to max is sensible.
- **Confirmation firewall DESTRUCTIVE delay**: The 30-second enforced delay after DESTRUCTIVE approval is a good design. Correctly implemented.
- **KeepAlive policies**: Most services correctly use `<true/>`. hermes-agent correctly uses `{SuccessfulExit: false}` to avoid restart loops on clean exits.
- **Thread safety**: `_health_lock` and `_metrics_lock` are consistently used for all reads AND writes on their respective shared state.

### Structural Debt
1. No unit tests for the inference proxy routing logic (model alias resolution, tier fallthrough, sensitivity filtering)
2. `kimi_relay.py` has no test coverage at all
3. The `_active` signal dict in `SignalPipeline` is in-memory only — restarts lose active position tracking
4. `confirmation_firewall._record_spend` uses a flat JSON file for state; should be replaced with Redis (already installed) for atomicity and TTL support
5. `sandbox_policy.json` `network_deny` is declarative but not enforced — `CommandGuard` only checks command strings, not actual network connections

---

## Fix Plan (CRITICAL + HIGH)

All fixes applied to the following files:
- `services/inference-proxy/app.py` — CRITICAL-2, HIGH-4, HIGH-5
- `lib/core/confirmation_firewall.py` — CRITICAL-3, MEDIUM-10
- `services/alpha/signal_pipeline.py` — HIGH-6, HIGH-7
- `infra/sandbox/command_guard.py` — HIGH-8
- `lib/telegram/kimi_relay.py` — HIGH-9
- `~/Library/LaunchAgents/com.sapphire.inference-proxy.plist` — CRITICAL-1

MEDIUM and LOW findings are documented here for future sessions.
