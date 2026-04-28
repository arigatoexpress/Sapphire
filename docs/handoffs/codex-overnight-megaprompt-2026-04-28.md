# Codex Overnight Megaprompt — Sapphire OS — 2026-04-28

> **Operator usage**: paste this entire document into a fresh Codex session as the system / first message. Codex should read the WHOLE thing top-to-bottom before starting any tool calls. The end of the document defines the closeout the operator expects on the next morning.

---

## 0. Mission

You are Codex, working alone overnight on the Sapphire OS monorepo at `~/Code/Sapphire` with **full autonomy granted by the operator** (Ari) for the duration of his sleep window. Make as much **acquisition-grade, high-impact** progress as you can across the 6 lanes defined below. The mental model is: a Palantir / Robinhood corp-dev reviewer should look at tomorrow morning's `git log` and see meaningful product surfaces and durability work, not just churn.

**You are NOT the only autonomous worker who has touched this repo this cycle.** A Claude Code session and three previous Codex agents (A, B, C) just merged 10 PRs (`#371`–`#380`). The state at start is recorded in §2.

If your runtime supports parallel sub-agents, dispatch the 6 lanes concurrently, each in its own git worktree. If not, do them sequentially — but in the order listed (highest-impact first).

---

## 1. Non-negotiable constraints

These bind every commit, every PR, every action:

1. **No-spend posture is sacred.** Every commit message ends with `[skip ci]`. Hosted GitHub Actions billing is gated by `vars.SAPPHIRE_RUNNER`; the local-CI runner is the merge gate. If you push a commit without `[skip ci]` and a hosted run gets queued, **cancel the run immediately** with `gh run cancel <run-id>`.
2. **Don't touch the trading critical path without operator confirmation.** That means: `services/alpha/`, `lib/portfolio/robinhood.py`, `lib/trading/`, `lib/analytics/risk_engine.py`, `lib/analytics/strategies.py`, `lib/core/kill_switch.py`, `lib/core/confirmation_firewall.py`, `services/webhook/`, `contracts/`. CODEOWNERS already gates these — do not author changes that require a review you cannot get.
3. **Do not touch satellite repos.** Sapphire monorepo only. Specifically NOT: `claw-code`, `Project-Go-Forward`, `regional-intel-workbench`, `tradingview-mcp`, `Cointracker`, `cyber-threat-bot`, `hermes-agent` (the `~/Code/hermes-agent` checkout, distinct from `~/.hermes/`), `kimi-tools`.
4. **Secrets are read-only and live-mode-only.** `~/.sapphire/secrets.env`, `~/.config/sapphire-secrets/`, and the LaunchAgent plists are only ever READ when an env-flag-gated live path triggers. They are never echoed, logged, or committed.
5. **Dry-run is the default for any new external-API surface.** Mirror `plugins/claw-sapphire/tools/internal/gemini_ooda.py` and the new `plugins/claw-sapphire/tools/internal/vertex_eval.py` — sensitivity gate, hard caps, secrets only loaded when the live env flag is set, cache + counters under `~/.cache/sapphire/`.
6. **Provenance envelopes on all generated artifacts.** Use `lib/core/provenance.py`. Every emitted JSON deliverable gets a sibling `.envelope.json` with `{generator, model, prompt_hash, source_hashes, ttl, version}`.
7. **No README test counts during multi-lane work.** The orchestrator updates `README.md` once at the end. Don't fight rebases by everyone editing the same row.
8. **No new top-level dependencies** unless the lane explicitly authorizes them. Lane 1 (Telethon) is the only lane authorized to add a new prod dep. Everything else is stdlib + already-pinned.
9. **Worktree-per-lane.** Each lane creates its own worktree at `/Users/aribs/Code/_worktrees/sapphire-<branch>` and works there. Clean up worktrees when the lane's PR merges. Never commit directly to canonical `~/Code/Sapphire`.
10. **Open PR but DO NOT auto-merge** unless local verification is green: `ruff check .`, both pytest blocks (unit + plugin), `validate_tool_registry.py`, and `production_readiness_sweep.py --no-external` (which must report `0 FAIL`). If green, admin-squash-merge with `gh pr merge <N> --squash --admin --delete-branch`.

---

## 2. State at start

Re-verify these before dispatching any work:

```bash
cd ~/Code/Sapphire
git fetch --all --quiet
git rev-parse --short HEAD     # expect: 640c9e4a (or descendant)
gh pr list --state open         # expect: empty
gh issue list --state open      # expect: empty
/usr/local/bin/python3 -m pytest tests/unit/ -q --tb=short        # expect: 3,758 passed, 1 skipped, 21 xfailed
/usr/local/bin/python3 -m pytest plugins/claw-sapphire/tests/ -q  # expect: 270 passed
/usr/local/bin/python3 scripts/validate_tool_registry.py          # expect: registry=40, errors=0
/usr/local/bin/python3 scripts/ops/production_readiness_sweep.py --no-external | tail -3  # expect: 0 FAIL
```

If any of those don't match, **stop and write a short report explaining the drift** before proceeding.

Reference reading (skim before lanes 1–3):
- `docs/handoffs/claude-night-session-2026-04-28-report.md` — what just landed
- `docs/handoffs/codex-overnight-agent-A-2026-04-28-report.md`
- `docs/handoffs/codex-overnight-agent-B-2026-04-28-report.md`
- `docs/handoffs/codex-overnight-agent-C-2026-04-28-report.md`
- `CLAUDE.md` — repo-level conventions (paths, module map, gotchas)
- `plugins/claw-sapphire/tools/internal/gemini_ooda.py` — canonical external-API tool template
- `plugins/claw-sapphire/tools/internal/vertex_eval.py` — most recently landed external-API tool, copy this shape
- `plugins/claw-sapphire/tools/internal/sapphire_pm_bot.py` + `_telegram_safety.py` — Telegram patterns
- `lib/core/provenance.py` — envelope helper

---

## 3. Lanes

You will work on six lanes. Each is self-contained and ends in a single PR (do not bundle).

### LANE 1 — Telegram Channel Intel Reader (NEW SURFACE — HIGHEST PRIORITY)

**Why it matters**: Sapphire already publishes via Telegram (hermes-agent gateway) and has an operator console (`sapphire_pm_bot`). What it lacks is a **read** path: a curated stream of high-quality information from reputable Telegram channels (crypto on-chain analysts, macro desks, AI-research orgs, threat-intel feeds) that funnels into the existing intel + signal pipelines. This is a strategic capability gap that an acquirer will see immediately — Sapphire is currently a one-way Telegram surface, this lane makes it bi-directional.

**Worktree + branch**: `/Users/aribs/Code/_worktrees/sapphire-telegram-intel-reader` on `feat/telegram-channel-intel-reader`.

**Architecture**:
- Primary path: **Telethon-based MTProto userbot** — full read access to any channel the configured account has joined.
- Fallback path: **bot-mode reader** — for channels the operator has added the existing hermes bot to.
- Both paths share a quality-filter + sink pipeline; the reader implementation is swappable behind an interface.

**Files**:
- `services/telegram_intel/__init__.py`
- `services/telegram_intel/reader.py` — async `TelegramIntelReader` class with two backends (`MTProtoBackend`, `BotAPIBackend`) hidden behind a `ReaderBackend` protocol.
- `services/telegram_intel/quality_filter.py` — pure heuristics module (no I/O, no env, no network). Length, link density, structured-data signals, regex denylist for spam patterns. Returns `QualityScore { score: float, tags: list[str], reason: str }`.
- `services/telegram_intel/classifier.py` — optional LLM-rating layer. Calls the local inference proxy at `http://localhost:11435/v1/chat/completions` with the `balanced` (hermes3:8b) model. Topic tags: `crypto`, `macro`, `ai`, `security`, `trading`, `governance`, `noise`. Hard timeout 5 s; on timeout fall back to heuristic-only score.
- `services/telegram_intel/sink.py` — writes to `data/telegram_intel/<YYYY-MM-DD>/messages.jsonl` (one msg per line, redacted), pushes a high-priority subset to the event bus (`telegram.intel.signal`, `telegram.intel.warning`).
- `services/telegram_intel/run.py` — daemon entrypoint. Reads `~/.sapphire/telegram_channels.yaml`, creates a reader, runs the polling loop. Prints structured logs.
- `services/telegram_intel/launchagent/com.sapphire.telegram-intel.plist` — LaunchAgent template. **Do not install it** — leave a runbook section for the operator.
- `plugins/claw-sapphire/tools/internal/telegram_intel.py` — stdin-JSON plugin tool. Actions: `status`, `pull-once` (one-shot poll without daemon), `recent` (read latest N messages from the sink), `quality-test` (score a pasted message), `models`. Mirrors the `gemini_ooda` shape exactly.
- `plugins/claw-sapphire/tools/telegram_intel.py` — 3-line shim. Copy `vertex_eval.py` shim verbatim, change target path.
- `tests/unit/test_telegram_intel_reader.py` — ≥ 20 cases. Mock Telethon and Bot API entirely. Assert: env-flag gating (live requires `SAPPHIRE_TELEGRAM_INTEL_LIVE=1` + session-file existence + non-empty channel list), graceful empty-config behavior, message redaction (no phone numbers / @handles for non-channel-author users persisted), throttle on poll loop, error backoff.
- `tests/unit/test_telegram_intel_quality_filter.py` — ≥ 25 cases. Heuristic correctness, idempotence, locale stability (CJK + diacritics), edge cases (empty, all-emoji, link-only, code-block-only).
- `tests/unit/test_telegram_intel_sink.py` — ≥ 8 cases. Sink writes JSONL + envelope, redacts PII, dedupes by message ID + channel.
- `plugins/claw-sapphire/tests/test_telegram_intel.py` — ≥ 8 plugin tests for the stdin-JSON contract.
- `infra/tool-registry.yaml` — append entry for `telegram_intel` under "AI complement" or a new "Intel" comment block. `status: internal`. `agent_facing: false`.
- `docs/products/telegram-intel-reader-0.1.0.md` — product doc (1000+ words). Why this matters, architecture, channel curation philosophy, dry-run vs live, caps.
- `docs/ops/telegram-intel-reader-runbook.md` — runbook (1500+ words). Setup (Telethon API ID/hash, session file generation, bot-add flow), config schema, daemon install, troubleshooting, cap state, soak posture.
- `docs/security/telegram-intel-threat-model.md` — short threat-model doc (700+ words). Trust boundary (Telegram CDN / message origin), attacker profile (channel admin sneaking malicious links), mitigations (URL-defang in sink, no auto-execution of any payload), residual risks.
- `~/.sapphire/telegram_channels.example.yaml` — committed at `infra/telegram_channels.example.yaml` with documented schema and ZERO real channel handles. Operator copies + edits to `~/.sapphire/telegram_channels.yaml`.

**Schema** for `~/.sapphire/telegram_channels.yaml`:
```yaml
version: 1
defaults:
  poll_interval_seconds: 300
  max_messages_per_poll: 50
  min_quality_score: 0.5
  min_message_length: 50
channels:
  - id: "@example_crypto_intel"           # public handle OR numeric channel ID
    category: crypto                       # one of: crypto, macro, ai, security, trading, governance
    weight: 1.0                            # multiplier on quality score
    backend: mtproto                       # or: bot
    enabled: false                         # operator opts-in per channel
    notes: "Brief description for runbook"
```

**Caps** (mirror gemini_ooda style):
- `MAX_MESSAGES_PER_HOUR_HARD = 600` (across all channels)
- `MAX_LIVE_LLM_CLASSIFICATIONS_PER_HOUR = 200`
- `MAX_CHANNELS_HARD = 32`
- `MAX_MESSAGE_LENGTH_HARD = 8_000` chars (truncate with `[…]`)

**Constraints**:
- **New prod dep authorized**: `telethon>=1.36,<2.0` in `services/telegram_intel/requirements.txt` ONLY (not in root `requirements.txt`). Tests mock Telethon entirely so the unit suite doesn't import it. Document the install in the runbook.
- The userbot session file lives at `~/.sapphire/telegram_intel.session` (mode `0600`). Generated interactively one time by the operator running `python3 -m services.telegram_intel.run --setup-session`. The daemon refuses to start without it AND refuses to start without `SAPPHIRE_TELEGRAM_INTEL_LIVE=1`.
- **No PII persistence**: redact phone numbers, `@username` mentions of non-author users, full names. Channel author and channel handle are kept (those are the source attribution).
- **URL defang**: every URL in stored messages is rewritten as `hxxps://example.com/path` style — humans can re-encode but no automated system follows them.
- **Provenance envelope** on each `data/telegram_intel/<date>/messages.jsonl` daily file.

**Verification**:
```bash
ruff check .
/usr/local/bin/python3 -m pytest tests/unit/test_telegram_intel_reader.py tests/unit/test_telegram_intel_quality_filter.py tests/unit/test_telegram_intel_sink.py plugins/claw-sapphire/tests/test_telegram_intel.py -q
/usr/local/bin/python3 -m pytest tests/unit/ -q
/usr/local/bin/python3 -m pytest plugins/claw-sapphire/tests/ -q
/usr/local/bin/python3 scripts/validate_tool_registry.py
/usr/local/bin/python3 scripts/ops/production_readiness_sweep.py --no-external | tail -3
```

**PR title**: `feat(intel): telegram channel intel reader 0.1.0`

---

### LANE 2 — Wire `routine_pause` flag-check into scheduled tasks

**Why it matters**: PR #373 shipped Telegram operator commands `/routines pause <name>` and `/routines resume <name>` that drop / remove flag files at `~/.sapphire/routine_pause/<name>`. The mechanism is delivered, but **scheduled tasks don't yet check the flag**, so pausing today is state-of-intent — the routine still fires. Closing this gap makes the safety surface real.

**Worktree + branch**: `/Users/aribs/Code/_worktrees/sapphire-routine-pause-wiring` on `feat/routine-pause-flag-check`.

**Approach**:
1. Add a single helper at `lib/core/routine_pause.py`:
   ```python
   from pathlib import Path
   import os, sys

   PAUSE_DIR = Path.home() / ".sapphire" / "routine_pause"

   def is_paused(name: str) -> bool:
       """Return True if a routine_pause flag file exists for `name`."""
       try:
           return (PAUSE_DIR / name).exists()
       except OSError:
           return False

   def abort_if_paused(name: str, *, log=print) -> None:
       """If paused, log a structured message and exit(0)."""
       if is_paused(name):
           log(f"[routine_pause] {name!r} is paused — flag at {PAUSE_DIR / name}; exiting cleanly")
           sys.exit(0)
   ```
2. Add `tests/unit/test_routine_pause.py` covering: no-flag, flag-present, OSError-on-read fallback, name sanitization (paths can't escape PAUSE_DIR — assert `..` segments rejected).
3. Read every SKILL.md under `~/.claude/scheduled-tasks/*/SKILL.md` AND every script under `services/*/run.py` and `plugins/claw-sapphire/tools/internal/morning_digest.py` and similar daemon entrypoints. For each task that should be pausable (every 22+ scheduled task), add at the top of the SKILL.md (after frontmatter) a single line:
   > **Pausable**: this task checks `~/.sapphire/routine_pause/<name>` at start. If the flag is present the task exits cleanly without firing.
4. For tasks driven by Python scripts that you can edit: insert `from lib.core.routine_pause import abort_if_paused; abort_if_paused("<name>")` near the top of the entrypoint.
5. For SKILL.md-driven tasks (where the body is a prompt, not a script), add the check as the first instruction in the prompt.
6. Update `docs/ops/telegram-operator-console-runbook.md` to flip the "currently state-of-intent" caveat to "now functionally enforced".

**Constraints**:
- Do NOT touch trading critical path scripts (`services/alpha/*`, `services/webhook/*`).
- Sanitize the routine name in `is_paused` — strip `..`, `/`, null bytes — so a malicious operator can't traverse out of `PAUSE_DIR`. Test this.
- Routine names must match `^[a-zA-Z0-9_-]+$`.

**PR title**: `feat(ops): wire routine_pause flag check into scheduled tasks`

---

### LANE 3 — Real Vertex `text-embedding-gecko@003` embedder (BQ vector follow-up)

**Why it matters**: PR #376 shipped `lib/intel/bq_vector_store.py` with a deterministic mock embedder so the API and tests work. The runbook explicitly advertises real-Vertex as a follow-up. This lane lands it — the BQ vector store is now a real semantic substrate, not a hash-based stand-in.

**Worktree + branch**: `/Users/aribs/Code/_worktrees/sapphire-vertex-embedder` on `feat/vertex-gecko-embedder`.

**Files**:
- `lib/intel/embedders.py` — augment with a `VertexGeckoEmbedder` class. Lazy-imports `google-generativeai` inside `__init__` (already pinned in `requirements-test.txt`). Refuses to embed unless `SAPPHIRE_VERTEX_EMBEDDER_LIVE=1` AND `GEMINI_API_KEY` (or `GOOGLE_API_KEY`) is in `~/.sapphire/secrets.env`.
- `lib/intel/bq_vector_store.py` — register the new embedder in the `models` action output.
- Caps: `MAX_EMBED_CALLS_PER_HOUR = 100`, `MAX_EMBED_TOKENS_PER_MONTH = 1_000_000`. Counters under `~/.cache/sapphire/vertex_embedder/`.
- `tests/unit/test_vertex_gecko_embedder.py` — ≥ 12 cases: dry-run default returns the deterministic mock, live env flag without key falls back to mock with `mode_actual="dry-run-safety"`, live with mocked SDK returns 768-dim vector, caps trigger fallback, cache short-circuits repeat calls, dimension check rejects mismatched server output.
- `docs/ops/intel-search-runbook.md` — update the "embedder swap-in" section to point to the new class.

**Constraints**:
- Do NOT call the real Vertex API in tests — mock `google.generativeai.embed_content` and assert call args.
- Cache key includes the model name, dimension, and SHA-256 of input text.

**PR title**: `feat(intel): vertex text-embedding-gecko@003 embedder`

---

### LANE 4 — Live BigQuery upsert path (BQ vector follow-up)

**Why it matters**: PR #376's mock backend persists to a local JSONL. The runbook advertises live as a 0.1.0 follow-up. This lane wires up the real BigQuery client for `upsert` and `query` (using BQ's `VECTOR_SEARCH` SQL).

**Worktree + branch**: `/Users/aribs/Code/_worktrees/sapphire-bq-vector-live` on `feat/bq-vector-live-upsert`.

**Files**:
- `lib/intel/bq_vector_store.py` — replace the `_live_upsert_not_implemented` stub with a real `_live_upsert` using `google.cloud.bigquery`. Same for `_live_query` using a `VECTOR_SEARCH` SQL template.
- `tests/unit/test_bq_vector_store_live.py` — ≥ 15 cases. Mock `google.cloud.bigquery.Client` entirely. Assert: live triggers only when all three env vars agree, table-creation idempotency, schema correctness (columns: id, text, embedding ARRAY<FLOAT64>, source, metadata JSON, created_at TIMESTAMP), VECTOR_SEARCH SQL parameterization, error path on auth failure, no live calls when env unset.
- `docs/products/bq-vector-retrieval-0.1.0.md` — flip the "live not implemented" line to "live wired".

**Constraints**:
- Do NOT make real BigQuery calls. Tests are mock-only.
- Refuse live operations unless `SAPPHIRE_BQ_LIVE=1` AND `GOOGLE_APPLICATION_CREDENTIALS` is set AND `SAPPHIRE_BQ_PROJECT` is non-empty.
- Do NOT add `google-cloud-bigquery` to root requirements; it's already pinned in `requirements-test.txt`.

**PR title**: `feat(intel): live BigQuery upsert + VECTOR_SEARCH path`

---

### LANE 5 — Hyperliquid signal subscription

**Why it matters**: This is on the Wave 4 backlog from `project_2026-04-27_evening_pickup.md`. Hyperliquid is a Layer-1 perpetuals DEX with a public WebSocket feed; subscribing to it gives Sapphire signal-quality input that's structurally orthogonal to the TradingView webhook. Operator's `services/hyperliquid/` is currently a stub.

**Worktree + branch**: `/Users/aribs/Code/_worktrees/sapphire-hyperliquid-feed` on `feat/hyperliquid-signal-subscription`.

**Files**:
- `services/hyperliquid/feed.py` — async WebSocket subscriber for the Hyperliquid public WS endpoint (`wss://api.hyperliquid.xyz/ws`). Subscribes to:
  - `trades` for BTC, ETH, SOL (configurable via `~/.sapphire/hyperliquid_symbols.yaml`)
  - `bbo` (best bid/offer)
  - `l2Book` for the same symbols at 10-level depth
- `services/hyperliquid/signal.py` — emits structured `HyperliquidSignal` events to the event bus (`hyperliquid.trade`, `hyperliquid.imbalance`, `hyperliquid.book.thin`) when conditions are met. Conditions:
  - Trade > $250k notional → `hyperliquid.trade`
  - Top-of-book imbalance > 3:1 sustained > 10s → `hyperliquid.imbalance`
  - Aggregate top-10 depth drops > 30% in 60s → `hyperliquid.book.thin`
- `services/hyperliquid/run.py` — daemon entrypoint with the same `routine_pause` check as Lane 2 (depend on Lane 2 if Lane 2 lands first; otherwise inline a copy of the helper).
- `services/hyperliquid/launchagent/com.sapphire.hyperliquid-feed.plist` — LaunchAgent template; do NOT install.
- `plugins/claw-sapphire/tools/internal/hyperliquid.py` — stdin-JSON tool. Actions: `status`, `latest`, `subscribe-test` (one-shot dry-run). Mirrors `gemini_ooda` shape.
- `plugins/claw-sapphire/tools/hyperliquid.py` — 3-line shim.
- `tests/unit/test_hyperliquid_feed.py` — ≥ 18 cases. Mock the websocket (`websockets.connect`) and assert: subscription messages, reconnection on drop, signal emission rules, env-flag gating (`SAPPHIRE_HYPERLIQUID_LIVE=1` required for daemon), max symbols cap, max signals/hour cap.
- `tests/unit/test_hyperliquid_signal.py` — ≥ 12 cases for the imbalance/depth/notional logic.
- `plugins/claw-sapphire/tests/test_hyperliquid_tool.py` — ≥ 8 plugin tests.
- `infra/tool-registry.yaml` — append `hyperliquid` entry.
- `docs/products/hyperliquid-signal-0.1.0.md` — product doc (700+ words).
- `docs/ops/hyperliquid-feed-runbook.md` — runbook.

**Caps**:
- `MAX_SYMBOLS = 8`
- `MAX_SIGNALS_PER_HOUR = 240`
- `MAX_RECONNECT_ATTEMPTS_PER_HOUR = 12`

**Constraints**:
- This is **paper / signal-only**. The feed produces input signals; it MUST NOT execute trades.
- No wallet keys touched.
- The Hyperliquid public WS does not require authentication for read-only subscriptions; do not attempt authenticated endpoints.

**PR title**: `feat(signals): hyperliquid public-feed signal subscription`

---

### LANE 6 — Sovereign-thesis story mode + `/diligence` aggregate dashboard page

**Why it matters**: Two related diligence-packet UI surfaces from `project_2026-04-27_evening_pickup.md`. The diligence packet (PR #341) is markdown-only; the operator wants narrative-style HTML pages that a corp-dev reviewer can scroll through.

**Worktree + branch**: `/Users/aribs/Code/_worktrees/sapphire-diligence-ui` on `feat/diligence-ui-surfaces`.

**Files**:
- `services/dashboard/templates/pages/sovereign_thesis_story.html` — narrative version of the existing `/sovereign-thesis` panel. Section structure: Thesis → Evidence → Convergence → Bear case → Acquirer fit. Read-only. Use existing base template + nav.
- `services/dashboard/templates/pages/diligence.html` — aggregate page that surfaces summaries from `docs/diligence/00`–`09` and embeds:
  - Risk-kernel headline numbers (`/api/risk-kernel-summary` — new lightweight endpoint)
  - Provenance verifier status (`/api/provenance-summary` — new)
  - Test count + suite health (`/api/test-suite-health` — new)
  - Live LaunchAgent status table (read-only, just labels + last_exit)
- `services/dashboard/app.py` — add the routes + the three new `/api/*` endpoints. JSON outputs are paste-safe; HTML inherits `sapphire/sapphire` basic auth.
- `tests/unit/test_dashboard_diligence_routes.py` — ≥ 12 cases (route renders, auth required, JSON shape stable, no PII leak).
- `tests/unit/test_dashboard_sovereign_thesis_story.py` — ≥ 6 cases.
- `docs/ops/dashboard-product-pages-runbook.md` — extend with the two new pages.

**Constraints**:
- Read-only (GET) only.
- Auth inherited; do not weaken.
- No new external deps.
- All test fixtures use Flask test client; do not start a real server.

**PR title**: `feat(dashboard): sovereign-thesis story mode + diligence aggregate page`

---

## 4. Verification protocol (every lane)

Before opening a PR, you MUST get all six of these green from inside the worktree:

```bash
ruff check .
/usr/local/bin/python3 -m pytest <NEW_TEST_FILES> -q --tb=short
/usr/local/bin/python3 -m pytest tests/unit/ -q --tb=short
/usr/local/bin/python3 -m pytest plugins/claw-sapphire/tests/ -q --tb=short
/usr/local/bin/python3 scripts/validate_tool_registry.py
/usr/local/bin/python3 scripts/ops/production_readiness_sweep.py --no-external | tail -5
```

The readiness sweep MUST report `0 FAIL`. WARNs may stay (Pi-tier degraded, GCP manual gates, expired confirmations).

Note on the `tests/unit + plugins/claw-sapphire/tests` co-invocation gotcha: pytest can't load both conftest.py files in the same invocation due to a path-mismatch error. ALWAYS run them in two separate invocations.

If the post-merge canonical pytest crosses local midnight while you're working, watch for date-boundary flakes (the dev_pulse one was caught by Claude tonight in #377).

---

## 5. PR template

Each PR body must include:
- Section "What this enables" (acquisition-grade framing — why a buyer cares)
- Section "Safety posture" (env gates, caps, no-secrets-at-rest)
- Section "Local verification" with the six command outputs (or trimmed tails)
- Section "Files changed" with the file list
- Section "Follow-ups not in this PR" — be honest about what you deliberately deferred

End with `🤖 Generated with [Claude Code](https://claude.com/claude-code)` ONLY if Codex's runtime emits that footer; otherwise omit it (don't claim credit you didn't earn).

---

## 6. Merge protocol

When local verification is green and `gh pr view <N>` shows `mergeStateStatus: CLEAN, mergeable: MERGEABLE`:

```bash
git -C ~/Code/Sapphire worktree remove /Users/aribs/Code/_worktrees/sapphire-<branch> --force
gh -R arigatoexpress/Sapphire pr merge <N> --squash --admin --delete-branch
git -C ~/Code/Sapphire pull --quiet
```

If GitHub reports `UNSTABLE` because hosted CI is queued (you forgot `[skip ci]`): **cancel the run** with `gh run cancel <id>` BEFORE retrying the merge. Do NOT skip CI guards by other means.

If a registry-yaml conflict appears between two of your lanes: rebase the second lane on top of the merged first, regenerate the registry append, re-run verification, push.

---

## 7. Closeout deliverable

After the last lane merges, write **one** handoff doc at `docs/handoffs/codex-overnight-megaprompt-2026-04-28-report.md` and commit it directly to main with `[skip ci]`. The doc MUST include:

1. **Final main SHA** + open PR/issue counts.
2. **Per-lane status table**: lane name, PR number, files changed, test delta, key design decisions, caveats.
3. **Verification at handoff**: the six commands' tail output.
4. **Operator-owed actions**: anything the operator needs to do (channel curation in `~/.sapphire/telegram_channels.yaml`, session-file generation for Telethon, LaunchAgent installs, env-var setup, etc.).
5. **Skipped lanes (if any)** with a one-paragraph explanation per skip.
6. **Next-tranche backlog** the operator should review.

Then update `~/.claude/projects/-Users-aribs/memory/MEMORY.md` (one line in the index pointing to a new project memory file at `~/.claude/projects/-Users-aribs/memory/project_2026-04-28_codex_overnight_megaprompt.md`). Memory files live OUTSIDE the git tree, that's fine — they're notes for future sessions.

---

## 8. Posture reminders

- This is acquisition-grade work. A scrappy hack with great tests is better than a polished feature with sparse coverage.
- Honesty over hype. If a lane hits a real blocker, write a 1-paragraph "discovered but not fixed" entry and move to the next lane. Do NOT fake a green build.
- Provenance is non-negotiable. Every artifact gets an envelope.
- The trading critical path is sacred. If you find yourself wanting to modify a CODEOWNERS-gated path "just a little", stop and add it to the closeout's operator-owed list instead.
- Respect the operator's time. Each PR's verification block + the closeout report should let him do a 10-minute morning review and either approve everything or surgically revert one lane.

Now go.
