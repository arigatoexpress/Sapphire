#!/usr/bin/env python3
"""Flag critical data files whose mtime is older than a configured threshold.

Usage:
  python3 scripts/ops/staleness_monitor.py                  # text output
  python3 scripts/ops/staleness_monitor.py --json           # JSON output
  python3 scripts/ops/staleness_monitor.py --stale-only     # only STALE rows
  python3 scripts/ops/staleness_monitor.py --exit-nonzero-on-stale

Exit code 2 means at least one path is STALE and `--exit-nonzero-on-stale`
was passed. Missing paths are treated as STALE unless the target was declared
`optional: true`; optional missing paths are reported MISSING but do not
influence the exit code.

Config: infra/staleness-thresholds.yaml. Each entry declares:
  - path:      glob relative to repo root; the latest matching file wins for
               globs, or the path itself for concrete filenames
  - max_age_h: threshold in hours; the file's mtime must be within this window
  - label:     short label for reports
  - optional:  true if a missing path should not count as STALE (default False)

Reads mtimes only — never opens or mutates the files.
"""

from __future__ import annotations

import argparse
import glob
import hashlib
import json
import os
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

CONFIG_PATH = REPO_ROOT / "infra" / "staleness-thresholds.yaml"
DEFAULT_DRAFT_QUEUE = Path.home() / ".cache" / "sapphire" / "telegram" / "pm_bot_drafts.jsonl"


@dataclass
class Row:
    label: str
    path: str
    status: str  # FRESH | STALE | MISSING
    age_hours: float | None
    threshold_hours: float
    resolved_path: str | None


def load_config(path: Path) -> list[dict]:
    # Minimal YAML parser sufficient for our schema: top-level `targets:` list,
    # each item a dict of scalar key/value pairs. Avoids adding a PyYAML runtime
    # dep just for this file.
    text = path.read_text(encoding="utf-8")
    targets: list[dict] = []
    current: dict | None = None
    in_targets = False
    for raw in text.splitlines():
        line = raw.rstrip()
        if not line or line.lstrip().startswith("#"):
            continue
        if line.startswith("targets:"):
            in_targets = True
            continue
        if not in_targets:
            continue
        if line.startswith("  - "):
            if current is not None:
                targets.append(current)
            current = {}
            body = line[4:]
            if ":" in body:
                key, _, value = body.partition(":")
                current[key.strip()] = _coerce(value.strip())
        elif line.startswith("    ") and current is not None:
            body = line.strip()
            if ":" in body:
                key, _, value = body.partition(":")
                current[key.strip()] = _coerce(value.strip())
    if current is not None:
        targets.append(current)
    return targets


def _coerce(raw: str) -> object:
    if raw.lower() in {"true", "yes"}:
        return True
    if raw.lower() in {"false", "no"}:
        return False
    if raw.isdigit():
        return int(raw)
    try:
        return float(raw)
    except ValueError:
        pass
    return raw.strip('"').strip("'")


def _anchor(pattern: str) -> Path:
    """Anchor a config path.

    Repo-relative by default, but `~` and absolute paths pass through so the
    monitor can watch artifacts written outside the worktree — several
    LaunchAgents write to ~/autonomy-status/logs, and the readiness sweep's
    cached report lives there.
    """
    expanded = Path(pattern).expanduser()
    return expanded if expanded.is_absolute() else REPO_ROOT / pattern


def _display_path(resolved: Path) -> str:
    try:
        return str(resolved.relative_to(REPO_ROOT))
    except ValueError:
        return str(resolved)


def resolve_latest(pattern: str) -> Path | None:
    matches = sorted(
        glob.glob(str(_anchor(pattern))), key=lambda p: Path(p).stat().st_mtime, reverse=True
    )
    return Path(matches[0]) if matches else None


def evaluate(target: dict, now: float) -> Row:
    label = target.get("label", target["path"])
    pattern = target["path"]
    threshold = float(target["max_age_h"])
    optional = bool(target.get("optional", False))
    if any(ch in pattern for ch in "*?["):
        resolved = resolve_latest(pattern)
    else:
        candidate = _anchor(pattern)
        resolved = candidate if candidate.exists() else None
    if resolved is None:
        status = "MISSING" if optional else "STALE"
        return Row(label, pattern, status, None, threshold, None)
    age_seconds = now - resolved.stat().st_mtime
    age_hours = age_seconds / 3600.0
    status = "FRESH" if age_hours <= threshold else "STALE"
    return Row(label, pattern, status, age_hours, threshold, _display_path(resolved))


@dataclass
class AgentRow:
    """A LaunchAgent whose last run exited non-zero."""

    label: str
    last_exit: str


# The sweep exits 20 by design when it finds FAILs — a diagnostic code, not a
# crash. Without this exemption the monitor would cry wolf on every cycle, and
# a monitor that always alerts is a monitor nobody reads.
_EXPECTED_NONZERO_EXITS = {"com.sapphire.readiness-cache": {"20"}}


def failing_agents() -> list[AgentRow]:
    """Report Sapphire LaunchAgents whose last run exited non-zero.

    Column 2 of `launchctl list` is the last exit status. A job that is loaded
    but exits non-zero on every cycle looks perfectly alive in `launchctl list`,
    in Activity Monitor, and in any process-liveness check — which is precisely
    how threat-refresh stayed broken for weeks. This is the complement to
    artifact freshness: the job ran, the job failed, the job wrote nothing.
    """
    try:
        result = subprocess.run(
            ["launchctl", "list"], capture_output=True, text=True, timeout=20, check=False
        )
    except (OSError, subprocess.SubprocessError):
        return []

    rows: list[AgentRow] = []
    for line in result.stdout.splitlines():
        parts = line.split()
        if len(parts) < 3 or not parts[2].startswith("com.sapphire."):
            continue
        last_exit, label = parts[1], parts[2]
        if last_exit in ("0", "-") or last_exit in _EXPECTED_NONZERO_EXITS.get(label, set()):
            continue
        rows.append(AgentRow(label=label, last_exit=last_exit))
    return rows


def format_alert(rows: list[Row], agents: list[AgentRow]) -> str:
    """Render a Telegram-ready body describing every unhealthy signal."""
    lines = ["⚠️ *Sapphire staleness alert*", ""]
    for row in rows:
        if row.status == "FRESH":
            continue
        detail = (
            "missing"
            if row.age_hours is None
            else f"{row.age_hours:.1f}h old (limit {row.threshold_hours:.0f}h)"
        )
        lines.append(f"\U0001f534 `{row.label}` — {detail}")
    for agent in agents:
        lines.append(f"\U0001f534 `{agent.label}` — last exit {agent.last_exit}")
    lines.append("")
    lines.append("Check: `python3 scripts/ops/staleness_monitor.py --stale-only`")
    return "\n".join(lines)


ALERT_STATE_PATH = REPO_ROOT / "data" / "health" / "staleness_alert_state.json"
ALERT_COOLDOWN_HOURS = 24.0


def alert_fingerprint(rows: list[Row], agents: list[AgentRow]) -> str:
    """Identify *which problems* are outstanding, independent of how old they are.

    Ages advance every run, so folding them in would make every fingerprint
    unique and defeat deduplication entirely. Hashing only (label, status) means
    a genuinely new problem re-alerts at once while an unchanged one stays quiet
    until the cooldown lapses.
    """
    parts = sorted(f"{r.label}:{r.status}" for r in rows if r.status != "FRESH")
    parts += sorted(f"agent:{a.label}:{a.last_exit}" for a in agents)
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()[:16]


def should_alert(fingerprint: str, *, now: float, state_path: Path = ALERT_STATE_PATH) -> bool:
    """Suppress repeats of an unchanged problem set inside the cooldown window.

    Without this, a file that has been stale for 23 days queues one draft per
    run forever. A queue full of duplicates is a queue nobody reads, which is
    exactly the blindness this monitor exists to remove.
    """
    try:
        state = json.loads(state_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return True

    if state.get("fingerprint") != fingerprint:
        return True
    last = float(state.get("alerted_at") or 0)
    return (now - last) >= ALERT_COOLDOWN_HOURS * 3600


def record_alert(fingerprint: str, *, now: float, state_path: Path = ALERT_STATE_PATH) -> None:
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(
        json.dumps({"fingerprint": fingerprint, "alerted_at": now}, indent=2), encoding="utf-8"
    )


def queue_alert(rows: list[Row], agents: list[AgentRow]) -> str:
    """Queue a draft for pm-bot to hand to an operator.

    `lib.telegram.draft_queue` deliberately has no send adapter — this writes a
    record and stops. Approving and sending stays a human action.
    """
    from lib.telegram.draft_queue import append_draft, build_draft

    queue_path = Path(
        os.environ.get("SAPPHIRE_PM_BOT_DRAFT_QUEUE_PATH", str(DEFAULT_DRAFT_QUEUE))
    )
    draft = build_draft(
        kind="sapphire_staleness_alert",
        topic="ops-health",
        body=format_alert(rows, agents),
        created_by="staleness-monitor",
        source_ids=tuple(r.label for r in rows if r.status != "FRESH"),
        metadata={
            "external_side_effect": False,
            "stale_count": sum(1 for r in rows if r.status == "STALE"),
            "failing_agents": [a.label for a in agents],
        },
    )
    append_draft(queue_path, draft)
    return draft.draft_id


def emit_text(rows: list[Row]) -> None:
    color = {
        "FRESH": "\033[32m",
        "STALE": "\033[31m",
        "MISSING": "\033[33m",
    }
    reset = "\033[0m"
    print(f"{'STATUS':<8}{'AGE(h)':>8}  {'THRESH':>7}  LABEL  →  PATH")
    for row in rows:
        age = f"{row.age_hours:7.1f}" if row.age_hours is not None else "     -"
        thresh = f"{row.threshold_hours:6.1f}"
        location = row.resolved_path or row.path
        print(f"{color[row.status]}{row.status:<8}{reset}{age}  {thresh}  {row.label}  →  {location}")


def emit_json(rows: list[Row]) -> None:
    print(json.dumps([row.__dict__ for row in rows], indent=2))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="emit JSON to stdout")
    parser.add_argument("--stale-only", action="store_true", help="hide FRESH rows")
    parser.add_argument(
        "--exit-nonzero-on-stale",
        action="store_true",
        help="exit 2 if any row is STALE (MISSING for optional targets is OK)",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=CONFIG_PATH,
        help=f"config path (default: {CONFIG_PATH.relative_to(REPO_ROOT)})",
    )
    parser.add_argument(
        "--check-agents",
        action="store_true",
        help="also report LaunchAgents whose last run exited non-zero",
    )
    parser.add_argument(
        "--alert",
        action="store_true",
        help="queue a Telegram draft for pm-bot when anything is unhealthy (never sends)",
    )
    args = parser.parse_args(argv)

    if not args.config.exists():
        print(f"missing config: {args.config}", file=sys.stderr)
        return 1

    targets = load_config(args.config)
    now = time.time()
    rows = [evaluate(t, now) for t in targets]
    shown = [r for r in rows if not args.stale_only or r.status != "FRESH"]
    agents = failing_agents() if args.check_agents else []

    if args.json:
        emit_json(shown)
    else:
        emit_text(shown)
        for agent in agents:
            print(f"NONZERO   agent  {agent.label}  last_exit={agent.last_exit}")

    any_stale = any(r.status == "STALE" for r in rows)

    if args.alert and (any_stale or agents):
        fingerprint = alert_fingerprint(rows, agents)
        if should_alert(fingerprint, now=now):
            try:
                print(f"queued draft {queue_alert(rows, agents)}")
                record_alert(fingerprint, now=now)
            except Exception as exc:
                # Alerting must never mask the finding it was trying to report.
                print(f"draft queue failed ({exc.__class__.__name__}: {exc})", file=sys.stderr)
        else:
            print(f"alert suppressed (unchanged since last alert, fp={fingerprint})")

    if args.exit_nonzero_on_stale and any_stale:
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
