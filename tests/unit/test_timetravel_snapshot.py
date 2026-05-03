"""Unit tests for ``lib.timetravel.snapshot``.

Coverage targets:

- correctness vs hand-computed expected snapshots,
- missing-data handling (empty scopes, unreadable files),
- UTC discipline (naive datetimes coerced to UTC),
- out-of-range request handling (before earliest, after latest),
- index idempotence (rebuild yields identical signature),
- index file fingerprints (sha256 + size + mtime present),
- timestamp resolution across the supported field set,
- per-scope filtering,
- snapshot envelope shape + provenance contents.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from lib.timetravel import snapshot as st_mod
from lib.timetravel.snapshot import (
    DEFAULT_SCOPE,
    SnapshotEntry,
    SystemSnapshot,
    build_index,
    index_status,
    load_index,
    take_snapshot,
)

# ---------------------------------------------------------------------------
# Test scaffolding
# ---------------------------------------------------------------------------


@pytest.fixture
def fake_repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Stand up a fake repo root with the six scope dirs and rebind module roots."""
    base = tmp_path / "repo"
    (base / "data" / "correlated_signals" / "2026-04-26").mkdir(parents=True)
    (base / "data" / "correlated_signals" / "2026-04-27").mkdir(parents=True)
    (base / "data" / "narratives" / "2026-04-26").mkdir(parents=True)
    (base / "data" / "cross_asset" / "2026-04-26").mkdir(parents=True)
    (base / "data" / "macro" / "2026-04-26").mkdir(parents=True)
    (base / "data" / "onchain" / "2026-04-26").mkdir(parents=True)
    (base / "data" / "events").mkdir(parents=True)

    # Rebind SCOPE_TO_ROOT and REPO_ROOT for the duration of the test.
    monkeypatch.setattr(st_mod, "REPO_ROOT", base)
    fake_map = {
        "correlated_signals": base / "data" / "correlated_signals",
        "narratives": base / "data" / "narratives",
        "cross_asset": base / "data" / "cross_asset",
        "macro": base / "data" / "macro",
        "onchain": base / "data" / "onchain",
        "events_bus": base / "data" / "events",
    }
    monkeypatch.setattr(st_mod, "SCOPE_TO_ROOT", fake_map)
    return base


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, sort_keys=True, default=str) + "\n")
    return path


def _row(symbol: str, ts: str, **extras: Any) -> dict[str, Any]:
    payload = {
        "symbol": symbol,
        "timeframe": "1h",
        "edge_score": 0.42,
        "consensus": "AGREE_BULL",
        "contributing": 3,
        "corroborated_by": ["tradingview", "telegram"],
        "divergent_sources": [],
        "bull_sources": ["tradingview", "telegram"],
        "bear_sources": [],
        "neutral_sources": [],
        "freshness_seconds": 60.0,
        "raw_score": 0.4,
        "agreement_multiplier": 1.05,
        "contradict_factor": 1.0,
        "total_weight": 0.8,
        "generated_at": ts,
    }
    payload.update(extras)
    return payload


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_build_index_empty_repo_yields_zero_rows(fake_repo: Path, tmp_path: Path) -> None:
    cache = tmp_path / "index.json"
    body = build_index(scopes=DEFAULT_SCOPE, cache_path=cache)
    assert body["totals"]["files"] == 0
    assert body["totals"]["rows"] == 0
    assert cache.exists()
    body2 = build_index(scopes=DEFAULT_SCOPE, cache_path=cache)
    # Idempotent — signature stable for an unchanged tree.
    assert body2["signature"] == body["signature"]


def test_build_index_picks_up_jsonl_files(fake_repo: Path, tmp_path: Path) -> None:
    path = fake_repo / "data" / "correlated_signals" / "2026-04-26" / "signals.jsonl"
    _write_jsonl(
        path,
        [
            _row("BTC", "2026-04-26T10:00:00+00:00"),
            _row("BTC", "2026-04-26T11:00:00+00:00", edge_score=0.55),
            _row("ETH", "2026-04-26T12:00:00+00:00"),
        ],
    )
    cache = tmp_path / "index.json"
    body = build_index(scopes=DEFAULT_SCOPE, cache_path=cache)
    assert body["totals"]["files"] == 1
    assert body["totals"]["rows"] == 3
    cs_entries = body["scopes"]["correlated_signals"]
    assert len(cs_entries) == 1
    entry = cs_entries[0]
    assert entry["first_ts"] == "2026-04-26T10:00:00+00:00"
    assert entry["last_ts"] == "2026-04-26T12:00:00+00:00"
    assert entry["sha256"] and len(entry["sha256"]) == 64


def test_build_index_idempotent_no_rewrite_when_signature_unchanged(
    fake_repo: Path, tmp_path: Path
) -> None:
    path = fake_repo / "data" / "narratives" / "2026-04-26" / "theses.jsonl"
    _write_jsonl(
        path,
        [
            {
                "symbol": "BTC",
                "timeframe": "1h",
                "thesis": {"symbol": "BTC", "timeframe": "1h"},
                "generated_at": "2026-04-26T10:00:00+00:00",
            }
        ],
    )
    cache = tmp_path / "index.json"
    first = build_index(scopes=DEFAULT_SCOPE, cache_path=cache)
    initial_mtime = cache.stat().st_mtime
    second = build_index(scopes=DEFAULT_SCOPE, cache_path=cache)
    assert first["signature"] == second["signature"]
    # Body unchanged → file shouldn't have been rewritten.
    assert cache.stat().st_mtime == initial_mtime


def test_load_index_builds_on_first_call(fake_repo: Path, tmp_path: Path) -> None:
    cache = tmp_path / "index.json"
    assert not cache.exists()
    body = load_index(cache_path=cache, scopes=DEFAULT_SCOPE)
    assert cache.exists()
    assert body["schema_version"] == 1


def test_take_snapshot_returns_empty_for_empty_repo(fake_repo: Path, tmp_path: Path) -> None:
    cache = tmp_path / "index.json"
    snap = take_snapshot(
        datetime(2026, 4, 26, 12, 0, tzinfo=UTC),
        cache_path=cache,
    )
    assert isinstance(snap, SystemSnapshot)
    assert snap.at == "2026-04-26T12:00:00+00:00"
    for sc in DEFAULT_SCOPE:
        assert snap.by_scope(sc).empty


def test_take_snapshot_includes_only_pre_at_rows(fake_repo: Path, tmp_path: Path) -> None:
    path = fake_repo / "data" / "correlated_signals" / "2026-04-26" / "signals.jsonl"
    _write_jsonl(
        path,
        [
            _row("BTC", "2026-04-26T09:00:00+00:00"),
            _row("BTC", "2026-04-26T10:00:00+00:00"),
            _row("BTC", "2026-04-26T11:00:00+00:00"),
            _row("BTC", "2026-04-26T12:00:00+00:00"),
        ],
    )
    cache = tmp_path / "index.json"
    snap = take_snapshot(datetime(2026, 4, 26, 10, 30, tzinfo=UTC), cache_path=cache)
    rows = snap.by_scope("correlated_signals").rows
    # Should include 09:00 + 10:00 only.
    assert len(rows) == 2
    timestamps = [r["generated_at"] for r in rows]
    assert "2026-04-26T11:00:00+00:00" not in timestamps


def test_take_snapshot_naive_datetime_is_treated_as_utc(fake_repo: Path, tmp_path: Path) -> None:
    path = fake_repo / "data" / "correlated_signals" / "2026-04-26" / "signals.jsonl"
    _write_jsonl(path, [_row("BTC", "2026-04-26T10:00:00+00:00")])
    cache = tmp_path / "index.json"
    naive = datetime(2026, 4, 26, 10, 0, 0)  # no tzinfo
    snap = take_snapshot(naive, cache_path=cache)
    assert snap.at.endswith("+00:00")
    assert snap.by_scope("correlated_signals").rows == (
        {
            **_row("BTC", "2026-04-26T10:00:00+00:00"),
        },
    )


def test_take_snapshot_filters_files_with_first_ts_after_at(
    fake_repo: Path, tmp_path: Path
) -> None:
    early = fake_repo / "data" / "correlated_signals" / "2026-04-26" / "signals.jsonl"
    late = fake_repo / "data" / "correlated_signals" / "2026-04-27" / "signals.jsonl"
    _write_jsonl(early, [_row("BTC", "2026-04-26T10:00:00+00:00")])
    _write_jsonl(late, [_row("BTC", "2026-04-27T10:00:00+00:00")])
    cache = tmp_path / "index.json"
    snap = take_snapshot(datetime(2026, 4, 26, 23, 0, tzinfo=UTC), cache_path=cache)
    files = snap.by_scope("correlated_signals").files_visited
    assert any("2026-04-26" in f for f in files)
    assert all("2026-04-27" not in f for f in files)


def test_take_snapshot_out_of_range_before_earliest_is_empty(
    fake_repo: Path, tmp_path: Path
) -> None:
    path = fake_repo / "data" / "correlated_signals" / "2026-04-26" / "signals.jsonl"
    _write_jsonl(path, [_row("BTC", "2026-04-26T10:00:00+00:00")])
    cache = tmp_path / "index.json"
    snap = take_snapshot(datetime(2025, 12, 31, tzinfo=UTC), cache_path=cache)
    entry = snap.by_scope("correlated_signals")
    assert entry.empty
    # Empty entry must still be a valid SnapshotEntry.
    assert isinstance(entry, SnapshotEntry)


def test_take_snapshot_provenance_envelope_has_warning(fake_repo: Path, tmp_path: Path) -> None:
    cache = tmp_path / "index.json"
    snap = take_snapshot(datetime(2026, 4, 26, 10, 0, tzinfo=UTC), cache_path=cache)
    env = snap.provenance_envelope
    assert env["generator"] == "lib.timetravel.snapshot"
    assert env["version"] == "0.1.0"
    assert "warning" in env and "research" in env["warning"]
    assert env["scope"] == list(DEFAULT_SCOPE)


def test_take_snapshot_handles_unreadable_file(
    fake_repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = fake_repo / "data" / "correlated_signals" / "2026-04-26" / "signals.jsonl"
    _write_jsonl(path, [_row("BTC", "2026-04-26T10:00:00+00:00")])
    cache = tmp_path / "index.json"
    build_index(scopes=DEFAULT_SCOPE, cache_path=cache)
    # Now nuke the file but keep it in the index.
    path.unlink()
    snap = take_snapshot(datetime(2026, 4, 26, 12, 0, tzinfo=UTC), cache_path=cache)
    assert snap.by_scope("correlated_signals").empty


def test_take_snapshot_non_default_scope_only_visits_requested(
    fake_repo: Path, tmp_path: Path
) -> None:
    cs = fake_repo / "data" / "correlated_signals" / "2026-04-26" / "signals.jsonl"
    macro = fake_repo / "data" / "macro" / "2026-04-26" / "events.jsonl"
    _write_jsonl(cs, [_row("BTC", "2026-04-26T10:00:00+00:00")])
    _write_jsonl(
        macro,
        [{"id": "fomc", "title": "FOMC", "generated_at": "2026-04-26T09:30:00+00:00"}],
    )
    cache = tmp_path / "index.json"
    snap = take_snapshot(
        datetime(2026, 4, 26, 12, 0, tzinfo=UTC),
        scope=("correlated_signals",),
        cache_path=cache,
    )
    assert tuple(snap.scope) == ("correlated_signals",)
    assert "macro" not in snap.entries
    assert not snap.by_scope("correlated_signals").empty


def test_index_status_reports_missing_index(tmp_path: Path) -> None:
    cache = tmp_path / "missing.json"
    status = index_status(cache_path=cache)
    assert status["exists"] is False
    assert status["files"] == 0
    assert status["rows"] == 0
    assert status["signature"] is None


def test_index_status_reports_built_index(fake_repo: Path, tmp_path: Path) -> None:
    path = fake_repo / "data" / "correlated_signals" / "2026-04-26" / "signals.jsonl"
    _write_jsonl(path, [_row("BTC", "2026-04-26T10:00:00+00:00")])
    cache = tmp_path / "index.json"
    build_index(scopes=DEFAULT_SCOPE, cache_path=cache)
    status = index_status(cache_path=cache)
    assert status["exists"] is True
    assert status["files"] == 1
    assert status["rows"] == 1
    assert status["signature"] is not None


def test_event_bus_scope_uses_flat_jsonl(fake_repo: Path, tmp_path: Path) -> None:
    bus_path = fake_repo / "data" / "events" / "bus.jsonl"
    _write_jsonl(
        bus_path,
        [
            {
                "id": "evt-1",
                "topic": "signal.correlated",
                "ts": "2026-04-26T10:00:00+00:00",
                "payload": {"symbol": "BTC"},
            },
            {
                "id": "evt-2",
                "topic": "signal.correlated",
                "ts": "2026-04-26T11:00:00+00:00",
                "payload": {"symbol": "ETH"},
            },
        ],
    )
    cache = tmp_path / "index.json"
    snap = take_snapshot(
        datetime(2026, 4, 26, 10, 30, tzinfo=UTC),
        cache_path=cache,
    )
    rows = snap.by_scope("events_bus").rows
    assert len(rows) == 1
    assert rows[0]["id"] == "evt-1"


def test_row_timestamp_falls_through_to_payload_ts(fake_repo: Path, tmp_path: Path) -> None:
    bus_path = fake_repo / "data" / "events" / "bus.jsonl"
    # Row has no top-level timestamp_iso/generated_at, only payload.ts.
    bus_path.parent.mkdir(parents=True, exist_ok=True)
    bus_path.write_text(
        json.dumps(
            {
                "id": "evt-1",
                "payload": {"ts": "2026-04-26T10:00:00+00:00", "symbol": "BTC"},
            }
        )
        + "\n",
        encoding="utf-8",
    )
    cache = tmp_path / "index.json"
    snap = take_snapshot(datetime(2026, 4, 26, 11, 0, tzinfo=UTC), cache_path=cache)
    assert len(snap.by_scope("events_bus").rows) == 1


def test_snapshot_serializes_to_dict(fake_repo: Path, tmp_path: Path) -> None:
    cache = tmp_path / "index.json"
    snap = take_snapshot(datetime(2026, 4, 26, 12, 0, tzinfo=UTC), cache_path=cache)
    payload = snap.to_dict()
    assert payload["at"] == "2026-04-26T12:00:00+00:00"
    assert isinstance(payload["entries"], dict)
    assert isinstance(payload["provenance_envelope"], dict)


def test_rebuild_index_is_idempotent_signature(fake_repo: Path, tmp_path: Path) -> None:
    path = fake_repo / "data" / "correlated_signals" / "2026-04-26" / "signals.jsonl"
    _write_jsonl(path, [_row("BTC", "2026-04-26T10:00:00+00:00")])
    cache = tmp_path / "index.json"
    a = build_index(scopes=DEFAULT_SCOPE, cache_path=cache)
    b = build_index(scopes=DEFAULT_SCOPE, cache_path=cache)
    assert a["signature"] == b["signature"]
    # Append a new row → signature must change.
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(_row("ETH", "2026-04-26T11:00:00+00:00"), default=str) + "\n")
    c = build_index(scopes=DEFAULT_SCOPE, cache_path=cache)
    assert c["signature"] != a["signature"]


def test_index_skips_oversized_file(
    fake_repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(st_mod, "MAX_BYTES_PER_FILE", 32)
    path = fake_repo / "data" / "correlated_signals" / "2026-04-26" / "signals.jsonl"
    _write_jsonl(
        path,
        [
            _row("BTC", "2026-04-26T10:00:00+00:00"),
            _row("BTC", "2026-04-26T11:00:00+00:00"),
            _row("BTC", "2026-04-26T12:00:00+00:00"),
        ],
    )
    cache = tmp_path / "index.json"
    body = build_index(scopes=DEFAULT_SCOPE, cache_path=cache)
    # File is way over 32 bytes, so it should be skipped.
    assert body["totals"]["files"] == 0


def test_take_snapshot_within_seconds_window(fake_repo: Path, tmp_path: Path) -> None:
    base = datetime(2026, 4, 26, 10, 0, tzinfo=UTC)
    rows = [_row("BTC", (base + timedelta(seconds=i)).isoformat()) for i in range(10)]
    path = fake_repo / "data" / "correlated_signals" / "2026-04-26" / "signals.jsonl"
    _write_jsonl(path, rows)
    cache = tmp_path / "index.json"
    snap = take_snapshot(base + timedelta(seconds=4), cache_path=cache)
    assert len(snap.by_scope("correlated_signals").rows) == 5
