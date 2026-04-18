"""Routine health controller — periodic health summary + self-healing.

Wraps `services.pipeline.check_routines` with:
  - Auto-restart of failed LaunchAgents via `launchctl kickstart -k`
  - Execution-time logging to data/routines/history.ndjson (for later optimization)
  - Telegram daily summary via safe_send (plaintext, backoff-aware)

Run modes:
    python -m services.pipeline.routine_controller --check        # read-only audit
    python -m services.pipeline.routine_controller --heal         # audit + restart failing
    python -m services.pipeline.routine_controller --summary      # audit + Telegram summary
    python -m services.pipeline.routine_controller --all          # audit + heal + summary

Intended schedule (LaunchAgent every 30 min):
    --heal    quiet mode; only restart and log
Intended schedule (daily 9 AM):
    --summary send digest to Telegram
"""

from __future__ import annotations

import argparse
import json
import logging
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path.home() / "Code" / "Sapphire"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "lib" / "telegram" / "src"))

from services.pipeline import check_routines  # noqa: E402

HISTORY = ROOT / "data" / "routines" / "history.ndjson"

log = logging.getLogger("routine_controller")


def audit() -> tuple[list[dict], int]:
    """Run the full check. Returns (rows, exit_code)."""
    start = time.time()
    rows, exit_code = check_routines.run()
    duration_ms = int((time.time() - start) * 1000)
    for r in rows:
        r["_audit_duration_ms"] = duration_ms
    return rows, exit_code


def heal(rows: list[dict]) -> list[dict]:
    """Attempt to restart any failed launchagent_* routines.

    Returns a list of healing actions taken.
    """
    actions: list[dict] = []
    by_name = {r.name: r for r in check_routines.ROUTINES}

    for row in rows:
        if row.get("ok"):
            continue
        name = row["name"]
        routine = by_name.get(name)
        if not routine or not routine.launchagent:
            continue

        label = routine.launchagent
        # Kickstart: -k kills existing, restarts. Requires LaunchAgent loaded.
        try:
            uid = subprocess.run(["id", "-u"], capture_output=True, text=True, timeout=5).stdout.strip()
            cmd = ["launchctl", "kickstart", "-k", f"gui/{uid}/{label}"]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
            actions.append(
                {
                    "name": name,
                    "label": label,
                    "cmd": " ".join(cmd),
                    "rc": result.returncode,
                    "stdout": result.stdout.strip()[:200],
                    "stderr": result.stderr.strip()[:200],
                    "healed": result.returncode == 0,
                }
            )
        except Exception as e:
            actions.append(
                {"name": name, "label": label, "healed": False, "error": str(e)[:200]}
            )
    return actions


def log_history(rows: list[dict], actions: list[dict]) -> None:
    HISTORY.parent.mkdir(parents=True, exist_ok=True)
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "total": len(rows),
        "ok": sum(1 for r in rows if r.get("ok")),
        "failing": [r["name"] for r in rows if not r.get("ok")],
        "healed": [a["name"] for a in actions if a.get("healed")],
        "audit_duration_ms": rows[0]["_audit_duration_ms"] if rows else 0,
    }
    with HISTORY.open("a") as f:
        f.write(json.dumps(entry) + "\n")


def format_summary(rows: list[dict], actions: list[dict]) -> str:
    """Plaintext-safe summary for Telegram."""
    ok = [r for r in rows if r.get("ok")]
    bad = [r for r in rows if not r.get("ok")]
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    lines = [
        f"Routine Health — {ts}",
        f"{len(ok)}/{len(rows)} healthy",
    ]
    if bad:
        lines.append("")
        lines.append(f"FAILING ({len(bad)}):")
        for r in bad:
            detail = r.get("detail", "?")[:100]
            lines.append(f"  - {r['name']}: {detail}")
    if actions:
        lines.append("")
        lines.append(f"HEALING ACTIONS ({len(actions)}):")
        for a in actions:
            result = "✓" if a.get("healed") else "✗"
            lines.append(f"  {result} {a['name']}")

    # Freshness block
    import time as _t

    fresh_rows = []
    for r in rows:
        age = r.get("age_secs")
        if age is None:
            continue
        hrs = age / 3600
        if hrs < 1:
            age_str = f"{age // 60:.0f}m"
        elif hrs < 48:
            age_str = f"{hrs:.1f}h"
        else:
            age_str = f"{hrs / 24:.1f}d"
        fresh_rows.append((r["name"], age_str))
    if fresh_rows:
        lines.append("")
        lines.append("FRESHNESS:")
        for name, age in fresh_rows[:10]:
            lines.append(f"  {name}: {age}")

    return "\n".join(lines)


def send_summary(summary: str, priority: str = "p2") -> dict:
    """Send via safe_send. Returns API result dict."""
    try:
        from sapphire_telegram.safe_send import send
        return send(summary, priority=priority, prefix=True, banner=None)
    except ImportError as e:
        log.warning("safe_send unavailable: %s", e)
        return {"ok": False, "error": str(e)}


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    p = argparse.ArgumentParser(description="Routine health controller")
    p.add_argument("--check", action="store_true", help="Audit only (default)")
    p.add_argument("--heal", action="store_true", help="Audit + restart failing agents")
    p.add_argument("--summary", action="store_true", help="Audit + send Telegram summary")
    p.add_argument("--all", action="store_true", help="Audit + heal + summary")
    p.add_argument("--priority", default="p2", choices=["p0", "p1", "p2"])
    p.add_argument("--json", action="store_true", help="Emit rows as JSON to stdout")
    args = p.parse_args()

    # Default mode
    if not (args.check or args.heal or args.summary or args.all):
        args.check = True

    rows, exit_code = audit()
    actions: list[dict] = []

    if args.heal or args.all:
        actions = heal(rows)
        if actions:
            log.info("Healing actions: %s", [a["name"] for a in actions])

    log_history(rows, actions)

    if args.json:
        print(json.dumps({"rows": rows, "actions": actions}, indent=2, default=str))
    else:
        ok = sum(1 for r in rows if r.get("ok"))
        print(f"{ok}/{len(rows)} routines healthy ({len(actions)} healing actions)")
        for r in rows:
            if not r.get("ok"):
                print(f"  ✗ {r['name']}: {r.get('detail', '?')}")
        for a in actions:
            mark = "✓" if a.get("healed") else "✗"
            print(f"  heal {mark} {a['name']}")

    if args.summary or args.all:
        summary = format_summary(rows, actions)
        # escalate priority if anything is still failing after heal
        still_failing = sum(1 for r in rows if not r.get("ok"))
        prio = args.priority
        if still_failing > 0 and args.priority == "p2":
            prio = "p1"
        result = send_summary(summary, priority=prio)
        if not result.get("ok"):
            log.warning("Telegram summary failed: %s", result)
            return 2

    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
