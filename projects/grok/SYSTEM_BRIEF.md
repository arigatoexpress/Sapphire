# Sapphire × Grok — System Brief

_Generated: 2026-08-06T20:12:06Z_

**Streamline score:** 8/8 (1.0)

## Next actions

- Plant: keep 30m grok-web-bridge LaunchAgent green
- Plant: reload rh-executor so gate_order is live in process
- Plant: upgrade genome to source=broker when fill prices available
- Win: run P0 acceptance before ARM L2
- Gemini: Phase 3 MC paint + data-truth UI (live pulse, stale honesty, operating rules)
- Plant: telemetry desk refresh via lib.grok.desk_projection each publish cycle
- GCP: cost posture min-instances=0 + Vertex idle skim

## Policy smoke

- ok: **True** · mandate: `free_reign_multi_rail`

## Genome

```json
{
  "count": 2,
  "wins": 1,
  "losses": 0,
  "blocked": 1,
  "realized_pnl_usd": 175.0
}
```

## Bridge

```json
{
  "export_count": 37,
  "by_day": {
    "2026-08-04": 1,
    "2026-08-05": 12,
    "2026-08-06": 24
  },
  "latest": [
    "2026-08-06_local-export_genome-closes-wired.md",
    "2026-08-06_lunch-autonomous-progress.md",
    "2026-08-06_operator-accept-gate-scope.md",
    "2026-08-06_plant-wire-receipt.md",
    "2026-08-06_public-trading-data-truth.md",
    "2026-08-06_system-brief.md",
    "2026-08-06_while-gemini-phase3.md",
    "2026-08-06_windows-datacenter-masterplan.md"
  ],
  "plant_wired": true,
  "mac_bridge_note": true,
  "mac_bridge_service": true,
  "plant_wire_receipt": true,
  "gate_wired": true,
  "genome_wired": true,
  "executor_reloaded": false,
  "gate_scope_accepted": true
}
```

## Windows DC

- p0_ok: False · arm_l2_allowed: False
- failed_p0: ['post_boot_report', 'tailscale_up', 'ssh_stable', 'ollama_aliases', 'no_sleep', 'free_reign_parity', 'schtasks_inventory']

## Critical alpha ↔ policy links

- `AU-05` **critical** — Hyperliquid hard caps + signing gate
  - fences: review_manually
- `SV-01` **critical** — Local-first authority boundary
  - fences: review_manually
- `SV-04` **critical** — Trading / mints / OAuth / prod cutovers at attended gates
  - fences: policy.evaluate_proposal rails rh_l2/rh_agentic
- `TR-AXTI` **critical** — AXTI playbook: defined-risk options + gamma scale-out
  - fences: policy.evaluate_scale_out / AXTI, windows.evaluate_windows_acceptance
  - action: After dust exits fill, stage 1–2 AXTI-class option probes (defined risk, ≤$35)
- `TR-DENS` **critical** — L2 dens: SONNY/BINGBONG class permanent
  - fences: policy.is_dens_blocked / DENS_BLOCK, policy.evaluate_proposal rails rh_l2/rh_agentic
- `TR-DUST` **critical** — Dust sleeve exits queued — do not re-place
  - fences: policy DUST_NO_REBUY
  - action: Confirm fills at RTH; then options-first only
- `SV-10` **critical** — Windows desktop is the private datacenter
  - fences: policy.is_dens_blocked / DENS_BLOCK, windows.evaluate_windows_acceptance
  - action: Implement Win DC ladder P0→P2; do not ARM until post-boot green
- `AU-10` **critical** — Agent harnesses over chat personas
  - fences: policy.is_dens_blocked / DENS_BLOCK, policy.evaluate_scale_out / AXTI, policy.evaluate_proposal rails rh_l2/rh_agentic, windows.evaluate_windows_acceptance, bridge exports + sync_grok_web_exports, genome.LessonBook
  - action: Close genome outcomes loop; daily research worker after smoke
- `OP-01` **critical** — Operator feed: free-reign L2 $10; MOSS grant expired
  - fences: policy.is_dens_blocked / DENS_BLOCK, policy.evaluate_proposal rails rh_l2/rh_agentic, policy MOSS_GRANT, policy DUST_NO_REBUY
  - action: Renew MOSS passkey grant; do not cancel dust exit sells
- `TR-PRESERVE` **critical** — Late-cycle day loss halt + options premium day cap
  - fences: policy.evaluate_scale_out / AXTI
  - action: Plant pass day_realized_pnl_usd and day_options_premium_usd into GateRequest
- `TR-HL` **critical** — Hyperliquid signing gate default disarmed in monorepo policy
  - fences: review_manually
  - action: Never ambient-arm HL from agents
- `PL-GATE` **critical** — Plant free-reign gate_order wired in telegram-bot executor (via=free_reign)
  - fences: policy.evaluate_proposal rails rh_l2/rh_agentic
  - action: Reload rh-executor process; monitor GATE DENIED logs

## Automations

- catalog: {'count': 13, 'by_status': {'live': 7, 'monorepo_ready_plant_pending': 1, 'paper_only_not_armed_until_p0': 1, 'read_only': 1, 'dry_run_default': 1, 'plant': 1, 'policy_in_monorepo': 1}} · resolved_in_repo: 11

- ✓ `grok-system-streamline` `live` — scripts/ops/grok_system_streamline.py
- ✓ `grok-mac-bridge-http` `live` — services/grok-bridge/
- ✓ `grok-web-bridge-launchagent` `live` — infra/launchagents/com.sapphire.grok-web-bridge.plist
- ✓ `grok-web-export-store` `live` — data/grok-web-exports/
- ✓ `sync-grok-web-exports` `monorepo_ready_plant_pending` — scripts/ops/sync_grok_web_exports.sh
- ✓ `grok-bridge-status` `live` — scripts/ops/grok_bridge_status.py
- ✓ `grok-loop-tick` `live` — scripts/ops/grok_loop_tick.py
- ✓ `gcp-cloudshell-bootstrap` `live` — scripts/ops/gcp_cloudshell_bootstrap.sh
- ✓ `win-research-worker` `paper_only_not_armed_until_p0` — scripts/windows_setup/run_research_worker.ps1
- ✓ `win-tv-agent` `read_only` — scripts/windows_setup/start_tv_agent.ps1
- ✓ `gemini-ooda-daily` `dry_run_default` — infra/launchagents/com.sapphire.gemini-ooda-daily.plist
- · `ralph-densify` `plant` — ops-state densify/Ralph loops

## Blindspots

- scoreboard: `{'count': 27, 'by_severity': {'P0': 7, 'P1': 13, 'P2': 7}, 'by_status': {'open': 13, 'recommended_accept': 1, 'resolved_plant': 3, 'encoded': 3, 'code_fixed_deploy_pending': 1, 'in_progress': 1, 'partial': 1, 'policy_ready_plant_pending': 1, 'blocked': 1, 'documented': 1, 'research': 1}, 'open_p0': ['BS-PUBLIC-DESK-STALE', 'BS-EXECUTOR-DEPLOY', 'BS-WIN-P0', 'BS-MOSS-GRANT'], 'gcp_leverage_top': ['Deploy dashboard SPA fix (no-traffic → verify JS MIME → traffic)', 'Cloud Run min-instances=0 + right-size memory', 'BQ warehouse for paper outcomes + regime digests (batch SQL)']}`

## Playbooks

- {'count': 7, 'ids': ['axti_options', 'hyperliquid_capped', 'l2_dust_experimental', 'late_cycle_preservation', 'moss_session', 'regime_aware_rsi_paper', 'tv_signal_spine'], 'ta_stack': ['ema_trend', 'rsi_14', 'macd', 'bollinger', 'volume']}


## Invariants

- Designated rails only: RH Agentic ••••8144, RH L2, MOSS/MegaETH (grant-gated), paper
- Models propose only — coordinator + first-party receipts authorize; no ambient spend/trade authority
- No THO / Project-Go-Forward money · Hermes messaging send · keys in model/git
- Dust-sleeve placer refuses; do not re-buy IBIT/HOOD/PLTR/NVDA dust; dens stay (SONNY/BINGBONG class)
- Paper/research/docs may advance; money paths refuse without exact gate / free-reign mandate
- Never archive paths named RETIRED without readlink / LaunchAgent WorkingDirectory check
- Never git add -A; report paths + diffs only
