# Monorepo purge leftovers (flag-only)

Living inventory of paths reviewed during the Sapphire monorepo purge that must
**not** be mass-deleted without a follow-up audit. Archive-over-delete remains
policy; `scripts/archived/` is the in-git cold shelf (Proton/GCS cold-tier exit
needs re-verify — STRUCTURE T4).

Last updated: 2026-07-17 (purge slice 3).

## FLAG — do not delete this slice

| Path | Status | Why |
|---|---|---|
| `infra/terraform/legacy/` | Flag only | Explicitly labeled older experiments in `infra/terraform/README.md`; needs consumer grep + `terraform plan` context before exit |
| `services/hackathon_frontend/` | **Live public surface** | Served at https://hack.sapphirealpha.xyz/ — tests + frontend inventory refs; keep |
| `plugins/claw-sapphire/tools/_deprecated/kronos_predict.py` | Sunset window | Live shim `tools/kronos_predict.py` still routes here until **v0.5.0** (`infra/tool-registry.yaml`) |
| `scripts/archived/` (~94 files after slice 3) | In-git cold shelf | Do **not** mass-delete; Proton/GCS re-verify before cold-tier exit |
| `results/*.md` (2 April audit remnants) | Flag | Still cited by `docs/code-quality/todo-triage-2026-04-26.md`; cold-tier copy claimed 2026-04-28 — update refs then remove |
| `docs/archive/` | Intentional archive | Leave |
| `services/scout-sandbox/`, `services/megaeth-ingest/` | Low-ref demos | Consumer audit later; not auto-purge |
| Zero-ref `scripts/deploy/deploy_*.sh` (see below) | Operator entrypoints | Basename has no in-repo call-sites, but scripts still target real Cloud Run / edge jobs — inventory + runbook before archive |

## Zero-ref deploy wrappers (FLAG — not archived)

These deploy scripts have **zero basename references** outside themselves (grep
2026-07-17) but remain the likely one-shot operator path for live or paused
services. Do **not** cold-shelf without a deploy inventory + human confirm:

- `scripts/deploy/deploy_architecture_bottleneck_digest_job.sh`
- `scripts/deploy/deploy_command_deck.sh`
- `scripts/deploy/deploy_flowise_cloudrun.sh`
- `scripts/deploy/deploy_rari1_research_node.sh`
- `scripts/deploy/deploy_rari2_aster_worker.sh`
- `scripts/deploy/deploy_sapphire_aster.sh`
- `scripts/deploy/deploy_sapphire_lighter.sh`
- `scripts/deploy/deploy_sapphirebook_all.sh`
- `scripts/deploy/deploy_scout_sandbox.sh`
- `scripts/deploy/deploy_strategy_ops_digest_job.sh`
- `scripts/deploy/deploy_strategy_ops_snapshot_job.sh`
- `scripts/deploy/deploy_superswarm_rollup_job.sh`

Still documented / multi-ref (keep active): `deploy_sapphire_alpha.sh`,
`deploy_lighter_*`, `deploy_log_dashboard.sh`, `deploy_sapphirebook_{web,firebase}.sh`.

## Slice 3 archived (safe zero-ref ops tools)

git mv → `scripts/archived/` (no external call-sites, no tests, no LaunchAgent
labels, no Makefile targets):

1. `check_tradingview_cli.py` — one-shot CDP/LaunchAgent health probe
2. `probe_robinhood_browser.py` — Brave-session RH login probe
3. `probe_tdr_pro_browser.py` — Brave-session TDR Pro probe
4. `tv_cdp_cli.py` — repo-local CDP CLI wrapper (superseded by `tv` binary + other ops helpers)
5. `worktree_consolidation_report.py` — one-shot worktree/session inventory report

## Hard fences (never purge from this track)

- `data/`, `signals/`, decisions/ledgers, live service configs under active LaunchAgents
- Shared checkout `~/Code/Sapphire` live processes
- THO prod, Hermes gateway, money-path systems
