# Sapphire Codex Handoff Package

> Generated: Feb 13, 2026 | Deploy: sapphire-alpha-00153-xvp | Tests: 308 passing

---

## 🎯 Mission

Build a top-tier autonomous crypto trading platform with secure multi-agent collaboration, crowdsourced swarm intelligence, and automated public presence.

**Owner directive:** "Ignore Asana and TradingView integrations until agents and trading systems are top tier (and scout molthub integration)."

**Execution priority:**
```
Phase 1 (NOW) → Phase 2 → Phase 3 → Phase 5 → Phase 4 → Phase 6 → Phase 7
Harden         Security   Forum      Tracking    Swarm      Social    On-chain
```

---

## 📍 Current State

### What's Live (sapphire-alpha-00153-xvp)
- **Multi-venue trading**: Drift, Hyperliquid, Aster, Symphony, Lighter
- **TradingView webhook integration**: Signal → cognition → execution pipeline
- **Dual-speed cognition**: Fast (Flash) + deep (Pro) AI pre-trade validation
- **Episodic memory**: Learns from past trades, informs future decisions
- **Portfolio tracker**: Position lifecycle, P&L, ring buffer history
- **Fill confirmation loop**: Async Future-based with timeout/retry
- **Skill security auditor**: 8 threat categories, isnad provenance chains, 24 injection patterns
- **Agent activity feed**: Periodic Telegram digests every 5 min, grouped by agent/category
- **Prompt injection defense**: Sanitizer on all LLM prompt paths (Telegram → Gemini, memory → cognition, trade data → recap)
- **Agent permission system**: 24 atomic capabilities, 4 role definitions, 12 runtime gates enforced
- **Forum service**: Rich collaborative forum with categories, voting, threading, quality metrics, agent profiles
- **Forum Telegram commands**: `/forum top`, `/forum vote`, `/forum agents`, `/forum thread`, `/forum post`

### Repo & Infra
- **Repo**: `arigatoexpress/Sapphire` (PRIVATE) — `/Users/aribs/Documents/Projects/AI Repo Manager/repos/Sapphire/`
- **Cloud**: GCP project `sapphire-479610`, Cloud Run `us-central1`
- **Build**: `gcloud builds submit --config=cloudbuild-alpha.yaml --substitutions=_IMAGE=gcr.io/sapphire-479610/sapphire-alpha --project=sapphire-479610`
- **Deploy**: `gcloud run deploy sapphire-alpha --image gcr.io/sapphire-479610/sapphire-alpha:latest --region us-central1 --project sapphire-479610 --quiet`
- **Tests**: `python3 -m pytest tests/unit/ -p no:anchorpy -p no:xprocess -v --tb=short`
- **Branch strategy**: Feature branches `codex/<name>` → PR → merge to `main` → build → deploy

---

## 🏗 Architecture

### Core Engine (4637 lines — `src/main.py`)
`AlphaEngine` is the monolithic orchestrator. Key subsystems:

| Subsystem | File | Lines | Purpose |
|-----------|------|-------|---------|
| **Main Engine** | `src/main.py` | 4637 | Orchestrator: signal routing, trade dispatch, Telegram commands |
| **Gemini Guard** | `src/ai/gemini_guard.py` | 321 | AI sentinel: hourly/daily recaps, owner chat, market checks |
| **Telegram Bot** | `shared/telegram_bot.py` | 1904 | Multi-agent Telegram interface, activity feed, command routing |
| **Forum** | `src/collaboration/forum.py` | 1668 | Internal forum: topics, replies, Scout communication layer |
| **Episodic Memory** | `shared/enhanced_episodic_memory.py` | 976 | Trade memory bank, pattern recall, decision context |
| **Cognition** | `shared/dual_speed_cognition.py` | 425 | Dual-speed AI: fast Flash screening + deep Pro analysis |
| **Skill Auditor** | `src/security/skill_auditor.py` | 518 | Supply-chain security: 24 injection + 11 exfil + 13 cred patterns |
| **Agent Permissions** | `src/security/agent_permissions.py` | 256 | Capability-based access control for 4 agent roles |
| **Prompt Sanitizer** | `src/security/prompt_sanitizer.py` | 279 | Injection detection, zero-width stripping, boundary wrapping |
| **Portfolio** | `src/execution/portfolio.py` | 324 | Position tracking, P&L calculation, ring buffer |
| **Dispatcher** | `src/execution/dispatcher.py` | — | Multi-venue order routing |
| **Market Data** | `src/feeds/market_data.py` | — | WebSocket feeds from multiple exchanges |
| **Strategy Engine** | `src/strategy/engine.py` | — | Alpha strategy with fallback strategies |
| **TV Autonomy** | `src/integrations/tradingview_autonomy.py` | — | TradingView autonomous dispatch plugin |

### Agent Roles

| Agent | Emoji | Capabilities | Purpose |
|-------|-------|-------------|---------|
| **Sapphire** 💎 | Trading, secrets, kill switch, portfolio, market data, Telegram, AI prompts | Execution & scouting |
| **Obsidian** 🖤 | Infrastructure, autonomy, venue control, system config, Telegram | Infrastructure & deployment |
| **Emerald** 💚 | Strategy, audit, moderation, cognition, memory, market data | Strategy & improvement |
| **Scout** 🔭 | Forum read/write, moltbook, skill audit, external API ONLY | External outreach (most restricted) |

### Security Layers
1. **Agent Permissions** (`agent_permissions.py`): `AgentGate` with `check()`/`require()`, 24 capabilities, PermissionDenied exception
2. **Prompt Sanitizer** (`prompt_sanitizer.py`): 22 detection patterns, risk scoring 0.0–1.0, boundary delimiters, zero-width stripping, homoglyph normalization
3. **Skill Auditor** (`skill_auditor.py`): 24 injection + 11 exfil + 13 credential + 7 filesystem patterns, isnad provenance chains
4. **Gemini Guard hardening**: Telegram messages sanitized before LLM interpolation, high-risk (≥0.8) rejected, trade data field-whitelisted
5. **Cognition hardening**: Memory recall sanitized before injection into cognition prompts

---

## 📊 Test Coverage (308 passing)

| Test File | Tests | Covers |
|-----------|-------|--------|
| `test_forum_phase3.py` | 39 | Categories, voting, threading, quality metrics, agent profiles, top topics |
| `test_gate_enforcement.py` | 38 | AgentGate capability boundaries, all 4 agents + rogue, 13 capabilities |
| `test_agent_permissions.py` | 37 | Per-agent caps, PermissionDenied, unknown agents, stats, registration |
| `test_prompt_sanitizer.py` | 35 | Role override, exfil, code exec, boundary, clean, scoring, trade data |
| `test_alpha_engine_telegram_control.py` | 40 | Telegram commands, routing, kill switch, venue control, forum commands |
| `test_security_fuzz.py` | 18 | Adversarial strings, injection payloads, forum sanitizer, prompt detection |
| `test_sapphire_forum_service.py` | 18 | Forum topics, replies, redaction, content filtering |
| `test_skill_auditor.py` | 17 | Credential theft, exfil, injection, obfuscation, isnad, reporting |
| `test_portfolio_tracker.py` | 13 | Position lifecycle, P&L, ring buffer, edge cases |
| `test_rate_limit_manager.py` | 10 | Rate limiting across venues |
| `test_activity_feed.py` | 8 | Activity recording, digest grouping, max cap, truncation |
| `test_execution_dispatcher.py` | 7 | Multi-venue dispatch, target normalization |
| `test_vpin_agent.py` | 7 | VPIN calculation |
| `test_alpha_strategy_engine.py` | 5 | Strategy selection, execution state |
| `test_virustotal_skill_scanner.py` | 5 | VirusTotal integration |
| `test_fallback_strategies.py` | 5 | Fallback strategy selection |
| `test_market_data_aggregator.py` | 3 | Tick extraction, outlier filtering |
| `test_error_classifier.py` | 3 | Error categorization |

---

## 📋 Completed PRs

| PR | Title | Key Changes |
|----|-------|-------------|
| #15 | Portfolio Tracker | Position lifecycle, P&L, ring buffer |
| #16 | Fill Confirmation Loop | Async Future-based, timeout/retry |
| #17 | Cognitive Systems | Episodic memory, dual-speed cognition |
| #18 | Skill Security Auditor | 8 threat categories, isnad chains |
| #19 | Smart Notifications | Autonomy spam fix, agent activity feed |
| #20 | Security Hardening Phase 2 | Agent permissions, prompt injection defense, sanitizer |
| #21 | AgentGate Enforcement | 12 critical operation gates, /permissions command |
| #22 | Forum Injection Hardening | 18 adversarial tests, forum content blocking |
| #23 | Phase 3 Forum Expansion | Categories, voting, threading, quality metrics, agent profiles |
| #24 | Forum Telegram Wiring | 5 new commands, 5 engine handlers, category/threading passthrough |

---

## 🔜 What To Do Next

### Immediate (Phase 3 Remaining)
1. **Forum-based approval workflows** — Route pending decisions (autonomy cycles, trade approvals) through forum topics with agent voting

### Phase 4: Molthub Swarm Intelligence
- Scout posts on Molthub inviting external bots (TRADE IDEAS ONLY)
- Bot reputation/points system: accuracy, profitability, info quality tracking
- Public leaderboard, reputation-weighted trade idea aggregation
- Consensus mechanisms for high-conviction trades

### Phase 5–7: See ROADMAP.md

---

## ⚠️ Known Issues & Gotchas

1. **Pytest plugins**: Always use `-p no:anchorpy -p no:xprocess` — they fail to import
2. **Integration tests broken**: `test_retired_d_integration.py` has `ModuleNotFoundError: No module named 'cloud_trader.aster_client'` — only run `tests/unit/`
3. **Cloud Build substitution**: Must pass `--substitutions=_IMAGE=gcr.io/sapphire-479610/sapphire-alpha` or build fails
4. **Monolithic architecture**: All agents share the same process (`main.py` is 4800+ lines). Agent permissions are logical, not process-level isolation
5. **Autonomy disabled by default**: `TRADINGVIEW_AUTONOMY_ENABLED` is not set in Cloud Run, so TV autonomy dispatch is silently skipped (this is intentional for now)

---

## 🔑 Key File Paths

```
/Users/aribs/Documents/Projects/AI Repo Manager/repos/Sapphire/
├── ROADMAP.md                              # Master plan with checkboxes
├── HANDOFF.md                              # This file
├── services/alpha-engine/
│   ├── src/
│   │   ├── main.py                         # Core engine (4637 lines)
│   │   ├── ai/gemini_guard.py              # AI sentinel (hardened)
│   │   ├── security/
│   │   │   ├── agent_permissions.py        # 24 capabilities, 4 roles
│   │   │   ├── prompt_sanitizer.py         # Injection defense
│   │   │   └── skill_auditor.py            # Supply-chain security
│   │   ├── collaboration/forum.py          # Internal forum
│   │   ├── execution/
│   │   │   ├── dispatcher.py               # Multi-venue routing
│   │   │   └── portfolio.py                # Position tracking
│   │   ├── feeds/market_data.py            # Exchange WebSocket feeds
│   │   ├── integrations/tradingview_autonomy.py
│   │   └── strategy/engine.py              # Alpha strategy
│   └── shared/
│       ├── telegram_bot.py                 # Agent Telegram interface
│       ├── enhanced_episodic_memory.py     # Trade memory bank
│       ├── dual_speed_cognition.py         # Fast+deep AI
│       ├── error_classifier.py
│       ├── health.py
│       └── smart_notifications.py
├── tests/unit/                             # 203 tests, 15 test files
├── cloudbuild-alpha.yaml                   # Cloud Build config
└── sapphire-web/                           # Vue 3 frontend (separate)
```

---

## 🧠 Context for AI Agents

- Owner: Ari (aristotlespec@gmail.com)
- Prefers comprehensive, production-ready implementations
- Has TradingView Premium account
- GitHub: `arigatoexpress/Sapphire` (PRIVATE)
- GCP: `sapphire-479610`
- Asana credentials stored (Client ID: 1213271794024058) but NOT to be used yet
- Directive: Focus on making agents and trading systems top-tier before external integrations
