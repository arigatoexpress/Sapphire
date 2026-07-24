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

from lib.core.provenance import write_envelope_sidecar

log = logging.getLogger("foundry.sync")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_DEFAULT_INTERVAL = 900  # 15 minutes
_STATE_FILE = "data/foundry_sync_state.json"
_HISTORY_FILE = "data/foundry_sync_history.jsonl"
_WATERMARK_DIR = Path.home() / ".cache" / "sapphire" / "foundry_sync"

# Dataset source groups — maps Foundry object type → local file patterns
_SOURCE_PATTERNS: dict[str, list[str]] = {
    "PaperTrade": ["data/signals/*.jsonl", "data/paper_portfolio.json"],
    "Alert": ["data/system_events.jsonl", "data/security/**/*.json"],
    "ServiceHealth": ["data/health/*.ndjson", "data/health/heartbeat.jsonl"],
    "ThreatIntel": [
        "data/intelligence/*/threats.json",
        "data/threat_intel/*.md",
    ],
    "DailyBrief": [
        "data/intelligence/*/daily_brief.json",
        "data/intelligence/*/daily_brief.md",
    ],
    "Region": ["data/foundry/regional-intel/Region.ndjson"],
    "IntelItem": ["data/foundry/regional-intel/IntelItem.ndjson"],
    "IntelSourceHealth": ["data/foundry/regional-intel/IntelSourceHealth.ndjson"],
    # Tranche-3 expansion (ontology v0.2.0). External-cache-backed sources
    # (vector store mock, gemini cache, hyperliquid signal log) are guarded
    # by repo-local mirror paths first; the worker scans home cache only as
    # a fallback so CI never accidentally picks up developer state.
    "IntelVectorRecord": [
        "data/intel/bq_vector_mock.jsonl",
    ],
    "TelegramIntelMessage": [
        "data/telegram_intel/*/messages.jsonl",
    ],
    "HyperliquidSignal": [
        "data/hyperliquid_signals.jsonl",
    ],
    "OODAPacket": [
        "data/gemini_ooda/*.json",
    ],
    "ThreatIndicator": [
        "data/intelligence/*/threats.json",
        "data/threat_intel/*.md",
    ],
}

# Watermark files live under ~/.cache/sapphire/foundry_sync/<type>.json. The
# watermark records the last-synced ``last_seen`` timestamp the transform
# observed. The sync engine keeps using the file mtime+hash delta detection
# for change scheduling, but emits + persists watermarks per type so external
# consumers (dashboards, audits) can answer "when did Foundry last see N
# records of type X?" without joining state files together.


def watermark_path(object_type: str, *, base_dir: Path | None = None) -> Path:
    """Return the per-type watermark file path."""
    base = base_dir or _WATERMARK_DIR
    return base / f"{object_type}.json"


def load_watermark(object_type: str, *, base_dir: Path | None = None) -> dict[str, Any]:
    """Load the watermark for ``object_type``. Returns ``{}`` if missing/corrupt."""
    path = watermark_path(object_type, base_dir=base_dir)
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            return data
    except (OSError, json.JSONDecodeError):
        return {}
    return {}


def write_watermark(
    object_type: str,
    *,
    last_synced_at: str,
    object_count: int,
    base_dir: Path | None = None,
    extra: dict[str, Any] | None = None,
) -> Path:
    """Persist a watermark for ``object_type`` and return the path written."""
    path = watermark_path(object_type, base_dir=base_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload: dict[str, Any] = {
        "object_type": object_type,
        "last_synced_at": last_synced_at,
        "object_count": int(object_count),
    }
    if extra:
        payload.update(extra)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str))
    tmp.replace(path)
    return path


def _repo_root() -> Path:
    override = os.getenv("SAPPHIRE_REPO_ROOT")
    if override:
        return Path(override).expanduser()

    home_repo = Path.home() / "Code" / "Sapphire"
    local_repo = Path(__file__).resolve().parents[2]
    for c in (local_repo, home_repo):
        if (c / "lib" / "foundry").exists() or (c / "AGENTS.md").exists():
            return c
    return local_repo


# ---------------------------------------------------------------------------
# Delta detection
# ---------------------------------------------------------------------------


@dataclass
class SyncState:
    """Tracks file modification times and content hashes between syncs.

    ``first_success_at`` and ``last_auth_warning_at`` are used to rate-limit
    Telegram alerts: a sync that has never succeeded once should not page the
    user every 15 minutes about misconfiguration, and auth errors should warn
    at most once per day until resolved.
    """

    files: dict[str, dict[str, Any]] = field(default_factory=dict)
    last_sync: str | None = None
    last_status: str = "never"
    sync_count: int = 0
    first_success_at: str | None = None
    last_auth_warning_at: str | None = None

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(
                {
                    "files": self.files,
                    "last_sync": self.last_sync,
                    "last_status": self.last_status,
                    "sync_count": self.sync_count,
                    "first_success_at": self.first_success_at,
                    "last_auth_warning_at": self.last_auth_warning_at,
                },
                indent=2,
                default=str,
            )
        )

    @classmethod
    def load(cls, path: Path) -> SyncState:
        if not path.is_file():
            return cls()
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return cls(
                files=data.get("files", {}),
                last_sync=data.get("last_sync"),
                last_status=data.get("last_status", "unknown"),
                sync_count=data.get("sync_count", 0),
                first_success_at=data.get("first_success_at"),
                last_auth_warning_at=data.get("last_auth_warning_at"),
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
                if (
                    prev is None
                    or prev.get("hash") != finfo.get("hash")
                    or prev.get("mtime") != finfo.get("mtime")
                ):
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
    write_envelope_sidecar(
        history_path,
        generator="lib.foundry.sync",
        metadata={"artifact_family": "foundry_sync_history"},
    )


def load_sync_history(root: Path | None = None, *, limit: int = 50) -> list[dict[str, Any]]:
    """Read the last *limit* sync history entries."""
    root = root or _repo_root()
    history_path = root / _HISTORY_FILE
    if not history_path.is_file():
        return []
    entries: list[dict[str, Any]] = []
    try:
        for line in history_path.read_text(encoding="utf-8").strip().split("\n"):
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

    import ssl
    import urllib.request

    ctx = ssl.create_default_context()
    try:
        import certifi

        ctx.load_verify_locations(certifi.where())
    except ImportError:
        pass

    try:
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        data = json.dumps({"chat_id": chat_id, "text": message, "parse_mode": "Markdown"}).encode()
        req = urllib.request.Request(
            url, data=data, headers={"Content-Type": "application/json"}, method="POST"
        )
        urllib.request.urlopen(req, timeout=10, context=ctx)  # nosec B310 - fixed Telegram HTTPS API base.
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
    5. Alert only on real upload failures after a prior successful connection
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
    watermark_base = Path(
        os.environ.get("SAPPHIRE_FOUNDRY_WATERMARK_DIR", str(_WATERMARK_DIR))
    ).expanduser()

    for obj_type in types_to_sync:
        fn = ALL_TRANSFORMS.get(obj_type)
        if fn is None:
            continue
        try:
            objects = fn(root)
            objects_by_type[obj_type] = objects
            # Watermark every transform that ran without crashing (even an
            # empty result is meaningful: "we looked, the source had nothing
            # new"). This is independent of upload outcome so consumers can
            # tell when ingestion last touched the source even if Foundry
            # itself is unreachable.
            try:
                write_watermark(
                    obj_type,
                    last_synced_at=now,
                    object_count=len(objects),
                    base_dir=watermark_base,
                    extra={
                        "changed_files": changes.get(obj_type, []),
                        "force": bool(force),
                    },
                )
            except OSError as wm_exc:
                log.warning("Failed to write watermark for %s: %s", obj_type, wm_exc)
        except Exception as exc:
            log.exception("Transform %s failed", obj_type)
            result.errors.append(f"Transform {obj_type}: {exc}")

    # 3. Upload
    config_missing = False
    auth_failed = False
    uploaded_anything = False
    if not dry_run:
        from lib.foundry.client import (
            FoundryAPIError,
            FoundryAuthError,
            FoundryClient,
            FoundryConfigError,
            FoundryError,
        )

        try:
            client = FoundryClient.from_env()
            target_types = [obj_type for obj_type, objects in objects_by_type.items() if objects]
            client.validate_write_target(target_types)
        except FoundryConfigError as exc:
            # No URL or credentials yet. This is expected before the user has
            # provisioned Foundry — log once and bail without paging Telegram.
            config_missing = True
            log.info("Foundry not configured, skipping sync: %s", exc)
            client = None
        except FoundryError as exc:
            log.error("Foundry client init failed: %s", exc)
            result.errors.append(f"Client init: {exc}")
            client = None

        if client is not None:
            # A 404 on the upsert action means the ontology/action pair hasn't
            # been deployed on Foundry yet — it's a setup step, not a runtime
            # failure. Downgrade the log level so the error file doesn't fill
            # with one identical ERROR line per 15-min cycle while Ari is still
            # provisioning the ontology.
            #
            # IMPORTANT (codex review #106): only demote 404s while the sync
            # has *never* succeeded. Once `state.first_success_at` is set, the
            # ontology has existed before, so a fresh 404 is a real regression
            # (action deleted / renamed / permissions revoked) and must stay at
            # ERROR + Telegram-alerting. Otherwise a broken prod ontology
            # silently looks like "skipped, no problem here".
            never_succeeded = state.first_success_at is None
            saw_404 = False
            saw_non_404_failure = False  # includes auth, non-404 API, generic FoundryError
            for obj_type, objects in objects_by_type.items():
                if not objects:
                    continue
                try:
                    if client.write_mode == "dataset":
                        client.upload_dataset_objects(obj_type, objects)
                    else:
                        client.upsert_objects(obj_type, objects)
                    result.uploaded_types[obj_type] = len(objects)
                    uploaded_anything = True
                    log.info("Uploaded %d %s objects", len(objects), obj_type)
                except FoundryAuthError as exc:
                    auth_failed = True
                    saw_non_404_failure = True
                    result.errors.append(f"Upload {obj_type}: {exc}")
                    log.error("Upload %s auth failed: %s", obj_type, exc)
                    break  # Don't hammer failing auth on every object type.
                except FoundryAPIError as exc:
                    result.errors.append(f"Upload {obj_type}: {exc}")
                    if (
                        client.write_mode == "action"
                        and exc.status == 404
                        and not uploaded_anything
                        and never_succeeded
                    ):
                        saw_404 = True
                        log.info(
                            "Upload %s skipped (ontology action not deployed; "
                            "HTTP 404) — finish Foundry ontology provisioning to enable",
                            obj_type,
                        )
                    else:
                        saw_non_404_failure = True
                        log.error("Upload %s failed: %s", obj_type, exc)
                except FoundryError as exc:
                    saw_non_404_failure = True
                    log.error("Upload %s failed: %s", obj_type, exc)
                    result.errors.append(f"Upload {obj_type}: {exc}")
            # Only demote to not_configured when EVERY failure was a pre-first-
            # success 404. If the batch mixed a 404 with any other failure
            # (500, timeout, auth, etc.), the run is a genuine error and must
            # alert through the standard path — not be silently swallowed.
            # (codex review #106 P1 follow-up: r3117240955)
            if saw_404 and not saw_non_404_failure and not uploaded_anything and never_succeeded:
                config_missing = True
    else:
        for obj_type, objects in objects_by_type.items():
            result.uploaded_types[obj_type] = len(objects)
            log.info("[DRY RUN] Would upload %d %s objects", len(objects), obj_type)

    # 4. Update state
    if config_missing:
        # Treat an unconfigured stack as a successful no-op skip — we did what
        # we could, and we don't want the sync to exit non-zero and trigger
        # LaunchAgent restart backoff.
        result.skipped = True
        result.ok = True
    else:
        result.ok = len(result.errors) == 0
    result.duration_s = time.monotonic() - t0

    state.files = current_files
    state.last_sync = now
    if config_missing:
        state.last_status = "not_configured"
    elif result.ok:
        state.last_status = "ok"
    else:
        state.last_status = "error"
    state.sync_count += 1
    if uploaded_anything and not state.first_success_at:
        state.first_success_at = now
    state.save(state_path)

    # 5. History
    _append_history(root, result.to_dict())

    # 6. Alert on failure — but only when it's a real data-sync problem.
    #    * Missing config: no alert, user hasn't finished provisioning.
    #    * Auth failure before first success: warn at most once per 24h.
    #    * Other upload errors after a prior success: page as before.
    if not result.ok and not config_missing and result.errors:
        first_success = state.first_success_at
        auth_warn_fresh = _auth_warning_fresh(state.last_auth_warning_at, now)
        if auth_failed and not first_success:
            if not auth_warn_fresh:
                log.warning(
                    "Foundry auth failing and sync has never connected — "
                    "check token/URL. (Telegram alert suppressed until first "
                    "successful sync.)"
                )
                state.last_auth_warning_at = now
                state.save(state_path)
            # Suppress Telegram to avoid a 15-min spam loop on bad creds.
        elif first_success:
            msg = (
                f"⚠️ *Foundry Sync Failed*\n"
                f"Time: {now}\n"
                f"Errors: {len(result.errors)}\n"
                f"{''.join(f'• {e}' + chr(10) for e in result.errors[:5])}"
            )
            _send_telegram_alert(msg)
        else:
            # Transform or misc error before first success — log but don't page.
            log.warning(
                "Foundry sync errors before first successful connection: %s",
                result.errors[:3],
            )

    return result


def _auth_warning_fresh(last_iso: str | None, now_iso: str) -> bool:
    """Return True if the last auth warning was emitted within the last 24h."""
    if not last_iso:
        return False
    try:
        last = datetime.fromisoformat(last_iso)
        now = datetime.fromisoformat(now_iso)
    except ValueError:
        return False
    return (now - last).total_seconds() < 24 * 3600


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
    parser.add_argument(
        "--interval", type=int, default=_DEFAULT_INTERVAL, help="Sync interval in seconds"
    )
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
