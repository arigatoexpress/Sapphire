#!/usr/bin/env python3
"""Audit sapphirealpha.xyz public trading/data surfaces for scarcity & honesty."""

from __future__ import annotations

import argparse
import json
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from lib.grok.public_surface import diagnose_public_payloads, public_operating_rules  # noqa: E402


def _get(url: str, timeout: float = 15.0) -> dict:
    req = urllib.request.Request(url, method="GET")
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
        return json.loads(resp.read().decode("utf-8"))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="https://sapphirealpha.xyz")
    ap.add_argument("--write", type=Path, default=None)
    args = ap.parse_args()
    base = args.base.rstrip("/")
    live = widgets = {}
    errors = []
    try:
        live = _get(f"{base}/api/v1/live")
    except Exception as exc:  # noqa: BLE001
        errors.append(f"live: {exc}")
    try:
        widgets = _get(f"{base}/api/v1/widgets")
    except Exception as exc:  # noqa: BLE001
        errors.append(f"widgets: {exc}")

    report = diagnose_public_payloads(live=live, widgets=widgets)
    report["errors"] = errors
    report["base"] = base
    report["rules_schema"] = public_operating_rules()["schema"]
    text = json.dumps(report, indent=2)
    print(text)
    if args.write:
        args.write.parent.mkdir(parents=True, exist_ok=True)
        args.write.write_text(text + "\n", encoding="utf-8")
    # non-zero if P0 issues
    p0 = [i for i in report.get("issues") or [] if i.get("sev") == "P0"]
    return 1 if p0 or errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
