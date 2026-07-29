"""Pure aggregator: ``calls.jsonl`` → per-tier telemetry report.

Reads ``~/.cache/sapphire/inference_proxy/calls.jsonl`` if present, otherwise
falls back to a caller-supplied fixture path. Computes:

- Latency percentiles (p50, p95, p99, p999).
- Throughput (calls/min, calls/hour, total calls).
- Error rate (failures / total).
- Token consumption (in, out, total).
- Cost (USD, via ``cost_model.estimate_cost``).

Side-effect-free: the aggregator never writes anywhere. Recommender and
plugin tools are responsible for any persistence.
"""

from __future__ import annotations

import json
import math
from collections.abc import Iterable
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from . import KNOWN_TIERS, SCHEMA_VERSION, VERSION
from .cost_model import (
    DEFAULT_COST_MODEL,
    CostModel,
    estimate_cost_record,
)

DEFAULT_CALLS_PATH = Path.home() / ".cache" / "sapphire" / "inference_proxy" / "calls.jsonl"
MAX_LINES_PER_READ = 250_000  # hard cap so a runaway log file can't OOM


# ── Data shapes ─────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class CallRecord:
    """Normalized inference call record. All fields optional except ``tier``."""

    tier: str
    model: str | None = None
    ts: datetime | None = None
    latency_ms: float | None = None
    ok: bool = True
    tokens_in: int = 0
    tokens_out: int = 0
    error_class: str | None = None

    @property
    def tokens_total(self) -> int:
        return int(self.tokens_in) + int(self.tokens_out)


@dataclass
class TierStats:
    tier: str
    calls: int = 0
    success: int = 0
    failure: int = 0
    error_classes: dict[str, int] = field(default_factory=dict)
    tokens_in: int = 0
    tokens_out: int = 0
    cost_usd: float = 0.0
    latency_p50_ms: float | None = None
    latency_p95_ms: float | None = None
    latency_p99_ms: float | None = None
    latency_p999_ms: float | None = None
    latency_mean_ms: float | None = None
    latency_max_ms: float | None = None
    calls_per_minute: float | None = None
    calls_per_hour: float | None = None
    first_seen_ts: str | None = None
    last_seen_ts: str | None = None

    @property
    def error_rate(self) -> float:
        return (self.failure / self.calls) if self.calls else 0.0

    @property
    def tokens_total(self) -> int:
        return self.tokens_in + self.tokens_out

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["error_rate"] = round(self.error_rate, 6)
        d["tokens_total"] = self.tokens_total
        # Round monetary + latency values for paste-safe display.
        for key in (
            "latency_p50_ms",
            "latency_p95_ms",
            "latency_p99_ms",
            "latency_p999_ms",
            "latency_mean_ms",
            "latency_max_ms",
            "calls_per_minute",
            "calls_per_hour",
        ):
            v = d.get(key)
            if isinstance(v, int | float):
                d[key] = round(float(v), 3)
        d["cost_usd"] = round(self.cost_usd, 6)
        return d


@dataclass
class TelemetryReport:
    schema_version: int = SCHEMA_VERSION
    version: str = VERSION
    generator: str = "lib.inference_telemetry.aggregator"
    source_path: str | None = None
    calls_path_exists: bool = False
    has_real_data: bool = False
    total_calls: int = 0
    total_success: int = 0
    total_failure: int = 0
    total_tokens_in: int = 0
    total_tokens_out: int = 0
    total_cost_usd: float = 0.0
    window_start: str | None = None
    window_end: str | None = None
    window_seconds: float | None = None
    parsed_lines: int = 0
    skipped_lines: int = 0
    cost_model_name: str = "default"
    tiers: list[TierStats] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    @property
    def error_rate(self) -> float:
        return (self.total_failure / self.total_calls) if self.total_calls else 0.0

    @property
    def total_tokens(self) -> int:
        return self.total_tokens_in + self.total_tokens_out

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["tiers"] = [t.to_dict() for t in self.tiers]
        d["error_rate"] = round(self.error_rate, 6)
        d["total_tokens"] = self.total_tokens
        d["total_cost_usd"] = round(self.total_cost_usd, 6)
        return d


# ── Parsing ─────────────────────────────────────────────────────────────────


def _parse_timestamp(raw: Any) -> datetime | None:
    if raw is None:
        return None
    if isinstance(raw, datetime):
        return raw if raw.tzinfo else raw.replace(tzinfo=UTC)
    if isinstance(raw, int | float):
        try:
            return datetime.fromtimestamp(float(raw), tz=UTC)
        except (OSError, OverflowError, ValueError):
            return None
    if isinstance(raw, str):
        try:
            text = raw.replace("Z", "+00:00")
            dt = datetime.fromisoformat(text)
            return dt if dt.tzinfo else dt.replace(tzinfo=UTC)
        except ValueError:
            return None
    return None


def parse_record(obj: Any) -> CallRecord | None:
    """Parse a single JSON object → ``CallRecord``. Permissive: returns None on garbage."""
    if not isinstance(obj, dict):
        return None
    tier = obj.get("tier") or obj.get("endpoint") or obj.get("backend")
    if not isinstance(tier, str) or not tier:
        return None
    ok_raw = obj.get("ok", obj.get("success", True))
    ok = bool(ok_raw) if not isinstance(ok_raw, str) else ok_raw.lower() == "true"
    latency = obj.get("latency_ms", obj.get("elapsed_ms"))
    try:
        latency_val = float(latency) if latency is not None else None
    except (TypeError, ValueError):
        latency_val = None
    return CallRecord(
        tier=tier,
        model=obj.get("model"),
        ts=_parse_timestamp(obj.get("ts") or obj.get("timestamp")),
        latency_ms=latency_val,
        ok=ok,
        tokens_in=int(obj.get("tokens_in", obj.get("prompt_tokens", 0)) or 0),
        tokens_out=int(obj.get("tokens_out", obj.get("completion_tokens", 0)) or 0),
        error_class=str(obj.get("error_class")) if obj.get("error_class") else None,
    )


def iter_records(
    path: Path,
    *,
    max_lines: int = MAX_LINES_PER_READ,
) -> Iterable[CallRecord]:
    """Yield ``CallRecord`` from a JSONL file. Lines that fail to parse are skipped silently."""
    if not path.exists():
        return
    with path.open("r", encoding="utf-8", errors="replace") as fh:
        for i, line in enumerate(fh):
            if i >= max_lines:
                break
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            rec = parse_record(obj)
            if rec is not None:
                yield rec


# ── Percentiles ─────────────────────────────────────────────────────────────


def percentile(values: list[float], pct: float) -> float | None:
    """Linear-interpolation percentile. Returns None for empty list."""
    if not values:
        return None
    if pct <= 0:
        return float(min(values))
    if pct >= 100:
        return float(max(values))
    sorted_vals = sorted(values)
    rank = (pct / 100.0) * (len(sorted_vals) - 1)
    lower = math.floor(rank)
    upper = math.ceil(rank)
    if lower == upper:
        return float(sorted_vals[lower])
    frac = rank - lower
    return float(sorted_vals[lower] + frac * (sorted_vals[upper] - sorted_vals[lower]))


# ── Aggregation ─────────────────────────────────────────────────────────────


def _build_tier_stats(tier: str, records: list[CallRecord], cost_model: CostModel) -> TierStats:
    stats = TierStats(tier=tier)
    latencies: list[float] = []
    timestamps: list[datetime] = []
    for r in records:
        stats.calls += 1
        if r.ok:
            stats.success += 1
        else:
            stats.failure += 1
            if r.error_class:
                stats.error_classes[r.error_class] = stats.error_classes.get(r.error_class, 0) + 1
        stats.tokens_in += int(r.tokens_in or 0)
        stats.tokens_out += int(r.tokens_out or 0)
        if r.latency_ms is not None and r.latency_ms >= 0:
            latencies.append(float(r.latency_ms))
        if r.ts is not None:
            timestamps.append(r.ts)
        cost = estimate_cost_record(r, cost_model)
        stats.cost_usd += cost

    if latencies:
        stats.latency_p50_ms = percentile(latencies, 50)
        stats.latency_p95_ms = percentile(latencies, 95)
        stats.latency_p99_ms = percentile(latencies, 99)
        stats.latency_p999_ms = percentile(latencies, 99.9)
        stats.latency_mean_ms = sum(latencies) / len(latencies)
        stats.latency_max_ms = max(latencies)

    if timestamps:
        stats.first_seen_ts = min(timestamps).isoformat()
        stats.last_seen_ts = max(timestamps).isoformat()
        window = (max(timestamps) - min(timestamps)).total_seconds()
        if window > 0:
            stats.calls_per_minute = stats.calls / max(window / 60.0, 1e-6)
            stats.calls_per_hour = stats.calls / max(window / 3600.0, 1e-6)
        else:
            # All calls share a single timestamp — treat as 1-second window for sanity.
            stats.calls_per_minute = float(stats.calls) * 60.0
            stats.calls_per_hour = float(stats.calls) * 3600.0
    return stats


def aggregate(
    path: Path | str | None = None,
    *,
    cost_model: CostModel | None = None,
    fixture_records: Iterable[CallRecord] | None = None,
) -> TelemetryReport:
    """Read ``calls.jsonl`` (or a fixture iterable) and compute a ``TelemetryReport``.

    Args:
        path: location of the JSONL log; defaults to ``DEFAULT_CALLS_PATH``.
        cost_model: optional override; defaults to ``DEFAULT_COST_MODEL``.
        fixture_records: when supplied, used in place of file reading. Useful for
            tests and for the recommender's sensitivity analyses.
    """
    cost_model = cost_model or DEFAULT_COST_MODEL
    target = Path(path) if path is not None else DEFAULT_CALLS_PATH
    report = TelemetryReport(
        source_path=str(target),
        cost_model_name=cost_model.name,
    )

    if fixture_records is not None:
        records: list[CallRecord] = list(fixture_records)
        report.calls_path_exists = False
        report.has_real_data = False
        report.notes.append("aggregated from fixture iterable (no real disk read)")
    else:
        report.calls_path_exists = target.exists()
        records = []
        skipped = 0
        if report.calls_path_exists:
            with target.open("r", encoding="utf-8", errors="replace") as fh:
                for i, line in enumerate(fh):
                    if i >= MAX_LINES_PER_READ:
                        report.notes.append(f"truncated at MAX_LINES_PER_READ={MAX_LINES_PER_READ}")
                        break
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        obj = json.loads(line)
                    except json.JSONDecodeError:
                        skipped += 1
                        continue
                    rec = parse_record(obj)
                    if rec is None:
                        skipped += 1
                        continue
                    records.append(rec)
            report.parsed_lines = len(records)
            report.skipped_lines = skipped
            report.has_real_data = bool(records)
        else:
            report.notes.append(
                f"calls.jsonl missing at {target} — no real fixture data; report is empty"
            )

    by_tier: dict[str, list[CallRecord]] = {}
    for rec in records:
        by_tier.setdefault(rec.tier, []).append(rec)

    # Stable ordering: known tiers first in canonical order, then unknown tiers
    # sorted lexically (so reports are deterministic for tests + provenance).
    ordered_tiers: list[str] = [t for t in KNOWN_TIERS if t in by_tier]
    extra_tiers = sorted(t for t in by_tier if t not in KNOWN_TIERS)
    if extra_tiers:
        report.notes.append(f"unknown tiers in log: {','.join(extra_tiers)}")
    ordered_tiers.extend(extra_tiers)

    for tier in ordered_tiers:
        ts = _build_tier_stats(tier, by_tier[tier], cost_model)
        report.tiers.append(ts)
        report.total_calls += ts.calls
        report.total_success += ts.success
        report.total_failure += ts.failure
        report.total_tokens_in += ts.tokens_in
        report.total_tokens_out += ts.tokens_out
        report.total_cost_usd += ts.cost_usd

    if records:
        with_ts = [r.ts for r in records if r.ts is not None]
        if with_ts:
            report.window_start = min(with_ts).isoformat()
            report.window_end = max(with_ts).isoformat()
            report.window_seconds = (max(with_ts) - min(with_ts)).total_seconds()

    return report


# ── Convenience helpers ─────────────────────────────────────────────────────


def project_monthly_cost(report: TelemetryReport) -> float:
    """Project monthly cost (USD) from observed window. Returns 0 when no time window.

    Honest: this assumes the observed window is representative. The recommender
    surfaces this caveat to users, never silently extrapolates.
    """
    if not report.window_seconds or report.window_seconds <= 0 or report.total_cost_usd <= 0:
        return 0.0
    seconds_in_month = 30.0 * 24.0 * 3600.0
    return float(report.total_cost_usd) * (seconds_in_month / float(report.window_seconds))


def project_monthly_calls(report: TelemetryReport) -> float:
    if not report.window_seconds or report.window_seconds <= 0:
        return 0.0
    seconds_in_month = 30.0 * 24.0 * 3600.0
    return float(report.total_calls) * (seconds_in_month / float(report.window_seconds))


def synthetic_fixture_report(
    *, now: datetime | None = None, cost_model: CostModel | None = None
) -> TelemetryReport:
    """Deterministic synthetic-only fixture report — used when no real data exists.

    The report is clearly labelled in ``notes`` so callers (dashboard, plugin) can
    surface "no real fixture data — synthetic only" honestly.
    """
    now = now or datetime.now(UTC)
    base = now - timedelta(hours=1)
    fixtures: list[CallRecord] = []
    # T1: many fast GPU calls.
    for i in range(40):
        fixtures.append(
            CallRecord(
                tier="T1_windows_gpu",
                model="hermes3:8b",
                ts=base + timedelta(seconds=15 * i),
                latency_ms=380 + (i % 5) * 12.0,
                ok=True,
                tokens_in=300 + i,
                tokens_out=150 + (i % 7),
            )
        )
    # T3: a few slow Mac fallbacks.
    for i in range(6):
        fixtures.append(
            CallRecord(
                tier="T3_mac_local",
                model="hermes3:8b",
                ts=base + timedelta(seconds=600 + 90 * i),
                latency_ms=82_000 + i * 1_500.0,
                ok=True,
                tokens_in=320,
                tokens_out=210,
            )
        )
    # T4: a couple of Kimi calls (more expensive).
    for i in range(3):
        fixtures.append(
            CallRecord(
                tier="T4_kimi_cloud",
                model="kimi-cloud",
                ts=base + timedelta(seconds=2_400 + i * 240),
                latency_ms=2_400 + i * 200.0,
                ok=i != 2,
                tokens_in=1_800,
                tokens_out=900,
                error_class="HTTPError" if i == 2 else None,
            )
        )
    rep = aggregate(fixture_records=fixtures, cost_model=cost_model)
    rep.notes.append(
        "synthetic-only fixture: real ~/.cache/sapphire/inference_proxy/calls.jsonl absent"
    )
    rep.has_real_data = False
    return rep


__all__ = [
    "DEFAULT_CALLS_PATH",
    "MAX_LINES_PER_READ",
    "CallRecord",
    "TierStats",
    "TelemetryReport",
    "parse_record",
    "iter_records",
    "percentile",
    "aggregate",
    "project_monthly_cost",
    "project_monthly_calls",
    "synthetic_fixture_report",
]
