# ADR 0000 — Template

- **Status**: template
- **Date**: 2026-04-29
- **Authors**: Sapphire ops
- **Related**: n/a (this file is the template)

## Context

Why is this decision being made? What problem are we solving? What constraints
apply? Cite the original PR / handoff doc / runbook where the issue surfaced.

Capture the relevant facts only. The reader does not need a tutorial — they need
to know which forces pushed us toward the decision.

## Decision

The decision in one or two paragraphs. Should be specific enough that a future
contributor can read this section alone and know what to do. Use plain language;
prefer "we will" over "we should".

If there is an associated invariant (e.g. CI check, hook, CODEOWNERS rule, env
flag default), cite the file path that enforces it.

## Consequences

- **Positive**: what does the decision unlock or improve?
- **Negative**: what does it cost us? Where will future contributors stub their
  toe? What is the operational burden?
- **Neutral**: what stays the same that someone might expect to change?

This section is non-optional. If we cannot enumerate negatives, the decision is
under-thought.

## Alternatives Considered

At least one. State each alternative in one sentence and explain why it lost.
"Do nothing" is a valid alternative — say why it was rejected.

## References

- Originating PR / issue: `#NNN`
- Runbook(s): `docs/ops/<name>-runbook.md`
- Memory entry (if any): `~/.claude/projects/-Users-aribs/memory/<name>.md`
- Code path enforcing this decision: `path/to/file.py`
