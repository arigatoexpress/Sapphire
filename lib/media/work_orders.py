"""Offline media work orders from Sapphire content artifacts.

The work-order layer turns existing content-engine draft manifests into
deterministic briefs for image, video, and audio generation. It does not call
model APIs, media APIs, Telegram, or publish paths.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .artifacts import REPO_ROOT, make_run_id, write_manifest

SCHEMA_VERSION = 1
DEFAULT_CONTENT_ROOT = REPO_ROOT / "data" / "content"
DEFAULT_WORK_ORDER_ROOT = REPO_ROOT / "data" / "media" / "work_orders"
DEFAULT_MANIFEST_ROOT = REPO_ROOT / "data" / "media" / "manifests"


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _repo_relative(path: Path, root: Path) -> str:
    try:
        return str(path.resolve().relative_to(root.resolve()))
    except ValueError:
        return str(path)


def _slug(value: str, *, default: str = "content") -> str:
    token = re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")
    return token or default


def _load_json(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return data


def load_draft_manifest(path: Path | str) -> dict[str, Any]:
    """Load a content-engine draft manifest."""
    return _load_json(Path(path))


@dataclass(frozen=True)
class DraftRef:
    """A local draft manifest plus the fields needed for selection."""

    path: Path
    kind: str
    published_at: str


def _draft_ref(path: Path) -> DraftRef | None:
    try:
        data = load_draft_manifest(path)
    except (OSError, ValueError, json.JSONDecodeError):
        return None
    report = data.get("report") if isinstance(data.get("report"), dict) else {}
    kind = str(report.get("kind") or path.stem.split("_", 2)[-1] or "content")
    published_at = str(data.get("published_at") or report.get("generated_at") or "")
    return DraftRef(path=path, kind=kind, published_at=published_at)


def discover_drafts(
    content_root: Path | str = DEFAULT_CONTENT_ROOT,
    *,
    kinds: list[str] | tuple[str, ...] | None = None,
    latest: bool = False,
    limit: int | None = None,
) -> list[Path]:
    """Return draft manifest paths selected by kind/date.

    With ``latest=True``, returns the newest draft per selected kind.
    """
    content_root = Path(content_root)
    wanted = {_slug(kind) for kind in kinds or ()}
    refs = [
        ref
        for path in sorted((content_root / "drafts").glob("*.json"))
        if (ref := _draft_ref(path)) is not None and (not wanted or _slug(ref.kind) in wanted)
    ]
    refs.sort(key=lambda ref: (ref.published_at, ref.path.name), reverse=True)
    if latest:
        by_kind: dict[str, DraftRef] = {}
        for ref in refs:
            by_kind.setdefault(_slug(ref.kind), ref)
        refs = list(by_kind.values())
        refs.sort(key=lambda ref: (ref.published_at, ref.path.name), reverse=True)
    if limit is not None:
        refs = refs[: max(0, limit)]
    return [ref.path for ref in refs]


def _read_rendering_text(path: Path, *, max_chars: int = 1400) -> list[str]:
    if not path.is_file():
        return []
    if path.suffix == ".jsonl":
        lines: list[str] = []
        for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
            if not raw.strip():
                continue
            try:
                row = json.loads(raw)
            except json.JSONDecodeError:
                continue
            text = str(row.get("text") or "").strip()
            if text:
                lines.append(text[:max_chars])
        return lines
    content = path.read_text(encoding="utf-8", errors="replace")
    lines = [
        line.strip()
        for line in content.splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]
    return ["\n".join(lines)[:max_chars]] if lines else []


def _rendering_records(
    draft: dict[str, Any],
    *,
    root: Path,
) -> tuple[list[dict[str, Any]], list[Path]]:
    records: list[dict[str, Any]] = []
    paths: list[Path] = []
    renderings = draft.get("renderings") if isinstance(draft.get("renderings"), dict) else {}
    for platform, item in sorted(renderings.items()):
        if not isinstance(item, dict) or not item.get("path"):
            continue
        path = root / str(item["path"])
        quality = item.get("quality") if isinstance(item.get("quality"), dict) else {}
        paths.append(path)
        records.append(
            {
                "platform": platform,
                "path": _repo_relative(path, root),
                "exists": path.is_file(),
                "quality": {
                    "passed": bool(quality.get("passed")),
                    "word_count": quality.get("word_count"),
                    "citation_count": quality.get("citation_count"),
                    "evidence_coverage": quality.get("evidence_coverage"),
                    "unsupported_claims": quality.get("unsupported_claims") or [],
                    "performance_claim_violations": quality.get("performance_claim_violations")
                    or [],
                    "reasons": quality.get("reasons") or [],
                },
                "caption_candidates": _read_rendering_text(path),
            }
        )
    return records, paths


def _facts_summary(report: dict[str, Any]) -> dict[str, Any]:
    facts = report.get("facts") if isinstance(report.get("facts"), dict) else {}
    forecasts = facts.get("forecasts") if isinstance(facts.get("forecasts"), list) else []
    symbols = sorted(
        {
            str(item.get("symbol"))
            for item in forecasts
            if isinstance(item, dict) and item.get("symbol")
        }
    )
    data_sources = facts.get("data_sources") or report.get("data_sources") or []
    if not isinstance(data_sources, list):
        data_sources = []
    return {
        "forecast_count": len(forecasts),
        "symbols": symbols,
        "data_sources": data_sources,
    }


def _public_claim_constraints(renderings: list[dict[str, Any]]) -> list[str]:
    constraints = [
        "Use only facts present in the source draft or rendered platform artifacts.",
        "Do not add live market prices, performance claims, or sourced claims that are not in the inputs.",
        "Preserve the informational-only and not-investment-advice posture for market content.",
    ]
    if any(
        not item["quality"]["passed"]
        or item["quality"]["unsupported_claims"]
        or item["quality"]["performance_claim_violations"]
        for item in renderings
    ):
        constraints.append(
            "Treat this as internal-only until unsupported claims and quality failures are resolved."
        )
    return constraints


def _visual_style(kind: str) -> dict[str, Any]:
    palette = {
        "weekly_crypto_brief": ["deep graphite", "electric cyan", "signal green"],
        "market_pulse": ["charcoal", "amber", "cool white"],
        "security_digest": ["near black", "warning red", "steel blue"],
        "ai_intel": ["ink", "violet", "soft white"],
    }.get(_slug(kind), ["graphite", "cyan", "white"])
    return {
        "palette": palette,
        "avoid": ["fake charts", "made-up logos", "unverified numbers"],
        "composition": "clean operational briefing, legible overlays, source-grounded visuals",
    }


def _deliverables(
    *,
    title: str,
    kind: str,
    summary: dict[str, Any],
    renderings: list[dict[str, Any]],
) -> dict[str, Any]:
    captions = [
        text for rendering in renderings for text in rendering.get("caption_candidates", [])[:2]
    ]
    primary_caption = captions[0] if captions else title
    symbols = ", ".join(summary["symbols"]) if summary["symbols"] else "Sapphire"
    return {
        "image_card": {
            "format": "square 1:1 and vertical 9:16 variants",
            "headline": title,
            "overlay_text": [title, symbols],
            "alt_text": f"Operational media card for {title}",
            "style": _visual_style(kind),
        },
        "short_video": {
            "duration_seconds": 30,
            "storyboard": [
                {
                    "scene": 1,
                    "seconds": "0-6",
                    "brief": f"Open with {title} and the current Sapphire data context.",
                },
                {
                    "scene": 2,
                    "seconds": "6-20",
                    "brief": primary_caption,
                },
                {
                    "scene": 3,
                    "seconds": "20-30",
                    "brief": "Close on source list and informational-only disclaimer.",
                },
            ],
        },
        "voiceover": {
            "tone": "calm operator briefing",
            "script": primary_caption,
            "max_seconds": 30,
        },
        "captions": captions[:6],
    }


def build_work_order(
    draft_path: Path | str,
    *,
    root: Path = REPO_ROOT,
    manifest_root: Path = DEFAULT_MANIFEST_ROOT,
    created_at: datetime | None = None,
) -> dict[str, Any]:
    """Build a deterministic work-order dict for one draft manifest."""
    created_at = created_at or _utcnow()
    draft_path = Path(draft_path)
    draft = load_draft_manifest(draft_path)
    report = draft.get("report") if isinstance(draft.get("report"), dict) else {}
    kind = str(report.get("kind") or draft_path.stem.split("_", 2)[-1] or "content")
    title = str(report.get("title") or draft_path.stem)
    renderings, rendering_paths = _rendering_records(draft, root=root)
    summary = _facts_summary(report)
    slug = draft_path.stem
    run_id = make_run_id("media_work_order", slug, when=created_at)
    manifest_path = manifest_root / f"{run_id}.json"
    source_paths = [draft_path, *rendering_paths]
    return {
        "schema_version": SCHEMA_VERSION,
        "work_order_id": run_id,
        "created_at": created_at.isoformat().replace("+00:00", "Z"),
        "dry_run": True,
        "approval_status": "pending",
        "source_draft": _repo_relative(draft_path, root),
        "provenance_manifest_path": _repo_relative(manifest_path, root),
        "report": {
            "kind": kind,
            "title": title,
            "published_at": draft.get("published_at"),
            "generated_at": report.get("generated_at"),
            "summary": summary,
        },
        "source_paths": [_repo_relative(path, root) for path in source_paths if path.is_file()],
        "renderings": renderings,
        "constraints": _public_claim_constraints(renderings),
        "deliverables": _deliverables(
            title=title,
            kind=kind,
            summary=summary,
            renderings=renderings,
        ),
    }


def write_work_order(
    draft_path: Path | str,
    *,
    root: Path = REPO_ROOT,
    output_root: Path = DEFAULT_WORK_ORDER_ROOT,
    manifest_root: Path = DEFAULT_MANIFEST_ROOT,
    created_at: datetime | None = None,
) -> dict[str, Any]:
    """Write a work-order JSON file and a media provenance manifest."""
    created_at = created_at or _utcnow()
    draft_path = Path(draft_path)
    work_order = build_work_order(
        draft_path,
        root=root,
        manifest_root=manifest_root,
        created_at=created_at,
    )
    output_root.mkdir(parents=True, exist_ok=True)
    output_path = output_root / f"{work_order['work_order_id']}.json"
    work_order["work_order_path"] = _repo_relative(output_path, root)
    output_path.write_text(json.dumps(work_order, indent=2, sort_keys=True) + "\n")

    input_paths = [root / item for item in work_order["source_paths"]]
    manifest = write_manifest(
        kind="media_work_order",
        slug=draft_path.stem,
        media_kind="work_order",
        inputs=input_paths,
        outputs=[output_path],
        root=root,
        manifest_root=manifest_root,
        dry_run=True,
        approval_status="pending",
        metadata={
            "report_kind": work_order["report"]["kind"],
            "source_draft": work_order["source_draft"],
            "work_order_id": work_order["work_order_id"],
        },
        created_at=created_at,
    )
    return {
        "work_order": work_order,
        "manifest": manifest,
        "path": output_path,
    }


def generate_work_orders(
    *,
    content_root: Path | str = DEFAULT_CONTENT_ROOT,
    root: Path = REPO_ROOT,
    output_root: Path = DEFAULT_WORK_ORDER_ROOT,
    manifest_root: Path = DEFAULT_MANIFEST_ROOT,
    kinds: list[str] | tuple[str, ...] | None = None,
    latest: bool = False,
    limit: int | None = None,
    created_at: datetime | None = None,
) -> list[dict[str, Any]]:
    """Discover selected drafts and write work orders for them."""
    selected = discover_drafts(content_root, kinds=kinds, latest=latest, limit=limit)
    return [
        write_work_order(
            path,
            root=root,
            output_root=output_root,
            manifest_root=manifest_root,
            created_at=created_at,
        )
        for path in selected
    ]
