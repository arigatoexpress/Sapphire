from __future__ import annotations

import json
from pathlib import Path

import pytest

from lib.event_impact.event_corpus import (
    DEFAULT_CORPUS_PATH,
    REQUIRED_CATEGORIES,
    HistoricalEvent,
    dedupe_events,
    events_by_category,
    load_events,
    validate_event,
)


def _raw_event(**overrides):
    raw = {
        "event_id": "x1",
        "timestamp": "2024-01-10T21:00:00+00:00",
        "category": "etf_approval",
        "sub_category": "spot_btc_etf_approval",
        "title": "SEC approves spot Bitcoin ETP exchange rule changes",
        "assets": ["BTC", "ETH"],
        "magnitude": None,
        "metadata": {
            "source_url": "https://www.sec.gov/newsroom/speeches-statements/gensler-statement-spot-bitcoin-011023",
            "source_name": "SEC",
        },
    }
    raw.update(overrides)
    return raw


def test_default_corpus_has_at_least_80_events():
    assert len(load_events(DEFAULT_CORPUS_PATH)) >= 80


def test_default_corpus_contains_every_required_category():
    counts = events_by_category(load_events(DEFAULT_CORPUS_PATH))
    assert REQUIRED_CATEGORIES <= set(counts)


@pytest.mark.parametrize("field", ["event_id", "timestamp", "category", "sub_category", "title", "assets", "metadata"])
def test_validate_event_rejects_missing_required_fields(field):
    raw = _raw_event()
    raw.pop(field)
    with pytest.raises(ValueError, match="missing required"):
        validate_event(raw)


def test_validate_event_rejects_unknown_category():
    with pytest.raises(ValueError, match="unsupported category"):
        validate_event(_raw_event(category="press_rumor"))


def test_validate_event_rejects_empty_assets():
    with pytest.raises(ValueError, match="non-empty"):
        validate_event(_raw_event(assets=[]))


def test_validate_event_rejects_missing_citation_url():
    with pytest.raises(ValueError, match="source_url"):
        validate_event(_raw_event(metadata={"source_name": "SEC"}))


def test_validate_event_rejects_non_http_citation_url():
    with pytest.raises(ValueError, match="HTTP URL"):
        validate_event(_raw_event(metadata={"source_url": "file:///tmp/nope"}))


def test_validate_event_rejects_bad_timestamp():
    with pytest.raises(ValueError, match="timestamp"):
        validate_event(_raw_event(timestamp="not-a-date"))


def test_historical_event_from_dict_normalizes_assets_and_utc():
    event = HistoricalEvent.from_dict(_raw_event(assets=["btc", "Eth"]))
    assert event.assets == ("BTC", "ETH")
    assert event.timestamp.tzinfo is not None


def test_historical_event_to_dict_is_json_serializable():
    payload = HistoricalEvent.from_dict(_raw_event()).to_dict()
    assert payload["schema_version"] == "0.1.0"
    json.dumps(payload)


def test_dedupe_events_keeps_first_occurrence():
    first = HistoricalEvent.from_dict(_raw_event(title="first"))
    second = HistoricalEvent.from_dict(_raw_event(title="second"))
    assert dedupe_events([first, second]) == [first]


def test_load_events_sorts_by_timestamp(tmp_path: Path):
    path = tmp_path / "events.jsonl"
    early = _raw_event(event_id="early", timestamp="2020-01-01T00:00:00+00:00")
    late = _raw_event(event_id="late", timestamp="2024-01-01T00:00:00+00:00")
    path.write_text(json.dumps(late) + "\n" + json.dumps(early) + "\n", encoding="utf-8")
    assert [e.event_id for e in load_events(path)] == ["early", "late"]


def test_load_events_reports_line_number_for_bad_json(tmp_path: Path):
    path = tmp_path / "bad.jsonl"
    path.write_text("{}\nnot-json\n", encoding="utf-8")
    with pytest.raises(ValueError, match=":1:"):
        load_events(path)


def test_events_by_category_counts_rows():
    events = [
        HistoricalEvent.from_dict(_raw_event(event_id="a", category="fomc_decision")),
        HistoricalEvent.from_dict(_raw_event(event_id="b", category="fomc_decision")),
        HistoricalEvent.from_dict(_raw_event(event_id="c", category="macro_shock")),
    ]
    assert events_by_category(events) == {"fomc_decision": 2, "macro_shock": 1}
