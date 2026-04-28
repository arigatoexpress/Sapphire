"""Tests for the repository structure guard."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "ops" / "check_repo_structure.py"

SPEC = importlib.util.spec_from_file_location("check_repo_structure", SCRIPT)
assert SPEC and SPEC.loader
check_repo_structure = importlib.util.module_from_spec(SPEC)
sys.modules["check_repo_structure"] = check_repo_structure
SPEC.loader.exec_module(check_repo_structure)


def test_structure_sections_include_current_guard_files() -> None:
    dirs = check_repo_structure.parse_section(
        ROOT / "STRUCTURE.md",
        check_repo_structure.DIR_START,
        check_repo_structure.DIR_END,
        strip_slash=True,
    )
    files = check_repo_structure.parse_section(
        ROOT / "STRUCTURE.md",
        check_repo_structure.FILE_START,
        check_repo_structure.FILE_END,
        strip_slash=False,
    )

    assert "docs" in dirs
    assert "tools" in dirs
    assert "STRUCTURE.md" in files
    assert ".gitleaks-docs.toml" in files


def test_current_top_level_rejects_undocumented_path(tmp_path: Path) -> None:
    (tmp_path / "known").mkdir()
    (tmp_path / "surprise").mkdir()
    (tmp_path / "README.md").write_text("ok", encoding="utf-8")

    errors = check_repo_structure.check_current_top_level(
        tmp_path,
        allowed_dirs={"known"},
        allowed_files={"README.md"},
    )

    assert errors == ["top-level directory is undocumented in STRUCTURE.md: surprise/"]
