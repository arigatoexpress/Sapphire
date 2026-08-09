"""User-editable Telegram settings for Sapphire.

The pm-bot's ``⚙️ Settings`` inline menu writes to a small JSON file so
scheduled tasks (like the heartbeat LaunchAgent) can pick up the same
config without needing a live IPC channel.

File format::

    {
      "heartbeat_enabled": true,
      "heartbeat_hours": 4,
      "updated_at": "2026-07-25T18:00:00+00:00"
    }

The default location is ``~/.config/sapphire/telegram_settings.json``.
Override with ``SAPPHIRE_TELEGRAM_SETTINGS_PATH`` for tests.
"""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import asdict, dataclass, replace
from datetime import UTC, datetime
from pathlib import Path

DEFAULT_HEARTBEAT_HOURS = 4
_VALID_HOURS = {4, 12, 24}


@dataclass(frozen=True)
class TelegramSettings:
    heartbeat_enabled: bool = False
    heartbeat_hours: int = DEFAULT_HEARTBEAT_HOURS
    updated_at: str = ""

    def with_change(self, **kwargs) -> TelegramSettings:
        merged = replace(self, **kwargs)
        return replace(merged, updated_at=datetime.now(UTC).isoformat())


def default_path() -> Path:
    override = os.environ.get("SAPPHIRE_TELEGRAM_SETTINGS_PATH", "").strip()
    if override:
        return Path(override).expanduser()
    return Path.home() / ".config" / "sapphire" / "telegram_settings.json"


def load(path: Path | None = None) -> TelegramSettings:
    """Load settings; returns defaults on missing/corrupt file."""
    target = path or default_path()
    try:
        raw = target.read_text()
    except FileNotFoundError:
        return TelegramSettings()
    except OSError:
        return TelegramSettings()
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return TelegramSettings()
    if not isinstance(payload, dict):
        return TelegramSettings()

    hours_raw = payload.get("heartbeat_hours", DEFAULT_HEARTBEAT_HOURS)
    try:
        hours = int(hours_raw)
    except (TypeError, ValueError):
        hours = DEFAULT_HEARTBEAT_HOURS
    if hours not in _VALID_HOURS:
        hours = DEFAULT_HEARTBEAT_HOURS

    return TelegramSettings(
        heartbeat_enabled=bool(payload.get("heartbeat_enabled", False)),
        heartbeat_hours=hours,
        updated_at=str(payload.get("updated_at") or ""),
    )


def save(settings: TelegramSettings, path: Path | None = None) -> Path:
    """Atomically write the settings file (parents auto-created, 0600 mode)."""
    target = path or default_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    stamped = settings if settings.updated_at else settings.with_change()
    fd, tmp_name = tempfile.mkstemp(dir=target.parent, prefix=".telegram_settings.", suffix=".tmp")
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "w") as handle:
            json.dump(asdict(stamped), handle, indent=2, sort_keys=True)
            handle.write("\n")
        os.chmod(tmp_path, 0o600)
        os.replace(tmp_path, target)
    finally:
        if tmp_path.exists():
            try:
                tmp_path.unlink()
            except OSError:
                pass
    return target


def apply_change(action: str, path: Path | None = None) -> TelegramSettings:
    """Interpret a menu-driven change and persist it.

    Accepted actions::

        "on" | "off"
        "4h" | "12h" | "1d"
    """
    current = load(path)
    if action == "on":
        updated = current.with_change(heartbeat_enabled=True)
    elif action == "off":
        updated = current.with_change(heartbeat_enabled=False)
    elif action == "4h":
        updated = current.with_change(heartbeat_hours=4)
    elif action == "12h":
        updated = current.with_change(heartbeat_hours=12)
    elif action == "1d":
        updated = current.with_change(heartbeat_hours=24)
    else:
        return current
    save(updated, path)
    return updated


__all__ = [
    "DEFAULT_HEARTBEAT_HOURS",
    "TelegramSettings",
    "apply_change",
    "default_path",
    "load",
    "save",
]
