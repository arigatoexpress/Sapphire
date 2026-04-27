# Codex Handoff — 2026-04-27 Autonomous Window

A self-contained handoff for Codex picking up the system after Claude's
extended autonomous run. Codex started this window in the morning, hit
its usage limit at ~14:10 PT mid-PR, and Claude continued through the
afternoon under explicit autonomy from Ari.

Read this first when you return — every section is something you'd otherwise
have to reconstruct from `git log`, GitHub PR lists, and stale memory files.

## TL;DR

- **17 Sapphire PRs merged** end-to-end on `main` (last: #282
  control-plane event_stream tests). Tip is at HEAD `f9763a28`.
- **Cross-silo deployments**: regional-intel-workbench gained tests +
  collector resilience (PRs #5 and #6); cyber-threat-bot got 3 PRs
  (#3 timeouts, #4 severity tests, #6 latent-bug fixes) plus issue #5
  filed and closed; tradingview-mcp gained initial vitest scaffolding
  (#1 merged); THO landed 5 production-affecting PRs (#15-#19 from
  Codex morning + #20, #21, #23 from Claude afternoon + #22 in flight).
- **~520 new tests added** across all repos. Sapphire testbed grew
  most heavily.
- **No-spend gate held throughout**: every Sapphire PR was merged on
  local CI evidence (`scripts/ops/local_ci_verify.py`) with hosted
  Actions skipped via the `SAPPHIRE_RUNNER` guard. THO and other
  satellite repos were merged on hosted CI (THO autodeploys, so we
  cannot bypass).
- **Memory files updated**: see
  [`memory/project_2026-04-27_autonomous_window.md`](../../../../.claude/projects/-Users-aribs/memory/project_2026-04-27_autonomous_window.md)
  for the full PR ledger.

## 1. Where the codebase actually is

```
~/Code/Sapphire                     main @ f9763a28 (clean)
~/Code/Project-Go-Forward           main @ ff453725 (clean as of #21 merge,
                                                    #22 may be ahead)
~/Code/regional-intel-workbench     main @ a3225594 (clean; runtime data
                                                    file untracked)
~/Code/cyber-threat-bot             master @ cda66808 (clean)
~/Code/tradingview-mcp              master @ 3a468569 (clean)
~/Code/Cointracker                  unchanged — intentionally excluded
                                    (financial data, AGENTS.md cautions)
```

`~/Code/_worktrees/` should be empty after Claude finished cleanup;
verify with `git worktree list` from each repo. If you see leftover
THO-related worktrees they're inspection holds for the open PR(s).

## 2. PRs merged this window — Sapphire

`gh pr list --repo arigatoexpress/Sapphire --state merged --search "merged:>=2026-04-27" --limit 25`

| PR | Type | Module | Tests added |
|---|---|---|---|
| [#256](https://github.com/arigatoexpress/Sapphire/pull/256) | feat | investment intel source mesh | (Codex morning) |
| [#257](https://github.com/arigatoexpress/Sapphire/pull/257) | feat | sovereign thesis engine | (Codex morning) |
| [#258](https://github.com/arigatoexpress/Sapphire/pull/258) | chore | prevent paid Actions fallback | (Codex morning — the no-spend gate) |
| [#259](https://github.com/arigatoexpress/Sapphire/pull/259) | chore | refresh low-risk test deps | (Codex morning) |
| [#260](https://github.com/arigatoexpress/Sapphire/pull/260) | feat | deepen sovereign thesis evidence ledger | (Codex morning) |
| [#265](https://github.com/arigatoexpress/Sapphire/pull/265) | chore | refresh security test deps | (Codex morning) |
| [#266](https://github.com/arigatoexpress/Sapphire/pull/266) | feat | continuous intelligence work planner | (Codex morning) |
| [#267](https://github.com/arigatoexpress/Sapphire/pull/267) | feat | tokenization + agentic payments thesis | (Codex morning) |
| [#268](https://github.com/arigatoexpress/Sapphire/pull/268) | feat | continuous intelligence artifact sink | (Codex morning) |
| [#269](https://github.com/arigatoexpress/Sapphire/pull/269) | feat | continuous intelligence dashboard panel | (Codex morning) |
| [#270](https://github.com/arigatoexpress/Sapphire/pull/270) | fix | PM bot webhook secret | (Codex morning) |
| [#271](https://github.com/arigatoexpress/Sapphire/pull/271) | fix | media intent routing | (handoff bridge — Claude finished Codex's mid-air PR) |
| [#272](https://github.com/arigatoexpress/Sapphire/pull/272) | test | signal_logger webhook | 36 |
| [#273](https://github.com/arigatoexpress/Sapphire/pull/273) | test | sovereign_thesis helpers | 77 |
| [#274](https://github.com/arigatoexpress/Sapphire/pull/274) | test | dashboard thesis endpoints | 17 |
| [#275](https://github.com/arigatoexpress/Sapphire/pull/275) | test | continuous_intelligence_artifacts security guard | 67 |
| [#276](https://github.com/arigatoexpress/Sapphire/pull/276) | test | heartbeat 60s state machine | 39 |
| [#277](https://github.com/arigatoexpress/Sapphire/pull/277) | test | autonomy_audit security helpers | 58 |
| [#278](https://github.com/arigatoexpress/Sapphire/pull/278) | test | alpha_kill_switch_bridge + security_kill_switch | 15 |
| [#279](https://github.com/arigatoexpress/Sapphire/pull/279) | test | control-plane scoring | 47 |
| [#280](https://github.com/arigatoexpress/Sapphire/pull/280) | test | control-plane digest formatters | 39 |
| [#281](https://github.com/arigatoexpress/Sapphire/pull/281) | test | daily_brief pure helpers | 53 |
| [#282](https://github.com/arigatoexpress/Sapphire/pull/282) | test | control-plane event_stream JSONL log | 53 |

## 3. PRs merged this window — Cross-silo

### regional-intel-workbench

- [#5](https://github.com/arigatoexpress/regional-intel-workbench/pull/5) `/api/intel/recent` normalization tests + Foundry NDJSON deterministic ordering + provenance guard
- [#6](https://github.com/arigatoexpress/regional-intel-workbench/pull/6) Collector resilience: per-source timeouts + retry helper + failed-sources ledger. New env knobs: `REGIONAL_INTEL_SOURCE_TIMEOUT` (25s), `REGIONAL_INTEL_RETRY_LIMIT` (2), `REGIONAL_INTEL_RETRY_BACKOFF_BASE` (0.5s)

The repo's `data/regional_intel_history.jsonl` runtime file remains
modified locally and **must not be touched** — agents stash/pop it
during sync.

### cyber-threat-bot

- [#3](https://github.com/arigatoexpress/cyber-threat-bot/pull/3) Per-request timeouts (`CYBER_THREAT_BOT_TIMEOUT`, default 30s) + retry with exponential backoff
- [#4](https://github.com/arigatoexpress/cyber-threat-bot/pull/4) 48 severity-classification edge-case tests
- [issue #5](https://github.com/arigatoexpress/cyber-threat-bot/issues/5) filed for 3 latent behaviors flagged by the test additions (CVSS string-coerce, negative-score clamp, CVE-ID format validation)
- [#6](https://github.com/arigatoexpress/cyber-threat-bot/pull/6) Closed #5: hardened all 3 latent behaviors with WARNING-log on dropped/coerced entries. 78 tests pass (was 69 before)

Hosted Actions are blocked by GitHub billing on this repo — local
pytest is the merge evidence.

### tradingview-mcp

- [#1](https://github.com/arigatoexpress/tradingview-mcp/pull/1) Initial test infrastructure: `vitest@^2.1.8` (only new dep), `vitest.config.ts` (Node env, no DOM), `src/__tests__/pine-script.test.ts` (5 tests for `PineScriptService.validate`), `.github/workflows/ci.yml` (Node 20, npm install + npm test on push/PR), README testing section. **Default branch is `master`, not `main`.**

### Project-Go-Forward (THO) — production-adjacent

THO is the highest-stakes silo: every merge to `main` auto-deploys to
Cloud Run. AGENTS.md normally requires explicit human approval per PR;
Ari granted blanket authority for this window's merges.

| PR | Behavior change | Notes |
|---|---|---|
| [#15-#19](https://github.com/arigatoexpress/Project-Go-Forward/pulls?q=is:pr+is:merged) | Codex morning batch | fail-closed admin, doc-center lookup, JSON 404, inventory reconcile, live inventory context |
| [#20](https://github.com/arigatoexpress/Project-Go-Forward/pull/20) | Inventory Pydantic validators | Soft validation (warn-log, never blocks live sync) |
| [#21](https://github.com/arigatoexpress/Project-Go-Forward/pull/21) | Resilient JSON error envelope | `/api/*` errors now `{success, status_code, message}`; Cache-Control max-age=3600 on inventory GETs, no-cache elsewhere; `/api/v1/*` partner contract preserved |
| [#22](https://github.com/arigatoexpress/Project-Go-Forward/pull/22) | Deal pre-validation | New `database/deal_validation.py`; `POST /api/deals/{id}/generate-document` returns 400 `{error: "missing_required_fields", missing: {...}}` for incomplete deals **before** doc engine runs. **CI initially failed** because tests imported `main` which spins up Firestore at module load; Claude's fix mocks `google.cloud.firestore.Client` globally before the import. See section 6 for the gotcha. |
| [#23](https://github.com/arigatoexpress/Project-Go-Forward/pull/23) | Frontend testing proposal docs | Vitest + Testing Library + jsdom recommendation; no code, no deps, awaits framework decision |

Live site: https://sapphirealpha.xyz/. Production state at handoff:
revision 26+, 43 live homes, browser-verified by morning agents.

## 4. Patterns established this window — copy these forward

### 4.1 No-spend SAPPHIRE_RUNNER gate (Sapphire)

The CI workflow now skips every job when `SAPPHIRE_RUNNER` is unset on
the Actions runner (PR #258, "Prevent paid Actions fallback"). Local
verification is the merge evidence. Use:

```bash
uv run --python 3.11 --no-project --with-requirements requirements-test.txt \
  env PYTHON3=python python scripts/ops/local_ci_verify.py --verbose
```

Then merge via the GitHub API path (NOT `gh pr merge`) to avoid
multi-worktree conflicts:

```bash
gh api -X PUT repos/arigatoexpress/Sapphire/pulls/N/merge \
  -f merge_method=squash \
  -f commit_title="..." \
  -f commit_message="Local CI PASS on <sha>; hosted Actions skipped by no-spend gate."
```

### 4.2 Module-name collision pattern (control-plane app vs dashboard app)

Two services both call their package `app`:

- `services/dashboard/app.py` (single .py file) — already on
  `sys.path` via the shared `tests/conftest.py`, used by
  `test_sensitivity_filter.py` etc.
- `services/control-plane/app/` (package) — needed by control-plane
  tests but its `app.models` import collides with dashboard's `app.py`.

**The pattern (see PRs #279, #280, #282):** wrap the control-plane
imports in a `_control_plane_app_namespace()` context manager that
swaps `sys.modules["app"]` for the duration of the import block, then
restores the prior state. Captured names (e.g. `from app.scoring import
score_news`) keep working because they reference the module objects
directly. Without this, every control-plane test would break unrelated
dashboard tests.

### 4.3 GCP Application Default Credentials in tests (THO #22 gotcha)

`main.py` instantiates Firestore-backed services
(`ConversationMemory`, `ChatHistory`, `LeadManager`,
`AppointmentManager`, plus `_db = get_database()`) at import time.
Each calls `firestore.Client(project=...)` eagerly, which triggers
Google ADC. CI has no ADC.

**The pattern (THO #22 fix):** before `importlib.import_module("main")`,
patch `google.cloud.firestore.Client` to a no-op stub class:

```python
from google.cloud import firestore as _firestore_module
class _FakeFirestoreClient:
    def __init__(self, *args, **kwargs):
        pass
    def collection(self, *args, **kwargs):
        raise RuntimeError("Tests must not exercise live Firestore queries")
monkeypatch.setattr(_firestore_module, "Client", _FakeFirestoreClient)
```

This is lighter than the full `sys.modules` fakery in
`tests/test_api_v1.py` and works for the slim set of endpoint tests.

### 4.4 Worktree-per-PR with cleanup discipline

Every test PR was developed in
`~/Code/_worktrees/sapphire-<feature>` and removed after merge with:

```bash
git worktree remove ~/Code/_worktrees/sapphire-<feature> --force
git branch -D <branch-name>
```

Branches were force-deleted even after squash-merge because the local
branch tip diverges from the squashed commit on main. Never
`git worktree remove` without confirming `git status --short` is clean.

### 4.5 PR creation, evidence comment, then API merge

```bash
gh pr create --repo arigatoexpress/Sapphire --base main --head <branch> \
  --title "..." --body-file /tmp/pr-body.md
sleep 6  # let GitHub compute mergeable_state
gh api -X POST repos/arigatoexpress/Sapphire/issues/N/comments \
  -f body="Local CI Verify PASS at HEAD <sha>. Hosted Actions skipped..."
gh api -X PUT repos/arigatoexpress/Sapphire/pulls/N/merge \
  -f merge_method=squash -f commit_title="..." -f commit_message="..."
```

Always paste local CI verifier output in the PR body AND in the
evidence comment. The body is the durable record; the comment is the
gate decision rationale.

## 5. Recurring scheduled agents still armed

Two RemoteTrigger routines from the 2026-04-26 evening window are still
active:

- `trig_019rrxazJyygbUV3QjKCDRd3` — daily 13:00 UTC content-engine soak
  collector. Reads `docs/ops/content-engine-soak-runbook.md`. Opens
  cycle PRs.
- `trig_01QpjB7rvRXbinMoBmaTtHD8` — weekly Monday 14:00 UTC mission
  status digest. Reads `docs/ops/mission-status-digest-runbook.md`.
  Opens a `mission-digest`-labelled GitHub issue per week.

Don't re-arm these. Verify they exist with the RemoteTrigger `list`
action before assuming.

## 6. Known-stale doc / behavior notes

- **CLAUDE.md** in the Sapphire root says **"Key counts (verified
  2026-04-26): 2,287 passing tests"**. After this window the count is
  ~2,807 (2,287 + ~520 new). Bump it the next time you touch
  `CLAUDE.md`.
- **`docs/ops/codex-lead-operating-model.md`** is from Codex's earlier
  pass and still applies — defaults to local-CI-as-evidence and
  admin-merge for tests/docs.
- **Issue [#220](https://github.com/arigatoexpress/Sapphire/issues/220)**
  documents the GitHub Actions billing block. Still open; the
  `SAPPHIRE_RUNNER` gate is the ongoing workaround. If billing gets
  settled, flip the gate by setting the runner env var.
- **THO `tho_documents/`** contains regulatory PDFs — never modify
  these.
- **THO `database/models.py`, `tools/inventory_sync.py`,
  `database/deal_validation.py`, the global exception handler block in
  `main.py`** were all touched by PRs #20-#22 — if you re-open a worktree
  on any of these check for stale state first.
- **cyber-threat-bot** still has the GitHub billing block. The
  `Run unit tests (no Firestore/GCS)` job runs locally fine but fails
  in CI for billing reasons. Local pytest is the merge evidence.
- **regional-intel-workbench** has no SAPPHIRE_RUNNER-style gate. Its
  hosted CI fails on billing too. Cancel runs via `gh run cancel <id>`
  after pushing if you want to be tidy; merge on local evidence.
- **The runtime file `data/regional_intel_history.jsonl`** in
  regional-intel-workbench's main checkout is locally modified but not
  committed; do not touch it during sync.

## 7. Open / outstanding items

### Open at handoff time

- [THO #22](https://github.com/arigatoexpress/Project-Go-Forward/pull/22) —
  fix-pushed (commit `c83dba6`), CI re-running. If green, merge with:
  ```bash
  gh api -X PUT repos/arigatoexpress/Project-Go-Forward/pulls/22/merge \
    -f merge_method=squash \
    -f commit_title="feat(deals): pre-validate deal data before document generation (#22)" \
    -f commit_message="..."
  ```
  If still red, inspect with `gh run view <run-id> --log-failed`.

### Decisions Ari needs to make on return

- **THO frontend testing framework** — PR #23 proposed Vitest + Testing
  Library + jsdom. Awaits Ari's signoff before a follow-up PR installs
  the deps and adds the first 8 InventoryBrowse component tests.
- **Cyber-threat-bot billing** — issue #220 (Sapphire) parallels: the
  bot needs the same no-spend gate or its billing settled.
- **Regional-intel CI billing** — same. Adopt the SAPPHIRE_RUNNER
  pattern or settle billing.

### Next-best work in the queue

- **Sapphire docs** — `lib/agents/runner.py` and `lib/agents/alpha_agent.py`
  already have tests; `lib/agents/base.py` (156 lines) does not.
- **Sapphire trading** — Codex's earlier "paper-trading enforcement at
  predict.py" idea was rejected by Claude on review (predict() is
  read-only TA, not the right enforcement layer). Don't re-litigate.
- **Sapphire `services/intelligence/analytics.py` (17.9K) and
  `optimize.py` (14.4K)** — both untested. `daily_brief.py` got pure
  helpers covered (#281); the section builders need mocks for live
  intel sources.
- **Sapphire `services/control-plane/app/`** — `news.py` (3.7K) and
  `sources.py` (1.7K) are still untested. `event_stream.py` (179 LOC)
  was covered in #282; `digest.py` in #280; `scoring.py` in #279.
  `models.py` is small dataclasses (no tests needed). `main.py` (64K),
  `control_plane.py` (114K), `project_board.py` (54K), and
  `storage.py` (12K) are massive and would need integration mocking.
- **THO** — frontend test wave (after #23 framework decision) is the
  natural next chunk.

## 8. How to pick up cold

```bash
# Sync everything
for r in ~/Code/Sapphire ~/Code/Project-Go-Forward \
         ~/Code/regional-intel-workbench ~/Code/cyber-threat-bot \
         ~/Code/tradingview-mcp; do
  echo "=== $r ==="
  git -C "$r" fetch --all --prune --quiet
  git -C "$r" status --short --branch
  git -C "$r" worktree list
done

# Look for any abandoned worktrees
ls ~/Code/_worktrees/

# Confirm scheduled remote agents
# (use the ccsdk RemoteTrigger list action)

# Check open PRs across silos
for r in arigatoexpress/Sapphire arigatoexpress/Project-Go-Forward \
         arigatoexpress/regional-intel-workbench \
         arigatoexpress/cyber-threat-bot arigatoexpress/tradingview-mcp; do
  echo "=== $r ==="
  gh pr list --repo "$r" --state open --json number,title,isDraft --limit 5
done
```

## 9. Reference: full session memory

Detailed PR ledger, commit SHAs, and tests-added counts:
[`memory/project_2026-04-27_autonomous_window.md`](../../../../.claude/projects/-Users-aribs/memory/project_2026-04-27_autonomous_window.md)

Architecture snapshot of the broader Sapphire system:
[`memory/sapphire_v03_architecture.md`](../../../../.claude/projects/-Users-aribs/memory/sapphire_v03_architecture.md)

Multi-agent dispatch playbook (when Ari is gone):
[`memory/feedback_full_autonomous_dispatch.md`](../../../../.claude/projects/-Users-aribs/memory/feedback_full_autonomous_dispatch.md)

The previous Codex window's status doc, for the pattern of how these
handoffs are structured:
[`docs/status/2026-04-26-evening-autonomous-window.md`](2026-04-26-evening-autonomous-window.md)
