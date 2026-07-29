"""Alerts must route non-critical events into the digest, not out immediately.

The screenshot showed 5,893 unread messages — every low-priority CVE, mover,
and info event firing a full Telegram push. The fix: p1 alerts still send
now, but p2/p3 land in ``lib.telegram.digest_queue`` and only leave the
machine when the scheduled digest tick drains them.

These tests pin that routing so a future producer that dispatches at p2
"just to be safe" doesn't quietly regress the noise floor.
"""

from __future__ import annotations

import pytest

from lib.telegram import alerts, digest_queue


@pytest.fixture(autouse=True)
def _isolate_journals(tmp_path, monkeypatch):
    """Point every JSONL sink at tmp_path so tests never touch ~/.cache/.

    Every alert helper reads NOTIFY_TOOL + JOURNAL_PATH + DEFAULT_JOURNAL
    from module-level constants. We swap all three so no test crosses
    into another test's state and no test writes under $HOME.
    """
    monkeypatch.setattr(alerts, "JOURNAL_PATH", tmp_path / "alert_journal.jsonl")
    monkeypatch.setattr(digest_queue, "DEFAULT_JOURNAL", tmp_path / "digest.jsonl")
    monkeypatch.setattr(digest_queue, "ARCHIVE_DIR", tmp_path / "archive")
    # alerts.digest_queue.enqueue reads digest_queue.DEFAULT_JOURNAL at
    # call time, so patching the module attr is enough — no extra
    # per-test wiring needed.
    monkeypatch.setattr(alerts, "digest_queue", digest_queue)


@pytest.fixture
def stub_notify(monkeypatch, tmp_path):
    """Present a real notify.py path + capture subprocess.run invocations."""
    fake_notify = tmp_path / "notify.py"
    fake_notify.write_text("# stub\n")
    monkeypatch.setattr(alerts, "NOTIFY_TOOL", fake_notify)
    captured: dict = {"calls": []}

    def _spy(argv, **kwargs):
        captured["calls"].append(argv)

        class _Completed:
            returncode = 0

        return _Completed()

    monkeypatch.setattr(alerts.subprocess, "run", _spy)
    return captured


class TestNonCriticalAlertsBatch:
    """p2 and p3 must never touch notify.py — they belong in the queue."""

    def test_large_move_lands_in_digest(self, monkeypatch, tmp_path):
        # Explode if notify.py runs for a p2 alert.
        def _boom(*a, **kw):
            raise AssertionError("notify.py should not run for p2 alerts")

        monkeypatch.setattr(alerts.subprocess, "run", _boom)

        ok = alerts.alert_large_move(symbol="BTC", pct_change=6.4)
        assert ok is True

        entries = digest_queue.peek(journal=digest_queue.DEFAULT_JOURNAL)
        assert len(entries) == 1
        assert entries[0].kind == "large_move"
        assert entries[0].priority == "p2"

    def test_low_severity_cve_batches(self, monkeypatch, tmp_path):
        def _boom(*a, **kw):
            raise AssertionError("notify.py should not run for low CVEs")

        monkeypatch.setattr(alerts.subprocess, "run", _boom)
        alerts.alert_new_cve(cve_id="CVE-2026-1", severity="low", package="p")
        entries = digest_queue.peek(journal=digest_queue.DEFAULT_JOURNAL)
        assert len(entries) == 1
        assert entries[0].priority == "p2"  # low CVE maps to p2 in alerts.py

    def test_below_threshold_neither_sends_nor_batches(self, monkeypatch, tmp_path):
        called = {"notify": 0}
        monkeypatch.setattr(
            alerts.subprocess, "run", lambda *a, **k: called.__setitem__("notify", 1)
        )
        assert alerts.alert_large_move(symbol="BTC", pct_change=1.0) is False
        assert called["notify"] == 0
        assert digest_queue.peek(journal=digest_queue.DEFAULT_JOURNAL) == []


class TestCriticalAlertsStillSendNow:
    """Kill switch, regime shift, and high/critical CVEs stay immediate."""

    def test_kill_switch_fires_immediately(self, stub_notify):
        alerts.alert_kill_switch("test reason")
        assert len(stub_notify["calls"]) == 1
        # Digest journal must stay empty for p1 events.
        assert digest_queue.peek(journal=digest_queue.DEFAULT_JOURNAL) == []

    def test_regime_shift_fires_immediately(self, stub_notify):
        alerts.alert_regime_shift(old_regime="risk_on", new_regime="risk_off")
        assert len(stub_notify["calls"]) == 1

    def test_critical_cve_fires_immediately(self, stub_notify):
        alerts.alert_new_cve(cve_id="CVE-2026-2", severity="critical", package="p")
        assert len(stub_notify["calls"]) == 1


class TestDedupSurvivesRouting:
    """Same fingerprint must be silenced regardless of channel."""

    def test_second_p2_alert_dedupes(self, monkeypatch, tmp_path):
        first = alerts.alert_large_move(symbol="BTC", pct_change=6.4)
        second = alerts.alert_large_move(symbol="BTC", pct_change=6.4)
        assert first is True
        assert second is False  # deduped
        entries = digest_queue.peek(journal=digest_queue.DEFAULT_JOURNAL)
        assert len(entries) == 1


class TestBodyRendering:
    def test_digest_body_strips_mdv2_escapes(self):
        text = "🚀 *Large move* · `BTC`\n\n• *Change*: 🟢 `\\+6\\.4%`"
        body = alerts._digest_body(text)
        assert "\\" not in body
        assert body.startswith("*Change")
