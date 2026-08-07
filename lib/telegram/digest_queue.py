"""Batching queue for non-critical Telegram alerts.

The spec was blunt: **only critical events (kill switch, regime shift,
>5% moves) should fire individual Telegram messages. Everything else
batches into a morning or evening digest.** The user's screenshot
showed 5,893 unread messages — proof of the failure mode this module
prevents.

Design:

* Producers call :func:`enqueue` with (kind, body, priority). The record
  is appended to a JSONL journal at
  ``~/.cache/sapphire/telegram/digest_queue.jsonl``.
* :func:`flush_digest` reads the journal, groups records by kind, drops
  entries older than ``max_age_hours``, formats one MarkdownV2 message,
  archives the drained lines, and returns the formatted text (or
  ``None`` when there was nothing to send).
* The heartbeat / morning-brief scheduler shells this and pipes the
  result through ``notify.py`` — same live-send gate every other
  outbound message respects.

The journal survives crashes (append-only, atomic-ish rename on
archive) and is bounded (``MAX_ENTRIES`` lines) so a producer stuck in a
loop can't fill the disk. Records older than ``MAX_AGE_HOURS`` are
dropped on read (not batched into the next digest — they'd be stale
noise by then, exactly what this file exists to prevent).

Priority mapping (matches ``lib.telegram.alerts``):

    p1 → NOT queued here. Producer sends immediately via the alert path.
    p2 → queued with severity "warn"
    p3 → queued with severity "info"

This module never dispatches on its own. The one-way flow (append here,
drain via scheduler) keeps the outbound-send gate visible in exactly
one place upstream.
"""

from __future__ import annotations

import json
import logging
import os
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from lib.telegram import formatters as fmt

logger = logging.getLogger(__name__)

DEFAULT_JOURNAL = Path.home() / ".cache" / "sapphire" / "telegram" / "digest_queue.jsonl"
ARCHIVE_DIR = Path.home() / ".cache" / "sapphire" / "telegram" / "digest_archive"

# Hard bounds: past these we're wasting disk on stale noise.
MAX_ENTRIES = 2048
MAX_AGE_HOURS = 24

_ALLOWED_PRIORITIES: frozenset[str] = frozenset({"p2", "p3"})


@dataclass(frozen=True)
class DigestEntry:
    """One queued line, JSON-serializable via ``asdict``."""

    ts: str  # ISO8601 UTC
    kind: str  # e.g. "portfolio_mover", "signal", "chain_delta"
    body: str  # short, one-line summary — NOT pre-escaped
    priority: str  # "p2" | "p3"
    metadata: dict = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def enqueue(
    *,
    kind: str,
    body: str,
    priority: str = "p3",
    metadata: dict | None = None,
    journal: Path | None = None,
    now: datetime | None = None,
) -> bool:
    """Append one non-critical alert to the digest queue.

    Returns ``True`` on write, ``False`` when the entry was rejected
    (invalid priority, empty body, over the hard cap). Never raises —
    the queue must never be a producer-crash surface.

    ``journal`` defaults to :data:`DEFAULT_JOURNAL` at call time (not at
    import), so a test that monkeypatches ``DEFAULT_JOURNAL`` sees the
    new path without needing to thread ``journal=`` through every
    producer.
    """
    if journal is None:
        journal = DEFAULT_JOURNAL
    if priority not in _ALLOWED_PRIORITIES:
        # p1 belongs in the immediate-send path (alerts.py). Refuse
        # cleanly so a mislabel doesn't silently degrade to batched.
        logger.warning(
            "digest_queue: priority=%s not in %s; refusing to queue kind=%s",
            priority,
            sorted(_ALLOWED_PRIORITIES),
            kind,
        )
        return False

    clean_body = str(body or "").strip()
    if not clean_body:
        return False
    if len(clean_body) > 500:
        clean_body = clean_body[:497].rstrip() + "…"

    entry = DigestEntry(
        ts=(now or datetime.now(UTC)).isoformat(),
        kind=str(kind or "unknown"),
        body=clean_body,
        priority=priority,
        metadata=dict(metadata or {}),
    )
    try:
        _write_line(journal, entry)
    except OSError as exc:
        logger.warning("digest_queue: journal write failed: %s", exc)
        return False
    _trim_journal(journal)
    return True


def peek(*, journal: Path | None = None, max_age_hours: float = MAX_AGE_HOURS) -> list[DigestEntry]:
    """Return the queued (non-stale) entries without draining the journal.

    Callers use this when they want to render the digest text before
    committing to a flush — the heartbeat previews the digest to
    decide whether to send.
    """
    return list(_iter_entries(journal or DEFAULT_JOURNAL, max_age_hours=max_age_hours))


def flush_digest(
    *,
    journal: Path | None = None,
    max_age_hours: float = MAX_AGE_HOURS,
    now: datetime | None = None,
    archive_dir: Path | None = None,
    banner: str = "📬 Sapphire Digest",
) -> str | None:
    """Drain the queue and return one formatted MarkdownV2 message.

    ``None`` means "nothing to send". A caller that shells to
    ``notify.py`` should check for ``None`` before spending an SMS/
    Telegram credit.
    """
    journal = journal or DEFAULT_JOURNAL
    archive_dir = archive_dir or ARCHIVE_DIR
    entries = list(_iter_entries(journal, max_age_hours=max_age_hours))
    if not entries:
        return None
    text = format_digest(entries, banner=banner, now=now)
    _archive(journal, entries, archive_dir=archive_dir, now=now)
    return text


def format_digest(
    entries: Iterable[DigestEntry],
    *,
    banner: str = "📬 Sapphire Digest",
    now: datetime | None = None,
) -> str:
    """Render the queued entries as one MarkdownV2 message.

    Layout:

        *📬 Sapphire Digest*
        _12 items · window 8h_

        *portfolio_mover* · 3 items
        • BTC +3.1%
        • ETH +2.4%
        • SOL -2.9%

        *signal* · 2 items
        • …

    Groups are ordered by count desc, then kind asc. Body lines are
    escaped for MDV2. If a kind has >8 entries, the oldest are dropped
    with a ``… + N older`` suffix — keeps the message under Telegram's
    4096-char cap on chatty days.
    """
    entries_list = list(entries)
    if not entries_list:
        return f"{fmt.bold(banner)}\n\n{fmt.esc('(nothing queued)')}"

    counts = Counter(e.kind for e in entries_list)
    order = sorted(counts, key=lambda k: (-counts[k], k))

    window_seconds = _window_seconds(entries_list, now=now)
    header = fmt.bold(banner)
    subtitle = fmt.esc(f"{len(entries_list)} items · window {fmt.fmt_duration(window_seconds)}")

    sections: list[str] = []
    for kind in order:
        items = [e for e in entries_list if e.kind == kind]
        # Newest first inside each kind.
        items.sort(key=lambda e: e.ts, reverse=True)
        header_line = f"{fmt.bold(kind)} · {fmt.esc(str(len(items)) + ' items')}"
        body_lines: list[str] = []
        shown = items[:8]
        for entry in shown:
            body_lines.append(f"• {fmt.esc(entry.body)}")
        if len(items) > 8:
            body_lines.append(fmt.esc(f"… + {len(items) - 8} older"))
        sections.append(header_line + "\n" + "\n".join(body_lines))

    return f"{header}\n_{subtitle}_\n\n" + "\n\n".join(sections)


def stats(*, journal: Path | None = None, max_age_hours: float = MAX_AGE_HOURS) -> dict:
    """One-shot introspection for the /status card + doctor."""
    journal = journal or DEFAULT_JOURNAL
    entries = list(_iter_entries(journal, max_age_hours=max_age_hours))
    counts = Counter(e.kind for e in entries)
    return {
        "path": str(journal),
        "queued": len(entries),
        "kinds": dict(counts),
        "priority_p2": sum(1 for e in entries if e.priority == "p2"),
        "priority_p3": sum(1 for e in entries if e.priority == "p3"),
        "window_seconds": _window_seconds(entries),
    }


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------


def _write_line(journal: Path, entry: DigestEntry) -> None:
    journal.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "ts": entry.ts,
        "kind": entry.kind,
        "body": entry.body,
        "priority": entry.priority,
        "metadata": entry.metadata,
    }
    with journal.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload) + "\n")


def _iter_entries(journal: Path, *, max_age_hours: float) -> Iterable[DigestEntry]:
    if not journal.exists():
        return
    cutoff = datetime.now(UTC).timestamp() - max_age_hours * 3600
    try:
        raw = journal.read_text(encoding="utf-8")
    except OSError:
        return
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(payload, dict):
            continue
        ts_str = str(payload.get("ts") or "")
        try:
            when = datetime.fromisoformat(ts_str)
            if when.timestamp() < cutoff:
                continue
        except ValueError:
            # Unparseable timestamp = skip rather than crash.
            continue
        yield DigestEntry(
            ts=ts_str,
            kind=str(payload.get("kind") or "unknown"),
            body=str(payload.get("body") or ""),
            priority=str(payload.get("priority") or "p3"),
            metadata=dict(payload.get("metadata") or {}),
        )


def _trim_journal(journal: Path) -> None:
    """Cap the journal to ``MAX_ENTRIES`` most recent lines.

    Cheap enough to run on every write for the volumes we expect
    (dozens per day). If it ever gets hot, promote to a scheduled cron.
    """
    try:
        with journal.open("r", encoding="utf-8") as handle:
            lines = handle.readlines()
    except (FileNotFoundError, OSError):
        return
    if len(lines) <= MAX_ENTRIES:
        return
    kept = lines[-MAX_ENTRIES:]
    tmp = journal.with_suffix(".jsonl.tmp")
    try:
        tmp.write_text("".join(kept), encoding="utf-8")
        os.replace(tmp, journal)
    except OSError as exc:
        logger.warning("digest_queue: trim failed: %s", exc)


def _archive(
    journal: Path,
    entries: list[DigestEntry],
    *,
    archive_dir: Path,
    now: datetime | None = None,
) -> None:
    """Move the drained lines to the archive dir and empty the journal.

    We rotate rather than delete so a mistaken digest can still be
    reconstructed. Archive files are safe to prune out of band; the
    live queue never reads them back.
    """
    ts = (now or datetime.now(UTC)).strftime("%Y%m%d-%H%M%S")
    archive_dir.mkdir(parents=True, exist_ok=True)
    archive_path = archive_dir / f"digest-{ts}.jsonl"
    with archive_path.open("w", encoding="utf-8") as handle:
        for entry in entries:
            handle.write(
                json.dumps(
                    {
                        "ts": entry.ts,
                        "kind": entry.kind,
                        "body": entry.body,
                        "priority": entry.priority,
                        "metadata": entry.metadata,
                    }
                )
                + "\n"
            )
    try:
        # Empty the live journal atomically.
        journal.write_text("", encoding="utf-8")
    except OSError as exc:
        logger.warning("digest_queue: reset failed: %s", exc)


def _window_seconds(entries: list[DigestEntry], *, now: datetime | None = None) -> int:
    """Age of the oldest entry, in whole seconds. 0 if empty."""
    if not entries:
        return 0
    reference = now or datetime.now(UTC)
    oldest = min(entries, key=lambda e: e.ts)
    try:
        when = datetime.fromisoformat(oldest.ts)
    except ValueError:
        return 0
    return max(0, int((reference - when).total_seconds()))


__all__ = [
    "ARCHIVE_DIR",
    "DEFAULT_JOURNAL",
    "DigestEntry",
    "MAX_AGE_HOURS",
    "MAX_ENTRIES",
    "enqueue",
    "flush_digest",
    "format_digest",
    "peek",
    "stats",
]
