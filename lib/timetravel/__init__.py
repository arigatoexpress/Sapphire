"""Sapphire Time-Travel + Replay capability.

Read-only over append-only JSONL artifacts under ``data/`` so the
operator can ask: "what did Sapphire think at time T?" and "what would
Sapphire produce at time T given today's code?"

The package is split into three deliberately small modules:

- :mod:`lib.timetravel.snapshot` builds an interval index over the
  append-only time series and packages a ``SystemSnapshot`` for a
  given UTC timestamp. The index is cached at
  ``~/.cache/sapphire/timetravel/index.json`` and is idempotent.
- :mod:`lib.timetravel.replay` re-invokes the correlator + narrative
  engines on the snapshot data, returning a ``ReplayResult`` that
  represents "what current code would produce". It never writes back
  to ``data/`` and never re-emits trades, alerts, or events.
- :mod:`lib.timetravel.diff` compares the on-disk artifact ("what was
  actually produced at T") with the replay result ("what would be
  produced at T given current code"), surfacing drift on a small
  set of well-defined fields.

UTC discipline: every datetime crossing a public boundary is timezone-
aware UTC. Any naive datetime supplied by a caller is treated as UTC
and re-tagged before use. Storage timestamps are ISO-8601 with the
``+00:00`` offset.

Trading critical path: time-travel is a read-only research tool. It
does not place orders, does not send Telegram messages, does not
publish to the event bus, and does not modify ``data/``. Replays are
held strictly in memory.
"""

from __future__ import annotations

from lib.timetravel.diff import (
    DiffResult,
    SignalDiff,
    diff_actual_vs_replay,
)
from lib.timetravel.replay import (
    ReplayResult,
    replay,
)
from lib.timetravel.snapshot import (
    DEFAULT_SCOPE,
    INDEX_PATH,
    SCOPE_TO_ROOT,
    SnapshotEntry,
    SystemSnapshot,
    build_index,
    index_status,
    load_index,
    take_snapshot,
)

__all__ = [
    "DEFAULT_SCOPE",
    "INDEX_PATH",
    "SCOPE_TO_ROOT",
    "DiffResult",
    "ReplayResult",
    "SignalDiff",
    "SnapshotEntry",
    "SystemSnapshot",
    "build_index",
    "diff_actual_vs_replay",
    "index_status",
    "load_index",
    "replay",
    "take_snapshot",
]

VERSION = "0.1.0"
GENERATOR = "lib.timetravel"
