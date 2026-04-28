#!/usr/bin/env python3
"""Sapphire Signal Correlator daemon.

Polls configured signal sources on disk, fuses them through
:mod:`lib.correlator.engine`, and emits a unified ``signal.correlated``
payload to:

- ``data/correlated_signals/<YYYY-MM-DD>/signals.jsonl`` (append-only)
- a sibling ``signals.jsonl.envelope.json`` provenance envelope
- the Sapphire event bus, on topic ``signal.correlated``

Read-only signal consumer: never writes back to source streams.

Subcommands
-----------

- ``run-once`` — single tick, prints JSON, exits 0. Useful for tests
  and ad-hoc operator runs.
- ``daemon`` — long-running poll loop. Honors ``--rate-limit-per-hour``
  to satisfy the ``MAX_CORRELATIONS_PER_HOUR = 1200`` cap.
- ``status`` — report most recent emission + counters under the
  ``~/.cache/sapphire/correlator/`` cache.

Environment
-----------

- ``SAPPHIRE_CORRELATOR_LIVE_BUS=1`` — actually publish to the event bus.
  Without this flag, events are formatted but not published (the JSONL
  is still written). Default is *off* so unit tests and CI don't try to
  connect to Redis.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from lib.correlator import (  # noqa: E402
    MAX_CORRELATIONS_PER_HOUR,
    CorrelatedSignal,
    CorrelatorConfig,
    build_default_sources,
    correlate_universe,
    load_weights,
)
from lib.correlator.engine import UniversePair  # noqa: E402

log = logging.getLogger(__name__)

DEFAULT_OUTPUT_ROOT = REPO_ROOT / "data" / "correlated_signals"
DEFAULT_CACHE_DIR = Path.home() / ".cache" / "sapphire" / "correlator"
DEFAULT_UNIVERSE: tuple[tuple[str, str], ...] = (
    ("BTC", "1h"),
    ("BTC", "4h"),
    ("ETH", "1h"),
    ("ETH", "4h"),
    ("SOL", "1h"),
    ("SOL", "4h"),
    ("SPY", "1d"),
    ("TSLA", "1d"),
)
GENERATOR = "services.correlator.run"
VERSION = "0.1.0"


# ---------------------------------------------------------------------------
# Output helpers
# ---------------------------------------------------------------------------


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _output_path(root: Path, *, now: datetime | None = None) -> Path:
    today = (now or _utc_now()).strftime("%Y-%m-%d")
    return root / today / "signals.jsonl"


def _envelope_path(jsonl_path: Path) -> Path:
    return jsonl_path.with_name(jsonl_path.name + ".envelope.json")


def _serialize(signal: CorrelatedSignal) -> dict[str, Any]:
    return signal.to_dict()


def _write_jsonl(
    signals: Sequence[CorrelatedSignal],
    *,
    output_root: Path = DEFAULT_OUTPUT_ROOT,
    now: datetime | None = None,
) -> tuple[Path, Path]:
    """Append signals + (re)stamp envelope. Returns (jsonl, envelope) paths."""
    path = _output_path(output_root, now=now)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        for sig in signals:
            fh.write(json.dumps(_serialize(sig), default=str, sort_keys=True) + "\n")

    envelope_path = _envelope_path(path)
    from datetime import timedelta

    written_at = now or _utc_now()
    envelope = {
        "generator": GENERATOR,
        "version": VERSION,
        "schema_version": 1,
        "wrote_at": written_at.isoformat(),
        "artifact": str(path.name),
        "signals_appended": len(signals),
        "ttl_seconds": 7 * 86_400,
        "expires_at": (written_at + timedelta(seconds=7 * 86_400)).isoformat(),
    }
    envelope_path.write_text(json.dumps(envelope, indent=2, sort_keys=True), encoding="utf-8")
    return path, envelope_path


# ---------------------------------------------------------------------------
# Cache / counters
# ---------------------------------------------------------------------------


def _load_counters(cache_dir: Path) -> dict[str, Any]:
    counters_path = cache_dir / "counters.json"
    if not counters_path.exists():
        return {"emissions": [], "lifetime": 0}
    try:
        return json.loads(counters_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"emissions": [], "lifetime": 0}


def _save_counters(cache_dir: Path, counters: dict[str, Any]) -> None:
    cache_dir.mkdir(parents=True, exist_ok=True)
    (cache_dir / "counters.json").write_text(
        json.dumps(counters, indent=2, sort_keys=True), encoding="utf-8"
    )


def _prune_emissions(counters: dict[str, Any], *, now: float | None = None) -> dict[str, Any]:
    cutoff = (now or time.time()) - 3600
    counters["emissions"] = [t for t in counters.get("emissions", []) if t >= cutoff]
    return counters


def _check_rate(counters: dict[str, Any], *, max_per_hour: int) -> tuple[bool, str]:
    if len(counters.get("emissions", [])) >= max_per_hour:
        return False, f"rate_limit_exceeded: {max_per_hour}/hour"
    return True, "ok"


# ---------------------------------------------------------------------------
# Event publishing
# ---------------------------------------------------------------------------


def _publish_events(signals: Sequence[CorrelatedSignal]) -> int:
    """Best-effort publish to the Sapphire event bus.

    Skipped unless ``SAPPHIRE_CORRELATOR_LIVE_BUS=1`` is set. Returns
    the number of events successfully published.
    """
    if os.environ.get("SAPPHIRE_CORRELATOR_LIVE_BUS", "").strip() != "1":
        return 0
    try:
        from lib.core.event_bus import get_bus
    except ImportError:  # pragma: no cover - event_bus is shipped.
        log.warning("event_bus unavailable — skipping publish")
        return 0
    try:
        bus = get_bus(source="signal-correlator")
    except Exception as exc:  # noqa: BLE001 - never let pubsub take the daemon down.
        log.warning("event bus init failed (%s) — skipping publish", exc)
        return 0
    published = 0
    for sig in signals:
        try:
            bus.publish(
                "signal.correlated",
                _serialize(sig),
                source="signal-correlator",
            )
            published += 1
        except Exception as exc:  # noqa: BLE001
            log.warning("publish failed for %s (%s)", sig.symbol, exc)
    return published


# ---------------------------------------------------------------------------
# Tick
# ---------------------------------------------------------------------------


def run_once(
    *,
    universe: Sequence[tuple[str, str]] = DEFAULT_UNIVERSE,
    sources: Sequence[Any] | None = None,
    config: CorrelatorConfig | None = None,
    output_root: Path = DEFAULT_OUTPUT_ROOT,
    cache_dir: Path = DEFAULT_CACHE_DIR,
    rate_limit_per_hour: int = MAX_CORRELATIONS_PER_HOUR,
    now: datetime | None = None,
    publish: bool = True,
) -> dict[str, Any]:
    """Single correlation tick. Returns a status dict."""
    if config is None:
        config = CorrelatorConfig(weights=load_weights())
    if sources is None:
        sources = build_default_sources()

    counters = _prune_emissions(_load_counters(cache_dir))
    expected = len(universe)
    allowed, reason = _check_rate(counters, max_per_hour=rate_limit_per_hour)
    if not allowed:
        return {
            "ok": False,
            "reason": reason,
            "counters": counters,
        }

    pairs = [UniversePair(symbol=s, timeframe=t) for s, t in universe]
    signals = correlate_universe(pairs, sources=sources, config=config, now=now)
    jsonl_path, envelope_path = _write_jsonl(signals, output_root=output_root, now=now)
    published = _publish_events(signals) if publish else 0

    counters.setdefault("emissions", []).extend([time.time()] * len(signals))
    counters["lifetime"] = counters.get("lifetime", 0) + len(signals)
    _save_counters(cache_dir, counters)

    return {
        "ok": True,
        "expected": expected,
        "emitted": len(signals),
        "published": published,
        "jsonl_path": str(jsonl_path),
        "envelope_path": str(envelope_path),
        "rate_limit_state": {
            "emissions_last_hour": len(counters["emissions"]),
            "max_per_hour": rate_limit_per_hour,
        },
    }


def daemon(
    *,
    poll_interval_seconds: float = 60.0,
    universe: Sequence[tuple[str, str]] = DEFAULT_UNIVERSE,
    sources: Sequence[Any] | None = None,
    config: CorrelatorConfig | None = None,
    output_root: Path = DEFAULT_OUTPUT_ROOT,
    cache_dir: Path = DEFAULT_CACHE_DIR,
    max_iterations: int | None = None,
    sleep: Any = time.sleep,
) -> dict[str, Any]:
    """Long-running tick loop. ``max_iterations`` is for tests."""
    iterations = 0
    while True:
        run_once(
            universe=universe,
            sources=sources,
            config=config,
            output_root=output_root,
            cache_dir=cache_dir,
        )
        iterations += 1
        if max_iterations is not None and iterations >= max_iterations:
            break
        sleep(poll_interval_seconds)
    return {"iterations": iterations}


def status(*, cache_dir: Path = DEFAULT_CACHE_DIR) -> dict[str, Any]:
    counters = _prune_emissions(_load_counters(cache_dir))
    return {
        "cache_dir": str(cache_dir),
        "emissions_last_hour": len(counters.get("emissions", [])),
        "lifetime_emissions": counters.get("lifetime", 0),
        "max_per_hour": MAX_CORRELATIONS_PER_HOUR,
        "live_bus": os.environ.get("SAPPHIRE_CORRELATOR_LIVE_BUS") == "1",
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    sub.add_parser("run-once", help="single tick")
    daemon_p = sub.add_parser("daemon", help="continuous poll loop")
    daemon_p.add_argument("--poll-interval-seconds", type=float, default=60.0)
    daemon_p.add_argument(
        "--max-iterations", type=int, default=None,
        help="cap iterations (for testing)",
    )
    sub.add_parser("status", help="report counters")
    return parser


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    args = build_parser().parse_args(argv)
    if args.action == "run-once":
        result = run_once()
    elif args.action == "daemon":
        result = daemon(
            poll_interval_seconds=args.poll_interval_seconds,
            max_iterations=args.max_iterations,
        )
    elif args.action == "status":
        result = status()
    else:  # pragma: no cover - argparse enforces choices
        result = {"error": f"unknown action {args.action}"}
    json.dump(result, sys.stdout, indent=2, sort_keys=True, default=str)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
