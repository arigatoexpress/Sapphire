"""Routine health check — audits every row in docs/routines-manifest.md.

For each routine, verifies:
  * LaunchAgent is loaded (Mac)
  * Its output artifact (if any) is newer than `max_age_secs`
  * GCP scheduled queries show state != FAILED

Exit codes:
  0 — all routines healthy
  1 — at least one routine is stale or failed

Usage:
    python -m services.pipeline.check_routines          # human output
    python -m services.pipeline.check_routines --json   # machine output
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import logging
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

log = logging.getLogger("check_routines")

ROOT = Path.home() / "Code" / "Sapphire"
DATA = ROOT / "data"
LA_DIR = Path.home() / "Library" / "LaunchAgents"

GCP_PROJECT = "tho-ai-agent"
GCP_NUMBER = "691674245427"


# -- Config ----------------------------------------------------------------

@dataclasses.dataclass
class Routine:
    name: str
    kind: str                    # launchagent_always, launchagent_scheduled, gcp_scheduled_query
    artifact: str | None = None  # absolute path or glob; None = process-only
    max_age_secs: int | None = None
    launchagent: str | None = None
    transfer_config_id: str | None = None


ROUTINES: list[Routine] = [
    # Always-on services
    Routine("inference-proxy",   "launchagent_always", launchagent="com.sapphire.inference-proxy"),
    Routine("control-plane",     "launchagent_always", launchagent="com.sapphire.control-plane"),
    Routine("dashboard",         "launchagent_always", launchagent="com.sapphire.dashboard"),
    Routine("signal-logger",     "launchagent_always", launchagent="com.sapphire.signal-logger"),
    Routine("openbb-api",        "launchagent_always", launchagent="com.sapphire.openbb-api"),
    Routine("regional-intel",    "launchagent_always", launchagent="com.sapphire.regional-intel"),
    Routine("hermes-agent",      "launchagent_always", launchagent="ai.hermes.gateway"),

    # Scheduled Mac jobs
    Routine("chain-refresh",      "launchagent_scheduled",
            launchagent="com.sapphire.chain-refresh",
            artifact=str(DATA / "intelligence" / "latest" / "chain.json"),
            max_age_secs=30 * 60),         # 15 min + buffer
    Routine("correlation-refresh", "launchagent_scheduled",
            launchagent="com.sapphire.correlation-refresh",
            artifact=str(DATA / "intelligence" / "latest" / "correlations.json"),
            max_age_secs=2 * 60 * 60),     # 1 h + buffer
    Routine("gcp-sync",            "launchagent_scheduled",
            launchagent="com.sapphire.gcp-sync",
            artifact=str(DATA / ".gcp_sync_state.json"),
            max_age_secs=2 * 60 * 60),
    Routine("kronos-daily",        "launchagent_scheduled",
            launchagent="com.sapphire.kronos-daily",
            artifact=str(DATA / "intelligence" / "latest" / "predictions.json"),
            max_age_secs=36 * 60 * 60),    # daily, 36h window
    Routine("threat-refresh",      "launchagent_scheduled",
            launchagent="com.sapphire.threat-refresh",
            artifact=str(DATA / "intelligence" / "latest" / "threats.json"),
            max_age_secs=6 * 60 * 60),     # every 4h + buffer
    Routine("daily-brief",         "launchagent_scheduled",
            launchagent="com.sapphire.daily-brief",
            artifact=str(DATA / "intelligence" / "latest" / "daily_brief.md"),
            max_age_secs=36 * 60 * 60),
    Routine("logrotate",           "launchagent_scheduled",
            launchagent="com.sapphire.logrotate",
            max_age_secs=None),

    # GCP scheduled queries
    Routine("bq.daily_performance",   "gcp_scheduled_query",
            transfer_config_id="69f08739-0000-2ef4-a18c-5c337bc73dfb"),
    Routine("bq.weekly_regime",       "gcp_scheduled_query",
            transfer_config_id="6a171c83-0000-2292-8ab5-3c286d46cb7e"),
    Routine("bq.daily_threats",       "gcp_scheduled_query",
            transfer_config_id="6a2d0d4e-0000-28ed-abae-5c337bc5e7c7"),
    Routine("bq.prediction_accuracy", "gcp_scheduled_query",
            transfer_config_id="6a3b11c0-0000-2ed7-be8a-2405888140a4"),
]


# -- Checks ----------------------------------------------------------------

def _launchctl_list() -> dict[str, dict]:
    """Map label -> {pid, status} from `launchctl list`."""
    try:
        out = subprocess.run(["launchctl", "list"], capture_output=True, text=True, timeout=10)
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return {}
    agents: dict[str, dict] = {}
    for line in out.stdout.splitlines()[1:]:
        parts = line.split(maxsplit=2)
        if len(parts) < 3:
            continue
        pid, status, label = parts
        agents[label] = {
            "pid": None if pid == "-" else int(pid),
            "status": int(status) if status.lstrip("-").isdigit() else None,
        }
    return agents


def _artifact_age_secs(artifact: str) -> int | None:
    p = Path(artifact)
    if not p.exists():
        return None
    mtime = datetime.fromtimestamp(p.stat().st_mtime, tz=timezone.utc)
    return int((datetime.now(timezone.utc) - mtime).total_seconds())


def _gcp_query_state(cfg_id: str) -> tuple[str, str | None]:
    """Return (state, error_msg) of the latest run of a BQ scheduled query."""
    try:
        out = subprocess.run(
            ["bq", "ls", "--transfer_run", "--run_attempt=LATEST", "--format=json",
             f"projects/{GCP_NUMBER}/locations/us/transferConfigs/{cfg_id}"],
            capture_output=True, text=True, timeout=30,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired) as e:
        return "UNKNOWN", f"bq error: {e}"
    if out.returncode != 0:
        return "UNKNOWN", (out.stderr or "").strip()[:200]
    try:
        runs = json.loads(out.stdout)
    except json.JSONDecodeError:
        return "UNKNOWN", "bq ls returned non-JSON"
    if not runs:
        return "NO_RUNS", None
    r = runs[0]
    return r.get("state", "UNKNOWN"), (r.get("errorStatus") or {}).get("message")


# -- Dispatcher ------------------------------------------------------------

def check(routine: Routine, agents: dict[str, dict]) -> dict:
    row: dict = {"name": routine.name, "kind": routine.kind, "ok": True, "detail": ""}

    if routine.kind in ("launchagent_always", "launchagent_scheduled"):
        info = agents.get(routine.launchagent or "")
        if info is None:
            row["ok"] = False
            row["detail"] = f"launchagent not loaded: {routine.launchagent}"
            return row
        if routine.kind == "launchagent_always":
            if info.get("pid") is None:
                row["ok"] = False
                row["detail"] = f"not running (last exit {info.get('status')})"
                return row
        else:
            last_exit = info.get("status")
            if last_exit not in (0, None):
                row["ok"] = False
                row["detail"] = f"last run exited {last_exit}"
                return row

        if routine.artifact and routine.max_age_secs is not None:
            age = _artifact_age_secs(routine.artifact)
            if age is None:
                row["ok"] = False
                row["detail"] = f"artifact missing: {routine.artifact}"
                return row
            row["age_secs"] = age
            if age > routine.max_age_secs:
                row["ok"] = False
                row["detail"] = f"artifact stale: age={age}s max={routine.max_age_secs}s"
                return row
        row["detail"] = "OK"
        return row

    if routine.kind == "gcp_scheduled_query":
        state, err = _gcp_query_state(routine.transfer_config_id or "")
        row["state"] = state
        if state == "SUCCEEDED":
            row["detail"] = "OK"
        elif state in ("PENDING", "RUNNING"):
            row["detail"] = f"{state}"
        else:
            row["ok"] = False
            row["detail"] = f"{state}{(': ' + err) if err else ''}"
        return row

    row["ok"] = False
    row["detail"] = f"unknown kind: {routine.kind}"
    return row


# -- Main ------------------------------------------------------------------

def run() -> tuple[list[dict], int]:
    agents = _launchctl_list()
    rows = [check(r, agents) for r in ROUTINES]
    failed = [r for r in rows if not r["ok"]]
    return rows, len(failed)


def _fmt_row(r: dict) -> str:
    status = "✅" if r["ok"] else "❌"
    age = f" age={r['age_secs']}s" if r.get("age_secs") is not None else ""
    state = f" state={r['state']}" if r.get("state") else ""
    return f"  {status} {r['name']:<28} {r['kind']:<22}{state}{age}  {r['detail']}"


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--json", action="store_true", help="Machine-readable output")
    p.add_argument("-v", "--verbose", action="store_true")
    args = p.parse_args()
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    rows, failures = run()

    if args.json:
        print(json.dumps({"rows": rows, "failures": failures,
                          "generated_at": datetime.now(timezone.utc).isoformat()}, indent=2))
    else:
        print("=== Sapphire Routines — Health Check ===")
        for r in rows:
            print(_fmt_row(r))
        print(f"\n{'PASS' if failures == 0 else 'FAIL'}: {len(rows) - failures}/{len(rows)} healthy"
              + (f" — {failures} failure(s)" if failures else ""))

    return 0 if failures == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
