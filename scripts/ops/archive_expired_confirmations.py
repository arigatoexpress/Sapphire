#!/usr/bin/env python3
"""Archive expired confirmation-firewall pending files.

Default mode is dry-run. The report intentionally prints only paste-safe
metadata: code, risk, status, timestamps, field presence, and file hashes. Raw
actions/details stay inside the local file and are never rendered.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from firewall_status_report import default_state_dir  # noqa: E402


def archive_expired_confirmations(
    *,
    state_dir: Path | None = None,
    archive_dir: Path | None = None,
    apply: bool = False,
    now: float | None = None,
) -> dict[str, Any]:
    """Return a paste-safe archive report; move files only when apply=True."""
    state_dir = (state_dir or default_state_dir()).expanduser()
    pending_dir = state_dir / "pending_confirmations"
    cutoff = time.time() if now is None else now
    archive_dir = (archive_dir or state_dir / "archived_pending_confirmations").expanduser()

    entries: list[dict[str, Any]] = []
    if not pending_dir.exists():
        return _report(state_dir, archive_dir, apply=apply, entries=entries)

    for path in sorted(pending_dir.glob("*.json")):
        record = _load_json(path)
        if record is None:
            continue
        expires = _float_or_none(record.get("expires"))
        if expires is None or cutoff <= expires:
            continue

        entry = _safe_entry(record, path=path, now=cutoff, expires=expires)
        if apply:
            destination = _destination_for(path, archive_dir)
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(path), str(destination))
            entry["archived"] = True
            entry["destination_hash"] = _hash_text(str(destination.relative_to(archive_dir)))
        else:
            entry["archived"] = False
        entries.append(entry)

    return _report(state_dir, archive_dir, apply=apply, entries=entries)


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Expired Confirmation Archive",
        "",
        f"- Generated: {report['generated_at']}",
        f"- Mode: {'apply' if report['applied'] else 'dry-run'}",
        f"- Expired files matched: {report['matched_count']}",
        f"- Archived files: {report['archived_count']}",
        "- Scope: paste-safe metadata only; raw actions/details are not rendered.",
        "",
    ]
    if not report["entries"]:
        lines.append("No expired pending confirmation files matched.")
        return "\n".join(lines) + "\n"

    lines.extend(
        [
            "| Code | Risk | Status | Expired | Seconds Expired | Archived | Action Field | Details Field |",
            "|---|---|---|---:|---:|---:|---:|---:|",
        ]
    )
    for item in report["entries"]:
        lines.append(
            f"| {item['code']} | {item['risk']} | {item['status']} | "
            f"{item.get('expires') or '-'} | {item.get('seconds_expired') or 0} | "
            f"{_yn(item.get('archived'))} | {_yn(item.get('has_action'))} | "
            f"{_yn(item.get('has_details'))} |"
        )
    return "\n".join(lines) + "\n"


def _report(
    state_dir: Path,
    archive_dir: Path,
    *,
    apply: bool,
    entries: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "state_dir": str(state_dir),
        "archive_dir": str(archive_dir),
        "applied": apply,
        "matched_count": len(entries),
        "archived_count": sum(1 for item in entries if item.get("archived")),
        "entries": entries,
    }


def _load_json(path: Path) -> dict[str, Any] | None:
    try:
        parsed = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    return parsed if isinstance(parsed, dict) else None


def _safe_entry(
    record: dict[str, Any],
    *,
    path: Path,
    now: float,
    expires: float,
) -> dict[str, Any]:
    return {
        "code": str(record.get("code") or path.stem).upper(),
        "file_hash": _hash_text(path.name),
        "risk": str(record.get("risk") or "unknown"),
        "status": str(record.get("status") or "pending"),
        "created": _iso_from_epoch(record.get("created")),
        "expires": _iso_from_epoch(expires),
        "seconds_expired": max(0, int(now - expires)),
        "has_action": "action" in record,
        "has_details": "details" in record,
    }


def _destination_for(path: Path, archive_dir: Path) -> Path:
    destination = archive_dir / path.name
    if not destination.exists():
        return destination
    stem = path.stem
    suffix = path.suffix
    digest = _hash_text(path.name)
    return archive_dir / f"{stem}-{digest}{suffix}"


def _float_or_none(value: object) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _iso_from_epoch(value: object) -> str | None:
    ts = _float_or_none(value)
    if ts is None:
        return None
    return datetime.fromtimestamp(ts, UTC).isoformat(timespec="seconds")


def _hash_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]


def _yn(value: object) -> str:
    return "yes" if bool(value) else "no"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state-dir", type=Path, default=default_state_dir())
    parser.add_argument("--archive-dir", type=Path, default=None)
    parser.add_argument("--apply", action="store_true", help="Move expired files into archive-dir")
    parser.add_argument("--json", action="store_true", help="Emit JSON instead of Markdown")
    args = parser.parse_args(argv)

    report = archive_expired_confirmations(
        state_dir=args.state_dir,
        archive_dir=args.archive_dir,
        apply=args.apply,
    )
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(render_markdown(report), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
