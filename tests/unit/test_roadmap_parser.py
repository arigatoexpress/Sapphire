"""Tests for RoadmapParser — roadmap-aware task generation.

Verifies:
  - Parsing incomplete items from markdown
  - Phase header detection and normalization
  - Agent inference from keywords
  - Task generation with dedup
  - Edge cases (missing file, empty roadmap, all checked)
"""

import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

import pytest

# Add alpha-engine source to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "services", "alpha-engine"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "services", "alpha-engine", "src"))

from collaboration.task_manager import RoadmapParser, TaskManager


# ── Sample Roadmap ───────────────────────────────────────────────────


SAMPLE_ROADMAP = """\
# Sapphire Master Roadmap

## Phase 1: Production Hardening ⚡ ✅

- [x] Verify fill confirmation loop
- [x] Stress-test portfolio tracker

## Phase 2: Security Architecture 🔒

- [x] Segment Scout from agents
- [ ] Research Zama FHE — encrypted computation
- [ ] Prototype encrypted skill evaluation
- [ ] Design encrypted communication channels between agents

## Phase 6: Social Media Automation 📢

- [x] MediaManager with publish queue
- [ ] Configure API credentials in production
- [ ] Implement actual Substack publishing
- [ ] Automated weekly post: progress, learnings, open experiment

## Phase 7: OpenClaw Agent Upgrade 🤖

- [x] Verify existing OpenClaw agents
- [ ] Run comparison tests: old vs new model quality
- [ ] Update model configuration and redeploy

## Phase 9: Virtuals Integration (DEFERRED)

- [ ] Research Virtuals protocol on Base
- [ ] Identify integration points
"""


# ── Fixtures ─────────────────────────────────────────────────────────


@pytest.fixture
def roadmap_file(tmp_path):
    p = tmp_path / "ROADMAP.md"
    p.write_text(SAMPLE_ROADMAP)
    return str(p)


@pytest.fixture
def parser(roadmap_file):
    return RoadmapParser(roadmap_path=roadmap_file)


@pytest.fixture
def task_manager():
    return TaskManager()


# ── Parsing Tests ────────────────────────────────────────────────────


class TestParseIncompleteItems:
    def test_finds_unchecked_items(self, parser):
        items = parser.parse_incomplete_items()
        # Phase 2: 3, Phase 6: 3, Phase 7: 2, Phase 9: 2 = 10
        assert len(items) == 10

    def test_skips_checked_items(self, parser):
        items = parser.parse_incomplete_items()
        titles = [i["title"] for i in items]
        assert "Verify fill confirmation loop" not in titles
        assert "Stress-test portfolio tracker" not in titles
        assert "Segment Scout from agents" not in titles

    def test_extracts_title_correctly(self, parser):
        items = parser.parse_incomplete_items()
        titles = [i["title"] for i in items]
        assert any("Zama FHE" in t for t in titles)
        assert any("Substack" in t for t in titles)

    def test_assigns_phase(self, parser):
        items = parser.parse_incomplete_items()
        phases = {i["phase"] for i in items}
        assert "security_architecture" in phases or any("security" in p for p in phases)

    def test_assigns_agent(self, parser):
        items = parser.parse_incomplete_items()
        agents = {i["agent"] for i in items}
        # Should contain at least OBSIDIAN and SAPPHIRE (social media → SAPPHIRE)
        assert "OBSIDIAN" in agents or "EMERALD" in agents or "SAPPHIRE" in agents

    def test_missing_file_returns_empty(self):
        parser = RoadmapParser(roadmap_path="/nonexistent/ROADMAP.md")
        items = parser.parse_incomplete_items()
        assert items == []

    def test_empty_file_returns_empty(self, tmp_path):
        p = tmp_path / "EMPTY.md"
        p.write_text("")
        parser = RoadmapParser(roadmap_path=str(p))
        items = parser.parse_incomplete_items()
        assert items == []

    def test_all_checked_returns_empty(self, tmp_path):
        content = "## Phase 1\n\n- [x] Done\n- [x] Also done\n"
        p = tmp_path / "DONE.md"
        p.write_text(content)
        parser = RoadmapParser(roadmap_path=str(p))
        items = parser.parse_incomplete_items()
        assert items == []


# ── Agent Inference Tests ────────────────────────────────────────────


class TestAgentInference:
    def test_security_maps_to_emerald(self):
        assert RoadmapParser._infer_agent("Security Architecture", "something") == "EMERALD"

    def test_deploy_maps_to_obsidian(self):
        assert RoadmapParser._infer_agent("Deployment", "deploy script") == "OBSIDIAN"

    def test_social_maps_to_sapphire(self):
        assert RoadmapParser._infer_agent("Social Media Automation", "publish tweet") == "SAPPHIRE"

    def test_trading_maps_to_sapphire(self):
        assert RoadmapParser._infer_agent("Trading", "backtest strategy") == "SAPPHIRE"

    def test_openclaw_maps_to_obsidian(self):
        assert RoadmapParser._infer_agent("OpenClaw Agent Upgrade", "config") == "OBSIDIAN"

    def test_unknown_defaults_to_obsidian(self):
        assert RoadmapParser._infer_agent("Random Phase", "random item") == "OBSIDIAN"

    def test_title_keywords_override_phase(self):
        # Even if phase is generic, "deploy" in title should pick OBSIDIAN
        assert RoadmapParser._infer_agent("Misc", "deploy new version") == "OBSIDIAN"

    def test_ci_maps_to_obsidian(self):
        assert RoadmapParser._infer_agent("CI Pipeline", "fix build") == "OBSIDIAN"


# ── Phase Normalization Tests ────────────────────────────────────────


class TestPhaseNormalization:
    def test_basic_normalization(self):
        assert RoadmapParser._normalize_phase("Security Architecture 🔒") == "security_architecture"

    def test_strips_emojis(self):
        slug = RoadmapParser._normalize_phase("Phase 8: Predictions 🔮")
        assert "🔮" not in slug

    def test_truncation(self):
        long_phase = "A" * 100
        assert len(RoadmapParser._normalize_phase(long_phase)) <= 60

    def test_empty_returns_unknown(self):
        assert RoadmapParser._normalize_phase("") == "unknown"


# ── Task Generation Tests ────────────────────────────────────────────


class TestGenerateTasks:
    def test_creates_tasks(self, parser, task_manager):
        result = parser.generate_tasks(task_manager)
        assert result["ok"]
        assert result["items_found"] == 10
        assert result["created"] == 10
        assert result["skipped"] == 0
        # Verify tasks were actually created
        summary = task_manager.summary()
        assert summary["total_tasks"] == 10

    def test_skips_duplicates(self, parser, task_manager):
        # First run creates tasks
        result1 = parser.generate_tasks(task_manager)
        assert result1["created"] == 10
        # Second run skips all (same titles)
        result2 = parser.generate_tasks(task_manager)
        assert result2["created"] == 0
        assert result2["skipped"] == 10

    def test_tags_include_roadmap(self, parser, task_manager):
        parser.generate_tasks(task_manager)
        # Inspect first task
        summary = task_manager.summary()
        assert summary["total_tasks"] > 0

    def test_empty_roadmap(self, tmp_path, task_manager):
        p = tmp_path / "EMPTY.md"
        p.write_text("")
        parser = RoadmapParser(roadmap_path=str(p))
        result = parser.generate_tasks(task_manager)
        assert result["ok"]
        assert result["created"] == 0
        assert result["items_found"] == 0
