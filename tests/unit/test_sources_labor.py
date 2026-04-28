from __future__ import annotations

import json
from datetime import UTC, datetime

from lib.sources.labor import LaborSource


def test_labor_dry_run_reads_cache(tmp_path, monkeypatch) -> None:
    monkeypatch.delenv("SAPPHIRE_LABOR_LIVE", raising=False)
    cache = tmp_path / "labor.json"
    cache.write_text(
        json.dumps(
            {
                "retrieved_at": datetime.now(UTC).isoformat(),
                "items": [{"title": "Employment Situation"}],
                "jobs": [{"title": f"AI engineer {idx}"} for idx in range(12)],
            }
        ),
        encoding="utf-8",
    )

    sig = LaborSource(cache_path=cache).latest_for("SPY", "1d")

    assert sig is not None
    assert sig.direction == "bull"
    assert sig.raw["bls_items"] == 1
    assert sig.raw["public_jobs"] == 12
    assert sig.raw["live_operator_flag"] is False


def test_labor_sitemap_parser_excludes_linkedin_and_indeed() -> None:
    xml = """<?xml version="1.0"?>
    <urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
      <url><loc>https://example.com/careers/backend-engineer</loc></url>
      <url><loc>https://linkedin.com/jobs/view/1</loc></url>
      <url><loc>https://indeed.com/viewjob?jk=1</loc></url>
    </urlset>"""

    rows = LaborSource._parse_sitemap(xml, source_url="https://example.com/sitemap.xml")

    assert rows == [
        {
            "url": "https://example.com/careers/backend-engineer",
            "source": "career_sitemap",
            "source_url": "https://example.com/sitemap.xml",
        }
    ]
