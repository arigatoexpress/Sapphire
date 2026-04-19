"""Tests for lib/content/quality.py — anti-slop content filter.

Run: /usr/local/bin/python3 -m pytest tests/unit/test_content_quality.py -v
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from lib.content.quality import (  # type: ignore
    BANNED_PHRASES,
    MAX_AVG_SENTENCE_WORDS,
    MAX_BANNED,
    MIN_ARGUMENT_COHERENCE,
    MIN_CITATION_QUALITY,
    MIN_EVIDENCE_COVERAGE,
    MIN_EVIDENCE_DENSITY,
    MIN_ORIGINALITY_SCORE,
    MIN_NUMBERS,
    check,
    citation_quality,
    coherence,
    count_banned,
    count_numbers,
    evidence_metrics,
    extract_citations,
    find_overreach,
    find_small_sample_performance_claims,
    find_unsupported_claims,
    originality,
    readability,
)

# ── Helpers ────────────────────────────────────────────────────────────────────

def _good_text(extra: str = "") -> str:
    """Minimal passing text: 35+ words, 3+ numbers, short sentences, no banned phrases."""
    base = (
        "BTC closed at $65,432 yesterday. ETH gained 4.2% over 48 hours. "
        "SOL open interest rose by $120M in Q1. "
        "The funding rate hit 0.03% on three major venues. "
        "Position sizing remained at 10% of the $100K notional book. " + extra
    )
    return base


# ── count_banned ──────────────────────────────────────────────────────────────

class TestCountBanned:
    def test_no_hits(self):
        assert count_banned("BTC is up 5% today.") == []

    def test_single_phrase_matched(self):
        hits = count_banned("This is a game-changer for DeFi.")
        assert hits == ["game-changer"]

    def test_case_insensitive(self):
        hits = count_banned("This is a GAME-CHANGER for DeFi.")
        assert hits == ["game-changer"]

    def test_max_banned_threshold_exact(self):
        text = "game-changer and robust solution."
        hits = count_banned(text)
        assert len(hits) == MAX_BANNED

    def test_exceeds_max_banned(self):
        text = "game-changer, robust, seamless, and revolutionary."
        hits = count_banned(text)
        assert len(hits) > MAX_BANNED

    def test_all_banned_phrases_detectable(self):
        for phrase in BANNED_PHRASES:
            hits = count_banned(f"This is {phrase} for the market.")
            assert phrase in hits

    def test_custom_phrases(self):
        hits = count_banned("foo bar baz", phrases=("foo", "qux"))
        assert hits == ["foo"]


# ── count_numbers ─────────────────────────────────────────────────────────────

class TestCountNumbers:
    def test_plain_integers(self):
        assert count_numbers("BTC up 5 points.") == 1

    def test_dollar_amounts(self):
        assert count_numbers("Price is $65,432.") == 1

    def test_percentages(self):
        assert count_numbers("Gained 4.2%.") == 1

    def test_negative_numbers(self):
        assert count_numbers("Down -3.1% on the day.") >= 1

    def test_multiple_numbers(self):
        assert count_numbers("BTC $65,432 up 4.2% in 48 hours.") >= 3

    def test_no_numbers(self):
        assert count_numbers("The market moved today.") == 0

    def test_comma_separated_large_number(self):
        assert count_numbers("$1,234,567 in volume.") == 1

    def test_min_numbers_threshold(self):
        text = "1 plus 2 equals 3."
        assert count_numbers(text) >= MIN_NUMBERS


# ── citations / evidence ─────────────────────────────────────────────────────

class TestCitationExtraction:
    def test_extracts_repo_paths(self):
        text = "Sources: data/content/ready/linkedin/post.md and docs/runbook.md"
        refs = extract_citations(text)
        assert "data/content/ready/linkedin/post.md" in refs
        assert "docs/runbook.md" in refs

    def test_extracts_urls(self):
        refs = extract_citations("See https://example.com/report for details.")
        assert refs == ["https://example.com/report"]


class TestEvidenceMetrics:
    def test_evidence_metrics_reward_numbers_and_sources(self):
        text = (
            "BTC rose 5% to $65,000. Sources: data/market_pulse/pulse_20260418.md "
            "and https://example.com/chart."
        )
        citation_count, _, density, coverage = evidence_metrics(text)
        assert citation_count == 2
        assert density >= MIN_EVIDENCE_DENSITY
        assert coverage >= MIN_EVIDENCE_COVERAGE


# ── readability ───────────────────────────────────────────────────────────────

class TestReadability:
    def test_word_count_basic(self):
        words, _ = readability("one two three four five")
        assert words == 5

    def test_avg_sentence_length_single_sentence(self):
        text = "This is a sentence with exactly seven words here."
        words, avg = readability(text)
        assert words == 9
        assert avg == pytest.approx(9.0, abs=1.0)

    def test_avg_sentence_multiple_sentences(self):
        text = "Short one. Another short sentence here. Third."
        words, avg = readability(text)
        assert words > 0
        assert avg < MAX_AVG_SENTENCE_WORDS

    def test_empty_text(self):
        words, avg = readability("")
        assert words == 0

    def test_no_sentence_terminators(self):
        text = "no terminator at all in this text"
        words, avg = readability(text)
        assert words == len(text.split())
        assert avg == pytest.approx(float(words), abs=0.1)

    def test_long_sentence_detected(self):
        long_sent = " ".join(["word"] * 40) + "."
        _, avg = readability(long_sent)
        assert avg > MAX_AVG_SENTENCE_WORDS


# ── check (integration) ───────────────────────────────────────────────────────

class TestCheck:
    def test_good_text_passes(self):
        report = check(_good_text())
        assert report.passed is True
        assert report.reasons == []

    def test_fails_on_too_many_banned_phrases(self):
        text = _good_text("game-changer, robust, and seamless.")
        report = check(text)
        assert report.passed is False
        assert any("too_many_banned_phrases" in r for r in report.reasons)

    def test_fails_on_low_data_density(self):
        # Construct text with enough words but no numbers
        words = " ".join(["word"] * 40)
        report = check(words)
        assert report.passed is False
        assert any("data_density_low" in r for r in report.reasons)

    def test_fails_on_too_short(self):
        report = check("BTC up $100 by 2% daily.")
        assert report.passed is False
        assert any("too_short" in r for r in report.reasons)

    def test_evidence_dense_short_form_can_pass_length_gate(self):
        text = (
            "BTC +5.2% to $65,000, ETH +4.1%, SOL +3.3%, OI +$120M, "
            "funding 0.03%, book flat at 10% gross, turnover low, "
            "regime neutral, and risk unchanged."
        )
        report = check(text)
        assert not any("too_short" in r for r in report.reasons)

    def test_fails_on_runaway_sentences(self):
        # One sentence of 40 words with 3 numbers embedded — avg will be ~40 > 35
        words = ["word"] * 13 + ["$1"] + ["word"] * 13 + ["4.2%"] + ["word"] * 12 + ["3"]
        long_sent = " ".join(words) + "."
        report = check(long_sent)
        assert any("sentences_too_long" in r for r in report.reasons)

    def test_exactly_max_banned_still_passes(self):
        text = _good_text("game-changer and robust choice.")
        report = check(text)
        # MAX_BANNED=2 means >2 fails; exactly 2 is ok
        assert not any("too_many_banned_phrases" in r for r in report.reasons)

    def test_report_fields_populated(self):
        report = check(_good_text())
        assert isinstance(report.banned_hits, list)
        assert isinstance(report.number_count, int)
        assert isinstance(report.citation_count, int)
        assert isinstance(report.word_count, int)
        assert isinstance(report.avg_sentence_words, float)
        assert isinstance(report.evidence_density, float)
        assert isinstance(report.evidence_coverage, float)
        assert isinstance(report.citation_quality, float)
        assert isinstance(report.coherence_score, float)
        assert isinstance(report.originality_score, float)
        assert isinstance(report.unsupported_claims, list)
        assert isinstance(report.overreach_hits, list)

    def test_multiple_failures_reported(self):
        report = check("short text with game-changer robust seamless")
        assert len(report.reasons) >= 2

    def test_fails_on_unsupported_conclusion(self):
        text = (
            "This is a game-changer for the market. "
            "Therefore this proves the strategy will always work forever."
        )
        report = check(text)
        assert report.passed is False
        assert any("unsupported_conclusions" in r for r in report.reasons)

    def test_fails_on_low_citation_quality_for_long_form(self):
        sentence = "BTC rose 5% and ETH gained 4% while SOL added 3% on the session."
        text = " ".join([sentence] * 6)
        report = check(text)
        assert report.word_count >= 80
        assert report.citation_quality < MIN_CITATION_QUALITY
        assert any("citation_quality_low" in r for r in report.reasons)

    def test_to_dict_includes_research_grade_metrics(self):
        d = check(_good_text()).to_dict()
        assert set(d.keys()) == {
            "passed",
            "banned_hits",
            "number_count",
            "citation_count",
            "word_count",
            "avg_sentence_words",
            "evidence_density",
            "evidence_coverage",
            "citation_quality",
            "coherence_score",
            "originality_score",
            "unsupported_claims",
            "overreach_hits",
            "performance_claim_violations",
            "reasons",
        }

    def test_to_dict_keys(self):
        d = check(_good_text()).to_dict()
        assert "passed" in d
        assert "reasons" in d

    def test_to_dict_passed_is_bool(self):
        d = check(_good_text()).to_dict()
        assert isinstance(d["passed"], bool)

    def test_fails_on_small_sample_accuracy_claim(self):
        text = "The model is at 58.3% accuracy across 14/24 scored forecasts."
        report = check(text, facts={"predictions": {"total": 24}})
        assert report.passed is False
        assert report.performance_claim_violations == [text]
        assert any("performance_claim_sample_too_small" in r for r in report.reasons)


class TestResearchSignals:
    def test_find_unsupported_claims(self):
        text = (
            "Markets are exciting today. "
            "Clearly this means the thesis is correct."
        )
        claims = find_unsupported_claims(text)
        assert claims == ["Clearly this means the thesis is correct."]

    def test_find_overreach(self):
        text = "This strategy always wins and nobody loses."
        hits = find_overreach(text)
        assert hits == [text]

    def test_coherence_rewards_evidence_backed_flow(self):
        text = (
            "BTC rose 5% to $65,000. "
            "This move lifted ETH by 3.2%. "
            "Therefore the book stayed at 10% gross exposure."
        )
        score = coherence(text)
        assert score >= MIN_ARGUMENT_COHERENCE

    def test_originality_penalizes_repetition(self):
        text = "Edge matters. Edge matters. Edge matters. Edge matters."
        score = originality(text)
        assert score < MIN_ORIGINALITY_SCORE

    def test_citation_quality_rewards_specific_refs(self):
        text = (
            "BTC rose 5% to $65,000. "
            "Sources: data/market_pulse/pulse_20260418.md "
            "https://example.com/report"
        )
        score = citation_quality(text)
        assert score >= MIN_CITATION_QUALITY

    def test_find_small_sample_performance_claims(self):
        text = (
            "Track record note.\n"
            "Predictions: 14/24 correct (58.3% accuracy).\n"
            "BTC 8/12"
        )
        violations = find_small_sample_performance_claims(
            text, {"predictions": {"total": 24}}
        )
        assert violations == [
            "Predictions: 14/24 correct (58.3% accuracy)",
            "BTC 8/12",
        ]
