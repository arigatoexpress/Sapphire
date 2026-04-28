#!/usr/bin/env python3
"""Foundry Sync LaunchAgent wrapper.

Delegates to lib.foundry.sync which handles delta-aware syncing
of Sapphire data sources to the Foundry ontology.

Called every 15 minutes by com.sapphire.foundry-sync LaunchAgent.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from lib.core.routine_pause import abort_if_paused  # noqa: E402


def main() -> int:
    abort_if_paused("foundry-sync")
    from lib.foundry.sync import run_sync

    result = run_sync()
    return 0 if result.ok else 1


if __name__ == "__main__":
    sys.exit(main())
