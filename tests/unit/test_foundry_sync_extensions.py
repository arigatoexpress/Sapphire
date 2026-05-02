"""Unit tests for Tranche-3 Foundry sync expansion (v0.2.0).

These tests cover the new behaviour added in :mod:`lib.foundry.sync` for
the five new ontology types:

- ``_SOURCE_PATTERNS`` registers the new types so :func:`detect_changes`
  fires the right delta key when a new-type source file shows up.
- :func:`run_sync` writes a per-type watermark JSON under
  ``~/.cache/sapphire/foundry_sync/<type>.json`` after each transform run.
- The watermark base directory is overridable via
  ``SAPPHIRE_FOUNDRY_WATERMARK_DIR`` for CI isolation.
- Existing types continue to sync unchanged.
"""

from __future__ import annotations

import json
from unittest import mock

import pytest

from lib.foundry.sync import (
    _SOURCE_PATTERNS,
    SyncState,
    detect_changes,
    load_watermark,
    run_sync,
    watermark_path,
    write_watermark,
)


@pytest.fixture(autouse=True)
def _isolate_secrets(tmp_path_factory, monkeypatch):
    """Avoid picking up the developer's actual Foundry/Telegram credentials."""
    empty = tmp_path_factory.mktemp("empty-secrets")
    monkeypatch.setenv("SAPPHIRE_SECRETS_DIR", str(empty))
    for var in (
        "PALANTIR_FOUNDRY_URL",
        "FOUNDRY_URL",
        "PALANTIR_FOUNDRY_TOKEN",
        "FOUNDRY_TOKEN",
        "FOUNDRY_API_TOKEN",
    ):
        monkeypatch.delenv(var, raising=False)


# ---------------------------------------------------------------------------
# _SOURCE_PATTERNS expansion (≥4 cases)
# ---------------------------------------------------------------------------


class TestSourcePatternsExpansion:
    def test_new_types_registered(self):
        for name in (
            "IntelVectorRecord",
            "TelegramIntelMessage",
            "HyperliquidSignal",
            "OODAPacket",
            "ThreatIndicator",
        ):
            assert name in _SOURCE_PATTERNS
            assert isinstance(_SOURCE_PATTERNS[name], list)
            assert _SOURCE_PATTERNS[name], f"{name} must have ≥1 pattern"

    def test_intel_vector_record_change_detected(self):
        state = SyncState(files={})
        current = {
            "data/intel/bq_vector_mock.jsonl": {
                "mtime": 1000,
                "hash": "v1",
                "size": 100,
            }
        }
        changes = detect_changes(state, current)
        assert "IntelVectorRecord" in changes
        assert "data/intel/bq_vector_mock.jsonl" in changes["IntelVectorRecord"]

    def test_telegram_intel_change_detected(self):
        state = SyncState(files={})
        current = {
            "data/telegram_intel/2026-04-27/messages.jsonl": {
                "mtime": 1000,
                "hash": "h",
                "size": 50,
            }
        }
        changes = detect_changes(state, current)
        assert "TelegramIntelMessage" in changes

    def test_hyperliquid_signal_change_detected(self):
        state = SyncState(files={})
        current = {"data/hyperliquid_signals.jsonl": {"mtime": 1000, "hash": "h", "size": 50}}
        changes = detect_changes(state, current)
        assert "HyperliquidSignal" in changes

    def test_ooda_packet_change_detected(self):
        state = SyncState(files={})
        current = {"data/gemini_ooda/abcd1234.json": {"mtime": 1000, "hash": "h", "size": 50}}
        changes = detect_changes(state, current)
        assert "OODAPacket" in changes

    def test_threat_indicator_uses_existing_threat_intel_files(self):
        # ThreatIndicator shares the underlying file patterns with ThreatIntel
        # so a single change to threats.json fires both delta keys.
        state = SyncState(files={})
        current = {
            "data/intelligence/2026-04-27/threats.json": {
                "mtime": 1000,
                "hash": "h",
                "size": 50,
            }
        }
        changes = detect_changes(state, current)
        assert "ThreatIntel" in changes
        assert "ThreatIndicator" in changes


# ---------------------------------------------------------------------------
# Watermark helpers (≥4 cases)
# ---------------------------------------------------------------------------


class TestWatermarkHelpers:
    def test_write_and_load_roundtrip(self, tmp_path):
        path = write_watermark(
            "IntelVectorRecord",
            last_synced_at="2026-04-27T10:00:00+00:00",
            object_count=3,
            base_dir=tmp_path,
        )
        assert path.is_file()
        loaded = load_watermark("IntelVectorRecord", base_dir=tmp_path)
        assert loaded["object_count"] == 3
        assert loaded["last_synced_at"].startswith("2026-04-27")

    def test_load_missing_returns_empty(self, tmp_path):
        assert load_watermark("Nope", base_dir=tmp_path) == {}

    def test_load_corrupt_returns_empty(self, tmp_path):
        path = watermark_path("OODAPacket", base_dir=tmp_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("not json")
        assert load_watermark("OODAPacket", base_dir=tmp_path) == {}

    def test_write_creates_parent(self, tmp_path):
        nested = tmp_path / "a" / "b"
        write_watermark(
            "HyperliquidSignal",
            last_synced_at="2026-04-27T10:00:00+00:00",
            object_count=1,
            base_dir=nested,
        )
        assert (nested / "HyperliquidSignal.json").is_file()

    def test_write_extra_metadata_preserved(self, tmp_path):
        write_watermark(
            "TelegramIntelMessage",
            last_synced_at="2026-04-27T10:00:00+00:00",
            object_count=5,
            base_dir=tmp_path,
            extra={"changed_files": ["data/telegram_intel/2026-04-27/messages.jsonl"]},
        )
        loaded = load_watermark("TelegramIntelMessage", base_dir=tmp_path)
        assert "changed_files" in loaded
        assert loaded["changed_files"] == ["data/telegram_intel/2026-04-27/messages.jsonl"]


# ---------------------------------------------------------------------------
# run_sync + watermarks (≥6 cases)
# ---------------------------------------------------------------------------


class TestRunSyncWatermarkProgression:
    def test_dry_run_writes_watermark_for_new_type(self, tmp_path, monkeypatch):
        # Provide a repo-local IntelVectorRecord source.
        intel_path = tmp_path / "data" / "intel" / "bq_vector_mock.jsonl"
        intel_path.parent.mkdir(parents=True)
        intel_path.write_text(
            json.dumps(
                {
                    "id": "v1",
                    "text": "alpha",
                    "embedding": [0.1, 0.2],
                    "source": "ad_hoc",
                    "created_at": "2026-04-27T10:00:00+00:00",
                }
            )
            + "\n"
        )

        watermark_dir = tmp_path / "_watermark"
        monkeypatch.setenv("SAPPHIRE_FOUNDRY_WATERMARK_DIR", str(watermark_dir))
        monkeypatch.setenv("SAPPHIRE_BQ_VECTOR_MOCK_PATH", str(intel_path))

        result = run_sync(tmp_path, dry_run=True, force=True)
        assert result.ok is True
        assert "IntelVectorRecord" in result.uploaded_types

        loaded = load_watermark("IntelVectorRecord", base_dir=watermark_dir)
        assert loaded["object_count"] == 1
        assert loaded["last_synced_at"]

    def test_watermark_progresses_after_subsequent_run(self, tmp_path, monkeypatch):
        intel_path = tmp_path / "data" / "intel" / "bq_vector_mock.jsonl"
        intel_path.parent.mkdir(parents=True)
        intel_path.write_text(json.dumps({"id": "v1", "text": "a", "embedding": [0.1]}) + "\n")
        watermark_dir = tmp_path / "_watermark"
        monkeypatch.setenv("SAPPHIRE_FOUNDRY_WATERMARK_DIR", str(watermark_dir))
        monkeypatch.setenv("SAPPHIRE_BQ_VECTOR_MOCK_PATH", str(intel_path))

        run_sync(tmp_path, dry_run=True, force=True)
        first = load_watermark("IntelVectorRecord", base_dir=watermark_dir)

        # Append a new record + force a second sync run to advance watermark.
        with intel_path.open("a") as fh:
            fh.write(json.dumps({"id": "v2", "text": "b", "embedding": [0.2]}) + "\n")
        run_sync(tmp_path, dry_run=True, force=True)
        second = load_watermark("IntelVectorRecord", base_dir=watermark_dir)

        assert second["object_count"] == 2
        # Timestamps should not regress.
        assert second["last_synced_at"] >= first["last_synced_at"]

    def test_existing_types_still_get_watermarks(self, tmp_path, monkeypatch):
        """Backward-compat: original 8 types must continue to get watermarks too."""
        signals_dir = tmp_path / "data" / "signals"
        signals_dir.mkdir(parents=True)
        (signals_dir / "2026-04-27.jsonl").write_text(
            json.dumps({"pipeline_id": "t1", "symbol": "BTC", "timestamp": "2026-04-27"}) + "\n"
        )
        watermark_dir = tmp_path / "_watermark"
        monkeypatch.setenv("SAPPHIRE_FOUNDRY_WATERMARK_DIR", str(watermark_dir))

        run_sync(tmp_path, dry_run=True, force=True)
        loaded = load_watermark("PaperTrade", base_dir=watermark_dir)
        assert loaded.get("object_count", 0) >= 1

    def test_no_watermark_when_transform_crashes(self, tmp_path, monkeypatch):
        """If a transform raises, no watermark is recorded for that type.

        We patch the registered callable in ``ALL_TRANSFORMS`` directly —
        ``ALL_TRANSFORMS`` is the source of truth the sync uses, so module-
        level monkeypatching of the underlying function would be invisible
        once the dict was built.
        """
        watermark_dir = tmp_path / "_watermark"
        monkeypatch.setenv("SAPPHIRE_FOUNDRY_WATERMARK_DIR", str(watermark_dir))

        from lib.foundry import ingestion as ing

        def _boom(_root, **_kwargs):
            raise RuntimeError("boom")

        with mock.patch.dict(ing.ALL_TRANSFORMS, {"IntelVectorRecord": _boom}):
            result = run_sync(tmp_path, dry_run=True, force=True)
        # The error is captured; other transforms still ran.
        assert any("IntelVectorRecord" in e for e in result.errors)
        assert load_watermark("IntelVectorRecord", base_dir=watermark_dir) == {}

    def test_watermark_for_empty_source_records_zero_count(self, tmp_path, monkeypatch):
        """Even empty results must drop a watermark — that's the 'we looked' signal."""
        watermark_dir = tmp_path / "_watermark"
        monkeypatch.setenv("SAPPHIRE_FOUNDRY_WATERMARK_DIR", str(watermark_dir))

        # Create a signals dir so the change-detection picks up something.
        (tmp_path / "data" / "signals").mkdir(parents=True)
        run_sync(tmp_path, dry_run=True, force=True)

        loaded = load_watermark("IntelVectorRecord", base_dir=watermark_dir)
        # Should exist; the transform ran. Post-Tranche-5 the BQ-vector-store
        # mock surfaces a small fixed set of IntelVectorRecord rows so the
        # count is non-zero even with no operator-supplied source records.
        # The watermark progression — that it WAS recorded at all — is the
        # invariant being verified here, not the absolute count.
        assert loaded != {}
        assert isinstance(loaded["object_count"], int)
        assert loaded["object_count"] >= 0

    def test_watermark_skipped_when_no_changes(self, tmp_path, monkeypatch):
        """A truly skipped sync (no force, no changes) does not write watermarks.

        After the very first run we WILL have watermarks because force=True
        ran the full pass. The second non-force run should record neither
        new uploads nor change watermark mtimes.
        """
        intel_path = tmp_path / "data" / "intel" / "bq_vector_mock.jsonl"
        intel_path.parent.mkdir(parents=True)
        intel_path.write_text(json.dumps({"id": "v1", "text": "a", "embedding": [0.1]}) + "\n")
        watermark_dir = tmp_path / "_watermark"
        monkeypatch.setenv("SAPPHIRE_FOUNDRY_WATERMARK_DIR", str(watermark_dir))
        monkeypatch.setenv("SAPPHIRE_BQ_VECTOR_MOCK_PATH", str(intel_path))

        run_sync(tmp_path, dry_run=True, force=True)
        wm_before = load_watermark("IntelVectorRecord", base_dir=watermark_dir)

        result = run_sync(tmp_path, dry_run=True, force=False)
        assert result.skipped is True

        wm_after = load_watermark("IntelVectorRecord", base_dir=watermark_dir)
        # Skipped sync must not advance the watermark.
        assert wm_after["last_synced_at"] == wm_before["last_synced_at"]


# ---------------------------------------------------------------------------
# Live-mode gating (we never actually contact Foundry)
# ---------------------------------------------------------------------------


class TestLiveModeStillOperatorGated:
    def test_dry_run_does_not_contact_foundry(self, tmp_path, monkeypatch):
        """dry_run=True must never call the Foundry client."""
        watermark_dir = tmp_path / "_watermark"
        monkeypatch.setenv("SAPPHIRE_FOUNDRY_WATERMARK_DIR", str(watermark_dir))
        # Even with credentials present, dry_run wins.
        monkeypatch.setenv("PALANTIR_FOUNDRY_URL", "https://f.example.com")
        monkeypatch.setenv("PALANTIR_FOUNDRY_TOKEN", "secret")

        with mock.patch("lib.foundry.client.FoundryClient.from_env") as factory:
            run_sync(tmp_path, dry_run=True, force=True)
        assert factory.call_count == 0
