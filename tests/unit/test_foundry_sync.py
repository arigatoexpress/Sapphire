"""Unit tests for lib.foundry.sync."""

from __future__ import annotations

import json
from unittest import mock

import pytest

from lib.foundry.sync import (
    SyncResult,
    SyncState,
    _auth_warning_fresh,
    _file_hash,
    _repo_root,
    detect_changes,
    get_sync_status,
    load_sync_history,
    run_sync,
)


@pytest.fixture(autouse=True)
def _isolate_secrets(tmp_path_factory, monkeypatch):
    """Point SAPPHIRE_SECRETS_DIR at an empty tmp dir so run_sync tests
    don't pick up the developer's real foundry_url/foundry_token files."""
    empty = tmp_path_factory.mktemp("empty-secrets")
    monkeypatch.setenv("SAPPHIRE_SECRETS_DIR", str(empty))
    for v in (
        "PALANTIR_FOUNDRY_URL",
        "FOUNDRY_URL",
        "PALANTIR_FOUNDRY_TOKEN",
        "FOUNDRY_TOKEN",
        "FOUNDRY_API_TOKEN",
        "PALANTIR_FOUNDRY_CLIENT_ID",
        "FOUNDRY_CLIENT_ID",
        "PALANTIR_FOUNDRY_CLIENT_SECRET",
        "FOUNDRY_CLIENT_SECRET",
        "PALANTIR_FOUNDRY_ONTOLOGY",
        "FOUNDRY_ONTOLOGY",
        "PALANTIR_FOUNDRY_UPSERT_ACTION",
        "FOUNDRY_UPSERT_ACTION",
        "PALANTIR_FOUNDRY_WRITE_MODE",
        "FOUNDRY_WRITE_MODE",
        "PALANTIR_FOUNDRY_DATASET_MAP",
        "FOUNDRY_DATASET_MAP",
    ):
        monkeypatch.delenv(v, raising=False)


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


class TestRepoRoot:
    def test_env_override_wins(self, tmp_path, monkeypatch):
        monkeypatch.setenv("SAPPHIRE_REPO_ROOT", str(tmp_path))

        assert _repo_root() == tmp_path


# ---------------------------------------------------------------------------
# Delta detection
# ---------------------------------------------------------------------------


class TestDetectChanges:
    def test_new_file(self):
        state = SyncState(files={})
        current = {"data/signals/2026-04-19.jsonl": {"mtime": 1000, "hash": "abc", "size": 100}}
        changes = detect_changes(state, current)
        assert "PaperTrade" in changes
        assert "data/signals/2026-04-19.jsonl" in changes["PaperTrade"]

    def test_changed_hash(self):
        state = SyncState(
            files={"data/signals/2026-04-19.jsonl": {"mtime": 1000, "hash": "old", "size": 100}}
        )
        current = {"data/signals/2026-04-19.jsonl": {"mtime": 1000, "hash": "new", "size": 150}}
        changes = detect_changes(state, current)
        assert "PaperTrade" in changes

    def test_changed_mtime(self):
        state = SyncState(
            files={"data/signals/2026-04-19.jsonl": {"mtime": 1000, "hash": "abc", "size": 100}}
        )
        current = {"data/signals/2026-04-19.jsonl": {"mtime": 2000, "hash": "abc", "size": 100}}
        changes = detect_changes(state, current)
        assert "PaperTrade" in changes

    def test_no_changes(self):
        files = {"data/signals/2026-04-19.jsonl": {"mtime": 1000, "hash": "abc", "size": 100}}
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
        current = {"data/system_events.jsonl": {"mtime": 1000, "hash": "xyz", "size": 50}}
        changes = detect_changes(state, current)
        assert "Alert" in changes

    def test_regional_intel_change(self):
        state = SyncState(files={})
        current = {
            "data/foundry/regional-intel/IntelItem.ndjson": {
                "mtime": 1000,
                "hash": "regional",
                "size": 50,
            }
        }
        changes = detect_changes(state, current)
        assert changes == {"IntelItem": ["data/foundry/regional-intel/IntelItem.ndjson"]}


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
            json.dumps({"pipeline_id": "t1", "symbol": "BTC", "timestamp": "2026-04-19T10:00:00Z"})
            + "\n"
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
        assert "IntelItem" in status["source_types"]


# ---------------------------------------------------------------------------
# Graceful degradation — no Telegram spam when Foundry isn't configured
# ---------------------------------------------------------------------------


class TestRunSyncGracefulDegradation:
    def test_config_missing_exits_ok_and_skipped(self, tmp_path):
        """With no URL configured, run_sync must exit cleanly and not page."""
        # Create at least one changed source so we hit the upload path
        signals_dir = tmp_path / "data" / "signals"
        signals_dir.mkdir(parents=True)
        (signals_dir / "2026-04-19.jsonl").write_text(
            json.dumps({"pipeline_id": "t1", "symbol": "BTC"}) + "\n"
        )

        with mock.patch("lib.foundry.sync._send_telegram_alert") as tg:
            result = run_sync(tmp_path, dry_run=False, force=True)

        assert tg.call_count == 0, "Telegram must not fire on config_missing"
        assert result.ok is True
        assert result.skipped is True

        state_path = tmp_path / "data" / "foundry_sync_state.json"
        state = json.loads(state_path.read_text())
        assert state["last_status"] == "not_configured"

    def test_foundry_preflight_config_error_exits_ok_and_skipped(self, tmp_path, monkeypatch):
        """Missing ontology/action config is a setup gap, not a per-object error."""
        monkeypatch.setenv("PALANTIR_FOUNDRY_URL", "https://f.example.com")
        monkeypatch.setenv("PALANTIR_FOUNDRY_TOKEN", "ok-tok")

        signals_dir = tmp_path / "data" / "signals"
        signals_dir.mkdir(parents=True)
        (signals_dir / "2026-04-19.jsonl").write_text(
            json.dumps({"pipeline_id": "t1", "symbol": "BTC"}) + "\n"
        )

        from lib.foundry.client import FoundryConfigError

        with (
            mock.patch(
                "lib.foundry.client.FoundryClient.validate_write_target",
                side_effect=FoundryConfigError("Configured Foundry ontology missing"),
            ),
            mock.patch("lib.foundry.sync._send_telegram_alert") as tg,
        ):
            result = run_sync(tmp_path, dry_run=False, force=True)

        assert tg.call_count == 0
        assert result.ok is True
        assert result.skipped is True
        state_path = tmp_path / "data" / "foundry_sync_state.json"
        state = json.loads(state_path.read_text())
        assert state["last_status"] == "not_configured"

    def test_auth_failure_before_first_success_does_not_telegram(self, tmp_path, monkeypatch):
        """Auth error with no prior success → warn once, no Telegram spam."""
        monkeypatch.setenv("PALANTIR_FOUNDRY_URL", "https://f.example.com")
        monkeypatch.setenv("PALANTIR_FOUNDRY_TOKEN", "bad-tok")

        signals_dir = tmp_path / "data" / "signals"
        signals_dir.mkdir(parents=True)
        (signals_dir / "2026-04-19.jsonl").write_text(
            json.dumps({"pipeline_id": "t1", "symbol": "BTC"}) + "\n"
        )

        from lib.foundry.client import FoundryAuthError

        with (
            mock.patch(
                "lib.foundry.client.FoundryClient.validate_write_target",
                return_value=None,
            ),
            mock.patch(
                "lib.foundry.client.FoundryClient.upsert_objects",
                side_effect=FoundryAuthError("401 unauthorized"),
            ),
            mock.patch("lib.foundry.sync._send_telegram_alert") as tg,
        ):
            result = run_sync(tmp_path, dry_run=False, force=True)

        assert tg.call_count == 0, "must not page on first-time auth failure"
        assert result.ok is False
        state_path = tmp_path / "data" / "foundry_sync_state.json"
        state = json.loads(state_path.read_text())
        assert state["first_success_at"] is None
        assert state["last_auth_warning_at"] is not None

    def test_alert_fires_after_first_success_then_failure(self, tmp_path, monkeypatch):
        """Real upload failure after prior success → Telegram alert fires."""
        monkeypatch.setenv("PALANTIR_FOUNDRY_URL", "https://f.example.com")
        monkeypatch.setenv("PALANTIR_FOUNDRY_TOKEN", "ok-tok")

        # Pre-seed state with a prior successful sync
        state_path = tmp_path / "data" / "foundry_sync_state.json"
        state_path.parent.mkdir(parents=True, exist_ok=True)
        state_path.write_text(
            json.dumps(
                {
                    "files": {},
                    "last_sync": "2026-04-18T00:00:00+00:00",
                    "last_status": "ok",
                    "sync_count": 3,
                    "first_success_at": "2026-04-18T00:00:00+00:00",
                    "last_auth_warning_at": None,
                }
            )
        )

        signals_dir = tmp_path / "data" / "signals"
        signals_dir.mkdir(parents=True)
        (signals_dir / "2026-04-19.jsonl").write_text(
            json.dumps({"pipeline_id": "t1", "symbol": "BTC"}) + "\n"
        )

        from lib.foundry.client import FoundryAPIError

        with (
            mock.patch(
                "lib.foundry.client.FoundryClient.validate_write_target",
                return_value=None,
            ),
            mock.patch(
                "lib.foundry.client.FoundryClient.upsert_objects",
                side_effect=FoundryAPIError("500 Internal", status=500),
            ),
            mock.patch("lib.foundry.sync._send_telegram_alert") as tg,
        ):
            result = run_sync(tmp_path, dry_run=False, force=True)

        assert result.ok is False
        assert tg.call_count == 1, "page once after post-success failure"

    def test_404_before_first_success_demotes_to_not_configured(
        self, tmp_path, monkeypatch, caplog
    ):
        """A 404 on upsert-action before any success means the ontology isn't
        provisioned yet. Downgrade to INFO, route to the not_configured state,
        and don't Telegram-alert. This keeps foundry-sync-err.log clean while
        the user finishes setup, but preserves ERROR for real 4xx/5xx failures.
        """
        monkeypatch.setenv("PALANTIR_FOUNDRY_URL", "https://f.example.com")
        monkeypatch.setenv("PALANTIR_FOUNDRY_TOKEN", "ok-tok")

        signals_dir = tmp_path / "data" / "signals"
        signals_dir.mkdir(parents=True)
        (signals_dir / "2026-04-19.jsonl").write_text(
            json.dumps({"pipeline_id": "t1", "symbol": "BTC"}) + "\n"
        )

        from lib.foundry.client import FoundryAPIError

        with (
            mock.patch(
                "lib.foundry.client.FoundryClient.validate_write_target",
                return_value=None,
            ),
            mock.patch(
                "lib.foundry.client.FoundryClient.upsert_objects",
                side_effect=FoundryAPIError(
                    "Foundry API POST /api/v2/ontologies/ontology/actions/sapphire-upsert/apply → 404",
                    status=404,
                ),
            ),
            mock.patch("lib.foundry.sync._send_telegram_alert") as tg,
            caplog.at_level("INFO"),
        ):
            result = run_sync(tmp_path, dry_run=False, force=True)

        assert tg.call_count == 0, "ontology-not-ready must not Telegram"
        assert result.skipped is True, "should route to not_configured path"
        assert result.ok is True
        state_path = tmp_path / "data" / "foundry_sync_state.json"
        state = json.loads(state_path.read_text())
        assert state["last_status"] == "not_configured"
        # Confirm the INFO line fired and no ERROR for the same 404
        info_msgs = [r.getMessage() for r in caplog.records if r.levelname == "INFO"]
        error_msgs = [r.getMessage() for r in caplog.records if r.levelname == "ERROR"]
        assert any("skipped" in m and "404" in m for m in info_msgs), (
            f"expected INFO log like 'Upload ... skipped (... 404) ...', got {info_msgs!r}"
        )
        assert not any("404" in m for m in error_msgs), (
            "404 must be INFO, not ERROR, while ontology is unprovisioned"
        )

    def test_404_mixed_with_non_404_failure_does_not_demote(self, tmp_path, monkeypatch, caplog):
        """Codex review #106 P1 follow-up (r3117240955): if the batch mixes a
        pre-success 404 with any other failure (e.g. 500), the run is a real
        failure and must alert — not be silently demoted to not_configured.
        """
        monkeypatch.setenv("PALANTIR_FOUNDRY_URL", "https://f.example.com")
        monkeypatch.setenv("PALANTIR_FOUNDRY_TOKEN", "ok-tok")

        signals_dir = tmp_path / "data" / "signals"
        signals_dir.mkdir(parents=True)
        (signals_dir / "2026-04-19.jsonl").write_text(
            json.dumps({"pipeline_id": "t1", "symbol": "BTC"}) + "\n"
        )

        from lib.foundry.client import FoundryAPIError

        # First upload returns 404, second returns 500
        side_effects = [
            FoundryAPIError("not deployed → 404", status=404),
            FoundryAPIError("server exploded → 500", status=500),
        ]
        with (
            mock.patch.dict(
                "lib.foundry.ingestion.ALL_TRANSFORMS",
                {"TypeA": lambda r: [{"id": "a1"}], "TypeB": lambda r: [{"id": "b1"}]},
                clear=True,
            ),
            mock.patch(
                "lib.foundry.client.FoundryClient.validate_write_target",
                return_value=None,
            ),
            mock.patch(
                "lib.foundry.client.FoundryClient.upsert_objects",
                side_effect=side_effects,
            ),
            mock.patch("lib.foundry.sync._send_telegram_alert"),
            caplog.at_level("INFO"),
        ):
            result = run_sync(tmp_path, dry_run=False, force=True)

        # The mixed-error case must NOT be demoted to not_configured —
        # the 500 is a real failure that deserves visibility.
        assert result.skipped is False, (
            "mixed 404+500 must not silently demote to skipped/not_configured"
        )
        assert result.ok is False
        state_path = tmp_path / "data" / "foundry_sync_state.json"
        state = json.loads(state_path.read_text())
        assert state["last_status"] == "error"
        # The 500 ERROR log must be present.
        error_msgs = [r.getMessage() for r in caplog.records if r.levelname == "ERROR"]
        assert any("500" in m for m in error_msgs), (
            f"expected an ERROR log for the 500; got {error_msgs!r}"
        )

    def test_404_after_first_success_pages_as_regression(self, tmp_path, monkeypatch, caplog):
        """Codex review #106 P1: once the sync has ever succeeded, a 404 is
        a regression (action deleted / renamed / perms revoked), not a fresh
        setup gap. Must page + stay at ERROR, not be silently demoted to
        not_configured.
        """
        monkeypatch.setenv("PALANTIR_FOUNDRY_URL", "https://f.example.com")
        monkeypatch.setenv("PALANTIR_FOUNDRY_TOKEN", "ok-tok")

        # Pre-seed state as if we've synced successfully before
        state_path = tmp_path / "data" / "foundry_sync_state.json"
        state_path.parent.mkdir(parents=True, exist_ok=True)
        state_path.write_text(
            json.dumps(
                {
                    "files": {},
                    "last_sync": "2026-04-18T00:00:00+00:00",
                    "last_status": "ok",
                    "sync_count": 3,
                    "first_success_at": "2026-04-18T00:00:00+00:00",
                    "last_auth_warning_at": None,
                }
            )
        )

        signals_dir = tmp_path / "data" / "signals"
        signals_dir.mkdir(parents=True)
        (signals_dir / "2026-04-19.jsonl").write_text(
            json.dumps({"pipeline_id": "t1", "symbol": "BTC"}) + "\n"
        )

        from lib.foundry.client import FoundryAPIError

        with (
            mock.patch(
                "lib.foundry.client.FoundryClient.validate_write_target",
                return_value=None,
            ),
            mock.patch(
                "lib.foundry.client.FoundryClient.upsert_objects",
                side_effect=FoundryAPIError(
                    "Foundry API POST /api/v2/ontologies/ontology/actions/sapphire-upsert/apply → 404",
                    status=404,
                ),
            ),
            mock.patch("lib.foundry.sync._send_telegram_alert") as tg,
            caplog.at_level("INFO"),
        ):
            result = run_sync(tmp_path, dry_run=False, force=True)

        assert result.ok is False, "post-success 404 must report failure, not ok=True"
        assert result.skipped is False, "must not demote to skipped/not_configured"
        assert tg.call_count == 1, "post-success 404 must Telegram (regression)"
        state = json.loads(state_path.read_text())
        assert state["last_status"] == "error", "status must reflect the regression"
        # ERROR path, not INFO
        error_msgs = [r.getMessage() for r in caplog.records if r.levelname == "ERROR"]
        assert any("404" in m for m in error_msgs), (
            f"expected ERROR carrying 404 once first_success_at is set; got ERRORs={error_msgs!r}"
        )

    def test_dataset_mode_uploads_dataset_snapshot(self, tmp_path, monkeypatch):
        """Dataset write mode uploads JSONL snapshots and does not require an action."""
        monkeypatch.setenv("PALANTIR_FOUNDRY_URL", "https://f.example.com")
        monkeypatch.setenv("PALANTIR_FOUNDRY_TOKEN", "ok-tok")
        monkeypatch.setenv("FOUNDRY_WRITE_MODE", "dataset")
        monkeypatch.setenv(
            "FOUNDRY_DATASET_MAP",
            '{"PaperTrade":"ri.foundry.main.dataset.paper"}',
        )

        signals_dir = tmp_path / "data" / "signals"
        signals_dir.mkdir(parents=True)
        (signals_dir / "2026-04-19.jsonl").write_text(
            json.dumps({"pipeline_id": "t1", "symbol": "BTC"}) + "\n"
        )

        with (
            mock.patch(
                "lib.foundry.client.FoundryClient.validate_write_target",
                return_value=None,
            ) as validate,
            mock.patch(
                "lib.foundry.client.FoundryClient.upload_dataset_objects",
                return_value={"objects_uploaded": 1},
            ) as upload,
            mock.patch("lib.foundry.sync._send_telegram_alert") as tg,
        ):
            result = run_sync(tmp_path, dry_run=False, force=True)

        assert tg.call_count == 0
        assert result.ok is True
        assert result.skipped is False
        assert result.uploaded_types["PaperTrade"] == 1
        validate.assert_called_once_with(["PaperTrade"])
        upload.assert_called_once()
        assert upload.call_args.args[0] == "PaperTrade"

    def test_dataset_mode_404_is_not_demoted(self, tmp_path, monkeypatch):
        """Dataset upload 404s are real write failures, not missing action setup."""
        monkeypatch.setenv("PALANTIR_FOUNDRY_URL", "https://f.example.com")
        monkeypatch.setenv("PALANTIR_FOUNDRY_TOKEN", "ok-tok")
        monkeypatch.setenv("FOUNDRY_WRITE_MODE", "dataset")
        monkeypatch.setenv(
            "FOUNDRY_DATASET_MAP",
            '{"PaperTrade":"ri.foundry.main.dataset.paper"}',
        )

        signals_dir = tmp_path / "data" / "signals"
        signals_dir.mkdir(parents=True)
        (signals_dir / "2026-04-19.jsonl").write_text(
            json.dumps({"pipeline_id": "t1", "symbol": "BTC"}) + "\n"
        )

        from lib.foundry.client import FoundryAPIError

        with (
            mock.patch(
                "lib.foundry.client.FoundryClient.validate_write_target",
                return_value=None,
            ),
            mock.patch(
                "lib.foundry.client.FoundryClient.upload_dataset_objects",
                side_effect=FoundryAPIError("dataset missing", status=404),
            ),
            mock.patch("lib.foundry.sync._send_telegram_alert") as tg,
        ):
            result = run_sync(tmp_path, dry_run=False, force=True)

        assert tg.call_count == 0
        assert result.ok is False
        assert result.skipped is False
        state_path = tmp_path / "data" / "foundry_sync_state.json"
        state = json.loads(state_path.read_text())
        assert state["last_status"] == "error"


class TestAuthWarningFresh:
    def test_none(self):
        assert _auth_warning_fresh(None, "2026-04-19T00:00:00+00:00") is False

    def test_within_24h(self):
        assert (
            _auth_warning_fresh(
                "2026-04-19T00:00:00+00:00",
                "2026-04-19T10:00:00+00:00",
            )
            is True
        )

    def test_beyond_24h(self):
        assert (
            _auth_warning_fresh(
                "2026-04-17T00:00:00+00:00",
                "2026-04-19T00:00:00+00:00",
            )
            is False
        )
