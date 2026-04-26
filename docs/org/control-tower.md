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

The initial Core+Satellites set is Sapphire, Project-Go-Forward, claw-code,
cyber-threat-bot, regional-intel-workbench, tradingview-mcp,
tradingview-mcp-v2, crypto-tax-tracker/Cointracker, hermes-agent, and active
GCP/local runtime services.

## Status Commands

Use the status helper for a read-only snapshot:

```bash
python3 scripts/ops/org_status.py --no-external --markdown
python3 scripts/ops/org_status.py --markdown
python3 scripts/ops/org_status.py --output /tmp/sapphire-org-status.json
```

`--no-external` skips `gh`, `gcloud`, `launchctl`, and Docker probes. It is the
CI-safe mode and the right first check when editing the manifest or report
shape.

## Current Waves

- **Wave 0: Control Tower** - in progress. Ship the manifest, status script,
  dashboard doc, and validation tests. No production behavior changes.
- **Wave 1: Routine Migration** - in progress. Weekly backtest and
  threat-refresh are shadowing remotely while local routines remain canonical.
- **Wave 2: Repo Hardening** - in progress. TradingView MCP v2 guardrails are
  blocked on upstream PR review, and crypto-tax-tracker guardrails are complete
  via [arigatoexpress/crypto-tax-tracker#2](https://github.com/arigatoexpress/crypto-tax-tracker/pull/2).
- **Wave 3: Agent Consolidation** - in progress. Map Hermes, claw-code, Sapphire
  plugins, Claude scheduled tasks, OpenClaw remnants, and LaunchAgents. Hermes
  runtime mapping is documented in `docs/org/hermes-agent-consolidation-map.md`.
- **Wave 4: Data + Intelligence Platform** - queued. Normalize schemas,
  Foundry, GCS, BigQuery, threat, regional, market, and chain intel flows.
- **Wave 5: Autonomy Safety** - queued. Finish audit logging, confirmation
  firewall, feedback loops, cost reporting, and dry-run defaults.

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

1. `feat/remote-threat-refresh-shadow` - shipped. Keep collecting shadow
   artifacts before disabling the local LaunchAgent.
2. `infra/org-control-tower` - current PR. Manifest, read-only status script,
   control-board doc, and validation tests.
3. `chore/satellite-ci-parity-tradingview` - validated. Upstream PR
   [tradesdontlie/tradingview-mcp#102](https://github.com/tradesdontlie/tradingview-mcp/pull/102)
   adds AGENTS, CI, pre-commit parity, and offline test scripts; blocked on
   upstream maintainer merge.
4. `chore/repo-classification-report` - tracked in
   `infra/org-classification-report.yaml` and
   `docs/org/repo-classification-report.md`.
5. `feat/autonomy-audit-log` - tracked. Structured decision/alert audit logging
   lives in `docs/org/autonomy-audit-log.md`.
6. `chore/crypto-tax-hardening-tracked` - current bookkeeping PR. The
   crypto-tax-tracker satellite now has AGENTS/CLAUDE guidance, hard ruff and
   pytest CI, pre-commit parity, and README check commands.
7. `docs/hermes-consolidation-map` - current Wave 3 map. It records the
   difference between the Hermes development clone and the patched runtime
   checkout before any gateway update, fork, or hook migration.
8. `docs/kimi-tools-absorb-map` - current Wave 3 map. It records that
   `kimi-tools` has no live Sapphire import callers and Kimi fallback
   guardrails are now covered by Sapphire tests before any archive step.
9. `docs/hermes-sapphire-skill-surface` - current Wave 3 audit. It classifies
   all 15 Sapphire Hermes skills by blast radius before any consolidation,
   deletion, or template rewrite.

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
