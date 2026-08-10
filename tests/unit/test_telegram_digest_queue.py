"""Tests for the non-critical Telegram digest queue."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from lib.telegram import digest_queue as dq


@pytest.fixture
def journal(tmp_path) -> Path:
    return tmp_path / "digest.jsonl"


@pytest.fixture
def archive_dir(tmp_path) -> Path:
    return tmp_path / "archive"


class TestEnqueue:
    def test_writes_one_line(self, journal):
        assert dq.enqueue(kind="mover", body="BTC +3%", journal=journal)
        lines = journal.read_text().splitlines()
        assert len(lines) == 1
        payload = json.loads(lines[0])
        assert payload["kind"] == "mover"
        assert payload["body"] == "BTC +3%"
        assert payload["priority"] == "p3"

    def test_rejects_p1_so_it_doesnt_batch(self, journal):
        # p1 is the immediate-send channel — batching one would silence
        # a critical alert. Fail closed.
        assert not dq.enqueue(kind="kill", body="x", priority="p1", journal=journal)
        assert not journal.exists() or journal.read_text() == ""

    def test_rejects_empty_body(self, journal):
        assert not dq.enqueue(kind="mover", body="   ", journal=journal)

    def test_truncates_long_bodies(self, journal):
        long_body = "x" * 800
        assert dq.enqueue(kind="mover", body=long_body, journal=journal)
        payload = json.loads(journal.read_text().strip())
        assert payload["body"].endswith("…")
        assert len(payload["body"]) <= 500

    def test_ok_priorities_are_p2_and_p3(self, journal):
        assert dq.enqueue(kind="a", body="x", priority="p2", journal=journal)
        assert dq.enqueue(kind="a", body="y", priority="p3", journal=journal)
        assert len(journal.read_text().splitlines()) == 2

    def test_metadata_round_trips(self, journal):
        dq.enqueue(
            kind="cve",
            body="x",
            journal=journal,
            metadata={"cve": "CVE-2026-1", "severity": "high"},
        )
        payload = json.loads(journal.read_text().strip())
        assert payload["metadata"]["cve"] == "CVE-2026-1"


class TestPeek:
    def test_empty_returns_empty(self, journal):
        assert dq.peek(journal=journal) == []

    def test_returns_recent_entries(self, journal):
        dq.enqueue(kind="a", body="x", journal=journal)
        dq.enqueue(kind="b", body="y", journal=journal)
        entries = dq.peek(journal=journal)
        assert {e.body for e in entries} == {"x", "y"}

    def test_drops_stale_entries(self, journal):
        # Write a stale entry manually with a timestamp beyond max_age.
        old_ts = (datetime.now(UTC) - timedelta(days=3)).isoformat()
        with journal.open("w") as fh:
            fh.write(
                json.dumps(
                    {"ts": old_ts, "kind": "old", "body": "x", "priority": "p3", "metadata": {}}
                )
                + "\n"
            )
        dq.enqueue(kind="new", body="y", journal=journal)
        entries = dq.peek(journal=journal, max_age_hours=24)
        assert [e.kind for e in entries] == ["new"]


class TestFlush:
    def test_returns_none_when_empty(self, journal, archive_dir):
        assert dq.flush_digest(journal=journal, archive_dir=archive_dir) is None

    def test_formats_and_archives(self, journal, archive_dir):
        dq.enqueue(kind="mover", body="BTC +3%", priority="p2", journal=journal)
        dq.enqueue(kind="mover", body="ETH +2%", priority="p3", journal=journal)
        dq.enqueue(kind="signal", body="Long BTC", priority="p3", journal=journal)

        text = dq.flush_digest(journal=journal, archive_dir=archive_dir)
        assert text is not None
        assert "Sapphire Digest" in text
        assert "mover" in text
        assert "BTC \\+3%" in text  # MDV2-escaped
        assert "signal" in text

        # Journal drained.
        assert journal.read_text().strip() == ""
        # Archived to timestamped file.
        archives = list(archive_dir.iterdir())
        assert len(archives) == 1
        archive_lines = archives[0].read_text().splitlines()
        assert len(archive_lines) == 3

    def test_group_ordering_by_count_desc(self, journal, archive_dir):
        for i in range(5):
            dq.enqueue(kind="mover", body=f"row {i}", journal=journal)
        dq.enqueue(kind="signal", body="one", journal=journal)
        text = dq.flush_digest(journal=journal, archive_dir=archive_dir)
        assert text is not None
        # mover appears first because it has more entries.
        assert text.index("mover") < text.index("signal")


class TestFormat:
    def test_over_eight_items_truncated(self):
        now = datetime.now(UTC)
        entries = [
            dq.DigestEntry(
                ts=(now - timedelta(minutes=i)).isoformat(),
                kind="mover",
                body=f"row {i}",
                priority="p3",
            )
            for i in range(12)
        ]
        text = dq.format_digest(entries)
        assert "\\+ 4 older" in text or "+ 4 older" in text.replace("\\", "")

    def test_empty_iterable_renders_nothing_queued(self):
        text = dq.format_digest([])
        assert "nothing queued" in text.replace("\\", "")


class TestStats:
    def test_stats_shape(self, journal):
        dq.enqueue(kind="mover", body="a", priority="p2", journal=journal)
        dq.enqueue(kind="mover", body="b", priority="p3", journal=journal)
        dq.enqueue(kind="signal", body="c", priority="p3", journal=journal)
        s = dq.stats(journal=journal)
        assert s["queued"] == 3
        assert s["kinds"]["mover"] == 2
        assert s["priority_p2"] == 1
        assert s["priority_p3"] == 2


class TestJournalBounds:
    def test_trim_caps_journal(self, journal, monkeypatch):
        monkeypatch.setattr(dq, "MAX_ENTRIES", 5)
        for i in range(20):
            dq.enqueue(kind="a", body=f"n{i}", journal=journal)
        # After trim, only the latest MAX_ENTRIES survive.
        assert len(journal.read_text().splitlines()) == 5

    def test_missing_journal_never_raises(self, tmp_path):
        # peek/stats on an untouched queue must return safely, not 500.
        assert dq.peek(journal=tmp_path / "nope.jsonl") == []
        assert dq.stats(journal=tmp_path / "nope.jsonl")["queued"] == 0


class TestOnlyOneOutwardGate:
    """The queue must not have its own dispatch path — the outbound-send
    gate lives one layer up (notify.py + SAPPHIRE_NOTIFY_TELEGRAM_LIVE).
    """

    def test_module_exports_no_send_function(self):
        for name in dq.__all__:
            assert "send" not in name.lower(), (
                f"digest_queue.{name} looks like a sender — outbound gate must stay in notify.py"
            )
