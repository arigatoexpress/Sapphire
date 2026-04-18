#!/usr/bin/env python3
"""Sapphire log rotation — runs daily via LaunchAgent.

Rotates logs in ~/autonomy-status/logs/ and ~/.hermes/logs/.
Keeps the 3 most recent rotated copies; deletes older ones.
Max size before rotation: 5MB.
"""

import gzip
import shutil
from datetime import datetime
from pathlib import Path

MAX_BYTES = 5 * 1024 * 1024  # 5 MB
KEEP_COPIES = 3

LOG_DIRS = [
    Path.home() / "autonomy-status" / "logs",
    Path.home() / ".hermes" / "logs",
]

EXTENSIONS = {".log", ".err"}


def rotate_file(path: Path) -> bool:
    """Rotate a single log file if it exceeds MAX_BYTES. Returns True if rotated."""
    if not path.exists() or path.stat().st_size < MAX_BYTES:
        return False

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    rotated = path.with_suffix(f".{stamp}{path.suffix}.gz")

    with path.open("rb") as f_in, gzip.open(rotated, "wb") as f_out:
        shutil.copyfileobj(f_in, f_out)

    # Truncate (not delete) so the running process can keep writing
    path.write_bytes(b"")
    print(f"  rotated: {path.name} → {rotated.name} ({rotated.stat().st_size // 1024}KB compressed)")
    return True


def prune_old_rotations(log_dir: Path, stem: str) -> None:
    """Keep only the KEEP_COPIES most recent .gz files for a given log stem."""
    pattern = f"{stem}.*.gz"
    old = sorted(log_dir.glob(pattern), key=lambda p: p.stat().st_mtime, reverse=True)
    for stale in old[KEEP_COPIES:]:
        stale.unlink()
        print(f"  pruned: {stale.name}")


def main():
    print(f"[logrotate] {datetime.now().isoformat()}")
    for log_dir in LOG_DIRS:
        if not log_dir.exists():
            continue
        for f in sorted(log_dir.iterdir()):
            if f.suffix in EXTENSIONS and not f.name.endswith(".gz"):
                stem = f.stem
                rotated = rotate_file(f)
                if rotated:
                    prune_old_rotations(log_dir, stem)
    print("[logrotate] done")


if __name__ == "__main__":
    main()
