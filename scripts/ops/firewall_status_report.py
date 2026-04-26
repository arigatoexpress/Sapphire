#!/usr/bin/env python3
"""Read-only confirmation firewall status report.

The report intentionally avoids rendering pending action text, details, raw
Telegram payloads, or any secret-like values. It shows only operator-safe
metadata needed to understand whether the firewall is waiting on a reply.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

DEFAULT_STATE_DIR = Path.home() / ".sapphire"
SAFE_AUDIT_FIELDS = ("event_type", "risk", "status", "code", "reason")


def default_state_dir() -> Path:
    return Path(os.environ.get("SAPPHIRE_STATE_DIR", DEFAULT_STATE_DIR)).expanduser()


def load_pending_confirmations(
    state_dir: Path,
    *,
    now: float | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Return active and expired pending confirmation metadata."""
    pending_dir = state_dir / "pending_confirmations"
    if not pending_dir.exists():
        return [], []

    cutoff = time.time() if now is None else now
    active: list[dict[str, Any]] = []
    expired: list[dict[str, Any]] = []
    for path in sorted(pending_dir.glob("*.json")):
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue

        expires = _float_or_none(record.get("expires"))
        if expires and cutoff > expires:
            expired.append(_safe_expired_pending(record, path=path, now=cutoff, expires=expires))
            continue
        if record.get("status", "pending") != "pending":
            continue

        active.append(
            {
                "code": str(record.get("code") or path.stem).upper(),
                "risk": str(record.get("risk") or "unknown"),
                "status": "pending",
                "created": _iso_from_epoch(record.get("created")),
                "expires": _iso_from_epoch(record.get("expires")),
                "seconds_until_expiry": (
                    max(0, int(expires - cutoff)) if expires is not None else None
                ),
            }
        )
    return active, expired


def load_recent_audit_events(audit_path: Path, *, limit: int) -> list[dict[str, Any]]:
    """Load recent audit metadata without raw action/details fields."""
    if limit <= 0 or not audit_path.exists():
        return []

    lines = audit_path.read_text(encoding="utf-8").splitlines()
    events: list[dict[str, Any]] = []
    for line in lines[-limit:]:
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        event = {field: record[field] for field in SAFE_AUDIT_FIELDS if field in record}
        if "ts" in record:
            event["ts"] = _iso_from_epoch(record["ts"])
        events.append(event)
    return events


def build_report(
    *,
    state_dir: Path | None = None,
    audit_path: Path | None = None,
    recent: int = 10,
    now: float | None = None,
) -> dict[str, Any]:
    state_dir = (state_dir or default_state_dir()).expanduser()
    audit_path = audit_path or state_dir / "audit" / "confirmation_firewall.jsonl"
    pending, expired = load_pending_confirmations(state_dir, now=now)
    expired_visible = expired[-max(0, recent) :] if recent > 0 else []
    return {
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "state_dir": str(state_dir),
        "pending_count": len(pending),
        "expired_pending_count": len(expired),
        "expired_pending": expired_visible,
        "expired_pending_omitted": max(0, len(expired) - len(expired_visible)),
        "pending": pending,
        "recent_audit": load_recent_audit_events(audit_path.expanduser(), limit=recent),
    }


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Confirmation Firewall Status",
        "",
        f"- Generated: {report['generated_at']}",
        f"- Pending: {report['pending_count']}",
        f"- Expired pending files: {report['expired_pending_count']}",
        "",
        "## Pending",
        "",
    ]
    if report["pending"]:
        lines.extend(["| Code | Risk | Expires | Seconds |", "|---|---|---:|---:|"])
        for item in report["pending"]:
            lines.append(
                f"| {item['code']} | {item['risk']} | "
                f"{item.get('expires') or '-'} | {item.get('seconds_until_expiry') or 0} |"
            )
    else:
        lines.append("No active pending confirmations.")

    lines.extend(["", "## Expired Pending Files", ""])
    if report.get("expired_pending"):
        lines.extend(
            [
                "| Code | Risk | Status | Created | Expired | Seconds Expired | Action Field | Details Field |",
                "|---|---|---|---:|---:|---:|---:|---:|",
            ]
        )
        for item in report["expired_pending"]:
            lines.append(
                f"| {item['code']} | {item['risk']} | {item['status']} | "
                f"{item.get('created') or '-'} | {item.get('expires') or '-'} | "
                f"{item.get('seconds_expired') or 0} | {_yn(item.get('has_action'))} | "
                f"{_yn(item.get('has_details'))} |"
            )
        omitted = int(report.get("expired_pending_omitted") or 0)
        if omitted:
            lines.append(f"\n{omitted} additional expired pending files omitted.")
    else:
        lines.append("No expired pending files.")

    lines.extend(["", "## Recent Audit", ""])
    if report["recent_audit"]:
        lines.extend(["| Time | Event | Risk | Status | Code |", "|---|---|---|---|---|"])
        for item in report["recent_audit"]:
            lines.append(
                f"| {item.get('ts', '-')} | {item.get('event_type', '-')} | "
                f"{item.get('risk', '-')} | {item.get('status', '-')} | "
                f"{item.get('code', '-')} |"
            )
    else:
        lines.append("No recent audit events.")
    return "\n".join(lines) + "\n"


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


def _safe_expired_pending(
    record: dict[str, Any],
    *,
    path: Path,
    now: float,
    expires: float,
) -> dict[str, Any]:
    """Return paste-safe metadata for an expired pending confirmation file."""
    code = str(record.get("code") or path.stem).upper()
    return {
        "code": code,
        "file_hash": hashlib.sha256(path.name.encode("utf-8")).hexdigest()[:12],
        "risk": str(record.get("risk") or "unknown"),
        "status": str(record.get("status") or "pending"),
        "created": _iso_from_epoch(record.get("created")),
        "expires": _iso_from_epoch(expires),
        "seconds_expired": max(0, int(now - expires)),
        "has_action": "action" in record,
        "has_details": "details" in record,
    }


def _yn(value: object) -> str:
    return "yes" if bool(value) else "no"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state-dir", type=Path, default=default_state_dir())
    parser.add_argument("--audit-path", type=Path, default=None)
    parser.add_argument("--recent", type=int, default=10)
    parser.add_argument("--json", action="store_true", help="Emit JSON instead of Markdown")
    args = parser.parse_args(argv)

    report = build_report(
        state_dir=args.state_dir,
        audit_path=args.audit_path,
        recent=args.recent,
    )
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(render_markdown(report), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
