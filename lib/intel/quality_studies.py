"""Offline quality studies for Sapphire intelligence artifacts.

The functions here are pure analyzers: they accept local JSON/JSONL-style
records, return serializable reports, and never call live market or Hyperliquid
APIs. They are intended for post-run quality studies, not execution paths.
"""

from __future__ import annotations

import math
from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Any

from lib.counterparty.tracker import TraderStats

REGIME_UNCERTAIN = "regime_uncertain"
REGIME_LABELS = (
    "risk_on_correlated",
    "risk_on_decorrelated",
    "risk_off_flight_to_dollar",
    "crisis_correlation_spike",
    REGIME_UNCERTAIN,
)


def _now_iso(now: datetime | None = None) -> str:
    return (now or datetime.now(UTC)).replace(microsecond=0).isoformat()


def _safe_float(value: Any, default: float = 0.0) -> float:
    if value is None or isinstance(value, bool):
        return default
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return number if math.isfinite(number) else default


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _round(value: float | None, digits: int = 4) -> float | None:
    if value is None:
        return None
    return round(float(value), digits)


def _timestamp_key(row: Mapping[str, Any], fallback: int) -> str:
    value = (
        row.get("timestamp")
        or row.get("generated_at")
        or row.get("observed_at")
        or row.get("date")
        or row.get("snapshot_id")
    )
    return str(value or f"snapshot-{fallback:04d}")


def _coerce_regime_row(row: Mapping[str, Any], index: int) -> dict[str, Any] | None:
    payload = row.get("regime") if isinstance(row.get("regime"), Mapping) else row
    label = str(payload.get("label") or payload.get("state") or payload.get("regime") or "").strip()
    if not label:
        return None
    return {
        "timestamp": _timestamp_key(payload, index),
        "label": label,
        "confidence": _clamp(_safe_float(payload.get("confidence"), 0.0), 0.0, 1.0),
        "drivers": list(payload.get("drivers") or []),
        "metrics": dict(payload.get("metrics") or {}),
    }


@dataclass(frozen=True)
class RegimeRun:
    """A consecutive run of the same regime label."""

    label: str
    start_index: int
    end_index: int
    length: int
    start_timestamp: str
    end_timestamp: str
    mean_confidence: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class RegimeStabilityReport:
    """Summary of cross-asset regime label stability."""

    generated_at: str
    observations: int
    label_counts: dict[str, int]
    transition_count: int
    transition_rate: float
    one_sample_flip_count: int
    one_sample_flip_rate: float
    uncertainty_rate: float
    mean_confidence: float
    persistence_score: float
    stability_score: float
    suggested_global_regime_weight: float
    verdict: str
    runs: list[RegimeRun]
    per_label_weights: dict[str, dict[str, float | int | str]]
    notes: list[str]

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["runs"] = [run.to_dict() for run in self.runs]
        return data


def analyze_regime_stability(
    records: Iterable[Mapping[str, Any]],
    *,
    generated_at: datetime | None = None,
) -> RegimeStabilityReport:
    """Analyze stability of cross-asset regime labels from local artifacts."""
    rows = [
        coerced
        for index, row in enumerate(records)
        if isinstance(row, Mapping) and (coerced := _coerce_regime_row(row, index)) is not None
    ]
    observations = len(rows)
    if observations == 0:
        return RegimeStabilityReport(
            generated_at=_now_iso(generated_at),
            observations=0,
            label_counts={},
            transition_count=0,
            transition_rate=0.0,
            one_sample_flip_count=0,
            one_sample_flip_rate=0.0,
            uncertainty_rate=0.0,
            mean_confidence=0.0,
            persistence_score=0.0,
            stability_score=0.0,
            suggested_global_regime_weight=0.25,
            verdict="insufficient_data",
            runs=[],
            per_label_weights={},
            notes=["no usable regime rows"],
        )

    labels = [str(row["label"]) for row in rows]
    confidences = [float(row["confidence"]) for row in rows]
    label_counts = dict(Counter(labels))
    transition_count = sum(1 for left, right in zip(labels, labels[1:], strict=False) if left != right)
    transition_rate = transition_count / max(1, observations - 1)
    runs = _regime_runs(rows)
    one_sample_flip_count = sum(1 for run in runs if run.length == 1 and run.label != REGIME_UNCERTAIN)
    one_sample_flip_rate = one_sample_flip_count / max(1, len(runs))
    uncertainty_rate = label_counts.get(REGIME_UNCERTAIN, 0) / observations
    mean_confidence = sum(confidences) / observations
    avg_run_length = observations / max(1, len(runs))
    persistence_score = _clamp(avg_run_length / 4.0, 0.0, 1.0)
    stability_score = _clamp(
        0.40 * mean_confidence
        + 0.30 * persistence_score
        + 0.20 * (1.0 - uncertainty_rate)
        + 0.10 * (1.0 - one_sample_flip_rate),
        0.0,
        1.0,
    )
    suggested_global_regime_weight = _clamp(0.25 + stability_score, 0.25, 1.20)
    per_label_weights = _per_label_weights(rows, runs, observations)
    notes = _regime_notes(
        transition_rate=transition_rate,
        uncertainty_rate=uncertainty_rate,
        one_sample_flip_rate=one_sample_flip_rate,
        stability_score=stability_score,
    )
    return RegimeStabilityReport(
        generated_at=_now_iso(generated_at),
        observations=observations,
        label_counts=label_counts,
        transition_count=transition_count,
        transition_rate=round(transition_rate, 4),
        one_sample_flip_count=one_sample_flip_count,
        one_sample_flip_rate=round(one_sample_flip_rate, 4),
        uncertainty_rate=round(uncertainty_rate, 4),
        mean_confidence=round(mean_confidence, 4),
        persistence_score=round(persistence_score, 4),
        stability_score=round(stability_score, 4),
        suggested_global_regime_weight=round(suggested_global_regime_weight, 4),
        verdict=_stability_verdict(stability_score),
        runs=runs,
        per_label_weights=per_label_weights,
        notes=notes,
    )


def _regime_runs(rows: Sequence[Mapping[str, Any]]) -> list[RegimeRun]:
    runs: list[RegimeRun] = []
    start = 0
    while start < len(rows):
        label = str(rows[start]["label"])
        end = start + 1
        while end < len(rows) and rows[end]["label"] == label:
            end += 1
        chunk = rows[start:end]
        mean_confidence = sum(float(row["confidence"]) for row in chunk) / len(chunk)
        runs.append(
            RegimeRun(
                label=label,
                start_index=start,
                end_index=end - 1,
                length=len(chunk),
                start_timestamp=str(chunk[0]["timestamp"]),
                end_timestamp=str(chunk[-1]["timestamp"]),
                mean_confidence=round(mean_confidence, 4),
            )
        )
        start = end
    return runs


def _per_label_weights(
    rows: Sequence[Mapping[str, Any]],
    runs: Sequence[RegimeRun],
    observations: int,
) -> dict[str, dict[str, float | int | str]]:
    by_label_conf: dict[str, list[float]] = defaultdict(list)
    by_label_run_lengths: dict[str, list[int]] = defaultdict(list)
    for row in rows:
        by_label_conf[str(row["label"])].append(float(row["confidence"]))
    for run in runs:
        by_label_run_lengths[run.label].append(run.length)

    out: dict[str, dict[str, float | int | str]] = {}
    for label in sorted(by_label_conf):
        confs = by_label_conf[label]
        run_lengths = by_label_run_lengths[label]
        sample_share = len(confs) / max(1, observations)
        mean_conf = sum(confs) / len(confs)
        mean_run = sum(run_lengths) / len(run_lengths)
        base = 0.35 + mean_conf * 0.55 + _clamp(mean_run / 4.0, 0.0, 1.0) * 0.25
        if label == REGIME_UNCERTAIN:
            base = min(base, 0.50)
        if sample_share < 0.15:
            base *= 0.85
        out[label] = {
            "samples": len(confs),
            "sample_share": round(sample_share, 4),
            "mean_confidence": round(mean_conf, 4),
            "mean_run_length": round(mean_run, 4),
            "suggested_weight": round(_clamp(base, 0.25, 1.20), 4),
            "interpretation": _label_interpretation(label),
        }
    return out


def _label_interpretation(label: str) -> str:
    if label == REGIME_UNCERTAIN:
        return "cap downstream confidence; use as a pause or review context"
    if label in REGIME_LABELS:
        return "eligible as a bounded context weight when corroborated"
    return "unknown label; review artifact schema before using as weight"


def _stability_verdict(score: float) -> str:
    if score >= 0.76:
        return "stable"
    if score >= 0.55:
        return "mixed"
    return "unstable"


def _regime_notes(
    *,
    transition_rate: float,
    uncertainty_rate: float,
    one_sample_flip_rate: float,
    stability_score: float,
) -> list[str]:
    notes: list[str] = []
    if transition_rate > 0.40:
        notes.append("high transition rate; avoid increasing regime weight without longer soak")
    if uncertainty_rate > 0.25:
        notes.append("uncertainty is material; cap or pause regime-dependent narratives")
    if one_sample_flip_rate > 0.25:
        notes.append("one-sample flicker is elevated; consider stronger smoothing")
    if stability_score >= 0.76:
        notes.append("regime labels are stable enough for bounded offline tuning experiments")
    elif not notes:
        notes.append("regime labels are usable for review, but not strong enough to upweight alone")
    return notes


@dataclass(frozen=True)
class SnapshotLeaderboard:
    """Normalized top-N leaderboard snapshot."""

    snapshot_id: str
    timestamp: str
    traders: list[dict[str, Any]]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class TraderStability:
    """Stability metrics for one public counterparty."""

    address: str
    display_name: str | None
    appearances: int
    appearance_rate: float
    average_rank: float
    rank_stdev: float
    best_rank: int
    worst_rank: int
    latest_rank: int
    latest_quality_score: float
    latest_realized_pnl_30d_usd: float
    stable_watchlist_candidate: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class CounterpartyLeaderboardStabilityReport:
    """Summary of public Hyperliquid counterparty leaderboard stability."""

    generated_at: str
    snapshots: int
    top_n: int
    unique_traders: int
    mean_adjacent_jaccard: float | None
    mean_rank_spearman: float | None
    mean_churn_rate: float | None
    leaderboard_stability_score: float
    verdict: str
    stable_watchlist: list[TraderStability]
    trader_stability: list[TraderStability]
    adjacent_windows: list[dict[str, Any]]
    notes: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            **asdict(self),
            "stable_watchlist": [item.to_dict() for item in self.stable_watchlist],
            "trader_stability": [item.to_dict() for item in self.trader_stability],
        }


def analyze_counterparty_leaderboard_stability(
    records: Iterable[Mapping[str, Any]],
    *,
    top_n: int = 20,
    min_appearance_rate: float = 0.67,
    max_rank_stdev: float = 3.0,
    generated_at: datetime | None = None,
) -> CounterpartyLeaderboardStabilityReport:
    """Analyze rank/constituent stability of local counterparty snapshots."""
    snapshots = normalize_leaderboard_snapshots(records, top_n=top_n)
    if len(snapshots) < 2:
        return CounterpartyLeaderboardStabilityReport(
            generated_at=_now_iso(generated_at),
            snapshots=len(snapshots),
            top_n=top_n,
            unique_traders=len({row["address"] for snap in snapshots for row in snap.traders}),
            mean_adjacent_jaccard=None,
            mean_rank_spearman=None,
            mean_churn_rate=None,
            leaderboard_stability_score=0.0,
            verdict="insufficient_data",
            stable_watchlist=[],
            trader_stability=[],
            adjacent_windows=[],
            notes=["need at least two leaderboard snapshots"],
        )

    adjacent = [_compare_snapshots(left, right) for left, right in zip(snapshots, snapshots[1:], strict=False)]
    mean_jaccard = _mean([float(row["jaccard"]) for row in adjacent])
    spearman_values = [float(row["rank_spearman"]) for row in adjacent if row["rank_spearman"] is not None]
    mean_spearman = _mean(spearman_values)
    mean_churn = _mean([float(row["churn_rate"]) for row in adjacent])
    trader_rows = _trader_stability(
        snapshots,
        min_appearance_rate=min_appearance_rate,
        max_rank_stdev=max_rank_stdev,
    )
    retention_score = len([row for row in trader_rows if row.stable_watchlist_candidate]) / max(1, len(trader_rows))
    spearman_score = ((mean_spearman + 1.0) / 2.0) if mean_spearman is not None else 0.0
    score = _clamp((mean_jaccard or 0.0) * 0.45 + spearman_score * 0.35 + retention_score * 0.20, 0.0, 1.0)
    stable_watchlist = [row for row in trader_rows if row.stable_watchlist_candidate]
    notes = _counterparty_notes(score=score, mean_churn=mean_churn, stable_watchlist=stable_watchlist)
    return CounterpartyLeaderboardStabilityReport(
        generated_at=_now_iso(generated_at),
        snapshots=len(snapshots),
        top_n=top_n,
        unique_traders=len(trader_rows),
        mean_adjacent_jaccard=_round(mean_jaccard),
        mean_rank_spearman=_round(mean_spearman),
        mean_churn_rate=_round(mean_churn),
        leaderboard_stability_score=round(score, 4),
        verdict=_stability_verdict(score),
        stable_watchlist=stable_watchlist,
        trader_stability=trader_rows,
        adjacent_windows=adjacent,
        notes=notes,
    )


def normalize_leaderboard_snapshots(
    records: Iterable[Mapping[str, Any]],
    *,
    top_n: int = 20,
) -> list[SnapshotLeaderboard]:
    """Normalize JSON/JSONL artifact records into ordered leaderboard snapshots."""
    grouped_rows: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    grouped_times: dict[str, str] = {}
    snapshots: list[SnapshotLeaderboard] = []

    for index, record in enumerate(records):
        if not isinstance(record, Mapping):
            continue
        leaderboard = _extract_leaderboard(record)
        if leaderboard is not None:
            snapshot_id = str(record.get("snapshot_id") or record.get("generated_at") or f"snapshot-{index:04d}")
            timestamp = str(record.get("generated_at") or record.get("timestamp") or snapshot_id)
            snapshots.append(
                SnapshotLeaderboard(
                    snapshot_id=snapshot_id,
                    timestamp=timestamp,
                    traders=_normalize_leaderboard_rows(leaderboard, top_n=top_n),
                )
            )
            continue

        address = record.get("address") or record.get("user") or record.get("account")
        if not address:
            continue
        snapshot_id = str(record.get("snapshot_id") or record.get("generated_at") or record.get("timestamp") or "default")
        grouped_rows[snapshot_id].append(record)
        grouped_times[snapshot_id] = str(record.get("generated_at") or record.get("timestamp") or snapshot_id)

    for snapshot_id in sorted(grouped_rows):
        snapshots.append(
            SnapshotLeaderboard(
                snapshot_id=snapshot_id,
                timestamp=grouped_times[snapshot_id],
                traders=_normalize_leaderboard_rows(grouped_rows[snapshot_id], top_n=top_n),
            )
        )
    return sorted(snapshots, key=lambda item: item.timestamp)


def _extract_leaderboard(record: Mapping[str, Any]) -> list[Any] | None:
    for key in ("leaderboard", "traders", "rankings"):
        value = record.get(key)
        if isinstance(value, list):
            return value
    snapshot = record.get("snapshot")
    if isinstance(snapshot, Mapping):
        return _extract_leaderboard(snapshot)
    return None


def _normalize_leaderboard_rows(rows: Sequence[Any], *, top_n: int) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for index, raw in enumerate(rows):
        if not isinstance(raw, Mapping):
            continue
        stats = TraderStats.from_dict(dict(raw))
        if not stats.address:
            continue
        rank = stats.rank if stats.rank is not None else index + 1
        normalized.append(
            {
                **stats.to_dict(),
                "rank": _safe_int(rank, index + 1),
                "quality_score": round(stats.quality_score(), 6),
            }
        )
    normalized.sort(key=lambda row: (_safe_int(row.get("rank"), 999999), -_safe_float(row.get("quality_score"))))
    return normalized[: max(1, int(top_n))]


def _compare_snapshots(left: SnapshotLeaderboard, right: SnapshotLeaderboard) -> dict[str, Any]:
    left_ranks = {row["address"]: int(row["rank"]) for row in left.traders}
    right_ranks = {row["address"]: int(row["rank"]) for row in right.traders}
    left_set = set(left_ranks)
    right_set = set(right_ranks)
    union = left_set | right_set
    common = sorted(left_set & right_set)
    jaccard = len(common) / len(union) if union else 0.0
    return {
        "left_snapshot": left.snapshot_id,
        "right_snapshot": right.snapshot_id,
        "left_timestamp": left.timestamp,
        "right_timestamp": right.timestamp,
        "overlap": len(common),
        "entered": sorted(right_set - left_set),
        "exited": sorted(left_set - right_set),
        "jaccard": round(jaccard, 4),
        "churn_rate": round(1.0 - jaccard, 4),
        "rank_spearman": _round(_spearman_for_common(left_ranks, right_ranks, common)),
    }


def _spearman_for_common(
    left_ranks: Mapping[str, int],
    right_ranks: Mapping[str, int],
    common: Sequence[str],
) -> float | None:
    if len(common) < 2:
        return None
    xs = [float(left_ranks[address]) for address in common]
    ys = [float(right_ranks[address]) for address in common]
    return _pearson(xs, ys)


def _pearson(xs: Sequence[float], ys: Sequence[float]) -> float | None:
    if len(xs) != len(ys) or len(xs) < 2:
        return None
    mean_x = sum(xs) / len(xs)
    mean_y = sum(ys) / len(ys)
    num = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys, strict=True))
    den_x = math.sqrt(sum((x - mean_x) ** 2 for x in xs))
    den_y = math.sqrt(sum((y - mean_y) ** 2 for y in ys))
    if den_x == 0.0 or den_y == 0.0:
        return None
    return _clamp(num / (den_x * den_y), -1.0, 1.0)


def _trader_stability(
    snapshots: Sequence[SnapshotLeaderboard],
    *,
    min_appearance_rate: float,
    max_rank_stdev: float,
) -> list[TraderStability]:
    seen: dict[str, list[dict[str, Any]]] = defaultdict(list)
    display: dict[str, str | None] = {}
    for snapshot_index, snapshot in enumerate(snapshots):
        for row in snapshot.traders:
            address = str(row["address"])
            seen[address].append({**row, "snapshot_index": snapshot_index})
            display[address] = row.get("display_name")
    total = len(snapshots)
    out: list[TraderStability] = []
    for address, rows in seen.items():
        ranks = [int(row["rank"]) for row in rows]
        latest = max(rows, key=lambda row: int(row["snapshot_index"]))
        avg = sum(ranks) / len(ranks)
        stdev = _stdev(ranks)
        appearance_rate = len(rows) / total
        candidate = appearance_rate >= min_appearance_rate and stdev <= max_rank_stdev
        out.append(
            TraderStability(
                address=address,
                display_name=display.get(address),
                appearances=len(rows),
                appearance_rate=round(appearance_rate, 4),
                average_rank=round(avg, 4),
                rank_stdev=round(stdev, 4),
                best_rank=min(ranks),
                worst_rank=max(ranks),
                latest_rank=int(latest["rank"]),
                latest_quality_score=round(_safe_float(latest.get("quality_score")), 6),
                latest_realized_pnl_30d_usd=round(_safe_float(latest.get("realized_pnl_30d_usd")), 2),
                stable_watchlist_candidate=candidate,
            )
        )
    return sorted(out, key=lambda row: (not row.stable_watchlist_candidate, row.average_rank, row.rank_stdev, row.address))


def _mean(values: Sequence[float]) -> float | None:
    return sum(values) / len(values) if values else None


def _stdev(values: Sequence[int | float]) -> float:
    if len(values) < 2:
        return 0.0
    mean = sum(float(value) for value in values) / len(values)
    return math.sqrt(sum((float(value) - mean) ** 2 for value in values) / len(values))


def _counterparty_notes(
    *,
    score: float,
    mean_churn: float | None,
    stable_watchlist: Sequence[TraderStability],
) -> list[str]:
    notes: list[str] = []
    if mean_churn is not None and mean_churn > 0.45:
        notes.append("leaderboard churn is high; use cohort aggregates instead of trader-level claims")
    if not stable_watchlist:
        notes.append("no stable watchlist candidates under current thresholds")
    if score >= 0.76:
        notes.append("leaderboard is stable enough for offline quality weighting experiments")
    elif not notes:
        notes.append("leaderboard is mixed; use as corroboration only")
    return notes


__all__ = [
    "CounterpartyLeaderboardStabilityReport",
    "RegimeStabilityReport",
    "SnapshotLeaderboard",
    "TraderStability",
    "analyze_counterparty_leaderboard_stability",
    "analyze_regime_stability",
    "normalize_leaderboard_snapshots",
]
