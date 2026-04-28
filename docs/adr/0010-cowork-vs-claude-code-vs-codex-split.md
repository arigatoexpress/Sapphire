# ADR 0010 — Cowork vs Claude Code vs Codex agent split

- **Status**: accepted
- **Date**: 2026-04-29
- **Authors**: Sapphire ops
- **Related**: ADR 0001, ADR 0002, ADR 0003

## Context

Sapphire runs three distinct agent surfaces concurrently:

1. **Claude Code** (Anthropic, 1M-context Opus) in agent harness mode.
2. **ChatGPT Codex** in autonomous parallel-tranche mode.
3. **Cowork** (Claude Desktop) for paired operator-in-the-loop sessions.

Both Codex and Claude Code have shipped overnight tranches. Cowork
runs the operator's morning routine. Without a clear split, the three
tools step on each other:

- Codex and Claude Code editing canonical concurrently produces merge
  conflicts (mitigated by ADR 0002 worktree-per-lane).
- Cowork witnessing operator clicks while Claude Code is also
  attempting to drive the same surface causes UX confusion.
- Operator ambiguity over "who should do this task" wastes time.

The 2026-04-29 force-multiplier playbook
(`docs/process/claude-force-multiplier-playbook-2026-04-29.md`)
is the durable reference. This ADR is the one-page summary of the
decisions in that playbook.

## Decision

The three agents are fenced by **task shape**, not by raw capability:

### Codex — autonomous parallel build lanes

- Best at: 8-lane overnight megaprompts, repetitive 600-LOC-per-file
  generation, GitHub Connector-driven self-merge cycles, hosted-CI
  gating.
- Default for: Tranche-style multi-lane builds where each lane is
  scoped to a clean worktree and produces one PR.
- Discipline: `[skip ci]` subjects, `vars.SAPPHIRE_RUNNER` no-spend
  gate (ADR 0001), worktree-per-lane (ADR 0002), admin-squash with
  explicit `-t '<title> [skip ci]'`.

### Claude Code — long-context analysis + multi-file refactors

- Best at: tasks needing > 200K tokens of context, architectural
  refreshes, security reviews of large branches, CLAUDE.md hygiene
  passes, MCP-driven work (TradingView, computer-use, context7),
  Anthropic skills system (`pptx`, `docx`, `xlsx`, `pdf`, `canvas-design`,
  `algorithmic-art`, `web-artifacts-builder`, `theme-factory`,
  `brand-guidelines`, `doc-coauthoring`, `slack-gif-creator`,
  `consolidate-memory`).
- Default for: ADRs, runbooks, diligence packets, SLO definitions,
  pitch decks, multi-file refactors that don't parallelize.
- Discipline: same `[skip ci]` + worktree pattern; PostToolUse hook
  in `.claude/settings.json` runs `ruff format --fix` + matching
  pytest after every Edit/Write.

### Cowork — paired operator-in-the-loop sessions

- Best at: credential rotations, email replies to real counterparties,
  live-trading verification, browser logins, console clicks, CMS access
  the operator owns.
- Default for: anything where the operator's hands must be on the
  keyboard for compliance, audit, or counterparty-trust reasons.
- Discipline: witness mode — Cowork drafts, operator clicks, never
  the reverse. Notes file at `~/Documents/Cowork/morning-briefing-<date>.md`.

### Cross-cutting rules

- **CODEOWNERS-gated paths** (ADR 0003) are operator-driven regardless
  of which agent drafted the PR.
- **Trading critical path** stays operator-only for execution; agents
  may draft analysis PRs in `lib/analytics/` only outside the gated
  paths.
- **Satellite repos** (Project-Go-Forward, regional-intel-workbench,
  cyber-threat-bot, Cointracker, hermes-agent, claw-code,
  tradingview-mcp-v2) follow per-repo `AGENTS.md` policy. THO is
  draft-PR-only because it has 1,963 real customers in Firestore.

## Consequences

- **Positive**:
  - Clear default for any task shape. Operator can route work
    without re-deciding the split each time.
  - Prevents the three agents from stepping on each other.
  - Captures honest tradeoffs (Codex is faster on parallel builds;
    Claude is better on long-context coherence; Cowork is the only
    path for operator-in-the-loop work).
- **Negative**:
  - The split is heuristic, not enforced. An agent that picks up a
    task outside its preferred shape can still ship; the split is
    advisory.
  - Capability boundaries change as Anthropic / OpenAI ship new
    features. The split has a useful life of months, not years.
  - Cowork-only routines (morning credential rotation) are a
    bottleneck on the operator's calendar. Cannot be parallelized.
- **Neutral**:
  - All three agents share the same `[skip ci]` posture, the same
    safe-merge wrapper, and the same provenance discipline.

## Alternatives Considered

- **Single agent (Claude only or Codex only)**: rejected — different
  task shapes have measurably different optimum agents. The 2026-04-28
  A/B observation in the force-multiplier playbook documents this.
- **No split — operator manually picks per task**: rejected — wastes
  decision energy on every task and produces inconsistent throughput.
- **Tool-level routing (e.g. always Codex for `feat/*` branches,
  Claude for `docs/*`)**: deferred — branch-name conventions are
  fragile; task-shape routing is more durable.

## References

- Force-multiplier playbook (full version):
  `docs/process/claude-force-multiplier-playbook-2026-04-29.md`
- Cowork morning routine:
  `docs/handoffs/cowork-morning-briefing-2026-04-28.md`
- Tranche reports (A/B comparison):
  - `docs/handoffs/codex-megaprompt-tranche-4-2026-04-29-report.md`
  - `docs/handoffs/claude-night-session-2026-04-28-report.md`
- Memory entries:
  - `~/.claude/projects/-Users-aribs/memory/feedback_autonomous_dispatch.md`
  - `~/.claude/projects/-Users-aribs/memory/feedback_full_autonomous_dispatch.md`
