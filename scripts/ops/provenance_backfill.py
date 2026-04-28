#!/usr/bin/env python3
"""Backfill provenance sidecars for generated Sapphire artifacts.

Dry-run is the default. Use ``--apply --i-mean-it`` to write
``<artifact>.envelope.json`` siblings.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from lib.core.provenance import sidecar_path, write_envelope_sidecar  # noqa: E402

DEFAULT_ROOTS = (
    ROOT / "data" / ".autonomy",
    ROOT / "data" / "content" / "drafts",
    ROOT / "data" / "intelligence",
)


def iter_artifacts(roots: tuple[Path, ...]) -> list[Path]:
    artifacts: list[Path] = []
    for root in roots:
        if not root.exists():
            continue
        for path in sorted(root.rglob("*")):
            if not path.is_file():
                continue
            if path.name.endswith(".envelope.json"):
                continue
            artifacts.append(path)
    return artifacts


def build_report(roots: tuple[Path, ...], *, apply: bool) -> dict[str, Any]:
    artifacts = iter_artifacts(roots)
    rows: list[dict[str, Any]] = []
    for path in artifacts:
        sidecar = sidecar_path(path)
        action = "exists" if sidecar.exists() else ("write" if apply else "would_write")
        if apply and not sidecar.exists():
            stat = path.stat()
            write_envelope_sidecar(
                path,
                generator="scripts.ops.provenance_backfill",
                metadata={
                    "backfilled": True,
                    "artifact_mtime": datetime.fromtimestamp(stat.st_mtime, tz=UTC)
                    .replace(microsecond=0)
                    .isoformat(),
                },
            )
        rows.append({"artifact": str(path), "sidecar": str(sidecar), "action": action})
    return {
        "schema_version": 1,
        "mode": "apply" if apply else "dry-run",
        "roots": [str(root) for root in roots],
        "artifacts": len(artifacts),
        "sidecars_existing": sum(1 for row in rows if row["action"] == "exists"),
        "sidecars_to_write": sum(1 for row in rows if row["action"] == "would_write"),
        "sidecars_written": sum(1 for row in rows if row["action"] == "write"),
        "rows": rows,
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", action="append", type=Path, help="Artifact root to scan.")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--i-mean-it", action="store_true")
    parser.add_argument("--pretty", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    apply = bool(args.apply and args.i_mean_it)
    roots = tuple(args.root) if args.root else DEFAULT_ROOTS
    report = build_report(tuple(path.expanduser() for path in roots), apply=apply)
    print(json.dumps(report, indent=2 if args.pretty else None, sort_keys=bool(args.pretty)))
    if args.apply and not args.i_mean_it:
        return 64
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
