# Sapphire Reproducibility Playbook

This playbook brings up a fresh macOS workstation into a demo-safe Sapphire
environment. It is designed for a new Mac with no credentials and no
operator-personal files. Linux can use the same checkout, venv, and secrets
steps, but LaunchAgents are macOS-only.

## Safety Model

The bootstrap defaults to demo mode:

- `~/.sapphire/secrets.env` is created from `infra/secrets.env.example` with
  inert placeholders.
- Live exchange, payment, publishing, and messaging flags are off.
- Telegram stays dry-run.
- LaunchAgents are copied with `RunAtLoad=false` and are not bootstrapped.
- Existing secrets are preserved and never printed.

Do not flip live flags until an operator has populated real secrets, reviewed
the specific service runbook, and accepted the blast radius. The bootstrap does
not enable real trading, real Telegram sends, or x402 payment behavior.

## First Run

From a fresh shell:

```bash
git clone https://github.com/arigatoexpress/Sapphire.git ~/Code/Sapphire
cd ~/Code/Sapphire
SAPPHIRE_BOOTSTRAP_DRY_RUN=1 make sapphire-on-fresh-mac
make sapphire-on-fresh-mac
```

The dry-run prints every command it would execute. The real run:

1. Validates macOS or prints Linux fallback notes.
2. Installs or validates Homebrew tools: `git`, `python@3.11`, `ruff`, and
   `gitleaks`.
3. Clones Sapphire if `SAPPHIRE_REPO_PATH` does not already point at a checkout.
4. Creates `.venv-fresh-mac` and installs `requirements-test.txt`.
5. Creates `~/.sapphire/secrets.env` from demo placeholders with mode `0600`.
6. Copies demo LaunchAgent plists into `~/Library/LaunchAgents/` with
   `RunAtLoad=false`.
7. Runs a local CI smoke through `scripts/ops/local_ci_verify.py` with plugin,
   registry, and test-inventory checks skipped for first-boot speed.

Useful overrides:

```bash
SAPPHIRE_REPO_PATH="$HOME/Code/Sapphire" make sapphire-on-fresh-mac
SAPPHIRE_BOOTSTRAP_VENV="$HOME/Code/Sapphire/.venv-fresh-mac" make sapphire-on-fresh-mac
SAPPHIRE_BOOTSTRAP_LOCAL_CI_SMOKE=0 make sapphire-on-fresh-mac
```

## Demo Lifecycle

```bash
make sapphire-demo-up
make sapphire-demo-down
make sapphire-demo-reset
```

`sapphire-demo-up` is an alias for the bootstrap. `sapphire-demo-down` removes
the demo LaunchAgent copies and `.venv-fresh-mac`, preserving
`~/.sapphire/secrets.env`. `sapphire-demo-reset` also removes the secrets file
only when it still contains the known placeholder marker.

## LaunchAgents

The copied demo LaunchAgents come from
`infra/bootstrap/demo-launchagents.list`. The bootstrap rewrites each copied
plist to:

- `RunAtLoad=false`
- demo/live-off environment gates
- the configured `SAPPHIRE_REPO_PATH`

The script deliberately does not call `launchctl bootstrap`, `launchctl load`,
or `launchctl kickstart`. Loading a service is an operator action after the
secrets file has been reviewed.

## Linux Notes

Linux runs skip LaunchAgent installation. Install the package-manager
equivalents of `git`, Python 3.11+, `ruff`, and `gitleaks`, then run the same
bootstrap. Use systemd or a process supervisor only after translating the
demo-off flags from `infra/bootstrap/demo-services.env`.

## Verification

Focused lane checks:

```bash
python3 -m pytest tests/unit/test_bootstrap_fresh_mac_dryrun.py tests/unit/test_makefile_targets_present.py -q
bash -n scripts/ops/bootstrap_fresh_mac.sh scripts/ops/teardown_fresh_mac.sh
ruff check tests/unit/test_bootstrap_fresh_mac_dryrun.py tests/unit/test_makefile_targets_present.py
git diff --check
```

Full local CI remains available once the fresh machine has enough dependencies:

```bash
python3 scripts/ops/local_ci_verify.py --quiet
```
