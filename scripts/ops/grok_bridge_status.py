#!/usr/bin/env python3
"""Grok web ↔ plant bridge status (read-only by default).

Inventories ``data/grok-web-exports/``, validates lightweight frontmatter, and
optionally writes ``MANIFEST.json`` for densify / plant deck consumers.

Usage:
  python3 scripts/ops/grok_bridge_status.py
  python3 scripts/ops/grok_bridge_status.py --write-manifest
  python3 scripts/ops/grok_bridge_status.py --json
  python3 scripts/ops/grok_bridge_status.py --check  # exit 1 if critical gaps
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
EXPORT_DIR = ROOT / "data" / "grok-web-exports"
MANIFEST_PATH = EXPORT_DIR / "MANIFEST.json"
FM_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)
KEY_RE = re.compile(r"^(?P<k>[A-Za-z0-9_-]+):\s*(?P<v>.*)$", re.MULTILINE)

# Mission-critical exports Claude densify / operators expect present
REQUIRED_HINTS = (
    "bridge-setup",
    "master-handoff",
    "alpha",
    "windows-datacenter-masterplan",
    "gcp-cloudshell",
)


@dataclass
class ExportItem:
    name: str
    size: int
    mtime_utc: str
    has_frontmatter: bool
    source: str | None
    date: str | None
    type: str | None
    title: str | None
    topics: list[str]
    issues: list[str]


def parse_frontmatter(text: str) -> dict[str, Any]:
    m = FM_RE.match(text)
    if not m:
        return {}
    block = m.group(1)
    out: dict[str, Any] = {}
    for line in block.splitlines():
        km = KEY_RE.match(line.strip())
        if not km:
            continue
        k, v = km.group("k"), km.group("v").strip()
        if v.startswith("[") and v.endswith("]"):
            inner = v[1:-1].strip()
            out[k] = [p.strip().strip("'\"") for p in inner.split(",") if p.strip()]
        else:
            out[k] = v.strip("\"'")
    return out


def inventory(export_dir: Path = EXPORT_DIR) -> list[ExportItem]:
    items: list[ExportItem] = []
    if not export_dir.is_dir():
        return items
    for path in sorted(export_dir.glob("*.md")):
        if path.name == "README.md":
            continue
        raw = path.read_text(encoding="utf-8", errors="replace")
        fm = parse_frontmatter(raw)
        issues: list[str] = []
        if not fm:
            issues.append("missing_frontmatter")
        if not fm.get("source"):
            issues.append("missing_source")
        if not fm.get("date"):
            issues.append("missing_date")
        # dated filename convention
        if not re.match(r"^\d{4}-\d{2}-\d{2}", path.name):
            issues.append("filename_not_dated")
        st = path.stat()
        topics = fm.get("topics") or []
        if isinstance(topics, str):
            topics = [topics]
        items.append(
            ExportItem(
                name=path.name,
                size=st.st_size,
                mtime_utc=datetime.fromtimestamp(st.st_mtime, tz=timezone.utc).strftime(
                    "%Y-%m-%dT%H:%M:%SZ"
                ),
                has_frontmatter=bool(fm),
                source=fm.get("source"),
                date=fm.get("date"),
                type=fm.get("type"),
                title=fm.get("title"),
                topics=list(topics),
                issues=issues,
            )
        )
    return items


def build_report(items: list[ExportItem]) -> dict[str, Any]:
    by_source: dict[str, int] = {}
    by_type: dict[str, int] = {}
    issue_count = 0
    for it in items:
        by_source[it.source or "unknown"] = by_source.get(it.source or "unknown", 0) + 1
        by_type[it.type or "unknown"] = by_type.get(it.type or "unknown", 0) + 1
        issue_count += len(it.issues)
    names = " ".join(it.name for it in items)
    missing_hints = [h for h in REQUIRED_HINTS if h not in names]
    return {
        "generated_at": datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "export_dir": str(EXPORT_DIR.relative_to(ROOT)),
        "count": len(items),
        "issue_count": issue_count,
        "by_source": by_source,
        "by_type": by_type,
        "missing_required_hints": missing_hints,
        "latest": [asdict(it) for it in items[-12:]],
        "items": [asdict(it) for it in items],
        "plant_sync": {
            "monorepo_script": "scripts/ops/sync_grok_web_exports.sh",
            "plant_wrapper": "~/ops-state/finish-line/scripts/sync_grok_web_exports.sh",
            "inbox": "~/Knowledge/0-Inbox/grok-web/",
            "deck": "http://127.0.0.1:8100/",
        },
        "ok": not missing_hints and issue_count == 0,
    }


def print_human(report: dict[str, Any]) -> None:
    print("═══════════════════════════════════════════════════════════")
    print("  SAPPHIRE GROK BRIDGE STATUS")
    print("═══════════════════════════════════════════════════════════")
    print(f"  dir:     {report['export_dir']}")
    print(f"  count:   {report['count']} exports")
    print(f"  issues:  {report['issue_count']}")
    print(f"  sources: {report['by_source']}")
    print(f"  types:   {report['by_type']}")
    if report["missing_required_hints"]:
        print(f"  MISSING hints: {report['missing_required_hints']}")
    else:
        print("  required topic hints: all present")
    print("  --- latest ---")
    for it in report["latest"]:
        flag = "!" if it["issues"] else " "
        print(f"  {flag} {it['name']}  ({it.get('source') or '?'} / {it.get('type') or '?'})")
    print("  --- plant ---")
    for k, v in report["plant_sync"].items():
        print(f"  {k}: {v}")
    print(f"  ok={report['ok']}")
    print("═══════════════════════════════════════════════════════════")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--write-manifest", action="store_true")
    ap.add_argument("--check", action="store_true", help="exit 1 if missing required hints")
    args = ap.parse_args(argv)

    items = inventory()
    report = build_report(items)

    if args.write_manifest:
        MANIFEST_PATH.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        print(f"wrote {MANIFEST_PATH.relative_to(ROOT)}", file=sys.stderr)

    if args.json:
        json.dump(report, sys.stdout, indent=2)
        sys.stdout.write("\n")
    else:
        print_human(report)

    if args.check and report["missing_required_hints"]:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
