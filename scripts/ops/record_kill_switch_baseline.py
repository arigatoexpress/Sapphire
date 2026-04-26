#!/usr/bin/env python3
"""Record an explicit kill-switch operator baseline without toggling state.

This tool is intentionally *not* a kill/resume command. It appends a
``kill_switch.operator_baseline`` event so the safety report can distinguish an
operator-observed baseline from a missing audit log. It never sends Telegram,
publishes events, or mutates the in-process kill-switch singleton.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    audit_path = resolve_audit_path(args.state_dir, args.audit_path)
    observed_active = args.observed_active == "true"
    result = build_result(
        audit_path=audit_path,
        observed_active=observed_active,
        apply=args.apply,
        force=args.force,
    )
    rendered = json.dumps(result, indent=2, sort_keys=True) + "\n" if args.json else render(result)
    print(rendered, end="")
    return int(result["exit_code"])


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--observed-active",
        choices=("true", "false"),
        required=True,
        help="Operator-observed kill-switch state to baseline.",
    )
    parser.add_argument("--state-dir", type=Path, default=None)
    parser.add_argument("--audit-path", type=Path, default=None)
    parser.add_argument("--apply", action="store_true", help="Append the baseline event.")
    parser.add_argument(
        "--force",
        action="store_true",
        help="Append even when transition events already exist.",
    )
    parser.add_argument("--json", action="store_true")
    return parser


def build_result(
    *,
    audit_path: Path,
    observed_active: bool,
    apply: bool,
    force: bool = False,
) -> dict[str, Any]:
    transition_count = count_transition_events(audit_path)
    if transition_count and not force:
        return {
            "ok": False,
            "exit_code": 78,
            "applied": False,
            "reason": "transition_events_already_present",
            "audit_path": str(audit_path),
            "transition_count": transition_count,
            "observed_active": observed_active,
        }

    event = build_event(observed_active=observed_active)
    result = {
        "ok": True,
        "exit_code": 0,
        "applied": False,
        "dry_run": not apply,
        "audit_path": str(audit_path),
        "transition_count": transition_count,
        "event_type": event["event_type"],
        "observed_active": observed_active,
        "reason_hash": hashlib.sha256(str(event["reason"]).encode("utf-8")).hexdigest()[:12],
        "reason_chars": len(str(event["reason"])),
    }
    if apply:
        audit_path.parent.mkdir(parents=True, exist_ok=True)
        with audit_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(event, sort_keys=True, separators=(",", ":")) + "\n")
        result["applied"] = True
        result["dry_run"] = False
    return result


def build_event(*, observed_active: bool) -> dict[str, Any]:
    return {
        "event_type": "kill_switch.operator_baseline",
        "kind": "operator_baseline",
        "timestamp": datetime.now(UTC).isoformat(timespec="seconds"),
        "observed_active": observed_active,
        "reason": "operator baseline recorded without kill-switch transition",
        "source": "codex_operator_cli",
    }


def count_transition_events(audit_path: Path) -> int:
    if not audit_path.exists():
        return 0
    count = 0
    for line in audit_path.read_text(encoding="utf-8").splitlines():
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        if record.get("event_type") in {"kill_switch.activated", "kill_switch.deactivated"}:
            count += 1
    return count


def resolve_audit_path(state_dir: Path | None, audit_path: Path | None) -> Path:
    if audit_path:
        return audit_path.expanduser()
    state_root = state_dir or Path(os.environ.get("SAPPHIRE_STATE_DIR", Path.home() / ".sapphire"))
    return state_root.expanduser() / "audit" / "kill_switch.jsonl"


def render(result: dict[str, Any]) -> str:
    lines = [
        "# Kill-Switch Baseline",
        "",
        f"- OK: {result['ok']}",
        f"- Applied: {result['applied']}",
        f"- Dry run: {result.get('dry_run', False)}",
        f"- Observed active: {result['observed_active']}",
        f"- Event type: `{result.get('event_type', '-')}`",
        f"- Existing transitions: {result.get('transition_count', 0)}",
        f"- Reason hash: `{result.get('reason_hash', '-')}`",
        f"- Reason chars: {result.get('reason_chars', 0)}",
    ]
    if result.get("reason"):
        lines.append(f"- No-op reason: `{result['reason']}`")
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    raise SystemExit(main())
