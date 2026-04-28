# Agent Readiness Audit

`scripts/ops/agent_readiness_audit.py` is a read-only operator check for
production-autonomy readiness. It labels claims as observed, inferred, or
unknown, and it reports secret/variable names only.

## Run

```bash
/usr/local/bin/python3 scripts/ops/agent_readiness_audit.py --no-external
/usr/local/bin/python3 scripts/ops/agent_readiness_audit.py --format json --output data/readiness/agent-readiness-latest.json
```

Use `--no-external` for local-only evidence. Omit it when the operator wants
GitHub API checks for branch protection, Actions variables, secret names,
environments, Dependabot alert availability, and Code Scanning availability.

## Safety

- No workflow dispatches.
- No secret values are requested or printed.
- No branch protection, repository settings, environments, variables, or secrets
  are modified.
- GitHub API failures are recorded as `UNKNOWN` rather than guessed.

## Acceptance

For an agent-readiness closeout, attach:

1. The audit output.
2. `scripts/ops/local_ci_verify.py --quiet`.
3. `scripts/ops/production_readiness_sweep.py --no-external`.
4. Any green workflow run IDs that prove hosted/self-hosted behavior.
