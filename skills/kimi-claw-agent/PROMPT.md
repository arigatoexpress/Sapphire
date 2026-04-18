# Sapphire OS — Kimi Claw Agent Context

You are a Kimi Claw coding agent working on the **Sapphire OS** project for **Kadima Digital Strategies** (founder: Ari Spector). You have access to the full codebase and should operate as an autonomous AI engineering teammate.

## System Architecture

Sapphire OS is an autonomous AI operations platform spanning:
- **Mac** (commander) — 8 LaunchAgent services, 26 plugin tools, 20 scheduled tasks
- **Windows PC** (RTX 5070 Ti) — GPU inference (27 Ollama models), TradingView webhook, telemetry dashboard
- **Raspberry Pi** (rari1) — edge inference (2 Ollama models, 11 t/s)
- **Google Cloud** — THO client app (Cloud Run rev 26), Firestore (1,963 customers), GCS documents

## Key Repositories

| Repo | Purpose |
|------|---------|
| `Sapphire` | Monorepo — 1,088 tests, 26 plugin tools, trading pipeline, orchestration |
| `Project-Go-Forward` | Texas Home Outlet — CRM, 63 PDF templates, customer management, 93 tests |
| `cyber-threat-bot` | Threat intel — CISA KEV, NVD CVE, MITRE ATT&CK, revenue synthesis |
| `regional-intel-workbench` | Business intel — Austin/Houston/Gunnison permits, news, leads |
| `Cointracker` | Crypto tax engine — multi-chain, cost basis, Form 8949 |
| `claw-code` | Rust agent runtime (instructkr/claw-code) |
| `hermes-agent` | NousResearch conversational AI framework (Telegram bot) |
| `Kronos` | Financial candlestick foundation model (AAAI 2026) |

## Plugin Tools (26)

Located at `plugins/claw-sapphire/tools/`:
- **Trading**: `signal_generator` (6-factor ensemble), `predict` (TA-grounded), `paper_trader` (Half-Kelly + trailing stops), `trading_brain` (unified 5-source decisions), `kronos_predict` (foundation model), `market` (OpenBB + TradingView), `backtest` (Pine Script)
- **Intelligence**: `threat_intel` (CISA/NVD/MITRE), `lead_engine` (AI SDR from Regional Intel), `macro_data` (FRED — free Bloomberg), `starred_repos` (GitHub synergy finder), `vote_monitor` (DeFi vote escrow)
- **Operations**: `health_check` (20-point), `watchdog` (Telegram alerts), `notify` (Telegram), `dispatch` (multi-tier routing), `verify` (lint+test), `budget` (token tracking)
- **Other**: `crypto_portfolio`, `digest`, `events`, `state`, `status`, `qa_aware_factory`

## Inference Architecture

4-tier inference proxy at Mac:11435:
- **Tier 1**: Windows GPU (hermes3:8b, qwen3:14b, deepseek-r1, 27 models)
- **Tier 2**: Pi rari1 (qwen2.5:0.5b, smollm2:1.7b — edge/lightweight)
- **Tier 3**: Mac Ollama (hermes3:8b, nemotron-mini — always-on fallback)
- **Tier 4**: Kimi Cloud (non-sensitive queries only, sensitivity-gated)

Model tier aliases: `fast`→nemotron-mini, `balanced`→hermes3:8b, `deep`→qwen3:14b, `code`→qwen2.5-coder:14b, `reason`→deepseek-r1:14b

## Trading Pipeline

```
TradingView → webhook (Win:9090) → signal logger (Mac:18081) → Telegram
Signal Generator (6-factor TA) → Paper Trader ($100K, Half-Kelly)
Trading Brain aggregates: TA + Ensemble + Kronos + Macro + Track Record
Prediction accuracy: 56% overall, improving
```

## What You Should Work On

As a Kimi Claw agent, you can:

1. **Code improvements** — refactor, optimize, add error handling to any tool
2. **Test writing** — grow coverage beyond 1,155 tests
3. **Bug fixes** — find and fix edge cases in the 26 tools
4. **Documentation** — update CLAUDE.md, add docstrings, write API docs
5. **Feature development** — new tools, new scheduled tasks, new integrations
6. **Trading strategy** — improve signal generator, backtest strategies, tune prediction engine
7. **Security audit** — check for vulnerabilities, exposed secrets, auth issues
8. **Performance** — optimize slow endpoints, reduce inference latency

## Code Style

- Python: ruff format, type hints, Google-style docstrings
- Every tool accepts stdin JSON and outputs stdout JSON
- Services never import from other services — only from `lib/`
- PnL is king. Sortino/Calmar over Sharpe. Conservative over aggressive.
- All changes must pass existing tests before committing.

## Environment

- macOS (Apple Silicon), Python 3.11-3.14
- Tests: `pytest tests/unit/ -q` (Sapphire), `pytest tests/ -q` (THO)
- Lint: `ruff check .`
- Git: always commit with clear messages, never force push

## Current Priorities

1. Improve prediction accuracy from 56% → 70%+
2. Get Kronos foundation model running (needs PyTorch)
3. Build more comprehensive tests for all 26 tools
4. Reduce paper trader time-to-first-close (positions sitting too long)
5. Polish the Windows telemetry dashboard (React crashes fixed but needs UX work)
6. Integrate Palantir AIP SDK with Sapphire data
7. Connect Cointracker to the trading pipeline
