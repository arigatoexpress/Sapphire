# 09 - Team And Process

Sapphire is a one-operator project, and that fact should be presented honestly. Ari is the product owner, operator, infrastructure owner, and final risk authority. Codex is the primary implementation operator for repo work. Claude/Hermes are constrained reviewers, helpers, and routine participants unless Ari explicitly grants ownership. The collaboration model is reflected in `/Users/aribs/Code/Sapphire/CLAUDE.md`, `/Users/aribs/Code/Sapphire/docs/ops/codex-lead-operating-model.md`, `/Users/aribs/Code/Sapphire/infra/hermes-sapphire-skills.yaml`, and the local branch/PR/local-CI pattern used throughout this tranche.

The strength of the one-operator model is speed with context. Sapphire can move from security incident to productized risk kernel to provenance envelopes to scheduled OODA cadence in days because the operator has the whole system in view. The weakness is key-person risk. This diligence packet exists partly to reduce that risk: it names the architecture, files, controls, costs, incidents, and roadmap so another senior team can inspect the system without needing Ari to narrate every decision live.

Codex and Claude have different roles. Codex leads production-autonomy repo work: live verification, isolated worktrees, small PRs, local CI, and no-spend commits. Claude/Hermes can review, summarize, run constrained routines, and operate through explicit skills. The Hermes skill inventory in `/Users/aribs/Code/Sapphire/infra/hermes-sapphire-skills.yaml` is important because it classifies side effects; the runtime readiness guard in `/Users/aribs/Code/Sapphire/scripts/ops/hermes_runtime_readiness.py` keeps that helper path anchored to the correct Sapphire repo.

The no-spend posture is process, not vibes. Every tranche PR here used `[skip ci]`, relied on `/Users/aribs/Code/Sapphire/scripts/ops/local_ci_verify.py`, and avoided hosted GitHub runner minutes. `/Users/aribs/Code/Sapphire/docs/org/no-spend-github-actions-strategy.md` and `/Users/aribs/Code/Sapphire/docs/ops/self-hosted-actions-runner-setup.md` explain the runner stance. For a buyer, this demonstrates discipline: Sapphire knows when external infrastructure is useful and when it is just invisible burn.

The satellite repo strategy is to keep Sapphire as the canonical control tower while sibling repos and external routines remain bounded. `/Users/aribs/Code/Sapphire/docs/org/control-tower.md` describes core/satellite scope and routine migration stages. `/Users/aribs/Code/Sapphire/infra/org-repos.yaml` and `/Users/aribs/Code/Sapphire/scripts/ops/org_status.py` give repo-level status. This lets Ari use adjacent repos without turning Sapphire into an unmanaged monorepo.

Process quality shows up in the PR shape. Risk Kernel 0.1.0 was separated from Provenance 0.1.0. Provenance backfill and verification were separated from daily OODA scheduling. OODA scheduling was separated from the diligence packet. A tiny ignore-rule cleanup PR was cut when generated provenance sidecars dirtied canonical status. That is the operating pattern an acquirer should care about: small, reviewable, locally verified, safety-aware changes.

The right acquirer is not buying a large team. It is buying a compact operating system and the taste encoded in its guardrails: local-first inference, explicit provenance, risk before action, dry-run before live, and no invented claims. Palantir should care because Sapphire speaks ontology, provenance, and operational readiness. Robinhood should care because Sapphire has a risk-first trading intelligence system with order-draft discipline rather than reckless automation. A security acquirer should care because incidents are turned into controls instead of buried.

The immediate post-acquisition process recommendation is to keep Ari as operator-in-residence for a transition window, assign one engineering owner to risk/provenance packaging, one platform owner to runtime/LaunchAgents, and one product/security owner to decide which mutation paths may ever go live. Sapphire's current state is not "replace the operator." It is "make the operator's judgment executable, inspectable, and eventually transferable."

## Diligence Readout

The buyer should view Ari's one-operator status as both a risk and a feature. It is a risk because too much context can live in one head. It is a feature because the product has not been diluted by committee incentives. The system reflects a coherent taste: local-first, safety-first, evidence-first. That taste is visible in the repo structure and should be preserved through acquisition.

The Codex/Claude collaboration model is also a process asset. Codex is useful as the primary repo operator because it can verify state, edit, test, open PRs, and report what actually happened. Claude/Hermes are useful as reviewers, routines, and constrained assistants. A buyer should not collapse these roles into one undifferentiated "agent." Separation of authority is part of the safety model.

The process should become more team-readable next. That means CODEOWNERS-style ownership for risk, provenance, dashboard, inference, and ops; package-level READMEs for buyer-facing surfaces; and a formal release note for every public surface version. None of that requires a rewrite. It is documentation and ownership around code that now exists.

The satellite strategy should also remain conservative. Sapphire can coordinate adjacent repos, but it should not absorb every experiment. The control-tower docs and org status scripts are the right shape: inspect satellites, classify them, and promote only what earns its way into the core. This is how a one-operator project becomes a platform without turning into a junk drawer.

The cultural close is simple: Sapphire is valuable because it is opinionated about restraint. It can do many things, but it keeps asking whether it should. That is the quality an acquirer should want to preserve.

That restraint should become onboarding material. New engineers should learn the local-CI gate, worktree policy, confirmation firewall, provenance contract, and no-spend posture before they touch feature code.

## Evidence

- `/Users/aribs/Code/Sapphire/CLAUDE.md`
- `/Users/aribs/Code/Sapphire/docs/ops/codex-lead-operating-model.md`
- `/Users/aribs/Code/Sapphire/infra/hermes-sapphire-skills.yaml`
- `/Users/aribs/Code/Sapphire/docs/org/control-tower.md`
- `/Users/aribs/Code/Sapphire/scripts/ops/local_ci_verify.py`
