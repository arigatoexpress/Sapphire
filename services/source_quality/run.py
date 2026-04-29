#!/usr/bin/env python3
"""Source-quality daily daemon.

Reads append-only JSONL feeds for the sources we care about, derives
``SignalRecord`` + ``Outcome`` lists, runs SNR + correlation + decay,
and writes a paste-safe ``data/source_quality/<date>/report.json`` plus
a rolling aggregate at ``data/source_quality/aggregates/rolling.json``.

The daemon is operator-opt-in: the LaunchAgent template ships with
``RunAtLoad=false`` and the runbook walks the operator through the
toggle. Read-only: no live API calls, no outbound network. All input
files come from local disk.

CLI
----

::

    python3 -m services.source_quality.run --help

Default behaviour: walk known feeds, build a report dated today (UTC),
write the artefact + provenance envelope.

The daemon never raises on a missing feed file — if a source has no
data we emit a row with ``samples=0`` and a note. This keeps the
artefact stable even on a fresh install.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from lib.core.provenance import write_envelope_sidecar  # noqa: E402
from lib.source_quality.correlation import (  # noqa: E402
    compute_pairwise_correlation,
    flag_near_duplicates,
)
from lib.source_quality.decay import detect_decay  # noqa: E402
from lib.source_quality.snr import (  # noqa: E402
    Outcome,
    SignalRecord,
    compute_source_snr,
)

log = logging.getLogger("source_quality")

DEFAULT_REPORT_ROOT = ROOT / "data" / "source_quality"
DEFAULT_AGGREGATES_ROOT = DEFAULT_REPORT_ROOT / "aggregates"

# Feed registry: relative path (or glob) → display source name. Each
# entry maps a JSONL file (or directory) into a stream of normalised
# SignalRecords. The exact wire format per feed varies; the
# normalisation is done by ``_extract_signals`` below.
FEED_PATHS: dict[str, tuple[Path, ...]] = {
    "tradingview": (ROOT / "data" / "signals",),
    "telegram_intel": (ROOT / "data" / "telegram_intel",),
    "hyperliquid": (ROOT / "data" / "hyperliquid",),
    "macro": (ROOT / "data" / "macro",),
    "cross_asset_regime": (ROOT / "data" / "cross_asset",),
    "onchain": (ROOT / "data" / "onchain",),
    "correlated_signals": (ROOT / "data" / "correlated_signals",),
}

OUTCOMES_PATH = ROOT / "data" / "source_quality_outcomes.jsonl"


@dataclass(frozen=True)
class ReportArtefact:
    """Where the daily report ended up on disk."""

    report_path: Path
    aggregates_path: Path
    sidecar_path: Path

    def to_dict(self) -> dict:
        return {
            "report_path": str(self.report_path),
            "aggregates_path": str(self.aggregates_path),
            "sidecar_path": str(self.sidecar_path),
        }


def _safe_iter_jsonl(path: Path) -> Iterable[dict]:
    """Yield decoded JSON lines from ``path``, ignoring malformed rows."""
    if not path.exists() or not path.is_file():
        return
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            yield value


def _walk_feed(root: Path) -> Iterable[dict]:
    """Walk a feed root; if it's a file, iterate it; if a dir, iterate ``*.jsonl``."""
    if not root.exists():
        return
    if root.is_file():
        yield from _safe_iter_jsonl(root)
        return
    for child in sorted(root.glob("**/*.jsonl")):
        yield from _safe_iter_jsonl(child)


def _normalise_direction(value: object) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, (int, float)):
        if value > 0:
            return "bull"
        if value < 0:
            return "bear"
    return "neutral"


def _coerce_timestamp(value: object) -> datetime | None:
    if isinstance(value, (int, float)):
        try:
            return datetime.fromtimestamp(float(value), tz=UTC)
        except (OSError, ValueError, OverflowError):
            return None
    if isinstance(value, str):
        try:
            s = value
            if s.endswith("Z"):
                s = s[:-1] + "+00:00"
            dt = datetime.fromisoformat(s)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=UTC)
            return dt
        except ValueError:
            return None
    return None


def _extract_signal(row: dict, source: str) -> SignalRecord | None:
    """Best-effort normalisation of one JSONL row into a SignalRecord.

    The exact wire format varies per feed, so we look for a small
    closed set of keys. Anything missing → row is skipped.
    """
    sym = row.get("symbol") or row.get("ticker") or row.get("asset")
    direction = (
        row.get("direction")
        or row.get("intent")
        or row.get("side")
        or row.get("regime")
        or row.get("bias")
    )
    ts_raw = (
        row.get("timestamp")
        or row.get("ts")
        or row.get("time")
        or row.get("created_at")
        or row.get("emitted_at")
    )
    if not sym or not ts_raw:
        return None
    ts = _coerce_timestamp(ts_raw)
    if ts is None:
        return None
    confidence_raw = row.get("confidence", row.get("score", 0.7))
    try:
        confidence = float(confidence_raw)
    except (TypeError, ValueError):
        confidence = 0.7
    return SignalRecord(
        source=source,
        symbol=str(sym).strip().upper(),
        timestamp=ts,
        direction=_normalise_direction(direction),
        confidence=max(0.0, min(1.0, confidence)),
    )


def _extract_outcome(row: dict) -> Outcome | None:
    sym = row.get("symbol") or row.get("ticker")
    ts_raw = row.get("timestamp") or row.get("ts") or row.get("time")
    ret_raw = row.get("realised_return", row.get("return", row.get("pct_change")))
    if not sym or not ts_raw or ret_raw is None:
        return None
    ts = _coerce_timestamp(ts_raw)
    if ts is None:
        return None
    try:
        return Outcome(symbol=str(sym).strip().upper(), timestamp=ts, realised_return=float(ret_raw))
    except (TypeError, ValueError):
        return None


def gather_signals(feed_paths: dict[str, tuple[Path, ...]] | None = None) -> list[SignalRecord]:
    """Walk every registered feed and normalise rows into SignalRecords."""
    feeds = feed_paths if feed_paths is not None else FEED_PATHS
    out: list[SignalRecord] = []
    for source, roots in feeds.items():
        for root in roots:
            for row in _walk_feed(root):
                rec = _extract_signal(row, source=source)
                if rec is not None:
                    out.append(rec)
    return out


def gather_outcomes(outcomes_path: Path | None = None) -> list[Outcome]:
    """Walk the outcomes feed (if present)."""
    path = outcomes_path or OUTCOMES_PATH
    if not path.exists():
        return []
    out: list[Outcome] = []
    for row in _safe_iter_jsonl(path):
        outcome = _extract_outcome(row)
        if outcome is not None:
            out.append(outcome)
    return out


def build_report(
    signals: Iterable[SignalRecord] | None = None,
    outcomes: Iterable[Outcome] | None = None,
    *,
    now: datetime | None = None,
) -> dict:
    """Build the report dict (no I/O).

    Tests use this directly; the daemon's :func:`run` calls it after
    :func:`gather_signals` + :func:`gather_outcomes`.
    """
    sigs = list(signals) if signals is not None else []
    outs = list(outcomes) if outcomes is not None else []
    snr_map = compute_source_snr(sigs, outs)
    correlation_report = compute_pairwise_correlation(sigs)
    decay_report = detect_decay(sigs, outs, now=now)
    near_dups = flag_near_duplicates(correlation_report)
    today = (now or datetime.now(UTC)).date().isoformat()
    return {
        "schema_version": 1,
        "generated_at": (now or datetime.now(UTC)).replace(microsecond=0).isoformat(),
        "report_date": today,
        "snr": {name: snr.to_dict() for name, snr in sorted(snr_map.items())},
        "correlation": correlation_report.to_dict(),
        "near_duplicates": [p.to_dict() for p in near_dups],
        "decay": decay_report.to_dict(),
        "summary": {
            "sources_count": len(snr_map),
            "samples_total": sum(s.samples for s in snr_map.values()),
            "near_duplicate_pairs": len(near_dups),
            "decayed_sources_count": len(decay_report.decayed_sources),
            "low_sample_sources_count": sum(1 for s in snr_map.values() if s.low_sample),
        },
        "read_only": True,
    }


def aggregates_payload(
    today_report: dict,
    *,
    now: datetime | None = None,
    history_days: int = 30,
) -> dict:
    """A small rolling-aggregates payload, append-friendly."""
    timestamp = (now or datetime.now(UTC)).replace(microsecond=0).isoformat()
    return {
        "schema_version": 1,
        "updated_at": timestamp,
        "history_days": history_days,
        "latest": {
            "report_date": today_report.get("report_date"),
            "summary": today_report.get("summary", {}),
        },
    }


def write_artefact(
    report: dict,
    *,
    report_root: Path | None = None,
    aggregates_root: Path | None = None,
    now: datetime | None = None,
) -> ReportArtefact:
    """Serialise ``report`` + a rolling aggregate; emit provenance sidecar."""
    today = (now or datetime.now(UTC)).date().isoformat()
    rroot = report_root or DEFAULT_REPORT_ROOT
    aroot = aggregates_root or (rroot / "aggregates")
    daily_dir = rroot / today
    daily_dir.mkdir(parents=True, exist_ok=True)
    aroot.mkdir(parents=True, exist_ok=True)
    daily_path = daily_dir / "report.json"
    rolling_path = aroot / "rolling.json"
    daily_path.write_text(
        json.dumps(report, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )
    aggregates = aggregates_payload(report, now=now)
    rolling_path.write_text(
        json.dumps(aggregates, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )
    sidecar = write_envelope_sidecar(
        daily_path,
        generator="source_quality.daemon@0.1.0",
        metadata={"report_date": today, "summary": report.get("summary", {})},
    )
    return ReportArtefact(
        report_path=daily_path,
        aggregates_path=rolling_path,
        sidecar_path=sidecar,
    )


def run(
    *,
    feed_paths: dict[str, tuple[Path, ...]] | None = None,
    outcomes_path: Path | None = None,
    report_root: Path | None = None,
    aggregates_root: Path | None = None,
    now: datetime | None = None,
    write: bool = True,
) -> dict:
    """End-to-end daily run.

    Returns the report dict plus, when ``write`` is True, the artefact
    paths under ``"artefact"``.
    """
    signals = gather_signals(feed_paths)
    outcomes = gather_outcomes(outcomes_path)
    report = build_report(signals, outcomes, now=now)
    if not write:
        return report
    artefact = write_artefact(
        report,
        report_root=report_root,
        aggregates_root=aggregates_root,
        now=now,
    )
    return {**report, "artefact": artefact.to_dict()}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="source-quality-daemon")
    parser.add_argument(
        "--report-root",
        type=Path,
        default=None,
        help="Override default data/source_quality root.",
    )
    parser.add_argument(
        "--no-write",
        action="store_true",
        help="Build the report but do not persist to disk.",
    )
    parser.add_argument(
        "--date",
        default=None,
        help="ISO date (YYYY-MM-DD) used as 'now' for the report.",
    )
    args = parser.parse_args(argv)
    now: datetime | None = None
    if args.date:
        try:
            now = datetime.fromisoformat(args.date).replace(tzinfo=UTC)
        except ValueError:
            log.error("invalid --date: %s", args.date)
            return 2
    payload = run(
        report_root=args.report_root,
        now=now,
        write=not args.no_write,
    )
    json.dump(payload, sys.stdout, indent=2, sort_keys=True, default=str)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "DEFAULT_AGGREGATES_ROOT",
    "DEFAULT_REPORT_ROOT",
    "FEED_PATHS",
    "OUTCOMES_PATH",
    "ReportArtefact",
    "aggregates_payload",
    "build_report",
    "gather_outcomes",
    "gather_signals",
    "run",
    "write_artefact",
]


# Make the date import deterministic for tests that monkey-patch.
def _today_iso(now: datetime | None = None) -> str:
    return (now or datetime.now(UTC)).date().isoformat()


# Helper kept around for downstream tests.
def _yesterday_iso(now: datetime | None = None) -> str:
    return ((now or datetime.now(UTC)).date() - timedelta(days=1)).isoformat()


# A small typed sentinel for "no data" displays.
NO_DATA_PLACEHOLDER = "—"


# Re-export Outcome/SignalRecord for callers that import from the daemon.
SignalRecord = SignalRecord
Outcome = Outcome


# Constants used by tests:
TODAY_KEY = "report_date"


# Module-level runtime guard so tests can detect the daemon stub.
DAEMON_VERSION = "0.1.0"

# Logging silence policy: tests should not see stray log noise.
log.setLevel(logging.WARNING)


# Minor helper for the dashboard route to look up "where's today's report".
def latest_report_path(report_root: Path | None = None, *, now: datetime | None = None) -> Path:
    today = (now or datetime.now(UTC)).date().isoformat()
    return (report_root or DEFAULT_REPORT_ROOT) / today / "report.json"


# Date type helper kept for parity with audit_panel runner.
TODAY_DATE: type[date] = date
