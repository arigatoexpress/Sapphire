# ADR 0001 — No-spend posture for autonomous CI

- **Status**: accepted
- **Date**: 2026-04-26 (originally), codified 2026-04-29
- **Authors**: Ari (operator), Sapphire ops
- **Related**: PR #388 (the PR that exposed the gap), `scripts/ops/sapphire_safe_merge.sh`, ADR 0002

## Context

Sapphire CI is a heavy-cost surface: ruff + pytest (≥ 5,000 cases) + plugin pytest
+ tool-registry validator + gitleaks + bandit, on every push, every PR, every
Dependabot bump. With autonomous Codex + Claude tranches landing 8-12 PRs per
night, hosted-runner cost compounds quickly. On 2026-04-26 a billing block hit
GitHub Actions (issue #220) from cumulative hosted runs.

Three patterns drive cost:

1. **Hosted runners on PR pushes** — `.github/workflows/ci.yml` triggers default
   on every push. With 100+ autonomous PRs/week, hosted minutes blow past free
   tier.
2. **Squash-merge stripping `[skip ci]`** — `gh pr merge --squash` defaults to
   the PR title as the squash commit subject, silently dropping `[skip ci]`
   from branch commits. Hit on PR #388.
3. **Queued runs after a non-`[skip ci]` slip** — even when caught quickly,
   queued runs continue to consume minutes unless explicitly cancelled.

## Decision

We adopt a **no-spend posture** with three enforcement points:

1. **Every commit ends with `[skip ci]`** during autonomous tranches. The hook
   in `.claude/settings.json` does not enforce this — it is a working agreement
   embedded in every megaprompt + the safe-merge wrapper.
2. **`vars.SAPPHIRE_RUNNER` gates every workflow** in `.github/workflows/`. When
   the variable is empty (no self-hosted runner provisioned) the workflow exits
   cleanly without consuming hosted minutes. When populated, the workflow runs
   on the self-hosted runner only.
3. **`scripts/ops/sapphire_safe_merge.sh`** wraps `gh pr merge --squash` with
   the explicit `-t '<title> [skip ci]'` flag and a post-merge `gh run list`
   sweep that cancels any queued or in-progress runs.

The wrapper is the canonical merge path for autonomous PRs. Operator-driven
merges of trading-critical-path PRs (CODEOWNERS-gated; see ADR 0003) follow
the same cadence but with `--admin` removed.

## Consequences

- **Positive**:
  - Zero hosted-runner billing during autonomous nights. Verified across
    Tranches 2-5 (≥ 60 PRs cumulatively, $0 spend).
  - Self-correcting: if a commit slips through without `[skip ci]`, the wrapper's
    post-merge sweep cancels the queued run before it consumes minutes.
  - Discipline scales: same wrapper works for Codex agents, Claude agents, and
    operator-driven merges.
- **Negative**:
  - We do not get green-CI evidence on every PR. Operators must run the
    verification protocol (`ruff`, both pytest blocks, registry validator,
    production-readiness sweep) **locally** before merging. This is a real
    burden for satellite-repo PRs that lack a wrapper.
  - The `[skip ci]` discipline is human-enforced — there is no commit-hook
    that adds it automatically. A forgotten `[skip ci]` is a real risk and
    has happened (PR #388).
  - Dependabot PRs land outside the gate and must be batched manually
    (see `feedback_multi_repo_workflow.md`).
- **Neutral**:
  - When the self-hosted runner is provisioned (`vars.SAPPHIRE_RUNNER` set),
    CI runs as normal — the no-spend posture is an opt-out, not a permanent
    state.

## Alternatives Considered

- **Provision a self-hosted runner permanently**: rejected for cost (operator
  hardware) and complexity (runner management, OS-level sandboxing). May be
  revisited when revenue supports it.
- **Disable CI workflows entirely**: rejected — we still want green CI on
  release tags and operator-driven merges of high-risk surfaces.
- **Per-PR CI opt-in via labels**: rejected — labels are easy to forget; the
  `[skip ci]` subject convention is git-native and visible in `git log`.
- **Move CI to Cloud Build / GCP**: deferred. GCP has its own free tier; could
  be a future option but adds a second vendor.

## References

- Originating PR exposing the gap: PR #388 (squash-merge stripped `[skip ci]`)
- Wrapper: `scripts/ops/sapphire_safe_merge.sh`
- Memory entry: `~/.claude/projects/-Users-aribs/memory/feedback_multi_repo_workflow.md`
- Workflow gate: `.github/workflows/ci.yml` (filters on `vars.SAPPHIRE_RUNNER`)
