#!/usr/bin/env python3
"""sapphire_budget — token usage report per inference tier.

Input schema (optional):
    {} — show today's budget
    {"date": "2026-04-01"} — show specific date
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "lib"))
from token_governor import format_report, status


def main():
    try:
        input_data = json.loads(sys.stdin.read())
    except (json.JSONDecodeError, EOFError):
        input_data = {}

    if input_data.get("json"):
        print(json.dumps(status(), indent=2))
    else:
        print(format_report())


if __name__ == "__main__":
    main()
