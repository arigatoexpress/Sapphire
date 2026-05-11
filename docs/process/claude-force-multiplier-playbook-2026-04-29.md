# Claude Force-Multiplier Playbook — 2026-04-29

> **Audience**: future Sapphire operators, future Claude Code sessions, and any acquirer-side CTO
> who asks "why two parallel autonomous agents, and how do you decide which one does what?"
> **Status**: durable. Re-read at the start of any multi-agent push. Update only when a section
> here is contradicted by observed behavior — not by speculation.
> **Companion docs**:
> [`docs/handoffs/codex-overnight-megaprompt-2026-04-28-report.md`](../handoffs/codex-overnight-megaprompt-2026-04-28-report.md),
> [`docs/handoffs/codex-megaprompt-tranche-4-2026-04-29-report.md`](../handoffs/codex-megaprompt-tranche-4-2026-04-29-report.md),
> [`docs/handoffs/claude-night-session-2026-04-28-report.md`](../handoffs/claude-night-session-2026-04-28-report.md),
> [`docs/handoffs/cowork-morning-briefing-2026-04-28.md`](../handoffs/cowork-morning-briefing-2026-04-28.md),
> [`CLAUDE.md`](../../CLAUDE.md).

---

## 1. Executive summary

Sapphire OS runs **two parallel autonomous coding agents**: ChatGPT-Codex and Anthropic Claude.
Both have full repo access, both can land production-grade PRs overnight, and both have proven
they can operate inside the same `[skip ci]` no-spend posture, the same CODEOWNERS gate, and the
same provenance-envelope discipline. The strategic question is not *which is better* — it is
*where is each one uniquely positioned*.

This playbook locks down that answer in three forms of Claude:

1. **Claude Code (agent harness, 1M-context Opus)** — long-context analysis, multi-file
   refactors, sensitive operator-personal work, and anything that benefits from the Anthropic
   skills system (`pptx`, `docx`, `xlsx`, `pdf`, `canvas-design`, `algorithmic-art`,
   `web-artifacts-builder`, `theme-factory`, `brand-guidelines`, `doc-coauthoring`,
   `slack-gif-creator`), MCP integrations (TradingView, context7, Macos, computer-use), and
   hooks-driven automation.
2. **Cowork (Claude Desktop)** — interactive paired sessions with the operator in the loop.
   Witnesses clicks. Drafts texts. Holds the operator accountable to an order. Used today for
   the morning credential-rotation, email-reply, and live-trading-verification routine
   (`docs/handoffs/cowork-morning-briefing-2026-04-28.md`).
3. **Claude API (raw, headless)** — programmatic invocations from inside Sapphire itself: the
   inference-proxy's T4 fallback, the `gemini_ooda` shape extended to Anthropic, the narrative
   thesis engine (PR #408 is currently OpenAI-side-only; Tranche 5 should add an Anthropic
   path), and any future scheduled task that needs a model larger than what the local mesh
   serves.

Codex remains uniquely positioned for **autonomous parallel build lanes** — its overnight
8-lane megaprompts (Tranches 2/3/4) consistently land 8-9 PRs in 4-6 hours, with a tight
GitHub Connector loop that lets it self-cancel queued runs the moment a `[skip ci]` subject
slips. Claude's job is the **harder-to-parallelize work**: the architectural overview that
keeps the diligence packet honest, the security review that runs across 50 files at once, the
operator-personal work that needs Cowork's witness-mode discipline, and the long-context audits
that fit in a 1M window but would blow past Codex's effective working set.

The honest version: **if you only had one agent, Codex would build faster.** What Claude buys
you is *durability and judgment* — the part of the system that survives an acquisition due
diligence pass.

---

## 2. The two-agent stack

### 2.1 What each one shipped this week

The handoff docs from 2026-04-28 are the cleanest A/B test we will ever have on a single
codebase. Both agents worked from the same `main` SHA, the same CLAUDE.md, the same hooks, and
the same operator allowlists.

**Codex side (overnight tranches):**

- *Tranche 1 (Agents A/B/C)*: 12 PRs across pytest collection restoration, repo hygiene,
  BacktestEngine adapter normalization, sweep regen validation, performance-endpoint smoke,
  risk-kernel public-type coverage. Reports:
  [`codex-overnight-agent-A-2026-04-28-report.md`](../handoffs/codex-overnight-agent-A-2026-04-28-report.md),
  [`-B-`](../handoffs/codex-overnight-agent-B-2026-04-28-report.md),
  [`-C-`](../handoffs/codex-overnight-agent-C-2026-04-28-report.md).
- *Tranche 2 megaprompt*: Nemotron Telegram live-context fix + 6 lanes (Telegram channel intel
  reader, `routine_pause` flag enforcement, Vertex `text-embedding-gecko@003` embedder, live
  BigQuery upsert + `VECTOR_SEARCH`, Hyperliquid public feed, sovereign-thesis story / diligence
  UI). PRs #383-#392. Verification at handoff: 4,219 unit + 291 plugin tests passing, registry=42,
  zero readiness FAIL.
- *Tranche 4 closeout*: 9 / 9 lane PRs merged, integration pass via PR #413, 4,899 unit tests
  passing, registry=49. Final SHA `c44519e5`.

**Claude side (night session):**

- 10 PRs (#371-#380), all admin-squash with `[skip ci]`. Notable scope:
  - **PR #372**: vertex/gemini eval harness — new `vertex_eval` plugin tool, `lib/eval/`
    surface, +34 tests.
  - **PR #373**: telegram operator-console hardening — *124 telegram tests*, new
    `_telegram_safety` module, 7 new bot commands.
  - **PR #374**: threat-intel + customer-dossier dashboards — 88 tests, 2 new dashboard pages,
    `lib/security/pii_redactor.py`.
  - **PR #375**: pytest-xdist parallelization — +144 tests, 5 new isolated lib suites.
  - **PR #376**: BQ vector retrieval layer — +53 tests, new `intel_search` plugin tool.
  - **PR #377**: clock-pinning fix for `dev_pulse` date-flake (the canonical fix template the
    Tranche 3 megaprompt later pointed Codex at).
  - **PR #378**: orjson + python-dotenv security bumps.
  - **PR #379**: post-Wave-4 cleanup — CODEOWNERS gate on telegram safety surface + README
    counts re-aligned to 4,045+.
- Architectural overview refresh (PR #381).
- Tranche 3 fill-in work documented in
  [`claude-night-session-2026-04-28-report.md`](../handoffs/claude-night-session-2026-04-28-report.md).

### 2.2 What the comparison reveals

Three patterns are visible:

1. **Codex is a parallelization engine.** Its tranche-megaprompts dispatch 8 lanes
   concurrently in worktrees, fence each one to a tight allowlist, and self-merge with admin
   squash + `[skip ci]`. The Tranche 2 closeout report cites the canonical embarrassment: PR
   #388's squash subject dropped `[skip ci]` because `gh pr merge --squash` defaulted to the PR
   title rather than the branch commit subjects. Codex *immediately* checked queued runs, found
   none, and documented the mistake. The Tranche 3 megaprompt then made `-t '<title> [skip ci]'`
   a non-negotiable rule. **This kind of self-correcting GitHub-side discipline is Codex's
   strongest suit.**
2. **Claude shipped *more* tests per PR.** PR #373 alone added 124 telegram tests; PR #374 added
   88 dashboard tests; PR #375 added 144 isolated lib tests. That density — security-relevant
   tests on the operator console, PII redaction tests on the threat-intel dashboard — is the
   work that benefits most from the long-context window: Claude was reading the entire affected
   surface before generating new coverage, not just the file under edit.
3. **The truly architectural work was Claude's.** PR #381 (architectural overview refresh) is
   not a feature — it is a *coherence pass* across the whole repo, and it is the kind of edit
   that would be very expensive to do as a tranche lane because it touches the whole module
   map. Similarly, the `_telegram_safety` module in PR #373 is a *shared safety surface* that
   has to land before the 7 new bot commands; Codex tranche-style worktree-per-lane parallelism
   would have created merge conflicts on this kind of work.

### 2.3 Where Claude is honestly worse

This is acquisition-grade thinking, so be honest:

- **Cold starts on a fresh worktree are slower in Claude Code than in Codex.** Codex's GitHub
  Connector means it can `gh pr create` and `gh pr merge` faster than Claude Code's Bash-tool
  loop. Over an 8-lane night, that compounds.
- **Multi-PR waves with hosted-CI gating are Codex's home turf.** When the merge gate is "wait
  for CI green" rather than "local verify green + admin merge", Codex's shorter feedback loop
  wins.
- **Plain code-generation throughput, holding context-quality constant, is roughly comparable
  on hot paths but Codex tends to be cheaper per token.** When a task is clearly a "write 600
  LOC of Python following this template", Codex is the right tool.

The split this playbook recommends respects all three.

---

## 3. When to reach for Claude Code

### 3.1 Long-context analysis (the 1M Opus context)

Use Claude Code when the task **must read more than ~200K tokens** to be done correctly. Concrete
Sapphire-side examples:

- **Architectural overview refresh** (the PR #381 pattern). Reading every service's README, the
  `lib/` module map, the `services/` boundaries, and the plugin registry to produce a coherent
  diagram is exactly the kind of work that scales with context.
- **Acquirer diligence packet audit.** When `docs/diligence/00`-`09` is the surface, and the
  question is "does this map cleanly to what the dashboard observability page actually shows?",
  Claude can hold both views in working memory and surface drift.
- **CLAUDE.md hygiene passes.** The `claude-md-improver` skill is purpose-built for this — see
  §7 below.
- **Pre-merge security review of a large branch.** The `security-review` skill (already in
  `~/.claude/skills/`) and `code-review` slash command both benefit when the diff is bigger than
  a single file.

### 3.2 Multi-file refactors that don't parallelize

If the work is "rename one type across 47 files", Codex tranche-style parallelism does not help
— there is no clean way to fence each file into its own lane without merge-conflict storms.
Claude Code's single-coherent-edit-stream is structurally better here. The PR #373
`_telegram_safety` extraction is a small example; a future "extract `lib/correlator/sources.py`
adapter base into a shared abstract class" is the larger one.

### 3.3 Sensitive operator-personal work

CLAUDE.md's hooks already block edits to `*secrets*`, `*.env`, `*trading_signals*`, and
`*migrated_customers*`, but the harder filter is *judgment*: anything that involves reading the
operator's actual messages, looking at real PII, or making a recommendation about a
counterparty (Etai, Mark, Celeste in the cowork briefing) belongs in Claude — not because Codex
*can't* do it, but because Claude's overall posture (the user's CLAUDE.md global instructions,
the "Mac is commander" principle, the "perfection over speed" preference) is more conservative.

### 3.4 The Anthropic skills system

Claude Code's most underused force-multiplier is the **skills layer**. The skills installed at
the user level in `~/.claude/skills/` plus the Anthropic-bundled skills are a packaged-expertise
toolkit. The ones Sapphire benefits from most:

| Skill | Sapphire-side use case |
|---|---|
| `pptx` | Acquirer pitch deck refresh ahead of any second meeting. The Palantir packet plus the diligence packet should be one coherent deck; manually-built decks drift. |
| `docx` | THO document templates (63 PDF/XFA templates today are filled by the Document Center, but operator-facing docs — proposals, scope memos to Etai — should ride the docx skill). |
| `xlsx` | Backtest leaderboard exports for buyer-side analysts who want raw data, not screenshots. Wires cleanly into `lib.analytics.backtest_results.summary()`. |
| `pdf` | Buyer-safe redaction profile (PR #419) outputs static demos; pdf skill could ship the next-rev "diligence packet PDF" with provenance envelope as a sidecar. |
| `canvas-design` | One-off acquirer-microsite hero images, `docs/competitive/landscape-2026-04-28.md` cover plates. |
| `algorithmic-art` | Dashboard easter eggs, content-engine cover art. Lower priority but the work-stream exists. |
| `web-artifacts-builder` | Faster rev cycles on the diligence dashboard pages without bouncing through the Flask render. |
| `theme-factory` | Brand-consistent buyer-microsite restyling. Ari's brand spec is in `docs/brand/`. |
| `brand-guidelines` | Confirms acquirer-microsite typography and color system match. |
| `doc-coauthoring` | This playbook itself. Operator-led memo work where Claude proposes an outline and the operator iterates section by section. |
| `slack-gif-creator` | Telegram alert-channel celebratory GIFs — a small but real morale lever. |
| `consolidate-memory` | Periodic memory hygiene on `~/.claude/projects/-Users-aribs/memory/MEMORY.md` (already 50+ entries, growing). |

**The rule of thumb**: if the deliverable's *file format* is something Codex would have to
hand-roll (a real .pptx, a real .xlsx, a real branded PDF), Claude Code with the right skill is
the correct tool. Codex's skill-equivalent ecosystem is thinner.

### 3.5 MCP integrations

Sapphire already runs three MCPs (per the user-level memory entry):

- **tradingview-mcp** (78 tools, CDP-driven via `tv_*` tool prefix) — chart capture, Pine
  compile/validate, alerts, screenshots.
- **context7** — live documentation lookup for any library; mandatory before answering "how
  does this OpenBB endpoint work".
- **scheduled-tasks** / **mcp-registry** / others.

Claude Code's MCP loader is deeper than Codex's GitHub Connector — when the task involves *live
chart inspection*, *macOS GUI control*, *browser automation through Chrome*, or *the
TradingView desktop app*, Claude Code is the only viable choice. The TradingView MCP alone
makes Pine-side strategy authoring (`pine/standalone/*.pine`) far more productive in Claude than
in Codex.

### 3.6 Hooks-driven automation

The PostToolUse hook in `.claude/settings.json` already auto-runs `ruff format --fix` + the
matching `tests/test_<basename>.py` after every Edit/Write. The PreToolUse hook blocks edits
to secrets / trading signals / `.env` / migrated customers. This is **Claude Code's harness, not
Codex's** — extending it (see §8) is a Claude-Code-side investment that pays back across both
agents only insofar as Codex respects the same conventions.

---

## 4. When to reach for Cowork (Claude Desktop)

Cowork's job is **paired sessions with the operator in the loop, step by step**. Read the full
[cowork-morning-briefing-2026-04-28.md](../handoffs/cowork-morning-briefing-2026-04-28.md) for
the canonical shape.

The working agreement encoded there is the template:

> "You (Ari) own the actual clicks and approvals. Cowork's job is to: (1) walk you through each
> item below in order, (2) draft any email / message I name, (3) after each step, ask you to
> confirm 'done + here's the evidence', (4) never proceed past an item without explicit 'done'
> or 'skip', (5) never touch any console, secret, or external service on your behalf. You click;
> Cowork witnesses."

**When to use Cowork specifically:**

- **Credential rotations** (MOONSHOT_API_KEY, KIMI_CLAW_BOT_TOKEN per the runbook). The
  operator must do the actual key generation in the provider console; Cowork drafts the
  surrounding shell commands, witnesses each step, and logs the rotation timestamp + last-4 of
  the old key for audit trail.
- **Email replies that involve real counterparties** (Etai Zilberman, Mark Willcott, Celeste).
  Drafts go through Cowork; the operator sends. Cowork keeps the running notes file at
  `~/Documents/Cowork/morning-briefing-<date>.md`.
- **Live-trading verification.** When the $5 BTC limit-buy filled at 04:06 UTC on 2026-04-28,
  the operator-owned step was opening the Robinhood app, confirming the position, and recording
  attribution (manual button-press vs confirmation-token gate). That is *exactly* the kind of
  work where the harness has no business autonomously touching the broker — and Cowork's
  witness-mode is the right discipline.
- **Operator-supervised dependency bumps** to the trading critical path. The
  `services/alpha/aiohttp` 3.11.11 → 3.13.4+ bump in cowork-morning section 9 is the canonical
  shape: the operator watches the alpha logs while the bump installs, restarts the
  signal-logger LaunchAgent, smokes `/health`, and only commits after a 30-minute green
  window.
- **Browser logins, console clicks, and CMS access.** The texashomeoutlet.com `MH-Checklist.pdf`
  resolution in section 4 of the cowork briefing is the shape — Cowork doesn't have admin access
  on the CMS, but it can draft the message asking who does.

**When *not* to use Cowork:**

- Anything that fits cleanly in a `[skip ci]` PR — that's Claude Code or Codex.
- Anything that's already automated by a scheduled task or LaunchAgent.
- Anything Codex is currently working on. The cowork briefing's "What's deliberately NOT in
  this prompt" section is correct: don't shadow Codex's lanes.

**Cowork's scheduled-tasks layer**: the cowork briefing's section 1 documents 5 cloud-side
tasks (`morning-briefing`, `meeting-prep-tomorrow`, `end-of-day-log`,
`weekly-downloads-cleanup`, `tho-weekly-service-rollup`). The decision tree there — keep,
mount-folder, or delete — is operator-owned and the kind of decision Claude Code should *not*
make autonomously. Once mounted, those tasks become a recurring Cowork surface that the
operator can rely on for items that don't fit either Sapphire scheduled tasks or cloud
routines.

---

## 5. When to reach for Codex

Reading the Codex tranche megaprompts back-to-back makes the answer obvious:

- **Autonomous parallel build lanes.** Tranche 4 dispatched 8 lanes concurrently in worktrees
  and landed all 8 plus an integration pass in 4-6 hours overnight. That throughput is what
  Codex is *for*.
- **Tight GitHub Connector integration.** Codex's `gh pr create` → `gh pr merge --squash --admin
  --delete-branch -t "<title> [skip ci]"` loop is faster than Claude Code's equivalent. When the
  merge gate is admin-squash with `[skip ci]`, Codex eats fewer round-trips.
- **Large multi-PR waves where GitHub-side review automation matters.** The Tranche 4
  squash-merge subject audit (every PR ending in `[skip ci]` after merge) is the kind of
  GitHub-API-loop verification Codex does well.
- **Worktree-per-lane fencing.** The pattern of
  `/Users/aribs/Code/_worktrees/sapphire-<branch>` per lane, with hard allowlist on touchable
  paths, is the only safe way to run 8 agents concurrently in the same monorepo. Codex was the
  first to operationalize this.
- **High-volume routine maintenance.** Agent A's pytest-collection restoration + cache-fail
  triage (PRs #360-#369) is rote-but-essential work; Codex burns through it.

The most expensive Codex mistake observed (PR #388's missing `[skip ci]` due to the `gh pr
merge` default-subject behavior) was caught and fixed by *Codex itself* in the same session.
That self-correction is part of why Codex earns broad autonomy on overnight tranches.

---

## 6. Eight concrete Sapphire-side deployment recommendations

For each: what to build, which Claude form, why Claude > Codex.

### 6.1 Make the diligence packet a recurring Claude Code job

**What to build**: a scheduled task at `~/.claude/scheduled-tasks/diligence-packet-coherence/`
that, weekly, reads `docs/diligence/00`-`09`, the dashboard observability page output, and the
acquirer-microsite, and produces a coherence-drift report. Open an issue if drift exceeds a
threshold.
**Form**: Claude Code (long-context), routed via the cloud routine system (per CLAUDE.md
"Cloud Routines" section, 8 already running).
**Why Claude > Codex**: this is a coherence pass across ~50 files; Codex tranche-lanes
fragment exactly the kind of cross-cutting view this requires.

### 6.2 Wire the Anthropic API into the inference proxy as a real T4 fallback

**What to build**: today the proxy's T4 is Kimi Cloud (Moonshot). Add an Anthropic path with the
`claude-api` skill's prompt-caching pattern baked in. Gate behind `ANTHROPIC_API_LIVE=1` to
match the existing dry-run-default convention.
**Form**: Claude Code (one-time build), then raw API at runtime.
**Why Claude > Codex**: the `claude-api` skill is purpose-built for this and includes prompt
caching guidance; Codex doesn't have an equivalent.

### 6.3 Replace `vertex_eval`-only paths with multi-provider eval

**What to build**: extend `lib/eval/` (PR #372) so the eval harness can run side-by-side
comparisons across `gpt-*`, `claude-*`, `gemini-*`, and the local Ollama tiers. Surface the
result on the `/observability` page next to the existing single-provider surface.
**Form**: Claude Code build, runs against the API at evaluation time.
**Why Claude > Codex**: cross-provider eval is exactly the comparative-judgment task Anthropic
trains for. Codex has a structural conflict-of-interest here.

### 6.4 The Cowork morning-briefing routine should auto-generate from Sapphire signals

**What to build**: a Sapphire-side scheduled task that, by 7:30 AM, writes the morning's
operator-owed actions into a file that Cowork reads at 8:00 AM. The Tranche 4 readiness sweep
already produces structured WARNs (4 expired pending confirmations, GCP gate, etc.); these
should auto-populate the briefing.
**Form**: Sapphire scheduled task writing the file; Cowork (Claude Desktop) consumes it.
**Why Claude > Codex**: Cowork is the consumer, and its briefing format is operator-shaped
prose (not GitHub-issue prose). Claude is better at producing the operator-shaped prose.

### 6.5 Acquirer pitch deck regen after each tranche closeout

**What to build**: a Claude Code skill that reads the latest tranche-closeout report
(`docs/handoffs/codex-megaprompt-tranche-*-report.md`) and updates the pitch deck
(`docs/products/<acquirer>-deck.pptx`) with the new test counts, registry size, and headline
shipped surfaces.
**Form**: Claude Code with the `pptx` skill.
**Why Claude > Codex**: file format is .pptx; that's the `pptx` skill's home turf.

### 6.6 PII redaction sweep across handoff docs

**What to build**: extend `lib/security/pii_redactor.py` (PR #374) with a Claude-Code-driven
sweep that runs nightly across all `docs/handoffs/` files, flags any new PII, and either
redacts in place (if the sweep is allowlisted) or opens an issue.
**Form**: Claude Code, with the existing `security-review` skill.
**Why Claude > Codex**: the redaction decision is a *judgment call*, not a regex match. The
PII redactor's CODEOWNERS gate exists for exactly this reason.

### 6.7 Live-trading-soak weekly deep-dive

**What to build**: a Claude Code session that, weekly, reads the live $5 trade ledger
(`data/live_portfolio.jsonl` once option B from cowork section 8 ships), the soak window's
Sortino/Calmar trajectory, and the paper portfolio's correlation, and writes a
`docs/products/live-trading-soak-week-N.md` memo. The 14-day Sortino-soak window is already
ticking; the next ramp-rung gate should be evidenced.
**Form**: Claude Code (long-context), output is a Markdown memo with provenance envelope.
**Why Claude > Codex**: this is decision-support writing, not feature work.

### 6.8 Claude Code as the "shipped surface explainer"

**What to build**: a `/explain-shipped` slash command (skill) that takes a PR number, reads the
PR diff + the reports referencing it, and produces an operator-friendly one-page summary. The
surface is documented enough now (50+ PRs over the last 72 hours) that the operator's mental
model needs help.
**Form**: Claude Code skill (user-invocable), reads from gh + git.
**Why Claude > Codex**: explanatory writing for an operator audience is exactly Anthropic's
trained-for shape.

---

## 7. Subagent + skill catalog

The skills that ship with Claude Code today, ranked by Sapphire-side relevance:

### 7.1 First-class skills

| Skill | Trigger | Sapphire use |
|---|---|---|
| `claude-md-management:claude-md-improver` | "audit/improve CLAUDE.md" | Quarterly hygiene pass on root CLAUDE.md + every module SKILL.md (already 50+ across plugins/services). |
| `claude-md-management:revise-claude-md` | end of session | Session-end memory updates so the next Claude session inherits learnings. |
| `code-review:code-review` | "review this PR" | Pre-merge review of any PR landed by Codex overnight. The split: Codex builds; Claude reviews before admin-merge. |
| `coderabbit:review` / `autofix` | CodeRabbit comment processing | Companion to CodeRabbit's automated review; pull comments, fix interactively. |
| `security-review` | pre-merge / branch | Shipped in `~/.claude/skills/security-reviewer.md`. Run before any merge that touches `lib/security/`, `lib/core/kill_switch.py`, `services/webhook/`, contracts, or the trading critical path. |
| `init` | new repo | Initialize CLAUDE.md for satellite repos (cyber-threat-bot, regional-intel-workbench, etc.) when absorbing them. |
| `simplify` | post-implementation | After a Codex-tranche lane lands, run `/simplify` against the touched paths. |
| `fewer-permission-prompts` | as friction grows | Periodic allowlist tuning — read `Bash(curl http://localhost:*)` patterns from transcripts and add them to `.claude/settings.json`. |

### 7.2 Output-format skills (the pptx/docx/xlsx/pdf cohort)

Use only when the deliverable's file format requires it:

- `anthropic-skills:pptx` — acquirer decks.
- `anthropic-skills:docx` — operator-facing memos and template-driven docs (THO scope memos to
  Etai, etc.).
- `anthropic-skills:xlsx` — backtest/leaderboard exports.
- `anthropic-skills:pdf` — diligence packet snapshot.
- `anthropic-skills:canvas-design` / `algorithmic-art` — visual artifacts.
- `anthropic-skills:web-artifacts-builder` — claude.ai HTML artifacts for buyer-side
  walkthroughs.
- `anthropic-skills:theme-factory` / `brand-guidelines` — visual consistency on acquirer
  surfaces.
- `anthropic-skills:doc-coauthoring` — this playbook is the canonical example.
- `anthropic-skills:slack-gif-creator` — Telegram alert-channel morale.
- `anthropic-skills:internal-comms` — operator-side updates (status reports, leadership memos
  to investors / family).
- `anthropic-skills:mcp-builder` — when extending the existing MCP roster (see §9).
- `anthropic-skills:consolidate-memory` — quarterly hygiene on the user-level memory file at
  `~/.claude/projects/-Users-aribs/memory/MEMORY.md`.
- `anthropic-skills:setup-cowork` — re-initiated when Cowork's mount-folder decision is revisited
  (cowork-morning section 1).

### 7.3 Workflow skills

- `claude-api` — building any new Claude-API consumer (recommendation 6.2).
- `agent-sdk-dev:new-sdk-app` — new SDK harnesses, e.g., a future hermes-like agent on Anthropic
  primitives.
- `loop` — recurring polling tasks, e.g., "every 5 minutes, check if the live $5 BTC position has
  moved more than 1%".
- `schedule` — scheduling Claude-side cloud routines (the 8 already running per CLAUDE.md
  "Cloud Routines"). When Sapphire ships a new operator-grade recurring need, this is the
  authorization tool.
- `update-config` / `keybindings-help` — Claude Code harness configuration hygiene.

### 7.4 Subagents

The `Agent` tool dispatches subagents that run with their own context window. Sapphire-side
patterns:

- **Reviewer subagent** that runs `security-review` against a specific PR while the main agent
  continues building.
- **Test-writer subagent** that mirrors the existing `tho-test-writer` scheduled task pattern
  but for arbitrary new modules — fed a module path, returns a test file.
- **Doc-coherence subagent** for the diligence-packet recommendation (6.1).

For autonomous multi-task fan-out, see the user-level memory entry on "Autonomous dispatch
when authorized" — broad autonomy means default to parallel `Agent` tasks + recurring routines
+ admin-squash-merge.

---

## 8. Hooks recommendations

The current `~/.claude/settings.json` (project-level: `<repo>/.claude/settings.json`) has:

- **PreToolUse Edit|Write**: blocks edits matching `*trading_signals*`, `*migrated_customers*`,
  `*.env`, `*secrets*`, `*secret_*`, `*/keys.txt`, `*sapphire-secrets*`.
- **PostToolUse Edit|Write**: runs `ruff format --quiet` + `ruff check --fix --quiet` on the
  touched `.py`, then runs `pytest tests/test_<basename>.py` if a matching test file exists.

This is good. The recommended additions:

### 8.1 PreToolUse: warn before editing the trading critical path

Add a `Bash` matcher that warns (exit code 0 with stderr message) before any edit to:
`services/alpha/`, `lib/portfolio/robinhood.py`, `lib/trading/`,
`lib/analytics/risk_engine.py`, `lib/analytics/strategies.py`, `lib/core/kill_switch.py`,
`lib/core/confirmation_firewall.py`, `services/webhook/`, `contracts/`. CODEOWNERS already
gates these on review; the hook gates them on operator-attention. Distinguish from secrets-block
(exit 2) — this should *warn*, not *block*, so the operator sees a clear notice but Claude can
proceed if explicitly authorized.

### 8.2 PostToolUse: provenance envelope check on docs/

Add a hook that, after any Edit|Write to a path matching `docs/{products,security,competitive,
diligence,process}/*.md`, checks whether a `<file>.envelope.json` exists. If not, emit a
warning. This enforces the Tranche-3 §1.7 rule ("provenance envelopes on all generated
artifacts") at the harness level, not just at code-review time.

### 8.3 Stop hook: post-session memory update

Per the user-level memory file (`~/.claude/projects/-Users-aribs/memory/MEMORY.md`), the
current pattern is manual ("revise-claude-md" skill at session end). Promote this to a Stop
hook that runs `claude-md-management:revise-claude-md` if and only if the session touched ≥ 3
files in `lib/` or `services/`. This makes session-end memory updates default, not opt-in.

### 8.4 PreToolUse on `gh pr merge`: enforce `[skip ci]` subject

The Tranche 2 #388 incident is the canonical motivation. A `Bash` PreToolUse hook can match
`gh pr merge` invocations and require `-t '<subject> [skip ci]'` (exit 2 if missing). This
is harness-side enforcement of a discipline currently enforced only at the megaprompt level.

### 8.5 PostToolUse on test files: re-run the parent module's tests

Today, edits to `lib/foo.py` re-run `tests/test_foo.py`. Edits to `tests/test_foo.py` should
*also* re-run `tests/test_foo.py` (currently they don't, because the basename match doesn't fire
on test files). Add a sibling matcher.

### 8.6 PostToolUse: append session summary on task completion

Add a hook on the `Task` tool's completion that appends a one-line summary to a session-log
file at `~/.claude/projects/-Users-aribs/sessions/<session-id>.md`. Useful for the post-session
revise-claude-md run.

### 8.7 PreToolUse on `Bash` for scheduled-task edits

Edits under `~/.claude/scheduled-tasks/` should trigger a confirmation prompt, since they
change scheduled-task behavior with no PR review. Block by default; require explicit
acknowledgment.

---

## 9. MCP recommendations

Beyond the existing roster (tradingview-mcp 78 tools, context7, plus the MCPs surfaced by the
session — Macos, Desktop_Commander, Chrome, Read_and_Send_iMessages, Read_and_Write_Apple_Notes,
Asana, Asana-via-plugin, Anthropic Connectors, Google Drive, Google Calendar, Gmail, Asana,
Hugging Face Hub, Figma, Noteplan, scheduled-tasks, claude-context, computer-use,
agent-unified-terminal, Claude Preview, Claude in Chrome, Control Chrome):

### 9.1 GitHub MCP (if not already wired)

Sapphire's GitHub footprint is large enough that a dedicated GitHub MCP would shorten the
distance between "I want to know the state of PR #393" and the answer. Today this routes
through `gh` CLI in Bash, which works but is verbose. A native MCP would accelerate the
PR-comment-processing loop in particular.

### 9.2 Postgres / SQLite MCP for the Sapphire data lake

`services/pipeline/` already syncs events to BigQuery; for *local* analysis, a SQLite-MCP over
the `data/events/bus.jsonl` fallback path or a session-scoped Postgres mirror would let Claude
do ad-hoc analytical queries without writing one-off Python.

### 9.3 Foundry / Palantir MCP shim

`lib/foundry/sync.py` and the broader Palantir Foundry strategy
(`docs/foundry-strategy-2026-04-19.md`, the live partnership pitch) are central to the
acquirer thesis. A Foundry-side MCP — even a thin one that exposes the existing
`IntelVectorRecord` ontology object — would let Claude do diligence-packet coherence checks
against live Foundry state, not just the local snapshots.

### 9.4 Telegram MCP

As of 2026-05-11 the Telegram surface is owned by `services/pm_bot` in webhook
mode; a Telegram MCP (read-only — strictly no send) would let Claude reason about message
streams the way `tradingview-mcp` lets it reason about charts. Pair carefully with the Tranche 2
Telegram intel reader's quality filter.

### 9.5 Sentry / observability MCP

If Sapphire ever lights up Sentry on the dashboard (currently it's local logging only), a
Sentry MCP would close the loop on "the dashboard is throwing 502s" → "open the relevant
issues, look at the stack trace, propose a fix" without leaving Claude.

### 9.6 OpenBB MCP (or a thin wrapper)

OpenBB-API is currently consumed via REST (`http://localhost:6900`); a native MCP wrapper that
encodes OpenBB's 32-provider matrix as MCP tools would shorten "ask OpenBB about AAPL" from
"write a curl + jq" to "call the tool".

The general principle: **add MCPs for every long-running internal service that Claude
currently reaches via Bash + curl.** Each one is a force-multiplier the next time the question
is "what does the system actually look like right now".

---

## 10. Anti-patterns

What NOT to use Claude for. Be specific.

### 10.1 Don't use Claude Code for high-volume rote PR mills

If the work is "open 30 PRs each touching 1-3 files following the same template", Codex's
parallel-lane shape is structurally faster. Examples:

- Per-module dependency bumps.
- Mass renames driven by a regex.
- One-test-per-untested-module test-coverage drives.

Codex's Tranche 1 Agent A pytest-collection restoration (PRs #360-#369) is the canonical
example: 7 PRs, all rote, under 6 hours.

### 10.2 Don't use Cowork for autonomous overnight work

Cowork is *paired*. Its scheduled-tasks layer (cowork-morning section 1) can run in the cloud,
but the briefing format itself assumes the operator is awake and clicking. Don't try to use
Cowork as a third autonomous agent — it's a fundamentally different shape.

### 10.3 Don't use raw Claude API for tasks the harness already handles

The inference-proxy's T4 fallback today is Kimi Cloud, sensitivity-gated. Adding an Anthropic
T4 (recommendation 6.2) is correct, but routing the *whole* dispatch through raw API rather
than through the proxy's tier system would lose the sensitivity gate, the budget tracker, the
dry-run-default discipline, and the cost analytics. The harness exists for a reason.

### 10.4 Don't ask Claude to do GitHub-side merge automation in real time

Codex's `gh pr merge --squash --admin --delete-branch -t "<title> [skip ci]"` loop is faster
than Claude Code's equivalent. When the goal is "merge this PR right now", let Codex do it.

### 10.5 Don't bypass CODEOWNERS via Claude

The trading critical path's CODEOWNERS gate
(`.github/CODEOWNERS`) is the operator's sleep insurance. Claude should *not* attempt to merge a
PR that touches `services/alpha/`, `lib/portfolio/`, `lib/trading/`, etc., even with admin
rights. The Tranche 3 §1.2 rule is explicit and must be respected.

### 10.6 Don't pile new top-level dependencies into Claude-Code-led PRs

Tranche 3 §1.9 ("no new top-level dependencies unless the lane explicitly authorizes them")
applies symmetrically. Claude has a slightly higher tendency to reach for new libraries; resist.

### 10.7 Don't use Claude for trivial config edits the harness already automates

If the answer is "edit one line in pyproject.toml", the PostToolUse ruff hook already handles
formatting, the test hook handles verification, and any Bash-tool agent can do it in 30
seconds. Don't dispatch a full Claude session for one line.

### 10.8 Don't use Claude API tier-1 for sensitivity-gated paths

If the input contains anything that the inference-proxy's regex sensitivity gate would block
from T4 (api_key, password, jwt, SSN, CC), it must not reach Anthropic API either. The same
gate must apply.

### 10.9 Don't generate provenance-envelope-required artifacts without provenance

The Tranche 3 §1.7 rule ("provenance envelopes on all generated artifacts") applies to every
deliverable from every agent. The hook in §8.2 will enforce this; until then, every Claude
Code session that touches `docs/{products,security,competitive,diligence,process}/` must
produce the sidecar.

### 10.10 Don't shadow Codex's active lanes

The cowork briefing's "What's deliberately NOT in this prompt" section is the canonical
phrasing. If Codex is currently working on a tranche lane, do not let Claude touch the same
files. The worktree-per-lane fencing protects against this on the Codex side; the operator's
discipline protects against it on the Claude side.

---

## 11. Operator decision tree

When faced with task X, which agent?

| Signal | Choose |
|---|---|
| Multi-file refactor, one coherent edit stream | Claude Code |
| 8+ independent build lanes, overnight | Codex |
| Architectural diagram refresh / coherence pass | Claude Code |
| Mass dependency bumps following a template | Codex |
| Cross-provider model eval | Claude Code |
| GitHub PR merge wave with hosted CI | Codex |
| Output is .pptx, .xlsx, .docx, .pdf | Claude Code (skill-driven) |
| Output is Python module + tests (rote) | Codex |
| Output is operator memo / decision doc | Claude Code (`doc-coauthoring`) |
| Real-time pair session with operator clicks | Cowork |
| Credential rotation | Cowork |
| Email reply to real counterparty | Cowork |
| Live-trade verification | Cowork |
| Trading critical path (services/alpha, lib/portfolio, lib/trading, kill_switch, contracts) | Cowork (operator must witness); never autonomous |
| TradingView chart inspection / Pine compile | Claude Code (tradingview-mcp) |
| macOS GUI control / Chrome automation | Claude Code (computer-use, Chrome MCPs) |
| Anything sensitive or PII-touching | Claude Code or Cowork; not Codex |
| Long-context analysis (>200K tokens) | Claude Code (1M Opus) |
| Inference-proxy T4 cloud fallback (runtime) | Claude API (raw) |
| Diligence packet update | Claude Code |
| 30-minute live-soak window watch | Cowork |
| Ad-hoc test write for a single function | Either; default Claude Code |
| Test coverage drive across 50 modules | Codex |
| Pre-merge security review | Claude Code (`security-review`) |
| Post-merge "what did this PR actually do" explainer | Claude Code |

ASCII variant for the operator's wallet card:

```
                     +-----------------------------+
                     |  Task arrives at desk.      |
                     +--------------+--------------+
                                    |
              +---------------------+----------------------+
              |                     |                      |
              v                     v                      v
   Operator must click          Many parallel        Coherence / docs /
   or witness?                  build lanes?         long context / skills?
              |                     |                      |
              v                     v                      v
          COWORK                  CODEX               CLAUDE CODE

                       Sensitive path?  -> Cowork (or Claude Code, never Codex alone)
                       Trading critical -> Cowork; CODEOWNERS-gated
                       Output format    -> Claude Code with the matching skill
```

---

## 12. Closing posture

Sapphire's two-agent stack is durable because each agent does what it is structurally best at.
Codex compresses build velocity. Claude compresses *judgment*. Cowork compresses *operator
attention*. The Anthropic API compresses *runtime intelligence* the local mesh can't deliver.

The acquirer-side question — "why two agents?" — has a one-line answer: **because the four
shapes of work do not overlap, and any single agent buys you only one shape of speed.**

The next time this playbook needs a refresh:

1. Re-read the latest tranche-closeout reports under `docs/handoffs/`.
2. Look for cases where the agent that *did* the work was, in retrospect, the wrong choice.
3. Update the decision tree (§11) accordingly.
4. Bump the date in the filename. Don't overwrite this one — it's part of the durable record.

Memory entry to write at session end (per `claude-md-management:revise-claude-md`):

> 2026-04-29 — Authored Claude force-multiplier playbook at
> `docs/process/claude-force-multiplier-playbook-2026-04-29.md`. Codifies the
> Codex/Claude-Code/Cowork/raw-API split, 8 deployment recommendations, hooks/MCP roster, and an
> operator decision tree. Re-read at the start of any multi-agent push.
