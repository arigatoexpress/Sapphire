"""Unit tests for :mod:`lib.sources.sec_classifier`."""

from __future__ import annotations

from lib.sources.sec_classifier import (
    FilingEvent,
    classify_filing,
    filter_high_severity,
    is_amendment,
    parse_item_codes,
    summarize_direction,
    summarize_severity,
)

# ---------------------------------------------------------------------------
# parse_item_codes
# ---------------------------------------------------------------------------


def test_parse_item_codes_simple_csv() -> None:
    assert parse_item_codes("1.01,2.03") == ["1.01", "2.03"]


def test_parse_item_codes_with_item_prefix() -> None:
    assert parse_item_codes("Item 5.02,Item 7.01") == ["5.02", "7.01"]


def test_parse_item_codes_normalizes_zero_padding() -> None:
    # "5.2" should normalize to "5.02"
    codes = parse_item_codes("5.2")
    assert codes == ["5.02"]


def test_parse_item_codes_empty_string_returns_empty_list() -> None:
    assert parse_item_codes("") == []
    assert parse_item_codes(None) == []  # type: ignore[arg-type]


def test_parse_item_codes_skips_garbage() -> None:
    assert parse_item_codes("hello,1.01,not-a-code,2.03") == ["1.01", "2.03"]


# ---------------------------------------------------------------------------
# classify_filing — 8-K paths
# ---------------------------------------------------------------------------


def test_classify_8k_item_4_01_auditor_change_is_bear_high() -> None:
    event = classify_filing(ticker="aapl", form="8-K", items_field="4.01")
    assert event.severity == "high"
    assert event.direction == "bear"
    assert "auditor" in event.summary.lower() or "certifying accountant" in event.summary.lower()
    # Ticker normalized to upper
    assert event.ticker == "AAPL"


def test_classify_8k_item_1_01_material_agreement_is_high_neutral() -> None:
    event = classify_filing(ticker="MSFT", form="8-K", items_field="Item 1.01")
    assert event.severity == "high"
    assert event.direction == "neutral"
    assert event.items == "1.01"


def test_classify_8k_item_4_02_restatement_is_bear_high() -> None:
    event = classify_filing(ticker="X", form="8-K", items_field="4.02")
    assert event.severity == "high"
    assert event.direction == "bear"


def test_classify_8k_multi_item_picks_highest_severity_bear() -> None:
    # 7.01 (low) + 4.01 (high bear) → 4.01 dominates.
    event = classify_filing(ticker="X", form="8-K", items_field="7.01,4.01,9.01")
    assert event.severity == "high"
    assert event.direction == "bear"
    assert "4.01" in event.summary


def test_classify_8k_unknown_item_falls_back_to_8k_base() -> None:
    event = classify_filing(ticker="X", form="8-K", items_field="99.99")
    # Unknown item — falls back to the 8-K form base (medium / neutral).
    assert event.severity == "medium"
    assert event.direction == "neutral"


def test_classify_8k_item_1_03_bankruptcy_is_bear_high() -> None:
    event = classify_filing(ticker="X", form="8-K", items_field="1.03")
    assert event.severity == "high"
    assert event.direction == "bear"
    assert "bankruptcy" in event.summary.lower()


# ---------------------------------------------------------------------------
# classify_filing — 10-K / 10-Q
# ---------------------------------------------------------------------------


def test_classify_10k_is_high_severity_neutral() -> None:
    event = classify_filing(ticker="A", form="10-K", items_field="")
    assert event.severity == "high"
    assert event.direction == "neutral"
    assert "annual" in event.summary.lower()


def test_classify_10q_is_high_severity_neutral() -> None:
    event = classify_filing(ticker="A", form="10-Q", items_field="")
    assert event.severity == "high"
    assert event.direction == "neutral"
    assert "quarterly" in event.summary.lower()


def test_classify_amendment_form_is_recognized() -> None:
    event = classify_filing(ticker="A", form="10-K/A", items_field="")
    assert event.form == "10-K/A"
    assert is_amendment(event.form) is True


def test_classify_unknown_form_is_low_neutral() -> None:
    event = classify_filing(ticker="A", form="NT-10K", items_field="")
    assert event.severity == "low"
    assert event.direction == "neutral"


# ---------------------------------------------------------------------------
# Aggregations
# ---------------------------------------------------------------------------


def test_summarize_severity_buckets() -> None:
    events = [
        FilingEvent(ticker="A", form="8-K", items="4.01", severity="high", direction="bear", summary="", filed_at="", accession=""),
        FilingEvent(ticker="A", form="8-K", items="1.01", severity="high", direction="neutral", summary="", filed_at="", accession=""),
        FilingEvent(ticker="A", form="8-K", items="5.02", severity="medium", direction="neutral", summary="", filed_at="", accession=""),
        FilingEvent(ticker="A", form="8-K", items="7.01", severity="low", direction="neutral", summary="", filed_at="", accession=""),
    ]
    out = summarize_severity(events)
    assert out["high"] == 2
    assert out["medium"] == 1
    assert out["low"] == 1


def test_summarize_direction_buckets() -> None:
    events = [
        FilingEvent(ticker="A", form="8-K", items="4.01", severity="high", direction="bear", summary="", filed_at="", accession=""),
        FilingEvent(ticker="A", form="8-K", items="1.01", severity="high", direction="neutral", summary="", filed_at="", accession=""),
    ]
    out = summarize_direction(events)
    assert out["bear"] == 1
    assert out["neutral"] == 1
    assert out["bull"] == 0


def test_filter_high_severity_only_returns_high() -> None:
    events = [
        FilingEvent(ticker="A", form="8-K", items="4.01", severity="high", direction="bear", summary="", filed_at="", accession=""),
        FilingEvent(ticker="A", form="8-K", items="5.02", severity="medium", direction="neutral", summary="", filed_at="", accession=""),
        FilingEvent(ticker="A", form="8-K", items="7.01", severity="low", direction="neutral", summary="", filed_at="", accession=""),
    ]
    assert len(filter_high_severity(events)) == 1


# ---------------------------------------------------------------------------
# Asset hints
# ---------------------------------------------------------------------------


def test_classify_filing_emits_asset_hints() -> None:
    event = classify_filing(ticker="aapl", form="8-K", items_field="1.01")
    assert event.asset_hints == ("AAPL",)


def test_classify_filing_preserves_metadata_fields() -> None:
    event = classify_filing(
        ticker="NVDA",
        form="8-K",
        items_field="2.02",
        filed_at="2026-04-28",
        accession="0001045810-26-000123",
        primary_document="nvda-20260428.htm",
        retrieved_at="2026-04-29T00:00:00+00:00",
    )
    assert event.filed_at == "2026-04-28"
    assert event.accession == "0001045810-26-000123"
    assert event.primary_document == "nvda-20260428.htm"
    assert event.retrieved_at == "2026-04-29T00:00:00+00:00"


def test_filing_event_to_dict_round_trip() -> None:
    event = classify_filing(ticker="X", form="10-K", items_field="")
    d = event.to_dict()
    assert d["form"] == "10-K"
    assert d["severity"] == "high"
    assert d["asset_hints"] == ("X",)
