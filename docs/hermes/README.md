# Hermes Skill Templates

This directory holds **delivery templates** for new Hermes skills the Sapphire
Telegram bot should ship. Live Hermes skills are loaded from
`~/.hermes/skills/sapphire/<skill>/` (outside the repo); we keep the source
template in-repo so it can be reviewed in PRs and copied across at deploy time.

## Layout

```
docs/hermes/
├── README.md                      # this file
└── skills/<skill>/
    ├── SKILL.md                   # Hermes-loadable skill (frontmatter + body)
    └── <skill>.yaml               # action wiring + plugin-tool contract
```

The 14 currently-live skills (cyber-intel, inference-tier, kimi-delegate,
macro-data, paper-trading, regional-intel, repo-discovery, system-health,
system-ops, tho-operations, threat-intel, trading-analysis, trading-brain,
trading-signals — plus the legacy mutating `tradingview`) remain owned outside
this repo and are not modified here. See
`docs/org/hermes-sapphire-skill-surface.md` for the inventory + classifications.

## Deployment

Copy the skill directory into the Hermes skills root and restart the gateway:

```bash
cp -R ~/Code/Sapphire/docs/hermes/skills/<skill> \
      ~/.hermes/skills/sapphire/<skill> && \
  ~/.local/bin/hermes gateway restart
```

For `tradingview-orchestrator`:

```bash
cp -R ~/Code/Sapphire/docs/hermes/skills/tradingview-orchestrator \
      ~/.hermes/skills/sapphire/tradingview-orchestrator && \
  ~/.local/bin/hermes gateway restart
```

Then smoke-test from Telegram with one of the SKILL.md "When to Use" prompts.

## Contract

Every Sapphire Hermes skill template should:

1. Use the standard frontmatter (`name`, `description`, `version`, `author`,
   `metadata.hermes.tags`, optional `commands`, `requires`).
2. Drive a Sapphire-owned plugin tool over stdin JSON wherever possible
   (`plugins/claw-sapphire/tools/<name>.py`), not inline bash that touches
   services directly.
3. Document its classification in the body and the YAML `skill_class` field
   (`read_only`, `local_mutating`, `external_mutating`, `production_adjacent`)
   per `infra/hermes-sapphire-skills.yaml`.
4. Never hardcode credentials. Document the secret pointer (env var,
   `~/.sapphire/secrets.env`, macOS keychain) instead of inlining the value.

## Notes

- Do not write to `~/.hermes/` from CI or tests. Deployment is always an
  explicit operator-supervised step.
- Restarting the gateway briefly drops Telegram polling — fine for a manual
  push, but pair with a quick post-restart smoke test.
