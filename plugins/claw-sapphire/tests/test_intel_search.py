"""Tests for the Sapphire intel_search plugin tool.

Covers:
- the four actions (search / index / stats / models) on the stdin contract
- the mock embedder + JSONL backend produces stable, ranked hits
- live mode is gated on the three-env-var combination
- snapshot indexing reads from local JSON files only (no network)
"""

from __future__ import annotations

import importlib.util
import io
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
INTERNAL = ROOT / "plugins" / "claw-sapphire" / "tools" / "internal" / "intel_search.py"

_spec = importlib.util.spec_from_file_location("intel_search_internal", INTERNAL)
assert _spec is not None and _spec.loader is not None
intel_search = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = intel_search
_spec.loader.exec_module(intel_search)


@pytest.fixture
def isolated_store(monkeypatch, tmp_path):
    mock_path = tmp_path / "mock.jsonl"
    rate_path = tmp_path / "rate.json"
    monkeypatch.setattr("lib.intel.bq_vector_store.DEFAULT_MOCK_PATH", mock_path)
    monkeypatch.setattr("lib.intel.bq_vector_store.DEFAULT_RATE_PATH", rate_path)
    monkeypatch.delenv("SAPPHIRE_BQ_LIVE", raising=False)
    monkeypatch.delenv("GOOGLE_APPLICATION_CREDENTIALS", raising=False)
    monkeypatch.delenv("SAPPHIRE_BQ_PROJECT", raising=False)
    yield {"mock": mock_path, "rate": rate_path, "tmp": tmp_path}


def _index_corpus(snapshot_dir: Path) -> None:
    """Write a small corpus snapshot under ``snapshot_dir``."""
    (snapshot_dir / "intel").mkdir(parents=True, exist_ok=True)
    (snapshot_dir / "threat_intel").mkdir(parents=True, exist_ok=True)
    (snapshot_dir / "intel" / "sovereign_thesis_snapshot.json").write_text(
        json.dumps(
            {
                "assets": [
                    {
                        "symbol": "BTC",
                        "name": "Bitcoin",
                        "asset_class": "crypto",
                        "thesis": "Hard money, fixed supply, censorship resistant.",
                        "thesis_tags": ["hard_money", "self_custody"],
                    },
                    {
                        "symbol": "NEE",
                        "name": "NextEra Energy",
                        "asset_class": "equity",
                        "thesis": "Renewable infrastructure compounder with AI-power backlog.",
                        "thesis_tags": ["renewables", "ai-power"],
                    },
                ]
            }
        ),
        encoding="utf-8",
    )
    (snapshot_dir / "intel" / "convergence_watchlist.json").write_text(
        json.dumps(
            {
                "watchlist": [
                    {
                        "symbol": "FSLR",
                        "name": "First Solar",
                        "asset_class": "equity",
                        "thesis": "US-domiciled solar manufacturer with AI-load tailwinds.",
                        "tier": "core",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    (snapshot_dir / "threat_intel" / "brief.md").write_text(
        "# Threat Brief\n\nSapphire is exposed to supply chain risk in the GPU layer.\n",
        encoding="utf-8",
    )


# ---------------------------------------------------------------------------
# models / stats
# ---------------------------------------------------------------------------


def test_models_action_lists_mock_and_placeholders(isolated_store):
    out = intel_search.handle({"action": "models", "dims": 64})
    names = {row["name"] for row in out["embedders"]}
    assert "mock-hash" in names
    assert "vertex-gecko" in names
    assert out["default"] == "mock-hash"
    assert out["dims"] == 64


def test_stats_action_reports_mock_mode_and_caps(isolated_store):
    out = intel_search.handle({"action": "stats", "dims": 64})
    assert out["mode"] == "mock"
    assert out["max_query_k"] == intel_search.MAX_QUERY_K
    assert out["max_index_records_per_run"] == intel_search.MAX_INDEX_RECORDS_PER_RUN
    assert "sovereign_thesis" in out["known_sources"]


# ---------------------------------------------------------------------------
# index + search
# ---------------------------------------------------------------------------


def test_index_then_search_returns_ranked_hits(isolated_store, tmp_path):
    snapshot = tmp_path / "snap"
    _index_corpus(snapshot)
    index_payload = {
        "action": "index",
        "snapshot_dir": str(snapshot),
        "dims": 64,
        "repo_root": str(tmp_path),
    }
    indexed = intel_search.handle(index_payload)
    assert indexed["ok"] is True
    assert indexed["indexed"] >= 3  # 2 thesis assets + 1 watchlist + 1 threat brief
    search_payload = {
        "action": "search",
        "query": "Bitcoin hard money",
        "k": 3,
        "dims": 64,
    }
    out = intel_search.handle(search_payload)
    assert out["ok"] is True
    assert len(out["hits"]) >= 1
    top = out["hits"][0]
    assert "Bitcoin" in top["text"] or top["metadata"].get("symbol") == "BTC"
    # Provenance must be present on every hit.
    for hit in out["hits"]:
        assert hit["provenance"]["schema_version"] == 1


def test_search_filters_by_source(isolated_store, tmp_path):
    snapshot = tmp_path / "snap2"
    _index_corpus(snapshot)
    intel_search.handle(
        {
            "action": "index",
            "snapshot_dir": str(snapshot),
            "dims": 64,
            "repo_root": str(tmp_path),
        }
    )
    out = intel_search.handle(
        {
            "action": "search",
            "query": "solar",
            "filters": {"source": "convergence_watchlist"},
            "k": 5,
            "dims": 64,
        }
    )
    assert out["ok"] is True
    assert all(h["source"] == "convergence_watchlist" for h in out["hits"])


def test_search_rejects_missing_query(isolated_store):
    out = intel_search.handle({"action": "search", "dims": 64})
    assert "error" in out


# ---------------------------------------------------------------------------
# Live gating
# ---------------------------------------------------------------------------


def test_index_live_refuses_without_env(isolated_store, tmp_path):
    snapshot = tmp_path / "snap3"
    _index_corpus(snapshot)
    out = intel_search.handle(
        {
            "action": "index",
            "snapshot_dir": str(snapshot),
            "dims": 64,
            "live": True,
            "repo_root": str(tmp_path),
        }
    )
    assert out["ok"] is False
    assert out["error"] == "live gate refused"
    assert out["gate"]["allowed"] is False


# ---------------------------------------------------------------------------
# stdin / stdout contract
# ---------------------------------------------------------------------------


def test_main_emits_models_via_stdin_contract(isolated_store):
    stdin = io.StringIO(json.dumps({"action": "models", "dims": 64}))
    stdout = io.StringIO()
    rc = intel_search.main(stdin, stdout)
    assert rc == 0
    parsed = json.loads(stdout.getvalue())
    assert parsed["default"] == "mock-hash"


def test_main_rejects_invalid_json(isolated_store):
    stdin = io.StringIO("not-json")
    stdout = io.StringIO()
    rc = intel_search.main(stdin, stdout)
    assert rc == 2
    assert "error" in json.loads(stdout.getvalue())


def test_main_rejects_non_object_payload(isolated_store):
    stdin = io.StringIO("[1, 2, 3]")
    stdout = io.StringIO()
    rc = intel_search.main(stdin, stdout)
    assert rc == 2


def test_unknown_action_returns_error(isolated_store):
    out = intel_search.handle({"action": "delete-everything"})
    assert "error" in out
    assert "search" in out["valid_actions"]
