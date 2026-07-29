"""Task 105 regression proof for control-plane Telegram authority retirement."""

from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MAIN = ROOT / "services" / "control-plane" / "app" / "main.py"
FRONTEND = ROOT / "services" / "control-plane" / "app" / "frontend"


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
