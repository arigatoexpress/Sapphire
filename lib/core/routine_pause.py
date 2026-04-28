"""Durable pause flags for scheduled Sapphire routines."""

from __future__ import annotations

import json
import re
import sys
from collections.abc import Callable
from pathlib import Path

PAUSE_DIR = Path.home() / ".sapphire" / "routine_pause"
_ROUTINE_NAME_RE = re.compile(r"^[a-zA-Z0-9_-]+$")


def _pause_flag(name: str) -> Path:
    if not _ROUTINE_NAME_RE.fullmatch(name):
        raise ValueError(f"invalid routine name: {name!r}")
    return PAUSE_DIR / name


def is_paused(name: str) -> bool:
    """Return whether a valid routine name has an active pause flag."""
    try:
        return _pause_flag(name).exists()
    except OSError:
        return False


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
