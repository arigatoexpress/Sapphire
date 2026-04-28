"""Unit tests for lib.foundry.sdk."""

from __future__ import annotations

import json

import pytest

from lib.foundry.sdk import (
    DEFAULT_SCHEMA_VERSION,
    FoundrySDKIdempotencyError,
    FoundrySDKSchemaError,
    FoundryWriteEnvelope,
    IdempotencyLedger,
    SapphireFoundrySDK,
    compute_request_hash,
    derive_idempotency_key,
)


class FakeFoundryClient:
    def __init__(self, *, write_mode: str = "action"):
        self.write_mode = write_mode
        self.upsert_calls: list[tuple[str, list[dict], str]] = []
        self.dataset_calls: list[tuple[str, list[dict]]] = []

    def upsert_objects(
        self,
        object_type: str,
        objects: list[dict],
        *,
        primary_key: str = "id",
    ) -> dict:
        self.upsert_calls.append((object_type, objects, primary_key))
        return {"editedObjectTypes": [object_type], "count": len(objects)}

    def upload_dataset_objects(self, object_type: str, objects: list[dict]) -> dict:
        self.dataset_calls.append((object_type, objects))
        return {"dataset": object_type, "count": len(objects)}


def test_envelope_round_trips_schema_version() -> None:
    client = FakeFoundryClient()
    sdk = SapphireFoundrySDK(client=client, source="unit-test")

    envelope = sdk.build_envelope("PaperTrade", [{"id": "p1", "symbol": "BTC"}])
    parsed = FoundryWriteEnvelope.from_dict(envelope.to_dict())

    assert parsed.schema_version == DEFAULT_SCHEMA_VERSION
    assert parsed.sdk_version == envelope.sdk_version
    assert parsed.idempotency_key == envelope.idempotency_key
    assert parsed.request_hash == envelope.request_hash
    assert parsed.to_dict()["objects"] == [{"id": "p1", "symbol": "BTC"}]


def test_request_hash_and_idempotency_key_are_stable() -> None:
    objects = [{"id": "p1", "symbol": "BTC"}, {"id": "p2", "symbol": "ETH"}]

    first_hash = compute_request_hash(
        schema_version=DEFAULT_SCHEMA_VERSION,
        operation="upsert_objects",
        object_type="PaperTrade",
        primary_key="id",
        objects=objects,
    )
    second_hash = compute_request_hash(
        schema_version=DEFAULT_SCHEMA_VERSION,
        operation="upsert_objects",
        object_type="PaperTrade",
        primary_key="id",
        objects=json.loads(json.dumps(objects)),
    )

    assert first_hash == second_hash
    assert derive_idempotency_key(
        schema_version=DEFAULT_SCHEMA_VERSION,
        operation="upsert_objects",
        object_type="PaperTrade",
        primary_key="id",
        objects=objects,
    ).endswith(first_hash[:32])


def test_write_objects_is_idempotent_with_persistent_ledger(tmp_path) -> None:
    client = FakeFoundryClient()
    ledger_path = tmp_path / "foundry-sdk-ledger.json"
    sdk = SapphireFoundrySDK(client=client, ledger=IdempotencyLedger(ledger_path))

    first = sdk.write_objects("PaperTrade", [{"id": "p1", "symbol": "BTC"}])
    second_sdk = SapphireFoundrySDK(
        client=client,
        ledger=IdempotencyLedger(ledger_path),
    )
    second = second_sdk.write_objects("PaperTrade", [{"id": "p1", "symbol": "BTC"}])

    assert first.ok is True
    assert second.skipped is True
    assert second.idempotency_key == first.idempotency_key
    assert len(client.upsert_calls) == 1


def test_idempotency_key_reuse_with_different_payload_raises(tmp_path) -> None:
    client = FakeFoundryClient()
    sdk = SapphireFoundrySDK(client=client, ledger=IdempotencyLedger(tmp_path / "ledger.json"))

    sdk.write_objects(
        "PaperTrade",
        [{"id": "p1", "symbol": "BTC"}],
        idempotency_key="manual-key",
    )

    with pytest.raises(FoundrySDKIdempotencyError):
        sdk.write_objects(
            "PaperTrade",
            [{"id": "p1", "symbol": "ETH"}],
            idempotency_key="manual-key",
        )


def test_replay_envelope_skips_known_request_without_resubmitting(tmp_path) -> None:
    client = FakeFoundryClient()
    ledger = IdempotencyLedger(tmp_path / "ledger.json")
    sdk = SapphireFoundrySDK(client=client, ledger=ledger)
    first = sdk.write_objects("PaperTrade", [{"id": "p1", "symbol": "BTC"}])

    replay = sdk.replay_envelope(first.envelope)

    assert replay.replay is True
    assert replay.skipped is True
    assert replay.request_hash == first.request_hash
    assert len(client.upsert_calls) == 1


def test_replay_envelope_force_submits_again(tmp_path) -> None:
    client = FakeFoundryClient()
    ledger = IdempotencyLedger(tmp_path / "ledger.json")
    sdk = SapphireFoundrySDK(client=client, ledger=ledger)
    first = sdk.write_objects("PaperTrade", [{"id": "p1", "symbol": "BTC"}])

    replay = sdk.replay_envelope(first.envelope, force=True)

    assert replay.replay is True
    assert replay.skipped is False
    assert len(client.upsert_calls) == 2


def test_dataset_mode_uses_dataset_upload_surface() -> None:
    client = FakeFoundryClient(write_mode="dataset")
    sdk = SapphireFoundrySDK(client=client)

    result = sdk.write_objects("ServiceHealth", [{"id": "svc-1", "status": "ok"}])

    assert result.ok is True
    assert client.upsert_calls == []
    assert client.dataset_calls == [("ServiceHealth", [{"id": "svc-1", "status": "ok"}])]


def test_rejects_missing_primary_keys() -> None:
    sdk = SapphireFoundrySDK(client=FakeFoundryClient())

    with pytest.raises(FoundrySDKSchemaError):
        sdk.build_envelope("PaperTrade", [{"symbol": "BTC"}])


def test_rejects_tampered_envelope_hash() -> None:
    sdk = SapphireFoundrySDK(client=FakeFoundryClient())
    envelope = sdk.build_envelope("PaperTrade", [{"id": "p1", "symbol": "BTC"}]).to_dict()
    envelope["objects"][0]["symbol"] = "ETH"

    with pytest.raises(FoundrySDKSchemaError, match="request_hash"):
        FoundryWriteEnvelope.from_dict(envelope)
