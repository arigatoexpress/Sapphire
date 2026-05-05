"""Static checks for Sapphire source-of-truth guardrails."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "ops" / "check_source_of_truth.sh"


def test_source_of_truth_uses_code_sapphire_as_canonical_path() -> None:
    script = SCRIPT.read_text(encoding="utf-8")

    assert 'CANONICAL_PATH="/Users/aribs/Code/Sapphire"' in script
    assert 'CANONICAL_PATH="/Users/aribs/Sapphire"' not in script
    assert "/Users/aribs/Code/_worktrees" in script
