# Sapphire Foundry SDK 0.1.0

Status: release candidate

The Sapphire Foundry SDK is the public, versioned write surface for moving
Sapphire objects into Foundry. It wraps the lower-level `FoundryClient` with a
contract that is easier to diligence:

- Every write uses an explicit `schema_version`.
- Every payload gets a deterministic `request_hash`.
- Every request gets an idempotency key.
- Every request can be serialized and replayed from an envelope.
- Every write can run against a fake client in tests before touching Foundry.

## Python Surface

```python
from lib.foundry.sdk import IdempotencyLedger, SapphireFoundrySDK

sdk = SapphireFoundrySDK.from_env(
    ledger=IdempotencyLedger("data/foundry/sdk_idempotency_ledger.json")
)

result = sdk.write_objects(
    "PaperTrade",
    [{"id": "paper-1", "symbol": "BTC", "direction": "long"}],
    primary_key="id",
)

print(result.to_dict())
```

For replay:

```python
result = sdk.replay_envelope(previous_result.envelope)
```

`replay_envelope(..., force=True)` intentionally submits the same envelope
again. Without `force`, a known idempotency key returns a skipped successful
result.

## Envelope Schema

Schema version: `sapphire.foundry.write.v0.1.0`

```json
{
  "schema_version": "sapphire.foundry.write.v0.1.0",
  "sdk_version": "0.1.0",
  "operation": "upsert_objects",
  "object_type": "PaperTrade",
  "primary_key": "id",
  "objects": [{"id": "paper-1", "symbol": "BTC"}],
  "idempotency_key": "foundry:PaperTrade:<request-hash-prefix>",
  "request_hash": "<sha256 of canonical request payload>",
  "source": "sapphire-foundry-sdk",
  "generated_at": "2026-04-28T00:00:00+00:00",
  "metadata": {}
}
```

The canonical request payload is the sorted JSON representation of:

```json
{
  "schema_version": "sapphire.foundry.write.v0.1.0",
  "operation": "upsert_objects",
  "object_type": "PaperTrade",
  "primary_key": "id",
  "objects": []
}
```

`request_hash` is the SHA-256 of that canonical payload. The default
`idempotency_key` is `foundry:<object_type>:<first 32 request hash chars>`.

## Idempotency Rules

- Reusing an idempotency key with the same request hash is a successful replay.
- Reusing an idempotency key with a different request hash raises
  `FoundrySDKIdempotencyError`.
- The SDK validates that every object has the configured primary key and that
  primary keys are unique within one request.
- The optional `IdempotencyLedger` persists entries as JSON and writes
  atomically by replacing a temporary file.

## Write Modes

The SDK respects `FoundryClient.write_mode`.

| Mode | Delegate |
|---|---|
| `action` | `FoundryClient.upsert_objects(object_type, objects, primary_key=...)` |
| `dataset` | `FoundryClient.upload_dataset_objects(object_type, objects)` |

## Safety Contract

The SDK is not a permission escalator. It never reads secrets directly unless
`from_env()` is used, and it never broadens Foundry access beyond the injected
`FoundryClient`.

Unit tests cover:

- schema-version round-tripping,
- deterministic request hash and idempotency key derivation,
- idempotent replay without a second write,
- forced replay,
- dataset-mode delegation,
- primary-key validation,
- tampered-envelope rejection.
