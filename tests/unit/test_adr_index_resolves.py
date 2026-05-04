"""Structural tests for ``docs/adr/`` — Architecture Decision Record index.

Validates the ADR catalog ships in a reviewable shape:

- Every ADR linked from ``index.md`` exists on disk.
- Every ADR file has a recognized status (``proposed``, ``accepted``,
  ``deprecated``, ``superseded``, ``template``).
- Every ``superseded`` ADR points to its successor in the ``Related`` line.
- Every ADR file has the required sections (Status, Context, Decision,
  Consequences, Alternatives Considered).
- Every ADR file has a numeric prefix matching its filename.
- The index summary section lists exactly the ADRs that appear in the table.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
ADR_DIR = REPO_ROOT / "docs" / "adr"
INDEX_FILE = ADR_DIR / "index.md"

VALID_STATUSES = {"proposed", "accepted", "deprecated", "superseded", "template"}
REQUIRED_SECTIONS_TEMPLATE = (
    "## Context",
    "## Decision",
    "## Consequences",
    "## Alternatives Considered",
)


def _adr_files() -> list[Path]:
    """Return all ADR files (NNNN-*.md) sorted by numeric prefix."""
    pattern = re.compile(r"^\d{4}-.*\.md$")
    return sorted(p for p in ADR_DIR.glob("*.md") if pattern.match(p.name))


def _index_links() -> list[tuple[str, str]]:
    """Parse the index file's main table — return list of (filename, title)."""
    text = INDEX_FILE.read_text(encoding='utf-8')
    # Match a row like: | [0001](0001-foo.md) | Title text | accepted |
    row_pattern = re.compile(
        r"\|\s*\[\d{4}\]\(([^)]+)\)\s*\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|"
    )
    out: list[tuple[str, str]] = []
    for match in row_pattern.finditer(text):
        out.append((match.group(1).strip(), match.group(2).strip()))
    return out


def _status_of(path: Path) -> str:
    """Extract the status field from an ADR file body."""
    text = path.read_text(encoding='utf-8')
    match = re.search(r"\*\*Status\*\*:\s*([\w-]+)", text)
    if not match:
        return ""
    return match.group(1).strip().lower()


def test_adr_directory_exists():
    """ADR directory must be present at the canonical path."""
    assert ADR_DIR.is_dir(), f"ADR directory missing at {ADR_DIR}"


def test_index_file_exists():
    """Index file must exist at docs/adr/index.md."""
    assert INDEX_FILE.is_file(), f"ADR index missing at {INDEX_FILE}"


def test_template_file_exists():
    """The 0000 template must be available as a starting point."""
    template = ADR_DIR / "0000-template.md"
    assert template.is_file(), "ADR 0000 template is missing"


def test_at_least_ten_adrs_present():
    """Lane 2 spec requires ADRs 0001-0010 at minimum."""
    files = _adr_files()
    numbers = sorted({int(f.name[:4]) for f in files})
    assert 0 in numbers, "0000 template must be in the catalog"
    for needed in range(1, 11):
        assert needed in numbers, f"ADR {needed:04d} missing from catalog"


def test_every_index_link_resolves_to_real_file():
    """Every link in the index table must point to an existing file."""
    links = _index_links()
    assert links, "index.md table parsed empty — check the regex / table shape"
    for filename, _title in links:
        target = ADR_DIR / filename
        assert target.is_file(), f"index links to {filename} but file missing"


def test_every_adr_status_is_valid():
    """Each ADR must declare a status from the recognized set."""
    for path in _adr_files():
        status = _status_of(path)
        assert status, f"{path.name}: missing or unparseable Status field"
        assert status in VALID_STATUSES, (
            f"{path.name}: unknown status {status!r}; "
            f"expected one of {sorted(VALID_STATUSES)}"
        )


def test_every_superseded_adr_points_at_successor():
    """An ADR with status=superseded must cite its replacement in Related."""
    for path in _adr_files():
        status = _status_of(path)
        if status != "superseded":
            continue
        text = path.read_text(encoding='utf-8')
        related_match = re.search(r"\*\*Related\*\*:\s*([^\n]+)", text)
        assert related_match, (
            f"{path.name}: status=superseded but no Related line"
        )
        related = related_match.group(1)
        # Must mention at least one ADR number that is NOT itself.
        own_number = path.name[:4]
        successor_pattern = re.compile(r"ADR\s*0?(\d{2,4})", re.IGNORECASE)
        successors = [
            m.group(1).zfill(4)
            for m in successor_pattern.finditer(related)
            if m.group(1).zfill(4) != own_number
        ]
        assert successors, (
            f"{path.name}: status=superseded but Related line {related!r} "
            f"does not reference a successor ADR number"
        )


def test_every_real_adr_has_required_sections():
    """Every non-template ADR must have all four canonical sections."""
    for path in _adr_files():
        text = path.read_text(encoding='utf-8')
        for section in REQUIRED_SECTIONS_TEMPLATE:
            assert section in text, f"{path.name}: missing section {section!r}"


def test_template_has_required_sections():
    """The 0000 template itself must demonstrate all canonical sections."""
    template = ADR_DIR / "0000-template.md"
    text = template.read_text(encoding='utf-8')
    for section in REQUIRED_SECTIONS_TEMPLATE:
        assert section in text, f"0000-template.md missing section {section!r}"


def test_index_summaries_exist_for_every_listed_adr():
    """The 'One-line summaries' bullets must list every linked ADR."""
    text = INDEX_FILE.read_text(encoding='utf-8')
    summaries_section = text.split("## One-line summaries", 1)
    assert len(summaries_section) == 2, (
        "index.md must contain a 'One-line summaries' section"
    )
    summaries = summaries_section[1]
    # Every linked NNNN-*.md must show up as a bullet `**NNNN ...**`
    for filename, _title in _index_links():
        if filename == "0000-template.md":
            continue  # template is exempt from the one-line bullets
        prefix = filename[:4]
        bullet_pattern = re.compile(rf"\*\*{prefix}\b")
        assert bullet_pattern.search(summaries), (
            f"index.md missing one-line summary bullet for {filename}"
        )


def test_filename_prefix_matches_adr_number_in_body():
    """The Title or first heading must match the filename's numeric prefix."""
    pattern = re.compile(r"^#\s*ADR\s*(\d{4})\b", re.MULTILINE)
    for path in _adr_files():
        text = path.read_text(encoding='utf-8')
        match = pattern.search(text)
        assert match, f"{path.name}: no '# ADR NNNN' first heading found"
        body_number = match.group(1)
        filename_number = path.name[:4]
        assert body_number == filename_number, (
            f"{path.name}: filename prefix {filename_number} "
            f"disagrees with body 'ADR {body_number}'"
        )


def test_no_duplicate_adr_numbers():
    """Each numeric prefix appears exactly once in the catalog."""
    files = _adr_files()
    numbers = [f.name[:4] for f in files]
    duplicates = {n for n in numbers if numbers.count(n) > 1}
    assert not duplicates, f"Duplicate ADR numbers: {sorted(duplicates)}"


@pytest.mark.parametrize(
    "expected_filename",
    [
        "0001-no-spend-posture.md",
        "0002-worktree-per-lane.md",
        "0003-trading-critical-path-codeowners-gate.md",
        "0004-bounded-llm-tools-via-env-flag-pattern.md",
        "0005-provenance-envelopes-everywhere.md",
        "0006-fixture-clock-vs-impl-clock-test-template.md",
        "0007-correlator-deterministic-rules-then-llm-narrative.md",
        "0008-customer-surface-mock-default-with-three-gates.md",
        "0009-foundry-ontology-as-acquisition-bridge.md",
        "0010-cowork-vs-claude-code-vs-codex-split.md",
    ],
)
def test_lane_spec_adrs_present(expected_filename: str):
    """Every ADR named in the Tranche 6 Lane 2 spec must exist by exact name."""
    target = ADR_DIR / expected_filename
    assert target.is_file(), (
        f"Lane 2 spec requires {expected_filename} but file is missing"
    )
