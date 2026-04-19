"""Foundry sync engine — 15-min delta-aware scheduled sync.

Watches local Sapphire data sources, detects changes via file mtime + content
hash, transforms changed data into Foundry ontology objects, and uploads them.
Sends Telegram alerts on sync failure.

Usage::

    # One-shot sync
    python3 -m lib.foundry.sync

    # Daemon (15-min loop)
    python3 -m lib.foundry.sync --daemon

    # Dry-run (no uploads)
    python3 -m lib.foundry.sync --dry-run
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import signal
import sys
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

log = logging.getLogger("foundry.sync")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_DEFAULT_INTERVAL = 900  # 15 minutes
_STATE_FILE = "data/foundry_sync_state.json"
_HISTORY_FILE = "data/foundry_sync_history.jsonl"

# Dataset source groups — maps Foundry object type → local file patterns
_SOURCE_PATTERNS: dict[str, list[str]] = {
    "PaperTrade": ["data/signals/*.jsonl", "data/paper_portfolio.json"],
    "Alert": ["data/system_events.jsonl", "data/security/*.json"],
    "ServiceHealth": ["data/health/*.ndjson"],
    "ThreatIntel": [
        "data/intelligence/*/threats.json",
        "data/threat_intel/*.md",
    ],
    "DailyBrief": [
        "data/intelligence/*/daily_brief.json",
        "data/intelligence/*/daily_brief.md",
    ],
}


def _repo_root() -> Path:
    home_repo = Path.home() / "Code" / "Sapphire"
    local_repo = Path(__file__).resolve().parents[2]
    for c in (home_repo, local_repo):
        if c.exists():
            return c
    return local_repo


# ---------------------------------------------------------------------------
# Delta detection
# ---------------------------------------------------------------------------


@dataclass
class SyncState:
    """Tracks file modification times and content hashes between syncs."""

    files: dict[str, dict[str, Any]] = field(default_factory=dict)
    last_sync: str | None = None
    last_status: str = "never"
    sync_count: int = 0

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({
            "files": self.files,
            "last_sync": self.last_sync,
            "last_status": self.last_status,
            "sync_count": self.sync_count,
        }, indent=2, default=str))

    @classmethod
    def load(cls, path: Path) -> "SyncState":
        if not path.is_file():
            return cls()
        try:
            data = json.loads(path.read_text())
            return cls(
                files=data.get("files", {}),
                last_sync=data.get("last_sync"),
                last_status=data.get("last_status", "unknown"),
                sync_count=data.get("sync_count", 0),
            )
        except Exception:
            return cls()


def _file_hash(path: Path, *, max_bytes: int = 1_000_000) -> str:
    """Fast content hash (first MB) for delta detection."""
    h = hashlib.sha256()
    try:
        with path.open("rb") as fh:
            h.update(fh.read(max_bytes))
    except OSError:
        return ""
    return h.hexdigest()[:16]


def _scan_sources(root: Path) -> dict[str, dict[str, Any]]:
    """Scan all source patterns and return file → {mtime, hash} map."""
    result: dict[str, dict[str, Any]] = {}
    for patterns in _SOURCE_PATTERNS.values():
        for pattern in patterns:
            for path in root.glob(pattern):
                if not path.is_file():
                    continue
                key = str(path.relative_to(root))
                try:
                    stat = path.stat()
                    result[key] = {
                        "mtime": stat.st_mtime,
                        "size": stat.st_size,
                        "hash": _file_hash(path),
                    }
                except OSError:
                    continue
    return result


def detect_changes(
    state: SyncState, current_files: dict[str, dict[str, Any]]
) -> dict[str, list[str]]:
    """Compare current files against saved state.  Returns changed object types."""
    changed_types: dict[str, list[str]] = {}

    for obj_type, patterns in _SOURCE_PATTERNS.items():
        changed_files: list[str] = []
        for pattern in patterns:
            for fkey, finfo in current_files.items():
                # Check if this file matches the pattern's prefix
                import fnmatch

                if not fnmatch.fnmatch(fkey, pattern):
                    continue
                prev = state.files.get(fkey)
                if prev is None:
                    changed_files.append(fkey)
                elif prev.get("hash") != finfo.get("hash"):
                    changed_files.append(fkey)
                elif prev.get("mtime") != finfo.get("mtime"):
                    changed_files.append(fkey)
        if changed_files:
            changed_types[obj_type] = changed_files

    return changed_types


# ---------------------------------------------------------------------------
# Sync history (append-only JSONL)
# ---------------------------------------------------------------------------


def _append_history(root: Path, record: dict[str, Any]) -> None:
    history_path = root / _HISTORY_FILE
    history_path.parent.mkdir(parents=True, exist_ok=True)
    with history_path.open("a") as fh:
        fh.write(json.dumps(record, default=str) + "\n")


def load_sync_history(root: Path | None = None, *, limit: int = 50) -> list[dict[str, Any]]:
    """Read the last *limit* sync history entries."""
    root = root or _repo_root()
    history_path = root / _HISTORY_FILE
    if not history_path.is_file():
        return []
    entries: list[dict[str, Any]] = []
    try:
        for line in history_path.read_text().strip().split("\n"):
            if line.strip():
                try:
                    entries.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    except OSError:
        pass
    return entries[-limit:]


# ---------------------------------------------------------------------------
# Telegram alert
# ---------------------------------------------------------------------------


def _send_telegram_alert(message: str) -> None:
    """Best-effort Telegram notification on sync failure."""
    try:
        # Reuse Sapphire's existing telegram helper if available
        from lib.telegram.src.sapphire_telegram.safe_send import send
        send(message, priority="high")
        return
    except Exception:
        pass

    # Fallback: direct API call
    token = os.getenv("TELEGRAM_BOT_TOKEN", "")
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "")
    if not token or not chat_id:
        log.warning("No Telegram credentials — cannot send sync failure alert")
        return

    import urllib.request

    try:
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        data = json.dumps({"chat_id": chat_id, "text": message, "parse_mode": "Markdown"}).encode()
        req = urllib.request.Request(
            url, data=data, headers={"Content-Type": "application/json"}, method="POST"
        )
        urllib.request.urlopen(req, timeout=10)
    except Exception as exc:
        log.warning("Telegram alert failed: %s", exc)


# ---------------------------------------------------------------------------
# Sync execution
# ---------------------------------------------------------------------------


@dataclass
class SyncResult:
    """Result of a single sync cycle."""

    ok: bool
    timestamp: str
    duration_s: float = 0.0
    changed_types: dict[str, int] = field(default_factory=dict)
    uploaded_types: dict[str, int] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)
    dry_run: bool = False
    skipped: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "timestamp": self.timestamp,
            "duration_s": round(self.duration_s, 2),
            "changed_types": self.changed_types,
            "uploaded_types": self.uploaded_types,
            "errors": self.errors,
            "dry_run": self.dry_run,
            "skipped": self.skipped,
        }


def run_sync(
    root: Path | None = None,
    *,
    dry_run: bool = False,
    force: bool = False,
) -> SyncResult:
    """Execute one sync cycle.

    1. Scan local sources for changes
    2. Transform changed data into Foundry objects
    3. Upload to Foundry (unless dry_run)
    4. Update state file
    5. Alert on failure
    """
    root = root or _repo_root()
    state_path = root / _STATE_FILE
    state = SyncState.load(state_path)
    t0 = time.monotonic()
    now = datetime.now(UTC).isoformat()

    result = SyncResult(ok=True, timestamp=now, dry_run=dry_run)

    # 1. Scan
    current_files = _scan_sources(root)
    changes = detect_changes(state, current_files)

    if not changes and not force:
        result.skipped = True
        result.duration_s = time.monotonic() - t0
        log.info("No changes detected — sync skipped")
        return result

    result.changed_types = {k: len(v) for k, v in changes.items()}
    log.info("Changes detected: %s", result.changed_types)

    # 2. Transform
    from lib.foundry.ingestion import ALL_TRANSFORMS

    objects_by_type: dict[str, list[dict[str, Any]]] = {}
    types_to_sync = list(changes.keys()) if not force else list(ALL_TRANSFORMS.keys())

    for obj_type in types_to_sync:
        fn = ALL_TRANSFORMS.get(obj_type)
        if fn is None:
            continue
        try:
            if obj_type == "ServiceHealth":
                objects_by_type[obj_type] = fn(root)
            else:
                objects_by_type[obj_type] = fn(root)
        except Exception as exc:
            log.exception("Transform %s failed", obj_type)
            result.errors.append(f"Transform {obj_type}: {exc}")

    # 3. Upload
    if not dry_run:
        try:
            from lib.foundry.client import FoundryClient, FoundryError

            client = FoundryClient.from_env()
            for obj_type, objects in objects_by_type.items():
                if not objects:
                    continue
                try:
                    client.upsert_objects(obj_type, objects)
                    result.uploaded_types[obj_type] = len(objects)
                    log.info("Uploaded %d %s objects", len(objects), obj_type)
                except FoundryError as exc:
                    log.error("Upload %s failed: %s", obj_type, exc)
                    result.errors.append(f"Upload {obj_type}: {exc}")
        except Exception as exc:
            log.error("Foundry client init failed: %s", exc)
            result.errors.append(f"Client init: {exc}")
    else:
        for obj_type, objects in objects_by_type.items():
            result.uploaded_types[obj_type] = len(objects)
            log.info("[DRY RUN] Would upload %d %s objects", len(objects), obj_type)

    # 4. Update state
    result.ok = len(result.errors) == 0
    result.duration_s = time.monotonic() - t0

    state.files = current_files
    state.last_sync = now
    state.last_status = "ok" if result.ok else "error"
    state.sync_count += 1
    state.save(state_path)

    # 5. History
    _append_history(root, result.to_dict())

    # 6. Alert on failure
    if not result.ok:
        msg = (
            f"⚠️ *Foundry Sync Failed*\n"
            f"Time: {now}\n"
            f"Errors: {len(result.errors)}\n"
            f"{''.join(f'• {e}' + chr(10) for e in result.errors[:5])}"
        )
        _send_telegram_alert(msg)

    return result


# ---------------------------------------------------------------------------
# Sync status (for dashboard API)
# ---------------------------------------------------------------------------


def get_sync_status(root: Path | None = None) -> dict[str, Any]:
    """Return current sync status for the dashboard."""
    root = root or _repo_root()
    state_path = root / _STATE_FILE
    state = SyncState.load(state_path)

    history = load_sync_history(root, limit=10)
    recent_errors = [h for h in history if not h.get("ok", True)]

    return {
        "last_sync": state.last_sync,
        "last_status": state.last_status,
        "sync_count": state.sync_count,
        "tracked_files": len(state.files),
        "recent_history": history[-5:],
        "recent_errors": len(recent_errors),
        "interval_seconds": _DEFAULT_INTERVAL,
        "source_types": list(_SOURCE_PATTERNS.keys()),
    }


# ---------------------------------------------------------------------------
# Daemon loop
# ---------------------------------------------------------------------------


def _daemon(root: Path, *, interval: int = _DEFAULT_INTERVAL, dry_run: bool = False) -> None:
    """Run sync in a loop.  Graceful shutdown on SIGTERM/SIGINT."""
    running = True

    def _stop(signum: int, frame: Any) -> None:
        nonlocal running
        log.info("Received signal %d — stopping sync daemon", signum)
        running = False

    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)

    log.info("Foundry sync daemon started (interval=%ds, dry_run=%s)", interval, dry_run)
    while running:
        try:
            result = run_sync(root, dry_run=dry_run)
            if result.skipped:
                log.debug("Cycle skipped (no changes)")
            else:
                log.info(
                    "Cycle complete: ok=%s, uploaded=%s, errors=%d",
                    result.ok,
                    result.uploaded_types,
                    len(result.errors),
                )
        except Exception:
            log.exception("Sync cycle crashed")
        # Sleep in small increments for responsiveness to signals
        for _ in range(interval):
            if not running:
                break
            time.sleep(1)

    log.info("Foundry sync daemon stopped")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(description="Foundry sync for Sapphire")
    parser.add_argument("--daemon", action="store_true", help="Run in daemon mode (15-min loop)")
    parser.add_argument("--interval", type=int, default=_DEFAULT_INTERVAL, help="Sync interval in seconds")
    parser.add_argument("--dry-run", action="store_true", help="Transform but don't upload")
    parser.add_argument("--force", action="store_true", help="Sync all types regardless of changes")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s %(message)s",
    )

    root = _repo_root()

    if args.daemon:
        _daemon(root, interval=args.interval, dry_run=args.dry_run)
    else:
        result = run_sync(root, dry_run=args.dry_run, force=args.force)
        print(json.dumps(result.to_dict(), indent=2))
        sys.exit(0 if result.ok else 1)


if __name__ == "__main__":
    main()
