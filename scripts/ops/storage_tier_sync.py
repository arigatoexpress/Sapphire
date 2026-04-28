#!/usr/bin/env python3
"""Plan, verify, or explicitly apply Sapphire storage-tier sync actions."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PROTON_ROOT = (
    Path.home() / "Library/CloudStorage/ProtonDrive-aribspector@proton.me-folder/Sapphire-OS"
)


@dataclass(frozen=True)
class SyncAction:
    tier: str
    operation: str
    source: str
    destination: str
    reason: str
    writes: bool


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--plan", action="store_true", help="Print the plan without writes. Default.")
    mode.add_argument("--apply", action="store_true", help="Execute local copy actions.")
    mode.add_argument("--verify", action="store_true", help="Verify source/destination readiness.")
    parser.add_argument("--i-mean-it", action="store_true", help="Required with --apply.")
    parser.add_argument("--repo-root", type=Path, default=ROOT)
    parser.add_argument("--proton-root", type=Path, default=DEFAULT_PROTON_ROOT)
    args = parser.parse_args(argv)

    repo = args.repo_root.resolve()
    proton_root = args.proton_root.expanduser().resolve()
    actions = build_plan(repo, proton_root)

    if args.apply and not args.i_mean_it:
        print("--apply requires --i-mean-it. No writes performed.")
        print_plan(actions)
        return 2
    if args.verify:
        return verify(actions)
    if args.apply:
        return apply(actions)
    print_plan(actions)
    return 0


def build_plan(repo: Path, proton_root: Path) -> list[SyncAction]:
    cold_root = proton_root / "cold-tier" / "sapphire"
    actions = [
        SyncAction(
            "T2-hot",
            "verify_only",
            str(repo / "data/health"),
            "local retention window: 7 days",
            "hot service-health telemetry should stay local until promoted",
            False,
        ),
        SyncAction(
            "T2-hot",
            "verify_only",
            str(repo / "data/.gcp_stage"),
            "gs://sapphire-data-lake staging",
            "GCP staging must be visible before any prune decision",
            False,
        ),
    ]
    cold_candidates = [
        (
            "legacy_code",
            "legacy_code",
            "legacy source is frozen and should leave git after cold backup proof",
        ),
        ("results", "results", "dated generated reports are cold artifacts, not active source"),
        (
            "data/benchmarks",
            "data-benchmarks",
            "benchmark output should be preserved outside git/local hot paths",
        ),
    ]
    for source_rel, dest_name, reason in cold_candidates:
        source = repo / source_rel
        if source.exists():
            actions.append(
                SyncAction(
                    "T4-cold",
                    "copy_tree",
                    str(source),
                    str(cold_root / dest_name),
                    reason,
                    True,
                )
            )
    return actions


def print_plan(actions: list[SyncAction]) -> None:
    print("# Sapphire Storage Tier Sync Plan")
    for action in actions:
        write_label = "write" if action.writes else "read-only"
        print(f"- [{action.tier}] {action.operation} ({write_label})")
        print(f"  read: {action.source}")
        print(f"  write: {action.destination if action.writes else 'none'}")
        print(f"  reason: {action.reason}")


def verify(actions: list[SyncAction]) -> int:
    print("# Sapphire Storage Tier Sync Verification")
    failed = False
    for action in actions:
        src = Path(action.source)
        dst = Path(action.destination) if action.writes else None
        src_ok = src.exists()
        dst_parent_ok = True if dst is None else nearest_existing_parent(dst).exists()
        print(
            f"- {action.operation}: source_exists={src_ok} destination_root_exists={dst_parent_ok}"
        )
        print(f"  read: {action.source}")
        print(f"  write: {action.destination if action.writes else 'none'}")
        failed = failed or (action.writes and not src_ok) or not dst_parent_ok
    return 1 if failed else 0


def apply(actions: list[SyncAction]) -> int:
    print("# Sapphire Storage Tier Sync Apply")
    manifest = {
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "actions": [],
    }
    for action in actions:
        print(f"- considering {action.operation}")
        print(f"  read: {action.source}")
        print(f"  write: {action.destination if action.writes else 'none'}")
        if not action.writes or action.operation != "copy_tree":
            manifest["actions"].append({**asdict(action), "status": "skipped_read_only"})
            continue
        src = Path(action.source)
        dst = Path(action.destination)
        if not src.exists():
            manifest["actions"].append({**asdict(action), "status": "missing_source"})
            continue
        dst.parent.mkdir(parents=True, exist_ok=True)
        if dst.exists():
            manifest["actions"].append({**asdict(action), "status": "destination_exists"})
            continue
        shutil.copytree(src, dst, symlinks=True)
        manifest["actions"].append(
            {**asdict(action), "status": "copied", "source_hash": tree_hash(src)}
        )
    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0


def tree_hash(path: Path) -> str:
    digest = hashlib.sha256()
    if path.is_file():
        digest.update(path.read_bytes())
        return digest.hexdigest()
    for child in sorted(p for p in path.rglob("*") if p.is_file()):
        digest.update(child.relative_to(path).as_posix().encode())
        digest.update(child.read_bytes())
    return digest.hexdigest()


def nearest_existing_parent(path: Path) -> Path:
    current = path
    while not current.exists() and current.parent != current:
        current = current.parent
    return current


if __name__ == "__main__":
    raise SystemExit(main())
