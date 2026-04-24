# Sapphire OS — Tomorrow's Priorities (2026-04-25)

Generated: 2026-04-24T19:44 MDT by sapphire-self-improvement

---

## System State (EOD 2026-04-24)

| Check | Status |
|-------|--------|
| Core tests (Sapphire unit) | 2,004 passed, 1 skipped, 21 xfailed (known gaps) |
| Plugin tests | 67 passed |
| THO tests | 22 passed |
| Windows GPU Ollama | **RED** — timed out (machine likely off or Ollama not listening) |
| Trading signals | **FIXED** — signal_generator.py sys.path bug patched; scanner runs (0 signals today: BTC RSI=63, below 70 threshold) |
| Threat intel | Fresh (12h old, ran 2026-04-22 03:00 UTC) |
| Market pulse | Fresh (ran today, BTC LEAN_LONG RSI=63) |
| Starred repos | Yellow (24h old) |
| Trading predictions | Yellow (24h old) |

---

## What Was Done Today

- **Fixed `sys.path` bug in `signal_generator.py` and `research.py`**: Both used
  `.parent.parent / "lib"` (resolves to `tools/lib`, non-existent). After being moved
  to `tools/internal/`, they need `.parent.parent.parent / "lib"` to reach
  `claw-sapphire/lib`. This caused `trading_signals.jsonl` to go stale (114h).
  Commit: `5d3bb0e7` on `feat/service-supervisor`.
- New `session_recap` tool merged to main (session note from 2026-04-22): aggregates
  signals, predictions, paper trades, events for "catch me up" queries.
- Sapphire test count up to 2,004 (from 2,001 on 2026-04-21).

---

## Priorities for 2026-04-25

### 1. [HIGH] Merge signal_generator / research.py sys.path fix to main
The fix is on `feat/service-supervisor` (commit `5d3bb0e7`). If this branch is
ready to merge (no other in-progress changes blocking), merge it to main so the
fix persists and the CI gate validates it. Check branch status:
`cd ~/Code/Sapphire && git log feat/service-supervisor ^main --oneline | head -10`.

### 2. [MEDIUM] Fix `datetime.utcnow()` in THO `firestore_client.py`
Lines 108, 109, 122, 318, 319 in `~/Code/Project-Go-Forward/database/firestore_client.py`
still use the deprecated `datetime.utcnow()`. Replace with `datetime.now(datetime.UTC)`
(Python 3.11+). This is the same fix done in `lead_management.py`. The THO test
suite already has 22 tests covering CRUD — verify they still pass after the fix.

### 3. [MEDIUM] Add `session_recap` to morning-briefing scheduled task
The session_recap tool was built and merged but not yet wired into `sapphire-morning-briefing`.
Add a "last 8h activity" section before the market section: 
`echo '{"hours": 8}' | python3 ~/Code/Sapphire/plugins/claw-sapphire/tools/internal/session_recap.py`
This gives every morning brief a cheap recap of overnight automation activity.

### 4. [MEDIUM] Fix Windows GPU Ollama (persistent issue)
RTX 5070 Ti (100.71.10.48:11434) has been offline for at least 3 days. SSH to
the Windows machine (`ssh aribs@100.71.10.48`) and verify: (a) machine is up via
Tailscale ping, (b) OllamaServe scheduled task is running, (c) `OLLAMA_HOST=0.0.0.0`
is set at Machine scope. Without GPU T1, hermes-agent inference degrades to Mac CPU
(~90s/response). The inference proxy already handles fallback gracefully; fix is
purely about performance.

### 5. [LOW] Extract `_read_jsonl` to `claw-sapphire/lib/data_utils.py`
The `session_recap` tool note flagged that 3+ tools share the same JSONL-reading
pattern (filter by timestamp, skip malformed lines). Extract it to avoid drift.
Tools to check: `session_recap.py`, `paper_trader.py`, `trading_brain.py`. Only
do this if the pattern is identical — don't over-abstract.

---

## Market Context (2026-04-24)

- **BTC**: LEAN_LONG, RSI=63 (approaching overbought but no trigger yet), MA bullish,
  price ~$77,600. 90% confidence on bullish signal, but Ensemble vote is neutral.
  Kronos model path missing — no ML confirmation layer.
- **ETH**: LEAN_LONG, RSI=62, MA bullish, price ~$2,322.
- **SOL**: RSI=53, MA bullish, no strong directional bias.
- No paper trades triggered today (thresholds not met — healthy, avoids overtrading).

## Threat Context (2026-04-22 sweep)

Top active threats:
1. **CVE-2025-32975** — Quest KACE SMA auth bypass, CVSS 10.0, exploited in wild.
2. **CVE-2025-2749** — Kentico Xperience path traversal RCE, CVSS 7.2, CISA KEV.
3. **CVE-2025-48700** — Zimbra XSS via crafted email, CVSS 6.1, CISA KEV.
None directly affect Sapphire stack. No action required unless Kentico/Quest/Zimbra
products are in use.
