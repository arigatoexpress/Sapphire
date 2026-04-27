# Self-hosted GitHub Actions runner — free CI unblock

When the repo's GitHub Actions billing fails (issue [#220](https://github.com/arigatoexpress/Sapphire/issues/220)
on 2026-04-26), the workflows in `.github/workflows/` stop running. This
document is the free fallback path: register a single self-hosted runner
on the always-on Mac commander so every existing workflow keeps firing
without paying GitHub for runner minutes.

## Why this is safe enough

- Sapphire is a private repo. Self-hosted runners on private repos do
  not execute fork-PR workflows by default — only collaborator-authored
  branches and direct pushes trigger jobs.
- The runner runs the workflow YAML verbatim, so the existing CI
  contract (`ruff`, `pytest`, plugin tests, gitleaks, tool registry)
  works without modification.
- The Mac commander is already the trust root for Sapphire. Adding a
  runner does not expand the threat surface.

## Setup — one-time, ~10 minutes

1. Open `https://github.com/arigatoexpress/Sapphire/settings/actions/runners/new`.
   Pick **macOS** + **ARM64**.

2. Run the four commands GitHub gives you, with two adjustments:
   - Place the runner under `~/actions-runner/` (out of the repo).
   - When prompted for a "name", use `sapphire-mac-commander`.
   - Add labels `self-hosted, macOS, arm64, sapphire-commander`.

   ```bash
   mkdir -p ~/actions-runner && cd ~/actions-runner
   curl -o actions-runner-osx-arm64.tar.gz -L \
     <download URL from GitHub UI>
   tar xzf ./actions-runner-osx-arm64.tar.gz
   ./config.sh \
     --url https://github.com/arigatoexpress/Sapphire \
     --token <token from GitHub UI> \
     --name sapphire-mac-commander \
     --labels self-hosted,macOS,arm64,sapphire-commander \
     --work _work --unattended
   ```

3. Install the runner as a LaunchAgent so it survives reboots:

   ```bash
   ./svc.sh install
   ./svc.sh start
   launchctl list | grep actions.runner   # should show a PID
   ```

   Logs land at `~/actions-runner/_diag/Runner_<date>.log`.

4. Switch the workflows to prefer the self-hosted runner. Edit each
   workflow's `runs-on:` from `ubuntu-latest` to a list with a
   conditional fallback. You can land this as a separate PR:

   ```yaml
   jobs:
     lint:
       runs-on: [self-hosted, macOS, arm64, sapphire-commander]
   ```

   Or, to keep the option of falling back to GitHub-hosted once billing
   is restored:

   ```yaml
   jobs:
     lint:
       runs-on: ${{ vars.SAPPHIRE_RUNNER || 'ubuntu-latest' }}
   ```

   and set the repo variable `SAPPHIRE_RUNNER=self-hosted` in
   `Settings -> Actions -> Variables`.

5. Confirm a workflow run pushes through:

   ```bash
   gh workflow run ci.yml --ref main
   gh run list --workflow=ci.yml --limit 1
   ```

## Hardening checklist

Run through these once before relying on the runner for production
verification:

- [ ] `actions-runner/` lives in the operator's `$HOME`, not in the repo.
- [ ] `svc.sh install` registered the LaunchAgent (`launchctl list | grep actions.runner` returns a PID).
- [ ] The runner only accepts jobs from `arigatoexpress/Sapphire` — verify
      under repo settings.
- [ ] Workflows that touch secrets (`security.yml`, etc.) gate on
      `if: github.event.pull_request.head.repo.full_name == github.repository`
      so a fork PR cannot tickle them.
- [ ] CodeQL / gitleaks / osv-scanner workflows that pull blocklist URLs
      have their cache directory whitelisted in any local firewall.
- [ ] Dependabot / external-PR runs are kept on `ubuntu-latest` (do NOT
      route them to the self-hosted runner).

## Fallback that does not need a runner

While the runner is offline, every PR can still be verified with
`scripts/ops/local_ci_verify.py`:

```bash
# Verify a specific PR before admin-merge
python3 scripts/ops/local_ci_verify.py --pr 230

# Verify the working tree
python3 scripts/ops/local_ci_verify.py
```

The script writes a JSON report under `data/ci/` (gitignored) and
prints a Markdown summary. Exit code matches the CI contract:
`0` PASS, `10` WARN, `20` FAIL.

This is the procedure I used during the 2026-04-26 evening autonomous
window to admin-merge tests-only and doc-only PRs while CI was billing-
blocked. See [issue #220](https://github.com/arigatoexpress/Sapphire/issues/220) for the full bypass log.

## Decommissioning when GitHub-hosted CI returns

Once billing is restored and you want to retire the self-hosted runner:

```bash
cd ~/actions-runner
./svc.sh stop
./svc.sh uninstall
./config.sh remove --token <removal token from GitHub UI>
rm -rf ~/actions-runner
```

And revert the `runs-on:` change in `.github/workflows/*.yml` (or set
the repo variable `SAPPHIRE_RUNNER=` to empty).

## Cost summary

| Item | Cost |
|---|---|
| GitHub Actions runner minutes | $0 (self-hosted) |
| Mac commander uptime | already 24/7 |
| Bandwidth for runner heartbeat | tens of KB / day |
| Secrets exposure | unchanged (workflows don't gain new permissions) |

The only hidden cost is the operator-time to monitor the runner —
budget five minutes a week to glance at `~/actions-runner/_diag/`.
