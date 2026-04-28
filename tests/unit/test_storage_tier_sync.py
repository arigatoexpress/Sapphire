"""Tests for storage tier sync planning."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "ops" / "storage_tier_sync.py"

SPEC = importlib.util.spec_from_file_location("storage_tier_sync", SCRIPT)
assert SPEC and SPEC.loader
storage_tier_sync = importlib.util.module_from_spec(SPEC)
sys.modules["storage_tier_sync"] = storage_tier_sync
SPEC.loader.exec_module(storage_tier_sync)


def test_plan_prints_actions_without_writes(tmp_path: Path, capsys) -> None:
    repo = tmp_path / "repo"
    proton = tmp_path / "proton" / "Sapphire-OS"
    (repo / "data" / "health").mkdir(parents=True)
    (repo / "data" / ".gcp_stage").mkdir(parents=True)
    (repo / "legacy_code").mkdir()
    (repo / "results").mkdir()
    (repo / "data" / "benchmarks").mkdir(parents=True)
    proton.mkdir(parents=True)

    rc = storage_tier_sync.main(["--plan", "--repo-root", str(repo), "--proton-root", str(proton)])
    out = capsys.readouterr().out

    assert rc == 0
    assert "Sapphire Storage Tier Sync Plan" in out
    assert "copy_tree" in out
    assert not (proton / "cold-tier").exists()


def test_apply_requires_explicit_gate(tmp_path: Path, capsys) -> None:
    repo = tmp_path / "repo"
    proton = tmp_path / "proton" / "Sapphire-OS"
    repo.mkdir()
    proton.mkdir(parents=True)

    rc = storage_tier_sync.main(["--apply", "--repo-root", str(repo), "--proton-root", str(proton)])
    out = capsys.readouterr().out

    assert rc == 2
    assert "--apply requires --i-mean-it" in out
    assert not (proton / "cold-tier").exists()
