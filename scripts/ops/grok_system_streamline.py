#!/usr/bin/env python3
"""Streamline + test the Grok-linked system surface (alpha, policy, bridge, autos).

Usage:
  python3 scripts/ops/grok_system_streamline.py
  python3 scripts/ops/grok_system_streamline.py --write
  python3 scripts/ops/grok_system_streamline.py --write --export
  python3 scripts/ops/grok_system_streamline.py --check   # exit 1 if policy smoke fails
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from lib.grok.system_brief import (  # noqa: E402
    build_system_brief,
    render_brief_markdown,
    write_brief,
)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--write", action="store_true", help="write projects/grok SYSTEM_BRIEF.*")
    ap.add_argument(
        "--export",
        action="store_true",
        help="also write data/grok-web-exports/YYYY-MM-DD_system-brief.md",
    )
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--check", action="store_true", help="fail if policy smoke not ok")
    args = ap.parse_args()

    brief = build_system_brief()

    if args.write:
        paths = write_brief(brief)
        print(f"wrote {paths['json'].relative_to(ROOT)}", file=sys.stderr)
        print(f"wrote {paths['md'].relative_to(ROOT)}", file=sys.stderr)

    if args.export:
        day = datetime.now(tz=UTC).strftime("%Y-%m-%d")
        exp = ROOT / "data" / "grok-web-exports" / f"{day}_system-brief.md"
        body = render_brief_markdown(brief)
        exp.write_text(
            "---\n"
            "source: grok-web\n"
            f"date: {day}\n"
            "type: system-brief\n"
            "topics: [streamline, alpha, policy, bridge, automations]\n"
            "title: Sapphire system brief (alpha + policy + bridge)\n"
            "---\n\n" + body,
            encoding="utf-8",
        )
        print(f"wrote {exp.relative_to(ROOT)}", file=sys.stderr)

    if args.json:
        print(json.dumps(brief, indent=2))
    else:
        print(render_brief_markdown(brief))

    if args.check and not (brief.get("policy_smoke") or {}).get("ok"):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
