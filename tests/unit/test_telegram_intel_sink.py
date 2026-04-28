from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from lib.core.provenance import sidecar_path, verify
from services.telegram_intel.models import ChannelConfig, ClassificationResult, RawMessage
from services.telegram_intel.quality_filter import quality_filter
from services.telegram_intel.sink import TelegramIntelSink, build_record, canonical_message_id


def _record(message_id: str = "1", text: str | None = None) -> dict:
    message = RawMessage(
        channel_id="security",
        message_id=message_id,
        text=text
        or "CVE-2026-5555 exploit confirmed with mitigation guidance at https://example.com.",
        published_at="2026-04-28T12:00:00+00:00",
        metadata={"author_id": 123, "sender": "@person"},
    )
    channel = ChannelConfig(
        id="@security_feed",
        source="@security_feed",
        category="security",
        weight=1.1,
    )
    quality = quality_filter(message.text, channel_id=channel.id)
    classification = ClassificationResult(
        label="security",
        confidence=0.9,
        topics=("security",),
        model="balanced",
        source="local-inference-proxy",
        rationale="test",
    )
    return build_record(message, channel, quality, classification)


def test_build_record_is_provenance_stamped() -> None:
    record = _record()
    assert verify(record) is True
    assert record["provenance"]["generator"] == "services.telegram_intel.reader"


def test_build_record_keeps_channel_attribution_not_sender_metadata() -> None:
    record = _record()
    assert record["channel"]["source"] == "@security_feed"
    assert record["channel"]["category"] == "security"
    assert record["channel"]["weight"] == 1.1
    blob = json.dumps(record)
    assert "author_id" not in blob
    assert "@person" not in blob


def test_build_record_defangs_urls_and_redacts_pii() -> None:
    record = _record(text="Email ari@example.com about https://evil.example/CVE-2026-5555 mitigation.")
    text = record["message"]["text"]
    assert "ari@example.com" not in text
    assert "https://" not in text
    assert "hxxps://" in text
    assert "[redacted-email]" in text


def test_canonical_message_id_is_stable() -> None:
    assert canonical_message_id("a", "1") == canonical_message_id("a", "1")
    assert canonical_message_id("a", "1") != canonical_message_id("a", "2")


def test_sink_writes_daily_jsonl(tmp_path: Path) -> None:
    sink = TelegramIntelSink(tmp_path)
    result = sink.write_records([_record()], when=datetime(2026, 4, 28, tzinfo=UTC))
    assert result.written == 1
    assert result.path == tmp_path / "2026-04-28" / "messages.jsonl"
    assert result.path.exists()


def test_sink_writes_file_level_envelope_sidecar(tmp_path: Path) -> None:
    sink = TelegramIntelSink(tmp_path)
    result = sink.write_records([_record()], when=datetime(2026, 4, 28, tzinfo=UTC))
    sidecar = sidecar_path(result.path)
    envelope = json.loads(sidecar.read_text(encoding="utf-8"))
    assert verify(envelope) is True
    assert envelope["artifact_path"].endswith("messages.jsonl")
    assert envelope["provenance"]["generator"] == "services.telegram_intel.reader"


def test_sink_updates_file_level_envelope_after_append(tmp_path: Path) -> None:
    sink = TelegramIntelSink(tmp_path)
    first = sink.write_records([_record("1")], when=datetime(2026, 4, 28, tzinfo=UTC))
    first_envelope = json.loads(sidecar_path(first.path).read_text(encoding="utf-8"))
    sink.write_records([_record("2")], when=datetime(2026, 4, 28, tzinfo=UTC))
    second_envelope = json.loads(sidecar_path(first.path).read_text(encoding="utf-8"))
    assert second_envelope["artifact_sha256"] != first_envelope["artifact_sha256"]
    assert verify(second_envelope) is True


def test_sink_deduplicates_existing_records(tmp_path: Path) -> None:
    sink = TelegramIntelSink(tmp_path)
    record = _record()
    first = sink.write_records([record], when=datetime(2026, 4, 28, tzinfo=UTC))
    second = sink.write_records([record], when=datetime(2026, 4, 28, tzinfo=UTC))
    assert first.written == 1
    assert second.written == 0
    assert second.duplicates == 1


def test_sink_recent_returns_newest_first(tmp_path: Path) -> None:
    sink = TelegramIntelSink(tmp_path)
    sink.write_records([_record("1")], when=datetime(2026, 4, 27, tzinfo=UTC))
    sink.write_records([_record("2")], when=datetime(2026, 4, 28, tzinfo=UTC))
    rows = sink.recent(limit=2)
    assert [row["message"]["id"] for row in rows] == ["2", "1"]


def test_sink_count_recent(tmp_path: Path) -> None:
    sink = TelegramIntelSink(tmp_path)
    sink.write_records([_record("1"), _record("2")], when=datetime(2026, 4, 28, tzinfo=UTC))
    assert sink.count_recent() == 2


def test_sink_rejects_invalid_provenance(tmp_path: Path) -> None:
    sink = TelegramIntelSink(tmp_path)
    record = _record()
    record["message"]["text"] = "mutated after stamp"
    with pytest.raises(ValueError, match="invalid provenance"):
        sink.write_records([record], when=datetime(2026, 4, 28, tzinfo=UTC))


def test_sink_recent_skips_bad_json_lines(tmp_path: Path) -> None:
    path = tmp_path / "2026-04-28" / "messages.jsonl"
    path.parent.mkdir(parents=True)
    path.write_text("not-json\n" + json.dumps(_record()) + "\n", encoding="utf-8")
    rows = TelegramIntelSink(tmp_path).recent(limit=2)
    assert len(rows) == 1


def test_build_record_truncates_long_text() -> None:
    record = _record(text=("CVE-2026-5555 patch released. " * 600))
    assert len(record["message"]["text"]) <= 8000
