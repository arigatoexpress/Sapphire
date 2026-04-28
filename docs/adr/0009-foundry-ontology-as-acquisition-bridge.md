# ADR 0009 — Palantir Foundry ontology as acquisition bridge

- **Status**: accepted
- **Date**: 2026-04-19 (originally), codified 2026-04-29
- **Authors**: Ari (operator), Sapphire ops
- **Related**: ADR 0005, ADR 0007

## Context

Sapphire is engaged in an active corp-dev conversation with Palantir
Foundry (cold pitch sent 2026-04-28; awaiting reply). The strategic
hypothesis is that Sapphire's value to Foundry is not the
intelligence-platform-itself — Foundry already has data integration
tooling — but specifically the **typed ontology surface** that lets
Sapphire's signals, correlated views, narratives, and trades flow
into Foundry as first-class objects.

Without an ontology bridge, Sapphire is "just another data feed" to
Foundry. With an ontology bridge, Sapphire is "a structured
intelligence layer that maps cleanly into Foundry's existing object
graph". The latter is acquisition-grade; the former is a vendor
relationship at best.

The decision predates Tranche 4. Tranche 4 then made it concrete:
`lib/foundry/` shipped with `client`, `ingestion`, `readiness`, `sync`
modules.

## Decision

Sapphire treats Palantir Foundry's ontology as a **first-class output
target**. Concretely:

1. **Schema mirror**: `docs/foundry-ontology-schema.md` defines the
   Foundry-side object types (Signal, CorrelatedView, Narrative,
   Trade, Customer, ThreatEvent, etc.) that Sapphire generates.
   Schema drift is reviewed PR-by-PR.
2. **Sync daemon**: `services/foundry_sync/` runs a 15-minute
   delta-aware sync from Sapphire's local data into Foundry's
   ontology. Authentication via bearer + OAuth (`lib/foundry/client.py`).
3. **Readiness audit**: `lib/foundry/readiness.py` runs a repo-grounded
   audit comparing what Sapphire generates against what the Foundry
   schema expects. Mismatches show up in mission-status digests.
4. **Provenance pass-through**: every object pushed to Foundry carries
   its provenance envelope (ADR 0005). Foundry-side users can chase
   any object back to its inputs.
5. **Diligence packet** (`docs/diligence/`) is structured around the
   ontology: each diligence section maps to one or more Foundry object
   types, so a Foundry reviewer can read the packet "in their
   language".

The pattern is **intentional vendor lock-in toward Foundry**. We do
not pretend the schema is provider-neutral. Other potential
acquirers (Bloomberg, Refinitiv) would require a separate bridge.

## Consequences

- **Positive**:
  - Acquisition narrative is concrete and demo-able. A Foundry
    reviewer can spin up the readiness audit in their own
    environment and see Sapphire's objects flowing into their
    ontology in real time.
  - The ontology forces Sapphire-side type discipline. Adding a new
    signal source means defining its Foundry-side schema first.
  - Provenance envelopes ride the same path; Foundry side gets full
    chain-of-custody.
- **Negative**:
  - Foundry-specific surface area. If the Palantir conversation
    stalls, the `lib/foundry/` code is dead weight (~1,000 LOC).
  - The 15-minute sync cadence is a poor fit for high-frequency
    signals; trading-critical-path objects sync via a different
    pipeline (not yet wired).
  - Schema drift is high-risk: Foundry-side schema changes can break
    the sync silently. The readiness audit catches this but only in
    the next mission digest, not in real time.
  - The sync daemon needs Foundry credentials. Operator-supervised
    only; not in autonomous CI.
- **Neutral**:
  - The ontology is a useful exercise even setting Foundry aside —
    it forced us to formalize types that were previously dataclasses
    scattered across `lib/`.

## Alternatives Considered

- **Provider-neutral schema (e.g. JSON-LD / RDF)**: rejected — the
  acquisition narrative is the point; provider-neutrality dilutes it.
  We can build a neutral export later if needed.
- **No ontology bridge; rely on flat data export**: rejected — flat
  exports do not produce the "structured intelligence layer" framing
  the acquisition needs.
- **Multiple bridges (Foundry + Bloomberg + Refinitiv)**: deferred —
  shipping one well is better than three half-finished. Foundry is the
  active conversation.

## References

- Strategy doc: `docs/foundry-strategy-2026-04-19.md`
- Schema: `docs/foundry-ontology-schema.md`
- Code: `lib/foundry/{client,ingestion,readiness,sync}.py`
- Service: `services/foundry_sync/`
- Memory entry: `~/.claude/projects/-Users-aribs/memory/project_palantir_pitch.md`
- Pitch (Apr-28): `docs/palantir-foundry-strategy-2026-04-19.md`
