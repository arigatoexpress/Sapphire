from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from lib.correlator.scoring import ScoringWeights, compose_score
from lib.correlator.sources import CrossAssetRegimeSource
from lib.event_impact.impact_modeler import ImpactModel, ImpactProfile
from lib.intelligence.tranche4_integration import (
    TRANCHE4_EVENT_TOPICS,
    build_narrative_context,
    enrich_signal_for_narrative,
    expected_reaction_events,
    feed_status_from_artifacts,
)
from lib.synthesis.prompts import build_user_prompt
from services.event_impact.run import EVENT_TOPIC, handle_macro_event

NOW = datetime(2026, 4, 28, 12, 0, tzinfo=UTC)


def _signal() -> dict:
    return {
        "symbol": "BTC",
        "timeframe": "1h",
        "edge_score": 0.42,
        "consensus": "PARTIAL_BULL",
        "generated_at": NOW.isoformat(),
    }


def _impact_model() -> ImpactModel:
    return ImpactModel(
        profiles=(
            ImpactProfile(
                category="monetary_policy",
                sub_category="rate_hike",
                asset="BTC",
                horizon_hours=6,
                mean_return_pct=-1.2,
                median_return_pct=-0.8,
                n=7,
                stdev=2.0,
                confidence_interval_95=(-4.0, 1.6),
                direction_consensus=-0.5,
            ),
        ),
        generated_at=NOW.isoformat(),
    )


def test_narrative_context_carries_cross_asset_regime_into_prompt() -> None:
    context = build_narrative_context(
        _signal(),
        cross_asset={"regime": {"label": "crisis_correlation_spike", "confidence": 0.9}},
        generated_at=NOW,
    )
    enriched = enrich_signal_for_narrative(_signal(), context=context)
    prompt = build_user_prompt(enriched, max_input_chars=18_000)

    assert context["cross_asset_regime"]["label"] == "crisis_correlation_spike"
    assert "crisis_correlation_spike" in prompt


def test_narrative_context_selects_next_macro_event_for_asset() -> None:
    context = build_narrative_context(
        _signal(),
        macro_calendar={
            "events": [
                {"title": "ECB lending survey", "assets": ["EUR"], "scheduled_at": "2026-04-28T13:00:00+00:00"},
                {
                    "title": "FOMC decision",
                    "category": "monetary_policy",
                    "assets": ["BTC", "USD"],
                    "scheduled_at": "2026-04-28T18:00:00+00:00",
                    "source_url": "https://www.federalreserve.gov/",
                },
            ]
        },
        generated_at=NOW,
    )

    assert context["next_macro_event"]["title"] == "FOMC decision"
    assert context["next_macro_event"]["source_url"].startswith("https://")


def test_narrative_context_includes_onchain_regime_tag() -> None:
    context = build_narrative_context(
        _signal(),
        onchain={
            "assets": {
                "BTC": {
                    "composite": {
                        "onchain_heat_score": 81.5,
                        "input_count": 6,
                    }
                }
            }
        },
        generated_at=NOW,
    )

    assert context["onchain_regime"]["regime"] == "euphoria"
    assert context["onchain_regime"]["heat_score"] == pytest.approx(81.5)


def test_narrative_context_includes_counterparty_consensus() -> None:
    context = build_narrative_context(
        _signal(),
        counterparty={
            "signals": [
                {"asset": "ETH", "smart_money_consensus": 0.9},
                {
                    "asset": "BTC",
                    "side": "long",
                    "smart_money_consensus": 0.64,
                    "traders_corroborating": 4,
                },
            ]
        },
        generated_at=NOW,
    )

    assert context["smart_money_consensus"]["side"] == "long"
    assert context["smart_money_consensus"]["traders_corroborating"] == 4


def test_adversarial_subscription_topics_cover_new_tranche4_feeds() -> None:
    expected = {
        "narrative.thesis.generated",
        "regime.shift.detected",
        "correlation.breakdown",
        "macro.event.detected",
        "macro.calendar.window_opening",
        "onchain.snapshot.updated",
        "event.expected_reaction.published",
        "counterparty.smart_money.move",
    }

    assert expected.issubset(set(TRANCHE4_EVENT_TOPICS))


def test_event_impact_macro_event_handler_publishes_expected_reaction_payloads() -> None:
    result = handle_macro_event(
        {
            "title": "FOMC raises rates",
            "category": "monetary_policy",
            "sub_category": "rate_hike",
        },
        model=_impact_model(),
        assets=("BTC",),
        horizons=(6,),
        publish=False,
        generated_at=NOW,
    )

    assert result["ok"] is True
    assert result["event_topic"] == EVENT_TOPIC
    assert result["reactions"][0]["event_type"] == "event.expected_reaction.published"
    assert result["reactions"][0]["expected_reaction"]["mean_return_pct"] == pytest.approx(-1.2)


def test_expected_reaction_payload_can_be_added_to_narrative_context() -> None:
    reaction = expected_reaction_events(
        {"title": "FOMC raises rates", "category": "monetary_policy", "sub_category": "rate_hike"},
        model=_impact_model(),
        assets=("BTC",),
        horizons=(6,),
        generated_at=NOW,
    )[0]["expected_reaction"]
    context = build_narrative_context(_signal(), expected_reaction=reaction, generated_at=NOW)

    assert context["expected_reaction"]["asset"] == "BTC"
    assert context["expected_reaction"]["matched_level"] == "exact"


def test_cross_asset_regime_source_contributes_to_correlator_score(tmp_path: Path) -> None:
    base = tmp_path / "cross_asset" / "2026-04-28"
    base.mkdir(parents=True)
    (base / "regimes.jsonl").write_text(
        json.dumps({"label": "crisis_correlation_spike", "timestamp": NOW.isoformat()}) + "\n",
        encoding="utf-8",
    )
    sig = CrossAssetRegimeSource(base_dir=tmp_path / "cross_asset").latest_for("BTC", "1h")

    assert sig is not None
    score = compose_score({"cross_asset_regime": sig.to_dict()}, ScoringWeights())
    assert score.edge_score < 0
    assert score.contributing[0].source == "cross_asset_regime"


def test_observability_feed_status_reads_all_tranche4_artifacts(tmp_path: Path) -> None:
    files = {
        "data/narratives/2026-04-28/theses.jsonl": {"generated_at": NOW.isoformat()},
        "data/cross_asset/2026-04-28/regimes.jsonl": {"generated_at": NOW.isoformat()},
        "data/macro/2026-04-28/events.jsonl": {"published_at": NOW.isoformat()},
        "data/intelligence/latest/onchain_intel.json": {"generated_at": NOW.isoformat(), "assets": []},
        "data/event_impact/expected_reactions.jsonl": {"generated_at": NOW.isoformat()},
        "data/counterparty/2026-04-28/counterparty_signals.json": {
            "signals": [{"generated_at": NOW.isoformat(), "asset": "BTC"}]
        },
    }
    for rel, payload in files.items():
        path = tmp_path / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        text = json.dumps(payload) + ("\n" if path.suffix == ".jsonl" else "")
        path.write_text(text, encoding="utf-8")

    status = feed_status_from_artifacts(root=tmp_path, generated_at=NOW)

    assert status["mode"] == "read_only_tranche4_feed_status"
    assert status["totals"]["feeds"] == 6
    assert status["totals"]["with_events"] == 6
    assert all(not p.startswith(str(tmp_path)) for feed in status["feeds"] for p in feed["relative_paths"])


def test_acquirer_microsite_lists_all_tranche4_surfaces() -> None:
    html = (Path(__file__).resolve().parents[2] / "web" / "acquirer" / "index.html").read_text(
        encoding="utf-8"
    )

    for label in (
        "Narrative synthesis",
        "Cross-asset regime",
        "Regulatory + macro intel",
        "Competitive landscape memo",
        "Adversarial defense",
        "On-chain intelligence",
        "Event-impact modeling",
        "Counter-party intelligence",
    ):
        assert label in html
