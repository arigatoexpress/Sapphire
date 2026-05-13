# Sapphire Autonomous Organization Control Tower

Sapphire is the command repo for the autonomous organization. This board keeps
the Core+Satellites scope explicit, tracks routine migration stages, and gives
Codex/Opus one shared operating surface before any production-adjacent change.

## Scope

The canonical scope lives in `infra/org-repos.yaml`.

Active classifications:

- `core`: Sapphire OS and THO production systems.
- `satellite`: actively used capability repositories.
- `integration`: upstream forks or local integrations used by Sapphire.
- `candidate_absorb`: overlapping systems to merge into a core or satellite repo.
- `candidate_archive`: stale or duplicative systems to freeze after inventory.

The active Core+Satellites set (as of 2026-05-12) is Sapphire, Project-Go-Forward,
cyber-threat-bot, regional-intel-workbench, tradingview-mcp-v2, and active
GCP/local runtime services. `claw-code`, `hermes-agent`, `tradingview-mcp` (original fork),
`Cointracker`, `kimi-tools`, and several vendor/reference clones were archived
2026-05-12 to `_Archive_2026-05-12/repo-quarantine-2026-05-12/`.

`infra/org-repos.yaml` also tracks an **upstream integration fleet** for
starred or locally integrated repositories that Sapphire depends on or uses as
architecture references. Each entry records the upstream repo, Ari fork, local
clone path, integration surface, and sync state. These repos are not
automatically production surfaces; runtime retargeting still requires a
dedicated PR and rollback notes.

## Status Commands

Use the status helper for a read-only snapshot:

```bash
python3 scripts/ops/org_status.py --no-external --markdown
python3 scripts/ops/org_status.py --markdown
python3 scripts/ops/org_status.py --output /tmp/sapphire-org-status.json
python3 scripts/ops/routine_soak_status.py --format markdown
```

`--no-external` skips `gh`, `gcloud`, `launchctl`, and Docker probes. It is the
CI-safe mode and the right first check when editing the manifest or report
shape. Dirty repository reporting is intentionally sanitized to counts by
porcelain status category; it does not print filenames or diff contents.
The local git worktree inventory still runs in `--no-external` mode so parallel
Codex/Claude/human lanes are visible before starting a new silo branch. When
external probes are skipped, the Open PR count is reported as `not checked`
rather than a confirmed zero.

Use `routine_soak_status.py` when deciding whether a remote-shadow routine has
enough scheduled GitHub Actions cycles to move from soak collection to artifact
review. It reads `infra/org-repos.yaml`, counts scheduled/manual workflow runs
since each routine's `started_at`, and reports gate progress without downloading
artifacts or printing raw run logs.

## Cluster Prompt And No-Spend CI

The canonical operator prompt for multi-agent production pushes is
`docs/org/autonomous-org-cluster-prompt.md`. Regenerate it after org manifest
changes with:

```bash
python3 scripts/ops/autonomous_org_prompt.py --output docs/org/autonomous-org-cluster-prompt.md
python3 scripts/ops/autonomous_org_prompt.py --check
```

The no-spend policy lives in `docs/org/no-spend-github-actions-strategy.md`.
Each active repo in `infra/org-repos.yaml` has a `ci_strategy` value so agents
can choose local CI, the Sapphire self-hosted runner gate, draft-only
auto-deploy handling, or upstream-fork local verification without guessing.
The org status report renders these strategy counts and the per-repo strategy
in the repo board.

## Current Waves

- **Wave 0: Control Tower** - in progress. Ship the manifest, status script,
  dashboard doc, and validation tests. No production behavior changes.
- **Wave 1: Routine Migration** - in progress. Weekly backtest and
  threat-refresh are soaking remotely while local routines remain canonical.
- **Wave 2: Repo Hardening** - in progress. TradingView MCP v2 guardrails are
  blocked on upstream PR review, and crypto-tax-tracker guardrails are complete
  via [arigatoexpress/crypto-tax-tracker#2](https://github.com/arigatoexpress/crypto-tax-tracker/pull/2).
- **Wave 3: Agent Consolidation** - **completed 2026-05-12.** `hermes-agent`, `claw-code`,
  `openclaw`, `kimi-tools`, and associated vendor clones were archived. Sapphire PM bot
  owns Telegram; agent dispatch is internal to Sapphire. Historical mapping doc:
  `docs/org/hermes-agent-consolidation-map.md`.
- **Wave 4: Data + Intelligence Platform** - in progress. Normalize schemas,
  Foundry, GCS, BigQuery, threat, regional, market, and chain intel flows.
  Regional-intel readiness now has a read-only OODA task and tracked
  GCS/BigQuery mapping metadata; runtime NDJSON and manifests remain ignored
  under `data/foundry/regional-intel/`.
- **Wave 5: Autonomy Safety** - in progress. Audit logging is wired for
  decision-engine and Kimi bridge autonomy requests; alpha full-autonomy
  dispatch defaults to dry-run, with code/GCP mutations disabled unless
  explicitly overridden. Cost posture reporting is read-only and flags warning
  log samples that hit the requested limit, grouped by service, severity, HTTP
  status, sanitized route category, and warning kind. Protected Cloud Run
  services such as `agentic-pm-hub` should keep unauthenticated public probes at
  `cloud_run_auth_required`; authenticated health checks remain the correct
  verification path.

## Routine Stages

- `local`: local LaunchAgent/service is canonical.
- `shadowing`: remote routine exists and produces comparable artifacts.
- `soaking`: shadow comparisons are being collected against cutover gates.
- `retired`: local routine has been disabled after shadow success and rollback
  notes exist.
- `blocked`: migration is intentionally paused on secrets, side effects, data
  parity, or safety decisions.
- `local_only`: no remote equivalent should be built until the surrounding
  system changes.

## First PR Queue

1. `feat/remote-threat-refresh-shadow` - soaking. First close-time comparison
   evidence is recorded in `docs/org/threat-refresh-shadow-soak-2026-04-26.md`;
   `scripts/ops/routine_soak_status.py` tracks scheduled cycle progress before
   disabling the local LaunchAgent.
2. `feat/remote-weekly-backtest-shadow` - soaking. First comparison evidence
   is recorded in `docs/org/backtest-weekly-shadow-soak-2026-04-26.md`; keep
   local weekly backtest canonical until scheduled cycles satisfy the cutover gate.
3. `infra/org-control-tower` - shipped. Manifest, read-only status script,
   control-board doc, and validation tests.
4. `chore/satellite-ci-parity-tradingview` - validated. Upstream PR
   [tradesdontlie/tradingview-mcp#102](https://github.com/tradesdontlie/tradingview-mcp/pull/102)
   adds AGENTS, CI, pre-commit parity, and offline test scripts; blocked on
   upstream maintainer merge.
5. `chore/repo-classification-report` - tracked in
   `infra/org-classification-report.yaml` and
   `docs/org/repo-classification-report.md`.
6. `feat/autonomy-audit-log` - tracked. Structured decision/alert audit logging
   lives in `docs/org/autonomy-audit-log.md`.
7. `chore/crypto-tax-hardening-tracked` - shipped. The
   crypto-tax-tracker satellite now has AGENTS/CLAUDE guidance, hard ruff and
   pytest CI, pre-commit parity, and README check commands.
8. `docs/hermes-consolidation-map` - shipped Wave 3 map. It records the
   difference between the Hermes development clone and the patched runtime
   checkout before any gateway update, fork, or hook migration.
9. `docs/kimi-tools-absorb-map` - shipped Wave 3 map. It records that
   `kimi-tools` has no live Sapphire import callers and Kimi fallback
   guardrails are now covered by Sapphire tests before any archive step.
10. `docs/hermes-sapphire-skill-surface` - shipped Wave 3 audit. It classifies
   all 15 Sapphire Hermes skills by blast radius before any consolidation,
   deletion, or template rewrite.
11. `infra/upstream-fleet-control` - updated 2026-05-12. Tracks OpenBB, Kronos, and
    tradingview-mcp-upstream with Ari fork/clone posture. OpenClaw, NemoClaw, Lumo,
    Hermes, Foundry/Palantir SDKs, FRED, charting, Goose, RTK, and career-ops
    were all archived 2026-05-12; see `infra/org-repos.yaml` `archived_repos` section.

## Safety Rules

- Treat the status script as read-only inventory. It must not edit GitHub,
  Cloud Run, LaunchAgents, Docker, Secret Manager, Firestore, GCS, DNS, or
  customer data.
- Do not print secret values, token contents, raw plist secrets, private keys,
  request bodies, or Secret Manager payloads.
- Keep production-adjacent repo changes on feature branches with PRs, CI, blast
  radius, test plan, and rollback notes.
- Local production services remain canonical until remote replacements pass
  documented shadow comparisons.
- Trading remains paper-only. Telegram tests use dry-run paths only.
