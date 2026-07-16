from __future__ import annotations

import base64
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from lib.sources.tdr_pro_email import (
    TDRProEmailItem,
    TDRProEmailSource,
    _body_text,
    _extract_google_sheet_links,
    _extract_research_links,
    _html_to_text,
)

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "tdr_pro"


def fixture(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def _b64(text: str) -> str:
    return base64.urlsafe_b64encode(text.encode("utf-8")).decode("ascii")


def test_html_to_text_preserves_line_breaks() -> None:
    html = "<p>Hello</p><br><p>World</p>"
    text = _html_to_text(html)
    assert "Hello" in text
    assert "World" in text
    assert text.index("World") > text.index("Hello")


def test_body_text_extracts_plain_text() -> None:
    payload = {
        "mimeType": "text/plain",
        "body": {"data": _b64("Plain text body.")},
    }
    assert _body_text(payload) == "Plain text body."


def test_body_text_extracts_html_as_text() -> None:
    payload = {
        "mimeType": "text/html",
        "body": {"data": _b64("<p>Hello <b>world</b></p>")},
    }
    assert _body_text(payload) == "Hello world"


def test_body_text_prefers_plain_in_multipart() -> None:
    payload = {
        "mimeType": "multipart/alternative",
        "parts": [
            {"mimeType": "text/plain", "body": {"data": _b64("plain")}},
            {"mimeType": "text/html", "body": {"data": _b64("<p>html</p>")}},
        ],
    }
    assert _body_text(payload) == "plain"


def test_extract_google_sheet_links() -> None:
    text = "Portfolio: https://docs.google.com/spreadsheets/d/abc/edit Other: https://example.com"
    assert _extract_google_sheet_links(text) == ["https://docs.google.com/spreadsheets/d/abc/edit"]


def test_extract_research_links() -> None:
    text = "Research: https://thedefireport.io/research/house-call-july-2026"
    assert _extract_research_links(text) == [
        "https://thedefireport.io/research/house-call-july-2026"
    ]


def test_parse_message_from_fixture() -> None:
    source = TDRProEmailSource()
    msg = fixture("tdr_pro_email_message.json")
    item = source._parse_message(msg)
    assert item is not None
    assert item.subject == "TDR Pro Portfolio Update — July 2026"
    assert item.sender == "Michael Nadeau <michael@thedefireport.com>"
    assert item.published_at == datetime(2026, 7, 15, 16, 0, 0, tzinfo=UTC)
    assert any(
        "thedefireport.io/research/house-call-july-2026" in link for link in item.research_links
    )
    assert any("docs.google.com/spreadsheets" in link for link in item.sheet_links)


def test_parse_message_ignores_non_tdr_sender() -> None:
    source = TDRProEmailSource()
    msg = fixture("tdr_pro_email_message.json")
    # Mutate sender to a non-TDR address.
    for h in msg["payload"]["headers"]:
        if h["name"] == "From":
            h["value"] = "spam@example.com"
    assert source._parse_message(msg) is None


def test_item_to_clipping_has_frontmatter_and_links() -> None:
    item = TDRProEmailItem(
        message_id="m1",
        thread_id="t1",
        subject="TDR Pro Portfolio Update — July 2026",
        sender="michael@thedefireport.com",
        published_at=datetime(2026, 7, 15, 16, 0, 0, tzinfo=UTC),
        body_text="Hello Ari.",
        links=("https://thedefireport.io/research/house-call",),
        sheet_links=("https://docs.google.com/spreadsheets/d/abc/edit",),
        research_links=("https://thedefireport.io/research/house-call",),
    )
    clipping = item.to_clipping()
    assert clipping.startswith("---")
    assert 'source: "tdr_pro_email"' in clipping
    assert 'portfolio_url: "https://docs.google.com/spreadsheets/d/abc/edit"' in clipping
    assert "[Portfolio Google Sheet]" in clipping
    assert "[Research]" in clipping
    assert "# TDR Pro — TDR Pro Portfolio Update — July 2026" in clipping


def test_item_to_signal_is_neutral_macro() -> None:
    published = datetime(2026, 7, 15, 16, 0, 0, tzinfo=UTC)
    item = TDRProEmailItem(
        message_id="m1",
        thread_id="t1",
        subject="s",
        sender="michael@thedefireport.com",
        published_at=published,
        body_text="b",
        links=(),
        sheet_links=(),
        research_links=(),
    )
    sig = item.to_signal()
    assert sig.source == "tdr_pro_email"
    assert sig.symbol == "BTC"
    assert sig.direction == "neutral"


def test_write_clippings_respects_dry_run(monkeypatch, tmp_path) -> None:
    monkeypatch.delenv("SAPPHIRE_TDR_PRO_LIVE", raising=False)
    source = TDRProEmailSource(inbox_dir=tmp_path)
    item = TDRProEmailItem(
        message_id="m1",
        thread_id="t1",
        subject="TDR Pro Update",
        sender="michael@thedefireport.com",
        published_at=datetime(2026, 7, 15, 16, 0, 0, tzinfo=UTC),
        body_text="b",
        links=(),
        sheet_links=(),
        research_links=(),
    )
    paths = source.write_clippings([item], dry_run=True)
    assert len(paths) == 1
    assert not paths[0].exists()


def test_live_gate_blocks_gmail_by_default(monkeypatch, tmp_path) -> None:
    monkeypatch.delenv("SAPPHIRE_TDR_PRO_LIVE", raising=False)
    monkeypatch.delenv("SAPPHIRE_TDR_PRO_EMAIL_LIVE", raising=False)
    source = TDRProEmailSource(inbox_dir=tmp_path)
    with pytest.raises(Exception):  # SourceError
        source.poll()


def test_poll_uses_mock_service_builder(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("SAPPHIRE_TDR_PRO_LIVE", "1")
    monkeypatch.setenv("SAPPHIRE_TDR_PRO_EMAIL_LIVE", "1")

    msg = fixture("tdr_pro_email_message.json")

    class FakeGet:
        def execute(self):
            return msg

    class FakeMessages:
        def list(self, **kwargs):
            return self

        def execute(self):
            return {"messages": [{"id": msg["id"]}]}

        def get(self, **kwargs):
            return FakeGet()

    class FakeUsers:
        def messages(self):
            return FakeMessages()

    class FakeService:
        def users(self):
            return FakeUsers()

    source = TDRProEmailSource(inbox_dir=tmp_path, service_builder=lambda: FakeService())
    items = source.poll()
    assert len(items) == 1
    assert items[0].subject == "TDR Pro Portfolio Update — July 2026"


def test_latest_clippings_writes_file(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("SAPPHIRE_TDR_PRO_LIVE", "1")
    monkeypatch.setenv("SAPPHIRE_TDR_PRO_EMAIL_LIVE", "1")

    msg = fixture("tdr_pro_email_message.json")

    class FakeGet:
        def execute(self):
            return msg

    class FakeMessages:
        def list(self, **kwargs):
            return self

        def execute(self):
            return {"messages": [{"id": msg["id"]}]}

        def get(self, **kwargs):
            return FakeGet()

    class FakeUsers:
        def messages(self):
            return FakeMessages()

    class FakeService:
        def users(self):
            return FakeUsers()

    source = TDRProEmailSource(inbox_dir=tmp_path, service_builder=lambda: FakeService())
    paths = source.latest_clippings()
    assert len(paths) == 1
    assert paths[0].exists()
    text = paths[0].read_text(encoding="utf-8")
    assert text.startswith("---")
    assert "tdr_pro_email" in text
