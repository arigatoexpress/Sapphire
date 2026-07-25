"""Write formatted content to data/content/ready/{platform}/.

The publisher is offline: it saves files to disk, never posts to an
external service. Human-in-the-loop reviews drafts before anything ships.

File layout (English — default, backward compatible):
    data/content/ready/linkedin/{date}_{kind}.md
    data/content/ready/substack/{date}_{kind}.md
    data/content/ready/x/{date}_{kind}.jsonl        (thread, one tweet per line)
    data/content/drafts/{date}_{kind}.json          (structured report + quality)

File layout (any other language, e.g. Spanish):
    data/content/ready/linkedin/{date}_{kind}.es.md
    data/content/ready/substack/{date}_{kind}.es.md
    data/content/ready/x/{date}_{kind}.es.jsonl

`publish(report)` runs the full pipeline: format for each platform listed
in scheduler.TARGET_PLATFORMS, in each language listed in scheduler
.TARGET_LANGUAGES, quality-check each rendering, and save. Outputs include
the quality result and (for non-English) the translator's artifact report,
so failures are visible in the dashboard.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from . import formatters, quality, scheduler
from .report_generator import REPO_ROOT, Report
from .translator import detect_artifacts

CONTENT_ROOT = REPO_ROOT / "data" / "content"
READY_ROOT = CONTENT_ROOT / "ready"
DRAFTS_ROOT = CONTENT_ROOT / "drafts"

for sub in ("linkedin", "substack", "x"):
    (READY_ROOT / sub).mkdir(parents=True, exist_ok=True)
DRAFTS_ROOT.mkdir(parents=True, exist_ok=True)


def _stamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M")


def _lang_suffix(language: str) -> str:
    """`en` is the historical default → no suffix. Other languages get `.xx`."""
    return "" if language == "en" else f".{language}"


def _write_linkedin(
    report: Report, stamp: str, language: str = "en"
) -> tuple[Path, quality.QualityReport, dict]:
    text = formatters.format_linkedin(report, language=language)
    # LinkedIn posts are bullet-point format — relax coherence threshold
    q = quality.check(text, min_coherence=0.2, facts=report.facts)
    path = READY_ROOT / "linkedin" / f"{stamp}_{report.kind}{_lang_suffix(language)}.md"
    path.write_text(text)
    return path, q, detect_artifacts(text, language=language).to_dict()


def _write_substack(
    report: Report, stamp: str, language: str = "en"
) -> tuple[Path, quality.QualityReport, dict]:
    text = formatters.format_substack(report, language=language)
    q = quality.check(text, facts=report.facts)
    path = READY_ROOT / "substack" / f"{stamp}_{report.kind}{_lang_suffix(language)}.md"
    path.write_text(text)
    return path, q, detect_artifacts(text, language=language).to_dict()


def _write_x(
    report: Report, stamp: str, language: str = "en"
) -> tuple[Path, quality.QualityReport, dict]:
    thread = formatters.format_x_thread(report, language=language)
    combined = "\n\n".join(thread)
    # Tweets are short-form — relax coherence threshold like LinkedIn
    q = quality.check(combined, min_coherence=0.2, facts=report.facts)
    path = READY_ROOT / "x" / f"{stamp}_{report.kind}{_lang_suffix(language)}.jsonl"
    with path.open("w") as f:
        for i, tweet in enumerate(thread):
            f.write(json.dumps({"index": i, "text": tweet}) + "\n")
    return path, q, detect_artifacts(combined, language=language).to_dict()


_WRITERS = {
    "linkedin": _write_linkedin,
    "substack": _write_substack,
    "x": _write_x,
}


def publish(
    report: Report,
    platforms: list[str] | None = None,
    languages: list[str] | None = None,
) -> dict:
    """Format and save the report for each (platform, language) pair.

    Returns a manifest (which is also written to data/content/drafts/) with
    per-platform-per-language path + quality result + translator artifact
    report. The English `renderings` block stays at the top level so existing
    dashboards keep working; additional languages nest under `renderings_by_language`.
    """
    if platforms is None:
        platforms = scheduler.TARGET_PLATFORMS.get(report.kind, ["linkedin", "substack", "x"])
    if languages is None:
        languages = scheduler.TARGET_LANGUAGES.get(report.kind, ["en"])

    stamp = _stamp()
    renderings_by_language: dict[str, dict[str, dict]] = {}
    for lang in languages:
        per_lang: dict[str, dict] = {}
        for plat in platforms:
            writer = _WRITERS.get(plat)
            if writer is None:
                per_lang[plat] = {"error": f"no writer for platform {plat}"}
                continue
            path, q, artifact = writer(report, stamp, language=lang)
            entry: dict = {
                "path": str(path.relative_to(REPO_ROOT)),
                "quality": q.to_dict(),
                "language": lang,
            }
            if lang != "en":
                entry["artifacts"] = artifact
            per_lang[plat] = entry
        renderings_by_language[lang] = per_lang

    # Historical shape: `renderings` is the English map. Callers that only
    # know EN keep working; multi-language callers read renderings_by_language.
    manifest: dict = {
        "report": report.to_dict(),
        "renderings": renderings_by_language.get("en", {}),
        "renderings_by_language": renderings_by_language,
        "languages": languages,
        "published_at": datetime.now().isoformat(timespec="seconds"),
    }
    draft_path = DRAFTS_ROOT / f"{stamp}_{report.kind}.json"
    draft_path.write_text(json.dumps(manifest, indent=2, default=str))
    manifest["manifest_path"] = str(draft_path.relative_to(REPO_ROOT))
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
