# AI Repo Manager

Multi-repo workspace for auditing, securing, and managing all arigatoexpress GitHub repositories.

## Repos (16 total)

| Repo | Stack | Description |
|------|-------|-------------|
| `AsterAI` | Python, Docker | Crypto trading bot with Redis cache, Telegram alerts |
| `SapphireAI` | Python, Docker | Fork/variant of AsterAI trading system |
| `quant-ai-trader` | Python, Docker, Grafana | Quantitative trading with web dashboard |
| `Rari_AI_Telegram_Manager` | Python | Telegram channel intelligence & sync bot |
| `fullsail_scanner` | Python | Sui blockchain event scanner |
| `full-sail-volume-calculator-2.0` | Python, Streamlit, Docker | Crypto volume analysis with Streamlit UI |
| `fullsail-site` | React, Tailwind | Landing page / marketing site |
| `DesktopOrganizer` | Python, Ollama | AI-powered file organization tool |
| `CyberSpectre` | Python | Security analysis toolkit |
| `AkaiJamboard` | TypeScript, Vite | AI beatmaker web app |
| `binance-trade-bot` | Python, Docker | Forked crypto trading bot (Binance) |
| `tensortrade` | Python, Docker | Forked ML trading framework |
| `freqtrade-strategies` | Python | Forked trading strategies collection |
| `rari-portfolio` | Web | Portfolio website |
| `ArigatoALMM` | Web | Project page |
| `arigatoexpress` | Web | GitHub profile README |
| `sapphire-inc` | TypeScript, Docker | Autonomous agent swarm (OpenClaw) — Sapphire, Inc. |
| `openclaw` | TypeScript | OpenClaw framework (cloned, built with pnpm) |

## Commands

| Command | Description |
|---------|-------------|
| `gh repo list arigatoexpress --limit 50` | List all GitHub repos |
| `gh api repos/arigatoexpress/<repo>` | Get repo details |
| `git -C repos/<name> status` | Check repo status |
| `git -C repos/<name> log --oneline -5` | Recent commits |
| `for d in repos/*/; do echo "=== $(basename $d) ===" && git -C "$d" status -s; done` | Status all repos |
| `node repos/openclaw/openclaw.mjs gateway run --port 18789 --token <t>` | Start OpenClaw gateway |
| `node repos/openclaw/openclaw.mjs agent --agent <id> --local -m "<msg>"` | Send message to agent |
| `gcloud services api-keys get-key-string <key-id>` | Get real API key from GCP (starts with AIza) |
| `gcloud secrets versions access latest --secret=<name> --project=sapphire-479610` | Read GCP secret |

## Architecture

```
AI Repo Manager/
  repos/              # All 16 cloned repositories
    AsterAI/          # Each is an independent git repo
    SapphireAI/
    quant-ai-trader/
    sapphire-inc/     # Agent swarm config, skills, deployment
    openclaw/         # OpenClaw framework (built, not modified)
    ...
  CLAUDE.md           # This file - project context
  .claude/
    settings.local.json  # Scoped permissions for this project
    plans/            # Execution plans from planning sessions
```

## Plugins

Three Claude Code plugins are enabled globally:

- **claude-md-management** - Audit and improve CLAUDE.md files (`/revise-claude-md`, `claude-md-improver` skill)
- **agent-sdk-dev** - Scaffold Agent SDK apps (`/new-sdk-app`), verify SDK projects
- **asana** - MCP integration with Asana for task management (SSE at `https://mcp.asana.com/sse`)

## Security Audit Workflow

1. Clone all repos: `gh repo list arigatoexpress --json name,sshUrl | jq ...`
2. Scan for secrets: grep for API keys, tokens, private keys in tracked files
3. Check .gitignore coverage: verify .env, credentials, IDE files are excluded
4. Check .dockerignore: ensure secrets don't leak into Docker images
5. Audit dependencies: `pip-audit` for Python, `npm audit` for JS
6. Fix by priority: secrets > code vulns > deps > config

## Sapphire, Inc. (Agent Swarm)

OpenClaw-based 3-agent swarm at `repos/sapphire-inc/`, config at `~/.openclaw/`.

| Agent | Role | Emoji |
|-------|------|-------|
| SAPPHIRE | Security & Code Quality | 💎 |
| OBSIDIAN | CI/CD & Deploy Ops | 🖤 |
| EMERALD | Innovation & Self-Improvement | 💚 |

- **Model:** `google/gemini-2.0-flash` via Gemini API key from GCP
- **Gateway:** `openclaw gateway run --port 18789` — Control UI at `http://127.0.0.1:18789/#token=<token>`
- **Skills:** 7 custom (`skills/`) + 49 built-in = 56 total
- **Config:** `~/.openclaw/openclaw.json` — auth profiles at `~/.openclaw/agents/{id}/agent/auth-profiles.json`
- **CLI test:** `node openclaw.mjs agent --agent sapphire --local -m "hello"`
- **GCP deploy:** `./scripts/deploy.sh` (Cloud Build → Artifact Registry → Cloud Run)
- **GitHub:** `arigatoexpress/sapphire-inc` (private)

## Gotchas

- **Background agents can't write/edit in plan mode** - execute file changes from main session only
- **AsterAI and SapphireAI share structure** - fixes usually need to be applied to both
- **`local.env` != `.env`** - `.env.*` gitignore patterns don't match `local.env` (no dot prefix)
- **binance-trade-bot uses `master` branch**, not `main`
- **quant-ai-trader uses `master` branch**, not `main`
- **tensortrade uses `master` branch**, not `main`
- **AkaiJamboard is on branch `claude/akai-ai-beatmaker-L2tUY`**, not `main`
- **quant-ai-trader has vendored `y/google-cloud-sdk/`** (~4000 files) - always exclude from Docker
- **OpenClaw `google-vertex` provider needs auth-profiles.json** — use `google/gemini-2.0-flash` with API key instead
- **GCP Secrets (`GEMINI_API_KEY`, `vertex_api_key_v1`) are KMS-encrypted** — use `api-keys get-key-string` for the real key
- **OpenClaw gateway needs `gateway.mode: "local"`** in config or `--allow-unconfigured` flag
- **macOS has no `timeout` command** — avoid it or use `gtimeout` from coreutils
- **Cloud Build can't compose substitution variables** — inline values directly
- **sapphire-inc uses `main` branch**

## Code Style

- Security commits use prefix: `security: <description>`
- Chore commits use prefix: `chore: <description>`
- Feature commits use prefix: `feat: <description>`
- Fix commits use prefix: `fix: <description>`
- All commits end with: `Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>`
- Agent commits use: `Co-Authored-By: <agent-name> @ Sapphire Inc <sapphire-inc@kadima.digital>`
- Use `git rm --cached` (not `git rm`) to untrack files while preserving locally
- Use HEREDOC format for multiline commit messages
