# Ultimate Handoff Megaprompt — 2026-05-03 EOD

**Authoritative timestamp:** 2026-05-03 end-of-day.
**Author:** Claude Opus 4.7 (1M context), this autonomous closing session.
**Supersedes:** `ultimate-megaprompt-2026-05-03.md` + `outstanding-todos-2026-05-03.md` (both folded in below).
**Purpose:** any session — Mac, Windows, cloud routine — opening this file gets a complete current-state briefing in one read.

This is the file to scp to the Windows box. It contains every piece of state the next session needs to pick up cleanly, plus the operator action items only the user can complete.

---

## 0. Quick orientation

Three live workstreams across four repos:

| Workstream | Primary repo | Secondary repos | Status |
|---|---|---|---|
| **Sapphire OS** (autonomous trading + intelligence) | `~/Code/Sapphire` | hermes-agent, regional-intel-workbench | 5 open PRs, soak window for 3 cutovers |
| **wildfire-watch** (autonomous drone fire detection) | `~/Code/wildfire-watch` | Sapphire (bridge), hermes-agent (alert skill) | 3 open PRs, fire-chief demo pack ready |
| **THO** (Project-Go-Forward — Ari's mom Celeste's family business client) | `~/Code/Project-Go-Forward` | — | 10+ open PRs, prod rev > 100 |

Memory: `~/.claude/projects/-Users-aribs/memory/MEMORY.md`. Read it first if you don't have context.

---

## 1. Sapphire — current `main` HEAD

```
8f5825b2 docs(handoff): ultimate megaprompt + outstanding TODOs (2026-05-03)
5272e9ae chore: Pine analyzer — screener rules + --strict mode (#626)
6d53356d feat: Hermes skill stub for tradingview-orchestrator (deploy via copy) (#624)
```

### Open PRs (5)

| # | Title | Group |
|---|---|---|
| 627 | feat(sentinel): wire Pyth Hermes as primary price source in chain-health gate | sentinel + Pyth |
| 625 | feat(pyth): off-chain Hermes API integration | sentinel + Pyth |
| 623 | fix(sentinel): chain-health gate fails CLOSED on factory init exception | sentinel + Pyth |
| 621 | feat(cross-chain): Pyth oracle divergence detector + arb-backtest | cross-chain |
| 617 | feat(packaging): sapphire-sentinel-gate as standalone PyPI-ready package | packaging |

### Trading-critical-path (paused per autonomous-dispatch agreement)

Per memory: "broad autonomy → parallel Agent tasks + admin-squash-merge; reserve confirmation for trading critical path / secrets / kill switch."

- **Hyperliquid signing verification:** `policy.signing_verified=False` blocks mainnet. Run `python3 scripts/ops/verify_hyperliquid_signing.py [--testnet-order]` and flip the flag if it passes.
- **Robinhood live-capital posture:** still at $5/order cap, manual-only, crypto-only. 14-day Sortino soak still ticking. Stock automation still blocked.

### Soak-window cutover dates approaching

- **content-engine** soak collector — cutover ~2026-05-04
- **threat-refresh** soak collector — cutover ~2026-05-04
- **backtest-weekly** soak collector — cutover ~2026-05-24

`docs/ops/<routine>-runbook.md` for the cutover checklist.

### Sapphire infrastructure status

- **Mac (100.x.x.w)** commander, all services. ALL services healthy.
- **Windows PC (100.x.x.z)** RTX 5070 Ti, GPU stack. `:3001` telemetry-dashboard may be down — check `Get-ScheduledTask -TaskName 'SapphireDashboard'` from PowerShell.
- **Pi rari1 (100.x.x.x)** Tailscale ONLINE, Ollama working, SSH refused.
- **Pi rari2 (100.x.x.y)** Tailscale ONLINE, Ollama working.

Live counts: see `~/Code/Sapphire/CLAUDE.md` (canonical).

---

## 2. wildfire-watch — the new flagship project

`~/Code/wildfire-watch` — the user's "dream" project, scaffolded over 3 sessions. **Repo is public at https://github.com/arigatoexpress/wildfire-watch.**

### Live state

- **619 tests passing** (was 548 yesterday)
- **~24,000 LOC of Python** across 250+ files
- **35+ commits** since scaffolding
- **Mid-band valuation: $4.39M** (per `python -m valuation.cli snapshot`)
- **Anduril #1 acquirer fit (0.721)** — Korean Air wildfire-UAV partnership Apr 2026 + Palmer Luckey XPRIZE Wildfire finalist

### What shipped this session (2026-05-03)

| Module | Tests | Description |
|---|---:|---|
| `sapphire_integration/historical_fires/` | 16 | NIFC + MTBS + 6 other public sources; ArcGIS REST fetcher; offline 3-fire fixture |
| `lib/backtest/` | 17 | Counterfactual fire replay using Anderson 1982 fuel-model 4 ROS + Rothermel 1972 |
| `lib/forecast/` | 14 | Forward-projection scout-target ranker (fuel + history + small-zone bonus) |
| `docs/strategy/FIRE_CHIEF_DEMO_PACK.md` | n/a | The single document the operator brings to the CBFPD chief |
| `sapphire_integration/fuel_load/` (recovered) | 39 | 8 USFS / CO sources, classifier, pipeline (was rate-limited Q-1) |
| `ml/fire_detection/synth/` (recovered) | 28 | Procedural fire/smoke generator + YOLO dataset pipeline (was rate-limited Q-4) |
| `sim/demo/` (recovered) | 4 | Deterministic flight recorder + single-file HTML report (was rate-limited Q-3) |
| `SECURITY.md` + `docs/security/` (recovered) | n/a | STRIDE threat model across 7 surfaces (was rate-limited Q-2) |

### Open PRs

| # | Title | Status |
|---|---|---|
| 14 | feat(backtest+forecast): historic-fire replay + scout-target ranker — fire-chief demo pack | open, mergeable |
| 15 | feat: recover 4 rate-limited-agent partials | open, mergeable |
| 9 | chore(types): mypy on ml/fire_detection/ — first slice | open, CI re-run triggered |

### The demos the chief actually needs

```bash
cd ~/Code/wildfire-watch

# "On historic fires we'd have done this"
python -m lib.backtest.cli demo --trials 100
# 3 of 3 fires caught | mean 30.6 min to detection | 2,560 acres saved at ground response

# "And here's where I want to scout this season"
python -m lib.forecast.cli rank --year 2026 --use-fixture
# slate-river-drainage 76.4 -> every 12 min   <-- top priority
# cement-creek-drainage 55.9 -> every 18 min
# east-river-corridor 31.3 -> every 30 min
```

Both deterministic, sub-2-second runtime, all assumptions in `lib/backtest/engine.py` (Anderson 1982 + Rothermel 1972, public-domain federal sources).

### AOR

**Gunnison Valley + Crested Butte corridor, Gunnison County, Colorado.** Field elevation 7,700–9,000+ ft. High beetle-kill fuel load. Source of truth: `~/Code/wildfire-watch/AOR.md`. Phase-0 mission: `sim/missions/gunnison_slate_river_1km2.yaml`.

**West Elk Wilderness is hard no-fly per 36 CFR 261.16** — enforced in `sim/geofence.py` via the exclusion-polygon model.

### What's still pending (next sessions)

In rough priority:

1. **CBFPD outreach** (gated on operator)
2. **Smooth visualization with time-scrubber + side-by-side counterfactual view** (deferred from this session's P5)
3. **Distributed dynamic task allocation** in `sim/swarm/` (deferred from P4)
4. **Pi-side autonomy stack** runnable on rari1/rari2 + Mavic Mini SDK integration (deferred from P6)
5. **Gemini + Kimi delegation tools** for bulk research / vision validation
6. **3D terrain rendering** in the web viewer (Mapbox/MapLibre)
7. **Real beetle-kill polygon ingestion** from GMUG forest-health (the Q-1 fuel_load module is stubbed; needs real data fetch)
8. **v0.1.0 model training** — recipe at `ml/fire_detection/runs/v0.1.0/train_recipe.yaml` is `TRAINING_READY`. Needs FASDD + FLAME-2 datasets + GPU.

---

## 3. THO (Project-Go-Forward) — current state

`~/Code/Project-Go-Forward` — Ari's mom Celeste's family business client app. Cloud Run production.

### HEAD

```
896ed72 fix(ui): hide empty fields instead of rendering placeholders (#75)
b59a386 feat(inventory): analytics endpoint + admin panel (#76)
32900f2 feat(crm): lead source attribution endpoint + chart (#73)
```

### Open PRs (10+)

Top of stack: #83 CSP+rate-limits, #82 OpenTelemetry tracing, #81 CLAUDE.md freshness, #80 Twilio SMS, #79 DocuSeal bulk uploader, #78 SchemaTextBodyGuard middleware, #77 DocuSeal e-sign feasibility, #69 inventory scheduled-sync, #66 customer email confirmations, #65 per-user admin identity scaffold.

These are not autonomous-dispatch territory — they need operator review.

### Stakeholders

Per memory `project_tho_stakeholders.md`: Mom Celeste, Mark (Drive gate), Ben (CC'd), Etai Zilberman (Notion contractor — Ari's 4-question reply still unanswered as of last check).

---

## 4. Quick-reference repos

```
~/Code/Sapphire                    # commander, autonomous trading + intel
~/Code/wildfire-watch              # autonomous drone fire detection (THIS SESSION)
~/Code/Project-Go-Forward          # THO client app
~/Code/cyber-threat-bot            # threat intel feeds
~/Code/regional-intel-workbench    # vote monitor, intel platform
~/Code/Cointracker                 # crypto tax engine
~/Code/hermes-agent                # NousResearch Telegram bot framework
~/Code/claw-code                   # Rust agent runtime
```

All public domains hosted at `arigatoexpress.github.io`-shaped URLs. wildfire-watch is now public at github.com/arigatoexpress/wildfire-watch.

---

## 5. Operator TODOs — things only the user can do

In strict priority order. Each item lists impact + how to verify.

### Wildfire-watch (highest leverage)

1. **Email Crested Butte FPD Fire Chief.**
   - Address: 700 6th Street, Crested Butte, CO 81224 — phone (970) 349-5333.
   - Template: `~/Code/wildfire-watch/docs/outreach/emails/01_cbfpd_loa_request.md`.
   - Demo pack to attach: `~/Code/wildfire-watch/docs/strategy/FIRE_CHIEF_DEMO_PACK.md`.
   - Impact: signed LOA = +$3M to mid-band valuation (from `valuation/engine.py`).

2. **Apply for Foundry Developer Tier** (free, capacity-capped).
   - URL: https://www.palantir.com/foundry/build/
   - Impact: ontology axis +0.30 → Palantir score 0.54 → ~0.65.

3. **Buy Part 107 study guide** ($175) and book FAA Knowledge Test.
   - Impact: +$125k asset-floor + unlocks BVLOS waiver path.

4. **File LAANC pre-auth for KGUC class-E** (free).
   - Aloft / B4UFLY app on iPhone or web.
   - Impact: gates real flight inside 5nm of Gunnison airport.

5. **Land PR #14 + PR #15 in wildfire-watch** when CI finishes.
   - `gh pr merge 14 --squash --delete-branch`
   - `gh pr merge 15 --squash --delete-branch`
   - Impact: makes the new modules visible from main + the public README links work.

### Sapphire (medium leverage)

6. **Restart TradingView Desktop with CDP enabled.**
   ```bash
   open -a "TradingView" --args --remote-debugging-port=9222
   curl -s http://127.0.0.1:9222/json/version | jq .Browser
   ```
   Impact: `tv` CLI reconnects, 4-hourly capture LaunchAgent + daily Pine batch resume.

7. **Hermes wildfire-alert skill deployment** (one-time, after PR #15 lands).
   ```bash
   cp -R ~/Code/Sapphire/docs/hermes/skills/wildfire-alert ~/.hermes/skills/sapphire/wildfire-alert
   ~/.local/bin/hermes gateway restart
   ```

8. **Trigger Windows research-worker** (sweep showed stale).
   ```powershell
   Start-ScheduledTask -TaskName 'SapphireResearchWorker'
   ```

9. **Triage 27 missing artifact envelopes** (sweep WARN).
   ```bash
   python3 ~/Code/Sapphire/scripts/ops/production_readiness_sweep.py --json | jq '.checks[] | select(.name=="artifact_envelopes")'
   ```

10. **Review 5 Sapphire open PRs** (sentinel + Pyth chain). They need operator judgment.

11. **Hyperliquid signing verification** (when soak ready).
    ```bash
    python3 ~/Code/Sapphire/scripts/ops/verify_hyperliquid_signing.py --testnet-order
    ```

### THO (operator review)

12. **Review 10+ THO PRs.** The whole stack is non-autonomous-dispatch territory (CSP, observability, Twilio, DocuSeal). Operator only.

13. **Reply to Etai Zilberman** (THO Notion contractor — outstanding 4-question reply).

### Memory + admin

14. **Glance at the Sapphire kill switch state** if it's still engaged in a drill loop. Per memory rules I won't clear it without confirmation.
    ```bash
    cat ~/Code/Sapphire/data/.security_kill_switch_active 2>/dev/null && echo "STILL ENGAGED" || echo "clear"
    ```

15. **Push the wildfire-watch repo's branches** that are local-only (this session created `feat/historical-fire-backtest` + `feat/recovered-agent-partials` — both pushed to origin; verify in `gh pr list --state open --limit 5`).

---

## 6. Live valuation snapshot (wildfire-watch)

```
BAND: $0 – $8.31M  (mid $4.39M)  commit 32fad915
  comparable_multiples  $8.31M (archetype=computer-vision-defense, 26.5× implicit_revenue $313k)
  venture_method        $1.89M  (E[exit] $100M, P=7%, IRR=30%, 5y horizon)
  dcf_lite              $0      (LOAs=0, partners=0 — biggest gap)
  asset_floor           $3.45M  (19,968 novel LOC + 9,119 test LOC, 0 pilots)

Acquirer ranking:
  Anduril    0.721  (consensus_swarm=1.00, ndaa=1.00, intent=0.85 from R-1 research)
  Ondas      0.625  (drone_in_a_box_maturity=1.00)
  Kratos     0.566
  Red Cat    0.547
  Palantir   0.540  (would jump to ~0.65 with Foundry tier engagement)
```

The single highest-leverage move is operator-side: one CBFPD email = +$3M.

---

## 7. Memory pointers (read these for context)

In `~/.claude/projects/-Users-aribs/memory/`:

- `MEMORY.md` — index
- `feedback_autonomous_dispatch.md` — when autonomous dispatch is OK
- `feedback_full_autonomous_dispatch.md` — when full-system dispatch is OK
- `feedback_parallel_agent_worktree_per_lane.md` — concurrency hygiene
- `feedback_parallel_agent_stash_defense.md` — preservation of WIP
- `project_wildfire_watch_2026-05-01.md` — wildfire-watch project state (may be stale; this doc is more current)
- `project_full_dispatch_2026-05-02.md` — yesterday's full-system run
- `project_admin_frontends_2026-05-02.md` — wildfire.sapphirealpha.xyz live
- `project_palantir_pitch.md` — Foundry pitch background
- `project_hyperliquid_live_executor.md` — fail-closed defaults + activation gates

---

## 8. CLI cheat sheet (paste this into a Windows terminal too)

```bash
# wildfire-watch demos
cd ~/Code/wildfire-watch
python3 -m pytest -q --ignore=tests/integration -p no:warnings    # 619 passing
python3 -m sim.cli run sim/missions/gunnison_slate_river_1km2.yaml --scenario single_smoke_plume --speed-multiplier 50
python3 -m sim.swarm.cli run sim/missions/gunnison_slate_river_1km2.yaml --scenario consensus_smoke --drones 3 --k 2 --speed-multiplier 50
python3 -m sim.web.server          # → http://127.0.0.1:8088
python3 -m valuation.cli snapshot  # current intrinsic-value band
python3 -m valuation.web           # → http://127.0.0.1:8090
python3 -m lib.backtest.cli demo --trials 100   # historic-fire counterfactual replay
python3 -m lib.forecast.cli rank --year 2026 --use-fixture   # ranked scout-targets

# Sapphire core
cd ~/Code/Sapphire
make test                          # core unit tests
make ci                            # mirror GitHub Actions CI locally
python3 -m valuation.cli snapshot  # (this CLI also lives in wildfire-watch)
python3 scripts/ops/production_readiness_sweep.py --json

# Cross-repo PR queue
for repo in Sapphire wildfire-watch Project-Go-Forward; do
  echo "=== $repo ==="
  cd ~/Code/$repo && gh pr list --state open --limit 5
done
```

---

## 9. The single highest-leverage thing to do tomorrow

**Send the CBFPD email.** Template + attachment ready. The whole valuation engine + acquirer-fit research + 619-test repo + 24k LOC of code converges on that single action.

The email template:
```
~/Code/wildfire-watch/docs/outreach/emails/01_cbfpd_loa_request.md
```

The attachment:
```
~/Code/wildfire-watch/docs/strategy/FIRE_CHIEF_DEMO_PACK.md
```

The valuation impact: $3M to mid-band on a signed LOA.

The cost: a stamp.

---

**End of handoff.** Memory is fresh, repos are at HEAD, tests are green, demos are runnable. Pick up wherever.
