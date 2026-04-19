"""Unit tests for lib.foundry.sync."""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from lib.foundry.sync import (
    SyncResult,
    SyncState,
    _file_hash,
    _scan_sources,
    detect_changes,
    get_sync_status,
    load_sync_history,
    run_sync,
)


# ---------------------------------------------------------------------------
# SyncState
# ---------------------------------------------------------------------------


class TestSyncState:
    def test_save_and_load(self, tmp_path):
        state = SyncState(
            files={"data/signals/2026-04-19.jsonl": {"mtime": 1000, "hash": "abc"}},
            last_sync="2026-04-19T10:00:00Z",
            last_status="ok",
            sync_count=5,
        )
        path = tmp_path / "state.json"
        state.save(path)

        loaded = SyncState.load(path)
        assert loaded.sync_count == 5
        assert loaded.last_status == "ok"
        assert "2026-04-19.jsonl" in list(loaded.files.keys())[0]

    def test_load_missing(self, tmp_path):
        state = SyncState.load(tmp_path / "nope.json")
        assert state.sync_count == 0
        assert state.last_sync is None

    def test_load_corrupt(self, tmp_path):
        path = tmp_path / "bad.json"
        path.write_text("not json")
        state = SyncState.load(path)
        assert state.sync_count == 0

    def test_save_creates_parent(self, tmp_path):
        path = tmp_path / "sub" / "dir" / "state.json"
        SyncState().save(path)
        assert path.is_file()


# ---------------------------------------------------------------------------
# File hash
# ---------------------------------------------------------------------------


class TestFileHash:
    def test_deterministic(self, tmp_path):
        f = tmp_path / "test.txt"
        f.write_text("hello world")
        h1 = _file_hash(f)
        h2 = _file_hash(f)
        assert h1 == h2
        assert len(h1) == 16

    def test_different_content(self, tmp_path):
        f1 = tmp_path / "a.txt"
        f2 = tmp_path / "b.txt"
        f1.write_text("hello")
        f2.write_text("world")
        assert _file_hash(f1) != _file_hash(f2)

    def test_missing_file(self, tmp_path):
        assert _file_hash(tmp_path / "nope.txt") == ""


# ---------------------------------------------------------------------------
# Delta detection
# ---------------------------------------------------------------------------


class TestDetectChanges:
    def test_new_file(self):
        state = SyncState(files={})
        current = {
            "data/signals/2026-04-19.jsonl": {"mtime": 1000, "hash": "abc", "size": 100}
        }
        changes = detect_changes(state, current)
        assert "PaperTrade" in changes
        assert "data/signals/2026-04-19.jsonl" in changes["PaperTrade"]

    def test_changed_hash(self):
        state = SyncState(files={
            "data/signals/2026-04-19.jsonl": {"mtime": 1000, "hash": "old", "size": 100}
        })
        current = {
            "data/signals/2026-04-19.jsonl": {"mtime": 1000, "hash": "new", "size": 150}
        }
        changes = detect_changes(state, current)
        assert "PaperTrade" in changes

    def test_changed_mtime(self):
        state = SyncState(files={
            "data/signals/2026-04-19.jsonl": {"mtime": 1000, "hash": "abc", "size": 100}
        })
        current = {
            "data/signals/2026-04-19.jsonl": {"mtime": 2000, "hash": "abc", "size": 100}
        }
        changes = detect_changes(state, current)
        assert "PaperTrade" in changes

    def test_no_changes(self):
        files = {
            "data/signals/2026-04-19.jsonl": {"mtime": 1000, "hash": "abc", "size": 100}
        }
        state = SyncState(files=files)
        changes = detect_changes(state, files)
        assert changes == {}

    def test_threat_intel_change(self):
        state = SyncState(files={})
        current = {
            "data/intelligence/2026-04-19/threats.json": {"mtime": 1000, "hash": "xyz", "size": 50}
        }
        changes = detect_changes(state, current)
        assert "ThreatIntel" in changes

    def test_alert_change(self):
        state = SyncState(files={})
        current = {
            "data/system_events.jsonl": {"mtime": 1000, "hash": "xyz", "size": 50}
        }
        changes = detect_changes(state, current)
        assert "Alert" in changes


# ---------------------------------------------------------------------------
# SyncResult
# ---------------------------------------------------------------------------


class TestSyncResult:
    def test_to_dict(self):
        r = SyncResult(
            ok=True,
            timestamp="2026-04-19T10:00:00Z",
            duration_s=1.234,
            changed_types={"PaperTrade": 3},
            uploaded_types={"PaperTrade": 15},
        )
        d = r.to_dict()
        assert d["ok"] is True
        assert d["duration_s"] == 1.23
        assert d["changed_types"]["PaperTrade"] == 3

    def test_default_values(self):
        r = SyncResult(ok=True, timestamp="now")
        d = r.to_dict()
        assert d["errors"] == []
        assert d["dry_run"] is False
        assert d["skipped"] is False


# ---------------------------------------------------------------------------
# Sync history
# ---------------------------------------------------------------------------


class TestSyncHistory:
    def test_load_empty(self, tmp_path):
        assert load_sync_history(tmp_path) == []

    def test_load_entries(self, tmp_path):
        history_path = tmp_path / "data" / "foundry_sync_history.jsonl"
        history_path.parent.mkdir(parents=True)
        entries = [
            {"ok": True, "timestamp": "2026-04-19T10:00:00Z"},
            {"ok": False, "timestamp": "2026-04-19T10:15:00Z", "errors": ["fail"]},
        ]
        history_path.write_text("\n".join(json.dumps(e) for e in entries) + "\n")

        loaded = load_sync_history(tmp_path)
        assert len(loaded) == 2
        assert loaded[1]["ok"] is False

    def test_limit(self, tmp_path):
        history_path = tmp_path / "data" / "foundry_sync_history.jsonl"
        history_path.parent.mkdir(parents=True)
        lines = "\n".join(json.dumps({"ok": True, "i": i}) for i in range(100))
        history_path.write_text(lines + "\n")

        loaded = load_sync_history(tmp_path, limit=5)
        assert len(loaded) == 5


# ---------------------------------------------------------------------------
# run_sync (dry-run mode)
# ---------------------------------------------------------------------------


class TestRunSyncDryRun:
    def test_dry_run_no_data(self, tmp_path):
        # Create minimal structure
        (tmp_path / "data" / "signals").mkdir(parents=True)
        result = run_sync(tmp_path, dry_run=True, force=True)
        assert result.ok is True
        assert result.dry_run is True

    def test_dry_run_with_data(self, tmp_path):
        signals_dir = tmp_path / "data" / "signals"
        signals_dir.mkdir(parents=True)
        (signals_dir / "2026-04-19.jsonl").write_text(
            json.dumps({"pipeline_id": "t1", "symbol": "BTC", "timestamp": "2026-04-19T10:00:00Z"}) + "\n"
        )
        result = run_sync(tmp_path, dry_run=True, force=True)
        assert result.ok is True
        assert result.uploaded_types.get("PaperTrade", 0) >= 1

    def test_skip_when_no_changes(self, tmp_path):
        (tmp_path / "data" / "signals").mkdir(parents=True)
        # First sync to populate state
        run_sync(tmp_path, dry_run=True, force=True)
        # Second sync should skip
        result = run_sync(tmp_path, dry_run=True, force=False)
        assert result.skipped is True

    def test_state_persisted(self, tmp_path):
        (tmp_path / "data" / "signals").mkdir(parents=True)
        (tmp_path / "data" / "signals" / "2026-04-19.jsonl").write_text(
            json.dumps({"pipeline_id": "t1", "symbol": "BTC"}) + "\n"
        )
        run_sync(tmp_path, dry_run=True, force=True)

        state_path = tmp_path / "data" / "foundry_sync_state.json"
        assert state_path.is_file()
        state = json.loads(state_path.read_text())
        assert state["sync_count"] == 1
        assert state["last_status"] == "ok"

    def test_history_appended(self, tmp_path):
        (tmp_path / "data" / "signals").mkdir(parents=True)
        run_sync(tmp_path, dry_run=True, force=True)

        history = load_sync_history(tmp_path)
        assert len(history) >= 1
        assert history[-1]["dry_run"] is True


# ---------------------------------------------------------------------------
# get_sync_status
# ---------------------------------------------------------------------------


class TestGetSyncStatus:
    def test_no_state(self, tmp_path):
        status = get_sync_status(tmp_path)
        assert status["last_status"] == "never"
        assert status["sync_count"] == 0
        assert "PaperTrade" in status["source_types"]

    def test_after_sync(self, tmp_path):
        (tmp_path / "data" / "signals").mkdir(parents=True)
        run_sync(tmp_path, dry_run=True, force=True)

        status = get_sync_status(tmp_path)
        assert status["last_status"] == "ok"
        assert status["sync_count"] == 1
        assert status["tracked_files"] >= 0
