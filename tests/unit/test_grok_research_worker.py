from __future__ import annotations

import json
from pathlib import Path

from lib.grok.research_worker import validate_research_manifest

ROOT = Path(__file__).resolve().parents[2]
FIX = ROOT / "projects/grok/fixtures"


def test_good_manifest():
    m = json.loads((FIX / "research_worker_manifest_good.json").read_text())
    r = validate_research_manifest(m)
    assert r["ok"] is True
    assert r["errors"] == []


def test_bad_manifest_rejects_live():
    m = json.loads((FIX / "research_worker_manifest_bad.json").read_text())
    r = validate_research_manifest(m)
    assert r["ok"] is False
    assert any("paper_only" in e for e in r["errors"])
