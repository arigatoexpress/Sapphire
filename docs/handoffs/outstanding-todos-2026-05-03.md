# Outstanding TODOs for the operator — 2026-05-03

Things this overnight autonomous run could not do, and that need you. Ordered by impact.

---

## 1. Restart TradingView Desktop on the Mac with CDP enabled

**Why:** sweep WARN `local/tradingview_cdp_version` URLError. The `tv` CLI can't reach `:9222`, so the 4-hourly capture LaunchAgent and the daily Pine batch are running blind right now.

**Action:**
```bash
# Quit TradingView Desktop, then relaunch with the debugger flag:
open -a "TradingView" --args --remote-debugging-port=9222
# Verify:
curl -s http://127.0.0.1:9222/json/version | jq .Browser
```

The `com.sapphire.tradingview-cdp` LaunchAgent should have started TV with that flag — check with `launchctl print gui/$(id -u)/com.sapphire.tradingview-cdp` if it didn't.

## 2. Bootstrap the cache LaunchAgent on a fresh login (already done this session, but if you reboot)

```bash
launchctl bootstrap gui/$UID ~/Library/LaunchAgents/com.sapphire.readiness-cache.plist
launchctl bootstrap gui/$UID ~/Library/LaunchAgents/com.sapphire.tradingview-pine-batch.plist
launchctl list | grep com.sapphire
```

The `com.sapphire.readiness-cache` agent (15-min cadence) feeds `/api/readiness/latest` on the dashboard.

## 3. Deploy the Hermes skill (one-time)

The TradingView orchestrator skill template is in the repo at `docs/hermes/skills/tradingview-orchestrator/`. Hermes loads skills from `~/.hermes/skills/sapphire/`.

```bash
cp -R ~/Code/Sapphire/docs/hermes/skills/tradingview-orchestrator \
      ~/.hermes/skills/sapphire/tradingview-orchestrator
~/.local/bin/hermes gateway restart
```

Then test from Telegram: "what's the latest TA score for ETH?" — should hit the new skill.

## 4. Fix the Windows :3001 telemetry dashboard

**Why:** sweep WARN `windows/telemetry_dashboard_tcp` TimeoutError. Other Windows ports (8081/9090/SSH/Ollama) are healthy; only :3001 is unreachable. Likely the `SapphireDashboard` Scheduled Task on Windows is stopped.

```powershell
# On Windows (or via SSH):
Get-ScheduledTask -TaskName 'SapphireDashboard' | Select-Object TaskName, State
Start-ScheduledTask -TaskName 'SapphireDashboard'
```

## 5. Trigger a research-worker run on Windows

**Why:** sweep WARN `windows/research_worker_freshness` is at sha `22b243e` from 2026-05-02 — stale. The next scheduled run will clear it, but if you want it now:

```powershell
# On Windows:
Start-ScheduledTask -TaskName 'SapphireResearchWorker'
```

## 6. Triage the 27 missing artifact envelopes

**Why:** sweep WARN `provenance/artifact_envelopes` — `checked=444; missing_or_invalid=27`. Parallel-workstream PRs (#604–#613, #621, etc.) shipped artifacts under `data/` without provenance envelopes. Not my work to fix.

```bash
# Find which artifacts are missing envelopes:
python3 ~/Code/Sapphire/scripts/ops/production_readiness_sweep.py --json | jq '.checks[] | select(.name=="artifact_envelopes")'
```

Then either backfill the envelopes (preferred) or accept the WARN until the originating PRs add them.

## 7. Review the 29 open PRs

Most are from the parallel autonomous workstreams (Pyth oracles, GMX panel, sentinel patches, cross-chain arb, frontends). They need your judgment, not mine.

```bash
gh pr list --state open --limit 30
```

Notable groups:
- **Sentinel + Pyth:** #623, #625, #627 (chain-health gate hardening + Hermes API integration)
- **Cross-chain arb:** #621, #606 (Pyth divergence detector + Aave APY arb backtest)
- **Multi-chain:** #608–#613 (Optimism Pyth, GMX panel, Slither patches, bridge calibration, Arbitrum Pyth)
- **Packaging:** #617 (sentinel-gate as standalone PyPI package)
- **Docs:** #604, #607 (CLAUDE.md tight-refresh — likely conflicts with my #620; grant drafts)

## 8. Trading-critical-path follow-ups (paused per the autonomous-dispatch agreement)

Memory says: "broad autonomy → parallel Agent tasks + admin-squash-merge; reserve confirmation for trading critical path / secrets / kill switch". I did not touch these:

- **Hyperliquid signing verification:** `policy.signing_verified=False` blocks mainnet. Run `python3 ~/Code/Sapphire/scripts/ops/verify_hyperliquid_signing.py [--testnet-order]` and flip the flag if it passes.
- **Robinhood live-capital posture:** still at $5/order cap, manual-only, crypto-only. 14-day Sortino soak ticking. Stock automation still blocked.
- **Robinhood/Hyperliquid live executions:** never auto-triggered.

Decide each based on your soak-window evidence.

## 9. Routine cutover dates approaching

- **content-engine** soak collector — cutover ~2026-05-04 (tomorrow). After cutover, retire the local mirror.
- **threat-refresh** soak collector — cutover ~2026-05-04. Same.
- **backtest-weekly** soak collector — cutover ~2026-05-24.

`docs/ops/<routine>-runbook.md` for the cutover checklist.

## 10. Memory file additions you may want to review

The 2026-05-03 memory consolidation pass 2 made these changes:
- Updated `reference_tradingview_orchestrator_surface.md` (HEAD bumped, new surfaces added)
- Updated `project_2026-04-30_night_session_final.md` with snapshot marker
- Created `feedback_parallel_agent_shared_checkout_salvage.md` (new pattern from PR #615 salvage)
- Tightened MEMORY.md hooks for `feedback_autonomous_dispatch.md` vs `feedback_full_autonomous_dispatch.md` (kept split, sharper trigger phrases)

Review at `~/.claude/projects/-Users-aribs/memory/` if you want to vet.

## 11. Things I noticed but didn't act on

- **Test inventory drift on README.md** (not CLAUDE.md): `--check-readme` flagged `total -75, unit -103, plugin +28, files -2` between README and live counts. CLAUDE.md is fresh; README needs a bump.
- **`docs/claude-md-tight-refresh` PR #604** likely conflicts with my #620 since both refresh CLAUDE.md. Whoever merges last needs to rebase.
- **regional-intel-workbench** has a runtime data file dirty (`data/regional_intel_history.jsonl`). Probably runtime accumulation, not source. If it accumulates indefinitely, consider rotating it like the other data files.

## 12. Things I asked for but never got

None blocking. The autonomous run had everything it needed via memory + repo conventions.

---

**End of TODOs.** When in doubt, `docs/handoffs/ultimate-megaprompt-2026-05-03.md` has the full state.
