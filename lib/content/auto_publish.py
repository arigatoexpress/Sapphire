"""Read ``data/content/ready/`` and push to live platforms.

Called by the 6:15 AM LaunchAgent
(``infra/launchagents/com.sapphire.content-publisher.plist``) fifteen
minutes after ``lib.content`` generates the day's posts.

Flow
----
1. For each platform in :data:`PLATFORM_DIRS`, find the newest
   rendering whose ``published_at`` is within the cutoff window and
   which has NOT already been published (idempotency ledger in
   ``data/content/published_ledger.json``).
2. Dispatch via the matching :class:`PublisherClient`.
3. Emit ``content.published`` to the event bus (success OR failure).
4. Append the outcome to the ledger.
5. Optionally Telegram-ping Ari with a per-run summary.

The orchestrator is dry-run by default. Set ``SAPPHIRE_PUBLISH_LIVE=1``
in the LaunchAgent env to flip every client into live mode. This lets
the pipeline run end-to-end in CI without risking a real post.
Telegram summaries are disabled by default and must be explicitly enabled
with ``SAPPHIRE_CONTENT_TELEGRAM_SUMMARY=1``.
"""

from __future__ import annotations

import json
import logging
import os
from collections.abc import Iterable
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from lib.core.routine_pause import abort_if_paused

from .publishers import PublishResult, load_client

logger = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parents[2]
READY_ROOT = REPO_ROOT / "data" / "content" / "ready"
LEDGER_PATH = REPO_ROOT / "data" / "content" / "published_ledger.json"

PLATFORM_DIRS: dict[str, str] = {
    "linkedin": "linkedin",
    "substack": "substack",
    "x": "x",
}

# How far back to look for un-published renderings.
DEFAULT_WINDOW = timedelta(hours=48)
_TRUE_VALUES = {"1", "true", "yes", "on"}


@dataclass
class DispatchItem:
    platform: str
    path: Path
    kind: str  # market_pulse, weekly_crypto_brief, ...


# --- ledger -----------------------------------------------------------------


def _load_ledger() -> dict[str, dict[str, Any]]:
    if not LEDGER_PATH.exists():
        return {}
    try:
        return json.loads(LEDGER_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        # corrupt ledger — start fresh rather than block publishing
        logger.warning("ledger corrupt, resetting: %s", LEDGER_PATH)
        return {}


def _write_ledger(data: dict[str, dict[str, Any]]) -> None:
    LEDGER_PATH.parent.mkdir(parents=True, exist_ok=True)
    LEDGER_PATH.write_text(json.dumps(data, indent=2, default=str))


def _ledger_key(item: DispatchItem) -> str:
    return f"{item.platform}:{item.kind}"


# --- discovery --------------------------------------------------------------


def _parse_stamp(path: Path) -> datetime | None:
    """Filenames are ``YYYYMMDD_HHMM_<kind>.<ext>``."""
    try:
        stem = path.stem
        stamp = "_".join(stem.split("_", 2)[:2])
        return datetime.strptime(stamp, "%Y%m%d_%H%M")
    except (ValueError, IndexError):
        return None


def _kind_from(path: Path) -> str:
    # "20260418_0600_market_pulse.md" -> "market_pulse"
    parts = path.stem.split("_", 2)
    return parts[2] if len(parts) >= 3 else "unknown"


def discover(
    window: timedelta = DEFAULT_WINDOW,
    platforms: Iterable[str] = PLATFORM_DIRS.keys(),
    now: datetime | None = None,
    ledger: dict[str, dict[str, Any]] | None = None,
) -> list[DispatchItem]:
    """Return the newest un-published rendering per (platform, kind)."""
    now = now or datetime.now()
    ledger = ledger if ledger is not None else _load_ledger()
    cutoff = now - window
    by_group: dict[tuple[str, str], DispatchItem] = {}

    for plat in platforms:
        subdir = READY_ROOT / PLATFORM_DIRS[plat]
        if not subdir.exists():
            continue
        for path in subdir.iterdir():
            if not path.is_file():
                continue
            stamp = _parse_stamp(path)
            if stamp is None or stamp < cutoff:
                continue
            item = DispatchItem(platform=plat, path=path, kind=_kind_from(path))
            if _ledger_key(item) in ledger:
                continue  # already published
            key = (plat, item.kind)
            # keep the newest per (platform, kind)
            prev = by_group.get(key)
            if prev is None or _parse_stamp(prev.path) < stamp:  # type: ignore[operator]
                by_group[key] = item

    return sorted(by_group.values(), key=lambda i: (i.platform, i.kind))


# --- dispatch ---------------------------------------------------------------


def _load_content(item: DispatchItem) -> dict[str, Any]:
    """Turn a file on disk into the kwargs each client expects."""
    text = item.path.read_text(encoding="utf-8")
    if item.platform == "linkedin":
        return {"text": text}
    if item.platform == "substack":
        # First line after an optional title marker is the post title.
        lines = text.splitlines()
        title = lines[0].lstrip("# ").strip() if lines else "Sapphire — Weekly Signal"
        body = text
        # Very light HTML conversion; Substack's email ingest tolerates markdown.
        return {"title": title, "body_html": body, "body_text": body}
    if item.platform == "x":
        # The X renderer writes JSONL — one tweet per line.
        tweets: list[str] = []
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
                tweets.append(obj.get("text", ""))
            except json.JSONDecodeError:
                tweets.append(line)
        return {"tweets": [t for t in tweets if t]}
    return {}


def dispatch_one(item: DispatchItem, *, dry_run: bool | None = None) -> PublishResult:
    client = load_client(item.platform, dry_run=dry_run)
    # X fallback to typefully if X creds aren't present but Typefully's is.
    if (
        item.platform == "x"
        and client is not None
        and not client.configured()
        and os.getenv("TYPEFULLY_API_KEY")
    ):
        client = load_client("typefully", dry_run=dry_run)
    if client is None:
        return PublishResult(
            platform=item.platform,
            ok=False,
            dry_run=True if dry_run is None else dry_run,
            error=f"no client registered for platform {item.platform}",
        )
    kwargs = _load_content(item)
    return client.publish(**kwargs)


# --- telemetry --------------------------------------------------------------


def _emit_event(item: DispatchItem, result: PublishResult) -> None:
    try:
        from lib.core import event_bus  # local import — avoid import-time cost

        event_bus.publish(
            "content.published",
            {
                "platform": item.platform,
                "kind": item.kind,
                "path": str(item.path.relative_to(REPO_ROOT)),
                "ok": result.ok,
                "dry_run": result.dry_run,
                "url": result.url,
                "error": result.error,
            },
            source="content-publisher",
        )
    except Exception:
        logger.exception("event_bus publish failed — continuing")


def _telegram_summary(results: list[tuple[DispatchItem, PublishResult]]) -> None:
    if not results:
        return
    try:
        from lib.telegram.src.sapphire_telegram import safe_send
    except Exception:
        logger.info("telegram safe_send not importable — skipping summary ping")
        return

    lines = ["Content publisher run"]
    for item, result in results:
        tag = "✅" if result.ok else "❌"
        mode = "[dry]" if result.dry_run else "[live]"
        ref = result.url or result.remote_id or result.error or ""
        lines.append(f"{tag} {mode} {item.platform}/{item.kind} — {ref}")
    priority = "p1" if any(not r.ok and not r.dry_run for _, r in results) else "p2"
    safe_send.send("\n".join(lines), priority=priority)


def _env_flag(name: str, *, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    return raw.strip().lower() in _TRUE_VALUES


# --- entry point ------------------------------------------------------------


def run(
    *,
    dry_run: bool | None = None,
    telegram_summary: bool | None = None,
    window: timedelta = DEFAULT_WINDOW,
    platforms: Iterable[str] = PLATFORM_DIRS.keys(),
) -> dict[str, Any]:
    ledger = _load_ledger()
    items = discover(window=window, platforms=platforms, ledger=ledger)
    results: list[tuple[DispatchItem, PublishResult]] = []
    for item in items:
        result = dispatch_one(item, dry_run=dry_run)
        results.append((item, result))
        _emit_event(item, result)
        if result.ok and not result.dry_run:
            ledger[_ledger_key(item)] = {
                "published_at": datetime.now().isoformat(timespec="seconds"),
                "url": result.url,
                "remote_id": result.remote_id,
            }
    _write_ledger(ledger)
    if telegram_summary is None:
        telegram_summary = _env_flag("SAPPHIRE_CONTENT_TELEGRAM_SUMMARY", default=False)
    if telegram_summary:
        _telegram_summary(results)
    else:
        logger.info("content publisher Telegram summary disabled")

    return {
        "run_at": datetime.now().isoformat(timespec="seconds"),
        "telegram_summary": bool(telegram_summary),
        "items": [
            {
                "item": {"platform": i.platform, "kind": i.kind, "path": str(i.path)},
                "result": asdict(r),
            }
            for i, r in results
        ],
    }


if __name__ == "__main__":
    abort_if_paused("content-publisher")
    out = run()
    print(json.dumps(out, indent=2, default=str))
