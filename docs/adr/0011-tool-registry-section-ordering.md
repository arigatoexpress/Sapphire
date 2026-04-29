# ADR 0011 — Tool registry section ordering convention

- **Status**: accepted
- **Date**: 2026-04-30
- **Authors**: Sapphire ops
- **Related**: ADR 0002 (worktree-per-lane), Tranche 6 closeout

## Context

`infra/tool-registry.yaml` is the source of truth for every invocable
tool in the repo (validated by `scripts/validate_tool_registry.py` in
CI). Each tool is one YAML mapping under `tools:`, and the schema is
flat — there is no namespacing within the file other than free-form
comment dividers.

During Tranche 5 and Tranche 6 we ran 8-lane parallel-merge waves
(each tranche). On both tranches every lane PR appended its new tool
entry at the same insertion point — typically right above the last
deprecated entry, or at the literal tail of `tools:`. The result was
a YAML conflict on every wave: `git` could not 3-way merge two
sibling appends at the same location even though the entries were
disjoint.

The conflict was always trivial to resolve manually, but each
resolution cost ~5 minutes of orchestrator attention and broke the
otherwise-clean parallel-merge model. Tranche 6 hit it at least 5
times in the same hour during the Lane 4 / Lane 5 / Lane 6 / Lane 7
window.

## Decision

We codify a **section ordering convention** in
`infra/tool-registry.yaml`. The file is structured top-to-bottom as:

```
1. Header (block comment, schema documentation)
2. ─── Section ordering convention (this ADR's body, copied as a comment)
3. version: 1
4. tools:
   1. ─── Registered / agent-facing (LLM-visible) ───
      (the lean LLM-visible subset)
   2. ─── Internal — Tranche 1 ───
      (internal tools introduced in Tranche 1)
   3. ─── Internal — Tranche 2 ───
   4. ─── Internal — Tranche 3 ───
   5. ─── Internal — Tranche 4 ───
   6. ─── Internal — Tranche 5 ───
   7. ─── Internal — Tranche 6 ───
   8. ─── Deprecated ───
   9. ─── Tranche 7 reserved ───  ← stable insertion point for the next wave
```

**Rules**:

1. New tools introduced in Tranche N are appended inside the
   `# ─── Internal — Tranche N ───` block. Never at end-of-file
   unless you are opening a brand-new tranche window.
2. The reserved divider at the tail (`# ─── Tranche M reserved ───`)
   stays as a placeholder. When Tranche M opens, lanes append above
   the divider and the divider is bumped to `Tranche M+1 reserved`.
3. Existing entries are NOT reordered when this convention is
   introduced. The section dividers are additive comments. Tranche
   6 Lane 9's introduction of this ADR is therefore zero-risk to
   the CI invariant in `validate_tool_registry.py`.
4. The convention is purely a positional discipline for parallel
   appends. It has no effect on the registry schema, on
   `agent-manifest.yaml`, or on tool-selection accuracy at runtime.

## Consequences

- **Positive**:
  - Eliminates the trivial-but-recurring YAML conflict on every
    parallel-merge wave. Tranche 7's 8 lanes can append in 8 distinct
    spots within the `Tranche 7` block (or a single block if they
    coordinate alphabetic ordering inside the block).
  - The file becomes self-documenting — a future operator can scan
    the dividers and see at a glance which tools came in which
    tranche, which is useful provenance.
  - Cheap to retrofit (this ADR is a comment-only edit).
- **Negative**:
  - One additional discipline to remember when adding a tool. New
    contributors may miss it; CI does not enforce the convention
    (it only enforces the invariants in
    `scripts/validate_tool_registry.py`).
  - The section markers are advisory; nothing prevents a lazy commit
    from appending at end-of-file. Code review is the enforcement
    layer.
- **Neutral**:
  - Existing tools are not reordered. Anyone reading
    `git blame infra/tool-registry.yaml` will see the original commit
    history unchanged.

## Alternatives Considered

- **Per-tranche files** (`infra/tool-registry/tranche-N.yaml` glued
  together by a loader): rejected — requires modifying
  `validate_tool_registry.py` and several callers, and breaks the
  single-source-of-truth principle.
- **Alphabetic ordering of all entries**: rejected — conflicts
  *more* often, not less, because alphabetic ordering forces every
  new tool name to land at a position determined by a prefix that
  may collide with another lane's prefix.
- **CI-enforced section ordering**: deferred to a future ADR if the
  comment-only convention proves insufficient. The rule is simple
  enough that code review should catch violations.

## References

- Tranche 6 closeout report: `docs/handoffs/tranche-6-excellence-2026-04-30-report.md`
- Validator: `scripts/validate_tool_registry.py`
- Manifest: `infra/agent-manifest.yaml`
- Registry: `infra/tool-registry.yaml`
