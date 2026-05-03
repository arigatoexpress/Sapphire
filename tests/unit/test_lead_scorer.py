"""Unit tests for lib/intel/lead_scorer.py."""

from __future__ import annotations

import pytest

from lib.intel import houston_leads, lead_scorer


@pytest.fixture
def temp_store(tmp_path, monkeypatch):
    leads_dir = tmp_path / "leads"
    leads_dir.mkdir()
    monkeypatch.setattr(houston_leads, "LEADS_DIR", leads_dir)
    monkeypatch.setattr(houston_leads, "LEADS_FILE", leads_dir / "houston_leads.jsonl")
    monkeypatch.setattr(lead_scorer, "LEADS_FILE", leads_dir / "houston_leads.jsonl")
    return leads_dir


def test_heuristic_score_foundation_is_highest():
    out = lead_scorer.heuristic_score(
        {"type": "Foundation Concern", "description": "structural foundation issue"}
    )
    assert out["score"] >= 90
    assert out["urgency"] == "high"


def test_heuristic_score_kitchen_remodel():
    out = lead_scorer.heuristic_score(
        {"type": "RES", "description": "kitchen remodel and addition"}
    )
    assert 75 <= out["score"] <= 90
    assert out["urgency"] == "medium"


def test_heuristic_score_commercial_low():
    out = lead_scorer.heuristic_score(
        {"type": "COMM", "description": "commercial office build-out"}
    )
    assert out["score"] <= 25


def test_heuristic_score_falls_back():
    out = lead_scorer.heuristic_score({"type": "", "description": ""})
    assert 0 <= out["score"] <= 100
    assert out["urgency"] in {"high", "medium", "low"}


def test_parse_response_extracts_json():
    text = '```json\n{"score": 85, "reason": "Roof", "urgency": "high"}\n```'
    parsed = lead_scorer._parse_response(text)
    assert parsed == {"score": 85, "reason": "Roof", "urgency": "high"}


def test_parse_response_rejects_invalid():
    assert lead_scorer._parse_response("") is None
    assert lead_scorer._parse_response('{"score": "high"}') is None
    assert lead_scorer._parse_response('{"score": 50}') is None  # missing reason
    assert lead_scorer._parse_response('{"score": 50, "reason": "x", "urgency": "extreme"}') is None


def test_parse_response_clamps_score():
    parsed = lead_scorer._parse_response('{"score": 150, "reason": "max", "urgency": "high"}')
    assert parsed["score"] == 100
    parsed_neg = lead_scorer._parse_response('{"score": -10, "reason": "min", "urgency": "low"}')
    assert parsed_neg["score"] == 0


def test_score_lead_falls_back_when_proxy_down(monkeypatch):
    monkeypatch.setattr(lead_scorer, "_infer", lambda *a, **k: None)
    out = lead_scorer.score_lead({"type": "Roof Damage", "description": "shingles missing"})
    assert out["score_engine"] == "heuristic"
    assert out["score"] >= 75


def test_score_lead_uses_ai_when_available(monkeypatch):
    monkeypatch.setattr(
        lead_scorer,
        "_infer",
        lambda *a, **k: '{"score": 92, "reason": "Foundation crack", "urgency": "high"}',
    )
    out = lead_scorer.score_lead({"type": "Foundation"})
    assert out["score"] == 92
    assert out["score_engine"].startswith("ai:")


def test_score_unscored_only_processes_unscored(temp_store, monkeypatch):
    monkeypatch.setattr(lead_scorer, "_infer", lambda *a, **k: None)  # force heuristic
    leads = [
        {
            "id": "test:1",
            "source": "311",
            "address": "1 A",
            "type": "Foundation",
            "score": None,
            "ingested_at": "x",
        },
        {
            "id": "test:2",
            "source": "311",
            "address": "2 B",
            "type": "Roof",
            "score": 80,
            "ingested_at": "x",
        },
    ]
    houston_leads.save_leads(leads)
    n = lead_scorer.score_unscored()
    assert n == 1
    saved = houston_leads.load_leads()
    by_id = {l["id"]: l for l in saved}
    assert by_id["test:1"]["score"] is not None
    assert by_id["test:2"]["score"] == 80  # unchanged
