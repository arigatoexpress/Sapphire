"""Task 105 regression proof for control-plane Telegram authority retirement."""

from __future__ import annotations

import ast
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MAIN = ROOT / "services" / "control-plane" / "app" / "main.py"
FRONTEND = ROOT / "services" / "control-plane" / "app" / "frontend"
CONTROL_PLANE = ROOT / "services" / "control-plane"


def _scoped_sources() -> dict[Path, str]:
    suffixes = {".py", ".js", ".html", ".md", ".json", ".example"}
    return {
        path: path.read_text(encoding="utf-8")
        for path in CONTROL_PLANE.rglob("*")
        if path.is_file()
        and "__pycache__" not in path.parts
        and (path.suffix in suffixes or path.name == ".env.example")
    }


def _route_function() -> ast.AsyncFunctionDef:
    tree = ast.parse(MAIN.read_text(encoding="utf-8"))
    return next(
        node
        for node in tree.body
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "telegram_webhook"
    )


def test_telegram_webhook_is_unconditional_constant_refusal():
    function = _route_function()
    source = ast.unparse(function)

    assert "request.json" not in source
    assert "append_event" not in source
    assert "log." not in source
    assert "get_settings" not in source
    assert "HTTPException" not in source
    assert "REFUSED_TELEGRAM_HAS_NO_AUTHORITY" in source
    assert "'authority': 'NONE'" in source
    assert "'mutation_allowed': False" in source


def test_control_plane_never_registers_or_owns_a_telegram_webhook():
    source = MAIN.read_text(encoding="utf-8")

    assert "set_webhook(" not in source
    assert "TelegramClient" not in source
    assert "STARTUP_REGISTER_WEBHOOK" not in source
    assert "telegram.message" not in source


def test_visible_control_plane_claims_are_notification_only():
    paths = [
        MAIN,
        ROOT / "services" / "control-plane" / "SKILL.md",
        ROOT / "services" / "control-plane" / ".env.example",
        FRONTEND / "index.html",
        FRONTEND / "assets" / "app.js",
        FRONTEND / "assets" / "architecture.js",
        FRONTEND / "assets" / "secops.js",
    ]
    visible = "\n".join(path.read_text(encoding="utf-8") for path in paths)

    assert "Telegram commands or text" not in visible
    assert "Prompt surface locked to Telegram" not in visible
    assert '"command_channel": "telegram"' not in visible
    assert '"control_channel": "telegram"' not in visible
    assert "Telegram notification-only" in visible


def test_recursive_inventory_has_no_telegram_command_or_client_authority():
    sources = _scoped_sources()
    combined = "\n".join(sources.values()).lower()

    for forbidden in (
        "telegram control",
        "telegram command",
        "telegram-first task",
        "telegram agents",
        "secure telegram control",
        "exclusive command",
        "operator steering channel",
        "api.telegram.org",
        "sendmessage",
        "setwebhook",
        "telegram_bot_token",
        "telegram_webhook_secret",
        "allowed_telegram_user_ids",
        "allowed_telegram_chat_ids",
        "startup_register_webhook",
    ):
        assert forbidden not in combined


def test_recursive_frontend_has_no_inbound_telegram_edge_or_command_palette():
    frontend_source = "\n".join(
        text for path, text in _scoped_sources().items() if FRONTEND in path.parents
    )
    assert (
        re.search(
            r"(?:TG|TEL)\[[^\n]*Telegram[^\n]*\]\s*-->\s*(?:HUB|RUN|CONTROL)",
            frontend_source,
            flags=re.IGNORECASE,
        )
        is None
    )
    for forbidden in (
        "Telegram Command Palette",
        'id="command-grid"',
        'data-copy="/',
        'id="control-channel">telegram',
        'data.control_channel || "telegram"',
        "Morning Briefing → Telegram",
        "Evening Digest → Telegram",
        "Health Alerts → Telegram",
    ):
        assert forbidden not in frontend_source


def test_dormant_config_and_api_authority_are_removed():
    config_tree = ast.parse((CONTROL_PLANE / "app" / "config.py").read_text(encoding="utf-8"))
    settings = next(
        node
        for node in config_tree.body
        if isinstance(node, ast.ClassDef) and node.name == "Settings"
    )
    fields = {
        node.target.id
        for node in settings.body
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name)
    }
    assert fields.isdisjoint(
        {
            "telegram_bot_token",
            "telegram_webhook_secret",
            "startup_register_webhook",
            "allowed_telegram_user_ids",
            "allowed_telegram_chat_ids",
        }
    )

    api_path = CONTROL_PLANE / "app" / "telegram_api.py"
    if api_path.exists():
        api = api_path.read_text(encoding="utf-8").lower()
        for forbidden in (
            "telegramclient",
            "bot_token",
            "api.telegram.org",
            "sendmessage",
            "setwebhook",
        ):
            assert forbidden not in api


def test_main_ui_state_is_not_derived_from_telegram_identity_allowlists():
    source = MAIN.read_text(encoding="utf-8")
    assert "allowed_telegram" not in source
    assert '"allowlist_enabled":' not in source
    assert '"control_channel": "owner_secure_review"' in source
