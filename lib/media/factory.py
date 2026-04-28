"""Dry-run media factory for local readiness artifacts.

This module consumes media work orders and materializes local image, audio, and
video readiness files. It never calls image, audio, video, Telegram, publishing,
or live market APIs.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .artifacts import REPO_ROOT, artifact_record, write_manifest
from .work_orders import (
    DEFAULT_WORK_ORDER_ROOT,
)
from .work_orders import (
    SCHEMA_VERSION as WORK_ORDER_SCHEMA_VERSION,
)

SCHEMA_VERSION = 1
DEFAULT_RUN_ROOT = REPO_ROOT / "data" / "media" / "runs"
MEDIA_KINDS = ("image", "audio", "video")
FACTORY_NAME = "local_dry_run_media_factory"

_WORK_ORDER_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")
_BLOCKED_TRUE_FLAGS = {
    "allow_live_calls",
    "api_calls_enabled",
    "audio_api_enabled",
    "live",
    "live_mode",
    "live_run",
    "publish",
    "publish_enabled",
    "publishing_enabled",
    "send_telegram",
    "telegram",
    "telegram_enabled",
    "video_api_enabled",
    "image_api_enabled",
}
_LIVE_STRING_FIELDS = {"execution_mode", "mode", "publish_mode", "run_mode"}
_LIVE_STRING_VALUES = {"live", "production", "publish", "send"}


@dataclass
class MediaFactorySafetyError(ValueError):
    """Raised when a work order would violate dry-run factory safety rules."""

    validation: dict[str, Any]
    work_order_path: Path | None = None

    def __post_init__(self) -> None:
        ValueError.__init__(self, "media work order failed dry-run safety validation")


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _iso(when: datetime) -> str:
    return when.isoformat().replace("+00:00", "Z")


def _repo_relative(path: Path, root: Path) -> str:
    try:
        return str(path.resolve().relative_to(root.resolve()))
    except ValueError:
        return str(path)


def _rooted(path: str | Path, root: Path) -> Path:
    candidate = Path(path)
    if candidate.is_absolute():
        return candidate
    return root / candidate


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _load_json_object(path: Path | str, *, label: str) -> dict[str, Any]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{label} must contain a JSON object")
    return data


def _issue(field: str, message: str) -> dict[str, str]:
    return {"field": field, "message": message}


def _flag_key(key: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", key.strip().lower()).strip("_")


def _walk_safety_flags(value: Any, *, path: str = "$") -> list[dict[str, str]]:
    issues: list[dict[str, str]] = []
    if isinstance(value, dict):
        for raw_key, child in value.items():
            key = str(raw_key)
            flag = _flag_key(key)
            child_path = f"{path}.{key}"
            if flag in _BLOCKED_TRUE_FLAGS and child is True:
                issues.append(
                    _issue(child_path, "live, publishing, or Telegram flag must be false")
                )
            if flag == "dry_run" and child is False and child_path != "$.dry_run":
                issues.append(_issue(child_path, "dry_run must remain true for media factory runs"))
            if (
                flag in _LIVE_STRING_FIELDS
                and isinstance(child, str)
                and child.strip().lower() in _LIVE_STRING_VALUES
            ):
                issues.append(_issue(child_path, "live execution modes are not allowed"))
            issues.extend(_walk_safety_flags(child, path=child_path))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            issues.extend(_walk_safety_flags(child, path=f"{path}[{index}]"))
    return issues


def load_work_order(path: Path | str) -> dict[str, Any]:
    """Load a media work-order JSON file."""
    return _load_json_object(path, label="work order")


def discover_work_orders(
    work_order_root: Path | str = DEFAULT_WORK_ORDER_ROOT,
    *,
    limit: int | None = None,
) -> list[Path]:
    """Return existing media work-order files, newest name first."""
    work_order_root = Path(work_order_root)
    if not work_order_root.is_dir():
        return []
    paths = sorted(work_order_root.glob("*.json"), reverse=True)
    if limit is not None:
        paths = paths[: max(0, limit)]
    return paths


def _source_path_errors(work_order: dict[str, Any], *, root: Path) -> list[dict[str, str]]:
    errors: list[dict[str, str]] = []
    source_draft = work_order.get("source_draft")
    if not isinstance(source_draft, str) or not source_draft.strip():
        errors.append(_issue("$.source_draft", "source_draft is required"))
    elif not _rooted(source_draft, root).is_file():
        errors.append(_issue("$.source_draft", "source draft does not exist"))

    source_paths = work_order.get("source_paths")
    if not isinstance(source_paths, list):
        return [*errors, _issue("$.source_paths", "source_paths must be a list")]

    for index, source_path in enumerate(source_paths):
        field = f"$.source_paths[{index}]"
        if not isinstance(source_path, str) or not source_path.strip():
            errors.append(_issue(field, "source path must be a non-empty string"))
            continue
        if not _rooted(source_path, root).is_file():
            errors.append(_issue(field, "source path does not exist"))
    return errors


def _deliverable_errors(work_order: dict[str, Any]) -> list[dict[str, str]]:
    deliverables = work_order.get("deliverables")
    if not isinstance(deliverables, dict):
        return [_issue("$.deliverables", "deliverables must be a JSON object")]

    errors: list[dict[str, str]] = []
    required = {
        "image_card": "$.deliverables.image_card",
        "short_video": "$.deliverables.short_video",
        "voiceover": "$.deliverables.voiceover",
    }
    for key, field in required.items():
        if not isinstance(deliverables.get(key), dict):
            errors.append(_issue(field, "required media deliverable is missing"))
    return errors


def _rendering_warnings(work_order: dict[str, Any]) -> list[dict[str, str]]:
    renderings = work_order.get("renderings")
    if not isinstance(renderings, list):
        return []

    warnings: list[dict[str, str]] = []
    for index, rendering in enumerate(renderings):
        if not isinstance(rendering, dict):
            continue
        quality = rendering.get("quality") if isinstance(rendering.get("quality"), dict) else {}
        if rendering.get("exists") is False:
            warnings.append(_issue(f"$.renderings[{index}].exists", "rendering file was missing"))
        if quality and quality.get("passed") is False:
            warnings.append(
                _issue(f"$.renderings[{index}].quality", "rendering quality did not pass")
            )
    return warnings


def validate_work_order(
    work_order: dict[str, Any],
    *,
    root: Path = REPO_ROOT,
    checked_at: datetime | None = None,
) -> dict[str, Any]:
    """Validate that a work order is safe for local dry-run readiness output."""
    checked_at = checked_at or _utcnow()
    errors: list[dict[str, str]] = []
    warnings: list[dict[str, str]] = []

    if work_order.get("schema_version") != WORK_ORDER_SCHEMA_VERSION:
        errors.append(_issue("$.schema_version", "unsupported work-order schema version"))

    work_order_id = work_order.get("work_order_id")
    if not isinstance(work_order_id, str) or not work_order_id.strip():
        errors.append(_issue("$.work_order_id", "work_order_id is required"))
    elif not _WORK_ORDER_ID_RE.fullmatch(work_order_id):
        errors.append(_issue("$.work_order_id", "work_order_id must be a safe directory name"))

    if work_order.get("dry_run") is not True:
        errors.append(_issue("$.dry_run", "work order must be dry_run=true"))

    if work_order.get("approval_status") != "pending":
        errors.append(_issue("$.approval_status", "approval_status must remain pending"))

    errors.extend(_source_path_errors(work_order, root=root))
    errors.extend(_deliverable_errors(work_order))
    errors.extend(_walk_safety_flags(work_order))
    warnings.extend(_rendering_warnings(work_order))

    return {
        "ok": not errors,
        "checked_at": _iso(checked_at),
        "errors": errors,
        "warnings": warnings,
    }


def _base_readiness(
    *,
    work_order: dict[str, Any],
    media_kind: str,
    created_at: datetime,
    source_work_order: str,
) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "work_order_id": work_order["work_order_id"],
        "media_kind": media_kind,
        "status": "ready",
        "dry_run": True,
        "approval_status": "pending",
        "live_calls_allowed": False,
        "api_calls_made": False,
        "telegram_sends_made": False,
        "publish_actions_made": False,
        "created_at": _iso(created_at),
        "generator": FACTORY_NAME,
        "source_work_order": source_work_order,
    }


def _image_readiness(
    work_order: dict[str, Any],
    *,
    created_at: datetime,
    source_work_order: str,
) -> tuple[dict[str, Any], str]:
    deliverable = work_order["deliverables"]["image_card"]
    headline = str(deliverable.get("headline") or work_order["report"]["title"])
    overlay_text = [
        str(item)
        for item in deliverable.get("overlay_text", [])
        if isinstance(item, str) and item.strip()
    ]
    prompt = {
        "headline": headline,
        "overlay_text": overlay_text,
        "alt_text": str(deliverable.get("alt_text") or headline),
        "format": deliverable.get("format"),
        "style": deliverable.get("style") if isinstance(deliverable.get("style"), dict) else {},
    }
    readiness = {
        **_base_readiness(
            work_order=work_order,
            media_kind="image",
            created_at=created_at,
            source_work_order=source_work_order,
        ),
        "deliverable_key": "image_card",
        "prompt": prompt,
        "next_step": "Manual review before any image generation API is enabled.",
    }
    prompt_lines = [
        "# Image Readiness",
        "",
        f"Headline: {prompt['headline']}",
        f"Alt text: {prompt['alt_text']}",
        f"Format: {prompt['format']}",
        "",
        "Overlay text:",
        *[f"- {item}" for item in overlay_text],
        "",
        "Style:",
        json.dumps(prompt["style"], indent=2, sort_keys=True),
        "",
        "Safety: dry-run only; no image API call was made.",
    ]
    return readiness, "\n".join(prompt_lines) + "\n"


def _audio_readiness(
    work_order: dict[str, Any],
    *,
    created_at: datetime,
    source_work_order: str,
) -> tuple[dict[str, Any], str]:
    deliverable = work_order["deliverables"]["voiceover"]
    script = str(deliverable.get("script") or work_order["report"]["title"])
    readiness = {
        **_base_readiness(
            work_order=work_order,
            media_kind="audio",
            created_at=created_at,
            source_work_order=source_work_order,
        ),
        "deliverable_key": "voiceover",
        "tone": deliverable.get("tone"),
        "max_seconds": deliverable.get("max_seconds"),
        "script": script,
        "next_step": "Manual review before any speech generation API is enabled.",
    }
    return readiness, script.strip() + "\n"


def _video_readiness(
    work_order: dict[str, Any],
    *,
    created_at: datetime,
    source_work_order: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    deliverable = work_order["deliverables"]["short_video"]
    storyboard = deliverable.get("storyboard")
    if not isinstance(storyboard, list):
        storyboard = []
    readiness = {
        **_base_readiness(
            work_order=work_order,
            media_kind="video",
            created_at=created_at,
            source_work_order=source_work_order,
        ),
        "deliverable_key": "short_video",
        "duration_seconds": deliverable.get("duration_seconds"),
        "storyboard": storyboard,
        "next_step": "Manual review before any video generation API is enabled.",
    }
    storyboard_artifact = {
        "schema_version": SCHEMA_VERSION,
        "work_order_id": work_order["work_order_id"],
        "media_kind": "video",
        "duration_seconds": deliverable.get("duration_seconds"),
        "storyboard": storyboard,
        "dry_run": True,
        "api_calls_made": False,
    }
    return readiness, storyboard_artifact


def _manifest_inputs(
    work_order: dict[str, Any], work_order_path: Path, *, root: Path
) -> list[Path]:
    paths: list[Path] = [work_order_path]
    seen = {work_order_path.resolve()}
    for source_path in [work_order.get("source_draft"), *work_order.get("source_paths", [])]:
        if not isinstance(source_path, str) or not source_path.strip():
            continue
        path = _rooted(source_path, root)
        resolved = path.resolve()
        if path.is_file() and resolved not in seen:
            paths.append(path)
            seen.add(resolved)
    return paths


def _output_record(path: Path, *, root: Path, media_kind: str) -> dict[str, Any]:
    return artifact_record(path, root=root, role="output", media_kind=media_kind)


def run_media_factory(
    work_order_path: Path | str,
    *,
    root: Path = REPO_ROOT,
    run_root: Path = DEFAULT_RUN_ROOT,
    created_at: datetime | None = None,
) -> dict[str, Any]:
    """Materialize dry-run readiness artifacts for one existing work order."""
    created_at = created_at or _utcnow()
    work_order_path = Path(work_order_path)
    work_order = load_work_order(work_order_path)
    validation = validate_work_order(work_order, root=root, checked_at=created_at)
    if not validation["ok"]:
        raise MediaFactorySafetyError(validation=validation, work_order_path=work_order_path)

    work_order_id = work_order["work_order_id"]
    run_dir = Path(run_root) / work_order_id
    source_work_order = _repo_relative(work_order_path, root)

    image_readiness, image_prompt = _image_readiness(
        work_order,
        created_at=created_at,
        source_work_order=source_work_order,
    )
    audio_readiness, audio_script = _audio_readiness(
        work_order,
        created_at=created_at,
        source_work_order=source_work_order,
    )
    video_readiness, storyboard = _video_readiness(
        work_order,
        created_at=created_at,
        source_work_order=source_work_order,
    )

    image_dir = run_dir / "image"
    audio_dir = run_dir / "audio"
    video_dir = run_dir / "video"
    image_readiness_path = image_dir / "readiness.json"
    image_prompt_path = image_dir / "prompt.md"
    audio_readiness_path = audio_dir / "readiness.json"
    audio_script_path = audio_dir / "script.txt"
    video_readiness_path = video_dir / "readiness.json"
    storyboard_path = video_dir / "storyboard.json"

    _write_json(image_readiness_path, image_readiness)
    image_prompt_path.write_text(image_prompt, encoding="utf-8")
    _write_json(audio_readiness_path, audio_readiness)
    audio_script_path.write_text(audio_script, encoding="utf-8")
    _write_json(video_readiness_path, video_readiness)
    _write_json(storyboard_path, storyboard)

    outputs = [
        (image_readiness_path, "image"),
        (image_prompt_path, "image"),
        (audio_readiness_path, "audio"),
        (audio_script_path, "audio"),
        (video_readiness_path, "video"),
        (storyboard_path, "video"),
    ]
    manifest = write_manifest(
        kind="media_factory_run",
        slug=work_order_id,
        media_kind="readiness",
        inputs=_manifest_inputs(work_order, work_order_path, root=root),
        outputs=[path for path, _media_kind in outputs],
        root=root,
        manifest_root=run_dir,
        dry_run=True,
        approval_status="pending",
        metadata={
            "factory": FACTORY_NAME,
            "work_order_id": work_order_id,
            "source_work_order": source_work_order,
        },
        created_at=created_at,
    )
    output_records = [
        _output_record(path, root=root, media_kind=media_kind) for path, media_kind in outputs
    ]
    summary_path = run_dir / "factory_run.json"
    summary = {
        "schema_version": SCHEMA_VERSION,
        "work_order_id": work_order_id,
        "status": "ready",
        "dry_run": True,
        "approval_status": "pending",
        "live_calls_allowed": False,
        "api_calls_made": False,
        "telegram_sends_made": False,
        "publish_actions_made": False,
        "created_at": _iso(created_at),
        "factory": FACTORY_NAME,
        "run_dir": _repo_relative(run_dir, root),
        "factory_run_path": _repo_relative(summary_path, root),
        "source_work_order": source_work_order,
        "manifest_path": manifest["manifest_path"],
        "validation": validation,
        "readiness": {
            "image": _repo_relative(image_readiness_path, root),
            "audio": _repo_relative(audio_readiness_path, root),
            "video": _repo_relative(video_readiness_path, root),
        },
        "outputs": output_records,
    }
    _write_json(summary_path, summary)
    return summary


def _run_summary(path: Path, summary: dict[str, Any], *, root: Path) -> dict[str, Any]:
    outputs = summary.get("outputs") if isinstance(summary.get("outputs"), list) else []
    return {
        "work_order_id": summary.get("work_order_id"),
        "status": summary.get("status"),
        "dry_run": summary.get("dry_run"),
        "approval_status": summary.get("approval_status"),
        "live_calls_allowed": summary.get("live_calls_allowed"),
        "api_calls_made": summary.get("api_calls_made"),
        "telegram_sends_made": summary.get("telegram_sends_made"),
        "publish_actions_made": summary.get("publish_actions_made"),
        "created_at": summary.get("created_at"),
        "run_dir": summary.get("run_dir"),
        "factory_run_path": summary.get("factory_run_path") or _repo_relative(path, root),
        "manifest_path": summary.get("manifest_path"),
        "output_count": len(outputs),
        "media_kinds": sorted(
            {
                str(item.get("media_kind"))
                for item in outputs
                if isinstance(item, dict) and item.get("media_kind") in MEDIA_KINDS
            }
        ),
    }


def media_factory_status(
    *,
    run_root: Path = DEFAULT_RUN_ROOT,
    root: Path = REPO_ROOT,
    work_order_id: str | None = None,
) -> dict[str, Any]:
    """Read local media factory run summaries."""
    run_root = Path(run_root)
    if work_order_id:
        summary_paths = [run_root / work_order_id / "factory_run.json"]
    elif run_root.is_dir():
        summary_paths = sorted(run_root.glob("*/factory_run.json"), reverse=True)
    else:
        summary_paths = []

    runs: list[dict[str, Any]] = []
    missing: list[str] = []
    for summary_path in summary_paths:
        if not summary_path.is_file():
            missing.append(_repo_relative(summary_path, root))
            continue
        summary = _load_json_object(summary_path, label="factory run")
        runs.append(_run_summary(summary_path, summary, root=root))

    return {
        "schema_version": SCHEMA_VERSION,
        "run_root": _repo_relative(run_root, root),
        "count": len(runs),
        "runs": runs,
        "missing": missing,
    }
