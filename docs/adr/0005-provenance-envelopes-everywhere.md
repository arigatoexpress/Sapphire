# ADR 0005 — Provenance envelopes on every generated artifact

- **Status**: accepted
- **Date**: 2026-04-28
- **Authors**: Sapphire ops
- **Related**: ADR 0004, ADR 0009

## Context

Sapphire generates a continuous stream of artifacts: backtest reports,
correlated signals, narrative summaries, dossiers, mission digests,
performance snapshots, intelligence briefs, customer-API responses,
content-engine drafts, audit-panel reports, security scans. Without a
shared provenance discipline, none of these artifacts can answer the
diligence-team question "what did this come from, and can we
reconstruct it?"

Three concrete drivers:

1. **Time-travel** (ADR not yet — Lane 3) needs deterministic inputs to
   replay any artifact. Provenance is the input manifest.
2. **Buyer diligence**: a Foundry / Palantir reviewer asks "show me the
   inputs to this BTC narrative — what data, what model, what code
   commit". Without provenance the answer is "go grep the logs at
   that timestamp". With provenance the answer is one JSON file.
3. **Self-audit**: the audit panel scores autonomous PRs. To do that
   it needs to know what fixtures, models, and commits went into the
   artifact under review.

## Decision

`lib/core/provenance.py` defines a schema-versioned envelope (current
`SCHEMA_VERSION = 1`). Every artifact-emitting code path attaches a
provenance envelope with the following fields:

- **schema_version**: integer; bumped on breaking changes.
- **generator**: tool / module identifier, e.g.
  `lib.synthesis.narrative_engine@0.1.0`.
- **generated_at**: ISO-8601 UTC, second precision.
- **inputs**: list of `{path, sha256}` entries for every file consumed.
- **model** (when applicable): model name, provider, prompt hash.
- **code_commit**: `git rev-parse HEAD` (or "uncommitted" if dirty).
- **flags**: relevant env-flag state (e.g. `SAPPHIRE_*_LIVE`).
- **hash**: sha256 of canonical-JSON of the artifact body excluding
  the envelope itself, to prevent post-hoc tampering.

**Storage**:

- Sidecar JSON: `<artifact_path>.envelope.json` next to the artifact.
- Inline `_provenance` field: when the artifact is itself JSON, embed
  the envelope as a top-level `_provenance` key. Buyer-facing exports
  strip this field but preserve the sidecar.

**Helpers** (see `lib/core/provenance.py`):

- `canonical_json(value)` — deterministic JSON for hashing.
- `sha256_canonical(value)` — sha256 of canonical-JSON.
- `sha256_file(path)` — sha256 of file contents.

New code paths wire provenance via the helpers; existing code paths
were retrofitted across Tranches 4-5.

## Consequences

- **Positive**:
  - Every artifact answers "what produced this" without log diving.
  - Time-travel + replay (ADR — Lane 3) becomes feasible.
  - Audit panel (Lane 5 of Tranche 5) has a typed surface to score.
  - Buyer diligence: provenance JSON sidecars are bulk-exportable
    and reviewable.
- **Negative**:
  - Storage cost: sidecar files are small but additive. Across ~10K
    artifacts/month we add ~50 MB.
  - Code burden: every new tool must remember to emit provenance.
    Hooks do not enforce this; we mitigate via review and via the
    audit panel scoring missing-provenance as a PR-quality signal.
  - Schema evolution: bumping `SCHEMA_VERSION` is a coordinated change.
    Rare but real.
  - Sensitive content (counterparty notes, signals) ends up in
    `inputs[].sha256` not the body — but a hash plus path can still
    leak structure. Buyer-facing exports must redact `inputs[].path`
    when those inputs are sensitive.
- **Neutral**:
  - Provenance envelopes are not signed cryptographically (no PKI).
    A determined adversary with write access to the artifact tree
    could regenerate envelopes. Acceptable for the current trust model
    (single operator, no public publishing of raw envelopes).

## Alternatives Considered

- **Append-only event log without sidecar envelopes**: rejected —
  reconstruction from the event log is operationally expensive and
  loses the artifact-level granularity that buyer diligence wants.
- **Database-backed provenance (Postgres / SQLite)**: rejected — adds
  a service and a backup surface for marginal benefit over filesystem
  sidecars.
- **Cryptographic signing (Sigstore / cosign)**: deferred — meaningful
  if Sapphire publishes artifacts publicly; not yet justified.
- **In-band only (no sidecar)**: rejected — non-JSON artifacts (PNGs,
  PDFs, .pptx) cannot embed JSON cleanly.

## References

- Implementation: `lib/core/provenance.py`
- Schema version constant: `SCHEMA_VERSION = 1` in
  `lib/core/provenance.py`
- Example sidecar: `docs/process/claude-force-multiplier-playbook-2026-04-29.md.envelope.json`
- Audit panel scoring missing-provenance:
  `lib/audit_panel/heuristics.py` (Tranche 5)
