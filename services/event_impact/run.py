#!/usr/bin/env python3
"""Event-impact integration daemon helpers.

The full event-impact model is built by ``services.event_impact.build``. This
thin runtime layer listens to already-detected macro events and converts them
into expected-reaction events. Publishing is dry-run by default and gated by
``SAPPHIRE_EVENT_IMPACT_LIVE_BUS=1``.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from lib.event_impact.lookup import load_model  # noqa: E402
from lib.intelligence import expected_reaction_events  # noqa: E402

DEFAULT_MODEL_ROOT = REPO_ROOT / "data" / "event_impact"
EVENT_TOPIC = "event.expected_reaction.published"
GENERATOR = "services.event_impact.run"


def latest_model_path(model_root: str | Path = DEFAULT_MODEL_ROOT) -> Path | None:
    root = Path(model_root)
    candidates = sorted(root.glob("model_*.json"))
    return candidates[-1] if candidates else None


def _publish(rows: list[dict[str, Any]], *, requested: bool) -> dict[str, Any]:
    if not requested or os.getenv("SAPPHIRE_EVENT_IMPACT_LIVE_BUS") != "1":
        return {"requested": requested, "actual": False, "published": 0}
    try:
        from lib.core.event_bus import get_bus

        bus = get_bus(source="event-impact")
        for row in rows:
            bus.publish(EVENT_TOPIC, row, source="event-impact")
    except Exception as exc:  # noqa: BLE001 - publish must not break lookup.
        return {
            "requested": requested,
            "actual": False,
            "published": 0,
            "error": f"{type(exc).__name__}: {exc}",
        }
    return {"requested": requested, "actual": True, "published": len(rows)}


def handle_macro_event(
    macro_event: dict[str, Any],
    *,
    model: dict[str, Any] | Any | None = None,
    model_path: str | Path | None = None,
    assets: tuple[str, ...] = ("BTC", "ETH", "SOL"),
    horizons: tuple[int, ...] = (6, 24),
    publish: bool = False,
    generated_at: datetime | None = None,
) -> dict[str, Any]:
    if model is None:
        path = Path(model_path) if model_path else latest_model_path()
        if path is None:
            return {
                "ok": False,
                "reason": "no event-impact model found",
                "event_topic": EVENT_TOPIC,
                "published": _publish([], requested=False),
            }
        model = load_model(path)
    rows = expected_reaction_events(
        macro_event,
        model=model,
        assets=assets,
        horizons=horizons,
        generated_at=generated_at,
    )
    published = _publish(rows, requested=publish)
    return {
        "ok": True,
        "service": GENERATOR,
        "event_topic": EVENT_TOPIC,
        "reactions": rows,
        "published": published,
        "generated_at": (generated_at or datetime.now(UTC)).astimezone(UTC).isoformat(),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--macro-event-json", required=True, help="macro event payload JSON")
    parser.add_argument("--model-path", type=Path)
    parser.add_argument("--asset", action="append", dest="assets")
    parser.add_argument("--horizon", action="append", dest="horizons", type=int)
    parser.add_argument("--publish", action="store_true")
    args = parser.parse_args(argv)
    event = json.loads(args.macro_event_json)
    result = handle_macro_event(
        event,
        model_path=args.model_path,
        assets=tuple(args.assets or ("BTC", "ETH", "SOL")),
        horizons=tuple(args.horizons or (6, 24)),
        publish=args.publish,
    )
    print(json.dumps(result, indent=2, sort_keys=True, default=str))
    return 0 if result.get("ok") else 2


if __name__ == "__main__":
    raise SystemExit(main())
