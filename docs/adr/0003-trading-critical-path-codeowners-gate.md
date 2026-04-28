# ADR 0003 — Trading critical path is CODEOWNERS-gated

- **Status**: accepted
- **Date**: 2026-04-19 (originally), codified 2026-04-29
- **Authors**: Ari (operator), Sapphire ops
- **Related**: ADR 0001, ADR 0005, ADR 0008

## Context

Sapphire ships autonomously, but real-money paths are not autonomous-safe.
The first $5 BTC live-trade fill on 2026-04-28 made this concrete: a
mistaken merge to the trading critical path could either (a) place an
unintended live order, (b) disable a kill switch, (c) leak credentials,
or (d) exfiltrate signal IP via the webhook. None of those failure modes
are recoverable.

Several autonomous-PR shapes have been observed bumping into the
critical path inadvertently — for example, a "cleanup" PR that reformats
imports across `lib/` and accidentally touches `lib/analytics/strategies.py`,
or a "test rigor" PR that adds a property test to `lib/portfolio/robinhood.py`.

The operator's posture is that **autonomous agents must not be able to
self-merge changes to anything that can spend money, disable safety,
mutate trading logic, or expose secrets** — even when the change looks
benign.

## Decision

`.github/CODEOWNERS` declares an explicit owner (`@arigatoexpress`) on
every trading-critical and security-critical path:

- **Security-sensitive**: `lib/security/`, `lib/core/kill_switch.py`,
  `lib/core/confirmation_firewall.py`, `lib/core/security_monitor.py`,
  `services/webhook/`, `contracts/`, `.git-secrets-patterns`,
  `.gitleaks.toml`, `.sops.yaml`.
- **Trading / execution**: `lib/analytics/strategies.py`,
  `lib/analytics/risk_engine.py`, `lib/portfolio/robinhood.py`,
  `lib/trading/`, `services/alpha/`.
- **CI / automation control plane**: `.github/workflows/`, `.github/actions/`.
- **Telegram operator console** (fail-closed safety surface):
  `plugins/claw-sapphire/tools/internal/_telegram_safety.py`,
  `sapphire_pm_bot.py` (top-level + internal).

**Branch protection on `main`** requires a CODEOWNERS approval for
matching paths. Autonomous agents that touch a CODEOWNERS path open
PRs but cannot self-merge — operator review gates them.

The default for un-fenced paths is **no required owner**. This is
deliberate: low-risk autonomy stays high-throughput; only the genuinely
load-bearing paths gate.

## Consequences

- **Positive**:
  - Clear, machine-enforced fence around the only paths that can spend
    money or disable safety. Autonomous agents cannot accidentally
    short-circuit them.
  - Reviewable from `git log --pretty='%h %s'` plus the CODEOWNERS file —
    no out-of-band tracking needed.
  - Same gate covers Codex agents, Claude agents, and operator-driven
    merges.
- **Negative**:
  - Adds latency to legitimate critical-path improvements. The operator
    is a single point of approval; if Ari is unreachable, the path is
    stalled.
  - The CODEOWNERS file itself is not in CODEOWNERS (chicken-and-egg).
    A malicious or careless edit to CODEOWNERS would loosen the gate;
    branch protection ships partial mitigation but the file is still a
    high-trust surface.
  - Some surfaces sit just outside the gate but arguably belong inside
    (e.g. `lib/correlator/scoring.py` could affect signal generation).
    The list is reviewed when a near-miss occurs.
- **Neutral**:
  - PR titles and bodies remain visible to all reviewers regardless of
    the gate.

## Alternatives Considered

- **Universal CODEOWNERS gate (operator must approve every PR)**:
  rejected — kills autonomous throughput for low-risk paths
  (docs, tests, ADRs). The whole point of autonomy is that low-risk
  changes ship without gating.
- **Path-prefix gates only (no per-file)**: rejected — `lib/core/` is
  too broad; we need `kill_switch.py` and `confirmation_firewall.py`
  gated but not the rest of `lib/core/`.
- **Two-key gate (two reviewers required)**: deferred — adds friction
  in single-operator mode. May revisit at headcount > 1.

## References

- File: `.github/CODEOWNERS`
- Trading critical path enumeration:
  `docs/handoffs/tranche-6-excellence-megaprompt-2026-04-29.md`
  (constraint #2)
- First live-trade fill:
  `~/.claude/projects/-Users-aribs/memory/project_robinhood_first_live_trade_2026-04-28.md`
- Live-capital posture:
  `~/.claude/projects/-Users-aribs/memory/project_robinhood_live_capital_posture.md`
- Branch protection: managed via GitHub repo settings (not in-repo)
