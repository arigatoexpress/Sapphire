#!/usr/bin/env python3
"""Sapphire log rotation — runs daily via LaunchAgent.

Rotates every directory in LOG_DIRS. Keeps the 3 most recent rotated copies;
deletes older ones. Max size before rotation: 5MB.

Coverage matters more than it looks: this job exits 0 whether or not it found
anything, so a directory missing from LOG_DIRS is silently unrotated forever
while the run still reports success.
"""

import gzip
import shutil
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from lib.core.routine_pause import abort_if_paused  # noqa: E402

MAX_BYTES = 5 * 1024 * 1024  # 5 MB
KEEP_COPIES = 3

LOG_DIRS = [
    Path.home() / "autonomy-status" / "logs",
    Path.home() / ".hermes" / "logs",
    # Added 2026-07-28. com.sapphire.moss-publisher retries a 503 endpoint every
    # 60s and had written a 6.7MB .err here over ~4 days while logrotate exited
    # 0 the whole time — the directory simply was not in this list.
    Path.home() / "ops-state" / "logs",
    # Holds webhook-tunnel.log, the largest log on the box (15MB and growing).
    ROOT / "data" / "logs",
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
    print(
        f"  rotated: {path.name} → {rotated.name} ({rotated.stat().st_size // 1024}KB compressed)"
    )
    return True


def prune_old_rotations(log_dir: Path, stem: str) -> None:
    """Keep only the KEEP_COPIES most recent .gz files for a given log stem."""
    pattern = f"{stem}.*.gz"
    old = sorted(log_dir.glob(pattern), key=lambda p: p.stat().st_mtime, reverse=True)
    for stale in old[KEEP_COPIES:]:
        stale.unlink()
        print(f"  pruned: {stale.name}")


def main():
    abort_if_paused("logrotate")
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
