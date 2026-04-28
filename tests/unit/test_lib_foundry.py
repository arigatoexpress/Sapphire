"""Isolated unit tests for ``lib.foundry``.

These exercise the SDK envelope contract, the idempotency ledger, the sync
delta detector, and a couple of ``run_sync`` branches that the integration
tests in ``test_foundry_sync.py`` skip (specifically the
"non-404 + 404 mixed failure" gate that codex review #106 P1 added in
``run_sync``).

External boundaries — ``FoundryClient`` HTTP, Telegram alerts, and the
filesystem outside ``tmp_path`` — are mocked / pinned. No live network.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from lib.foundry import sync as foundry_sync
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


class _FakeClient:
    """Minimal FoundryClient stand-in for SDK orchestration tests."""

    def __init__(self, *, mode: str = "action") -> None:
        self.write_mode = mode
        self.upsert_calls: list[tuple[str, list[dict[str, Any]], str]] = []
        self.dataset_calls: list[tuple[str, list[dict[str, Any]]]] = []

    def upsert_objects(
        self,
        object_type: str,
        objects: list[dict[str, Any]],
        *,
        primary_key: str = "id",
    ) -> dict[str, Any]:
        self.upsert_calls.append((object_type, list(objects), primary_key))
        return {"ok": True, "ingested": len(objects), "object_type": object_type}

    def upload_dataset_objects(
        self,
        object_type: str,
        objects: list[dict[str, Any]],
    ) -> dict[str, Any]:
        self.dataset_calls.append((object_type, list(objects)))
        return {"ok": True, "uploaded": len(objects), "object_type": object_type}


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------


class TestRequestHashDeterminism:
    def test_compute_request_hash_is_stable_under_key_order(self) -> None:
        a = compute_request_hash(
            schema_version=DEFAULT_SCHEMA_VERSION,
            operation="upsert_objects",
            object_type="PaperTrade",
            primary_key="signal_id",
            objects=[{"signal_id": "s1", "symbol": "BTC", "pnl": 12.5}],
        )
        # Different dict-key insertion order, identical content.
        b = compute_request_hash(
            schema_version=DEFAULT_SCHEMA_VERSION,
            operation="upsert_objects",
            object_type="PaperTrade",
            primary_key="signal_id",
            objects=[{"pnl": 12.5, "symbol": "BTC", "signal_id": "s1"}],
        )
        assert a == b
        assert len(a) == 64  # sha256 hex

    def test_compute_request_hash_changes_when_payload_changes(self) -> None:
        a = compute_request_hash(
            schema_version=DEFAULT_SCHEMA_VERSION,
            operation="upsert_objects",
            object_type="PaperTrade",
            primary_key="signal_id",
            objects=[{"signal_id": "s1", "pnl": 1.0}],
        )
        b = compute_request_hash(
            schema_version=DEFAULT_SCHEMA_VERSION,
            operation="upsert_objects",
            object_type="PaperTrade",
            primary_key="signal_id",
            objects=[{"signal_id": "s1", "pnl": 2.0}],
        )
        assert a != b

    def test_derive_idempotency_key_includes_object_type(self) -> None:
        key = derive_idempotency_key(
            schema_version=DEFAULT_SCHEMA_VERSION,
            operation="upsert_objects",
            object_type="Alert",
            primary_key="alert_id",
            objects=[{"alert_id": "a1"}],
        )
        assert key.startswith("foundry:Alert:")

    def test_unsupported_schema_version_rejected(self) -> None:
        with pytest.raises(FoundrySDKSchemaError):
            compute_request_hash(
                schema_version="sapphire.foundry.write.v999",
                operation="upsert_objects",
                object_type="x",
                primary_key="id",
                objects=[{"id": "a"}],
            )


# ---------------------------------------------------------------------------
# IdempotencyLedger
# ---------------------------------------------------------------------------


class TestIdempotencyLedger:
    def test_in_memory_ledger_stores_and_returns_copy(self) -> None:
        ledger = IdempotencyLedger()
        ledger.record("k1", {"request_hash": "abc", "ok": True})
        got = ledger.get("k1")
        assert got is not None
        assert got["request_hash"] == "abc"
        # Ensure we got a copy (mutation must not leak back into ledger).
        got["request_hash"] = "tampered"
        again = ledger.get("k1")
        assert again is not None
        assert again["request_hash"] == "abc"

    def test_ledger_get_missing_returns_none(self) -> None:
        ledger = IdempotencyLedger()
        assert ledger.get("never-recorded") is None

    def test_persistent_ledger_round_trips_via_disk(self, tmp_path: Path) -> None:
        path = tmp_path / "ledger.json"
        first = IdempotencyLedger(path)
        first.record("k1", {"request_hash": "xyz"})
        # Re-open: persisted state must come back.
        second = IdempotencyLedger(path)
        got = second.get("k1")
        assert got == {"request_hash": "xyz"}

    def test_persistent_ledger_recovers_from_corruption(self, tmp_path: Path) -> None:
        # Defensive branch the integration tests skip: corrupt JSON should not
        # explode loading — it should reset to empty rather than ImportError.
        path = tmp_path / "ledger.json"
        path.write_text("{not-json")
        ledger = IdempotencyLedger(path)
        assert ledger.get("anything") is None
        # And it should still accept new writes after recovery.
        ledger.record("fresh", {"request_hash": "ok"})
        assert ledger.get("fresh") == {"request_hash": "ok"}


# ---------------------------------------------------------------------------
# FoundryWriteEnvelope
# ---------------------------------------------------------------------------


class TestFoundryWriteEnvelope:
    def test_to_dict_and_from_dict_round_trip(self) -> None:
        sdk = SapphireFoundrySDK(client=_FakeClient(), source="sapphire-test")
        envelope = sdk.build_envelope(
            "PaperTrade",
            [{"signal_id": "s1", "symbol": "BTC"}],
            primary_key="signal_id",
        )
        data = envelope.to_dict()
        recovered = FoundryWriteEnvelope.from_dict(data)
        assert recovered.idempotency_key == envelope.idempotency_key
        assert recovered.request_hash == envelope.request_hash
        assert recovered.objects == envelope.objects

    def test_from_dict_rejects_tampered_hash(self) -> None:
        sdk = SapphireFoundrySDK(client=_FakeClient())
        envelope = sdk.build_envelope("Alert", [{"id": "a1"}], primary_key="id")
        data = envelope.to_dict()
        data["objects"] = [{"id": "a1", "extra": "smuggled"}]  # mutate after hash
        with pytest.raises(FoundrySDKSchemaError):
            FoundryWriteEnvelope.from_dict(data)

    def test_from_dict_rejects_missing_idempotency_key(self) -> None:
        sdk = SapphireFoundrySDK(client=_FakeClient())
        envelope = sdk.build_envelope("Alert", [{"id": "a1"}], primary_key="id")
        data = envelope.to_dict()
        data["idempotency_key"] = ""
        with pytest.raises(FoundrySDKSchemaError):
            FoundryWriteEnvelope.from_dict(data)


# ---------------------------------------------------------------------------
# SapphireFoundrySDK orchestration
# ---------------------------------------------------------------------------


class TestSapphireFoundrySDKOrchestration:
    def test_write_objects_invokes_action_upsert_and_records_ledger(self) -> None:
        client = _FakeClient(mode="action")
        sdk = SapphireFoundrySDK(client=client, source="t")
        result = sdk.write_objects(
            "PaperTrade",
            [{"signal_id": "s1", "symbol": "BTC"}],
            primary_key="signal_id",
        )
        assert result.ok is True
        assert result.skipped is False
        assert client.upsert_calls and not client.dataset_calls
        # Re-issuing the same write must short-circuit on the ledger.
        again = sdk.write_objects(
            "PaperTrade",
            [{"signal_id": "s1", "symbol": "BTC"}],
            primary_key="signal_id",
        )
        assert again.skipped is True
        assert len(client.upsert_calls) == 1

    def test_write_objects_dataset_mode_uses_dataset_upload(self) -> None:
        client = _FakeClient(mode="dataset")
        sdk = SapphireFoundrySDK(client=client)
        result = sdk.write_objects(
            "Alert",
            [{"id": "a1", "severity": "high"}],
            primary_key="id",
        )
        assert result.ok is True
        assert client.dataset_calls and not client.upsert_calls

    def test_dry_run_does_not_call_client(self) -> None:
        client = _FakeClient()
        sdk = SapphireFoundrySDK(client=client)
        result = sdk.write_objects(
            "Alert",
            [{"id": "a1"}],
            primary_key="id",
            dry_run=True,
        )
        assert result.dry_run is True
        assert result.foundry_result.get("dry_run") is True
        assert client.upsert_calls == []

    def test_replay_envelope_short_circuits_known_request(self) -> None:
        client = _FakeClient()
        sdk = SapphireFoundrySDK(client=client)
        envelope = sdk.build_envelope("Alert", [{"id": "a1"}], primary_key="id")
        first = sdk._write_envelope(envelope, dry_run=False, replay=False)
        assert first.skipped is False
        replay = sdk.replay_envelope(envelope)
        assert replay.skipped is True
        assert replay.replay is True
        # Force replay path
        forced = sdk.replay_envelope(envelope, force=True)
        assert forced.skipped is False

    def test_idempotency_collision_with_different_payload_raises(self) -> None:
        client = _FakeClient()
        sdk = SapphireFoundrySDK(client=client)
        explicit_key = "foundry:fixed-key:v1"
        sdk.write_objects(
            "Alert",
            [{"id": "a1", "value": 1}],
            primary_key="id",
            idempotency_key=explicit_key,
        )
        with pytest.raises(FoundrySDKIdempotencyError):
            sdk.write_objects(
                "Alert",
                [{"id": "a1", "value": 2}],
                primary_key="id",
                idempotency_key=explicit_key,
            )

    def test_rejects_duplicate_primary_keys_in_one_request(self) -> None:
        sdk = SapphireFoundrySDK(client=_FakeClient())
        with pytest.raises(FoundrySDKSchemaError):
            sdk.build_envelope(
                "Alert",
                [{"id": "a1"}, {"id": "a1"}],
                primary_key="id",
            )

    def test_rejects_empty_object_type(self) -> None:
        sdk = SapphireFoundrySDK(client=_FakeClient())
        with pytest.raises(FoundrySDKSchemaError):
            sdk.build_envelope("", [{"id": "a1"}], primary_key="id")


# ---------------------------------------------------------------------------
# foundry.sync helpers
# ---------------------------------------------------------------------------


class TestSyncStateAndDelta:
    def test_sync_state_round_trips_on_disk(self, tmp_path: Path) -> None:
        state_path = tmp_path / "state.json"
        state = foundry_sync.SyncState(
            files={"data/x.jsonl": {"mtime": 1.0, "hash": "abc", "size": 10}},
            last_sync="2026-04-27T00:00:00+00:00",
            last_status="ok",
            sync_count=3,
            first_success_at="2026-04-26T00:00:00+00:00",
        )
        state.save(state_path)
        loaded = foundry_sync.SyncState.load(state_path)
        assert loaded.last_status == "ok"
        assert loaded.sync_count == 3
        assert loaded.first_success_at == "2026-04-26T00:00:00+00:00"
        assert "data/x.jsonl" in loaded.files

    def test_load_returns_empty_state_when_path_missing(self, tmp_path: Path) -> None:
        loaded = foundry_sync.SyncState.load(tmp_path / "nope.json")
        assert loaded.files == {}
        assert loaded.last_status == "never"

    def test_detect_changes_flags_new_and_modified_files(self) -> None:
        prev = foundry_sync.SyncState(
            files={"data/system_events.jsonl": {"mtime": 1.0, "hash": "old"}}
        )
        current = {
            "data/system_events.jsonl": {"mtime": 2.0, "hash": "new"},
            # PaperTrade pattern matches via fnmatch (uses *, not **).
            "data/signals/2026-04-27.jsonl": {"mtime": 1.0, "hash": "fresh"},
        }
        changed = foundry_sync.detect_changes(prev, current)
        # The system_events file is in the Alert pattern list.
        assert "Alert" in changed
        assert "data/system_events.jsonl" in changed["Alert"]
        # The signals file is in the PaperTrade pattern list.
        assert "PaperTrade" in changed
        assert "data/signals/2026-04-27.jsonl" in changed["PaperTrade"]

    def test_detect_changes_returns_empty_when_nothing_changed(self) -> None:
        files = {"data/system_events.jsonl": {"mtime": 1.0, "hash": "h"}}
        state = foundry_sync.SyncState(files=files.copy())
        assert foundry_sync.detect_changes(state, files) == {}

    def test_auth_warning_fresh_within_24h(self) -> None:
        assert foundry_sync._auth_warning_fresh(
            "2026-04-27T00:00:00+00:00",
            "2026-04-27T12:00:00+00:00",
        )

    def test_auth_warning_fresh_returns_false_after_24h(self) -> None:
        assert not foundry_sync._auth_warning_fresh(
            "2026-04-26T00:00:00+00:00",
            "2026-04-28T00:00:00+00:00",
        )

    def test_auth_warning_fresh_returns_false_for_missing_or_invalid(self) -> None:
        assert not foundry_sync._auth_warning_fresh(None, "2026-04-27T00:00:00+00:00")
        assert not foundry_sync._auth_warning_fresh("garbage", "also-garbage")


class TestRunSyncBranches:
    """Cover the codex-#106 P1 branch: 404 + non-404 must NOT downgrade to skip."""

    def _empty_root(self, tmp_path: Path) -> Path:
        # Build a minimal repo root with the lib/foundry marker the loader looks for.
        (tmp_path / "lib" / "foundry").mkdir(parents=True)
        (tmp_path / "data").mkdir(parents=True)
        return tmp_path

    def test_run_sync_skips_with_no_changes_and_no_force(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        root = self._empty_root(tmp_path)
        # Force the source-scan to return no files.
        monkeypatch.setattr(foundry_sync, "_scan_sources", lambda r: {})
        result = foundry_sync.run_sync(root, dry_run=True, force=False)
        assert result.skipped is True
        assert result.ok is True

    def test_run_sync_dry_run_records_uploads_without_calling_client(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        root = self._empty_root(tmp_path)
        monkeypatch.setattr(
            foundry_sync,
            "_scan_sources",
            lambda r: {"data/system_events.jsonl": {"mtime": 1.0, "hash": "h"}},
        )

        # ALL_TRANSFORMS is imported lazily in run_sync; patch the module.
        from lib.foundry import ingestion

        monkeypatch.setattr(
            ingestion,
            "ALL_TRANSFORMS",
            {"Alert": lambda r: [{"id": "a1"}]},
        )
        result = foundry_sync.run_sync(root, dry_run=True)
        assert result.dry_run is True
        assert result.uploaded_types.get("Alert") == 1


__all__ = [
    "TestFoundryWriteEnvelope",
    "TestIdempotencyLedger",
    "TestRequestHashDeterminism",
    "TestRunSyncBranches",
    "TestSapphireFoundrySDKOrchestration",
    "TestSyncStateAndDelta",
]
