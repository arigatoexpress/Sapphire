"""Tests for _resolve_bot_token in services/pm_bot/server.py."""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

SERVICES_DIR = Path(__file__).resolve().parent
if str(SERVICES_DIR) not in sys.path:
    sys.path.insert(0, str(SERVICES_DIR))


@pytest.fixture
def reload_server(monkeypatch):
    """Reload services.pm_bot.server fresh so module-level SETTINGS rebuilds."""
    # Clear any cached module so from_env runs fresh under the monkeypatched env
    monkeypatch.delenv("SAPPHIRE_PM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
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
        server, "_SECRET_PATHS",
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
        server, "_SECRET_PATHS",
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
        server, "_SECRET_PATHS",
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
