#!/usr/bin/env python3
"""Hourly live-portfolio ramp status daemon.

The daemon reads only local JSONL ledger files. It never calls a broker API and
never submits trades.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from lib.core.provenance import ProvenanceEnvelope  # noqa: E402
from lib.live_portfolio.ledger import DEFAULT_LEDGER_ROOT, LiveLedger  # noqa: E402
from lib.live_portfolio.ramp_gate import evaluate_ramp_gate, write_status_jsonl  # noqa: E402

DEFAULT_INTERVAL_SECONDS = 3600


def _load_returns(path: Path | None) -> list[float]:
    if path is None or not path.exists():
        return []
    out: list[float] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        value = row.get("return") if isinstance(row, dict) else row
        try:
            out.append(float(value))
        except (TypeError, ValueError):
            continue
    return out


def _status_with_provenance(status: dict[str, Any]) -> dict[str, Any]:
    envelope = ProvenanceEnvelope.build(
        status,
        generator="services.live_portfolio_daemon",
        metadata={"live_api_calls": 0, "broker_mutation": False},
    ).to_dict()
    return {**status, "provenance": envelope}


def _publish_change(status: dict[str, Any]) -> str | None:
    if os.environ.get("SAPPHIRE_LIVE_PORTFOLIO_PUBLISH_BUS") != "1":
        return None
    from lib.core.event_bus import get_bus

    return get_bus(source="live_portfolio_daemon").publish(
        "ramp.gate.status.changed",
        status,
        source="live_portfolio_daemon",
    )


def run_once(
    *,
    ledger_root: str | Path = DEFAULT_LEDGER_ROOT,
    account_hash: str | None = None,
    returns_path: str | Path | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    ledger = LiveLedger(ledger_root)
    accounts = [account_hash] if account_hash else ledger.accounts()
    if not accounts:
        return {"ok": True, "accounts": [], "statuses": [], "note": "no live ledger accounts found"}

    returns = _load_returns(Path(returns_path) if returns_path else None)
    statuses: list[dict[str, Any]] = []
    for account in accounts:
        status = evaluate_ramp_gate(ledger, account_hash=account, returns=returns, now=now)
        row = _status_with_provenance(status.to_dict())
        path = write_status_jsonl(ledger, status, account_hash=account)
        event_id = _publish_change(row)
        statuses.append({"account_hash": account, "status": row, "path": str(path), "event_id": event_id})
    return {
        "ok": True,
        "accounts": accounts,
        "statuses": statuses,
        "generated_at": (now or datetime.now(UTC)).astimezone(UTC).replace(microsecond=0).isoformat(),
    }


async def run_forever(interval_seconds: int = DEFAULT_INTERVAL_SECONDS, **kwargs: Any) -> None:
    while True:
        run_once(**kwargs)
        await asyncio.sleep(interval_seconds)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ledger-root", default=str(DEFAULT_LEDGER_ROOT))
    parser.add_argument("--account-hash")
    parser.add_argument("--returns-path")
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--interval-seconds", type=int, default=DEFAULT_INTERVAL_SECONDS)
    args = parser.parse_args(argv)
    if args.once:
        print(
            json.dumps(
                run_once(
                    ledger_root=args.ledger_root,
                    account_hash=args.account_hash,
                    returns_path=args.returns_path,
                ),
                indent=2,
                sort_keys=True,
            )
        )
        return 0
    asyncio.run(
        run_forever(
            interval_seconds=args.interval_seconds,
            ledger_root=args.ledger_root,
            account_hash=args.account_hash,
            returns_path=args.returns_path,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
