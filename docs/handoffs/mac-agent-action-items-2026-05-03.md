# Mac Agent Action Items — 2026-05-03

**From:** Kimi Operator (Windows)
**To:** Mac Agent
**Priority:** CRITICAL
**Context:** Windows agent shipped B3 dashboard polish, THO PR merges, and Sapphire PR cleanup. Mac-side trading pipeline is the remaining blocker.

---

## 🚨 CRITICAL: Trading Pipeline Down

The Brain synthesis endpoint currently reports:
- `health_score`: 0.714
- `degraded_silos`: `['trading', 'services']`
- `trading_signals_24h`: N/A
- `regime`: TRANSITION

**Root cause:** `com.sapphire.signal-logger` and `com.sapphire.regime-collector` LaunchAgents are not running.

### Fix Steps

1. **Verify TradingView Desktop is running with CDP:**
   ```bash
   pgrep -f "TradingView" || open -a "TradingView" --args --remote-debugging-port=9222
   curl -s http://127.0.0.1:9222/json/version | jq .Browser
   ```

2. **Restart signal-logger LaunchAgent:**
   ```bash
   launchctl bootout gui/$(id -u) ~/Library/LaunchAgents/com.sapphire.signal-logger.plist 2>/dev/null
   launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.sapphire.signal-logger.plist
   launchctl print gui/$(id -u)/com.sapphire.signal-logger | head -5
   ```

3. **Restart regime-collector LaunchAgent:**
   ```bash
   launchctl bootout gui/$(id -u) ~/Library/LaunchAgents/com.sapphire.regime-collector.plist 2>/dev/null
   launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.sapphire.regime-collector.plist
   launchctl print gui/$(id -u)/com.sapphire.regime-collector | head -5
   ```

4. **Restart telemetry-collector (if stale):**
   ```bash
   launchctl bootout gui/$(id -u) ~/Library/LaunchAgents/com.sapphire.telemetry-collector.plist 2>/dev/null
   launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.sapphire.telemetry-collector.plist
   ```

5. **Verify signal flow:**
   ```bash
   tail -20 ~/.sapphire/logs/signal-logger.out
   tail -20 ~/.sapphire/logs/regime-collector.out
   curl -s https://sapphirealpha.xyz/api/brain/synthesis | jq '.trading_signals_24h, .degraded_silos'
   ```

6. **Verify BigQuery tables are getting fresh rows:**
   ```bash
   bq query --use_legacy_sql=false 'SELECT COUNT(*) FROM `tho-ai-agent.sapphire.trading_signals` WHERE TIMESTAMP_TRUNC(timestamp, DAY) = TIMESTAMP_TRUNC(CURRENT_TIMESTAMP(), DAY)'
   bq query --use_legacy_sql=false 'SELECT COUNT(*) FROM `tho-ai-agent.sapphire.market_regime` WHERE TIMESTAMP_TRUNC(timestamp, DAY) = TIMESTAMP_TRUNC(CURRENT_TIMESTAMP(), DAY)'
   ```

---

## 🛠️ HIGH: Enable Remote Login for Windows Agent Access

**Issue:** Windows agent cannot SSH to Mac. Port 22 is closed.
- Tailscale IP: `100.67.171.79`
- Local IP: `192.168.1.28`
- Tailscale ping works (4ms direct via `192.168.1.27:41641`)
- `Test-NetConnection -Port 22` fails

**Fix:**
```bash
# Enable Remote Login (SSH)
sudo systemsetup -setremotelogin on

# Verify sshd is listening
sudo lsof -i :22 | grep LISTEN

# Confirm Windows can reach it
# (Windows agent will verify automatically)
```

---

## 📊 MEDIUM: Run Canonical B1 Scan from Mac

The Windows-run B1 scan showed 26 FAILs — all Mac LaunchAgents. Run the canonical scan from the Mac to get an accurate baseline:

```bash
cd ~/Code/Sapphire
python3 scripts/ops/production_readiness_sweep.py --json | jq '.checks[] | select(.status=="WARN")'
```

Address any WARNs that are **not** environmental (i.e., not "service offline because Mac was asleep").

---

## ✅ VERIFICATION CHECKLIST

After completing the above, confirm:

- [ ] `curl http://127.0.0.1:9222/json/version` returns Chrome version
- [ ] `launchctl print gui/$(id -u)/com.sapphire.signal-logger` shows `state = running`
- [ ] `launchctl print gui/$(id -u)/com.sapphire.regime-collector` shows `state = running`
- [ ] Brain synthesis shows `trading_signals_24h > 0`
- [ ] Brain synthesis shows `degraded_silos` does **not** contain `trading`
- [ ] Windows agent can `ssh aribs@100.67.171.79`
- [ ] B1 scan shows ≤ 3 WARNs

---

## 📎 Context

- **Sapphire dashboard:** UX overhaul v2 deployed (rev 31). Markets hero rendering. `sapphirealpha.xyz` healthy.
- **THO portal:** Rate limiting + audit logging deployed (rev with SHA `a6f004a2`). `tho.sapphirealpha.xyz/healthz/` returns 200.
- **Windows services:** TV Agent, Webhook, Ollama all healthy. 29 models available.
- **Pi cluster:** Still degraded (inference tiers disabled). Out of scope for this handoff.

**End of handoff.**
