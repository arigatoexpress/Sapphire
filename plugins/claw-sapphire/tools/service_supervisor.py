#!/usr/bin/env python3
"""Self-healing LaunchAgent supervisor for Sapphire services.

The supervisor intentionally runs as a one-shot command. launchd owns the
schedule, and this module owns the state needed to make repeated invocations
idempotent: per-label restart cooldowns, a global rolling restart cap, and the
"seen event" categories that keep Telegram escalation sparse.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from dev_pulse import DEFAULT_LAUNCHAGENT_LABELS, ServiceStatus, collect_service_statuses
from notify import send_alert
from routine_pause_bridge import abort_if_paused

STATE_FILE = (
    Path.home()
    / "Library"
    / "Application Support"
    / "sapphire"
    / "service_supervisor"
    / "state.json"
)


def _now() -> datetime:
    return datetime.now(timezone.utc)  # noqa: UP017 - prompt requires timezone.utc


def _parse_dt(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)  # noqa: UP017 - keep timezone.utc
    return parsed.astimezone(timezone.utc)  # noqa: UP017 - keep timezone.utc


def _load_state() -> dict[str, Any]:
    try:
        if STATE_FILE.exists():
            data = json.loads(STATE_FILE.read_text())
            if isinstance(data, dict):
                data.setdefault("labels", {})
                data.setdefault("restart_attempts", [])
                data.setdefault("seen_event_categories", [])
                return data
    except (OSError, json.JSONDecodeError):
        pass
    return {"labels": {}, "restart_attempts": [], "seen_event_categories": []}


def _save_state(state: dict[str, Any]) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=2, sort_keys=True))


def _run(cmd: list[str], timeout: int = 20) -> tuple[int, str, str]:
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return result.returncode, result.stdout, result.stderr
    except FileNotFoundError:
        return 127, "", f"command not found: {cmd[0]}"
    except subprocess.TimeoutExpired:
        return 124, "", f"timeout after {timeout}s"
    except Exception as exc:
        return 1, "", f"{type(exc).__name__}: {exc}"


def _status_to_dict(status: ServiceStatus | None) -> dict[str, Any] | None:
    if status is None:
        return None
    return {
        "label": status.label,
        "loaded": status.loaded,
        "pid": status.pid,
        "exit_code": status.exit_code,
    }


def _is_healthy(status: ServiceStatus) -> bool:
    return status.loaded and (status.pid is not None or status.exit_code in (None, 0))


def _reason_for(status: ServiceStatus) -> str | None:
    if not status.loaded:
        return "unloaded_when_expected"
    if status.pid is not None:
        return None
    if status.exit_code not in (None, 0):
        return "crashed"
    return None


def _launchagent_plist(label: str) -> Path:
    return Path.home() / "Library" / "LaunchAgents" / f"{label}.plist"


def _restart_command(label: str, reason: str) -> list[str]:
    user_domain = f"gui/{os.getuid()}"
    if reason == "unloaded_when_expected":
        # bootstrap is the modern macOS launchctl verb for loading a job into a
        # specific domain. We target gui/<uid> explicitly so the one-shot
        # supervisor never guesses at launchd's active user session.
        return ["launchctl", "bootstrap", user_domain, str(_launchagent_plist(label))]
    return ["launchctl", "kickstart", "-k", f"{user_domain}/{label}"]


def _trim_attempts(state: dict[str, Any], now: datetime) -> list[dict[str, Any]]:
    cutoff = now - timedelta(hours=1)
    attempts: list[dict[str, Any]] = []
    for item in state.get("restart_attempts", []):
        if not isinstance(item, dict):
            continue
        ts = _parse_dt(item.get("timestamp"))
        if ts is not None and ts >= cutoff:
            attempts.append(item)
    state["restart_attempts"] = attempts
    return attempts


def _label_state(state: dict[str, Any], label: str) -> dict[str, Any]:
    labels = state.setdefault("labels", {})
    if not isinstance(labels, dict):
        labels = {}
        state["labels"] = labels
    current = labels.setdefault(label, {})
    if not isinstance(current, dict):
        current = {}
        labels[label] = current
    return current


def _get_firestore_db() -> Any | None:
    try:
        from google.cloud import firestore  # type: ignore
    except Exception:
        return None
    return firestore.Client(project=os.getenv("THO_FIRESTORE_PROJECT", "tho-ai-agent"))


def _write_activity(action: str, payload: dict[str, Any], now: datetime) -> str | None:
    db = _get_firestore_db()
    if db is None:
        return None

    doc_id = str(uuid.uuid4())
    metadata = {
        "label": payload.get("label"),
        "action": action,
        "reason": payload.get("reason"),
        "exit_code_before": payload.get("exit_code_before"),
        "exit_code_after": payload.get("exit_code_after"),
        "duration_seconds": payload.get("duration_seconds"),
    }
    metadata = {key: value for key, value in metadata.items() if value is not None}
    activity = {
        "id": doc_id,
        "activity_type": f"service_supervisor.{action}",
        "description": f"Sapphire service supervisor {action}: {payload.get('label', 'unknown')}",
        "project_id": "sapphire",
        "task_id": None,
        "actor": "service_supervisor",
        "metadata": metadata,
        "created_at": now,
    }
    try:
        db.collection("activities").document(doc_id).set(activity)
    except Exception as exc:
        return f"firestore:{action}:{payload.get('label')}: {type(exc).__name__}: {exc}"
    return None


def _record_activity(
    summary: dict[str, Any],
    action: str,
    payload: dict[str, Any],
    now: datetime,
    *,
    dry_run: bool,
) -> None:
    if dry_run:
        return
    error = _write_activity(action, payload, now)
    if error:
        summary["errors"].append(error)


def _notify(message: str, priority: str, summary: dict[str, Any], *, dry_run: bool) -> None:
    if dry_run:
        return
    try:
        send_alert(message, priority=priority)
    except Exception as exc:
        summary["errors"].append(f"notify: {type(exc).__name__}: {exc}")


def _entry(
    status: ServiceStatus,
    reason: str,
    command: list[str],
    *,
    dry_run: bool,
    after: ServiceStatus | None = None,
    rc: int | None = None,
    stderr: str | None = None,
    duration_seconds: float | None = None,
) -> dict[str, Any]:
    data: dict[str, Any] = {
        "label": status.label,
        "reason": reason,
        "restart_action": "bootstrap" if reason == "unloaded_when_expected" else "kickstart",
        "command": command,
        "dry_run": dry_run,
        "loaded_before": status.loaded,
        "exit_code_before": status.exit_code,
        "pid_before": status.pid,
    }
    if after is not None:
        data.update(
            {
                "loaded_after": after.loaded,
                "exit_code_after": after.exit_code,
                "pid_after": after.pid,
            }
        )
    if rc is not None:
        data["returncode"] = rc
    if stderr:
        data["stderr"] = stderr.strip()[:300]
    if duration_seconds is not None:
        data["duration_seconds"] = round(duration_seconds, 3)
    return data


def _is_restart_successful(before: ServiceStatus, after: ServiceStatus) -> bool:
    """Return True when a `launchctl kickstart -k` actually replaced the process.

    launchctl's `LastExitStatus` field persists the PREVIOUS exit code even
    after a successful restart — a service that crashed once and was
    KeepAlive-revived will read `exit_code == 1` indefinitely. Relying on
    exit_code alone would keep marking healthy services as "failed" and
    Telegram-spam the operator.

    Authoritative signal: the PID changed (or appeared). A new PID means
    launchd actually replaced the process. If the PID is unchanged and
    exit_code still non-zero, the restart did NOT happen.
    """
    if not after.loaded:
        return False
    # PID appeared where there was none before → fresh start ✓
    if before.pid is None and after.pid is not None:
        return True
    # PID changed → kickstart replaced the process ✓
    if after.pid is not None and after.pid != before.pid:
        return True
    # Fallback: launchctl sometimes clears the exit code on full bootstrap.
    # If it did, trust it.
    return after.exit_code in (None, 0)


def _monitored_labels(labels: list[str] | None, summary: dict[str, Any]) -> list[str]:
    allowed = set(DEFAULT_LAUNCHAGENT_LABELS)
    requested = labels if labels is not None else list(DEFAULT_LAUNCHAGENT_LABELS)
    out: list[str] = []
    for label in requested:
        if label == "com.sapphire.service-supervisor":
            continue
        if label not in allowed:
            summary["errors"].append(f"ignored unmonitored label: {label}")
            continue
        if label not in out:
            out.append(label)
    return out


def _mark_event_seen(state: dict[str, Any], category: str) -> bool:
    seen = state.setdefault("seen_event_categories", [])
    if not isinstance(seen, list):
        seen = []
        state["seen_event_categories"] = seen
    if category in seen:
        return False
    seen.append(category)
    return True


def _skip(
    summary: dict[str, Any],
    state: dict[str, Any],
    status: ServiceStatus,
    reason: str,
    skip_reason: str,
    now: datetime,
    *,
    dry_run: bool,
) -> None:
    payload = {
        "label": status.label,
        "reason": reason,
        "skip_reason": skip_reason,
        "loaded_before": status.loaded,
        "exit_code_before": status.exit_code,
        "dry_run": dry_run,
    }
    summary["skipped_cooldown"].append(payload)
    _record_activity(summary, "skipped_cooldown", payload, now, dry_run=dry_run)
    category = f"{status.label}:{reason}"
    if _mark_event_seen(state, category):
        _notify(
            f"*Service supervisor first crash*\n{status.label}: {reason} ({skip_reason})",
            "p1",
            summary,
            dry_run=dry_run,
        )


def _collect_one(label: str) -> ServiceStatus:
    statuses = collect_service_statuses([label])
    if statuses:
        return statuses[0]
    return ServiceStatus(label=label, loaded=False)


def supervise_once(
    labels: list[str] | None = None,
    *,
    restart_cooldown_seconds: int = 300,
    max_restarts_per_hour: int = 4,
    dry_run: bool = False,
) -> dict:
    """Check every LaunchAgent, restart crashed ones, notify if restart fails.

    Returns a structured summary:
    {ok, attempted, recovered, failed, skipped_cooldown, errors}.
    """
    now = _now()
    summary: dict[str, Any] = {
        "ok": True,
        "attempted": [],
        "recovered": [],
        "failed": [],
        "skipped_cooldown": [],
        "errors": [],
    }
    monitored = _monitored_labels(labels, summary)
    if not monitored:
        summary["ok"] = not summary["errors"]
        return summary

    state = _load_state()
    attempts = _trim_attempts(state, now)
    statuses = collect_service_statuses(monitored)
    by_label = {status.label: status for status in statuses}

    for label in monitored:
        status = by_label.get(label) or ServiceStatus(label=label, loaded=False)
        reason = _reason_for(status)
        if reason is None:
            label_state = _label_state(state, label)
            label_state["consecutive_failures"] = 0
            continue

        label_state = _label_state(state, label)
        last_attempt = _parse_dt(label_state.get("last_attempt_at"))
        if last_attempt and now - last_attempt < timedelta(seconds=restart_cooldown_seconds):
            _skip(summary, state, status, reason, "restart_cooldown", now, dry_run=dry_run)
            continue

        if int(label_state.get("consecutive_failures") or 0) >= 2:
            _skip(summary, state, status, reason, "consecutive_failures", now, dry_run=dry_run)
            continue

        if len(attempts) >= max_restarts_per_hour:
            payload = {
                "label": status.label,
                "reason": reason,
                "skip_reason": "rate_limited",
                "loaded_before": status.loaded,
                "exit_code_before": status.exit_code,
                "dry_run": dry_run,
            }
            summary["skipped_cooldown"].append(payload)
            summary["errors"].append("rate_limited: max restart attempts per rolling hour reached")
            _record_activity(summary, "skipped_cooldown", payload, now, dry_run=dry_run)
            _notify(
                "*Service supervisor rate limited*\n"
                f"Restart cap hit ({max_restarts_per_hour}/hour). No restart attempted for {status.label}.",
                "p0",
                summary,
                dry_run=dry_run,
            )
            continue

        command = _restart_command(label, reason)
        if dry_run:
            summary["attempted"].append(_entry(status, reason, command, dry_run=True))
            continue

        start = time.monotonic()
        attempted_at = _now()
        rc, _, stderr = _run(command)
        after = _collect_one(label)
        duration = time.monotonic() - start
        payload = _entry(
            status,
            reason,
            command,
            dry_run=False,
            after=after,
            rc=rc,
            stderr=stderr,
            duration_seconds=duration,
        )
        summary["attempted"].append(payload)
        _record_activity(summary, "attempted", payload, attempted_at, dry_run=False)

        label_state["last_attempt_at"] = attempted_at.isoformat()
        attempts.append(
            {
                "label": label,
                "timestamp": attempted_at.isoformat(),
                "reason": reason,
                "action": payload["restart_action"],
            }
        )
        state["restart_attempts"] = attempts
        _mark_event_seen(state, f"{label}:{reason}")

        if rc == 0 and _is_restart_successful(status, after):
            label_state["consecutive_failures"] = 0
            summary["recovered"].append(payload)
            _record_activity(summary, "recovered", payload, _now(), dry_run=False)
            continue

        label_state["consecutive_failures"] = int(label_state.get("consecutive_failures") or 0) + 1
        summary["failed"].append(payload)
        _record_activity(summary, "failed", payload, _now(), dry_run=False)
        _notify(
            "*Service supervisor restart failed*\n"
            f"{label}: {reason}; after loaded={after.loaded} exit={after.exit_code}; rc={rc}",
            "p0",
            summary,
            dry_run=False,
        )

    if not dry_run:
        _save_state(state)
    summary["ok"] = not summary["failed"] and not summary["errors"]
    return summary


def main() -> None:
    abort_if_paused("service-supervisor")
    parser = argparse.ArgumentParser(description="Run the Sapphire LaunchAgent supervisor once")
    parser.add_argument(
        "--label", action="append", dest="labels", help="Restrict to one monitored label"
    )
    parser.add_argument("--dry-run", action="store_true", help="Preview actions without restarting")
    parser.add_argument("--restart-cooldown-seconds", type=int, default=300)
    parser.add_argument("--max-restarts-per-hour", type=int, default=4)
    args = parser.parse_args()

    result = supervise_once(
        labels=args.labels,
        restart_cooldown_seconds=args.restart_cooldown_seconds,
        max_restarts_per_hour=args.max_restarts_per_hour,
        dry_run=args.dry_run,
    )
    print(json.dumps(result, indent=2, sort_keys=True, default=str))
    if not result.get("ok"):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
