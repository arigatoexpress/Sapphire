"""Tests for lib/content/glossary.py — bilingual EN/ES terminology.

Run: /usr/local/bin/python3 -m pytest tests/unit/test_content_glossary.py -v
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from lib.content.glossary import (  # noqa: E402
    CATEGORIES,
    GLOSSARY,
    Term,
    all_terms,
    lookup,
    terms_by_category,
)

# ── Completeness ──────────────────────────────────────────────────────────────


def test_glossary_has_at_least_130_terms():
    """Coverage target: 130+ terms across trading, crypto, financial, TA, Sapphire."""
    assert len(GLOSSARY) >= 130, f"glossary too small: {len(GLOSSARY)} < 130"


def test_all_expected_categories_present():
    """Every declared category has at least one term."""
    seen = {t.category for t in GLOSSARY.values()}
    for cat in CATEGORIES:
        assert cat in seen, f"category {cat!r} has no terms"


def test_trading_terms_present():
    """Anchor terms that every trading-content reader must recognize."""
    for en in ["bull market", "bear market", "volatility", "leverage", "liquidity"]:
        assert lookup(en) is not None, f"missing anchor trading term: {en}"


def test_crypto_terms_present():
    for en in ["wallet", "staking", "mining", "smart contract", "blockchain"]:
        assert lookup(en) is not None, f"missing anchor crypto term: {en}"


def test_financial_terms_present():
    for en in ["portfolio", "yield", "return", "capital", "asset"]:
        assert lookup(en) is not None, f"missing anchor financial term: {en}"


def test_sapphire_specific_terms_present():
    """Sapphire-internal jargon that must be consistently translated."""
    for en in ["kill switch", "signal", "regime", "backtest"]:
        assert lookup(en) is not None, f"missing Sapphire term: {en}"


# ── Term shape ────────────────────────────────────────────────────────────────


def test_every_term_has_required_fields():
    for en, term in GLOSSARY.items():
        assert isinstance(term, Term)
        assert term.en == en, f"key/en mismatch for {en!r}"
        assert term.es, f"empty ES for {en!r}"
        assert term.category in CATEGORIES, f"unknown category {term.category!r} for {en!r}"


def test_english_keys_are_lowercase():
    """Lookup is case-insensitive via lowercased keys."""
    for en in GLOSSARY:
        assert en == en.lower(), f"key not lowercased: {en!r}"


def test_no_duplicate_english_terms():
    """Case-insensitive uniqueness of English side."""
    lowered = [en.lower() for en in GLOSSARY]
    assert len(lowered) == len(set(lowered))


# ── Round-trip consistency ────────────────────────────────────────────────────


def test_lookup_is_case_insensitive():
    """Bull Market and BULL MARKET and bull market all resolve to the same term."""
    for variant in ["Bull Market", "BULL MARKET", "bull market", "  bull market  "]:
        t = lookup(variant)
        assert t is not None
        assert t.en == "bull market"
        assert "alcista" in t.es.lower()


def test_lookup_returns_none_for_unknown():
    assert lookup("this-is-not-a-term-anywhere") is None


def test_bear_market_maps_to_mercado_bajista():
    """Anchor round-trip: EN term must map to the exact ES term we expect."""
    t = lookup("bear market")
    assert t is not None
    assert t.es.lower() == "mercado bajista"


def test_wallet_maps_to_billetera():
    """Neutral LatAm — 'billetera' (LatAm) rather than 'cartera' (Spain)."""
    t = lookup("wallet")
    assert t is not None
    assert t.es.lower() == "billetera"


def test_kill_switch_uses_sapphire_translation():
    """Sapphire-internal term stays consistent (interruptor de apagado)."""
    t = lookup("kill switch")
    assert t is not None
    assert "interruptor" in t.es.lower() or "apagado" in t.es.lower()


# ── Neutral LatAm Spanish (no Spain-specific quirks) ──────────────────────────


def test_no_vosotros_conjugations():
    """Latin American Spanish uses ustedes, never vosotros."""
    for en, term in GLOSSARY.items():
        low = term.es.lower()
        for spain_only in ["vosotros", "vuestro", "vuestra"]:
            assert spain_only not in low.split(), (
                f"Spain-only word {spain_only!r} in ES for {en!r}: {term.es}"
            )


def test_uses_computadora_not_ordenador():
    """If 'computer' is in the glossary, prefer LatAm 'computadora'."""
    t = lookup("computer")
    if t is not None:
        assert "ordenador" not in t.es.lower(), (
            "computer should translate to computadora (LatAm), not ordenador (Spain)"
        )


# ── Categorization helpers ────────────────────────────────────────────────────


def test_terms_by_category_returns_all_terms():
    total = sum(len(v) for v in terms_by_category().values())
    assert total == len(GLOSSARY)


def test_all_terms_returns_iterable_of_term():
    got = list(all_terms())
    assert len(got) == len(GLOSSARY)
    assert all(isinstance(t, Term) for t in got)


def test_trading_category_has_min_20_terms():
    by_cat = terms_by_category()
    assert len(by_cat["trading"]) >= 20


def test_crypto_category_has_min_20_terms():
    by_cat = terms_by_category()
    assert len(by_cat["crypto"]) >= 20
