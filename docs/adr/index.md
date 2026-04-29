# Sapphire Architecture Decision Records (ADR) Index

Architecture Decision Records capture the load-bearing design choices that
shape Sapphire. Each record is a single page covering the context, the
decision, the consequences, and the alternatives considered.

**Statuses**:

- `proposed` — under discussion; not yet acted on.
- `accepted` — current decision; live in the codebase.
- `deprecated` — no longer recommended but still in effect somewhere.
- `superseded` — replaced by a newer ADR; the entry's `Related` line
  points at the successor.

**Adding an ADR**: copy `0000-template.md` to the next number, fill in
the sections, link it from this index. Use 4-digit zero-padded numbers.

**Modifying an ADR**: edit only the `Status` field if the decision is
overturned. The body stays as the historical record. Add a new ADR
that supersedes the old one.

## Index

| ADR | Title | Status |
|---|---|---|
| [0000](0000-template.md) | Template | template |
| [0001](0001-no-spend-posture.md) | No-spend posture for autonomous CI | accepted |
| [0002](0002-worktree-per-lane.md) | Worktree-per-lane for parallel autonomous agents | accepted |
| [0003](0003-trading-critical-path-codeowners-gate.md) | Trading critical path is CODEOWNERS-gated | accepted |
| [0004](0004-bounded-llm-tools-via-env-flag-pattern.md) | Bounded LLM tools via env-flag-gated live path | accepted |
| [0005](0005-provenance-envelopes-everywhere.md) | Provenance envelopes on every generated artifact | accepted |
| [0006](0006-fixture-clock-vs-impl-clock-test-template.md) | Fixture-clock vs impl-clock date-flake test template | accepted |
| [0007](0007-correlator-deterministic-rules-then-llm-narrative.md) | Correlator: deterministic rules first, LLM narrative second | accepted |
| [0008](0008-customer-surface-mock-default-with-three-gates.md) | Customer-facing surface is mock-default with three live gates | accepted |
| [0009](0009-foundry-ontology-as-acquisition-bridge.md) | Palantir Foundry ontology as acquisition bridge | accepted |
| [0010](0010-cowork-vs-claude-code-vs-codex-split.md) | Cowork vs Claude Code vs Codex agent split | accepted |
| [0011](0011-tool-registry-section-ordering.md) | Tool registry section ordering convention | accepted |

## One-line summaries

- **0001 No-spend posture** — `[skip ci]` + `vars.SAPPHIRE_RUNNER` gate
  + `scripts/ops/sapphire_safe_merge.sh` wrapper keep autonomous tranche
  cost at zero.
- **0002 Worktree-per-lane** — every parallel agent gets an isolated
  `~/Code/_worktrees/sapphire-<branch>` to prevent canonical
  collisions.
- **0003 Trading critical path CODEOWNERS-gated** — execution paths,
  kill switches, webhooks, and contracts require operator review;
  autonomous agents draft but do not self-merge.
- **0004 Bounded LLM tools via env-flag** — every LLM-touching tool
  defaults to deterministic mock; `SAPPHIRE_<TOOL>_LIVE=1` engages live
  mode. Tests never set the flag.
- **0005 Provenance envelopes everywhere** — every generated artifact
  carries a sha256-hashed provenance envelope (sidecar JSON or inline
  `_provenance` field) so any output can be traced to its inputs.
- **0006 Fixture-clock vs impl-clock template** — when a test uses
  clock primitives against an impl that reads its own clock, inject
  the clock as an arg or monkey-patch with `FrozenDatetime`.
- **0007 Correlator deterministic rules then LLM narrative** —
  `lib/correlator/` is pure rules; `lib/synthesis/` is the LLM
  narrative layer; LLM never sees raw signals.
- **0008 Customer surface mock-default with three gates** —
  customer-facing API requires env flag + payment-verified flag +
  per-tenant allowlist before returning live data.
- **0009 Foundry ontology as acquisition bridge** — Sapphire's signals
  flow into Palantir Foundry's ontology as first-class objects via
  `lib/foundry/`; the schema mirror is the acquisition narrative.
- **0010 Cowork vs Claude Code vs Codex split** — agent routing by task
  shape: Codex for parallel-build lanes, Claude for long-context +
  refactors + skills, Cowork for operator-in-the-loop sessions.
- **0011 Tool registry section ordering** — `infra/tool-registry.yaml`
  organises entries by tranche of introduction; new tools append
  inside their tranche's block, with a reserved divider at the tail
  for the next tranche. Eliminates the parallel-merge YAML conflict
  observed throughout Tranche 5 and Tranche 6.
