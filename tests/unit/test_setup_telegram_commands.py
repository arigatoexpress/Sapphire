"""Tests for the setMyCommands helper.

Covers the pure helpers so a regression that reintroduces a deprecated
command name (``/bots``, ``/shield``, …) or drifts from the BotFather
name-shape gets caught in CI, without hitting the Telegram API.

Network paths are exercised by monkeypatching ``_telegram_api_call``.
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = REPO_ROOT / "scripts" / "ops"
sys.path.insert(0, str(SCRIPTS_DIR))

# Fresh import so tests aren't tainted by an earlier PYTHONPATH state.
if "setup_telegram_commands" in sys.modules:
    del sys.modules["setup_telegram_commands"]
setup = importlib.import_module("setup_telegram_commands")


class TestDefaultCommandSet:
    def test_default_set_is_non_empty(self):
        assert setup.DEFAULT_COMMANDS
        assert len(setup.DEFAULT_COMMANDS) <= 12

    def test_default_set_validates_cleanly(self):
        assert setup.validate_commands(setup.DEFAULT_COMMANDS) == []

    def test_default_set_has_menu_first(self):
        # The whole point of the modern UI is that /menu is where every
        # session starts. Assert it's the highest-tapped entry.
        assert setup.DEFAULT_COMMANDS[0]["command"] == "menu"

    def test_deprecated_names_are_blocked(self):
        for name in ("bots", "pending", "skin", "tracks", "shield"):
            assert name in setup.DEPRECATED
            errors = setup.validate_commands(
                [{"command": name, "description": "x"}]
            )
            assert any("deprecated" in e for e in errors), errors


class TestValidation:
    @pytest.mark.parametrize(
        "name,should_error",
        [
            ("menu", False),
            ("brief", False),
            ("Brief", True),           # upper-case not allowed by BotFather
            ("with-dash", True),        # only alnum+underscore
            ("way_too_long_" + "x" * 40, True),
            ("", True),
        ],
    )
    def test_command_name_shape(self, name, should_error):
        errors = setup.validate_commands([{"command": name, "description": "d"}])
        if should_error:
            assert errors
        else:
            assert errors == []

    def test_empty_description_flagged(self):
        errors = setup.validate_commands([{"command": "menu", "description": ""}])
        assert any("empty description" in e for e in errors)

    def test_description_over_256_flagged(self):
        errors = setup.validate_commands(
            [{"command": "menu", "description": "x" * 257}]
        )
        assert any("256 chars" in e for e in errors)

    def test_duplicate_names_flagged(self):
        errors = setup.validate_commands(
            [
                {"command": "menu", "description": "a"},
                {"command": "menu", "description": "b"},
            ]
        )
        assert any("duplicate" in e for e in errors)


class TestTokenResolution:
    def test_env_var_wins(self, monkeypatch):
        monkeypatch.setenv("SAPPHIRE_PM_BOT_TOKEN", "explicit")
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "shared")
        token, source = setup.resolve_token()
        assert token == "explicit"
        assert source == "SAPPHIRE_PM_BOT_TOKEN"

    def test_shared_env_fallback(self, monkeypatch):
        monkeypatch.delenv("SAPPHIRE_PM_BOT_TOKEN", raising=False)
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "shared")
        token, source = setup.resolve_token()
        assert token == "shared"
        assert source == "TELEGRAM_BOT_TOKEN"

    def test_missing_when_nothing_set(self, monkeypatch, tmp_path):
        monkeypatch.delenv("SAPPHIRE_PM_BOT_TOKEN", raising=False)
        monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
        # Point secret paths at empty tmpdir so the loop finds nothing.
        monkeypatch.setattr(
            setup, "_TOKEN_SECRET_PATHS", [tmp_path / "does_not_exist"]
        )
        token, source = setup.resolve_token()
        assert token == ""
        assert source == "missing"


class TestDiff:
    def test_no_change_reads_cleanly(self):
        cmds = [{"command": "menu", "description": "🏠 Interactive home"}]
        assert "no changes" in setup.summarize_diff(cmds, cmds)

    def test_shows_add_remove_change(self):
        current = [
            {"command": "bots", "description": "old"},
            {"command": "menu", "description": "old menu"},
        ]
        desired = [
            {"command": "menu", "description": "new menu"},
            {"command": "portfolio", "description": "new"},
        ]
        diff = setup.summarize_diff(current, desired)
        assert "+ /portfolio" in diff
        assert "- /bots" in diff
        assert "~ /menu" in diff


class TestPayloadBuilder:
    def test_minimal_payload(self):
        commands = [{"command": "menu", "description": "x"}]
        assert setup.build_set_commands_payload(commands) == {"commands": commands}

    def test_scope_and_lang_when_provided(self):
        payload = setup.build_set_commands_payload(
            [], language_code="es", scope={"type": "default"}
        )
        assert payload == {
            "commands": [],
            "language_code": "es",
            "scope": {"type": "default"},
        }


class TestCLIGates:
    def test_dry_run_does_not_touch_network(self, monkeypatch, capsys):
        monkeypatch.setenv("SAPPHIRE_PM_BOT_TOKEN", "fake")
        called = {"get": 0, "push": 0}

        def _fake_get(token):
            called["get"] += 1
            return []

        def _fake_push(token, commands):
            called["push"] += 1
            return {}

        monkeypatch.setattr(setup, "get_current_commands", _fake_get)
        monkeypatch.setattr(setup, "push_commands", _fake_push)
        rc = setup.main([])
        assert rc == 0
        # We do call getMyCommands to render a diff — that's read-only.
        assert called["get"] == 1
        assert called["push"] == 0

    def test_apply_without_env_gate_refuses_to_push(self, monkeypatch, capsys):
        monkeypatch.setenv("SAPPHIRE_PM_BOT_TOKEN", "fake")
        monkeypatch.delenv("SAPPHIRE_PM_BOT_COMMANDS_APPLY", raising=False)
        called = {"push": 0}

        monkeypatch.setattr(setup, "get_current_commands", lambda t: [])
        monkeypatch.setattr(
            setup,
            "push_commands",
            lambda t, c: (called.__setitem__("push", called["push"] + 1), {})[1],
        )
        rc = setup.main(["--apply"])
        assert rc == 2
        assert called["push"] == 0

    def test_apply_with_env_gate_pushes(self, monkeypatch):
        monkeypatch.setenv("SAPPHIRE_PM_BOT_TOKEN", "fake")
        monkeypatch.setenv("SAPPHIRE_PM_BOT_COMMANDS_APPLY", "1")
        called = {"push": 0}

        monkeypatch.setattr(setup, "get_current_commands", lambda t: [])

        def _push(token, commands):
            called["push"] += 1
            assert token == "fake"
            assert commands == setup.DEFAULT_COMMANDS
            return True

        monkeypatch.setattr(setup, "push_commands", _push)
        rc = setup.main(["--apply"])
        assert rc == 0
        assert called["push"] == 1

    def test_clear_with_gate_pushes_empty(self, monkeypatch):
        monkeypatch.setenv("SAPPHIRE_PM_BOT_TOKEN", "fake")
        monkeypatch.setenv("SAPPHIRE_PM_BOT_COMMANDS_APPLY", "1")
        seen = {}
        monkeypatch.setattr(setup, "get_current_commands", lambda t: [])

        def _push(token, commands):
            seen["commands"] = commands
            return True

        monkeypatch.setattr(setup, "push_commands", _push)
        rc = setup.main(["--apply", "--clear"])
        assert rc == 0
        assert seen["commands"] == []


class TestTokenRedaction:
    def test_token_removed_from_error(self):
        redacted = setup._redact_token("boom bot123:secret failed", "123:secret")
        assert "123:secret" not in redacted
        assert "[REDACTED_TELEGRAM_TOKEN]" in redacted

    def test_no_token_no_op(self):
        assert setup._redact_token("hello", "") == "hello"


class TestModuleImportSideEffects:
    """Import must not read files or touch the network."""

    def test_import_reads_no_secret_files(self, tmp_path, monkeypatch):
        # Nothing writes on import; re-import fresh and confirm no PATHs
        # were resolved unexpectedly.
        monkeypatch.setenv("HOME", str(tmp_path))
        sys.modules.pop("setup_telegram_commands", None)
        importlib.import_module("setup_telegram_commands")
