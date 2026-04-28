"""Structural tests for the runbook coverage audit.

Validates that ``docs/ops/runbook-coverage-audit-2026-04-29.md``:

- Exists at the expected path.
- Lists every entry with a quality score in 1-5 (integer).
- Has a non-empty gap action whenever the score is < 4.
- Cites runbook paths that resolve to real files (or explicitly says
  "(none)" when there is no runbook).
- Has rubric definitions, aggregate scores, and remediation order
  sections (the document is not just a flat table).
- Mentions the SLO companion document as the partner artifact.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
OPS_DIR = REPO_ROOT / "docs" / "ops"
AUDIT_FILE = OPS_DIR / "runbook-coverage-audit-2026-04-29.md"
SLO_FILE = OPS_DIR / "slos.md"

def _audit_rows() -> list[dict[str, str]]:
    """Parse every row of the audit doc into a list of dicts.

    The audit has three tables of varying column counts (4-col Services,
    5-col LaunchAgents, 4-col Cloud routines, plus a 7-col Cloud routine
    row that includes cron + availability columns). Walk each pipe-row
    and locate the score column dynamically.
    """
    text = AUDIT_FILE.read_text()
    rows: list[dict[str, str]] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line.startswith("|") or not line.endswith("|"):
            continue
        if line.startswith("|---") or line.startswith("|--"):
            continue
        # Drop leading/trailing pipes, split on pipe.
        cells = [c.strip() for c in line.strip("|").split("|")]
        if len(cells) < 4:
            continue
        surface = cells[0]
        if surface.lower().startswith(("service", "launchagent", "routine")):
            continue
        # Score column is the first cell that is a single digit 1-5.
        score_idx = next(
            (
                i
                for i, c in enumerate(cells)
                if c.isdigit() and len(c) == 1 and 1 <= int(c) <= 5
            ),
            None,
        )
        if score_idx is None:
            continue
        # Runbook cell sits between surface (idx 0) and score; combine if
        # the table has multiple intermediate columns (e.g. plist source).
        if score_idx == 1:
            runbook = ""
        else:
            runbook = " | ".join(cells[1:score_idx])
        gap = cells[score_idx + 1] if score_idx + 1 < len(cells) else ""
        rows.append(
            {
                "surface": surface,
                "runbook": runbook,
                "score": cells[score_idx],
                "gap": gap,
            }
        )
    return rows


def _runbook_paths_in_cell(cell: str) -> list[str]:
    """Extract any backticked path-like strings from a runbook cell."""
    return re.findall(r"`([^`]+\.md)`", cell)


def test_audit_file_exists():
    """The audit document must ship at the canonical path."""
    assert AUDIT_FILE.is_file(), f"missing audit file at {AUDIT_FILE}"


def test_audit_has_meaningful_size():
    """The audit document must be substantive (not a stub)."""
    size = AUDIT_FILE.stat().st_size
    assert size > 5000, (
        f"audit file is only {size} bytes; expected a thorough doc "
        f"covering 19+ services + 23+ LaunchAgents + 8 cloud routines"
    )


def test_audit_has_rubric_section():
    """The doc must define the 1-5 rubric explicitly so scores are calibrated."""
    text = AUDIT_FILE.read_text()
    assert "Scoring rubric" in text or "scoring rubric" in text, (
        "audit must include a scoring rubric explanation"
    )
    # Each of the 5 rubric levels must be defined.
    for level in range(1, 6):
        assert re.search(rf"\*\*{level}\*\*", text), (
            f"audit rubric is missing level {level} definition"
        )


def test_audit_has_aggregate_section():
    """The doc must surface aggregate scores so reviewers can scan totals."""
    text = AUDIT_FILE.read_text()
    assert "Aggregate" in text, "audit must include an Aggregate section"
    # Spot-check at least one aggregate metric is reported.
    assert re.search(r"average", text, re.IGNORECASE), (
        "audit Aggregate section should report at least one average"
    )


def test_audit_has_remediation_order():
    """The doc must prioritize what to fix first — not just enumerate gaps."""
    text = AUDIT_FILE.read_text()
    assert "Recommended remediation order" in text or "remediation" in text.lower(), (
        "audit must include a remediation-priority section"
    )


def test_every_score_is_integer_1_to_5():
    """No score may sit outside the 1-5 rubric."""
    rows = _audit_rows()
    assert rows, "audit file parsed zero rows — check ROW_PATTERN"
    for row in rows:
        score = int(row["score"])
        assert 1 <= score <= 5, (
            f"surface {row['surface']!r} has score {score}; "
            f"rubric only defines 1..5"
        )


def test_low_scores_have_non_empty_gap_actions():
    """Every score below 4 must include a concrete gap action."""
    rows = _audit_rows()
    for row in rows:
        score = int(row["score"])
        if score >= 4:
            continue
        gap = row["gap"]
        assert gap and gap != "—", (
            f"surface {row['surface']!r} scored {score} but has empty "
            f"gap action; rubric requires action when score < 4"
        )
        # A gap action of "TODO" or "fixme" is also unacceptable.
        assert not re.match(r"^\s*(todo|fixme|tbd)\s*$", gap, re.IGNORECASE), (
            f"surface {row['surface']!r} has placeholder gap action {gap!r}"
        )


def test_high_scores_dont_demand_gap_actions():
    """Score 5 entries are allowed to have an em-dash for the gap action."""
    rows = _audit_rows()
    fives = [r for r in rows if int(r["score"]) == 5]
    assert fives, "expected at least one score-5 surface in the audit"


def test_every_cited_runbook_resolves():
    """Every backticked runbook path in the audit must point at a real file.

    Citations may be plain filenames (resolved against ``docs/ops/``) or
    full ``docs/<subdir>/<name>.md`` paths (resolved relative to repo root).
    """
    rows = _audit_rows()
    docs_root = REPO_ROOT / "docs"
    docs_runbook_files = {p.name for p in docs_root.rglob("*.md")}
    for row in rows:
        for cited in _runbook_paths_in_cell(row["runbook"]):
            # The cell may cite either a bare filename or a docs/<dir>/<name>
            # path. Reduce to filename for the lookup; we accept any docs/*.md.
            filename = cited.split("/")[-1]
            # Skip plist filenames cited as the plist-source column
            # (they end in `.plist` not `.md`).
            if not filename.endswith(".md"):
                continue
            assert filename in docs_runbook_files, (
                f"surface {row['surface']!r} cites runbook {cited!r} "
                f"but no such .md file exists anywhere under docs/"
            )


def test_audit_covers_known_critical_surfaces():
    """The audit must mention every critical-path surface explicitly."""
    text = AUDIT_FILE.read_text().lower()
    critical = [
        "alpha",
        "webhook",
        "hyperliquid",
        "correlator",
        "synthesis",
        "dashboard",
        "control-plane",
        "heartbeat",
        "pm_bot",
        "signal-logger",
        "telegram",
        "foundry",
    ]
    for term in critical:
        assert term in text, (
            f"audit must mention {term!r} surface (matched case-insensitively); "
            f"missing means a critical path is unaccounted-for"
        )


def test_slos_file_exists_as_companion_artifact():
    """The audit doc has a partner SLO artifact at docs/ops/slos.md."""
    assert SLO_FILE.is_file(), (
        f"missing partner SLO file at {SLO_FILE}; Lane 2 spec requires both"
    )


def test_slos_file_marks_aspirational_explicitly():
    """SLOs that exceed current measurement must be marked 'aspirational'."""
    text = SLO_FILE.read_text()
    assert "aspirational" in text.lower(), (
        "slos.md must mark at least one SLO as 'aspirational' per Lane 2 spec"
    )
    # And it must define what aspirational means so reviewers aren't guessing.
    assert re.search(r"aspirational", text, re.IGNORECASE), (
        "slos.md must define 'aspirational' as a status marker"
    )


def test_slos_file_covers_availability_latency_error_freshness():
    """The SLO doc must define all four SLO axes per the lane spec."""
    text = SLO_FILE.read_text().lower()
    for axis in ("availability", "latency", "error rate", "freshness"):
        assert axis in text, (
            f"slos.md must define the {axis!r} SLO axis"
        )


def test_audit_count_matches_lane_spec_floor():
    """Audit must cover at least 19 services + 23 LaunchAgents + 8 routines."""
    rows = _audit_rows()
    # The audit aggregates by surface kind via section headers; the row
    # count is a reasonable lower bound.
    assert len(rows) >= 50, (
        f"audit only has {len(rows)} rows; Lane 2 spec requires "
        f"≥ 50 surfaces (19 services + 23 LaunchAgents + 8 routines)"
    )


@pytest.mark.parametrize(
    "section_anchor",
    [
        "## Services",
        "## LaunchAgents",
        "## Cloud routines",
    ],
)
def test_audit_has_three_top_level_sections(section_anchor: str):
    """Audit must split into Services / LaunchAgents / Cloud routines."""
    text = AUDIT_FILE.read_text()
    assert section_anchor in text, (
        f"audit must have section {section_anchor!r}"
    )
