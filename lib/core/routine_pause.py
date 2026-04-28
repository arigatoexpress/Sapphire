"""Durable pause flags for scheduled Sapphire routines."""

from __future__ import annotations

import json
import re
import sys
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

PAUSE_DIR = Path.home() / ".sapphire" / "routine_pause"
_ROUTINE_NAME_RE = re.compile(r"^[a-zA-Z0-9_-]+$")


@dataclass(frozen=True)
class RoutinePause:
    """Paste-safe metadata for a routine pause flag."""

    name: str
    paused_at: str


def _pause_flag(name: str, *, pause_dir: Path | None = None) -> Path:
    if not _ROUTINE_NAME_RE.fullmatch(name):
        raise ValueError(f"invalid routine name: {name!r}")
    return (pause_dir or PAUSE_DIR) / name


def is_paused(name: str, *, pause_dir: Path | None = None) -> bool:
    """Return whether a valid routine name has an active pause flag."""
    try:
        return _pause_flag(name, pause_dir=pause_dir).exists()
    except OSError:
        return False


def _flag_timestamp(path: Path) -> str:
    """Return the persisted pause timestamp or a stable mtime fallback."""
    try:
        first_line = path.read_text(encoding="utf-8").splitlines()[0].strip()
    except (OSError, IndexError, UnicodeDecodeError):
        first_line = ""
    if first_line:
        return first_line
    try:
        return (
            datetime.fromtimestamp(path.stat().st_mtime, tz=UTC)
            .replace(microsecond=0)
            .isoformat()
        )
    except OSError:
        return "unknown"


def list_paused(*, pause_dir: Path | None = None) -> list[RoutinePause]:
    """Return valid routine pause flags sorted by routine name.

    Invalid filenames are ignored so a stray editor backup or path traversal
    probe cannot become user-visible status output.
    """
    try:
        entries = sorted((pause_dir or PAUSE_DIR).iterdir(), key=lambda item: item.name)
    except OSError:
        return []

    rows: list[RoutinePause] = []
    for entry in entries:
        if not entry.is_file():
            continue
        if not _ROUTINE_NAME_RE.fullmatch(entry.name):
            continue
        rows.append(RoutinePause(name=entry.name, paused_at=_flag_timestamp(entry)))
    return rows


def abort_if_paused(name: str, *, log: Callable[[str], object] = print) -> None:
    """Exit successfully when a scheduled routine has been paused."""
    flag = _pause_flag(name)
    try:
        paused = flag.exists()
    except OSError:
        paused = False
    if not paused:
        return
    log(
        json.dumps(
            {
                "event": "routine_pause.skipped",
                "routine": name,
                "pause_flag": str(flag),
            },
            sort_keys=True,
        )
    )
    sys.exit(0)
