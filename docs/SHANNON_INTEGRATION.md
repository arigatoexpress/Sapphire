# Shannon Integration (Sapphire)

This repository integrates [Shannon Lite](https://github.com/KeygraphHQ/shannon) as a **manual, staging-focused** autonomous pentest lane.

## Why this integration exists

- We ship continuously.
- Traditional pentests are infrequent.
- Shannon provides exploit-validated findings to reduce false positives.

## Guardrails in this integration

`/Users/aribs/Sapphire/scripts/run_shannon_scan.sh` enforces:

- Explicit authorization acknowledgement (`AUTHORIZATION_ACK=I_HAVE_EXPLICIT_AUTHORIZATION`)
- Target allowlist (`/Users/aribs/Sapphire/configs/security/shannon-target-allowlist.txt`)
- Production denylist (`/Users/aribs/Sapphire/configs/security/shannon-production-denylist.txt`)
- Staging-only default behavior (production needs `SHANNON_ALLOW_PRODUCTION=true`)

## Quick start

```bash
cd /Users/aribs/Sapphire
chmod +x scripts/run_shannon_scan.sh

AUTHORIZATION_ACK=I_HAVE_EXPLICIT_AUTHORIZATION \
TARGET_URL=https://your-staging-app.example.com \
TARGET_REPO_PATH=/Users/aribs/Sapphire \
ANTHROPIC_API_KEY=... \
./scripts/run_shannon_scan.sh
```

Optional with config:

```bash
AUTHORIZATION_ACK=I_HAVE_EXPLICIT_AUTHORIZATION \
TARGET_URL=https://your-staging-app.example.com \
TARGET_REPO_PATH=/Users/aribs/Sapphire \
SHANNON_CONFIG_SOURCE=configs/security/shannon-app-config.example.yaml \
ANTHROPIC_API_KEY=... \
./scripts/run_shannon_scan.sh
```

## Output

By default results are written under:

- `/Users/aribs/Sapphire/output/security/shannon`

The final report path (per workspace) is:

- `deliverables/comprehensive_security_assessment_report.md`

## Monitoring

```bash
cd /Users/aribs/Sapphire/tools/shannon
./shannon logs
./shannon workspaces
```

## Safety notes

- Do not run against production unless explicitly approved.
- Shannon is exploitative (mutative effects are possible).
- Only run with written authorization from target owner.
- Validate findings before remediation decisions.
