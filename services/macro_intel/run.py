#!/usr/bin/env python3
"""Run the Sapphire regulatory + macro intelligence daemon.

Default posture is dry-run and bounded:

* no live HTTP unless ``--live`` or ``SAPPHIRE_MACRO_INTEL_LIVE=1``;
* no event-bus publish unless ``--publish`` and
  ``SAPPHIRE_MACRO_INTEL_LIVE_BUS=1``;
* source pull caps are enforced in ``lib.macro.sources``;
* output is append-only JSONL under ``data/macro/<YYYY-MM-DD>/``.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys
import time
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from lib.macro.calendar import MacroCalendar, build_calendar  # noqa: E402
from lib.macro.classifier import enrich_event  # noqa: E402
from lib.macro.fred_loader import (  # noqa: E402
    DEFAULT_MARKET_REGIME_SERIES,
    FredLoader,
    FredLoaderError,
    fred_cache_dir,
    fred_observation_rows,
)
from lib.macro.sources import (  # noqa: E402
    MAX_EVENTS_PER_PULL,
    MAX_FORWARD_CALENDAR_DAYS,
    MAX_PULLS_PER_HOUR_PER_SOURCE,
    BaseMacroSource,
    MacroEvent,
    SourceError,
    build_default_sources,
    cache_base_dir,
)

try:  # noqa: E402
    from lib.core.provenance import stamp, verify, write_envelope_sidecar
except ModuleNotFoundError:  # pragma: no cover - repo always ships this module.
    stamp = None  # type: ignore[assignment]
    verify = None  # type: ignore[assignment]
    write_envelope_sidecar = None  # type: ignore[assignment]

log = logging.getLogger(__name__)

DEFAULT_OUTPUT_ROOT = REPO_ROOT / "data" / "macro"
DEFAULT_POLL_INTERVAL_SECONDS = 15 * 60
GENERATOR = "services.macro_intel.run"
VERSION = "0.1.0"


def _now_utc() -> datetime:
    return datetime.now(UTC).replace(microsecond=0)


def _date_key(now: datetime | None = None) -> str:
    return (now or _now_utc()).astimezone(UTC).strftime("%Y-%m-%d")


def _events_path(output_root: Path, now: datetime | None = None) -> Path:
    return output_root / _date_key(now) / "events.jsonl"


def _calendar_path(output_root: Path, now: datetime | None = None) -> Path:
    return output_root / _date_key(now) / "calendar.jsonl"


def _fred_observations_path(output_root: Path, now: datetime | None = None) -> Path:
    return output_root / _date_key(now) / "fred_observations.jsonl"


def _read_jsonl(path: Path, *, limit: int = 500) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return rows[-max(1, limit) :]


def _stamp_payload(
    payload: dict[str, Any], *, source_paths: tuple[str | Path, ...]
) -> dict[str, Any]:
    if stamp is None:
        return payload
    return stamp(
        payload,
        generator=GENERATOR,
        source_paths=source_paths,
        ttl_seconds=7 * 86_400,
        metadata={
            "version": VERSION,
            "official_sources_cited": bool(
                payload.get("metadata", {}).get("source_url") or payload.get("source_url")
            ),
        },
    )


def _dedupe_existing_ids(path: Path) -> set[str]:
    seen: set[str] = set()
    for row in _read_jsonl(path, limit=10_000):
        row_id = row.get("id")
        if isinstance(row_id, str) and row_id:
            seen.add(row_id)
    return seen


def _write_jsonl(
    path: Path,
    rows: Sequence[dict[str, Any]],
    *,
    source_paths: tuple[str | Path, ...],
) -> dict[str, Any]:
    path.parent.mkdir(parents=True, exist_ok=True)
    seen = _dedupe_existing_ids(path)
    written = 0
    duplicates = 0
    with path.open("a", encoding="utf-8") as handle:
        for row in rows:
            row_id = str(row.get("id") or "")
            if row_id and row_id in seen:
                duplicates += 1
                continue
            stamped = _stamp_payload(row, source_paths=source_paths)
            if verify is not None and not verify(stamped):
                raise ValueError(f"invalid provenance envelope for {row_id}")
            handle.write(json.dumps(stamped, sort_keys=True, separators=(",", ":")) + "\n")
            if row_id:
                seen.add(row_id)
            written += 1
    sidecar = None
    if path.exists() and write_envelope_sidecar is not None:
        sidecar = write_envelope_sidecar(
            path,
            generator=GENERATOR,
            source_paths=source_paths,
            ttl_seconds=7 * 86_400,
            metadata={"rows_written": written, "duplicates": duplicates, "version": VERSION},
        )
    return {
        "path": str(path),
        "written": written,
        "duplicates": duplicates,
        "envelope_path": str(sidecar) if sidecar else None,
    }


async def pull_sources(
    sources: Sequence[BaseMacroSource],
    *,
    since: datetime,
) -> tuple[list[MacroEvent], list[dict[str, Any]]]:
    events: list[MacroEvent] = []
    errors: list[dict[str, Any]] = []
    for source in sources:
        try:
            events.extend(await source.pull(since))
        except SourceError as exc:
            errors.append(
                {"source": source.name, "error": str(exc), "type": exc.__class__.__name__}
            )
        except Exception as exc:  # noqa: BLE001 - one official source must not kill the lane.
            log.warning("macro source %s failed: %s", source.name, exc)
            errors.append(
                {"source": source.name, "error": str(exc), "type": exc.__class__.__name__}
            )
    events.sort(key=lambda item: item.published_at, reverse=True)
    return events[:MAX_EVENTS_PER_PULL], errors


def _publish_events(
    event_rows: Sequence[dict[str, Any]],
    calendar_rows: Sequence[dict[str, Any]],
    *,
    requested: bool,
) -> dict[str, Any]:
    bus_env = os.environ.get("SAPPHIRE_MACRO_INTEL_LIVE_BUS", "").strip() == "1"
    if not requested or not bus_env:
        return {"requested": requested, "actual": False, "published": 0}
    try:
        from lib.core.event_bus import get_bus

        bus = get_bus(source="macro-intel")
    except Exception as exc:  # noqa: BLE001
        return {"requested": requested, "actual": False, "published": 0, "error": str(exc)}
    published = 0
    for row in event_rows:
        bus.publish("macro.event.detected", row, source="macro-intel")
        published += 1
    for row in calendar_rows:
        bus.publish("macro.calendar.window_opening", row, source="macro-intel")
        published += 1
    return {"requested": requested, "actual": True, "published": published}


def _calendar_window_rows(calendar: MacroCalendar, *, now: datetime) -> list[dict[str, Any]]:
    return [event.to_dict() for event in calendar.in_next_hours(24, now=now)]


def _live_allowed(*, live: bool) -> bool:
    return bool(live) or os.environ.get("SAPPHIRE_MACRO_INTEL_LIVE", "").strip() == "1"


def _pull_fred_rows(
    *,
    loader: FredLoader,
    series_ids: Sequence[str],
    now: datetime,
    observation_start: str | None = None,
    realtime_start: str | None = None,
    realtime_end: str | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    rows: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    for series_id in series_ids:
        try:
            snapshot = loader.pull_series(
                series_id,
                observation_start=observation_start,
                realtime_start=realtime_start,
                realtime_end=realtime_end,
            )
            rows.extend(fred_observation_rows(snapshot, ingested_at=now))
        except FredLoaderError as exc:
            errors.append({"source": "fred_alfred", "series_id": series_id, "error": str(exc)})
        except Exception as exc:  # noqa: BLE001 - one series must not kill the lane.
            errors.append(
                {
                    "source": "fred_alfred",
                    "series_id": series_id,
                    "error": str(exc),
                    "type": exc.__class__.__name__,
                }
            )
    return rows, errors


async def run_once_async(
    *,
    since_hours: float = 24.0,
    sources: Sequence[BaseMacroSource] | None = None,
    output_root: str | Path = DEFAULT_OUTPUT_ROOT,
    cache_dir: str | Path | None = None,
    now: datetime | None = None,
    live: bool = False,
    publish: bool = False,
    include_static_calendar: bool = True,
    include_fred: bool = False,
    fred_series_ids: Sequence[str] = DEFAULT_MARKET_REGIME_SERIES,
    fred_loader: FredLoader | None = None,
    fred_observation_start: str | None = None,
    fred_realtime_start: str | None = None,
    fred_realtime_end: str | None = None,
) -> dict[str, Any]:
    now = (now or _now_utc()).astimezone(UTC)
    output_root = Path(output_root)
    cache_dir = Path(cache_dir).expanduser() if cache_dir else cache_base_dir()
    live_ok = _live_allowed(live=live)
    using_injected_sources = sources is not None
    metadata = {
        "generator": GENERATOR,
        "version": VERSION,
        "dry_run": not live_ok and not using_injected_sources,
        "live_http_allowed": live_ok,
        "publish_requested": publish,
        "caps": {
            "max_pulls_per_hour_per_source": MAX_PULLS_PER_HOUR_PER_SOURCE,
            "max_events_per_pull": MAX_EVENTS_PER_PULL,
            "max_forward_calendar_days": MAX_FORWARD_CALENDAR_DAYS,
        },
        "cache_dir": str(cache_dir),
        "fred_cache_dir": str(fred_cache_dir()),
        "output_root": str(output_root),
    }
    if not live_ok and sources is None and not include_fred:
        calendar = build_calendar((), now=now, include_static=include_static_calendar)
        calendar_rows = _calendar_window_rows(calendar, now=now)
        return {
            "ok": True,
            "dry_run": True,
            "reason": "set SAPPHIRE_MACRO_INTEL_LIVE=1 or pass --live to fetch official sources",
            "events": [],
            "calendar_window": calendar_rows,
            "metadata": metadata,
            "published": _publish_events([], [], requested=False),
        }

    fred_write: dict[str, Any] | None = None
    fred_errors: list[dict[str, Any]] = []
    if include_fred:
        fred_rows, fred_errors = _pull_fred_rows(
            loader=fred_loader or FredLoader(),
            series_ids=fred_series_ids,
            now=now,
            observation_start=fred_observation_start,
            realtime_start=fred_realtime_start,
            realtime_end=fred_realtime_end,
        )
        fred_write = _write_jsonl(
            _fred_observations_path(output_root, now),
            fred_rows,
            source_paths=(Path(__file__), REPO_ROOT / "lib" / "macro" / "fred_loader.py"),
        )
        if not live_ok and sources is None:
            calendar = build_calendar((), now=now, include_static=include_static_calendar)
            calendar_rows = _calendar_window_rows(calendar, now=now)
            return {
                "ok": not fred_errors,
                "dry_run": True,
                "reason": "FRED cache-only/live-gated run; set SAPPHIRE_MACRO_INTEL_LIVE=1 or --live for event sources",
                "events": [],
                "calendar_window": calendar_rows,
                "errors": fred_errors,
                "writes": {"fred_observations": fred_write},
                "metadata": metadata,
                "published": _publish_events([], [], requested=False),
            }

    since = now - timedelta(hours=max(1.0, float(since_hours)))
    source_list = list(sources or build_default_sources(cache_dir=cache_dir))
    events, errors = await pull_sources(source_list, since=since)
    event_rows = [enrich_event(event) for event in events]
    calendar = build_calendar(events, now=now, include_static=include_static_calendar)
    calendar_rows = calendar.to_dicts()
    window_rows = _calendar_window_rows(calendar, now=now)

    event_write = _write_jsonl(
        _events_path(output_root, now),
        event_rows,
        source_paths=(Path(__file__), REPO_ROOT / "lib" / "macro" / "sources.py"),
    )
    calendar_write = _write_jsonl(
        _calendar_path(output_root, now),
        calendar_rows,
        source_paths=(Path(__file__), REPO_ROOT / "lib" / "macro" / "calendar.py"),
    )
    published = _publish_events(event_rows, window_rows, requested=publish)
    writes: dict[str, Any] = {"events": event_write, "calendar": calendar_write}
    if fred_write is not None:
        writes["fred_observations"] = fred_write
    return {
        "ok": not errors and not fred_errors,
        "dry_run": False,
        "pulled_sources": [source.name for source in source_list],
        "events": event_rows,
        "errors": errors + fred_errors,
        "calendar_window": window_rows,
        "writes": writes,
        "published": published,
        "metadata": metadata,
    }


def run_once(**kwargs: Any) -> dict[str, Any]:
    return asyncio.run(run_once_async(**kwargs))


def fred_daily_export(
    *,
    output_root: str | Path = DEFAULT_OUTPUT_ROOT,
    now: datetime | None = None,
    live: bool = False,
    fred_series_ids: Sequence[str] = DEFAULT_MARKET_REGIME_SERIES,
    fred_loader: FredLoader | None = None,
    fred_observation_start: str | None = None,
    fred_realtime_start: str | None = None,
    fred_realtime_end: str | None = None,
) -> dict[str, Any]:
    """Write the bounded daily FRED observation export artifact."""

    result = run_once(
        output_root=output_root,
        now=now,
        live=live,
        publish=False,
        include_static_calendar=False,
        include_fred=True,
        fred_series_ids=fred_series_ids,
        fred_loader=fred_loader,
        fred_observation_start=fred_observation_start,
        fred_realtime_start=fred_realtime_start,
        fred_realtime_end=fred_realtime_end,
    )
    errors = list(result.get("errors") or [])
    cache_miss_only = bool(errors) and all(
        isinstance(error, dict)
        and str(error.get("error") or "").startswith("FRED cache miss and live reads are disabled")
        for error in errors
    )
    if not live and cache_miss_only:
        result["ok"] = True
        result["empty_cache_only"] = True
        result["reason"] = "FRED cache is empty and live reads are disabled; no live pull attempted"
    return result


def daemon(
    *,
    poll_interval_seconds: float = DEFAULT_POLL_INTERVAL_SECONDS,
    max_iterations: int | None = None,
    live: bool = False,
    publish: bool = False,
    include_fred: bool = False,
    fred_series_ids: Sequence[str] = DEFAULT_MARKET_REGIME_SERIES,
    sleep: Any = time.sleep,
) -> dict[str, Any]:
    iterations = 0
    last: dict[str, Any] | None = None
    while True:
        last = run_once(
            live=live,
            publish=publish,
            include_fred=include_fred,
            fred_series_ids=fred_series_ids,
        )
        iterations += 1
        if max_iterations is not None and iterations >= max_iterations:
            break
        sleep(max(1.0, float(poll_interval_seconds)))
    return {"iterations": iterations, "last": last}


def status(*, output_root: str | Path = DEFAULT_OUTPUT_ROOT) -> dict[str, Any]:
    output_root = Path(output_root)
    today_events = _events_path(output_root)
    today_calendar = _calendar_path(output_root)
    today_fred = _fred_observations_path(output_root)
    cache_dir = cache_base_dir()
    source_counters: dict[str, Any] = {}
    if cache_dir.exists():
        for counters in cache_dir.glob("*/counters.json"):
            try:
                source_counters[counters.parent.name] = json.loads(
                    counters.read_text(encoding="utf-8")
                )
            except (OSError, json.JSONDecodeError):
                source_counters[counters.parent.name] = {"error": "unreadable"}
    return {
        "ok": True,
        "service": "macro_intel",
        "version": VERSION,
        "live_http_env": os.environ.get("SAPPHIRE_MACRO_INTEL_LIVE") == "1",
        "live_bus_env": os.environ.get("SAPPHIRE_MACRO_INTEL_LIVE_BUS") == "1",
        "fred_live_env": os.environ.get("SAPPHIRE_FRED_LIVE") == "1",
        "cache_dir": str(cache_dir),
        "fred_cache_dir": str(fred_cache_dir()),
        "today_events": len(_read_jsonl(today_events, limit=10_000)),
        "today_calendar": len(_read_jsonl(today_calendar, limit=10_000)),
        "today_fred_observations": len(_read_jsonl(today_fred, limit=10_000)),
        "source_counters": source_counters,
        "caps": {
            "max_pulls_per_hour_per_source": MAX_PULLS_PER_HOUR_PER_SOURCE,
            "max_events_per_pull": MAX_EVENTS_PER_PULL,
            "max_forward_calendar_days": MAX_FORWARD_CALENDAR_DAYS,
        },
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    run_once_p = sub.add_parser("run-once", help="single macro-intel tick")
    run_once_p.add_argument("--since-hours", type=float, default=24.0)
    run_once_p.add_argument("--live", action="store_true", help="allow official HTTP pulls")
    run_once_p.add_argument(
        "--publish", action="store_true", help="publish to event bus if env gate is set"
    )
    run_once_p.add_argument(
        "--fred",
        action="store_true",
        help="write cache-first FRED/ALFRED observation rows",
    )
    run_once_p.add_argument(
        "--fred-series",
        action="append",
        help="FRED series id to include; repeatable. Defaults to market-regime set.",
    )

    daemon_p = sub.add_parser("daemon", help="continuous poll loop")
    daemon_p.add_argument(
        "--poll-interval-seconds", type=float, default=DEFAULT_POLL_INTERVAL_SECONDS
    )
    daemon_p.add_argument("--max-iterations", type=int, default=None)
    daemon_p.add_argument("--live", action="store_true", help="allow official HTTP pulls")
    daemon_p.add_argument(
        "--publish", action="store_true", help="publish to event bus if env gate is set"
    )
    daemon_p.add_argument(
        "--fred",
        action="store_true",
        help="write cache-first FRED/ALFRED observation rows",
    )
    daemon_p.add_argument(
        "--fred-series",
        action="append",
        help="FRED series id to include; repeatable. Defaults to market-regime set.",
    )

    fred_p = sub.add_parser(
        "fred-daily-export",
        help="write daily bounded FRED observation rows without macro event pulls",
    )
    fred_p.add_argument("--live", action="store_true", help="allow live FRED cache misses")
    fred_p.add_argument(
        "--fred-series",
        action="append",
        help="FRED series id to include; repeatable. Defaults to market-regime set.",
    )
    fred_p.add_argument(
        "--observation-start",
        help="optional FRED observation_start date for bounded backfill windows",
    )
    fred_p.add_argument(
        "--realtime-start",
        help="optional ALFRED realtime_start date for vintage windows",
    )
    fred_p.add_argument(
        "--realtime-end",
        help="optional ALFRED realtime_end date for vintage windows",
    )
    fred_p.add_argument(
        "--output-root",
        default=str(DEFAULT_OUTPUT_ROOT),
        help="macro output root; defaults to repo data/macro",
    )

    sub.add_parser("status", help="report counters and local artifacts")
    return parser


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    args = build_parser().parse_args(argv)
    if args.action == "run-once":
        result = run_once(
            since_hours=args.since_hours,
            live=args.live,
            publish=args.publish,
            include_fred=args.fred,
            fred_series_ids=tuple(args.fred_series or DEFAULT_MARKET_REGIME_SERIES),
        )
    elif args.action == "daemon":
        result = daemon(
            poll_interval_seconds=args.poll_interval_seconds,
            max_iterations=args.max_iterations,
            live=args.live,
            publish=args.publish,
            include_fred=args.fred,
            fred_series_ids=tuple(args.fred_series or DEFAULT_MARKET_REGIME_SERIES),
        )
    elif args.action == "fred-daily-export":
        result = fred_daily_export(
            output_root=args.output_root,
            live=args.live,
            fred_series_ids=tuple(args.fred_series or DEFAULT_MARKET_REGIME_SERIES),
            fred_observation_start=args.observation_start,
            fred_realtime_start=args.realtime_start,
            fred_realtime_end=args.realtime_end,
        )
    elif args.action == "status":
        result = status()
    else:  # pragma: no cover - argparse enforces choices.
        result = {"ok": False, "error": f"unknown action {args.action}"}
    json.dump(result, sys.stdout, indent=2, sort_keys=True, default=str)
    sys.stdout.write("\n")
    return 0 if result.get("ok", True) else 1


if __name__ == "__main__":
    raise SystemExit(main())
