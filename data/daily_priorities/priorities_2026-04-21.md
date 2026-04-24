# Sapphire OS — Tomorrow's Priorities (2026-04-21)

Generated: 2026-04-20T23:43 CT by sapphire-self-improvement

---

## System State (EOD 2026-04-20)

| Check | Status |
|-------|--------|
| Core tests (Sapphire unit) | 1,961 passed, 21 xfailed (known gaps) |
| THO tests | 72 passing (22 existing + 50 new) |
| THO Cloud Run | Healthy (timeout was transient) |
| Windows GPU Ollama | Offline (timed out — machine likely off) |
| Trading signals | **74h stale** — signal_generator not producing fresh signals |
| Threat intel | 31h stale (sweep ran Apr 19 PM) |
| Market pulse | Fresh (ran today, 11h old) |

---

## Priorities for 2026-04-21

### 1. [HIGH] Investigate stale trading signals (74h)
`data/trading_signals.jsonl` last updated 2026-04-17. The signal_generator and
market-pulse scheduled tasks should be refreshing this. Check whether the signal
logger at :18081 is receiving webhook signals from TradingView and whether the
autonomous scanner (signal_generator.py) ran successfully. Look at LaunchAgent
logs: `log show --predicate 'subsystem == "com.sapphire"' --last 3d`.

### 2. [MEDIUM] Add `datetime.now(UTC)` fix to appointment_manager.py
Same `datetime.utcnow()` pattern exists in `appointment_manager.py` (not checked
today — but the Lead dataclass was fixed). Running `grep -n utcnow appointment_manager.py`
will confirm. Fix mirrors what was done in `lead_management.py` today. Run the 50
new tests in `tests/test_appointment_and_lead.py` to verify.

### 3. [MEDIUM] Fix Windows GPU offline state
RTX 5070 Ti Ollama (100.71.10.48:11434) timed out in health check. SSH to Windows
(`ssh aribs@100.71.10.48`) to verify machine is up. If up, check OllamaServe task:
`ssh aribs@100.71.10.48 "schtasks /Query /TN OllamaServe /FO LIST"`. Restart if
needed. The T1 GPU tier is the fastest inference path (232 tok/s for nemotron-mini)
— losing it degrades hermes-agent responses.

### 4. [LOW] Refresh threat intel and starred repos
Both are >24h stale. The threat-intel-sweep runs at 6:30 AM and 2 PM — verify
it ran on 2026-04-20. Check `data/threat_intel/` for a `latest_20260420_*.md` file.
If absent, the sweep task failed silently. Check logs and re-trigger if needed.

### 5. [LOW] plugin.json version bump
CLAUDE.md says v0.4.0 but architecture review noted plugin.json still shows v0.3.0.
Confirm with `grep version plugins/claw-sapphire/plugin.json`. If stale, bump to
0.4.0 — minor but keeps CLAUDE.md accurate.

---

## Key Intel (for context)

**Market (2026-04-20):** BTC bullish toward $76,467 (90% conf, 24h); ETH $2,373; SOL $87.
Paper portfolio +0.64%, 0 open positions. Prediction model at 33 scored forecasts
(below 100-call public threshold).

**Threat (2026-04-19):** Apache ActiveMQ CVE-2026-34197 — RCE via Jolokia JMX bridge,
CVSS 8.8, actively exploited. Upgrade to 5.19.4 or 6.2.3 if running ActiveMQ.

**Architecture (2026-04-19 review):** Control-plane monolith (5,847 lines across 3 files)
is the main long-term structural risk. No action needed now, but watch for complexity
creep as features compound. 15 tools registered in plugin.json (corrected from earlier
7-tool count — architecture review was written before the plugin.json update).

---

## What Was Done Today

- Fixed `datetime.utcnow()` → `datetime.now(UTC)` in THO `lead_management.py` (3 occurrences)
- Committed new test suite `tests/test_appointment_and_lead.py` (50 tests, all passing)
  → commit `8f315d8` on `main`
- Confirmed `predict_kronos.py` `import requests` issue already resolved (architecture
  review finding was stale — internal file uses only stdlib)
- All Sapphire unit tests passing (1,961 + 21 xfailed known gaps)
