# Sapphire Master Roadmap

> Last Updated: Feb 15, 2026 | Status: Phase 10 In Progress 🦅 | Tests: 1251 | Deploy: sapphire-alpha-00214-qsf | Gateway: openclaw-gateway-00004-dnd

## Vision
Build a top-tier autonomous crypto trading platform with secure multi-agent collaboration, crowdsourced swarm intelligence, and automated public presence.

---

## Phase 1: Production Hardening ⚡ ✅
_Get everything built into top-tier shape_

- [x] Verify fill confirmation loop in live environment (staged_live active)
- [x] Stress-test portfolio tracker with rapid fills
- [x] Tune cognition confidence thresholds with real data
- [x] Validate episodic memory learning from actual trades
- [x] Monitor activity feed digest quality in production
- [x] Tune digest interval based on trading activity patterns

## Phase 2: Security Architecture & Agent Segmentation 🔒
_Fully secure platform with isolated agent boundaries_

### Scout Agent Isolation
- [x] Segment Scout from agents with access to secrets/sensitive data (PR #20)
- [x] Implement strict communication boundaries (Scout ↔ Forum only) (PR #20)
- [x] Remove any direct access Scout has to execution, portfolio, or credentials (PR #20)
- [x] Audit all agent permission boundaries (PR #20)
- [x] Wire AgentGate.require() enforcement into main.py critical operations (PR #21)

### Prompt Injection Hardening
- [x] Audit all AI prompt paths for injection vulnerabilities (PR #20)
- [x] Implement input sanitization on all external data ingestion (PR #20)
- [x] Add injection detection to skill auditor patterns (PR #20)
- [x] Fuzz-test all Telegram command handlers (PR #22)
- [x] Harden forum post content against injection (PR #22)

### Cryptographic Security (Research)
- [ ] Research Zama FHE (github.com/zama-ai) — encrypted computation
- [ ] Research Ika (github.com/ika-rwth-aachen) — cryptographic techniques
- [ ] Identify feasible ZK proof / FHE implementations for data flows
- [ ] Prototype encrypted skill evaluation
- [ ] Design encrypted communication channels between agents

## Phase 3: Sapphire Forum Expansion 📖
_Rich collaborative forum as sole Scout ↔ Agent interface_

### Forum Infrastructure
- [x] Posts, Comments, Topics, Ideas as first-class entities (PR #23)
- [x] Topic categories: Trade Ideas, Strategy, Market Analysis, Platform (PR #23)
- [x] Threading, reply chains, post scoring, quality metrics (PR #23)

### Agent Personalities
- [x] Rich personality profiles for Sapphire 💎, Emerald 💚, Obsidian 🖤 (PR #23)
- [x] Distinct voice, perspective, expertise per agent (PR #23)
- [x] Natural conversational dynamics in forum threads (PR #24)

### Forum as Communication Layer
- [x] Route ALL Scout ↔ Agent communication through forum (PR #22/24)
- [x] Forum acts as audit trail for all inter-agent communication (PR #24)
- [x] Forum-based approval workflows (PR #25)

## Phase 4: Molthub Integration & Swarm Intelligence 🐝
_Secure external bot collaboration via crowdsourced trade ideas_

### Molthub Scout Outreach
- [x] Scout posts on Molthub inviting bots (TRADE IDEAS ONLY) (PR #30)
- [x] All external content passes through skill auditor (PR #30)
- [x] No sensitive data exposed in outbound communications (PR #30)

### Bot Reputation & Points System
- [x] Point/reputation schema for contributing agents (PR #26)
- [x] Track: ideas submitted, accuracy, profitability, info quality (PR #26)
- [x] Reward good actors, punish bad actors, permanent ban for malicious (PR #26)
- [x] Public leaderboard of contributing bots (PR #27)
- [x] Reputation-weighted trade idea aggregation (PR #28)

### Swarm Intelligence Framework
- [x] Aggregate trade ideas with reputation weighting (PR #28)
- [x] Consensus mechanisms for high-conviction trades (PR #28)
- [x] Collaborative learning across bot network (PR #29)

## Phase 5: Task Management System 📋
_Organized tracking of goals and progress_

- [x] Build internal TaskManager with full CRUD, milestones, deliverables (PR #31)
- [x] Asana MCP connector ready (credentials stored)
- [x] Agent tasks, milestones, deliverables tracking (PR #31)
- [x] Automated progress reports from agents (PR #31)
- [x] 6 Telegram commands (create, list, update, report, summary, agent) (PR #31)
- [x] 78 unit tests for task management (PR #31)

## Phase 6: Social Media Automation 📢
_Automated public presence across platforms_

### Infrastructure (PR #32)
- [x] MediaManager with publish queue, retry logic, approval workflows
- [x] TwitterClient (Tweepy API v2, thread splitting, async posting)
- [x] SubstackClient and LinkedInClient stubs
- [x] AI ContentGenerator (Gemini-powered, per-platform prompts)
- [x] Anti-slop quality controls (12 slop patterns, emoji density, repetition detection)
- [x] Quality scoring threshold (configurable, default 0.6)
- [x] Min posting interval enforcement per channel
- [x] AgentGate enforcement on MEDIA_PUBLISH and MEDIA_GENERATE
- [x] 7 Telegram commands (`/media status`, `mode`, `draft`, `publish`, `queue`, `approve/reject`, `generate`)
- [x] 67 unit tests for media system

### X/Twitter (@rariwrldd)
- [x] Tweepy API v2 client with thread splitting
- [ ] Configure API credentials in production
- [ ] Full automation of existing account

### Substack (Weekly)
- [x] Client stub ready for API/browser automation
- [ ] Implement actual Substack publishing
- [ ] Automated weekly post: progress, learnings, open experiment

### LinkedIn
- [x] Client stub ready for API integration
- [ ] Configure LinkedIn API credentials
- [ ] Mirror key Substack content with professional framing

## Phase 7: OpenClaw Agent Upgrade 🤖
_Verify and upgrade autonomous agent models_

- [x] Verify existing OpenClaw agents are working properly (dispatch, sessions, instruction routing) (PR #35)
- [x] Test all agent dispatch paths end-to-end (PR #35)
- [x] Identify current model versions used by each agent (PR #35)
- [x] Upgrade agent models to latest available versions (PR #35)
- [ ] Run comparison tests: old vs new model quality
- [ ] Update model configuration and redeploy

## Phase 8: Prediction Market Intelligence 🔮
_Polymarket + Kalshi data as trading signal sources_

### Data Infrastructure
- [x] Build `PredictionMarketFeed` base class (async polling + error backoff) (PR #40)
- [x] Implement Polymarket client (Gamma API for discovery, public endpoints) (PR #40)
- [x] Implement Kalshi client (REST API v2 for market data, public endpoints) (PR #40)
- [x] Unified `PredictionSignal` dataclass (market_id, question, probability, volume, source) (PR #40)
- [ ] Add WebSocket real-time feeds (Polymarket RTDS, Kalshi ticker channel)
- [ ] Rate limiting: Polymarket 1,000/hr, Kalshi tiered
- [x] Kalshi authenticated API support (API key from env/constructor) (PR #41)

### Signal Integration
- [x] Crypto-relevant market filter (BTC price, ETH price, crypto regulation, macro events) (PR #40)
- [x] Probability-to-sentiment mapper (>70% bullish → positive signal, <30% → negative) (PR #40)
- [x] Feed prediction signals into DualSpeedCognition context (PR #40)
- [x] Weight prediction data by market liquidity and volume (PR #40)
- [x] Macro event calendar from Kalshi categories (jobs reports, CPI, Fed decisions) (PR #40)

### Cross-Venue Arbitrage Detection
- [x] Fuzzy market name normalization for cross-venue matching (PR #41)
- [x] ArbitrageOpportunity dataclass (spread, confidence, direction) (PR #41)
- [x] Cross-venue spread detection (Polymarket vs Kalshi, >2% threshold) (PR #41)
- [x] Volume-weighted confidence scoring (balanced vs one-sided liquidity) (PR #41)
- [x] Arbitrage context injection into cognition prompts (PR #41)
- [x] Forum summaries include arbitrage alerts (PR #41)
- [x] Telegram `/arbitrage` command (PR #41)

### Forum & Swarm Integration
- [x] Scout posts prediction market summaries to forum (PR #40)
- [x] Agents can reference prediction probabilities in trade idea reasoning (PR #40)
- [x] Swarm consensus incorporates prediction market sentiment as virtual voter (PR #42)

### Whale Activity & Manipulation Awareness
- [x] Volume history tracking in feed base class (volume_1h_ago, volume_change) (PR #42)
- [x] Whale activity detection (>2x volume + >5% probability shift) (PR #42)
- [x] Volume spike detection (>3x in 1 hour) (PR #42)
- [x] Manipulation risk classification: wash_trading, insider_pattern, low_liquidity_pump (PR #42)
- [x] Whale/manipulation flags in signal context_string for cognition (PR #42)
- [x] Market intelligence alerts injected into cognition prompts (PR #42)
- [x] Forum summaries include whale/manipulation alerts (PR #42)
- [x] Telegram `/pm_whale` and `/pm_manipulation` commands (PR #42)

### Monitoring & Quality
- [x] Prediction accuracy tracker with Brier score calibration (PR #42)
- [x] Per-source and high-conviction accuracy tracking (PR #42)
- [x] Dashboard API endpoint `/api/v2/predictions/dashboard` (PR #42)
- [x] Telegram commands: `/predictions`, `/prediction <market>`, `/prediction_sentiment`, `/pm_high` (PR #40)
- [x] Telegram commands: `/arbitrage`, `/pm_arb` (PR #41)
- [x] Telegram commands: `/pm_accuracy`, `/pm_whale`, `/pm_manipulation` (PR #42)
- [x] Unit tests for feed clients, signal mapping, and integration (97 tests) (PR #40)
- [x] Unit tests for arbitrage detection, fuzzy matching, confidence scoring (47 new tests, 144 total) (PR #41)
- [x] Unit tests for swarm PM, accuracy, whale detection, manipulation (81 new tests, 225 total) (PR #42)

## Phase 9: Virtuals Integration (Base) 🌐 (DEFERRED)
_On-chain agent presence via Virtuals protocol — revisit later_

- [ ] Research Virtuals protocol on Base
- [ ] Identify integration points with Sapphire agents
- [ ] Design tokenomics alignment with reputation system
- [ ] Prototype on-chain agent identity

## Phase 10: OpenClaw-First Autonomous Operations 🦅
_Full agent autonomy — OBSIDIAN first, then multi-agent_

### Permission & Escalation (PR #50)
- [x] 7 new capabilities: CODE_READ/WRITE/DEPLOY/REVIEW, INFRASTRUCTURE_MODIFY, CI_CD_TRIGGER, HEALTH_MONITOR
- [x] Updated agent role sets (OBSIDIAN gets full code lifecycle, EMERALD gets review, SAPPHIRE gets read-only)
- [x] Risk tier mapping (low/medium/high) for all 31 capabilities
- [x] ApprovalPolicy class with graduated escalation: auto_approve / notify_proceed / require_approval
- [x] Proposal storage and decision workflow in AlphaEngine

### OpenClaw Gateway Dispatcher (PR #50)
- [x] OpenClawDispatcher class replacing tv_autonomy (was always None)
- [x] Direct HTTP dispatch to gateway (bearer token auth, session management)
- [x] Scope locks: allowed_repo_scope, allowed_project_scope
- [x] Wired into autonomy dispatch cycle (OpenClaw primary, tv_autonomy fallback)
- [x] Model switched from Gemini to Claude Opus 4.6 (anthropic/claude-opus-4-20250514)
- [x] Single-agent mode: OBSIDIAN only (SAPPHIRE/EMERALD preserved but disabled for testing)

### Multi-Agent Dispatch (PR #50)
- [x] Structured trigger routing with _autonomy_trigger_info()
- [x] OBSIDIAN-only initially (future multi-agent rotation ready)
- [x] Trigger categories: emergency / infrastructure / maintenance / improvement / review

### Telegram Commands (PR #50)
- [x] `/proposals` — list pending proposals
- [x] `/diff <key>` — show compact diff for a proposal
- [x] `/approve_proposal <key>` — approve a pending proposal
- [x] `/reject_proposal <key>` — reject a pending proposal
- [x] `/health` — run health diagnostics
- [x] `/roadmap_sync` — sync roadmap items to tasks
- [x] `/ci_status` — show CI feedback processor status
- [x] `/openclaw_status` — show OpenClaw dispatcher status
- [x] ChatIntentEngine updated with operations intent type

### CI/CD Feedback Loop (PR #50)
- [x] CIFeedbackProcessor: pytest output parsing → EMERALD tasks
- [x] Build failure parsing → OBSIDIAN tasks (critical priority)
- [x] Capped at 10 auto-generated tasks per CI run

### Roadmap-Aware Task Generation (PR #50)
- [x] RoadmapParser scans ROADMAP.md for incomplete `- [ ]` items
- [x] Agent inference from phase keywords (word-boundary regex)
- [x] Deduplicated task creation (skips existing active tasks)

### Testing (PR #50)
- [x] 121 new tests (1244 total): agent permissions, OpenClaw dispatch, CI feedback, roadmap parser
- [x] Frontend builds clean

### Production Enablement
- [x] Set OPENCLAW_GATEWAY_TOKEN in Cloud Run env vars
- [x] Set SAPPHIRE_AUTONOMY_ALLOW_CODE_CHANGES=true
- [x] Set SAPPHIRE_AUTONOMY_ALLOW_GCLOUD_CHANGES=true
- [x] Run enable_full_autonomy.sh for IAM roles (8 roles on sapphire-main-sa)
- [x] Run autonomy_readiness_check.sh (28/28 PASS)
- [x] ENABLED_VENUES=ASTER;LIGHTER

### OpenClaw Cloud Deployment (PR #51)
- [x] Built OpenClaw gateway Docker image on Cloud Build
- [x] Deployed as Cloud Run service: `openclaw-gateway`
- [x] Gateway URL: `https://openclaw-gateway-267358751314.us-central1.run.app`
- [x] Enabled HTTP endpoints: `/v1/chat/completions`, `/v1/responses`
- [x] Updated OpenClawDispatcher to use OpenAI-compatible Chat Completions API
- [x] Default gateway URL points to Cloud Run instead of localhost
- [x] Agent routing via `x-openclaw-agent-id` header
- [x] Updated OPENCLAW_GATEWAY_URL env var on sapphire-alpha
- [x] Gateway correctly resolves model to `anthropic/claude-opus-4-20250514`

### Multi-Agent Gateway Enablement
- [x] OBSIDIAN 🖤: full access — read/write/edit, exec, browser, web, sessions, memory, cron, gateway
- [x] EMERALD 💚: code-focused — read/write/edit, exec, web, sessions (inc. spawn), memory
- [x] SAPPHIRE 💎: read-only oversight — read, exec, web, sessions (no spawn/write), memory
- [x] All 3 agents respond HTTP 200 on `/v1/chat/completions` with proper routing
- [x] `/openclaw_smoke` Telegram command: pings all 3 agents and reports results
- [x] ChatIntentEngine updated: "ping agents", "smoke test" → OPENCLAW_SMOKE
- [x] 5 new multi-agent routing tests (1251 total)
- [x] Gateway revision: `openclaw-gateway-00004-dnd`

### Remaining
- [ ] Top up Anthropic API credits (gateway returns "credit balance too low")
- [ ] Verify from Telegram: /autonomy, /health, /proposals, /roadmap_sync, /openclaw_smoke
- [ ] End-to-end autonomy cycle test (trigger → dispatch → agent executes → results)

---

## Execution Priority
```
Phase 1 ✅  →  Phase 2 ✅  →  Phase 3 ✅  →  Phase 4 ✅  →  Phase 5 ✅  →  Phase 6 ✅  →  Phase 7 ✅  →  Phase 8 ✅  →  Phase 10 🦅
Harden        Security       Forum          Swarm          Tracking       Social           OpenClaw       Predictions      Autonomy
```

## Completed Milestones
- ✅ PR #15: Portfolio Tracker (position lifecycle, P&L, ring buffer)
- ✅ PR #16: Fill Confirmation Loop (async Future-based, timeout/retry)
- ✅ PR #17: Cognitive Systems (episodic memory, dual-speed cognition)
- ✅ PR #18: Skill Security Auditor (8 threat categories, isnad chains)
- ✅ PR #19: Smart Notifications (autonomy spam fix, agent activity feed)
- ✅ PR #20: Security Hardening Phase 2 (agent permissions, prompt injection defense, sanitizer)
- ✅ PR #21: AgentGate Enforcement (12 critical operation gates, /permissions command)
- ✅ PR #22: Forum Injection Hardening + Fuzz Tests (18 adversarial tests, forum content blocking)
- ✅ PR #23: Phase 3 Forum Expansion (categories, voting, threading, quality metrics, agent profiles)
- ✅ PR #24: Forum Telegram Wiring (5 new commands, 5 engine handlers, category/threading passthrough)
- ✅ PR #25: Forum Approval Workflows (consensus voting, governance-lane topics, auto-resolution)
- ✅ PR #26: Bot Reputation & Points System (weighted composite scoring, auto-ban, penalties, 30 tests)
- ✅ PR #27: Reputation Engine Wiring (5 Telegram commands, REPUTATION_READ/ADMIN capabilities)
- ✅ PR #28: Swarm Intelligence Aggregation (reputation-weighted consensus, conviction scoring, idea lifecycle)
- ✅ PR #29: Collaborative Learning (swarm knowledge extraction, adaptive confidence ±25%, conviction calibration)
- ✅ PR #30: Molthub Outreach (template library, regex credential leak detection, inbound idea validation)
- ✅ PR #31: Task Management System (CRUD, milestones, deliverables, progress reports, 6 Telegram commands)
- ✅ PR #32: Phase 6 Social Media Automation (AI content gen, anti-slop quality controls, 7 Telegram commands, 67 tests)
- ✅ PR #33: Masterplan Improvements (security hardening, frontend redesign, 3 test suites, new modules)
- ✅ PR #34: Telegram Handler Extraction (1,632 lines extracted from main.py → telegram_handlers.py)
- ✅ PR #35: OpenClaw Model Upgrade (18 files upgraded: gemini-2.0→2.5, gemini-3.0→3-flash-preview across all services)
- ✅ PR #36: Cognition/Memory Test Suite (118 tests for dual-speed cognition, episodic memory, enhanced memory)
- ✅ PR #37: Fill Confirmation Test Expansion (16 new tests: venue normalization, pause/resume, allocation bounds, retry logic)
- ✅ PR #38: Resilience Loop 1 (critical fixes, datetime modernization, prediction market roadmap)
- ✅ PR #39: Hardening Loop 2 (retry logic, fill cleanup, observability, config validation)
- ✅ PR #40: Phase 8 Prediction Market Intelligence (Polymarket + Kalshi feeds, 97 tests, 4 Telegram commands)
- ✅ PR #41: Cross-Venue Arbitrage Detection (fuzzy matching, spread detection, confidence scoring, 47 new tests)
- ✅ PR #42: Swarm PM Integration, Accuracy Tracking, Whale Detection, Dashboard API (81 new tests)
- ✅ PR #43-#49: Deploy fixes, frontend, accessibility, e2e tests, skeleton loading, WebSocket dashboard
- ✅ PR #50: OpenClaw-First Autonomous Operations (7 capabilities, OpenClawDispatcher, CI feedback, RoadmapParser, 121 new tests)
- ✅ 1244 tests passing
