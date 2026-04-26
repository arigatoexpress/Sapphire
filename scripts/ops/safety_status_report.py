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
import re
import sys
from collections import Counter
from collections.abc import Mapping, Sequence
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

SECRET_TEXT_PATTERNS = (
    re.compile(r"(?i)\b(api[_-]?key|token|password|secret|private[_-]?key)\s*[:=]\s*[^,\s]+"),
    re.compile(r"(?i)\b(bearer)\s+[a-z0-9._~+/=-]+"),
)
SECRET_KEY_RE = re.compile(
    r"(api[_-]?key|token|password|passwd|secret|private[_-]?key|credential|authorization)",
    re.IGNORECASE,
)
AUTONOMY_REQUIRED_FIELDS = ("event_type", "ts", "actor", "action", "outcome")


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


def summarize_autonomy_audit(
    audit_path: Path,
    *,
    recent: int = 10,
) -> dict[str, Any]:
    """Return paste-safe autonomy audit counts and recent event metadata."""
    audit_path = audit_path.expanduser()
    if not audit_path.exists():
        return {
            "audit_exists": False,
            "schema": _empty_autonomy_schema(),
            "event_counts": {},
            "actor_counts": {},
            "outcome_counts": {},
            "risk_counts": {},
            "recent_events": [],
        }

    records: list[dict[str, Any]] = []
    malformed_lines = 0
    missing_required: Counter[str] = Counter()
    unredacted_secret_risk_records = 0
    lines = audit_path.read_text(encoding="utf-8").splitlines()
    for line in lines:
        try:
            parsed = json.loads(line)
        except json.JSONDecodeError:
            malformed_lines += 1
            continue
        if isinstance(parsed, dict):
            records.append(parsed)
            for field in AUTONOMY_REQUIRED_FIELDS:
                if parsed.get(field) in (None, ""):
                    missing_required[field] += 1
            if _contains_unredacted_secret_like_value(parsed):
                unredacted_secret_risk_records += 1
        else:
            malformed_lines += 1

    return {
        "audit_exists": True,
        "schema": {
            "total_lines": len(lines),
            "valid_records": len(records),
            "malformed_lines": malformed_lines,
            "missing_required_fields": dict(sorted(missing_required.items())),
            "unredacted_secret_risk_records": unredacted_secret_risk_records,
        },
        "event_counts": dict(Counter(_safe_text(record.get("event_type")) for record in records)),
        "actor_counts": dict(Counter(_safe_text(record.get("actor")) for record in records)),
        "outcome_counts": dict(Counter(_safe_text(record.get("outcome")) for record in records)),
        "risk_counts": dict(Counter(_safe_text(record.get("risk") or "none") for record in records)),
        "recent_events": [_safe_autonomy_event(record) for record in records[-max(0, recent) :]],
    }


def build_report(
    *,
    state_dir: Path | None = None,
    firewall_audit_path: Path | None = None,
    kill_switch_audit_path: Path | None = None,
    autonomy_audit_path: Path | None = None,
    recent: int = 10,
    now: float | None = None,
) -> dict[str, Any]:
    """Build a combined read-only safety-control report."""
    state_dir = (state_dir or default_state_dir()).expanduser()
    kill_switch_audit_path = kill_switch_audit_path or state_dir / "audit" / "kill_switch.jsonl"
    autonomy_audit_path = autonomy_audit_path or state_dir / "audit" / "autonomy.jsonl"
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
        "autonomy_audit": summarize_autonomy_audit(
            autonomy_audit_path,
            recent=recent,
        ),
    }


def render_markdown(report: dict[str, Any]) -> str:
    firewall = report["confirmation_firewall"]
    kill_switch = report["kill_switch"]
    autonomy = report["autonomy_audit"]
    lines = [
        "# Sapphire Safety Status",
        "",
        f"- Generated: {report['generated_at']}",
        "- Scope: read-only local audit metadata; no raw actions, reasons, object refs, values, or payloads.",
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

    lines.extend(
        [
            "",
            "## Autonomy Audit",
            "",
            f"- Audit log present: {_yn(autonomy['audit_exists'])}",
            f"- Schema: {autonomy['schema']['valid_records']} valid records / "
            f"{autonomy['schema']['total_lines']} lines; "
            f"{autonomy['schema']['malformed_lines']} malformed; "
            f"{autonomy['schema']['unredacted_secret_risk_records']} unredacted secret-risk records",
            f"- Missing required fields: {json.dumps(autonomy['schema']['missing_required_fields'], sort_keys=True)}",
            f"- Event counts: {json.dumps(autonomy['event_counts'], sort_keys=True)}",
            f"- Risk counts: {json.dumps(autonomy['risk_counts'], sort_keys=True)}",
            "",
            "## Recent Autonomy Events",
            "",
        ]
    )
    if autonomy["recent_events"]:
        lines.extend(
            [
                "| Time | Event | Actor | Outcome | Risk | Object Hash | Metadata Keys |",
                "|---|---|---|---|---|---|---|",
            ]
        )
        for item in autonomy["recent_events"]:
            lines.append(
                f"| {item.get('ts') or '-'} | {item.get('event_type', '-')} | "
                f"{item.get('actor', '-')} | {item.get('outcome', '-')} | "
                f"{item.get('risk', '-')} | {item.get('object_ref_hash') or '-'} | "
                f"{', '.join(item.get('metadata_keys') or []) or '-'} |"
            )
    else:
        lines.append("No recent autonomy audit events.")
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


def _safe_autonomy_event(record: dict[str, Any]) -> dict[str, Any]:
    object_ref = str(record.get("object_ref") or "")
    action = str(record.get("action") or "")
    metadata = record.get("metadata") if isinstance(record.get("metadata"), dict) else {}
    event = {
        "event_type": _safe_text(record.get("event_type")),
        "ts": _safe_timestamp(record.get("ts")),
        "actor": _safe_text(record.get("actor")),
        "outcome": _safe_text(record.get("outcome")),
        "risk": _safe_text(record.get("risk") or "none"),
        "metadata_keys": sorted(_safe_text(key, max_len=60) for key in metadata),
        "metadata_key_count": len(metadata),
    }
    if action:
        event["action_hash"] = hashlib.sha256(action.encode("utf-8")).hexdigest()[:12]
        event["action_chars"] = len(action)
    else:
        event["action_hash"] = ""
        event["action_chars"] = 0
    if object_ref:
        event["object_ref_hash"] = hashlib.sha256(object_ref.encode("utf-8")).hexdigest()[:12]
        event["object_ref_chars"] = len(object_ref)
    else:
        event["object_ref_hash"] = ""
        event["object_ref_chars"] = 0
    return event


def _empty_autonomy_schema() -> dict[str, Any]:
    return {
        "total_lines": 0,
        "valid_records": 0,
        "malformed_lines": 0,
        "missing_required_fields": {},
        "unredacted_secret_risk_records": 0,
    }


def _contains_unredacted_secret_like_value(value: Any) -> bool:
    if value is None or isinstance(value, bool | int | float):
        return False
    if isinstance(value, str):
        return _text_has_unredacted_secret(value)
    if isinstance(value, Mapping):
        for key, item in value.items():
            if SECRET_KEY_RE.search(str(key)) and _non_redacted_secret_value(item):
                return True
            if _contains_unredacted_secret_like_value(item):
                return True
        return False
    if isinstance(value, Sequence) and not isinstance(value, bytes | bytearray):
        return any(_contains_unredacted_secret_like_value(item) for item in value)
    return _text_has_unredacted_secret(str(value))


def _non_redacted_secret_value(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        text = value.strip().lower()
        return bool(text and text not in {"<redacted>", "redacted"} and "<redacted>" not in text)
    return True


def _text_has_unredacted_secret(text: str) -> bool:
    for pattern in SECRET_TEXT_PATTERNS:
        for match in pattern.finditer(text):
            matched = match.group(0).lower()
            if "<redacted>" not in matched and "_redacted" not in matched:
                return True
    return False


def _event_type(record: dict[str, Any]) -> str:
    event_type = str(record.get("event_type") or "")
    if event_type:
        return event_type
    kind = str(record.get("kind") or "")
    if kind:
        return f"kill_switch.{kind}"
    return "unknown"


def _safe_timestamp(value: object) -> str:
    ts = _float_or_none(value)
    if ts is not None:
        return datetime.fromtimestamp(ts, UTC).isoformat(timespec="seconds")
    return _safe_text(value, max_len=80)


def _safe_text(value: object, *, max_len: int = 120) -> str:
    text = " ".join(str(value or "").split())
    for pattern in SECRET_TEXT_PATTERNS:
        text = pattern.sub(lambda match: f"{match.group(1)}=<redacted>", text)
    if len(text) > max_len:
        text = text[: max_len - 3] + "..."
    return text


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
    parser.add_argument("--autonomy-audit-path", type=Path, default=None)
    parser.add_argument("--recent", type=int, default=10)
    parser.add_argument("--json", action="store_true", help="Emit JSON instead of Markdown")
    args = parser.parse_args(argv)

    report = build_report(
        state_dir=args.state_dir,
        firewall_audit_path=args.firewall_audit_path,
        kill_switch_audit_path=args.kill_switch_audit_path,
        autonomy_audit_path=args.autonomy_audit_path,
        recent=args.recent,
    )
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(render_markdown(report), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
