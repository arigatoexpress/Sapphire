from __future__ import annotations

from datetime import UTC, datetime

import pytest

from lib.macro.classifier import classify_event, enrich_event
from lib.macro.sources import MacroEvent


def event(title: str, *, source: str = "fed_rss", summary: str = "") -> MacroEvent:
    return MacroEvent(
        id=f"id-{abs(hash((source, title))) % 100000}",
        source=source,
        title=title,
        summary=summary,
        url="https://official.example.test/item",
        published_at=datetime(2026, 1, 1, tzinfo=UTC),
        metadata={"source_url": "https://official.example.test/item", "official_source": True},
    )


@pytest.mark.parametrize(
    ("sample", "source", "category"),
    [
        ("FOMC Holds Rates Unchanged", "fed_rss", "monetary_policy"),
        ("Federal Open Market Committee releases minutes", "fed_fomc", "monetary_policy"),
        ("CFTC Charges Crypto Exchange With Fraud", "cftc_rss", "regulatory_enforcement"),
        ("SEC Charges Coinbase With Operating Unregistered Exchange", "sec_atom", "regulatory_enforcement"),
        ("Employment Situation: nonfarm payroll employment rises", "bls_empsit_rss", "data_release"),
        ("Consumer Price Index inflation hotter than expected", "bls_empsit_rss", "data_release"),
        ("Treasury auction: 10-Year Note", "treasury_auctions", "treasury_auction"),
        ("ECB monetary policy decisions", "ecb_rss", "international"),
        ("BIS publishes Basel Committee consultation", "bis_rss", "international"),
        ("Routine operational notice", "unknown", "other"),
    ],
)
def test_category_reachable(sample, source, category):
    assert classify_event(event(sample, source=source)).category == category


@pytest.mark.parametrize(
    ("sample", "direction"),
    [
        ("FOMC Holds Rates Unchanged", "dovish"),
        ("Federal Reserve announces 25 basis point rate hike", "hawkish"),
        ("ECB cuts key interest rates as inflation cools", "dovish"),
        ("Treasury auction sees high yield and weak demand", "hawkish"),
        ("Policy outlook is mixed and uncertain", "mixed"),
        ("BIS publishes consultation", "neutral"),
    ],
)
def test_direction_reachable(sample, direction):
    assert classify_event(event(sample)).direction_hint == direction


@pytest.mark.parametrize(
    ("sample", "source", "severity"),
    [
        ("Emergency surprise 100 basis point rate cut", "fed_rss", "extreme"),
        ("SEC Charges Binance With Fraud", "sec_atom", "extreme"),
        ("FOMC rate decision", "fed_rss", "high"),
        ("Employment Situation payroll report", "bls_empsit_rss", "high"),
        ("Treasury auction: 4-Week Bill", "treasury_auctions", "medium"),
        ("Routine operational notice", "unknown", "low"),
    ],
)
def test_severity_reachable(sample, source, severity):
    assert classify_event(event(sample, source=source)).expected_impact_severity == severity


def test_crypto_enforcement_affects_crypto_assets():
    cls = classify_event(event("CFTC Charges Crypto Exchange With Fraud", source="cftc_rss"))
    assert {"BTC", "ETH", "SOL"}.issubset(set(cls.assets_likely_affected))


def test_ecb_event_affects_eur():
    cls = classify_event(event("ECB monetary policy decisions", source="ecb_rss"))
    assert "EUR" in cls.assets_likely_affected


def test_treasury_event_affects_bonds_and_gold():
    cls = classify_event(event("Treasury auction: 10-Year Note", source="treasury_auctions"))
    assert "bonds" in cls.assets_likely_affected
    assert "gold" in cls.assets_likely_affected


def test_enrich_event_includes_official_metadata_and_classification():
    enriched = enrich_event(event("FOMC Holds Rates Unchanged"))
    assert enriched["metadata"]["source_url"].startswith("https://official")
    assert enriched["classification"]["category"] == "monetary_policy"
    assert enriched["classification"]["direction_hint"] == "dovish"
    assert 0.0 < enriched["classification"]["confidence"] <= 1.0
