"""Tests for lib/content/translator.py — EN→ES translator.

Run: /usr/local/bin/python3 -m pytest tests/unit/test_content_translator.py -v
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from lib.content.translator import (  # noqa: E402
    LANG_EN,
    LANG_ES,
    ArtifactReport,
    Translator,
    detect_artifacts,
    is_supported_language,
    translate_text,
)

# ── Basic contract ────────────────────────────────────────────────────────────


def test_supported_languages():
    assert is_supported_language(LANG_EN)
    assert is_supported_language(LANG_ES)
    assert is_supported_language("en")
    assert is_supported_language("es")
    assert not is_supported_language("fr")
    assert not is_supported_language("")


def test_translate_text_en_is_identity():
    """Translating to English is a no-op — we still emit the original."""
    text = "Bear market weakened predictions this week."
    assert translate_text(text, "en") == text


def test_translate_text_unsupported_raises():
    with pytest.raises(ValueError):
        translate_text("hello", "fr")


# ── Glossary application ──────────────────────────────────────────────────────


def test_translates_glossary_terms():
    got = translate_text("Bear market weakened.", "es")
    assert "mercado bajista" in got.lower()


def test_translates_multi_word_before_single_word():
    """`bull market` must translate whole, not word-by-word."""
    got = translate_text("Bull market signals.", "es")
    # If done word-by-word we'd get "toro mercado señales" or similar garbage.
    assert "mercado alcista" in got.lower()


def test_translates_case_insensitively_but_preserves_context():
    got = translate_text("BEAR MARKET is here.", "es")
    assert "mercado bajista" in got.lower()


def test_bear_and_bull_can_coexist():
    got = translate_text("Bear market gave way to a bull market.", "es")
    low = got.lower()
    assert "mercado bajista" in low
    assert "mercado alcista" in low


# ── Data preservation ────────────────────────────────────────────────────────


def test_ticker_symbols_preserved():
    """BTC, ETH, DXY etc must survive unchanged."""
    got = translate_text("BTC and ETH signals via DXY macro.", "es")
    assert "BTC" in got
    assert "ETH" in got
    assert "DXY" in got


def test_dollar_amounts_preserved():
    got = translate_text("Portfolio at $103,500.00 today.", "es")
    assert "$103,500.00" in got


def test_percentages_preserved():
    got = translate_text("Accuracy hit 83.3% this cycle.", "es")
    assert "83.3%" in got


def test_negative_and_signed_numbers_preserved():
    got = translate_text("PnL -2.5% and +3.7% respectively.", "es")
    assert "-2.5%" in got
    assert "+3.7%" in got


def test_data_paths_preserved():
    """data/foo.jsonl-style citations are structural — must not be mangled."""
    got = translate_text(
        "Source: data/trading_predictions.jsonl and data/paper_portfolio.json.",
        "es",
    )
    assert "data/trading_predictions.jsonl" in got
    assert "data/paper_portfolio.json" in got


def test_urls_preserved():
    got = translate_text("See https://sapphirealpha.xyz/dashboard for the market.", "es")
    assert "https://sapphirealpha.xyz/dashboard" in got


def test_cve_ids_preserved():
    got = translate_text("CVE-2026-1234 is exploited in the wild.", "es")
    assert "CVE-2026-1234" in got
    assert "explotado en la práctica" in got.lower()


def test_hashtags_preserved_and_not_split():
    """`#Crypto` stays intact — we do not translate the tag body."""
    got = translate_text("Publishing today. #Crypto #Sapphire", "es")
    assert "#Crypto" in got
    assert "#Sapphire" in got


# ── Platform-specific formatting ──────────────────────────────────────────────


def test_x_thread_translation_preserves_tweet_split():
    t = Translator(target="es")
    tweets_en = [
        "Sapphire weekly crypto brief — thread. (1/3)",
        "Bear market predictions: 84/120 correct. (2/3)",
        "Paper portfolio at $103,500. (3/3)",
    ]
    tweets_es = t.translate_x_thread(tweets_en)
    assert len(tweets_es) == len(tweets_en)
    # Tweet numbering stays untouched.
    assert tweets_es[0].endswith("(1/3)")
    assert tweets_es[2].endswith("(3/3)")
    # And no tweet exceeds the X limit.
    from lib.content.formatters import X_TWEET_LIMIT

    for tw in tweets_es:
        assert len(tw) <= X_TWEET_LIMIT, f"tweet over limit: {len(tw)} > {X_TWEET_LIMIT}: {tw}"


def test_linkedin_translation_preserves_limit():
    from lib.content.formatters import LINKEDIN_LIMIT

    en_text = (
        "Bull market predictions across BTC and ETH lifted the paper portfolio to $103,500. "
        "Accuracy hit 83.3% this cycle. Data sources: data/trading_predictions.jsonl.\n\n"
        "Informational only. Not investment advice."
    )
    got = translate_text(en_text, "es", platform="linkedin")
    assert len(got) <= LINKEDIN_LIMIT
    # Disclaimer survived translation.
    assert "no es asesoría de inversión" in got.lower()


def test_substack_translation_keeps_markdown_structure():
    en_md = (
        "# Sapphire Weekly Crypto Brief\n\n"
        "_Generated 2026-07-25_\n\n"
        "## Where the Predictions Stand\n\n"
        "Across 120 scored forecasts, the model hit 84 (70.0%).\n"
    )
    got = translate_text(en_md, "es", platform="substack")
    # Headers stay markdown headers.
    assert got.startswith("# ")
    assert "\n## " in got
    # Numbers survive.
    assert "120" in got
    assert "70.0%" in got


# ── Artifact detection ───────────────────────────────────────────────────────


def test_detect_double_spaces_from_placeholder_swap():
    """A common artifact of insert-and-strip translation: doubled spaces."""
    r = detect_artifacts("This is  a  test.  Really.")
    assert any("double_space" in a for a in r.artifacts)


def test_detect_untranslated_english_boilerplate():
    """If we say 'Not investment advice' remained in an ES doc, flag it."""
    es_body = "Cartera en papel a $103,500. Not investment advice."
    r = detect_artifacts(es_body, language="es")
    assert any("untranslated" in a for a in r.artifacts)


def test_detect_placeholder_leak():
    """__SAPPHIRE_PH_0__ etc must never survive into the output."""
    r = detect_artifacts("Broken translation __SAPPHIRE_PH_5__ leaked.")
    assert any("placeholder_leak" in a for a in r.artifacts)


def test_detect_smart_quote_from_glossary_leak():
    """Terms containing curly punctuation shouldn't create obvious artifacts."""
    r = detect_artifacts("Report is clean here.")
    assert r.artifacts == []


def test_detect_double_punctuation():
    r = detect_artifacts("Ended.. Started..")
    assert any("double_punctuation" in a for a in r.artifacts)


def test_clean_es_output_has_no_artifacts():
    """Sanity: a well-formed Spanish paragraph is flagged as clean."""
    good = (
        "El mercado alcista subió la cartera en papel a $103,500 esta semana. "
        "La precisión del modelo llegó a 83.3% en 36 predicciones evaluadas."
    )
    r = detect_artifacts(good, language="es")
    assert r.ok, f"expected clean but got: {r.artifacts}"


# ── Translator class integration ─────────────────────────────────────────────


def test_translator_returns_original_for_english():
    t = Translator(target="en")
    assert t.translate("Bear market") == "Bear market"


def test_translator_uses_glossary_consistently():
    """Same term twice → same Spanish rendering both times."""
    t = Translator(target="es")
    out = t.translate("Wallet 1 and wallet 2 are both cold wallets.")
    # Both `wallet` instances become `billetera`.
    assert out.lower().count("billetera") >= 3  # 2 wallet + 1 cold wallet


def test_translator_quality_check_returns_report():
    t = Translator(target="es")
    out, report = t.translate_with_report("Bull market. BTC at $100,000.")
    assert isinstance(report, ArtifactReport)
    # A short, well-formed line should be clean.
    assert report.ok, f"artifacts: {report.artifacts}"
    assert "mercado alcista" in out.lower()
