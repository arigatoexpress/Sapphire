#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import json
import shutil
from pathlib import Path
from typing import Any

SKILL_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DEBUG_ROOT = SKILL_ROOT / "output" / "executor-debug"


def _bytes_human(n: int) -> str:
    v = float(max(0, int(n)))
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if v < 1024.0 or unit == "TB":
            return f"{v:.1f}{unit}" if unit != "B" else f"{int(v)}B"
        v /= 1024.0
    return f"{int(n)}B"


def _dir_stats(path: Path) -> tuple[int, int]:
    total_bytes = 0
    file_count = 0
    stack = [path]
    while stack:
        cur = stack.pop()
        try:
            for entry in cur.iterdir():
                try:
                    if entry.is_symlink():
                        continue
                    if entry.is_dir():
                        stack.append(entry)
                    elif entry.is_file():
                        st = entry.stat()
                        total_bytes += int(st.st_size)
                        file_count += 1
                except FileNotFoundError:
                    continue
        except FileNotFoundError:
            continue
    return total_bytes, file_count


def _list_run_dirs(root: Path) -> list[dict[str, Any]]:
    if not root.exists():
        return []
    runs: list[dict[str, Any]] = []
    for child in root.iterdir():
        if not child.is_dir():
            continue
        try:
            st = child.stat()
        except FileNotFoundError:
            continue
        size_bytes, file_count = _dir_stats(child)
        runs.append(
            {
                "path": str(child),
                "name": child.name,
                "mtime_epoch": float(st.st_mtime),
                "size_bytes": int(size_bytes),
                "file_count": int(file_count),
            }
        )
    runs.sort(key=lambda r: (float(r.get("mtime_epoch") or 0.0), str(r.get("name") or "")), reverse=True)
    return runs


def _now_epoch() -> float:
    return dt.datetime.now(dt.timezone.utc).timestamp()


def _annotate_age(records: list[dict[str, Any]], now_epoch: float) -> None:
    for r in records:
        age_seconds = max(0.0, now_epoch - float(r.get("mtime_epoch") or now_epoch))
        r["age_seconds"] = round(age_seconds, 3)
        r["age_days"] = round(age_seconds / 86400.0, 6)
        r["mtime_iso"] = dt.datetime.fromtimestamp(float(r.get("mtime_epoch") or 0.0), tz=dt.timezone.utc).isoformat()


def _plan_cleanup(
    records: list[dict[str, Any]],
    *,
    keep_last: int,
    max_age_days: float | None,
    max_total_bytes: int | None,
) -> dict[str, Any]:
    keep_last = max(0, int(keep_last))
    decisions: list[dict[str, Any]] = []
    total_before = sum(int(r.get("size_bytes") or 0) for r in records)
    records_sorted = list(records)  # already newest -> oldest
    protected_paths = {str(r.get("path")) for r in records_sorted[:keep_last]}

    delete_by_age: set[str] = set()
    if max_age_days is not None and max_age_days >= 0:
        age_limit_seconds = float(max_age_days) * 86400.0
        for r in records_sorted:
            path = str(r.get("path"))
            if path in protected_paths:
                continue
            if float(r.get("age_seconds") or 0.0) > age_limit_seconds:
                delete_by_age.add(path)
                decisions.append({"path": path, "reason": "age", "age_days": r.get("age_days"), "size_bytes": r.get("size_bytes")})

    remaining = [r for r in records_sorted if str(r.get("path")) not in delete_by_age]
    total_after_age = sum(int(r.get("size_bytes") or 0) for r in remaining)
    delete_by_size: list[str] = []
    if max_total_bytes is not None and max_total_bytes >= 0 and total_after_age > max_total_bytes:
        current_total = total_after_age
        # Oldest first for size pruning.
        for r in sorted(remaining, key=lambda x: (float(x.get("mtime_epoch") or 0.0), str(x.get("name") or ""))):
            path = str(r.get("path"))
            if path in protected_paths:
                continue
            if current_total <= max_total_bytes:
                break
            delete_by_size.append(path)
            current_total -= int(r.get("size_bytes") or 0)
            decisions.append(
                {
                    "path": path,
                    "reason": "size",
                    "age_days": r.get("age_days"),
                    "size_bytes": r.get("size_bytes"),
                }
            )

    delete_set = {*(delete_by_age), *delete_by_size}
    keep = [r for r in records_sorted if str(r.get("path")) not in delete_set]
    delete = [r for r in records_sorted if str(r.get("path")) in delete_set]
    # Merge decision metadata by path for stable report.
    reasons_by_path: dict[str, list[str]] = {}
    for d in decisions:
        reasons_by_path.setdefault(str(d["path"]), []).append(str(d["reason"]))
    for r in delete:
        r["delete_reasons"] = sorted(set(reasons_by_path.get(str(r["path"]), [])))

    return {
        "keep": keep,
        "delete": delete,
        "totals": {
            "before_count": len(records_sorted),
            "before_bytes": total_before,
            "after_count": len(keep),
            "after_bytes": sum(int(r.get("size_bytes") or 0) for r in keep),
            "delete_count": len(delete),
            "delete_bytes": sum(int(r.get("size_bytes") or 0) for r in delete),
        },
        "policy": {
            "keep_last": keep_last,
            "max_age_days": max_age_days,
            "max_total_bytes": max_total_bytes,
        },
        "protected_paths": sorted(protected_paths),
    }


def _apply_cleanup(delete_records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for r in delete_records:
        path = Path(str(r.get("path")))
        rec = {
            "path": str(path),
            "name": r.get("name"),
            "size_bytes": r.get("size_bytes"),
            "delete_reasons": r.get("delete_reasons"),
        }
        try:
            if path.exists():
                shutil.rmtree(path)
            rec["deleted"] = True
        except Exception as e:  # noqa: BLE001
            rec["deleted"] = False
            rec["error"] = str(e)
        results.append(rec)
    return results


def _format_text(report: dict[str, Any]) -> str:
    t = report.get("totals") or {}
    lines = [
        f"Root: {report.get('root')}",
        f"Mode: {'dry-run' if report.get('dry_run') else 'apply'}",
        f"Policy: keep_last={((report.get('policy') or {}).get('keep_last'))} "
        f"max_age_days={((report.get('policy') or {}).get('max_age_days'))} "
        f"max_total_bytes={((report.get('policy') or {}).get('max_total_bytes'))}",
        f"Before: {t.get('before_count')} dirs, {_bytes_human(int(t.get('before_bytes') or 0))}",
        f"Delete: {t.get('delete_count')} dirs, {_bytes_human(int(t.get('delete_bytes') or 0))}",
        f"After: {t.get('after_count')} dirs, {_bytes_human(int(t.get('after_bytes') or 0))}",
    ]
    deleted = report.get("delete") or []
    if deleted:
        lines.append("Delete candidates:")
        for r in deleted[:20]:
            reasons = ",".join((r.get("delete_reasons") or []))
            lines.append(
                f"- {r.get('name')} size={_bytes_human(int(r.get('size_bytes') or 0))} age_days={r.get('age_days')} reasons={reasons}"
            )
        if len(deleted) > 20:
            lines.append(f"- ... ({len(deleted) - 20} more)")
    apply_results = report.get("apply_results") or []
    if apply_results:
        failed = [r for r in apply_results if not r.get("deleted")]
        lines.append(f"Apply results: deleted={len(apply_results)-len(failed)} failed={len(failed)}")
        for r in failed[:5]:
            lines.append(f"- failed {r.get('name')}: {r.get('error')}")
    return "\n".join(lines)


def main() -> int:
    p = argparse.ArgumentParser(description="Cleanup TradingView executor debug artifacts (age/size retention)")
    p.add_argument("--root", type=Path, default=DEFAULT_DEBUG_ROOT, help=f"Debug artifact root (default: {DEFAULT_DEBUG_ROOT})")
    p.add_argument("--keep-last", type=int, default=5, help="Always keep this many newest run directories")
    p.add_argument("--max-age-days", type=float, default=7.0, help="Delete dirs older than this age (days); <0 disables age pruning")
    p.add_argument(
        "--max-total-mb",
        type=float,
        default=512.0,
        help="After age pruning, prune oldest dirs until total size <= this MB; <0 disables size pruning",
    )
    p.add_argument("--dry-run", action="store_true", help="Plan only (default if --apply is not set)")
    p.add_argument("--apply", action="store_true", help="Delete the selected directories")
    p.add_argument("--json", action="store_true", help="Emit JSON report")
    args = p.parse_args()

    if args.apply and args.dry_run:
        p.error("Use either --apply or --dry-run, not both")

    root = args.root
    dry_run = not bool(args.apply)
    root.mkdir(parents=True, exist_ok=True)

    records = _list_run_dirs(root)
    now = _now_epoch()
    _annotate_age(records, now)

    max_age_days = None if args.max_age_days is None or args.max_age_days < 0 else float(args.max_age_days)
    max_total_bytes = None if args.max_total_mb is None or args.max_total_mb < 0 else int(float(args.max_total_mb) * 1024 * 1024)
    plan = _plan_cleanup(
        records,
        keep_last=max(0, int(args.keep_last)),
        max_age_days=max_age_days,
        max_total_bytes=max_total_bytes,
    )
    report: dict[str, Any] = {
        "root": str(root),
        "dry_run": dry_run,
        "generated_at": dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat(),
        **plan,
    }
    if not dry_run and plan.get("delete"):
        report["apply_results"] = _apply_cleanup(list(plan.get("delete") or []))

    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print(_format_text(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
