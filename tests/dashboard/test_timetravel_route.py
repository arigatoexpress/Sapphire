"""Dashboard ``/timetravel`` route + ``/api/timetravel-snapshot`` endpoint.

Read-only operator debug surface (Tranche 7-G). Uses the public API of
``lib.timetravel.snapshot.take_snapshot`` and matches its return shape via
``SystemSnapshot.to_dict()``.

Tests cover: auth gate, page render, happy-path snapshot, "no data" path
(timestamp before earliest indexed row), invalid-timestamp handling, and the
"compare to now" toggle. ``take_snapshot`` is monkeypatched so tests don't
depend on live ``data/`` artifacts.
"""

from __future__ import annotations

import base64
import importlib
import os
import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ["AUTH_PASSWORD"] = os.environ.get("AUTH_PASSWORD") or "test-password"
os.environ["X402_ENABLED"] = "0"

dashboard_app = importlib.import_module("services.dashboard.app")


def _auth_header() -> dict[str, str]:
    creds = base64.b64encode(
        f"{dashboard_app.AUTH_USERNAME}:{dashboard_app.AUTH_PASSWORD}".encode()
    ).decode("ascii")
    return {"Authorization": f"Basic {creds}"}


def _make_snapshot(at_iso: str, *, empty: bool = False, scope=None):
    """Build a ``SystemSnapshot``-shaped object via the real dataclass.

    Using the actual dataclass keeps the test honest about the public return
    shape rather than hand-rolling a duck-typed dict.
    """
    from lib.timetravel.snapshot import SnapshotEntry, SystemSnapshot

    scope_tuple = tuple(scope) if scope else ("correlated_signals", "narratives")
    entries: dict[str, SnapshotEntry] = {}
    for sc in scope_tuple:
        if empty:
            entries[sc] = SnapshotEntry(scope=sc)
        else:
            entries[sc] = SnapshotEntry(
                scope=sc,
                rows=(
                    {"id": f"{sc}-1", "ts": at_iso, "payload": {"k": "v"}},
                    {"id": f"{sc}-2", "ts": at_iso, "payload": {"k": "w"}},
                ),
                files_visited=(f"/data/{sc}/sample.jsonl",),
                earliest_ts=at_iso,
                latest_ts=at_iso,
            )
    return SystemSnapshot(
        at=at_iso,
        scope=scope_tuple,
        entries=entries,
        generated_at=at_iso,
        index_signature="testsig",
        provenance_envelope={
            "generator": "lib.timetravel.snapshot",
            "version": "0.1.0",
            "schema_version": 1,
            "at": at_iso,
            "scope": list(scope_tuple),
            "row_counts": {sc: len(entries[sc].rows) for sc in scope_tuple},
            "index_signature": "testsig",
            "warning": "test fixture",
        },
    )


@pytest.fixture
def client(monkeypatch):
    dashboard_app.app.config["TESTING"] = True

    # Default monkeypatch: take_snapshot returns a non-empty fixture snapshot.
    def _fake_take_snapshot(at, *, scope=None, **kwargs):
        # Coerce naive datetimes (the production helper does the same).
        if at.tzinfo is None:
            at = at.replace(tzinfo=UTC)
        return _make_snapshot(at.isoformat(), scope=scope)

    monkeypatch.setattr("lib.timetravel.snapshot.take_snapshot", _fake_take_snapshot)
    monkeypatch.setattr(
        "lib.timetravel.snapshot.index_status",
        lambda **_: {
            "exists": True,
            "files": 3,
            "rows": 42,
            "signature": "testsig",
            "built_at": "2026-04-30T00:00:00+00:00",
            "schema_version": 1,
        },
    )
    with dashboard_app.app.test_client() as test_client:
        yield test_client


# ---------------------------------------------------------------------------
# Page route
# ---------------------------------------------------------------------------


def test_timetravel_page_requires_auth(client) -> None:
    assert client.get("/timetravel").status_code == 401


def test_timetravel_page_renders(client) -> None:
    response = client.get("/timetravel", headers=_auth_header())
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "Time Travel" in html
    assert "/api/timetravel-snapshot" in html
    # Read-only warning must be visible.
    assert "Read-only" in html
    # Default scopes must be embedded for the JS to render the columns.
    assert "correlated_signals" in html


def test_nav_contains_timetravel_link(client) -> None:
    response = client.get("/timetravel", headers=_auth_header())
    assert 'href="/timetravel"' in response.get_data(as_text=True)


# ---------------------------------------------------------------------------
# API: happy path
# ---------------------------------------------------------------------------


def test_api_requires_auth(client) -> None:
    assert client.get("/api/timetravel-snapshot").status_code == 401


def test_api_happy_path_default_at(client) -> None:
    """No ``at`` query param → defaults to ``utcnow()`` and returns a snapshot."""
    response = client.get("/api/timetravel-snapshot", headers=_auth_header())
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["ok"] is True
    assert payload["compare_to_now"] is False
    primary = payload["primary"]
    assert primary["ok"] is True
    assert primary["no_data"] is False
    assert "snapshot" in primary
    entries = primary["snapshot"]["entries"]
    assert "correlated_signals" in entries
    assert entries["correlated_signals"]["row_count"] == 2


def test_api_happy_path_explicit_at(client) -> None:
    response = client.get(
        "/api/timetravel-snapshot?at=2026-04-30T12:00:00",
        headers=_auth_header(),
    )
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["ok"] is True
    primary = payload["primary"]
    # The snapshot ``at`` should be the (UTC-coerced) timestamp we sent.
    assert primary["snapshot"]["at"].startswith("2026-04-30T12:00:00")


def test_api_accepts_datetime_local_format(client) -> None:
    """HTML datetime-local inputs emit ``YYYY-MM-DDTHH:MM`` (no seconds)."""
    response = client.get(
        "/api/timetravel-snapshot?at=2026-04-30T12:00",
        headers=_auth_header(),
    )
    assert response.status_code == 200
    assert response.get_json()["ok"] is True


def test_api_accepts_z_suffix(client) -> None:
    response = client.get(
        "/api/timetravel-snapshot?at=2026-04-30T12:00:00Z",
        headers=_auth_header(),
    )
    assert response.status_code == 200
    assert response.get_json()["ok"] is True


# ---------------------------------------------------------------------------
# API: "no data" path (before earliest snapshot)
# ---------------------------------------------------------------------------


def test_api_no_data_path(client, monkeypatch) -> None:
    """Empty snapshot should set ``no_data: True`` on the primary payload."""

    def _empty_snapshot(at, *, scope=None, **kwargs):
        if at.tzinfo is None:
            at = at.replace(tzinfo=UTC)
        return _make_snapshot(at.isoformat(), empty=True, scope=scope)

    monkeypatch.setattr("lib.timetravel.snapshot.take_snapshot", _empty_snapshot)
    response = client.get(
        "/api/timetravel-snapshot?at=1990-01-01T00:00:00",
        headers=_auth_header(),
    )
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["ok"] is True
    assert payload["primary"]["no_data"] is True
    entries = payload["primary"]["snapshot"]["entries"]
    assert all(entry["empty"] is True for entry in entries.values())


# ---------------------------------------------------------------------------
# API: invalid timestamp
# ---------------------------------------------------------------------------


def test_api_invalid_timestamp_returns_400(client) -> None:
    response = client.get(
        "/api/timetravel-snapshot?at=not-a-real-timestamp",
        headers=_auth_header(),
    )
    assert response.status_code == 400
    payload = response.get_json()
    assert payload["ok"] is False
    assert "invalid" in payload["error"].lower()


def test_api_garbage_max_rows_falls_back_to_default(client) -> None:
    """Bad ``max_rows_per_scope`` shouldn't crash — we silently default."""
    response = client.get(
        "/api/timetravel-snapshot?max_rows_per_scope=banana",
        headers=_auth_header(),
    )
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["primary"]["row_cap"] == 200


# ---------------------------------------------------------------------------
# API: compare to now toggle
# ---------------------------------------------------------------------------


def test_api_compare_to_now(client) -> None:
    response = client.get(
        "/api/timetravel-snapshot?at=2026-04-30T12:00:00&compare_to_now=1",
        headers=_auth_header(),
    )
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["ok"] is True
    assert payload["compare_to_now"] is True
    assert "now" in payload
    assert payload["now"]["ok"] is True
    # Both columns should have the snapshot shape.
    assert "snapshot" in payload["primary"]
    assert "snapshot" in payload["now"]


def test_api_compare_to_now_off_omits_now_payload(client) -> None:
    response = client.get(
        "/api/timetravel-snapshot?at=2026-04-30T12:00:00",
        headers=_auth_header(),
    )
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["compare_to_now"] is False
    assert "now" not in payload


# ---------------------------------------------------------------------------
# API: scope filter
# ---------------------------------------------------------------------------


def test_api_scope_filter(client) -> None:
    response = client.get(
        "/api/timetravel-snapshot?at=2026-04-30T12:00:00&scope=correlated_signals",
        headers=_auth_header(),
    )
    assert response.status_code == 200
    payload = response.get_json()
    primary = payload["primary"]
    entries = primary["snapshot"]["entries"]
    assert list(entries.keys()) == ["correlated_signals"]


# ---------------------------------------------------------------------------
# API: row cap truncation
# ---------------------------------------------------------------------------


def test_api_row_cap_truncates_oversized_scope(client, monkeypatch) -> None:
    from lib.timetravel.snapshot import SnapshotEntry, SystemSnapshot

    def _fat_snapshot(at, *, scope=None, **kwargs):
        if at.tzinfo is None:
            at = at.replace(tzinfo=UTC)
        rows = tuple({"i": i, "ts": at.isoformat()} for i in range(500))
        entry = SnapshotEntry(
            scope="correlated_signals",
            rows=rows,
            files_visited=("/data/sample.jsonl",),
            earliest_ts=at.isoformat(),
            latest_ts=at.isoformat(),
        )
        return SystemSnapshot(
            at=at.isoformat(),
            scope=("correlated_signals",),
            entries={"correlated_signals": entry},
            generated_at=at.isoformat(),
            index_signature="testsig",
            provenance_envelope={"warning": "test"},
        )

    monkeypatch.setattr("lib.timetravel.snapshot.take_snapshot", _fat_snapshot)
    response = client.get(
        "/api/timetravel-snapshot?at=2026-04-30T12:00:00"
        "&scope=correlated_signals&max_rows_per_scope=50",
        headers=_auth_header(),
    )
    assert response.status_code == 200
    entry = response.get_json()["primary"]["snapshot"]["entries"]["correlated_signals"]
    assert entry.get("truncated") is True
    assert entry.get("truncated_to") == 50
    assert entry.get("original_row_count") == 500
    assert len(entry["rows"]) == 50


# ---------------------------------------------------------------------------
# Helper unit tests
# ---------------------------------------------------------------------------


def test_parse_at_helper_handles_utc_and_naive() -> None:
    parser = dashboard_app._timetravel_parse_at
    assert parser("2026-04-30T12:00:00+00:00") == datetime(2026, 4, 30, 12, 0, tzinfo=UTC)
    # Naive datetimes coerced to UTC.
    assert parser("2026-04-30T12:00:00") == datetime(2026, 4, 30, 12, 0, tzinfo=UTC)
    # Z suffix.
    assert parser("2026-04-30T12:00:00Z") == datetime(2026, 4, 30, 12, 0, tzinfo=UTC)
    # Garbage.
    assert parser("garbage") is None
    assert parser("") is None
    assert parser(None) is None
