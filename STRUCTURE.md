# Sapphire Repository Structure

This file is the canonical map for what belongs in the Sapphire monorepo.
It is intentionally operational: every top-level path has an owner, a retention
policy, and a rule for what must not drift into it.

## Operating Rules

- Git is for source, contracts, schemas, tests, runbooks, and reproducible
  generators. Runtime data, secrets, generated builds, and large binary
  artifacts belong in a storage tier outside git.
- `data/` may contain tracked reference data and schemas only. Hot runtime
  state remains gitignored and should age out through the storage-tier sync
  workflow.
- `tools/` is source-only. Build output such as Swift `.build/`, `dist/`, and
  compiled bundles must stay ignored or move to an artifact tier.
- New top-level paths require an update to this file in the same PR.

## Canonical Top-Level Directories

<!-- canonical-top-level-dirs:start -->
- `.claude/` — Claude/Codex helper instructions and skill references; tracked
  safety policy only, no local tokens. Retention: git.
- `.github/` — GitHub metadata and no-spend CI wiring. Retention: git.
- `agents/` — local agent configs and lightweight agent entrypoints. Retention:
  git for config; runtime output belongs in `data/` hot state.
- `clients/` — thin client adapters for adjacent systems. Retention: git.
- `config/` — non-secret runtime policies and examples. Retention: git.
- `contracts/` — Solidity/payment/verification contracts. Retention: git.
- `data/` — tracked reference data plus gitignored hot/warm local runtime
  artifacts. Retention: mixed; see `docs/ops/storage-tier-architecture.md`.
- `deploy/` — deployment helpers and service definitions. Retention: git.
- `docs/` — current runbooks, architecture, diligence, and dated reports.
  Retention: git for current docs; stale audits move to `docs/archive/`.
- `examples/` — small runnable product-surface examples that demonstrate
  public APIs without runtime secrets or external mutations. Retention: git.
- `infra/` — LaunchAgents, registries, org manifests, and cloud templates.
  Retention: git, no secret payloads.
- `lib/` — reusable Sapphire libraries and product kernels. Retention: git.
- `patches/` — small reviewable patch artifacts. Retention: git while active;
  stale patches move to `docs/archive/` or the cold tier.
- `pine/` — TradingView Pine scripts and related docs. Retention: git.
- `plugins/` — `claw-sapphire` plugin tools, tests, and registrations.
  Retention: git.
- `results/` — dated generated report remnants. Retention: deprecated in git;
  new generated results belong in `artifacts/` or cold storage.
- `scripts/` — operator scripts, CI helpers, deploy wrappers, and generators.
  Retention: git.
- `services/` — deployable services and service-owned LaunchAgents. Retention:
  git for source/config; logs and state are external.
- `skills/` — local skill packages and operator skill docs. Retention: git for
  source; generated skill output belongs in artifacts.
- `tests/` — unit, integration, fixtures, and static guardrail tests.
  Retention: git; caches ignored.
- `tools/` — source for standalone tools. Retention: git source only; build
  directories are generated artifacts.
<!-- canonical-top-level-dirs:end -->

## Canonical Top-Level Files

<!-- canonical-top-level-files:start -->
- `.editorconfig`
- `.env.integrations.example`
- `.eslintrc.cjs`
- `.firebaserc`
- `.gcloudignore`
- `.gemini_placeholder`
- `.git-secrets-patterns`
- `.gitattributes`
- `.gitignore`
- `.gitleaks-docs.toml`
- `.gitleaks.toml`
- `.mcp.json`
- `.pre-commit-config.yaml`
- `.sops.yaml`
- `AGENTS.md`
- `CLAUDE.md`
- `CONTRIBUTING.md`
- `GEMINI.md`
- `LICENSE`
- `Makefile`
- `README.md`
- `SAPPHIRE_PROMPT.md`
- `SECURITY.md`
- `STRUCTURE.md`
- `SYSTEM_UPGRADE_PLAN.md`
- `env.example`
- `foundry.toml`
- `pyproject.toml`
- `requirements-test.txt`
<!-- canonical-top-level-files:end -->

## Retention Summary

| Path family | Tier | Retention rule |
|---|---|---|
| Source, tests, schemas, docs | T1 git | permanent while current; archived docs stay indexed |
| `data/health`, `data/metrics`, `data/chain`, `data/intelligence/latest` | T2 hot local | 7 days unless promoted to GCS/BigQuery |
| `data/backtests`, `data/content`, recent security/soak evidence | T2 warm local | 30-90 days, then compress or promote |
| `results/`, generated benchmarks | T4 cold backup candidate | copy to Proton/GCS cold before git removal |
| THO customer docs and contracts | T5 Google Drive | never mirrored into Sapphire git |

## Review Checklist

1. Does a new file belong under an existing top-level path?
2. If it is generated, can it be recreated from tracked source?
3. If it contains customer data, runtime state, or secrets, why is it in git?
4. If a new top-level path is unavoidable, update this file and
   `scripts/ops/check_repo_structure.py` evidence in the same PR.
