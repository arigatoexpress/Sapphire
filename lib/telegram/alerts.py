"""Intraday alert dispatcher for Sapphire's Telegram surface.

Producer modules (chain intelligence, kill-switch, portfolio watcher,
threat sweep) call the ``alert_*`` helpers here. Each helper:

1. Builds a formatted MarkdownV2 message via ``lib.telegram.formatters``.
2. Skips if the alert's dedup key was seen in the last window.
3. Routes by priority:
   * ``p1`` (kill switch, regime shift, critical CVE) — shells out to
     ``plugins/claw-sapphire/tools/notify.py`` for an immediate send.
   * ``p2`` / ``p3`` (large single-holding moves, lower-severity CVEs,
     info) — appended to :mod:`lib.telegram.digest_queue` and rolled
     into the next scheduled digest tick.

The ``SAPPHIRE_NOTIFY_TELEGRAM_LIVE`` gate stays authoritative for
outbound sends — both p1 alerts and the drained digest go through
``notify.py``. This module never sends around it.

Idempotency: a small JSONL journal at
``~/.cache/sapphire/telegram/alert_journal.jsonl`` remembers the last
2048 dispatched keys. Producers can pass ``force=True`` to bypass.

None of these helpers raise on failure — an alert that couldn't be
sent is logged and returns ``False`` so producers stay resilient.
"""

from __future__ import annotations

import hashlib
import json
import logging
import subprocess
import sys
from collections import deque
from datetime import UTC, datetime
from pathlib import Path

from lib.telegram import digest_queue, formatters

logger = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parents[2]
NOTIFY_TOOL = REPO_ROOT / "plugins" / "claw-sapphire" / "tools" / "notify.py"
JOURNAL_PATH = Path.home() / ".cache" / "sapphire" / "telegram" / "alert_journal.jsonl"
JOURNAL_MAX_ENTRIES = 2048


def _load_seen(path: Path | None = None) -> set[str]:
    """Load the recent dedup keys from the journal (best-effort).

    ``path`` late-binds to :data:`JOURNAL_PATH` at call time so tests
    that monkeypatch ``JOURNAL_PATH`` see the swap without threading
    the argument through every producer.
    """
    path = path or JOURNAL_PATH
    if not path.exists():
        return set()
    try:
        recent: deque[str] = deque(maxlen=JOURNAL_MAX_ENTRIES)
        with path.open() as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue
                key = entry.get("key")
                if isinstance(key, str):
                    recent.append(key)
        return set(recent)
    except OSError:
        return set()


def _append_journal(key: str, kind: str, path: Path | None = None) -> None:
    path = path or JOURNAL_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    entry = {
        "key": key,
        "kind": kind,
        "ts": datetime.now(UTC).isoformat(),
    }
    with path.open("a") as handle:
        handle.write(json.dumps(entry) + "\n")


def _dedup_key(kind: str, *parts: object) -> str:
    joined = "|".join([kind, *(str(p) for p in parts)])
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()[:24]


def _dispatch(text: str, *, priority: str, dedup_key: str, kind: str, force: bool) -> bool:
    """Route an alert to either the immediate-send channel or the digest.

    Contract:

    * ``priority == "p1"``  → shell to ``notify.py`` right now.
    * ``priority in {"p2", "p3"}`` → append to
      :mod:`lib.telegram.digest_queue`; nothing goes out until the
      scheduled digest tick drains the journal.

    Dedup applies in both cases so a re-fire on the same fingerprint
    is a no-op regardless of channel. The digest path returns ``True``
    when the entry landed in the queue — producers only need to know
    whether their intent was accepted, not which channel delivered.
    """
    if not force:
        seen = _load_seen()
        if dedup_key in seen:
            logger.info("alert %s deduped (key=%s)", kind, dedup_key)
            return False

    if priority != "p1":
        # Non-critical — batch it. The digest queue caps + trims itself,
        # so we don't need to guard against runaway producers here.
        queued = digest_queue.enqueue(
            kind=kind,
            body=_digest_body(text),
            priority=priority,
            metadata={"dedup_key": dedup_key},
        )
        if queued:
            _append_journal(dedup_key, kind)
        return queued

    if not NOTIFY_TOOL.exists():
        logger.error("notify tool missing at %s", NOTIFY_TOOL)
        return False
    try:
        completed = subprocess.run(
            [sys.executable, str(NOTIFY_TOOL), "--priority", priority, text],
            check=False,
        )
    except (FileNotFoundError, OSError) as exc:
        logger.error("failed to shell notify.py: %s", exc)
        return False
    if completed.returncode != 0:
        logger.error("notify.py exited %s for kind=%s", completed.returncode, kind)
        return False
    _append_journal(dedup_key, kind)
    return True


def _digest_body(text: str) -> str:
    """Reduce a MarkdownV2 alert card to one plain-text digest line.

    Digest entries render inside a grouped section — we already know
    the kind, so we don't need the card's header. Take the first
    non-empty line after the title, strip MDV2 escape backslashes so
    the digest formatter can re-escape cleanly.
    """
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    # Skip the emoji + `*Title*` header (line 0) and the blank line.
    body_lines = lines[1:] if len(lines) > 1 else lines
    if not body_lines:
        return "(alert)"
    first = body_lines[0]
    # Strip bullet markup + MDV2 backslash escapes so downstream escaping
    # doesn't render "\\+3\\.1%" back to the user.
    first = first.lstrip("• ").replace("\\", "")
    return first[:200]


# ---------------------------------------------------------------------------
# Public alert helpers
# ---------------------------------------------------------------------------


def alert_regime_shift(
    *,
    old_regime: str,
    new_regime: str,
    confidence: float | None = None,
    force: bool = False,
) -> bool:
    """Fire when the GMM regime classifier flips."""
    key = _dedup_key("regime", old_regime, new_regime, datetime.now(UTC).strftime("%Y%m%d%H"))
    body_rows = [
        ("From", formatters.code(old_regime.upper())),
        ("To", formatters.code(new_regime.upper())),
    ]
    if confidence is not None:
        body_rows.append(("Confidence", formatters.fmt_pct(confidence * 100)))
    text = f"⚠️ {formatters.bold('Regime shift')}\n\n" + formatters.kv_table(body_rows)
    return _dispatch(text, priority="p1", dedup_key=key, kind="regime_shift", force=force)


def alert_kill_switch(reason: str, *, force: bool = False) -> bool:
    """Fire on kill-switch arm/trip. Never deduped by default — safety event."""
    key = _dedup_key("kill_switch", reason, datetime.now(UTC).strftime("%Y%m%d%H%M"))
    text = f"🚨 {formatters.bold('KILL SWITCH ARMED')}\n\n" + formatters.esc(reason)
    return _dispatch(text, priority="p1", dedup_key=key, kind="kill_switch", force=force or True)


def alert_large_move(
    *,
    symbol: str,
    pct_change: float,
    price: float | None = None,
    threshold_pct: float = 5.0,
    force: bool = False,
) -> bool:
    """Fire when a single holding moves > threshold in the last window."""
    if abs(pct_change) < threshold_pct:
        return False
    key = _dedup_key(
        "large_move",
        symbol,
        f"{pct_change:.1f}",
        datetime.now(UTC).strftime("%Y%m%d%H"),
    )
    emoji = "🚀" if pct_change > 0 else "🔻"
    rows = [
        ("Change", formatters.fmt_pct(pct_change)),
    ]
    if price is not None:
        rows.append(("Price", formatters.fmt_usd(price)))
    text = (
        f"{emoji} {formatters.bold('Large move')} · {formatters.code(symbol)}\n\n"
        + formatters.kv_table(rows)
    )
    return _dispatch(text, priority="p2", dedup_key=key, kind="large_move", force=force)


def alert_new_cve(
    *,
    cve_id: str,
    severity: str,
    package: str,
    summary: str = "",
    force: bool = False,
) -> bool:
    """Fire on a new CVE hit from the daily security sweep."""
    key = _dedup_key("cve", cve_id)
    card = formatters.fmt_security_card(
        formatters.ThreatCard(
            identifier=cve_id,
            severity=severity,
            package=package,
            summary=summary,
        )
    )
    priority = "p1" if severity.lower() in {"critical", "high"} else "p2"
    return _dispatch(card, priority=priority, dedup_key=key, kind="cve", force=force)


__all__ = [
    "alert_kill_switch",
    "alert_large_move",
    "alert_new_cve",
    "alert_regime_shift",
]
