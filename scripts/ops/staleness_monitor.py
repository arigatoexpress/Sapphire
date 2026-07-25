#!/usr/bin/env python3
"""Flag stale data files and silently-failing LaunchAgents.

Two failure modes this catches:

1. **File staleness** — a producer stops writing but nothing crashes visibly.
   Config: `infra/staleness-thresholds.yaml`. Each target names a path (or glob)
   plus a max age; the newest matching file's mtime is checked against it.

2. **Silent LaunchAgent failure** — the agent stays loaded but exits non-zero
   every cycle. `launchctl list` shows it, doctor.sh counts it as loaded, but
   its output is never produced.

The two together close a real gap. File-only monitoring misses failing agents
whose output file was never added to the threshold list (the exact bug behind
threat-refresh — the marker file it was supposed to check never existed, so the
monitor stayed silent). LaunchAgent-only monitoring misses producers that crash
mid-run but return 0 from the LaunchAgent's wrapper.

Usage:
  python3 scripts/ops/staleness_monitor.py                  # text output
  python3 scripts/ops/staleness_monitor.py --json           # JSON output
  python3 scripts/ops/staleness_monitor.py --stale-only     # hide FRESH rows
  python3 scripts/ops/staleness_monitor.py --exit-nonzero-on-stale
  python3 scripts/ops/staleness_monitor.py --queue-alert    # write Telegram draft

Exit code 2 means at least one row is STALE (or an agent is failing) AND
`--exit-nonzero-on-stale` was passed. MISSING for optional targets does not
influence the exit code.

Alerting NEVER sends. `--queue-alert` writes a draft to
`SAPPHIRE_PM_BOT_DRAFT_QUEUE_PATH` (env-configurable). An operator must
approve the draft in the PM bot before it goes out — the outward-message gate
lives one layer up, this script only queues.
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
import uuid
from dataclasses import dataclass
from pathlib import Path

# Cooldown between repeat alerts for the same fingerprint. 24h is long enough
# that a real regression doesn't get spammed hourly, short enough that if the
# problem recurs the next day it re-alerts (in case the operator forgot).
ALERT_COOLDOWN_SECONDS = 24 * 3600

REPO_ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = REPO_ROOT / "infra" / "staleness-thresholds.yaml"

# Labels whose non-zero exit is *diagnostic*, not a crash. `readiness-cache`
# exits 20 when the sweep it wraps found FAILs — that's the whole point of the
# sweep, so alerting on it would fire every cycle and train operators to
# ignore the monitor. Match EXACT label — sibling labels with a suffix (e.g. a
# `-x` variant used for staging) are still real failures worth reporting.
EXIT_CODE_EXEMPT_LABELS: frozenset[str] = frozenset({"com.sapphire.readiness-cache"})

# Only Sapphire-owned agents are our problem. `com.apple.*` and other system
# agents routinely carry non-zero last_exit values that mean nothing to us.
AGENT_LABEL_PREFIX = "com.sapphire."


@dataclass
class Row:
    label: str
    path: str
    status: str  # FRESH | STALE | MISSING
    age_hours: float | None
    threshold_hours: float
    resolved_path: str | None


@dataclass
class AgentRow:
    """A LaunchAgent that is loaded but exiting non-zero.

    The "silent failure" class of regression — `launchctl list` shows the
    agent, doctor.sh counts it as loaded, but the process never stays up.
    Without this check, the only signal is a stale output file — and only if
    someone remembered to add the file to the threshold list.
    """

    label: str
    last_exit: str


# ── Config parsing ────────────────────────────────────────────────────────────


def load_config(path: Path) -> list[dict]:
    """Parse the thresholds YAML.

    Minimal parser sufficient for our schema (top-level `targets:` list, each
    item a dict of scalar key/value pairs). Avoids adding a PyYAML runtime
    dep just for one file.
    """
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


# ── Path resolution ───────────────────────────────────────────────────────────


def _anchor(pattern: str) -> Path:
    """Anchor a config path.

    Repo-relative by default, but `~` and absolute paths pass through so the
    monitor can watch artifacts written outside the worktree — several
    LaunchAgents write to `~/autonomy-status/logs`, and the readiness sweep's
    cached report lives there. A repo-relative-only resolver would report those
    permanently MISSING, which is how a monitoring blind spot gets baked in.
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


# ── LaunchAgent introspection ─────────────────────────────────────────────────


def failing_agents() -> list[AgentRow]:
    """Sapphire agents whose last exit code was non-zero.

    Parses `launchctl list` output (columns: PID, last exit, label separated
    by tabs). A non-zero last-exit on a Sapphire agent means either (a) it's
    scheduled and it exited non-zero last cycle, or (b) it's supposed to be
    always_on and crashed. Either way, the operator wants to know.

    Diagnostic exit codes (see `EXIT_CODE_EXEMPT_LABELS`) are filtered out so
    the monitor doesn't cry wolf.
    """
    try:
        result = subprocess.run(
            ["launchctl", "list"],
            capture_output=True,
            text=True,
            check=False,
            timeout=5,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return []
    rows: list[AgentRow] = []
    for line in result.stdout.splitlines():
        parts = line.split("\t")
        if len(parts) < 3:
            continue
        _pid, last_exit, label = parts[0], parts[1], parts[2].strip()
        if not label.startswith(AGENT_LABEL_PREFIX):
            continue
        if last_exit == "0":
            continue
        if label in EXIT_CODE_EXEMPT_LABELS:
            continue
        rows.append(AgentRow(label=label, last_exit=last_exit))
    return rows


# ── Alert deduplication ───────────────────────────────────────────────────────


def alert_fingerprint(rows: list[Row], agents: list[AgentRow]) -> str:
    """Stable fingerprint of the current problem set.

    Two runs with the same STALE labels + failing agents produce the same
    fingerprint even if the ages drifted (which they always do), so `same
    problem set again` gets suppressed by the cooldown. Anything new — a
    fresh STALE label, a newly-crashed agent — changes the fingerprint and
    breaks through the cooldown.

    Fields intentionally excluded from the digest: `age_hours` (advances
    every run), `resolved_path` (the newest glob match rotates day-to-day for
    dated files like `signals/2026-07-16.jsonl`). Including either would
    defeat dedup entirely.
    """
    payload = {
        "stale": sorted(
            {(r.label, r.path) for r in rows if r.status == "STALE"}
        ),
        "missing": sorted(
            {(r.label, r.path) for r in rows if r.status == "MISSING"}
        ),
        "agents": sorted({(a.label, a.last_exit) for a in agents}),
    }
    encoded = json.dumps(payload, sort_keys=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()[:16]


def _load_alert_state(state_path: Path) -> dict[str, float]:
    if not state_path.exists():
        return {}
    try:
        raw = json.loads(state_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    return {k: float(v) for k, v in raw.items()} if isinstance(raw, dict) else {}


def _save_alert_state(state_path: Path, state: dict[str, float]) -> None:
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(json.dumps(state, sort_keys=True, indent=2), encoding="utf-8")


def should_alert(fingerprint: str, *, now: float, state_path: Path) -> bool:
    """True if we should emit an alert for this fingerprint at `now`.

    Suppresses repeats of the same fingerprint within `ALERT_COOLDOWN_SECONDS`
    of the last recorded emit. Different fingerprint → always True. State
    lives in a JSON file at `state_path` so cooldown persists across runs.
    """
    state = _load_alert_state(state_path)
    last = state.get(fingerprint)
    if last is None:
        return True
    return (now - last) >= ALERT_COOLDOWN_SECONDS


def record_alert(fingerprint: str, *, now: float, state_path: Path) -> None:
    """Persist the emit time so `should_alert` can honor the cooldown."""
    state = _load_alert_state(state_path)
    state[fingerprint] = now
    _save_alert_state(state_path, state)


# ── Alerting (draft-only; never sends) ────────────────────────────────────────


def queue_alert(rows: list[Row], agents: list[AgentRow]) -> str:
    """Queue a Telegram draft summarizing STALE rows + failing agents.

    Writes one JSONL entry to `SAPPHIRE_PM_BOT_DRAFT_QUEUE_PATH`. The record
    is marked `status: "draft"` and `requires_confirmation: true`, and
    `metadata.external_side_effect` is false — an operator must approve the
    draft in the PM bot before anything goes out. This function never sends.

    The outward-messaging gate is upstream (PM bot); this queue is the
    handoff. Never bypass by adding a "send now" path here — CLAUDE.md rule 1
    binds every agent in the fleet, including this one.
    """
    queue_path_str = os.environ.get("SAPPHIRE_PM_BOT_DRAFT_QUEUE_PATH")
    if not queue_path_str:
        raise RuntimeError(
            "SAPPHIRE_PM_BOT_DRAFT_QUEUE_PATH not set — refusing to write draft to an unknown path"
        )
    queue_path = Path(queue_path_str).expanduser()
    queue_path.parent.mkdir(parents=True, exist_ok=True)

    draft_id = f"tg_draft_{uuid.uuid4().hex[:12]}"
    body_lines = ["*Sapphire health regressions*", ""]
    stale_rows = [r for r in rows if r.status == "STALE"]
    if stale_rows:
        body_lines.append("*Stale data*:")
        for row in stale_rows:
            age = f"{row.age_hours:.1f}h" if row.age_hours is not None else "missing"
            body_lines.append(
                f"  • `{row.label}` — {age} old (threshold {row.threshold_hours:.0f}h)"
            )
        body_lines.append("")
    if agents:
        body_lines.append("*Silently failing LaunchAgents*:")
        for agent in agents:
            body_lines.append(f"  • `{agent.label}` — last exit {agent.last_exit}")
        body_lines.append("")
    if not stale_rows and not agents:
        body_lines.append("(no regressions detected — draft nevertheless emitted)")

    record = {
        "id": draft_id,
        "status": "draft",
        "requires_confirmation": True,
        "channel": "telegram",
        "body": "\n".join(body_lines),
        "metadata": {
            "external_side_effect": False,
            "source": "staleness_monitor",
            "created_ts": time.time(),
            "stale_row_count": len(stale_rows),
            "failing_agent_count": len(agents),
        },
    }
    with queue_path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record) + "\n")
    return draft_id


# ── CLI ───────────────────────────────────────────────────────────────────────


def emit_text(rows: list[Row], agents: list[AgentRow]) -> None:
    color = {"FRESH": "\033[32m", "STALE": "\033[31m", "MISSING": "\033[33m"}
    reset = "\033[0m"
    print(f"{'STATUS':<8}{'AGE(h)':>8}  {'THRESH':>7}  LABEL  →  PATH")
    for row in rows:
        age = f"{row.age_hours:7.1f}" if row.age_hours is not None else "     -"
        thresh = f"{row.threshold_hours:6.1f}"
        location = row.resolved_path or row.path
        print(f"{color[row.status]}{row.status:<8}{reset}{age}  {thresh}  {row.label}  →  {location}")
    if agents:
        print()
        print("Silently failing LaunchAgents:")
        for agent in agents:
            print(f"  \033[31mFAIL\033[0m  {agent.label} (last exit {agent.last_exit})")


def emit_json(rows: list[Row], agents: list[AgentRow]) -> None:
    print(
        json.dumps(
            {
                "rows": [row.__dict__ for row in rows],
                "failing_agents": [a.__dict__ for a in agents],
            },
            indent=2,
        )
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="emit JSON to stdout")
    parser.add_argument("--stale-only", action="store_true", help="hide FRESH rows")
    parser.add_argument(
        "--exit-nonzero-on-stale",
        action="store_true",
        help="exit 2 if any row is STALE or any agent is failing",
    )
    parser.add_argument(
        "--queue-alert",
        action="store_true",
        help="write a Telegram draft to SAPPHIRE_PM_BOT_DRAFT_QUEUE_PATH (never sends)",
    )
    parser.add_argument(
        "--skip-agents",
        action="store_true",
        help="skip LaunchAgent introspection (useful on non-macOS or in tests)",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=CONFIG_PATH,
        help=f"config path (default: {CONFIG_PATH.relative_to(REPO_ROOT)})",
    )
    args = parser.parse_args(argv)

    if not args.config.exists():
        print(f"missing config: {args.config}", file=sys.stderr)
        return 1

    targets = load_config(args.config)
    now = time.time()
    rows = [evaluate(t, now) for t in targets]
    shown = [r for r in rows if not args.stale_only or r.status != "FRESH"]
    agents = [] if args.skip_agents else failing_agents()

    if args.json:
        emit_json(shown, agents)
    else:
        emit_text(shown, agents)

    if args.queue_alert:
        draft_id = queue_alert(rows, agents)
        print(f"queued draft: {draft_id}", file=sys.stderr)

    any_stale = any(r.status == "STALE" for r in rows)
    if args.exit_nonzero_on_stale and (any_stale or agents):
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
