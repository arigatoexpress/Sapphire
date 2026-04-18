"""Write formatted content to data/content/ready/{platform}/.

The publisher is offline: it saves files to disk, never posts to an
external service. Human-in-the-loop reviews drafts before anything ships.

File layout:
    data/content/ready/linkedin/{date}_{kind}.md
    data/content/ready/substack/{date}_{kind}.md
    data/content/ready/x/{date}_{kind}.jsonl    (thread — one tweet per line)
    data/content/drafts/{date}_{kind}.json      (structured report + quality)

`publish(report)` runs the full pipeline: format for each platform listed
in scheduler.TARGET_PLATFORMS, quality-check each rendering, and save.
Outputs include the quality report so failures are visible in the dashboard.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from . import formatters, quality, scheduler
from .report_generator import REPO_ROOT, Report

CONTENT_ROOT = REPO_ROOT / "data" / "content"
READY_ROOT = CONTENT_ROOT / "ready"
DRAFTS_ROOT = CONTENT_ROOT / "drafts"

for sub in ("linkedin", "substack", "x"):
    (READY_ROOT / sub).mkdir(parents=True, exist_ok=True)
DRAFTS_ROOT.mkdir(parents=True, exist_ok=True)


def _stamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M")


def _write_linkedin(report: Report, stamp: str) -> tuple[Path, quality.QualityReport]:
    text = formatters.format_linkedin(report)
    q = quality.check(text)
    path = READY_ROOT / "linkedin" / f"{stamp}_{report.kind}.md"
    path.write_text(text)
    return path, q


def _write_substack(report: Report, stamp: str) -> tuple[Path, quality.QualityReport]:
    text = formatters.format_substack(report)
    q = quality.check(text)
    path = READY_ROOT / "substack" / f"{stamp}_{report.kind}.md"
    path.write_text(text)
    return path, q


def _write_x(report: Report, stamp: str) -> tuple[Path, quality.QualityReport]:
    thread = formatters.format_x_thread(report)
    combined = "\n\n".join(thread)
    q = quality.check(combined)
    path = READY_ROOT / "x" / f"{stamp}_{report.kind}.jsonl"
    with path.open("w") as f:
        for i, tweet in enumerate(thread):
            f.write(json.dumps({"index": i, "text": tweet}) + "\n")
    return path, q


_WRITERS = {
    "linkedin": _write_linkedin,
    "substack": _write_substack,
    "x": _write_x,
}


def publish(report: Report, platforms: list[str] | None = None) -> dict:
    """Format and save the report for each platform.

    Returns a manifest (which is also written to data/content/drafts/) with
    per-platform path + quality result.
    """
    if platforms is None:
        platforms = scheduler.TARGET_PLATFORMS.get(
            report.kind, ["linkedin", "substack", "x"]
        )

    stamp = _stamp()
    renderings: dict[str, dict] = {}
    for plat in platforms:
        writer = _WRITERS.get(plat)
        if writer is None:
            renderings[plat] = {"error": f"no writer for platform {plat}"}
            continue
        path, q = writer(report, stamp)
        renderings[plat] = {
            "path": str(path.relative_to(REPO_ROOT)),
            "quality": q.to_dict(),
        }

    manifest = {
        "report": report.to_dict(),
        "renderings": renderings,
        "published_at": datetime.now().isoformat(timespec="seconds"),
    }
    draft_path = DRAFTS_ROOT / f"{stamp}_{report.kind}.json"
    draft_path.write_text(json.dumps(manifest, indent=2, default=str))
    manifest["manifest_path"] = str(draft_path.relative_to(REPO_ROOT))

    # Publish to the event bus so dashboards and downstream automations
    # can react (e.g. alert on a draft that failed quality gates). Never
    # raises — content should still land on disk even if the bus is down.
    try:
        from lib.core.event_bus import get_bus
        passed = sum(
            1 for r in renderings.values()
            if (r.get("quality") or {}).get("passed")
        )
        failed = sum(
            1 for r in renderings.values()
            if (r.get("quality") or {}).get("passed") is False
        )
        get_bus().publish(
            "content.generated",
            {
                "kind": report.kind,
                "platforms": list(renderings.keys()),
                "quality_passed": passed,
                "quality_failed": failed,
                "manifest_path": manifest["manifest_path"],
            },
            source="content.publisher",
        )
    except Exception:
        pass

    return manifest


def list_drafts(limit: int = 50) -> list[dict]:
    """Return recent draft manifests, newest first."""
    if not DRAFTS_ROOT.exists():
        return []
    files = sorted(DRAFTS_ROOT.glob("*.json"), reverse=True)[:limit]
    out = []
    for p in files:
        try:
            data = json.loads(p.read_text())
            data["manifest_path"] = str(p.relative_to(REPO_ROOT))
            out.append(data)
        except json.JSONDecodeError:
            continue
    return out
