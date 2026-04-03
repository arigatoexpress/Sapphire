"""
Unit tests — PositionReconciler.

Critical paths:
  - handle_position_update() stores snapshot per platform
  - run_check(): no drift when all platforms are fresh
  - run_check(): staleness alert when last update is old with open positions
  - run_check(): no staleness alert when no positions are open (0 positions = flat)
  - run_check(): Firestore vs in-memory count mismatch detected
  - run_check(): Firestore has positions but no Pub/Sub snapshot → alert
  - run_check(): Firestore unavailable → Pub/Sub staleness still works
  - status() returns correct counts and ages
"""
import asyncio
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../services/shared"))

from position_reconciler import PositionReconciler

# ── Helpers ───────────────────────────────────────────────────────────────────

def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def _make(db=None, stale_threshold=120, interval=900) -> PositionReconciler:
    return PositionReconciler(
        firestore_client=db,
        stale_threshold_seconds=stale_threshold,
        reconcile_interval=interval,
    )


class _MockDoc:
    """Async Firestore document mock that streams a list of fake docs."""

    def __init__(self, records: list):
        self._records = records

    def stream(self):
        return _AsyncIter(self._records)


class _AsyncIter:
    def __init__(self, items):
        self._items = iter(items)

    def __aiter__(self):
        return self

    async def __anext__(self):
        try:
            return next(self._items)
        except StopIteration:
            raise StopAsyncIteration


class _FakeDocSnapshot:
    def __init__(self, id_, data):
        self.id = id_
        self._data = data

    def to_dict(self):
        return self._data.copy()


class _FakeDb:
    def __init__(self, docs: list):
        self._docs = docs

    def collection(self, name):
        return _MockDoc(self._docs)


# ── Pub/Sub snapshot updates ──────────────────────────────────────────────────

class TestHandlePositionUpdate:
    def test_stores_snapshot_for_platform(self):
        rec = _make()
        rec.handle_position_update({"platform": "lighter", "positions": [{"a": 1}, {"b": 2}]})
        assert "lighter" in rec._snapshots
        assert rec._snapshots["lighter"]["count"] == 2

    def test_missing_platform_ignored(self):
        rec = _make()
        rec.handle_position_update({"positions": [{"a": 1}]})
        assert len(rec._snapshots) == 0

    def test_empty_platform_string_ignored(self):
        rec = _make()
        rec.handle_position_update({"platform": "  ", "positions": []})
        assert len(rec._snapshots) == 0

    def test_overwrites_previous_snapshot(self):
        rec = _make()
        rec.handle_position_update({"platform": "aster", "positions": [1, 2, 3]})
        rec.handle_position_update({"platform": "aster", "positions": [1]})
        assert rec._snapshots["aster"]["count"] == 1


# ── Staleness check (Pub/Sub) ─────────────────────────────────────────────────

class TestStalenessCheck:
    def test_no_drift_when_fresh_with_positions(self):
        rec = _make(stale_threshold=60)
        rec.handle_position_update({"platform": "lighter", "positions": [{"sym": "BTC"}]})
        # received_at is just now — should be fresh
        drifts = _run(rec.run_check())
        assert drifts == []

    def test_stale_alert_when_old_update_with_open_positions(self):
        rec = _make(stale_threshold=60)
        rec.handle_position_update({"platform": "lighter", "positions": [{"sym": "BTC"}]})
        # Backdate by 3 minutes
        rec._snapshots["lighter"]["received_at"] = time.monotonic() - 200
        drifts = _run(rec.run_check())
        assert len(drifts) == 1
        assert "lighter" in drifts[0]
        assert "stale" in drifts[0].lower()

    def test_no_stale_alert_when_flat(self):
        """Zero open positions → no stale alert even if updates are old."""
        rec = _make(stale_threshold=60)
        rec.handle_position_update({"platform": "lighter", "positions": []})
        rec._snapshots["lighter"]["received_at"] = time.monotonic() - 300
        drifts = _run(rec.run_check())
        assert drifts == []

    def test_multiple_platforms_checked_independently(self):
        rec = _make(stale_threshold=60)
        rec.handle_position_update({"platform": "lighter", "positions": [{"x": 1}]})
        rec.handle_position_update({"platform": "aster", "positions": [{"y": 1}]})
        # Only backdate "lighter"
        rec._snapshots["lighter"]["received_at"] = time.monotonic() - 200
        drifts = _run(rec.run_check())
        assert len(drifts) == 1
        assert "lighter" in drifts[0]


# ── Firestore diff ────────────────────────────────────────────────────────────

class TestFirestoreDiff:
    def test_no_drift_when_counts_match(self):
        doc = _FakeDocSnapshot("lighter", {"platform": "lighter", "position_count": 2})
        db = _FakeDb([doc])
        rec = _make(db=db)
        rec.handle_position_update({"platform": "lighter", "positions": [1, 2]})
        drifts = _run(rec.run_check())
        assert drifts == []

    def test_drift_detected_when_counts_differ(self):
        doc = _FakeDocSnapshot("lighter", {"platform": "lighter", "position_count": 3})
        db = _FakeDb([doc])
        rec = _make(db=db)
        rec.handle_position_update({"platform": "lighter", "positions": [1]})  # only 1
        drifts = _run(rec.run_check())
        assert any("drift" in d.lower() or "mismatch" in d.lower() for d in drifts)
        assert any("lighter" in d for d in drifts)

    def test_firestore_has_positions_but_no_pubsub_snapshot(self):
        doc = _FakeDocSnapshot("lighter", {"platform": "lighter", "position_count": 2})
        db = _FakeDb([doc])
        rec = _make(db=db)
        # No Pub/Sub snapshot registered
        drifts = _run(rec.run_check())
        assert len(drifts) >= 1
        assert any("lighter" in d for d in drifts)

    def test_firestore_zero_positions_no_pubsub_snapshot_no_alert(self):
        """Firestore says 0 positions and no Pub/Sub snapshot → nothing to alert."""
        doc = _FakeDocSnapshot("lighter", {"platform": "lighter", "position_count": 0})
        db = _FakeDb([doc])
        rec = _make(db=db)
        drifts = _run(rec.run_check())
        assert drifts == []

    def test_firestore_error_does_not_crash_and_staleness_still_works(self):
        class BrokenDb:
            def collection(self, name):
                raise IOError("Firestore unavailable")

        rec = _make(db=BrokenDb(), stale_threshold=60)
        rec.handle_position_update({"platform": "lighter", "positions": [1]})
        rec._snapshots["lighter"]["received_at"] = time.monotonic() - 200
        # Should still detect staleness even though Firestore is broken
        drifts = _run(rec.run_check())
        assert any("stale" in d.lower() for d in drifts)

    def test_no_firestore_client_skips_diff(self):
        rec = _make(db=None)
        rec.handle_position_update({"platform": "lighter", "positions": [1]})
        drifts = _run(rec.run_check())
        # Fresh snapshot → no staleness; no Firestore → no diff → empty
        assert drifts == []


# ── Status introspection ──────────────────────────────────────────────────────

class TestReconcilerStatus:
    def test_status_reports_known_platforms(self):
        rec = _make()
        rec.handle_position_update({"platform": "lighter", "positions": [1, 2]})
        s = rec.status()
        assert "lighter" in s["platforms"]
        assert s["platforms"]["lighter"]["position_count"] == 2

    def test_status_age_is_non_negative(self):
        rec = _make()
        rec.handle_position_update({"platform": "aster", "positions": []})
        s = rec.status()
        assert s["platforms"]["aster"]["seconds_since_update"] >= 0

    def test_status_empty_when_no_updates(self):
        rec = _make()
        s = rec.status()
        assert s["platforms"] == {}
