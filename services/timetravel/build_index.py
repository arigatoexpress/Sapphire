#!/usr/bin/env python3
"""Build the time-travel interval index over Sapphire's append-only JSONL.

Idempotent: running twice in succession produces the same on-disk
content because we hash the index body before writing. The script is a
read-only consumer of ``data/`` and never publishes events or sends
notifications.

Usage::

    python3 services/timetravel/build_index.py            # build, print summary
    python3 services/timetravel/build_index.py --rebuild  # force rescan
    python3 services/timetravel/build_index.py --status   # show index status
    python3 services/timetravel/build_index.py --json     # machine output
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from lib.timetravel.snapshot import (  # noqa: E402
    DEFAULT_SCOPE,
    INDEX_PATH,
    build_index,
    index_status,
)


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--rebuild",
        action="store_true",
        help="rescan the source roots even if a cached index already exists",
    )
    p.add_argument(
        "--status",
        action="store_true",
        help="print the cached index status without building anything",
    )
    p.add_argument(
        "--json",
        action="store_true",
        help="print the result as a JSON object",
    )
    p.add_argument(
        "--scope",
        action="append",
        default=None,
        help="scope to include (defaults to all six); pass multiple times",
    )
    p.add_argument(
        "--cache-path",
        default=str(INDEX_PATH),
        help="override the cached index path (used by tests)",
    )
    return p


def _scope_arg(args: argparse.Namespace) -> tuple[str, ...]:
    if not args.scope:
        return DEFAULT_SCOPE
    return tuple(s.strip() for s in args.scope if s.strip())


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    cache_path = Path(args.cache_path).expanduser()

    if args.status and not args.rebuild:
        status = index_status(cache_path=cache_path)
        if args.json:
            print(json.dumps(status, indent=2, sort_keys=True))
        else:
            print(_render_status(status))
        return 0

    body = build_index(scopes=_scope_arg(args), cache_path=cache_path)
    summary = {
        "ok": True,
        "scope": list(body.get("scopes") or {}),
        "files": int((body.get("totals") or {}).get("files", 0)),
        "rows": int((body.get("totals") or {}).get("rows", 0)),
        "signature": body.get("signature"),
        "built_at": body.get("built_at"),
        "cache_path": str(cache_path),
    }
    if args.json:
        print(json.dumps(summary, indent=2, sort_keys=True))
    else:
        print(_render_summary(summary))
    return 0


def _render_status(status: dict) -> str:
    lines = [
        f"index path:   {status.get('path')}",
        f"exists:       {status.get('exists')}",
        f"signature:    {status.get('signature')}",
        f"built at:     {status.get('built_at')}",
        f"file count:   {status.get('files')}",
        f"row count:    {status.get('rows')}",
    ]
    scopes = status.get("scopes") or []
    lines.append(f"scopes:       {', '.join(scopes) if scopes else '<none>'}")
    return "\n".join(lines)


def _render_summary(summary: dict) -> str:
    lines = [
        "time-travel index built.",
        f"  cache path:  {summary['cache_path']}",
        f"  signature:   {summary['signature']}",
        f"  built at:    {summary['built_at']}",
        f"  scope count: {len(summary['scope'])}",
        f"  file count:  {summary['files']}",
        f"  row count:   {summary['rows']}",
    ]
    return "\n".join(lines)


if __name__ == "__main__":
    raise SystemExit(main())
