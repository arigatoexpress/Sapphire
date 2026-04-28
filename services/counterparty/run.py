#!/usr/bin/env python3
"""Counter-party intelligence refresh daemon.

Default behavior is read-only and dry-run friendly. Event-bus publishing
only occurs when explicitly requested by the caller.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from lib.core.provenance import write_envelope_sidecar  # noqa: E402
from lib.counterparty import (  # noqa: E402
    HyperliquidCounterpartyClient,
    generate_signals,
    track_position_changes,
)

DEFAULT_OUTPUT_ROOT = REPO_ROOT / "data" / "counterparty"


def refresh_once(
    *,
    client: HyperliquidCounterpartyClient | None = None,
    previous_positions: list[dict[str, Any]] | None = None,
    output_root: Path = DEFAULT_OUTPUT_ROOT,
    publish: bool = False,
) -> dict[str, Any]:
    client = client or HyperliquidCounterpartyClient()
    leaderboard = client.leaderboard()
    current = []
    for trader in leaderboard:
        current.extend(client.positions(trader.address))
    changes = track_position_changes(previous_positions or [], current)
    signals = generate_signals(changes)
    payload = {
        "generated_at": datetime.now(UTC).replace(microsecond=0).isoformat(),
        "leaderboard": [t.to_dict() for t in leaderboard],
        "position_changes": [c.to_dict() for c in changes],
        "signals": [s.to_dict() for s in signals],
        "mode": "live" if client.live_enabled else "dry-run",
    }
    target_dir = output_root / datetime.now(UTC).date().isoformat()
    target_dir.mkdir(parents=True, exist_ok=True)
    path = target_dir / "counterparty_signals.json"
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    write_envelope_sidecar(path, generator="services.counterparty.run", ttl_seconds=24 * 3600)
    if publish:
        from lib.core.event_bus import get_bus

        bus = get_bus(source="counterparty-intel")
        for signal in payload["signals"]:
            bus.publish("counterparty.smart_money.move", signal, source="counterparty-intel")
    payload["output_path"] = str(path)
    return payload


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", nargs="?", default="run-once", choices=["run-once"])
    parser.add_argument("--publish", action="store_true")
    args = parser.parse_args(argv)
    result = refresh_once(publish=args.publish)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
