# Sapphire Safe Merge Runbook

## Purpose

Sapphire runs in a no-spend posture for hosted GitHub Actions. The repository
uses local verification as the merge gate, and every merge commit subject must
carry `[skip ci]` so hosted workflows do not queue accidentally. A normal
`gh pr merge --squash` call uses the pull-request title as the squash subject.
That is convenient, but it is also easy to forget the skip marker when the PR
title itself does not contain it.

`scripts/ops/sapphire_safe_merge.py` is the guardrail for that failure mode. It
reads the PR title and changed-file list through `gh pr view`, appends
`[skip ci]` when missing, and classifies the PR before merge. Documentation-only
PRs keep the cheap path. Any PR that touches code, tests, configs, workflows, or
data must first pass `scripts/ops/local_ci_verify.py --pr <N> --quiet`; a
failing local CI result stops the merge before the squash commit lands. After a
successful squash merge, the wrapper inspects recent workflow runs and cancels
only runs that can be attributed to the just-merged PR.

## Command

From the Sapphire repo root:

```bash
make safe-merge PR=394
```

Equivalent direct call:

```bash
/usr/local/bin/python3 scripts/ops/sapphire_safe_merge.py 394
```

The shell wrapper is available when a bash entrypoint is preferable:

```bash
scripts/ops/sapphire_safe_merge.sh 394
```

Use `--dry-run` to see the resolved subject without merging:

```bash
/usr/local/bin/python3 scripts/ops/sapphire_safe_merge.py 394 --dry-run
```

The tool prints compact JSON with the PR number, the final squash subject,
whether the PR was documentation-only, whether local CI ran, and any workflow
run IDs it cancelled.

## Preconditions

For PRs that touch code, tests, configs, workflows, or data, the wrapper now
runs the full local CI verifier automatically before merging:

```bash
/usr/local/bin/python3 scripts/ops/local_ci_verify.py --pr <PR> --quiet
```

The manual equivalent remains useful while iterating in a worktree:

```bash
ruff check .
/usr/local/bin/python3 -m pytest tests/unit/ -q --tb=short
/usr/local/bin/python3 -m pytest plugins/claw-sapphire/tests/ -q --tb=short
/usr/local/bin/python3 scripts/validate_tool_registry.py
/usr/local/bin/python3 scripts/ops/production_readiness_sweep.py --no-external
```

Documentation-only PRs are intentionally exempt from the automatic full local CI
run. The docs-only classifier accepts files under `docs/`, top-level operator
docs such as `README.md`, `CLAUDE.md`, `AGENTS.md`, and common Markdown/AsciiDoc
suffixes. Empty or malformed file metadata is treated as non-docs and therefore
requires local CI. Root dependency files such as `requirements-test.txt` are not
docs-only even though they use a text suffix.

Also confirm the PR is cleanly mergeable:

```bash
gh pr view <PR> --json mergeStateStatus,mergeable,title,headRefName,headRefOid
```

If the PR is a draft, has unresolved conflicts, touches a hard-stop surface, or
requires Ari review under CODEOWNERS, stop before merging. This wrapper protects
the no-spend merge subject and run-cancellation scope; it is not a replacement
for safety review.

## Cancellation Scope

After the squash merge, the wrapper runs:

```bash
gh -R arigatoexpress/Sapphire run list --limit 20 --json databaseId,status,headSha,headBranch,displayTitle,event
```

It cancels only active runs whose status is `queued` or `in_progress` and that
match one of these fingerprints:

- `headSha` equals the PR head SHA returned by `gh pr view`.
- `headBranch` equals the PR head branch returned by `gh pr view`.
- `displayTitle` equals the exact explicit squash subject and `headBranch` is
  `main` or `master`.

This avoids a broad fleet cancellation. A busy repo can have unrelated queued
runs at the same time; those are left alone unless they match the just-merged
PR. Missing or malformed run IDs are ignored rather than guessed.

## Recovery

If local CI fails, the wrapper exits non-zero before the merge. Read the
`safe-merge error:` line, open the JSON report under `data/ci/`, fix the PR, and
retry. If the merge command itself fails, the wrapper also exits non-zero before
any cancellation. In both cases, verify that the branch still contains the
intended changes before retrying.

If the merge succeeds but `gh run list` fails, manually inspect recent runs:

```bash
gh run list --limit 20 --json databaseId,status,headSha,headBranch,displayTitle
```

Cancel only runs matching the same fingerprints above:

```bash
gh run cancel <run-id>
```

If a bad squash subject still lands, do not rewrite `main`. Record the incident
in the tranche handoff, cancel any matching queued or in-progress hosted runs,
and use the wrapper for the next merge. Rewriting `main` creates more operational
risk than a corrected follow-up note.

## Notes For Operators

The wrapper is intentionally small and importable. Unit tests mock all `gh` and
local-verifier subprocess calls so the guardrail can be checked without network
access or live PR mutation. The script does not read secrets, does not alter
branch protection, and does not broaden permissions. It assumes `gh` is already
authenticated for the Sapphire repository, which is the same prerequisite as the
manual merge flow it replaces.

The safest habit is simple: after local verification passes, run
`make safe-merge PR=<N>` instead of typing the raw `gh pr merge` command by
hand. The wrapper preserves the project policy in one place, and the JSON output
gives a compact audit trail for the final handoff.
