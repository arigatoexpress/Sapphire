#!/usr/bin/env python3
"""Read-only safety-control status report for Sapphire.

This combines confirmation-firewall queue metadata with kill-switch audit
state. It intentionally omits raw pending action text, Telegram payloads,
portfolio values, and free-form kill-switch reasons so the report can be pasted
into operator channels without leaking secrets or sensitive context.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from firewall_status_report import (  # noqa: E402
    build_report as build_firewall_report,
)
from firewall_status_report import (
    default_state_dir,
)


def load_kill_switch_events(audit_path: Path, *, limit: int) -> list[dict[str, Any]]:
    """Load recent kill-switch audit metadata without raw reason/value fields."""
    if limit <= 0 or not audit_path.exists():
        return []

    events: list[dict[str, Any]] = []
    for line in audit_path.read_text(encoding="utf-8").splitlines()[-limit:]:
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        events.append(_safe_kill_switch_event(record))
    return events


def summarize_kill_switch(
    audit_path: Path,
    *,
    recent: int = 10,
) -> dict[str, Any]:
    """Return inferred kill-switch state from the append-only audit log."""
    audit_path = audit_path.expanduser()
    if not audit_path.exists():
        return {
            "audit_exists": False,
            "inferred_active": None,
            "last_transition": None,
            "event_counts": {},
            "recent_events": [],
        }

    records: list[dict[str, Any]] = []
    for line in audit_path.read_text(encoding="utf-8").splitlines():
        try:
            parsed = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            records.append(parsed)

    transitions = [
        record
        for record in records
        if _event_type(record) in {"kill_switch.activated", "kill_switch.deactivated"}
    ]
    last_transition = _safe_kill_switch_event(transitions[-1]) if transitions else None
    inferred_active = None
    if last_transition:
        inferred_active = last_transition["event_type"] == "kill_switch.activated"

    return {
        "audit_exists": True,
        "inferred_active": inferred_active,
        "last_transition": last_transition,
        "event_counts": dict(Counter(_event_type(record) for record in records)),
        "recent_events": [_safe_kill_switch_event(record) for record in records[-max(0, recent) :]],
    }


def build_report(
    *,
    state_dir: Path | None = None,
    firewall_audit_path: Path | None = None,
    kill_switch_audit_path: Path | None = None,
    recent: int = 10,
    now: float | None = None,
) -> dict[str, Any]:
    """Build a combined read-only safety-control report."""
    state_dir = (state_dir or default_state_dir()).expanduser()
    kill_switch_audit_path = kill_switch_audit_path or state_dir / "audit" / "kill_switch.jsonl"
    return {
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "state_dir": str(state_dir),
        "confirmation_firewall": build_firewall_report(
            state_dir=state_dir,
            audit_path=firewall_audit_path,
            recent=recent,
            now=now,
        ),
        "kill_switch": summarize_kill_switch(
            kill_switch_audit_path,
            recent=recent,
        ),
    }


def render_markdown(report: dict[str, Any]) -> str:
    firewall = report["confirmation_firewall"]
    kill_switch = report["kill_switch"]
    lines = [
        "# Sapphire Safety Status",
        "",
        f"- Generated: {report['generated_at']}",
        "- Scope: read-only local audit metadata; no raw actions, reasons, values, or payloads.",
        "",
        "## Confirmation Firewall",
        "",
        f"- Pending: {firewall['pending_count']}",
        f"- Expired pending files: {firewall['expired_pending_count']}",
    ]

    if firewall["pending"]:
        lines.extend(["", "| Code | Risk | Expires | Seconds |", "|---|---|---:|---:|"])
        for item in firewall["pending"]:
            lines.append(
                f"| {item['code']} | {item['risk']} | "
                f"{item.get('expires') or '-'} | {item.get('seconds_until_expiry') or 0} |"
            )
    else:
        lines.extend(["", "No active pending confirmations."])

    lines.extend(
        [
            "",
            "## Kill Switch",
            "",
            f"- Audit log present: {_yn(kill_switch['audit_exists'])}",
            f"- Inferred active: {_maybe_yn(kill_switch['inferred_active'])}",
        ]
    )
    last = kill_switch.get("last_transition")
    if last:
        lines.append(
            f"- Last transition: `{last['event_type']}` at `{last.get('timestamp') or '-'}`"
        )
    else:
        lines.append("- Last transition: none")

    lines.extend(["", "## Recent Kill-Switch Events", ""])
    if kill_switch["recent_events"]:
        lines.extend(
            [
                "| Time | Event | Reason Hash | Reason Chars | 24h DD | Total DD |",
                "|---|---|---|---:|---:|---:|",
            ]
        )
        for item in kill_switch["recent_events"]:
            lines.append(
                f"| {item.get('timestamp') or '-'} | {item.get('event_type', '-')} | "
                f"{item.get('reason_hash') or '-'} | {item.get('reason_chars', 0)} | "
                f"{_pct(item.get('drawdown_24h'))} | {_pct(item.get('drawdown_total'))} |"
            )
    else:
        lines.append("No recent kill-switch events.")
    return "\n".join(lines) + "\n"


def _safe_kill_switch_event(record: dict[str, Any]) -> dict[str, Any]:
    reason = str(record.get("reason") or "")
    event = {
        "event_type": _event_type(record),
        "kind": str(record.get("kind") or ""),
        "timestamp": str(record.get("timestamp") or ""),
        "drawdown_24h": _float_or_none(record.get("drawdown_24h")),
        "drawdown_total": _float_or_none(record.get("drawdown_total")),
        "portfolio_value_present": "portfolio_value" in record,
    }
    if reason:
        event["reason_hash"] = hashlib.sha256(reason.encode("utf-8")).hexdigest()[:12]
        event["reason_chars"] = len(reason)
    else:
        event["reason_hash"] = ""
        event["reason_chars"] = 0
    return event


def _event_type(record: dict[str, Any]) -> str:
    event_type = str(record.get("event_type") or "")
    if event_type:
        return event_type
    kind = str(record.get("kind") or "")
    if kind:
        return f"kill_switch.{kind}"
    return "unknown"


def _float_or_none(value: object) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _pct(value: object) -> str:
    number = _float_or_none(value)
    if number is None:
        return "-"
    return f"{number:.2%}"


def _yn(value: bool) -> str:
    return "yes" if value else "no"


def _maybe_yn(value: bool | None) -> str:
    if value is None:
        return "unknown"
    return _yn(value)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state-dir", type=Path, default=default_state_dir())
    parser.add_argument("--firewall-audit-path", type=Path, default=None)
    parser.add_argument("--kill-switch-audit-path", type=Path, default=None)
    parser.add_argument("--recent", type=int, default=10)
    parser.add_argument("--json", action="store_true", help="Emit JSON instead of Markdown")
    args = parser.parse_args(argv)

    report = build_report(
        state_dir=args.state_dir,
        firewall_audit_path=args.firewall_audit_path,
        kill_switch_audit_path=args.kill_switch_audit_path,
        recent=args.recent,
    )
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(render_markdown(report), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
