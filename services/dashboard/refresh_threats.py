#!/usr/bin/env python3
"""Refresh threat intelligence data for the SOC dashboard.

Runs cyber-threat-bot and writes output to data/intelligence/YYYY-MM-DD/threats.json
so the /api/soc/threats endpoint can consume it. Runs every 4 hours via LaunchAgent.
"""
from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

THREAT_BOT_VENV = Path.home() / "Code" / "cyber-threat-bot" / ".venv"
THREAT_BOT_PY = THREAT_BOT_VENV / "bin" / "threat-bot"
DATA_DIR = Path.home() / "Code" / "Sapphire" / "data" / "intelligence"


def main() -> int:
    if not THREAT_BOT_PY.exists():
        print(f"threat-bot not found at {THREAT_BOT_PY}", file=sys.stderr)
        return 1

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    out_dir = DATA_DIR / today
    out_dir.mkdir(parents=True, exist_ok=True)

    result = subprocess.run(
        [str(THREAT_BOT_PY), "latest", "--days", "3", "--per-source", "5", "--format", "json"],
        capture_output=True,
        text=True,
        timeout=120,
    )
    if result.returncode != 0:
        print(f"threat-bot failed: {result.stderr}", file=sys.stderr)
        return result.returncode

    try:
        threats = json.loads(result.stdout)
    except json.JSONDecodeError as e:
        print(f"Invalid JSON from threat-bot: {e}", file=sys.stderr)
        return 1

    out_file = out_dir / "threats.json"
    payload = {
        "refreshed_at": datetime.now(timezone.utc).isoformat(),
        "source_count": len(threats),
        "threats": threats,
    }
    out_file.write_text(json.dumps(payload, indent=2))

    latest = DATA_DIR / "latest"
    try:
        if latest.is_symlink() or latest.exists():
            latest.unlink()
        latest.symlink_to(today)
    except Exception as e:
        print(f"Symlink update failed: {e}", file=sys.stderr)

    print(f"Wrote {len(threats)} threats to {out_file}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
