#!/usr/bin/env python3
"""Register Sapphire's modern command set with Telegram (BotFather side).

The user's Telegram client caches whatever commands the bot last registered
via ``setMyCommands``. Old deployments left leftovers like ``/bots``,
``/pending``, ``/skin``, ``/tracks``, ``/shield`` in the "menu" ReplyKeyboard
long after PR #975 replaced them with an inline console. The bot code no
longer knows about those names — but Telegram does, until we tell it not to.

This script does one thing: assemble the modern command list and push it
via the Bot API's ``setMyCommands`` endpoint. It also supports ``--clear``
to wipe the registered list entirely (useful when we want the client to
show *no* command hints and drive everything through ``/menu``).

Read-only by default. Actual mutation requires both ``--apply`` and the
``SAPPHIRE_PM_BOT_COMMANDS_APPLY=1`` env gate — the double lock matches
every other outward-mutation script in the tree (``setup_telegram_webhook``,
``deploy_robinhood_chain``, …).

Usage::

    python3 scripts/ops/setup_telegram_commands.py                # dry-run diff
    python3 scripts/ops/setup_telegram_commands.py --apply        # register
    python3 scripts/ops/setup_telegram_commands.py --clear --apply  # wipe

Token resolution mirrors the PM bot: SAPPHIRE_PM_BOT_TOKEN >
TELEGRAM_BOT_TOKEN > ~/.config/sapphire-secrets/telegram_bot_token.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Any

# The modern lean command set — matches what the pm-bot dispatcher in
# plugins/claw-sapphire/tools/sapphire_pm_bot.py actually implements.
# Every entry here has a live handler; the client can trust the hint.
#
# Ordered by likely tap frequency, capped at 12 (Telegram's practical limit
# before the menu becomes noise).
DEFAULT_COMMANDS: list[dict[str, str]] = [
    {"command": "menu", "description": "🏠 Interactive home"},
    {"command": "portfolio", "description": "📊 Portfolio + 24h moves"},
    {"command": "signals", "description": "📈 Active signals + accuracy"},
    {"command": "security", "description": "🔒 Threats + kill switch"},
    {"command": "brief", "description": "📰 Today's intelligence brief"},
    {"command": "reports", "description": "📋 Drafts + ready queue"},
    {"command": "status", "description": "🔄 Services + regime + F&G"},
    {"command": "settings", "description": "⚙️ Heartbeat + alert prefs"},
    {"command": "health", "description": "🩺 Deep service probe"},
    {"command": "help", "description": "❓ Command reference"},
]

# Old commands we've seen cached client-side that should NEVER re-appear.
# We assert none of them accidentally slip into DEFAULT_COMMANDS — the
# assertion runs even on a dry-run so drift is caught in CI.
DEPRECATED: frozenset[str] = frozenset(
    {
        "bots",
        "pending",
        "skin",
        "tracks",
        "shield",
        "summary",
        "digest",  # legacy top-level; still reachable as `/digest morning|dev`
    }
)

TELEGRAM_API_BASE = "https://api.telegram.org/bot"

_TOKEN_ENV_VARS = ("SAPPHIRE_PM_BOT_TOKEN", "TELEGRAM_BOT_TOKEN")
_TOKEN_SECRET_PATHS = [
    Path.home() / ".config" / "sapphire-secrets" / "telegram_bot_token",
    Path.home() / ".config" / "sapphire" / "telegram_bot_token",
]

# BotFather constraint: command names lower-case, 1-32 chars, alnum+underscore.
_COMMAND_RE = re.compile(r"^[a-z0-9_]{1,32}$")


# ---------------------------------------------------------------------------
# Pure helpers (unit-testable)
# ---------------------------------------------------------------------------


def resolve_token() -> tuple[str, str]:
    """Return ``(token, source)`` using the PM bot's precedence order."""
    for env in _TOKEN_ENV_VARS:
        value = os.environ.get(env, "").strip()
        if value:
            return value, env
    for path in _TOKEN_SECRET_PATHS:
        try:
            if path.exists():
                contents = path.read_text().strip()
                if contents:
                    return contents, str(path)
        except OSError:
            continue
    return "", "missing"


def validate_commands(commands: list[dict[str, str]]) -> list[str]:
    """Return a list of validation errors; empty means the payload is safe.

    Enforces BotFather's shape (name pattern + description length) plus our
    own deprecation guard. Called on every run — even ``--dry-run`` — so a
    typo can't silently regress the client's menu.
    """
    errors: list[str] = []
    seen: set[str] = set()
    for i, item in enumerate(commands):
        if not isinstance(item, dict):
            errors.append(f"[{i}] not a dict: {item!r}")
            continue
        # BotFather rejects any character outside lowercase alnum + underscore.
        # Don't silently lowercase — if we canonicalize, drift ("Menu" vs
        # "menu") sneaks through, and Telegram then returns a 400 that's a
        # nightmare to trace back to this file.
        name = str(item.get("command", ""))
        desc = str(item.get("description", ""))
        if not _COMMAND_RE.match(name):
            errors.append(f"[{i}] bad command name: {name!r} (must match {_COMMAND_RE.pattern})")
        if name.lower() in DEPRECATED:
            errors.append(f"[{i}] deprecated command re-introduced: /{name}")
        if name in seen:
            errors.append(f"[{i}] duplicate command: /{name}")
        seen.add(name)
        if not desc:
            errors.append(f"[{i}] empty description for /{name}")
        if len(desc) > 256:
            errors.append(f"[{i}] description > 256 chars for /{name}")
    if len(commands) > 100:
        errors.append(f"too many commands: {len(commands)} (Telegram cap 100)")
    return errors


def build_set_commands_payload(
    commands: list[dict[str, str]],
    *,
    language_code: str = "",
    scope: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build the ``setMyCommands`` request body.

    ``scope`` and ``language_code`` are Telegram's optional narrowing keys —
    left absent by default so the payload registers as the fleet-wide
    default. Passing a scope lets us later carve out chat-specific
    overrides without changing this function.
    """
    payload: dict[str, Any] = {"commands": commands}
    if language_code:
        payload["language_code"] = language_code
    if scope:
        payload["scope"] = scope
    return payload


def summarize_diff(current: list[dict[str, str]], desired: list[dict[str, str]]) -> str:
    """Human-readable diff between what's registered and what we'd push."""
    current_by_name = {c["command"]: c.get("description", "") for c in current}
    desired_by_name = {c["command"]: c.get("description", "") for c in desired}

    added = sorted(set(desired_by_name) - set(current_by_name))
    removed = sorted(set(current_by_name) - set(desired_by_name))
    changed = sorted(
        n
        for n in set(desired_by_name) & set(current_by_name)
        if desired_by_name[n] != current_by_name[n]
    )

    lines = []
    if not (added or removed or changed):
        lines.append("(no changes — bot already has the desired command set)")
    else:
        for n in added:
            lines.append(f"  + /{n} — {desired_by_name[n]}")
        for n in removed:
            lines.append(f"  - /{n} — {current_by_name[n]}")
        for n in changed:
            lines.append(f"  ~ /{n}: {current_by_name[n]!r} → {desired_by_name[n]!r}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Telegram Bot API
# ---------------------------------------------------------------------------


def _telegram_api_call(
    token: str,
    method: str,
    payload: dict[str, Any] | None = None,
    *,
    timeout: float = 10.0,
) -> dict[str, Any]:
    """POST to Bot API. Raises RuntimeError on non-ok response."""
    import urllib.error
    import urllib.request

    url = f"{TELEGRAM_API_BASE}{token}/{method}"
    body = json.dumps(payload or {}).encode("utf-8")
    request = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            data = json.loads(response.read())
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:400]
        raise RuntimeError(f"{method} HTTP {exc.code}: {detail}") from exc
    if not data.get("ok"):
        raise RuntimeError(f"{method} returned not-ok: {data}")
    return data.get("result", {})


def get_current_commands(token: str, *, timeout: float = 10.0) -> list[dict[str, str]]:
    """Return the currently registered default-scope commands."""
    result = _telegram_api_call(token, "getMyCommands", {}, timeout=timeout)
    if isinstance(result, list):
        return [c for c in result if isinstance(c, dict)]
    return []


def push_commands(
    token: str,
    commands: list[dict[str, str]],
    *,
    timeout: float = 10.0,
) -> dict[str, Any]:
    """setMyCommands. ``commands=[]`` clears the registration."""
    payload = build_set_commands_payload(commands)
    return _telegram_api_call(token, "setMyCommands", payload, timeout=timeout)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _redact_token(text: str, token: str) -> str:
    if not token:
        return text
    return text.replace(token, "[REDACTED_TELEGRAM_TOKEN]")


def _apply_gate_open() -> bool:
    return os.environ.get("SAPPHIRE_PM_BOT_COMMANDS_APPLY", "").strip() in {"1", "true", "yes"}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Actually call setMyCommands. Also requires SAPPHIRE_PM_BOT_COMMANDS_APPLY=1.",
    )
    parser.add_argument(
        "--clear",
        action="store_true",
        help="Push an empty command list — Telegram will erase the menu.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit machine-readable output on stdout (still logs to stderr).",
    )
    args = parser.parse_args(argv)

    desired = [] if args.clear else DEFAULT_COMMANDS

    # Validate before we ever touch the network.
    errors = validate_commands(desired) if desired else []
    if errors:
        for err in errors:
            print(f"error: {err}", file=sys.stderr)
        return 2

    token, source = resolve_token()
    if not token:
        print(
            "error: no Telegram bot token found. Set SAPPHIRE_PM_BOT_TOKEN or "
            "TELEGRAM_BOT_TOKEN, or drop the token at "
            "~/.config/sapphire-secrets/telegram_bot_token.",
            file=sys.stderr,
        )
        return 2

    # Read what's currently registered so we can print a real diff.
    try:
        current = get_current_commands(token)
    except Exception as exc:
        print(f"error: getMyCommands failed: {_redact_token(str(exc), token)}", file=sys.stderr)
        return 3

    print(f"Token source: {source}", file=sys.stderr)
    print(
        f"Current registration: {len(current)} command(s)",
        file=sys.stderr,
    )
    print(
        f"Desired registration: {len(desired)} command(s)" + (" (CLEAR)" if args.clear else ""),
        file=sys.stderr,
    )
    print("Diff:", file=sys.stderr)
    print(summarize_diff(current, desired), file=sys.stderr)

    output: dict[str, Any] = {
        "token_source": source,
        "current": current,
        "desired": desired,
        "would_apply": bool(args.apply),
        "apply_gate_open": _apply_gate_open(),
        "clear": bool(args.clear),
        "applied": False,
    }

    if not args.apply:
        output["dry_run_reason"] = "no --apply flag"
        if args.json:
            print(json.dumps(output, indent=2))
        else:
            print("dry-run — pass --apply and SAPPHIRE_PM_BOT_COMMANDS_APPLY=1 to push")
        return 0

    if not _apply_gate_open():
        output["dry_run_reason"] = "SAPPHIRE_PM_BOT_COMMANDS_APPLY env gate closed"
        print(
            "error: --apply requires SAPPHIRE_PM_BOT_COMMANDS_APPLY=1 as a "
            "second-key mutation gate. Not calling setMyCommands.",
            file=sys.stderr,
        )
        if args.json:
            print(json.dumps(output, indent=2))
        return 2

    try:
        result = push_commands(token, desired)
    except Exception as exc:
        print(f"error: setMyCommands failed: {_redact_token(str(exc), token)}", file=sys.stderr)
        output["error"] = _redact_token(str(exc), token)
        if args.json:
            print(json.dumps(output, indent=2))
        return 3

    output["applied"] = True
    output["telegram_response"] = result
    if args.json:
        print(json.dumps(output, indent=2))
    else:
        print(f"OK: setMyCommands accepted ({len(desired)} command(s) registered)")
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
