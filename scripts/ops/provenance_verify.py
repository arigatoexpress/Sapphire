#!/usr/bin/env python3
"""Verify provenance sidecars for Sapphire-generated artifacts."""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from lib.core.provenance import sha256_file, sidecar_path, verify  # noqa: E402
from scripts.ops.provenance_backfill import DEFAULT_ROOTS, iter_artifacts  # noqa: E402


def verify_sidecar(path: Path) -> tuple[bool, str]:
    sidecar = sidecar_path(path)
    if not sidecar.exists():
        return False, "missing_sidecar"
    try:
        data = json.loads(sidecar.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False, "invalid_sidecar_json"
    if not isinstance(data, dict) or not verify(data):
        return False, "invalid_provenance_hash"
    artifact_sha = data.get("artifact_sha256")
    if artifact_sha and artifact_sha != sha256_file(path):
        return False, "artifact_hash_mismatch"
    metadata = (data.get("provenance") or {}).get("metadata") or {}
    return True, "backfilled" if metadata.get("backfilled") else "ok"


def build_report(roots: tuple[Path, ...], *, older_than_hours: float) -> dict[str, Any]:
    cutoff = time.time() - max(0.0, older_than_hours) * 3600.0
    rows: list[dict[str, Any]] = []
    for path in iter_artifacts(roots):
        try:
            mtime = path.stat().st_mtime
        except OSError:
            continue
        if mtime > cutoff:
            continue
        ok, reason = verify_sidecar(path)
        rows.append(
            {
                "artifact": str(path),
                "sidecar": str(sidecar_path(path)),
                "ok": ok,
                "reason": reason,
            }
        )
    missing = [row for row in rows if not row["ok"]]
    return {
        "schema_version": 1,
        "roots": [str(root) for root in roots],
        "older_than_hours": older_than_hours,
        "checked": len(rows),
        "ok": len(missing) == 0,
        "missing_or_invalid": len(missing),
        "rows": rows,
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", action="append", type=Path, help="Artifact root to scan.")
    parser.add_argument("--older-than-hours", type=float, default=24.0)
    parser.add_argument("--pretty", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    roots = tuple(args.root) if args.root else DEFAULT_ROOTS
    report = build_report(
        tuple(path.expanduser() for path in roots), older_than_hours=args.older_than_hours
    )
    print(json.dumps(report, indent=2 if args.pretty else None, sort_keys=bool(args.pretty)))
    return 0 if report["ok"] else 20


if __name__ == "__main__":
    raise SystemExit(main())
