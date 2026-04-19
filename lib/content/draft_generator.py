"""Draft generator — thin coordination layer over report_generator.

Provides a higher-level API for the content pipeline:
  - ``generate_all()`` runs every configured report type and returns drafts
  - ``Draft`` wraps a Report with status (draft / ready / rejected)
  - Persists draft metadata to data/content/drafts.jsonl

The approval flow lives in lib.content.approval; this module only
generates and persists.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone

try:
    from datetime import UTC
except ImportError:
    UTC = timezone.utc
from pathlib import Path
from typing import Any

from lib.content import report_generator
from lib.content.report_generator import Report

log = logging.getLogger(__name__)

_REPO = Path(__file__).resolve().parents[2]
_DRAFTS_DIR = _REPO / "data" / "content" / "drafts"


@dataclass
class Draft:
    report: Report
    status: str = "draft"  # draft | approved | rejected
    rejection_reason: str = ""
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.report.kind,
            "title": self.report.title,
            "status": self.status,
            "rejection_reason": self.rejection_reason,
            "created_at": self.created_at,
            "body_preview": self.report.body[:200],
        }


def _persist(draft: Draft) -> None:
    _DRAFTS_DIR.mkdir(parents=True, exist_ok=True)
    slug = draft.report.kind.replace("_", "-")
    ts = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    path = _DRAFTS_DIR / f"{ts}_{slug}.md"
    path.write_text(
        f"# {draft.report.title}\n\n"
        f"_Status: {draft.status} | Created: {draft.created_at}_\n\n"
        f"{draft.report.body}\n\n"
        f"---\n\n## Sources\n\n"
        + "\n".join(f"- `{s}`" for s in draft.report.sources)
    )


_GENERATORS: dict[str, Any] = {
    "weekly_crypto_brief": report_generator.generate_weekly_crypto_brief,
    "market_pulse": report_generator.generate_market_pulse_tweet,
}


def generate(kind: str) -> Draft:
    """Generate a single report type and return a Draft."""
    gen = _GENERATORS.get(kind)
    if gen is None:
        raise ValueError(f"Unknown report kind: {kind!r}")
    report = gen()
    draft = Draft(report=report)
    _persist(draft)
    return draft


def generate_all() -> list[Draft]:
    """Generate all configured report types."""
    drafts = []
    for kind, gen in _GENERATORS.items():
        try:
            report = gen()
            draft = Draft(report=report)
            _persist(draft)
            drafts.append(draft)
        except Exception as exc:
            log.warning("draft generation failed for %s: %s", kind, exc)
    return drafts
