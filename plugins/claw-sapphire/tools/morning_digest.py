#!/usr/bin/env python3
"""Send the scheduled Sapphire morning operational digest."""

from __future__ import annotations

import argparse
import json
from typing import Any

import dev_pulse
from notify import send_alert


def run(*, dry_run: bool = False) -> dict[str, Any]:
    """Collect dev pulse state and send the rich morning digest to Telegram."""
    pulse = dev_pulse.pulse()
    message = dev_pulse.format_morning_digest_markdown(pulse)
    if dry_run:
        return {
            "ok": True,
            "sent": False,
            "priority": "p3",
            "message": message,
            "pulse": pulse.to_dict(),
        }
    result = send_alert(message, priority="p3")
    return {
        "ok": not bool(result.get("error")),
        "sent": True,
        "priority": "p3",
        "result": result,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Send the Sapphire morning digest")
    parser.add_argument("--dry-run", action="store_true", help="Print the digest without sending")
    args = parser.parse_args()
    print(json.dumps(run(dry_run=args.dry_run), indent=2, sort_keys=True, default=str))


if __name__ == "__main__":
    main()
