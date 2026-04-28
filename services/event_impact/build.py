#!/usr/bin/env python3
"""Build the historical event-impact lookup table.

The script is intentionally one-shot and dry-run friendly. It can fetch
OHLCV from the local OpenBB API, but tests mock the fetcher and never
require a network service.
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.parse
import urllib.request
from datetime import UTC, datetime, timedelta
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from lib.core.provenance import write_envelope_sidecar  # noqa: E402
from lib.event_impact import (  # noqa: E402
    DEFAULT_CORPUS_PATH,
    PriceBar,
    build_impact_model,
    load_events,
)

DEFAULT_OUTPUT_DIR = REPO_ROOT / "data" / "event_impact"
DEFAULT_OPENBB_URL = "http://127.0.0.1:6900"
DEFAULT_ASSETS = ("BTC", "ETH", "SOL", "SPY", "GLD")


def fetch_ohlcv(
    asset: str,
    *,
    days: int = 3650,
    openbb_url: str = DEFAULT_OPENBB_URL,
    timeout_seconds: float = 10.0,
) -> list[PriceBar]:
    """Fetch OHLCV from local OpenBB-compatible HTTP JSON.

    The endpoint shape varies across OpenBB deployments; this parser accepts
    either ``{"results": [...]}``, ``{"data": [...]}``, or a bare list.
    """
    end = datetime.now(UTC)
    start = end - timedelta(days=days)
    params = urllib.parse.urlencode(
        {
            "symbol": asset,
            "start_date": start.date().isoformat(),
            "end_date": end.date().isoformat(),
            "provider": "yfinance",
        }
    )
    url = f"{openbb_url.rstrip('/')}/api/v1/equity/price/historical?{params}"
    req = urllib.request.Request(url, headers={"User-Agent": "SapphireEventImpact/0.1"})
    with urllib.request.urlopen(req, timeout=timeout_seconds) as resp:  # noqa: S310 - local API
        raw = json.loads(resp.read().decode("utf-8"))
    rows = raw.get("results") or raw.get("data") if isinstance(raw, dict) else raw
    if not isinstance(rows, list):
        return []
    bars: list[PriceBar] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        try:
            bars.append(PriceBar.from_dict(row))
        except (TypeError, ValueError, KeyError):
            continue
    return bars


def build(
    *,
    corpus_path: Path = DEFAULT_CORPUS_PATH,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    assets: tuple[str, ...] = DEFAULT_ASSETS,
    fetcher=fetch_ohlcv,
    days: int = 3650,
) -> Path:
    events = load_events(corpus_path)
    bars_by_asset = {asset: fetcher(asset, days=days) for asset in assets}
    model = build_impact_model(events, bars_by_asset)
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / f"model_{datetime.now(UTC).date().isoformat()}.json"
    path.write_text(json.dumps(model.to_dict(), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    write_envelope_sidecar(
        path,
        generator="services.event_impact.build",
        source_paths=(corpus_path,),
        ttl_seconds=30 * 24 * 3600,
        metadata={"assets": list(assets), "days": days},
    )
    return path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", type=Path, default=DEFAULT_CORPUS_PATH)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--asset", action="append", dest="assets")
    parser.add_argument("--days", type=int, default=3650)
    args = parser.parse_args(argv)
    path = build(
        corpus_path=args.corpus,
        output_dir=args.output_dir,
        assets=tuple(args.assets or DEFAULT_ASSETS),
        days=args.days,
    )
    print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
