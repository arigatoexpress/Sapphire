"""Tests for deterministic content thesis and draft generation."""

from __future__ import annotations

import pytest

from lib.content import draft_generator
from lib.content.report_generator import Report
from lib.content.thesis_engine import ThesisEngine


def _report(kind: str = "market_pulse") -> Report:
    return Report(
        kind=kind,
        title="Market Pulse",
        generated_at="2026-04-27T17:00:00Z",
        facts={"asset": "BTC"},
        body="## Thesis\n\nBTC has mixed but improving market structure.",
        sources=["data/trading_predictions.jsonl"],
        tags=["unit"],
    )


def test_thesis_engine_builds_bullish_evidence() -> None:
    thesis = ThesisEngine().generate(
        "BTC",
        prediction={"symbol": "BTC", "direction": "strong_bullish"},
        regime="RISK_ON",
        factor_score=0.42,
    )

    assert thesis.stance == "bull"
    assert thesis.confidence == 1.0
    assert thesis.supporting == [
        "TA model: strong_bullish",
        "chain regime: RISK_ON",
        "factor score: +0.42",
    ]
    assert thesis.against == []
    assert thesis.headline == "BTC showing strength: TA model: strong_bullish."


def test_thesis_engine_uses_bearish_evidence_for_bear_headline() -> None:
    thesis = ThesisEngine().generate(
        "ETH",
        prediction={"symbol": "ETH", "direction": "bearish"},
        regime="RISK_OFF",
        factor_score=-0.51,
    )

    assert thesis.stance == "bear"
    assert thesis.confidence == 1.0
    assert thesis.supporting == [
        "TA model: bearish",
        "chain regime: RISK_OFF",
        "factor score: -0.51",
    ]
    assert thesis.against == []
    assert thesis.headline == "ETH under pressure: TA model: bearish."


def test_thesis_engine_neutral_tie_keeps_conflicting_evidence() -> None:
    thesis = ThesisEngine().generate(
        "SOL",
        prediction={"symbol": "SOL", "direction": "bullish"},
        regime="RISK_OFF",
        factor_score=-0.50,
    )

    assert thesis.stance == "neutral"
    assert thesis.confidence == 0.5
    assert thesis.supporting == ["mixed bullish/bearish evidence"]
    assert thesis.against == ["TA model: bullish", "chain regime: RISK_OFF", "factor score: -0.50"]
    assert thesis.headline == "SOL range-bound: mixed bullish/bearish evidence."


def test_generate_all_uses_first_prediction_per_asset() -> None:
    theses = ThesisEngine().generate_all(
        ["BTC"],
        predictions=[
            {"symbol": "BTC", "direction": "bullish"},
            {"symbol": "BTC", "direction": "bearish"},
        ],
        regime="RISK_ON",
    )

    assert len(theses) == 1
    assert theses[0].stance == "bull"
    assert "TA model: bullish" in theses[0].supporting


def test_thesis_engine_folds_confident_vault_evidence(monkeypatch) -> None:
    """With use_vault=True and a confident vault hit, the thesis grows one line."""
    from lib import vault_client
    from lib.content import thesis_engine as te

    hit = vault_client.VaultHit(
        title="BTC bullish playbook",
        path="/vault/BTC-bullish.md",
        note_id="btc-bull-1",
        group="crypto",
        score=0.71,
        chunk="Historically strong post-halving RSI + rising funding.",
        chunk_index=0,
        total_chunks=1,
    )
    result = vault_client.VaultResult(
        query="BTC bull thesis",
        verdict="confident",
        top1=0.71,
        results=[hit],
    )

    monkeypatch.setattr(te, "__name__", te.__name__)  # keep import path stable
    monkeypatch.setattr(vault_client, "query_vault", lambda *a, **kw: result)

    thesis = ThesisEngine(use_vault=True).generate(
        "BTC",
        prediction={"symbol": "BTC", "direction": "strong_bullish"},
        regime="RISK_ON",
    )

    assert thesis.stance == "bull"
    assert "vault: BTC bullish playbook" in thesis.supporting


def test_thesis_engine_ignores_weak_and_unavailable_vault(monkeypatch) -> None:
    """weak / none / unavailable verdicts must NEVER become citations."""
    from lib import vault_client
    from lib.content.thesis_engine import ThesisEngine

    for verdict in ("weak", "none", "unavailable"):
        result = vault_client.VaultResult(
            query="q",
            verdict=verdict,
            top1=0.1,
            results=[],
            error="fake" if verdict == "unavailable" else None,
        )
        monkeypatch.setattr(vault_client, "query_vault", lambda *a, r=result, **kw: r)

        thesis = ThesisEngine(use_vault=True).generate(
            "BTC",
            prediction={"symbol": "BTC", "direction": "strong_bullish"},
            regime="RISK_ON",
        )
        assert not any(s.startswith("vault:") for s in thesis.supporting), verdict


def test_thesis_engine_survives_vault_client_raising(monkeypatch) -> None:
    """A raising query_vault (any exception) must not crash thesis generation.

    This exercises the outer try/except in ``_vault_evidence`` — the guardrail
    that keeps a vault subprocess crash, timeout, or corrupted response from
    taking down deterministic thesis synthesis.
    """
    from lib import vault_client
    from lib.content.thesis_engine import ThesisEngine

    def _boom(*a, **kw):
        raise RuntimeError("vault process died mid-query")

    monkeypatch.setattr(vault_client, "query_vault", _boom)

    thesis = ThesisEngine(use_vault=True).generate(
        "BTC",
        prediction={"symbol": "BTC", "direction": "strong_bullish"},
        regime="RISK_ON",
    )
    assert thesis.stance == "bull"
    assert not any(s.startswith("vault:") for s in thesis.supporting)


def test_draft_generate_persists_markdown(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(draft_generator, "_DRAFTS_DIR", tmp_path)
    monkeypatch.setattr(draft_generator, "_GENERATORS", {"market_pulse": _report})

    draft = draft_generator.generate("market_pulse")

    assert draft.status == "draft"
    assert draft.to_dict()["body_preview"].startswith("## Thesis")
    files = list(tmp_path.glob("*_market-pulse.md"))
    assert len(files) == 1
    text = files[0].read_text(encoding="utf-8")
    assert text.startswith("# Market Pulse")
    assert "_Status: draft" in text
    assert "## Sources" in text
    assert "- `data/trading_predictions.jsonl`" in text


def test_draft_generate_rejects_unknown_kind(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(draft_generator, "_DRAFTS_DIR", tmp_path)
    monkeypatch.setattr(draft_generator, "_GENERATORS", {})

    with pytest.raises(ValueError, match="Unknown report kind"):
        draft_generator.generate("missing")

    assert list(tmp_path.iterdir()) == []


def test_draft_generate_all_skips_failed_generator(tmp_path, monkeypatch) -> None:
    def broken_report() -> Report:
        raise RuntimeError("boom")

    monkeypatch.setattr(draft_generator, "_DRAFTS_DIR", tmp_path)
    monkeypatch.setattr(
        draft_generator,
        "_GENERATORS",
        {
            "market_pulse": _report,
            "broken": broken_report,
        },
    )

    drafts = draft_generator.generate_all()

    assert [draft.report.kind for draft in drafts] == ["market_pulse"]
    assert len(list(tmp_path.glob("*.md"))) == 1
