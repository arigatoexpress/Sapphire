from __future__ import annotations

import json
import logging
import os
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

BOARD_STATUSES = ("backlog", "in_progress", "blocked", "done")
BOARD_PRIORITIES = ("low", "medium", "high", "urgent")
_OVERVIEW_CACHE: dict[str, Any] = {"ts": 0.0, "payload": None}
_OVERVIEW_TTL_SECONDS = 45.0
_GH_VIEW_CACHE: dict[str, dict[str, Any]] = {}
_FOCUS_CARD_IDS = {
    "card-validate-legacy-diffs",
    "card-openclaw-governor-connector",
    "card-worker-daemon-multi-device",
}

logger = logging.getLogger(__name__)


def _now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


def _verbose_logging_enabled() -> bool:
    return str(os.getenv("AGENTIC_VERBOSE_LOGGING", "")).strip().lower() in {"1", "true", "yes", "on"}


def _board_log(event_type: str, payload: dict[str, Any]) -> None:
    if not _verbose_logging_enabled():
        return
    try:
        compact = json.dumps(payload, separators=(",", ":"), ensure_ascii=True, default=str)
    except Exception:
        compact = str(payload)
    logger.info("[project_board] %s %s", event_type, compact)


def _is_cloud_runtime() -> bool:
    return bool(os.getenv("K_SERVICE", "").strip() or os.getenv("K_REVISION", "").strip())


def _path_should_skip_local_check(path_text: str) -> bool:
    text = str(path_text or "").strip()
    if not text:
        return False
    normalized = Path(text).expanduser().as_posix()
    if normalized.startswith("/Users/"):
        return True
    if normalized.startswith("/Volumes/"):
        return True
    if normalized.lower().startswith("c:/") or normalized.lower().startswith("d:/"):
        return True
    return False


def _safe_run(command: list[str], timeout_seconds: int = 7) -> str:
    try:
        result = subprocess.run(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            check=True,
            text=True,
            timeout=timeout_seconds,
        )
    except Exception:
        return ""
    return result.stdout.strip()


def _parse_size_bytes(size_text: str) -> int:
    if not size_text:
        return 0
    try:
        if size_text.endswith("K"):
            return int(float(size_text[:-1]) * 1024)
        if size_text.endswith("M"):
            return int(float(size_text[:-1]) * 1024 * 1024)
        if size_text.endswith("G"):
            return int(float(size_text[:-1]) * 1024 * 1024 * 1024)
        if size_text.endswith("T"):
            return int(float(size_text[:-1]) * 1024 * 1024 * 1024 * 1024)
        return int(float(size_text))
    except (ValueError, TypeError):
        return 0


def _human_size(num_bytes: int) -> str:
    units = ["B", "KB", "MB", "GB", "TB"]
    value = float(max(0, num_bytes))
    idx = 0
    while value >= 1024 and idx < len(units) - 1:
        value /= 1024.0
        idx += 1
    if idx == 0:
        return f"{int(value)}{units[idx]}"
    return f"{value:.1f}{units[idx]}"


def _board_file_path() -> Path:
    env_override = os.getenv("AGENTIC_BOARD_PATH", "").strip()
    if env_override:
        return Path(env_override)
    return Path(__file__).resolve().parent / "data" / "agentic_board.json"


def _snapshot_file_path() -> Path:
    env_override = os.getenv("AGENTIC_BOARD_SNAPSHOT_PATH", "").strip()
    if env_override:
        return Path(env_override)
    return Path(__file__).resolve().parent / "data" / "agentic_board_snapshot.json"


def _next_actions_file_path() -> Path:
    env_override = os.getenv("AGENTIC_NEXT_ACTIONS_PATH", "").strip()
    if env_override:
        return Path(env_override)
    return Path(__file__).resolve().parent / "data" / "agentic_next_actions.md"


def _roadmap_snapshot_file_path() -> Path:
    env_override = os.getenv("AGENTIC_ROADMAP_SNAPSHOT_PATH", "").strip()
    if env_override:
        return Path(env_override)
    return Path(__file__).resolve().parent / "data" / "agentic_roadmap_snapshot.json"


def _roadmap_markdown_file_path() -> Path:
    env_override = os.getenv("AGENTIC_ROADMAP_MARKDOWN_PATH", "").strip()
    if env_override:
        return Path(env_override)
    return Path(__file__).resolve().parent / "data" / "agentic_roadmap_snapshot.md"


def _tracked_projects_file_path() -> Path:
    env_override = os.getenv("AGENTIC_TRACKED_PROJECTS_PATH", "").strip()
    if env_override:
        return Path(env_override)
    return Path(__file__).resolve().parent / "data" / "tracked_projects.json"


def _canonical_github_root() -> Path:
    path = os.getenv("PROJECTS_CANONICAL_GITHUB_ROOT", "").strip()
    if path:
        return Path(path)
    return Path("/Users/aribs/Documents/Organized/Codex Projects/github")


def _projects_root() -> Path:
    path = os.getenv("PROJECTS_ROOT", "").strip()
    if path:
        return Path(path)
    return Path("/Users/aribs/Documents/Projects")


def _archives_root() -> Path:
    path = os.getenv("PROJECTS_ARCHIVE_ROOT", "").strip()
    if path:
        return Path(path)
    return Path("/Users/aribs/Documents/Organized/Archives")


def _default_board_cards() -> list[dict[str, Any]]:
    stamp = _now_iso()
    return [
        {
            "id": "card-consolidation-complete",
            "title": "Consolidate deprecated repos into dated archive",
            "project": "Workspace Consolidation",
            "status": "done",
            "priority": "high",
            "owner": "Codex",
            "notes": "Completed prune run and generated cleanup manifest.",
            "updated_at": stamp,
        },
        {
            "id": "card-validate-legacy-diffs",
            "title": "Review archived dirty clones for salvage commits",
            "project": "Workspace Consolidation",
            "status": "in_progress",
            "priority": "high",
            "owner": "Aribs",
            "notes": "Dirty branches were archived to preserve local work; cherry-pick anything important.",
            "updated_at": stamp,
        },
        {
            "id": "card-weekly-prune",
            "title": "Run weekly stale-asset prune",
            "project": "Ops Hygiene",
            "status": "backlog",
            "priority": "medium",
            "owner": "Codex",
            "notes": "Focus on browser recordings and superseded extension versions.",
            "updated_at": stamp,
        },
        {
            "id": "card-github-triage",
            "title": "Triage active GitHub repos into Keep/Merge/Archive",
            "project": "GitHub Portfolio",
            "status": "backlog",
            "priority": "high",
            "owner": "Aribs",
            "notes": "Use repo-level objectives and commit velocity to reduce portfolio sprawl.",
            "updated_at": stamp,
        },
        {
            "id": "card-automation",
            "title": "Automate board sync from repo telemetry",
            "project": "Agentic PM",
            "status": "done",
            "priority": "medium",
            "owner": "Codex",
            "notes": "Implemented sync engine, next-actions artifacts, and /api/projects/sync endpoint.",
            "updated_at": stamp,
        },
    ]


def _default_tracked_projects() -> dict[str, Any]:
    return {
        "version": 1,
        "updated_at": _now_iso(),
        "projects": [
            {
                "id": "ai-project-management-system",
                "name": "AI Project Management System",
                "slug": "ai-project-management-system",
                "canonical_local_path": "/Users/aribs/Documents/Organized/Codex Projects",
                "local_paths": [
                    "/Users/aribs/Documents/Organized/Codex Projects",
                ],
                "github_urls": [
                    "https://github.com/arigatoexpress/agentic-project-manager-hub",
                ],
                "notes": "Primary command deck, control plane, and Asana-style dashboard workspace.",
            },
            {
                "id": "tho-project-go-forward",
                "name": "THO (Project Go Forward)",
                "slug": "tho-project-go-forward",
                "canonical_local_path": "/Users/aribs/Documents/Organized/Codex Projects/github/Project-Go-Forward",
                "local_paths": [
                    "/Users/aribs/Documents/Organized/Codex Projects/github/Project-Go-Forward",
                    "/Users/aribs/Documents/Business/Kadima Digital Strategies 2026/THO_MASTER/project-go-forward",
                ],
                "github_urls": [
                    "https://github.com/arigatoexpress/Project-Go-Forward",
                ],
                "notes": "Legacy business clone contains unmerged local changes and should be merged before archival.",
            },
            {
                "id": "blanga-intelligence-system",
                "name": "Blanga Intelligence System",
                "slug": "blanga-intelligence-system",
                "canonical_local_path": "/Users/aribs/Documents/Organized/Codex Projects/blanga-bis-beta",
                "local_paths": [
                    "/Users/aribs/Documents/Organized/Codex Projects/blanga-bis-beta",
                    "/Users/aribs/Documents/Organized/Codex Projects/app/bis",
                ],
                "github_urls": [
                    "https://github.com/arigatoexpress/blanga-bis-beta",
                ],
                "notes": "Standalone BIS beta repo is live on Cloud Run and tracked alongside the embedded module.",
            },
            {
                "id": "sapphire",
                "name": "Sapphire",
                "slug": "sapphire",
                "canonical_local_path": "/Users/aribs/Documents/Organized/Codex Projects/github/Sapphire",
                "local_paths": [
                    "/Users/aribs/Documents/Organized/Codex Projects/github/Sapphire",
                    "/Users/aribs/Documents/Organized/Codex Projects/github/sapphire-control",
                    "/Users/aribs/Documents/Organized/Codex Projects/github/sapphire-inc",
                    "/Users/aribs/AIAster",
                ],
                "github_urls": [
                    "https://github.com/arigatoexpress/Sapphire",
                    "https://github.com/arigatoexpress/sapphire-control",
                    "https://github.com/arigatoexpress/sapphire-inc",
                ],
                "notes": "Includes core trading repo plus control-plane and org-ops companion repos.",
            },
            {
                "id": "blackjackal",
                "name": "Blackjackal",
                "slug": "blackjackal",
                "canonical_local_path": "/Users/aribs/.blackjackal-chrome",
                "local_paths": [
                    "/Users/aribs/.blackjackal-chrome",
                ],
                "github_urls": [
                    "https://github.com/arigatoexpress/blackjackal",
                ],
                "notes": "Tracked project repo created for Blackjackal; local Chrome workspace remains the canonical runtime data source.",
            },
            {
                "id": "crypto-tax-tracker",
                "name": "Crypto Tax Tracker",
                "slug": "crypto-tax-tracker",
                "canonical_local_path": "/Users/aribs/Documents/Projects/Cointracker",
                "local_paths": [
                    "/Users/aribs/Documents/Projects/Cointracker",
                ],
                "github_urls": [
                    "https://github.com/arigatoexpress/crypto-tax-tracker",
                ],
                "notes": "Tracked project repo created for Crypto Tax Tracker; local Cointracker directory remains canonical for active files.",
            },
        ],
    }


def _load_tracked_projects_payload() -> dict[str, Any]:
    path = _tracked_projects_file_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        payload = _default_tracked_projects()
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return payload

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        payload = _default_tracked_projects()
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return payload

    if not isinstance(payload, dict):
        payload = _default_tracked_projects()
    if not isinstance(payload.get("projects"), list):
        payload["projects"] = _default_tracked_projects()["projects"]
    return payload


def _persist_tracked_projects_payload(payload: dict[str, Any]) -> None:
    path = _tracked_projects_file_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _load_board_payload() -> dict[str, Any]:
    path = _board_file_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        payload = {"version": 1, "cards": _default_board_cards()}
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return payload

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        payload = {"version": 1, "cards": _default_board_cards()}
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return payload

    if not isinstance(payload, dict):
        payload = {"version": 1, "cards": _default_board_cards()}
    cards = payload.get("cards")
    if not isinstance(cards, list):
        payload["cards"] = _default_board_cards()
    return payload


def _persist_board_payload(payload: dict[str, Any]) -> None:
    path = _board_file_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def list_cards() -> list[dict[str, Any]]:
    payload = _load_board_payload()
    cards = [card for card in payload.get("cards", []) if isinstance(card, dict)]
    normalized: list[dict[str, Any]] = []
    for card in cards:
        status = str(card.get("status", "backlog"))
        if status not in BOARD_STATUSES:
            status = "backlog"
        priority = str(card.get("priority", "medium"))
        if priority not in BOARD_PRIORITIES:
            priority = "medium"
        normalized.append(
            {
                "id": str(card.get("id") or f"card-{len(normalized) + 1}"),
                "title": str(card.get("title") or "Untitled"),
                "project": str(card.get("project") or "General"),
                "status": status,
                "priority": priority,
                "owner": str(card.get("owner") or ""),
                "notes": str(card.get("notes") or ""),
                "updated_at": str(card.get("updated_at") or _now_iso()),
            }
        )
    focus = [
        {"id": str(card.get("id") or ""), "status": str(card.get("status") or ""), "updated_at": str(card.get("updated_at") or "")}
        for card in normalized
        if str(card.get("id") or "") in _FOCUS_CARD_IDS
    ]
    _board_log(
        "list_cards",
        {
            "card_count": len(normalized),
            "counts": _card_counts(normalized),
            "focus_cards": focus,
        },
    )
    return normalized


def create_card(new_card: dict[str, Any]) -> dict[str, Any]:
    payload = _load_board_payload()
    cards = list_cards()
    title = str(new_card.get("title") or "").strip()
    if not title:
        raise ValueError("title is required")

    status = str(new_card.get("status") or "backlog").strip()
    if status not in BOARD_STATUSES:
        status = "backlog"

    priority = str(new_card.get("priority") or "medium").strip()
    if priority not in BOARD_PRIORITIES:
        priority = "medium"

    card_id = str(new_card.get("id") or "").strip()
    if not card_id:
        ts = int(time.time() * 1000)
        card_id = f"card-{ts}"

    created = {
        "id": card_id,
        "title": title,
        "project": str(new_card.get("project") or "General"),
        "status": status,
        "priority": priority,
        "owner": str(new_card.get("owner") or ""),
        "notes": str(new_card.get("notes") or ""),
        "updated_at": _now_iso(),
    }
    cards.append(created)
    payload["cards"] = cards
    _persist_board_payload(payload)
    _OVERVIEW_CACHE["ts"] = 0.0
    _board_log(
        "create_card",
        {
            "card_id": created.get("id"),
            "title": created.get("title"),
            "status": created.get("status"),
            "priority": created.get("priority"),
            "owner": created.get("owner"),
        },
    )
    return created


def update_card(card_id: str, changes: dict[str, Any]) -> dict[str, Any]:
    payload = _load_board_payload()
    cards = list_cards()
    updated: dict[str, Any] | None = None
    for idx, card in enumerate(cards):
        if card.get("id") != card_id:
            continue
        merged = dict(card)
        for key in ("title", "project", "owner", "notes"):
            if key in changes:
                merged[key] = str(changes.get(key) or "")
        if "status" in changes:
            status = str(changes.get("status") or "").strip()
            if status in BOARD_STATUSES:
                merged["status"] = status
        if "priority" in changes:
            priority = str(changes.get("priority") or "").strip()
            if priority in BOARD_PRIORITIES:
                merged["priority"] = priority
        merged["updated_at"] = _now_iso()
        cards[idx] = merged
        updated = merged
        break

    if updated is None:
        raise KeyError(card_id)

    payload["cards"] = cards
    _persist_board_payload(payload)
    _OVERVIEW_CACHE["ts"] = 0.0
    _board_log(
        "update_card",
        {
            "card_id": card_id,
            "status": updated.get("status"),
            "priority": updated.get("priority"),
            "owner": updated.get("owner"),
            "updated_at": updated.get("updated_at"),
        },
    )
    return updated


def delete_card(card_id: str) -> bool:
    payload = _load_board_payload()
    cards = list_cards()
    kept = [card for card in cards if card.get("id") != card_id]
    if len(kept) == len(cards):
        return False
    payload["cards"] = kept
    _persist_board_payload(payload)
    _OVERVIEW_CACHE["ts"] = 0.0
    _board_log(
        "delete_card",
        {
            "card_id": card_id,
            "remaining_cards": len(kept),
            "counts": _card_counts(kept),
        },
    )
    return True


def _repo_size(path: Path) -> str:
    return _safe_run(["du", "-sh", str(path)]).split("\t", 1)[0].split(" ", 1)[0] or "0B"


def _scan_local_repos() -> list[dict[str, Any]]:
    root = _canonical_github_root()
    if not root.exists():
        return []

    repos: list[dict[str, Any]] = []
    for repo_dir in sorted(root.iterdir()):
        if not repo_dir.is_dir() or not (repo_dir / ".git").exists():
            continue

        branch = _safe_run(["git", "-C", str(repo_dir), "rev-parse", "--abbrev-ref", "HEAD"]) or "unknown"
        last_commit_date = _safe_run(["git", "-C", str(repo_dir), "log", "-1", "--format=%cs"]) or "unknown"
        dirty_output = _safe_run(["git", "-C", str(repo_dir), "status", "--porcelain"], timeout_seconds=10)
        dirty_files = len([line for line in dirty_output.splitlines() if line.strip()])
        remote = _safe_run(["git", "-C", str(repo_dir), "remote", "get-url", "origin"]) or ""

        repos.append(
            {
                "name": repo_dir.name,
                "path": str(repo_dir),
                "branch": branch,
                "last_commit_date": last_commit_date,
                "dirty_files": dirty_files,
                "size": _repo_size(repo_dir),
                "remote": remote,
            }
        )

    return repos


def _scan_github_repos(owner: str = "arigatoexpress") -> dict[str, dict[str, Any]]:
    output = _safe_run(
        [
            "gh",
            "repo",
            "list",
            owner,
            "--limit",
            "200",
            "--json",
            "name,isArchived,isPrivate,isFork,pushedAt,updatedAt,url,description",
        ],
        timeout_seconds=12,
    )
    if not output:
        return {}
    try:
        rows = json.loads(output)
    except json.JSONDecodeError:
        return {}
    if not isinstance(rows, list):
        return {}
    mapped: dict[str, dict[str, Any]] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        name = str(row.get("name") or "").strip()
        if not name:
            continue
        mapped[name] = row
    return mapped


def _github_lookup_available(github_index: dict[str, dict[str, Any]]) -> bool:
    if github_index:
        return True
    status = _safe_run(["gh", "auth", "status", "-h", "github.com"], timeout_seconds=6)
    return bool(status)


def _parse_repo_slug_from_url(url: str) -> tuple[str, str]:
    text = (url or "").strip()
    if not text:
        return "", ""

    if text.startswith("git@"):
        # git@github.com:owner/repo(.git)
        _, _, rhs = text.partition(":")
        slug = rhs.strip().rstrip("/")
    else:
        parsed = urlparse(text)
        slug = parsed.path.strip("/").rstrip("/")

    if slug.endswith(".git"):
        slug = slug[:-4]
    if "/" not in slug:
        return "", ""

    owner, name = slug.split("/", 1)
    return owner.strip(), name.strip()


def _normalize_project_github_urls(urls: list[str]) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for raw in urls:
        text = str(raw or "").strip()
        if not text:
            continue
        owner, name = _parse_repo_slug_from_url(text)
        canonical = f"https://github.com/{owner}/{name}" if owner and name else text
        dedupe_key = canonical.lower()
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        normalized.append(canonical)
    return normalized


def _gh_repo_view(owner: str, name: str) -> dict[str, Any]:
    if not owner or not name:
        return {}
    slug = f"{owner}/{name}".lower()
    cached = _GH_VIEW_CACHE.get(slug)
    if cached is not None:
        return cached

    output = _safe_run(
        [
            "gh",
            "repo",
            "view",
            f"{owner}/{name}",
            "--json",
            "name,isArchived,isPrivate,isFork,pushedAt,updatedAt,url,description",
        ],
        timeout_seconds=8,
    )
    if not output:
        _GH_VIEW_CACHE[slug] = {}
        return {}
    try:
        payload = json.loads(output)
    except json.JSONDecodeError:
        payload = {}
    if not isinstance(payload, dict):
        payload = {}
    _GH_VIEW_CACHE[slug] = payload
    return payload


def _local_path_ref(path_text: str) -> dict[str, Any]:
    path = Path(path_text).expanduser()
    ref: dict[str, Any] = {
        "path": str(path),
        "exists": path.exists(),
        "is_git_repo": False,
        "branch": "",
        "last_commit_date": "",
        "dirty_files": 0,
        "size": "0B",
        "remote": "",
    }
    if not path.exists():
        return ref
    if path.is_dir():
        ref["size"] = _dir_size(path)
    else:
        try:
            ref["size"] = _human_size(path.stat().st_size)
        except OSError:
            ref["size"] = "0B"

    if not path.is_dir() or not (path / ".git").exists():
        return ref

    ref["is_git_repo"] = True
    ref["branch"] = _safe_run(["git", "-C", str(path), "rev-parse", "--abbrev-ref", "HEAD"]) or "unknown"
    ref["last_commit_date"] = _safe_run(["git", "-C", str(path), "log", "-1", "--format=%cs"]) or ""
    dirty_output = _safe_run(["git", "-C", str(path), "status", "--porcelain"], timeout_seconds=10)
    ref["dirty_files"] = len([line for line in dirty_output.splitlines() if line.strip()])
    ref["remote"] = _safe_run(["git", "-C", str(path), "remote", "get-url", "origin"]) or ""
    return ref


def _github_url_ref(url: str, github_index: dict[str, dict[str, Any]], github_index_ci: dict[str, dict[str, Any]]) -> dict[str, Any]:
    owner, name = _parse_repo_slug_from_url(url)
    ref: dict[str, Any] = {
        "url": url,
        "owner": owner,
        "name": name,
        "exists": False,
        "archived": False,
        "private": False,
        "fork": False,
        "pushed_at": "",
        "updated_at": "",
        "description": "",
    }
    if not owner or not name:
        return ref

    gh_row: dict[str, Any] = {}
    if owner.lower() == "arigatoexpress":
        gh_row = github_index.get(name) or github_index_ci.get(name.lower()) or {}
    else:
        gh_row = _gh_repo_view(owner, name)

    if gh_row:
        ref["exists"] = True
        ref["archived"] = bool(gh_row.get("isArchived", False))
        ref["private"] = bool(gh_row.get("isPrivate", False))
        ref["fork"] = bool(gh_row.get("isFork", False))
        ref["pushed_at"] = str(gh_row.get("pushedAt") or "")
        ref["updated_at"] = str(gh_row.get("updatedAt") or "")
        ref["description"] = str(gh_row.get("description") or "")
        ref["url"] = str(gh_row.get("url") or url)

    return ref


def _github_url_unverified_ref(url: str) -> dict[str, Any]:
    owner, name = _parse_repo_slug_from_url(url)
    return {
        "url": url,
        "owner": owner,
        "name": name,
        "exists": False,
        "archived": False,
        "private": False,
        "fork": False,
        "pushed_at": "",
        "updated_at": "",
        "description": "",
    }


def _build_tracked_projects(github_index: dict[str, dict[str, Any]], *, github_lookup_available: bool = True) -> list[dict[str, Any]]:
    payload = _load_tracked_projects_payload()
    raw_rows = payload.get("projects")
    if not isinstance(raw_rows, list):
        return []

    github_index_ci = {str(key).lower(): value for key, value in github_index.items()}
    cloud_runtime = _is_cloud_runtime()
    tracked: list[dict[str, Any]] = []
    for idx, row in enumerate(raw_rows, start=1):
        if not isinstance(row, dict):
            continue

        project_id = str(row.get("id") or f"tracked-{idx}")
        name = str(row.get("name") or project_id)
        slug = str(row.get("slug") or project_id).strip() or project_id
        canonical_local_path = str(row.get("canonical_local_path") or "").strip()

        local_paths: list[str] = []
        if canonical_local_path:
            local_paths.append(canonical_local_path)
        raw_local_paths = row.get("local_paths")
        if isinstance(raw_local_paths, list):
            local_paths.extend([str(item).strip() for item in raw_local_paths if str(item).strip()])
        # Deduplicate while preserving order.
        dedup_local_paths = list(dict.fromkeys(local_paths))
        local_refs = [_local_path_ref(path_text) for path_text in dedup_local_paths]

        canonical_ref = _local_path_ref(canonical_local_path) if canonical_local_path else None
        if canonical_ref and canonical_ref["path"] not in {ref["path"] for ref in local_refs}:
            local_refs.insert(0, canonical_ref)

        github_urls: list[str] = []
        raw_urls = row.get("github_urls")
        if isinstance(raw_urls, list):
            github_urls.extend([str(item).strip() for item in raw_urls if str(item).strip()])
        github_urls = list(dict.fromkeys(github_urls))
        github_required = bool(row.get("github_required", True))
        github_check = "active"
        if not github_required:
            github_check = "not_required"
            if github_lookup_available:
                github_refs = [_github_url_ref(url, github_index, github_index_ci) for url in github_urls]
            else:
                github_refs = [_github_url_unverified_ref(url) for url in github_urls]
            missing_github = False
        elif github_lookup_available:
            github_refs = [_github_url_ref(url, github_index, github_index_ci) for url in github_urls]
            missing_github = len(github_refs) == 0 or not any(bool(ref.get("exists")) for ref in github_refs)
        else:
            github_refs = [_github_url_unverified_ref(url) for url in github_urls]
            if github_urls:
                github_check = "not_applicable"
                missing_github = False
            else:
                missing_github = True

        canonical_exists = bool(canonical_ref and canonical_ref.get("exists"))
        local_path_check = "active"
        missing_local = not canonical_exists
        if cloud_runtime and _path_should_skip_local_check(canonical_local_path):
            # Cloud runtimes cannot resolve host-only absolute paths.
            local_path_check = "not_applicable"
            missing_local = False
        dirty_ref_count = len([ref for ref in local_refs if int(ref.get("dirty_files", 0)) > 0])

        health = "healthy"
        if missing_local:
            health = "missing_local"
        elif missing_github:
            health = "missing_github"
        elif dirty_ref_count > 0:
            health = "attention"

        tracked.append(
            {
                "id": project_id,
                "name": name,
                "slug": slug,
                "notes": str(row.get("notes") or ""),
                "canonical_local_path": canonical_local_path,
                "canonical_exists": canonical_exists,
                "local_path_check": local_path_check,
                "github_required": github_required,
                "github_check": github_check,
                "local_refs": local_refs,
                "github_refs": github_refs,
                "missing_local": missing_local,
                "missing_github": missing_github,
                "dirty_local_ref_count": dirty_ref_count,
                "health": health,
                "updated_at": str(payload.get("updated_at") or _now_iso()),
            }
        )
    return tracked


def set_tracked_project_github_urls(project_id: str, github_urls: list[str]) -> dict[str, Any]:
    normalized_project_id = str(project_id or "").strip()
    if not normalized_project_id:
        raise ValueError("project_id is required")

    normalized_urls = _normalize_project_github_urls(github_urls)
    if not normalized_urls:
        raise ValueError("at least one github URL is required")

    payload = _load_tracked_projects_payload()
    rows = payload.get("projects")
    if not isinstance(rows, list):
        rows = []
        payload["projects"] = rows

    updated_row: dict[str, Any] | None = None
    for row in rows:
        if not isinstance(row, dict):
            continue
        if str(row.get("id") or "").strip() != normalized_project_id:
            continue
        row["github_urls"] = normalized_urls
        updated_row = row
        break

    if updated_row is None:
        raise KeyError(normalized_project_id)

    payload["updated_at"] = _now_iso()
    _persist_tracked_projects_payload(payload)
    _OVERVIEW_CACHE["ts"] = 0.0
    _OVERVIEW_CACHE["payload"] = None
    return updated_row


def _latest_cleanup_manifest() -> tuple[dict[str, Any] | None, str]:
    root = _archives_root()
    if not root.exists():
        return None, ""

    candidates = sorted(root.glob("pruned-*/cleanup_manifest.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not candidates:
        return None, ""

    manifest_path = candidates[0]
    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None, str(manifest_path)
    if not isinstance(payload, dict):
        return None, str(manifest_path)
    return payload, str(manifest_path)


def _manifest_move_entries(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for key in ("moves", "local_moves"):
        rows = manifest.get(key)
        if isinstance(rows, list):
            entries.extend([item for item in rows if isinstance(item, dict)])
    return entries


def _cleanup_summary(manifest: dict[str, Any] | None) -> dict[str, Any]:
    if not manifest:
        return {
            "total_moves": 0,
            "remote_archived_repos": 0,
            "total_size_bytes": 0,
            "total_size": "0B",
            "by_reason": [],
            "recent_moves": [],
        }

    moves = _manifest_move_entries(manifest)
    remote_archived = manifest.get("remote_archived_repos")
    remote_archived_count = len(remote_archived) if isinstance(remote_archived, list) else 0
    by_reason: dict[str, int] = {}
    size_bytes = 0
    for move in moves:
        reason = str(move.get("reason") or "unspecified")
        by_reason[reason] = by_reason.get(reason, 0) + 1
        size_bytes += _parse_size_bytes(str(move.get("size_before") or "0"))

    reason_rows = [{"reason": reason, "count": count} for reason, count in sorted(by_reason.items(), key=lambda item: (-item[1], item[0]))]
    recent_moves = moves[-8:]

    return {
        "total_moves": len(moves),
        "remote_archived_repos": remote_archived_count,
        "total_size_bytes": size_bytes,
        "total_size": _human_size(size_bytes),
        "by_reason": reason_rows,
        "recent_moves": recent_moves,
    }


def _dir_size(path: Path) -> str:
    if not path.exists():
        return "0B"
    output = _safe_run(["du", "-sh", str(path)], timeout_seconds=10)
    if not output:
        return "0B"
    return output.split("\t", 1)[0].split(" ", 1)[0]


def _workspace_sizes() -> list[dict[str, str]]:
    paths = [
        ("Projects Root", _projects_root()),
        ("Canonical GitHub Workspace", _canonical_github_root()),
        ("Claude", Path("/Users/aribs/.claude")),
        ("Kimi", Path("/Users/aribs/.kimi")),
        ("Antigravity", Path("/Users/aribs/.antigravity")),
        ("Gemini Antigravity", Path("/Users/aribs/.gemini/antigravity")),
    ]

    rows: list[dict[str, str]] = []
    for label, path in paths:
        rows.append({"label": label, "path": str(path), "size": _dir_size(path)})
    return rows


def _card_counts(cards: list[dict[str, Any]]) -> dict[str, int]:
    counts = {status: 0 for status in BOARD_STATUSES}
    for card in cards:
        status = str(card.get("status") or "backlog")
        if status in counts:
            counts[status] += 1
    return counts


def _derive_next_actions(
    cards: list[dict[str, Any]],
    repos: list[dict[str, Any]],
    cleanup: dict[str, Any],
    tracked_projects: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    actions: list[dict[str, Any]] = []

    dirty_repos = sorted(
        [repo for repo in repos if int(repo.get("dirty_files", 0)) > 0],
        key=lambda repo: int(repo.get("dirty_files", 0)),
        reverse=True,
    )
    for repo in dirty_repos[:3]:
        actions.append(
            {
                "id": f"repo-clean-{repo.get('name', 'unknown')}",
                "priority": "high",
                "category": "repo_hygiene",
                "title": f"Clean local changes in {repo.get('name')}",
                "detail": f"{repo.get('dirty_files')} dirty file(s) on branch {repo.get('branch')}.",
                "target": repo.get("path", ""),
            }
        )

    blocked_cards = [card for card in cards if card.get("status") == "blocked"]
    for card in blocked_cards[:3]:
        actions.append(
            {
                "id": f"unblock-{card.get('id', 'card')}",
                "priority": "high",
                "category": "board_unblock",
                "title": f"Unblock: {card.get('title')}",
                "detail": card.get("notes", "") or "Blocked card requires owner decision.",
                "target": card.get("id", ""),
            }
        )

    backlog_priority_cards = [
        card
        for card in cards
        if card.get("status") == "backlog" and card.get("priority") in {"high", "urgent"}
    ]
    for card in backlog_priority_cards[:3]:
        actions.append(
            {
                "id": f"start-{card.get('id', 'card')}",
                "priority": card.get("priority", "high"),
                "category": "board_start",
                "title": f"Start: {card.get('title')}",
                "detail": f"Project: {card.get('project', 'General')}",
                "target": card.get("id", ""),
            }
        )

    archived_visible = len([repo for repo in repos if repo.get("github_archived")])
    if archived_visible > 0:
        actions.append(
            {
                "id": "archive-verify",
                "priority": "medium",
                "category": "portfolio_hygiene",
                "title": "Verify archived repos are removed from active workspace",
                "detail": f"{archived_visible} archived repos still visible in canonical workspace listing.",
                "target": _canonical_github_root().as_posix(),
            }
        )

    if int(cleanup.get("total_moves", 0)) > 0:
        actions.append(
            {
                "id": "cleanup-review",
                "priority": "medium",
                "category": "cleanup_review",
                "title": "Review latest cleanup manifest and confirm restore safety",
                "detail": f"{cleanup.get('total_moves')} move operations logged in latest prune run.",
                "target": cleanup.get("manifest_path", ""),
            }
        )

    tracked_rows = tracked_projects if isinstance(tracked_projects, list) else []
    for project in tracked_rows:
        if bool(project.get("missing_local")):
            actions.append(
                {
                    "id": f"tracked-local-{project.get('id', 'project')}",
                    "priority": "high",
                    "category": "tracked_project_local",
                    "title": f"Recover missing local path for {project.get('name', 'tracked project')}",
                    "detail": "Canonical local path is missing and should be restored or updated in tracked_projects.json.",
                    "target": project.get("canonical_local_path", ""),
                }
            )

    for project in tracked_rows:
        if bool(project.get("missing_github")) and bool(project.get("github_required", True)):
            actions.append(
                {
                    "id": f"tracked-github-{project.get('id', 'project')}",
                    "priority": "medium",
                    "category": "tracked_project_github",
                    "title": f"Attach GitHub repo for {project.get('name', 'tracked project')}",
                    "detail": "No verified GitHub repo link is registered for this tracked project.",
                    "target": project.get("id", ""),
                }
            )

    for project in tracked_rows:
        refs = project.get("local_refs")
        if not isinstance(refs, list) or len(refs) <= 1:
            continue
        canonical_path = str(project.get("canonical_local_path") or "")
        dirty_noncanonical = [
            ref
            for ref in refs
            if str(ref.get("path") or "") != canonical_path and int(ref.get("dirty_files", 0)) > 0
        ]
        if not dirty_noncanonical:
            continue
        actions.append(
            {
                "id": f"tracked-consolidate-{project.get('id', 'project')}",
                "priority": "high",
                "category": "tracked_project_consolidation",
                "title": f"Consolidate non-canonical changes for {project.get('name', 'tracked project')}",
                "detail": f"{len(dirty_noncanonical)} secondary clone(s) have unmerged local edits.",
                "target": canonical_path or str(dirty_noncanonical[0].get("path") or ""),
            }
        )

    if not actions:
        actions.append(
            {
                "id": "steady-state",
                "priority": "low",
                "category": "maintenance",
                "title": "No urgent actions detected",
                "detail": "Workspace is clean. Keep backlog grooming cadence.",
                "target": "",
            }
        )

    return actions[:8]


def _actions_markdown(actions: list[dict[str, Any]], generated_at: str) -> str:
    lines = [
        "# Agentic Next Actions",
        "",
        f"Generated: {generated_at}",
        "",
    ]
    for idx, action in enumerate(actions, start=1):
        lines.append(f"{idx}. [{action.get('priority', 'medium')}] {action.get('title', 'Untitled action')}")
        detail = str(action.get("detail") or "").strip()
        target = str(action.get("target") or "").strip()
        if detail:
            lines.append(f"   - {detail}")
        if target:
            lines.append(f"   - Target: `{target}`")
    lines.append("")
    return "\n".join(lines)


def _build_roadmap_snapshot(overview: dict[str, Any]) -> dict[str, Any]:
    board = overview.get("board") if isinstance(overview.get("board"), dict) else {}
    cards = board.get("cards") if isinstance(board.get("cards"), list) else []
    counts = board.get("counts") if isinstance(board.get("counts"), dict) else {}
    next_actions = overview.get("next_actions") if isinstance(overview.get("next_actions"), list) else []

    now_items: list[dict[str, Any]] = []
    next_items: list[dict[str, Any]] = []
    later_items: list[dict[str, Any]] = []

    for card in cards:
        if not isinstance(card, dict):
            continue
        status = str(card.get("status") or "")
        priority = str(card.get("priority") or "medium")
        item = {
            "id": str(card.get("id") or ""),
            "title": str(card.get("title") or "Untitled card"),
            "source": "board_card",
            "status": status,
            "priority": priority,
            "target": str(card.get("id") or ""),
        }
        if status in {"blocked", "in_progress"}:
            now_items.append(item)
        elif status == "backlog" and priority in {"urgent", "high"}:
            next_items.append(item)
        elif status == "done":
            later_items.append(item)

    for action in next_actions:
        if not isinstance(action, dict):
            continue
        item = {
            "id": str(action.get("id") or ""),
            "title": str(action.get("title") or "Untitled action"),
            "source": "next_action",
            "status": "",
            "priority": str(action.get("priority") or "medium"),
            "target": str(action.get("target") or ""),
        }
        priority = item["priority"]
        if priority in {"urgent", "high"}:
            now_items.append(item)
        elif priority == "medium":
            next_items.append(item)
        else:
            later_items.append(item)

    # De-duplicate by id/title and keep roadmap concise.
    def _dedupe(items: list[dict[str, Any]], max_items: int) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        seen: set[str] = set()
        for row in items:
            key = f"{row.get('id')}|{row.get('title')}"
            if key in seen:
                continue
            seen.add(key)
            rows.append(row)
            if len(rows) >= max_items:
                break
        return rows

    now_rows = _dedupe(now_items, 6)
    next_rows = _dedupe(next_items, 6)
    later_rows = _dedupe(later_items, 6)

    if not now_rows:
        now_rows = [
            {
                "id": "steady-state",
                "title": "System is stable; monitor and execute scheduled hygiene runs.",
                "source": "system",
                "status": "",
                "priority": "low",
                "target": "",
            }
        ]

    return {
        "generated_at": _now_iso(),
        "runtime_mode": str(overview.get("runtime_mode") or "local"),
        "board_counts": counts,
        "summary": {
            "next_actions_count": len(next_actions),
            "now_count": len(now_rows),
            "next_count": len(next_rows),
            "later_count": len(later_rows),
        },
        "horizons": {
            "now": now_rows,
            "next": next_rows,
            "later": later_rows,
        },
    }


def _roadmap_markdown(snapshot: dict[str, Any]) -> str:
    generated_at = str(snapshot.get("generated_at") or _now_iso())
    runtime_mode = str(snapshot.get("runtime_mode") or "local")
    board_counts = snapshot.get("board_counts") if isinstance(snapshot.get("board_counts"), dict) else {}
    horizons = snapshot.get("horizons") if isinstance(snapshot.get("horizons"), dict) else {}

    lines = [
        "# Agentic Roadmap Snapshot",
        "",
        f"Generated: {generated_at}",
        f"Runtime Mode: {runtime_mode}",
        f"Board Counts: backlog={board_counts.get('backlog', 0)}, in_progress={board_counts.get('in_progress', 0)}, blocked={board_counts.get('blocked', 0)}, done={board_counts.get('done', 0)}",
        "",
    ]

    for section in ("now", "next", "later"):
        rows = horizons.get(section) if isinstance(horizons.get(section), list) else []
        lines.append(f"## {section.title()}")
        if not rows:
            lines.append("- none")
            lines.append("")
            continue
        for row in rows:
            if not isinstance(row, dict):
                continue
            title = str(row.get("title") or "Untitled")
            priority = str(row.get("priority") or "medium")
            source = str(row.get("source") or "system")
            target = str(row.get("target") or "").strip()
            if target:
                lines.append(f"- [{priority}] {title} ({source}) -> `{target}`")
            else:
                lines.append(f"- [{priority}] {title} ({source})")
        lines.append("")

    return "\n".join(lines)


def load_roadmap_snapshot() -> dict[str, Any]:
    path = _roadmap_snapshot_file_path()
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(payload, dict):
        return {}
    return payload


def sync_board_artifacts() -> dict[str, Any]:
    overview = get_projects_overview(force_refresh=True)
    snapshot_path = _snapshot_file_path()
    next_actions_path = _next_actions_file_path()
    roadmap_snapshot_path = _roadmap_snapshot_file_path()
    roadmap_markdown_path = _roadmap_markdown_file_path()
    snapshot_path.parent.mkdir(parents=True, exist_ok=True)
    next_actions_path.parent.mkdir(parents=True, exist_ok=True)
    roadmap_snapshot_path.parent.mkdir(parents=True, exist_ok=True)
    roadmap_markdown_path.parent.mkdir(parents=True, exist_ok=True)

    snapshot_payload = {
        "synced_at": _now_iso(),
        "overview": overview,
    }
    snapshot_path.write_text(json.dumps(snapshot_payload, indent=2), encoding="utf-8")
    next_actions = overview.get("next_actions", [])
    next_actions_path.write_text(
        _actions_markdown(next_actions if isinstance(next_actions, list) else [], overview.get("generated_at", _now_iso())),
        encoding="utf-8",
    )
    roadmap_snapshot = _build_roadmap_snapshot(overview)
    roadmap_snapshot_path.write_text(json.dumps(roadmap_snapshot, indent=2), encoding="utf-8")
    roadmap_markdown_path.write_text(_roadmap_markdown(roadmap_snapshot), encoding="utf-8")

    return {
        "status": "ok",
        "synced_at": snapshot_payload["synced_at"],
        "snapshot_path": str(snapshot_path),
        "next_actions_path": str(next_actions_path),
        "roadmap_snapshot_path": str(roadmap_snapshot_path),
        "roadmap_markdown_path": str(roadmap_markdown_path),
        "roadmap_now_count": len(roadmap_snapshot.get("horizons", {}).get("now", [])),
        "roadmap_next_count": len(roadmap_snapshot.get("horizons", {}).get("next", [])),
        "next_actions_count": len(next_actions) if isinstance(next_actions, list) else 0,
    }


def get_projects_overview(force_refresh: bool = False) -> dict[str, Any]:
    now_ts = time.time()
    if not force_refresh:
        cached_payload = _OVERVIEW_CACHE.get("payload")
        cached_ts = float(_OVERVIEW_CACHE.get("ts") or 0)
        if cached_payload and (now_ts - cached_ts) < _OVERVIEW_TTL_SECONDS:
            _board_log(
                "get_projects_overview_cache_hit",
                {
                    "force_refresh": bool(force_refresh),
                    "generated_at": cached_payload.get("generated_at") if isinstance(cached_payload, dict) else "",
                    "age_seconds": round(now_ts - cached_ts, 2),
                },
            )
            return cached_payload

    cards = list_cards()
    local_repos = _scan_local_repos()
    github_index = _scan_github_repos()
    github_lookup_available = _github_lookup_available(github_index)
    tracked_projects = _build_tracked_projects(github_index, github_lookup_available=github_lookup_available)

    enriched_repos: list[dict[str, Any]] = []
    for repo in local_repos:
        gh = github_index.get(repo["name"], {})
        enriched = dict(repo)
        enriched["github_archived"] = bool(gh.get("isArchived", False))
        enriched["github_private"] = bool(gh.get("isPrivate", False))
        enriched["github_fork"] = bool(gh.get("isFork", False))
        enriched["github_pushed_at"] = str(gh.get("pushedAt") or "")
        enriched["github_updated_at"] = str(gh.get("updatedAt") or "")
        enriched["github_url"] = str(gh.get("url") or repo.get("remote") or "")
        enriched["description"] = str(gh.get("description") or "")
        enriched_repos.append(enriched)

    manifest, manifest_path = _latest_cleanup_manifest()
    cleanup = _cleanup_summary(manifest)
    cleanup["manifest_path"] = manifest_path
    card_counts = _card_counts(cards)
    sorted_repos = sorted(
        enriched_repos,
        key=lambda row: (row.get("github_archived", False), row.get("name", "")),
    )
    next_actions = _derive_next_actions(cards, sorted_repos, cleanup, tracked_projects=tracked_projects)
    runtime_mode = "cloud_run" if _is_cloud_runtime() else "local"

    payload = {
        "status": "ok",
        "generated_at": _now_iso(),
        "runtime_mode": runtime_mode,
        "board": {
            "columns": list(BOARD_STATUSES),
            "cards": cards,
            "counts": card_counts,
        },
        "repos": sorted_repos,
        "tracked_projects": tracked_projects,
        "summary": {
            "local_repo_count": len(enriched_repos),
            "local_dirty_repo_count": len([row for row in enriched_repos if int(row.get("dirty_files", 0)) > 0]),
            "github_archived_visible_count": len([row for row in enriched_repos if row.get("github_archived")]),
            "board_card_count": len(cards),
            "tracked_project_count": len(tracked_projects),
            "tracked_missing_local_count": len([row for row in tracked_projects if row.get("missing_local")]),
            "tracked_local_not_applicable_count": len(
                [row for row in tracked_projects if row.get("local_path_check") == "not_applicable"]
            ),
            "tracked_github_not_applicable_count": len(
                [row for row in tracked_projects if row.get("github_check") == "not_applicable"]
            ),
            "tracked_missing_github_count": len([row for row in tracked_projects if row.get("missing_github")]),
            "cleanup_total_moves": cleanup["total_moves"],
            "cleanup_total_size": cleanup["total_size"],
            "cleanup_remote_archived_repos": cleanup["remote_archived_repos"],
        },
        "cleanup": cleanup,
        "next_actions": next_actions,
        "workspace_sizes": _workspace_sizes(),
    }

    _OVERVIEW_CACHE["ts"] = now_ts
    _OVERVIEW_CACHE["payload"] = payload
    _board_log(
        "get_projects_overview",
        {
            "force_refresh": bool(force_refresh),
            "runtime_mode": runtime_mode,
            "board_counts": card_counts,
            "tracked_project_count": len(tracked_projects),
            "missing_github_count": int(payload["summary"].get("tracked_missing_github_count", 0)),
            "missing_local_count": int(payload["summary"].get("tracked_missing_local_count", 0)),
            "next_actions_count": len(next_actions),
        },
    )
    return payload
