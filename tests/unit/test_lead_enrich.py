"""Unit tests for plugins/claw-sapphire/tools/internal/lead_enrich.py."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "plugins" / "claw-sapphire" / "tools" / "internal" / "lead_enrich.py"


@pytest.fixture
def enrich(monkeypatch):
    spec = importlib.util.spec_from_file_location("lead_enrich", TOOL)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    # Prevent Regional Intel HTTP calls.
    monkeypatch.setattr(mod, "_fetch_json", lambda url: None)
    return mod


def test_enrich_produces_required_fields(enrich) -> None:
    out = enrich.enrich_one({"name": "Acme Plumbing LLC", "category": "plumbing"})
    assert "score" in out
    assert "tier" in out
    assert "intent_signals" in out
    assert "enrichment" in out
    assert out["enrichment"]["domain"] == "acmeplumbing.com"


def test_intent_matching_word_boundary(enrich) -> None:
    # "raised" contains "ai" as a substring, but we should NOT match ai_adoption.
    out = enrich.enrich_one({
        "name": "Some Corp", "category": "finance",
        "description": "raised Series A round",
    })
    assert "ai_adoption" not in out["intent_signals"]
    assert "funding_event" in out["intent_signals"]


def test_intent_explicit_ai(enrich) -> None:
    out = enrich.enrich_one({
        "name": "AI Labs", "category": "tech",
        "description": "machine learning platform",
    })
    assert "ai_adoption" in out["intent_signals"]


def test_tier_boundaries(enrich) -> None:
    # hot: >=75, warm: >=55, cool: >=35, cold: <35
    assert enrich._tier(80) == "hot"
    assert enrich._tier(60) == "warm"
    assert enrich._tier(40) == "cool"
    assert enrich._tier(10) == "cold"


def test_guess_domain_strips_suffix(enrich) -> None:
    assert enrich._guess_domain("Acme Plumbing LLC") == "acmeplumbing.com"
    assert enrich._guess_domain("XYZ Group Inc") == "xyz.com"


def test_guess_emails_pattern_set(enrich) -> None:
    emails = enrich._guess_emails("Jane Doe", "example.com")
    assert "jane@example.com" in emails or "jane.doe@example.com" in emails
    assert all("@example.com" in e for e in emails)


def test_empty_name_scores_low(enrich) -> None:
    out = enrich.enrich_one({"name": "", "category": ""})
    assert out["score"] == 0.0
    assert out["tier"] == "cold"


def test_action_score_sorts_desc(enrich) -> None:
    leads = [
        {"name": "Weak", "category": ""},
        {"name": "Strong Corp", "category": "tech", "description": "now hiring and expanding team, raised Series B"},
    ]
    result = enrich.action_score(leads)
    assert result["leads"][0]["name"] == "Strong Corp"
    assert result["leads"][0]["score"] > result["leads"][1]["score"]


def test_tier_distribution_counts_correctly(enrich) -> None:
    leads = [
        {"name": f"Lead {i}", "category": "tech"} for i in range(5)
    ]
    result = enrich.action_score(leads)
    total = sum(result["tiers"].values())
    assert total == 5
