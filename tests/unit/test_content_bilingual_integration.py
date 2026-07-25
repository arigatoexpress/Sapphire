"""Integration tests: formatters + publisher emit correct EN + ES variants.

Run: /usr/local/bin/python3 -m pytest tests/unit/test_content_bilingual_integration.py -v
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from lib.content import formatters, publisher, scheduler  # noqa: E402
from lib.content.report_generator import Report  # noqa: E402

# ── Fixtures — self-contained Reports covering every kind ────────────────────


def _crypto_report() -> Report:
    return Report(
        kind="weekly_crypto_brief",
        title="Sapphire Weekly Crypto Brief",
        generated_at="2026-07-25T09:00:00+00:00",
        facts={
            "predictions": {
                "total": 120,
                "hits": 84,
                "accuracy": 0.70,
                "by_symbol": {
                    "BTC": {"hits": 30, "total": 40, "accuracy": 0.75},
                    "ETH": {"hits": 24, "total": 40, "accuracy": 0.60},
                    "SOL": {"hits": 30, "total": 40, "accuracy": 0.75},
                },
            },
            "portfolio": {
                "capital": 103500.0,
                "pnl_pct": 3.5,
                "open_positions": 1,
                "symbols": ["BTC"],
                "positions": [
                    {
                        "symbol": "BTC",
                        "side": "long",
                        "entry_price": 65000,
                        "stop_loss": 63000,
                        "take_profit": 70000,
                        "size_usd": 10000,
                    },
                ],
            },
            "signal_pipeline": {
                "count": 48,
                "sources": {"tradingview": 48},
                "symbols": {"BTC": 20, "ETH": 15, "SOL": 13},
            },
        },
        body="## Summary\n\nBull market predictions across BTC and ETH.",
        sources=["data/trading_predictions.jsonl", "data/paper_portfolio.json"],
        tags=["crypto", "trading", "weekly"],
    )


def _security_report() -> Report:
    return Report(
        kind="security_digest",
        title="Sapphire Security Digest",
        generated_at="2026-07-25T09:00:00+00:00",
        facts={
            "count": 3,
            "exploited_in_wild": 2,
            "avg_cvss": 8.4,
            "top_cves": [
                {
                    "cve": "CVE-2026-1234",
                    "title": "OpenSSL heap overflow",
                    "exploited": True,
                    "cvss": 9.1,
                    "priority_score": 0.92,
                },
            ],
        },
        body="## Top Priority CVEs\n\n3 items prioritized.",
        sources=["data/threat_intel/latest_20260725.md"],
        tags=["security"],
    )


# ── Formatters accept language= ──────────────────────────────────────────────


def test_format_linkedin_en_matches_previous_behavior():
    """Default language is `en` and output is unchanged from before this PR."""
    r = _crypto_report()
    text = formatters.format_linkedin(r)  # no language kwarg
    assert "predictions" in text.lower() or "prediction" in text.lower()
    assert "not investment advice" in text.lower()


def test_format_linkedin_es_translates_disclaimer():
    r = _crypto_report()
    text = formatters.format_linkedin(r, language="es")
    low = text.lower()
    assert "no es asesoría de inversión" in low
    assert "not investment advice" not in low
    # Fits in the same 1300-char budget after Spanish expansion.
    assert len(text) <= formatters.LINKEDIN_LIMIT


def test_format_linkedin_es_translates_key_terms():
    r = _crypto_report()
    text = formatters.format_linkedin(r, language="es")
    low = text.lower()
    # At least one anchor Spanish glossary term made it into the output.
    anchors = ["mercado", "cartera", "señal", "predicci", "precisi"]
    assert any(a in low for a in anchors), f"no ES anchors in: {text!r}"


def test_format_substack_es_keeps_markdown_headers():
    r = _crypto_report()
    text = formatters.format_substack(r, language="es")
    assert text.startswith("# ")
    assert "\n## " in text
    # Data path citations survive.
    assert "data/trading_predictions.jsonl" in text
    # Spanish disclaimer.
    assert "solo con fines informativos" in text.lower()


def test_format_x_thread_es_preserves_tweet_counters():
    r = _crypto_report()
    thread = formatters.format_x_thread(r, language="es")
    assert len(thread) >= 2
    # Every tweet still ends with its (N/M) counter.
    import re

    counter_re = re.compile(r"\(\d+/\d+\)\s*$")
    for tw in thread:
        assert counter_re.search(tw), f"missing counter on: {tw!r}"
        assert len(tw) <= formatters.X_TWEET_LIMIT


def test_format_x_thread_market_pulse_es_still_single_tweet():
    r = Report(
        kind="market_pulse",
        title="Market Pulse",
        generated_at="2026-07-25T09:00:00+00:00",
        facts={
            "predictions": {"total": 0, "hits": 0, "accuracy": 0, "by_symbol": {}},
            "portfolio": {"pnl_pct": 0, "open_positions": 0, "total_value": 100000},
            "forecasts": [],
        },
        body=(
            "Sapphire market pulse: BTC forecast bullish. "
            "Paper portfolio at +3.5% overall with 1 open positions and $103,500 total book value."
        ),
        sources=["data/paper_portfolio.json"],
        tags=["pulse"],
    )
    thread = formatters.format_x_thread(r, language="es")
    assert len(thread) == 1
    assert len(thread[0]) <= formatters.X_TWEET_LIMIT


def test_format_unsupported_language_raises():
    r = _crypto_report()
    with pytest.raises(ValueError):
        formatters.format_linkedin(r, language="fr")
    with pytest.raises(ValueError):
        formatters.format_substack(r, language="de")
    with pytest.raises(ValueError):
        formatters.format_x_thread(r, language="jp")


# ── Publisher emits per-language files ───────────────────────────────────────


def test_publisher_writes_en_and_es_variants(tmp_path):
    """Publisher writes both EN (no suffix) and ES (.es suffix) files."""
    r = _crypto_report()
    with (
        patch.object(publisher, "READY_ROOT", tmp_path / "ready"),
        patch.object(publisher, "DRAFTS_ROOT", tmp_path / "drafts"),
        patch.object(publisher, "REPO_ROOT", tmp_path),
    ):
        (tmp_path / "ready" / "linkedin").mkdir(parents=True)
        (tmp_path / "ready" / "substack").mkdir(parents=True)
        (tmp_path / "ready" / "x").mkdir(parents=True)
        (tmp_path / "drafts").mkdir(parents=True)

        manifest = publisher.publish(
            r, platforms=["linkedin", "substack", "x"], languages=["en", "es"]
        )

    # Manifest carries both languages.
    assert set(manifest["languages"]) == {"en", "es"}
    assert "en" in manifest["renderings_by_language"]
    assert "es" in manifest["renderings_by_language"]

    # EN files land with no language suffix (backward compat).
    en_link = manifest["renderings_by_language"]["en"]["linkedin"]["path"]
    assert en_link.endswith("_weekly_crypto_brief.md")
    assert ".es." not in en_link

    # ES files carry the .es infix.
    es_link = manifest["renderings_by_language"]["es"]["linkedin"]["path"]
    assert es_link.endswith("_weekly_crypto_brief.es.md")

    # ES rendering also has an artifact report.
    assert "artifacts" in manifest["renderings_by_language"]["es"]["linkedin"]
    assert "artifacts" not in manifest["renderings_by_language"]["en"]["linkedin"]


def test_publisher_default_language_backward_compatible(tmp_path):
    """When neither languages= nor scheduler map matches, EN-only is emitted."""
    r = _security_report()  # security_digest is EN-only per TARGET_LANGUAGES
    with (
        patch.object(publisher, "READY_ROOT", tmp_path / "ready"),
        patch.object(publisher, "DRAFTS_ROOT", tmp_path / "drafts"),
        patch.object(publisher, "REPO_ROOT", tmp_path),
    ):
        (tmp_path / "ready" / "linkedin").mkdir(parents=True)
        (tmp_path / "ready" / "substack").mkdir(parents=True)
        (tmp_path / "ready" / "x").mkdir(parents=True)
        (tmp_path / "drafts").mkdir(parents=True)

        manifest = publisher.publish(r)  # no languages= → scheduler default

    assert manifest["languages"] == ["en"]
    # Historical top-level `renderings` still populated.
    assert "linkedin" in manifest["renderings"]
    assert manifest["renderings"]["linkedin"]["path"].endswith("_security_digest.md")


def test_publisher_es_variant_has_no_english_boilerplate(tmp_path):
    """The ES-tagged file must not contain untranslated English disclaimers."""
    r = _crypto_report()
    with (
        patch.object(publisher, "READY_ROOT", tmp_path / "ready"),
        patch.object(publisher, "DRAFTS_ROOT", tmp_path / "drafts"),
        patch.object(publisher, "REPO_ROOT", tmp_path),
    ):
        (tmp_path / "ready" / "linkedin").mkdir(parents=True)
        (tmp_path / "ready" / "substack").mkdir(parents=True)
        (tmp_path / "ready" / "x").mkdir(parents=True)
        (tmp_path / "drafts").mkdir(parents=True)

        publisher.publish(r, platforms=["linkedin", "substack"], languages=["es"])

    es_link = next((tmp_path / "ready" / "linkedin").glob("*.es.md"))
    content = es_link.read_text().lower()
    assert "not investment advice" not in content
    assert "no es asesoría de inversión" in content


def test_scheduler_target_languages_crypto_is_bilingual():
    """Sanity check on the scheduler policy the publisher will follow."""
    assert scheduler.TARGET_LANGUAGES["weekly_crypto_brief"] == ["en", "es"]
    assert scheduler.TARGET_LANGUAGES["market_pulse"] == ["en", "es"]
    assert scheduler.TARGET_LANGUAGES["security_digest"] == ["en"]
    assert scheduler.TARGET_LANGUAGES["ai_intel"] == ["en"]


# ── Round-trip via manifest read ─────────────────────────────────────────────


def test_es_linkedin_uses_native_template_for_crypto():
    """The ES crypto template is native Spanish, not glossary-translated Spanglish."""
    r = _crypto_report()
    text = formatters.format_linkedin(r, language="es")
    # Native-only phrasing that the glossary translator would not produce
    # by itself (these are hand-written in _linkedin_crypto_es).
    assert "Con 120 pronósticos evaluados" in text
    assert "el modelo TA de 6 factores de Sapphire" in text
    assert "Cartera en papel:" in text
    assert "posiciones abiertas" in text
    assert "Fuentes de datos:" in text


def test_es_x_thread_uses_native_template_for_crypto():
    r = _crypto_report()
    thread = formatters.format_x_thread(r, language="es")
    joined = "\n".join(thread)
    assert "Informe semanal de cripto de Sapphire" in joined
    assert "Predicciones:" in joined
    assert "Cartera en papel:" in joined
    assert "posición larga" in joined


def test_es_market_pulse_uses_native_template():
    r = Report(
        kind="market_pulse",
        title="Market Pulse",
        generated_at="2026-07-25T09:00:00+00:00",
        facts={
            "predictions": {"total": 120, "hits": 84, "accuracy": 0.70, "by_symbol": {}},
            "portfolio": {"pnl_pct": 3.5, "open_positions": 1, "total_value": 103500},
            "forecasts": [
                {
                    "symbol": "BTC",
                    "direction": "bullish",
                    "target_price": 70000,
                    "confidence": 0.75,
                    "timeframe": "24h",
                }
            ],
        },
        body="ignored",
        sources=["data/paper_portfolio.json"],
        tags=["pulse"],
    )
    thread = formatters.format_x_thread(r, language="es")
    assert len(thread) == 1
    tw = thread[0]
    assert "Pulso de mercado de Sapphire" in tw
    assert "pronóstico alcista" in tw
    assert "horizonte 24h" in tw
    assert len(tw) <= formatters.X_TWEET_LIMIT


def test_manifest_json_serializable(tmp_path):
    r = _crypto_report()
    with (
        patch.object(publisher, "READY_ROOT", tmp_path / "ready"),
        patch.object(publisher, "DRAFTS_ROOT", tmp_path / "drafts"),
        patch.object(publisher, "REPO_ROOT", tmp_path),
    ):
        (tmp_path / "ready" / "linkedin").mkdir(parents=True)
        (tmp_path / "ready" / "substack").mkdir(parents=True)
        (tmp_path / "ready" / "x").mkdir(parents=True)
        (tmp_path / "drafts").mkdir(parents=True)

        manifest = publisher.publish(r, platforms=["x"], languages=["en", "es"])

    # Manifest must survive JSON round-trip (dashboard reads these).
    raw = json.dumps(manifest, default=str)
    parsed = json.loads(raw)
    assert parsed["languages"] == ["en", "es"]
