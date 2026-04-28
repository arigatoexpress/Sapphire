# Sapphire Provenance Envelopes 0.1.0

Sapphire Provenance Envelopes 0.1.0 gives generated artifacts a small,
verifiable metadata block before they are promoted into dashboards, Foundry,
content queues, or diligence materials.

The public library is `lib.core.provenance`.

## Schema

Every envelope uses `schema_version=1` and records:

- `generator`: module or script that produced the artifact
- `model`: optional model identifier
- `prompt_hash`: SHA-256 of the prompt text when a prompt exists
- `source_hashes`: map of source file path to SHA-256
- `generated_at`: UTC timestamp
- `ttl_seconds`: optional freshness horizon
- `expires_at`: derived UTC expiry when TTL is present
- `payload_hash`: SHA-256 of the canonical payload
- `metadata`: optional non-secret operational context
- `envelope_hash`: SHA-256 of the canonical envelope excluding itself

The library exposes:

```python
from lib.core.provenance import ProvenanceEnvelope, stamp, verify

stamped = stamp({"answer": 42}, generator="demo", model="local")
assert verify(stamped)
```

For file artifacts, `write_envelope_sidecar(path, ...)` writes a sibling named
`<artifact>.envelope.json`. Sidecars include the artifact path, byte count,
mtime, and file SHA-256 as the stamped payload.

## Canonicalization

All hashes use deterministic JSON:

```python
json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)
```

This means downstream consumers can independently recompute `payload_hash` and
`envelope_hash` without Sapphire-specific state. Mutating either the payload or
the envelope invalidates verification.

## Stamped Writers

0.1.0 wires sidecars or embedded provenance into:

- `lib/autonomy/continuous_intelligence_artifacts.py`
- `lib/content/draft_generator.py`
- `lib/content/report_generator.py`
- `lib/intel/sovereign_thesis.py`
- `lib/foundry/sync.py`
- `plugins/claw-sapphire/tools/internal/gemini_ooda.py`

The first five write sidecar envelopes for local artifacts. Gemini OODA live
cache records embed a provenance block in the cached JSON packet.

## Backfill And Verification

Backfill is dry-run by default:

```bash
python3 scripts/ops/provenance_backfill.py --pretty
```

Apply requires both gates:

```bash
python3 scripts/ops/provenance_backfill.py --apply --i-mean-it --pretty
```

Verification emits JSON and returns non-zero when any artifact older than the
configured age is missing or has an invalid sidecar:

```bash
python3 scripts/ops/provenance_verify.py --older-than-hours 24 --pretty
```

`scripts/ops/production_readiness_sweep.py` includes the verifier as
`provenance/artifact_envelopes`.

## Consumer Contract

Downstream consumers should:

1. Read the artifact.
2. Read `<artifact>.envelope.json`.
3. Verify the sidecar with `verify()`.
4. Recompute the artifact file SHA-256 and compare it with the stamped
   `artifact_sha256`.
5. Enforce `ttl_seconds`/`expires_at` according to the consuming system's
   freshness rules.

Consumers should treat missing or unverifiable envelopes as stale evidence, not
as trusted production facts.
