#!/usr/bin/env python3
"""Build data/grok-drive-pack/ for Google Drive densify (sanitized)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from lib.grok.drive_bridge import build_drive_pack  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true", help="build pack (default)")
    ap.add_argument("--max-exports", type=int, default=40)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    man = build_drive_pack(max_exports=args.max_exports)
    if args.json:
        print(json.dumps(man, indent=2))
    else:
        print(f"pack: data/grok-drive-pack/  files={man['copied_count']} skipped={man['skipped_count']}")
        print(f"drive: {man.get('grok_bridge_url')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
