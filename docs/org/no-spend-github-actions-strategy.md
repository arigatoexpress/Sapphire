# No-Spend GitHub Actions Strategy

Sapphire should keep moving without paying for hosted GitHub Actions minutes.
The default proof path is local verification, self-hosted runner evidence when
available, and explicit PR notes that hosted Actions were intentionally skipped.

## Rules

- Sapphire workflows must keep the `SAPPHIRE_RUNNER` gate. Jobs skip unless the
  variable is set, and `runs-on` must use `fromJSON(vars.SAPPHIRE_RUNNER)`.
- Do not add `ubuntu-latest`, `macos-latest`, `windows-latest`, or any other
  hosted-runner fallback to private-repo workflows.
- For satellites without a no-spend workflow gate, use a first guardrail PR
  that updates CI and local verification docs. Commit that bootstrap with
  `[skip ci]` when hosted Actions would otherwise bill or fail on billing.
- Treat `[skip ci]` as a temporary bootstrap tool, not a permanent verification
  substitute. It applies to `push` and `pull_request` events and may leave
  required checks pending.
- Prefer local CI evidence in the PR body and an evidence comment before merge.
- THO stays draft or explicitly approved because `main` auto-deploys to Cloud
  Run.

## Repo Strategies

The canonical strategy for each active repo lives in `infra/org-repos.yaml` as
`ci_strategy`.

| Strategy | Meaning |
|---|---|
| `sapphire_self_hosted_gate` | Sapphire's no-spend runner gate plus local CI evidence. |
| `local_evidence_skip_ci_bootstrap` | Local tests first; use `[skip ci]` only to land the first no-spend guard. |
| `draft_auto_deploy` | Production auto-deploy repo; PRs stay draft or explicitly approved. |
| `upstream_fork_local_only` | Upstream/fork integration; use local tests and avoid runtime retargeting. |

## Local Evidence Template

```text
Local verification:
- <command>: PASS
- <command>: PASS

Hosted Actions:
- Skipped by no-spend policy.
- No hosted-runner fallback was added.

Safety:
- No secrets printed or changed.
- No live Telegram sends.
- No live trading or money movement.
- No GCP, Foundry, DNS, Firestore, GCS, workflow, or LaunchAgent mutation.
```

## References

- [GitHub Actions billing](https://docs.github.com/en/billing/managing-billing-for-github-actions/about-billing-for-github-actions)
- [GitHub self-hosted runners](https://docs.github.com/en/actions/hosting-your-own-runners/about-self-hosted-runners)
- [Skipping workflow runs](https://docs.github.com/en/actions/how-tos/manage-workflow-runs/skip-workflow-runs)
