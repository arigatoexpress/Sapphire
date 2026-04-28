"""Tests for _resolve_bot_token in services/pm_bot/server.py."""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

SERVICES_DIR = Path(__file__).resolve().parent
if str(SERVICES_DIR) not in sys.path:
    sys.path.insert(0, str(SERVICES_DIR))


@pytest.fixture
def reload_server(monkeypatch):
    """Reload services.pm_bot.server fresh so module-level SETTINGS rebuilds."""
    # Clear any cached module so from_env runs fresh under the monkeypatched env
    monkeypatch.delenv("SAPPHIRE_PM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("SAPPHIRE_PM_BOT_WEBHOOK_SECRET", raising=False)
    monkeypatch.delenv("TELEGRAM_WEBHOOK_SECRET", raising=False)
    monkeypatch.delenv("MODE", raising=False)

    if "server" in sys.modules:
        del sys.modules["server"]

    def _load():
        return importlib.import_module("server")

    return _load


def test_explicit_token_wins(monkeypatch, reload_server):
    monkeypatch.setenv("SAPPHIRE_PM_BOT_TOKEN", "explicit-override")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "shared-should-be-ignored")
    server = reload_server()
    assert server._resolve_bot_token() == "explicit-override"


def test_falls_back_to_shared_telegram_token(monkeypatch, reload_server):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "shared-sapphire-token")
    server = reload_server()
    assert server._resolve_bot_token() == "shared-sapphire-token"


def test_falls_back_to_secrets_file(monkeypatch, tmp_path, reload_server):
    fake_home = tmp_path
    sapphire_secrets = fake_home / ".config" / "sapphire-secrets"
    sapphire_secrets.mkdir(parents=True)
    token_file = sapphire_secrets / "telegram_bot_token"
    token_file.write_text("  file-based-token  \n")

    monkeypatch.setenv("HOME", str(fake_home))
    server = reload_server()
    # Re-patch the module-level _SECRET_PATHS which is bound at import time
    from pathlib import Path as _Path

    monkeypatch.setattr(
        server,
        "_SECRET_PATHS",
        [
            _Path(fake_home) / ".config" / "sapphire-secrets" / "telegram_bot_token",
            _Path(fake_home) / ".config" / "sapphire" / "telegram_bot_token",
        ],
    )
    assert server._resolve_bot_token() == "file-based-token"


def test_returns_empty_when_nothing_configured(monkeypatch, tmp_path, reload_server):
    monkeypatch.setenv("HOME", str(tmp_path))
    server = reload_server()
    from pathlib import Path as _Path

    # Point secret paths at a directory that has no files
    monkeypatch.setattr(
        server,
        "_SECRET_PATHS",
        [
            _Path(tmp_path) / ".config" / "sapphire-secrets" / "telegram_bot_token",
            _Path(tmp_path) / ".config" / "sapphire" / "telegram_bot_token",
        ],
    )
    assert server._resolve_bot_token() == ""


def test_whitespace_only_token_is_treated_as_missing(monkeypatch, reload_server):
    monkeypatch.setenv("SAPPHIRE_PM_BOT_TOKEN", "   ")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "real-fallback")
    server = reload_server()
    # Whitespace-only explicit should not mask the shared token
    assert server._resolve_bot_token() == "real-fallback"


def test_empty_secrets_file_skipped(monkeypatch, tmp_path, reload_server):
    fake_home = tmp_path
    sapphire_secrets = fake_home / ".config" / "sapphire-secrets"
    sapphire_secrets.mkdir(parents=True)
    empty_file = sapphire_secrets / "telegram_bot_token"
    empty_file.write_text("   \n")  # whitespace only

    sapphire_dir = fake_home / ".config" / "sapphire"
    sapphire_dir.mkdir(parents=True)
    (sapphire_dir / "telegram_bot_token").write_text("secondary-file-token")

    server = reload_server()
    from pathlib import Path as _Path

    monkeypatch.setattr(
        server,
        "_SECRET_PATHS",
        [
            _Path(fake_home) / ".config" / "sapphire-secrets" / "telegram_bot_token",
            _Path(fake_home) / ".config" / "sapphire" / "telegram_bot_token",
        ],
    )
    assert server._resolve_bot_token() == "secondary-file-token"


def test_redacts_telegram_token_from_error_text(monkeypatch, reload_server):
    fake_token = "1234567890:abcdefghijklmnopqrstuvwxyzABCDE"
    monkeypatch.setenv("SAPPHIRE_PM_BOT_TOKEN", fake_token)
    server = reload_server()

    unsafe = (
        "409 Client Error: Conflict for url: "
        f"https://api.telegram.org/bot{fake_token}/getUpdates"
    )

    safe = server._redact_sensitive_text(unsafe)
    assert fake_token not in safe
    assert "https://api.telegram.org/bot[REDACTED]/getUpdates" in safe


def test_health_reports_webhook_secret_configured(monkeypatch, reload_server):
    monkeypatch.setenv("SAPPHIRE_PM_BOT_TOKEN", "test-token")
    monkeypatch.setenv("SAPPHIRE_PM_BOT_WEBHOOK_SECRET", "test-webhook-secret")
    server = reload_server()

    with TestClient(server.app) as client:
        response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["webhook_secret_configured"] is True


def test_shared_webhook_secret_fallback(monkeypatch, reload_server):
    monkeypatch.setenv("SAPPHIRE_PM_BOT_TOKEN", "test-token")
    monkeypatch.setenv("TELEGRAM_WEBHOOK_SECRET", "shared-webhook-secret")
    server = reload_server()

    assert server.SETTINGS.webhook_secret == "shared-webhook-secret"


def test_webhook_secret_falls_back_to_secret_file(monkeypatch, tmp_path, reload_server):
    fake_home = tmp_path
    sapphire_secrets = fake_home / ".config" / "sapphire-secrets"
    sapphire_secrets.mkdir(parents=True)
    (sapphire_secrets / "telegram_webhook_secret").write_text("  file-webhook-secret  \n")

    monkeypatch.setenv("SAPPHIRE_PM_BOT_TOKEN", "test-token")
    server = reload_server()
    from pathlib import Path as _Path

    monkeypatch.setattr(
        server,
        "_WEBHOOK_SECRET_PATHS",
        [
            _Path(fake_home) / ".config" / "sapphire-secrets" / "sapphire_pm_bot_webhook_secret",
            _Path(fake_home) / ".config" / "sapphire-secrets" / "telegram_webhook_secret",
            _Path(fake_home) / ".config" / "sapphire" / "telegram_webhook_secret",
        ],
    )

    assert server._resolve_webhook_secret() == "file-webhook-secret"


def test_explicit_webhook_secret_wins_over_secret_file(monkeypatch, tmp_path, reload_server):
    fake_home = tmp_path
    sapphire_secrets = fake_home / ".config" / "sapphire-secrets"
    sapphire_secrets.mkdir(parents=True)
    (sapphire_secrets / "telegram_webhook_secret").write_text("file-webhook-secret")

    monkeypatch.setenv("SAPPHIRE_PM_BOT_TOKEN", "test-token")
    monkeypatch.setenv("SAPPHIRE_PM_BOT_WEBHOOK_SECRET", "env-webhook-secret")
    server = reload_server()
    from pathlib import Path as _Path

    monkeypatch.setattr(
        server,
        "_WEBHOOK_SECRET_PATHS",
        [
            _Path(fake_home) / ".config" / "sapphire-secrets" / "sapphire_pm_bot_webhook_secret",
            _Path(fake_home) / ".config" / "sapphire-secrets" / "telegram_webhook_secret",
            _Path(fake_home) / ".config" / "sapphire" / "telegram_webhook_secret",
        ],
    )

    assert server._resolve_webhook_secret() == "env-webhook-secret"


def test_webhook_rejects_bad_secret_before_json(monkeypatch, reload_server):
    monkeypatch.setenv("SAPPHIRE_PM_BOT_TOKEN", "test-token")
    monkeypatch.setenv("SAPPHIRE_PM_BOT_WEBHOOK_SECRET", "expected-secret")
    server = reload_server()
    calls = []

    def fail_process_update(update):
        calls.append(update)
        raise AssertionError("process_update should not run for bad secret")

    monkeypatch.setattr(server, "process_update", fail_process_update)

    with TestClient(server.app) as client:
        response = client.post(
            "/telegram/webhook",
            content=b"not-json",
            headers={"X-Telegram-Bot-Api-Secret-Token": "wrong-secret"},
        )

    assert response.status_code == 403
    assert response.json()["detail"] == "invalid secret"
    assert calls == []


def test_webhook_accepts_valid_secret_without_sending(monkeypatch, reload_server):
    monkeypatch.setenv("SAPPHIRE_PM_BOT_TOKEN", "test-token")
    monkeypatch.setenv("SAPPHIRE_PM_BOT_WEBHOOK_SECRET", "expected-secret")
    server = reload_server()
    calls = []

    def fake_process_update(update):
        calls.append(update)
        return True

    monkeypatch.setattr(server, "process_update", fake_process_update)
    update = {"message": {"chat": {"id": 123}, "text": "/help"}}

    with TestClient(server.app) as client:
        response = client.post(
            "/telegram/webhook",
            json=update,
            headers={"X-Telegram-Bot-Api-Secret-Token": "expected-secret"},
        )

    assert response.status_code == 200
    assert response.json() == {"ok": True, "processed": True}
    assert calls == [update]
