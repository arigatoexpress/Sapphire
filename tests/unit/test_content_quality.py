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
    MIN_NUMBERS,
    check,
    count_banned,
    count_numbers,
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
        assert isinstance(report.word_count, int)
        assert isinstance(report.avg_sentence_words, float)

    def test_multiple_failures_reported(self):
        report = check("short text with game-changer robust seamless")
        assert len(report.reasons) >= 2

    def test_to_dict_keys(self):
        d = check(_good_text()).to_dict()
        assert set(d.keys()) == {
            "passed", "banned_hits", "number_count",
            "word_count", "avg_sentence_words", "reasons",
        }

    def test_to_dict_passed_is_bool(self):
        d = check(_good_text()).to_dict()
        assert isinstance(d["passed"], bool)
