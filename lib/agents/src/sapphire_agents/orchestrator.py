from __future__ import annotations

import asyncio
import hashlib
import html
import json
import logging
import os
import re
import time
from collections import deque
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx
from app.alpha_stream import build_alpha_stream_payload, score_alpha_stream_for_chat
from app.architecture_map import build_architecture_snapshot
from app.autonomy import load_autonomy_proposals, run_autonomy_cycle
from app.config import Settings
from app.control_plane import ControlPlaneStore
from app.digest import format_alpha_stream_message, format_digest_message, format_watchlist_message
from app.event_stream import append_event, recent_events
from app.membership_router import get_router_overview
from app.models import ChatConfig, NewsItem
from app.news import NewsFetcher
from app.project_board import get_projects_overview
from app.runtime_policy import (
    allowed_executor_agent_ids,
    allowed_executor_membership_ids,
    save_runtime_policy,
)
from app.sources import REPUTABLE_NEWS_SOURCES
from app.storage import ChatStore, default_chat_config
from app.telegram_api import TelegramClient

logger = logging.getLogger(__name__)
_TELEGRAM_RUNTIME_PROMPT_PATH = Path(__file__).resolve().parent / "data" / "crypton_telegram_agent_prompt.md"
_TELEGRAM_ARCHITECTURE_POLICY_PATH = Path(__file__).resolve().parent / "data" / "crypton_architecture_policy.md"


def _load_telegram_runtime_prompt(path: Path = _TELEGRAM_RUNTIME_PROMPT_PATH) -> dict[str, str]:
    payload = {
        "profile": "Crypton PM Commander v3",
        "path": str(path),
        "content": "",
        "version": "v3",
    }
    try:
        content = path.read_text(encoding="utf-8").strip()
    except OSError as exc:
        logger.warning("failed loading telegram runtime prompt %s: %s", path, exc)
        return payload

    payload["content"] = content
    for line in content.splitlines():
        cleaned = line.strip()
        if not cleaned:
            continue
        match = re.search(r"You are `([^`]+)`", cleaned)
        if match:
            payload["profile"] = match.group(1).strip() or payload["profile"]
        break
    return payload


def _load_architecture_policy(path: Path = _TELEGRAM_ARCHITECTURE_POLICY_PATH) -> dict[str, str]:
    payload = {
        "name": "Crypton Architecture Policy",
        "path": str(path),
        "content": "",
        "loaded": False,
    }
    try:
        content = path.read_text(encoding="utf-8").strip()
    except OSError as exc:
        logger.warning("failed loading architecture policy %s: %s", path, exc)
        return payload

    payload["content"] = content
    payload["loaded"] = True
    return payload


def _parse_csv(input_value: str, upper: bool = True) -> list[str]:
    output: list[str] = []
    seen = set()
    for token in re.split(r"[,\s]+", input_value.strip()):
        cleaned = token.strip()
        if not cleaned:
            continue
        normalized = cleaned.upper() if upper else cleaned.lower()
        if normalized in seen:
            continue
        seen.add(normalized)
        output.append(normalized)
    return output


def _extract_message(update: dict[str, Any]) -> dict[str, Any] | None:
    return update.get("message") or update.get("channel_post")


def _parse_command(raw_text: str) -> tuple[str, str]:
    text = raw_text.strip()
    if not text:
        return "", ""

    parts = text.split(maxsplit=1)
    command = parts[0]
    args = parts[1] if len(parts) > 1 else ""

    # Normalize /command@botname
    command = command.split("@", maxsplit=1)[0].lower()
    return command, args.strip()


def _normalize_assistant_mode(raw_text: str) -> str:
    text = str(raw_text or "").strip().lower()
    if text in {"operator", "ops", "control"}:
        return "operator"
    return "personal"


def _normalize_preference_tone(raw_text: str) -> str:
    text = str(raw_text or "").strip().lower()
    if text in {"detailed", "verbose", "deep"}:
        return "detailed"
    if text in {"balanced", "normal"}:
        return "balanced"
    return "concise"


def _normalize_preference_risk(raw_text: str) -> str:
    text = str(raw_text or "").strip().lower()
    if text in {"conservative", "low", "safe"}:
        return "conservative"
    if text in {"aggressive", "high", "fast"}:
        return "aggressive"
    return "balanced"


def _normalize_preference_coding_style(raw_text: str) -> str:
    text = str(raw_text or "").strip().lower().replace(" ", "_")
    if text in {"clean", "clean_architecture", "clean-architecture"}:
        return "clean_architecture"
    if text in {"exploratory", "creative"}:
        return "exploratory"
    return "pragmatic"


def _parse_utc_datetime(raw_text: str) -> datetime | None:
    text = str(raw_text or "").strip()
    if not text:
        return None
    try:
        value = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _extract_inline_decision_choice(raw_text: str) -> tuple[str, str] | None:
    text = re.sub(r"\s+", " ", str(raw_text or "").strip())
    if not text:
        return None
    match = re.match(
        r"^(?:/)?(?:decide|decision|approve)\s+([a-zA-Z0-9._:-]+)\s+(?:option\s*)?([1-3])$",
        text,
        flags=re.IGNORECASE,
    )
    if not match:
        return None
    decision_id = str(match.group(1) or "").strip()
    choice = str(match.group(2) or "").strip()
    if not decision_id or not choice:
        return None
    return decision_id, choice


def _infer_text_command(raw_text: str) -> tuple[str, str]:
    text = re.sub(r"\s+", " ", str(raw_text or "").strip())
    if not text:
        return "", ""
    lowered = text.lower()

    if lowered.startswith("research:"):
        return "/deepresearch", text.split(":", maxsplit=1)[1].strip()
    if lowered.startswith("deep research:"):
        return "/deepresearch", text.split(":", maxsplit=1)[1].strip()
    if lowered.startswith("deepresearch:"):
        return "/deepresearch", text.split(":", maxsplit=1)[1].strip()
    if lowered.startswith("deep research on "):
        return "/deepresearch", text[len("deep research on ") :].strip()

    if lowered.startswith("mode:"):
        return "/mode", text.split(":", maxsplit=1)[1].strip()
    if lowered in {"personal mode", "switch to personal mode"}:
        return "/mode", "personal"
    if lowered in {"operator mode", "switch to operator mode"}:
        return "/mode", "operator"

    if lowered in {
        "status",
        "overview",
        "system status",
        "system overview",
        "health check",
        "where are we",
        "where are we now",
    }:
        return "/overview", ""

    if lowered in {
        "what next",
        "next steps",
        "what should we do next",
        "check in",
        "checkin",
        "brief",
    }:
        return "/brief", ""

    if lowered in {"assistant checkin", "assistant check-in", "run checkin", "run check-in"}:
        return "/checkin", ""

    if lowered in {
        "inbox",
        "decisions",
        "show decisions",
        "decision inbox",
        "steering questions",
        "questions for me",
    }:
        return "/inbox", ""

    if lowered in {"run autonomy", "autonomy now", "run autonomous cycle"}:
        return "/autonomy", ""

    if lowered in {"architecture", "architecture map", "topology", "system topology"}:
        return "/architecture", ""

    if lowered in {"agents", "agent fleet", "fleet status", "worker status"}:
        return "/agents", ""

    if lowered in {"cleanup agents", "cleanup stale agents", "prune stale agents"}:
        return "/cleanupagents", "dry"

    if lowered in {"rari mode", "rari status"}:
        return "/rari", "status"
    if lowered in {"enforce rari", "rari enforce", "enable rari mode"}:
        return "/rari", "enforce"

    if lowered.startswith("set sla ") or lowered.startswith("sla "):
        parts = text.split(maxsplit=1)
        if len(parts) > 1:
            return "/setsla", parts[1].strip()

    if lowered.startswith("checkin every "):
        value = text[len("checkin every ") :].strip().replace("minutes", "").replace("minute", "").strip()
        return "/setcheckin", value

    return "", ""


def _normalize_url(url: str) -> str:
    parsed = urlparse(url or "")
    scheme = (parsed.scheme or "https").lower()
    netloc = (parsed.netloc or "").lower()
    if netloc.startswith("www."):
        netloc = netloc[4:]
    path = parsed.path or ""
    return f"{scheme}://{netloc}{path}".rstrip("/")


def _single_agent_mode_enabled() -> bool:
    text = str(os.getenv("AGENTIC_SINGLE_AGENT_MODE") or "").strip().lower()
    return text in {"1", "true", "yes", "on"}


def _single_agent_membership_id() -> str:
    return str(os.getenv("AGENTIC_SINGLE_AGENT_MEMBERSHIP") or "").strip().lower()


def _single_agent_capabilities(default_capabilities: list[str]) -> list[str]:
    normalized_default: list[str] = []
    for capability in default_capabilities:
        text = str(capability or "").strip().lower()
        if text and text not in normalized_default:
            normalized_default.append(text)

    if not _single_agent_mode_enabled():
        return normalized_default

    single_caps: list[str] = []
    membership_id = _single_agent_membership_id()
    if membership_id:
        single_caps.append(f"membership:{membership_id}")
    single_caps.extend(["python", "git", "repo-write"])

    dedup: list[str] = []
    for capability in single_caps:
        if capability not in dedup:
            dedup.append(capability)
    return dedup


def _legacy_item_id(source_key: str, url: str, title: str) -> str:
    """
    Back-compat: older versions used sha256(source|url|title)[:20].
    Keep checking it so an upgrade doesn't resend historical items.
    """
    digest = hashlib.sha256(f"{source_key}|{url}|{title}".encode()).hexdigest()
    return digest[:20]

def _url_item_id(url: str) -> str:
    """
    Cross-source stable id based only on the normalized URL.

    Why:
    - Some feeds change titles over time (legacy ids can shift).
    - Some stories can appear via different sources with slightly different ids.
    - Using URL-only ids in the sent buffer helps prevent duplicate sends.
    """
    canonical = _normalize_url(url) or (url or "").strip()
    digest = hashlib.sha256(f"url|{canonical}".encode()).hexdigest()
    return digest[:20]


def _strip_html(raw: str) -> str:
    text = html.unescape(raw or "")
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _extract_meta_description(page_html: str) -> str:
    # Best-effort meta description extraction (works even on many paywalled sites).
    candidates = [
        r'<meta[^>]+property=["\']og:description["\'][^>]+content=["\']([^"\']+)["\']',
        r'<meta[^>]+name=["\']description["\'][^>]+content=["\']([^"\']+)["\']',
        r'<meta[^>]+name=["\']twitter:description["\'][^>]+content=["\']([^"\']+)["\']',
    ]
    for pattern in candidates:
        match = re.search(pattern, page_html, flags=re.IGNORECASE)
        if match:
            return _strip_html(match.group(1))
    # Fallback: first paragraph.
    match = re.search(r"<p[^>]*>(.*?)</p>", page_html, flags=re.IGNORECASE | re.DOTALL)
    if match:
        return _strip_html(match.group(1))
    return ""


def _extract_article_text(page_html: str) -> str:
    """
    Best-effort extraction of readable body text from an HTML page without heavy deps.

    Heuristics:
    - Prefer <article>...</article> when present
    - Otherwise concatenate <p>...</p> blocks
    """
    html_in = page_html or ""
    # Prefer <article> tag content if present.
    article_match = re.search(r"<article[^>]*>(.*?)</article>", html_in, flags=re.IGNORECASE | re.DOTALL)
    scope = article_match.group(1) if article_match else html_in

    paras = re.findall(r"<p[^>]*>(.*?)</p>", scope, flags=re.IGNORECASE | re.DOTALL)
    cleaned = [_strip_html(p) for p in paras]
    # Drop very short boilerplate paragraphs.
    cleaned = [p for p in cleaned if len(p) >= 40]
    text = re.sub(r"\s+", " ", " ".join(cleaned)).strip()
    return text


def _summarize_text(text: str, limit: int = 240) -> str:
    """
    Simple extractive summary: take 1-3 leading sentences until we hit the limit.
    This is intentionally cheap (no LLM) to avoid wasting resources.
    """
    raw = re.sub(r"\s+", " ", (text or "")).strip()
    if not raw:
        return ""
    if len(raw) <= limit:
        return raw
    sentences = re.split(r"(?<=[.!?])\\s+", raw)
    out: list[str] = []
    total = 0
    for s in sentences:
        s = s.strip()
        if not s:
            continue
        if total + len(s) + (1 if out else 0) > limit:
            break
        out.append(s)
        total += len(s) + (1 if out else 0)
        if len(out) >= 3:
            break
    summary = " ".join(out).strip()
    if len(summary) < 60:
        summary = raw[:limit].rstrip()
    return summary


class AlphaBotOrchestrator:
    def __init__(
        self,
        settings: Settings,
        store: ChatStore,
        telegram_client: TelegramClient,
        news_fetcher: NewsFetcher,
    ) -> None:
        self._settings = settings
        self._store = store
        self._telegram = telegram_client
        self._news = news_fetcher
        # De-dupe Telegram webhook retries (best-effort; in-memory per instance).
        self._recent_update_ids: deque[int] = deque()
        self._recent_update_id_set: set[int] = set()
        self._max_recent_updates = 512

        # Article snippet cache (normalized url -> {ts, snippet}) to avoid refetching.
        self._snippet_cache: dict[str, tuple[float, str]] = {}
        self._snippet_cache_ttl_seconds = float(settings.snippet_cache_ttl_seconds)
        self._snippet_fetch_timeout_seconds = float(settings.snippet_fetch_timeout_seconds)
        self._snippet_fetch_max_concurrency = int(settings.snippet_fetch_max_concurrency)
        self._sent_item_id_buffer_size = int(settings.sent_item_id_buffer_size)
        self._min_digest_interval_minutes = int(settings.min_digest_interval_minutes)
        self._default_heartbeat_interval_minutes = max(5, int(settings.heartbeat_interval_minutes))
        self._heartbeat_directive_max_chars = max(80, int(settings.heartbeat_directive_max_chars))
        self._allowed_user_ids = set(settings.allowed_telegram_user_ids)
        self._allowed_chat_ids = set(settings.allowed_telegram_chat_ids)
        self._telegram_runtime_prompt = _load_telegram_runtime_prompt()
        self._telegram_prompt_profile = str(self._telegram_runtime_prompt.get("profile") or "Crypton PM Commander v3")
        self._architecture_policy = _load_architecture_policy()
        self._architecture_cache: dict[str, Any] = {"ts": 0.0, "payload": None}
        self._architecture_cache_ttl_seconds = 20.0

    def _record_event(self, event_type: str, **kwargs: Any) -> None:
        try:
            append_event(event_type, **kwargs)
        except Exception as exc:
            logger.warning("failed to append orchestrator event %s: %s", event_type, exc)

    def _runtime_status_label(
        self,
        *,
        agents_online: int,
        tasks_queued: int,
        tasks_failed: int,
        board_blocked: int,
        memberships_ready: int,
    ) -> str:
        if agents_online <= 0 or tasks_failed > 0:
            return "Critical"
        if tasks_queued > 0 or board_blocked > 0 or memberships_ready <= 0:
            return "Degraded"
        return "Healthy"

    def _task_id_list(self, tasks: Sequence[dict[str, Any]], *, limit: int = 3) -> str:
        ids: list[str] = []
        for item in tasks[: max(0, limit)]:
            task_id = str(item.get("task_id") or "").strip()
            if task_id:
                ids.append(task_id)
        return ", ".join(ids) if ids else "none"

    def _decision_blocks(self, proposals: Sequence[dict[str, Any]], *, limit: int = 2) -> list[str]:
        lines: list[str] = []
        for item in proposals[: max(0, limit)]:
            decision_id = html.escape(str(item.get("decision_id") or "decision"))
            title = html.escape(str(item.get("title") or "Decision required"))
            urgency = html.escape(str(item.get("urgency") or ""))
            context = html.escape(str(item.get("context") or ""))
            recommended = html.escape(str(item.get("recommended") or ""))
            options = item.get("options") if isinstance(item.get("options"), list) else []

            lines.append(f"[Decision Block: {decision_id}]")
            lines.append(f"Title: {title}")
            if urgency:
                lines.append(f"Urgency: {urgency}")
            if context:
                lines.append(f"Context: {context}")
            lines.append("Options:")
            if options:
                for idx, option in enumerate(options[:3], start=1):
                    lines.append(f"{idx}. {html.escape(str(option))}")
            else:
                lines.append("1. No options provided.")
            if recommended:
                lines.append(f"Recommended: {recommended}")
            lines.append("")
        return lines

    def _steering_question_blocks(self, questions: Sequence[dict[str, Any]], *, limit: int = 2) -> list[str]:
        lines: list[str] = []
        for item in questions[: max(0, limit)]:
            question_id = html.escape(str(item.get("question_id") or "question"))
            project_name = html.escape(str(item.get("project_name") or item.get("project_id") or "project"))
            question = html.escape(str(item.get("question") or "No question provided."))
            why = html.escape(str(item.get("why") or ""))
            recommended = html.escape(str(item.get("recommended") or ""))
            options = item.get("options") if isinstance(item.get("options"), list) else []

            lines.append(f"[Steering Question: {question_id}]")
            lines.append(f"Project: {project_name}")
            lines.append(f"Question: {question}")
            if why:
                lines.append(f"Why now: {why}")
            lines.append("Options:")
            if options:
                for idx, option in enumerate(options[:3], start=1):
                    lines.append(f"{idx}. {html.escape(str(option))}")
            else:
                lines.append("1. No options provided.")
            if recommended:
                lines.append(f"Recommended: {recommended}")
            lines.append("")
        return lines

    def _load_tools_catalog(self) -> dict[str, Any]:
        """Load the Kimi tools catalog from app/data."""
        try:
            catalog_path = Path(__file__).resolve().parent / "data" / "kimi_tools_catalog.json"
            if not catalog_path.exists():
                return {}
            data = json.loads(catalog_path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}

    def _get_daily_research_status(self) -> dict[str, Any]:
        """Check daily research save paths and return status."""
        try:
            root_dir = Path(__file__).resolve().parent.parent
            research_dir = root_dir / "memory" / "kimi-deep-research"
            if not research_dir.exists():
                return {"available": False, "dir_exists": False, "today_exists": False}
            from datetime import date
            today = date.today().isoformat()
            today_report = research_dir / f"{today}.md"
            today_prompt = research_dir / f"{today}.prompt.md"
            index_file = research_dir / "index.jsonl"
            return {
                "available": True,
                "dir_exists": True,
                "today_exists": today_report.exists(),
                "today_report": str(today_report) if today_report.exists() else None,
                "today_prompt": str(today_prompt) if today_prompt.exists() else None,
                "index_exists": index_file.exists(),
                "save_path": str(research_dir),
            }
        except Exception:
            return {"available": False, "dir_exists": False, "today_exists": False}

    def _skills_message(self) -> str:
        catalog = self._load_tools_catalog()
        summary = catalog.get("summary") if isinstance(catalog.get("summary"), dict) else {}
        skills = catalog.get("skills") if isinstance(catalog.get("skills"), list) else []

        total = int(summary.get("total_skills", len(skills)))
        source_counts = summary.get("source_counts") if isinstance(summary.get("source_counts"), dict) else {}
        global_count = int(source_counts.get("global", 0))
        project_count = int(source_counts.get("project", 0))
        bins = summary.get("required_bins") if isinstance(summary.get("required_bins"), list) else []
        env_vars = summary.get("required_env_vars") if isinstance(summary.get("required_env_vars"), list) else []
        integrations = catalog.get("integrations") if isinstance(catalog.get("integrations"), dict) else {}
        clawhub = integrations.get("clawhub") if isinstance(integrations.get("clawhub"), dict) else {}
        clawhub_lock_exists = bool(clawhub.get("lock_exists"))
        clawhub_skill_count = int(clawhub.get("installed_skill_count", 0))

        sample_names: list[str] = []
        for row in skills[:24]:
            if not isinstance(row, dict):
                continue
            name = str(row.get("name") or row.get("slug") or "").strip()
            if not name:
                continue
            sample_names.append(name)

        lines = [
            f"<b>{html.escape(self._telegram_prompt_profile)} - /skills</b>",
            "Kimi tool/skill library snapshot:",
            f"- total_skills={total} | global={global_count} | project={project_count}",
            f"- required_bins={html.escape(', '.join([str(v) for v in bins]) if bins else 'none')}",
            f"- required_env={html.escape(', '.join([str(v) for v in env_vars]) if env_vars else 'none')}",
            "- capability flags: web-access, tool:tavily-search, tool:summarize, tool:gcloud, tool:gh, tool:docker",
            f"- clawhub_lock={'true' if clawhub_lock_exists else 'false'} | clawhub_installed={clawhub_skill_count}",
            "- catalog_json=app/data/kimi_tools_catalog.json",
            "- catalog_md=app/data/kimi_tools_catalog.md",
        ]
        if sample_names:
            lines.append("- sample_skills=" + html.escape(", ".join(sample_names[:12])))
            if len(sample_names) > 12:
                lines.append("- sample_skills_2=" + html.escape(", ".join(sample_names[12:24])))
        return "\n".join(lines)[:3900]

    def _deep_research_status_message(self) -> str:
        status = self._get_daily_research_status()
        lines = [
            f"<b>{html.escape(self._telegram_prompt_profile)} - /deepresearch status</b>",
            f"- available={str(bool(status.get('available'))).lower()}",
            f"- save_path={html.escape(str(status.get('save_path') or 'memory/kimi-deep-research'))}",
            f"- today_exists={str(bool(status.get('today_exists'))).lower()}",
            f"- today_report={html.escape(str(status.get('today_report') or 'missing'))}",
            f"- today_prompt={html.escape(str(status.get('today_prompt') or 'missing'))}",
            f"- index_exists={str(bool(status.get('index_exists'))).lower()}",
        ]
        return "\n".join(lines)[:3900]

    def _architecture_snapshot(self, *, refresh: bool = False) -> dict[str, Any]:
        now_ts = time.time()
        cached_payload = self._architecture_cache.get("payload")
        cached_ts = float(self._architecture_cache.get("ts") or 0)
        if not refresh and isinstance(cached_payload, dict) and (now_ts - cached_ts) < self._architecture_cache_ttl_seconds:
            return cached_payload

        try:
            payload = build_architecture_snapshot(
                control_store=ControlPlaneStore(),
                runtime_mode="cloud_run" if os.getenv("K_SERVICE") else "local",
                service_name=str(os.getenv("K_SERVICE") or "local"),
                service_revision=str(os.getenv("K_REVISION") or "local"),
                refresh_projects=bool(refresh),
            )
        except Exception as exc:
            payload = {
                "status": "error",
                "generated_at": datetime.now(tz=UTC).isoformat(),
                "error": str(exc),
            }
        self._architecture_cache["ts"] = now_ts
        self._architecture_cache["payload"] = payload
        return payload

    def _architecture_message(self, *, refresh: bool = False) -> str:
        snapshot = self._architecture_snapshot(refresh=refresh)
        generated_at = str(snapshot.get("generated_at") or "").replace("T", " ").replace("+00:00", " UTC")
        if str(snapshot.get("status") or "").lower() != "ok":
            error = html.escape(str(snapshot.get("error") or "unknown error"))
            return (
                f"<b>{html.escape(self._telegram_prompt_profile)} - /architecture</b>\n"
                f"<i>{html.escape(generated_at)}</i>\n"
                f"Could not build architecture snapshot: {error}"
            )[:3900]

        stats = snapshot.get("stats") if isinstance(snapshot.get("stats"), dict) else {}
        policy = snapshot.get("executor_policy") if isinstance(snapshot.get("executor_policy"), dict) else {}
        topology = snapshot.get("topology") if isinstance(snapshot.get("topology"), dict) else {}
        fleet_nodes = topology.get("fleet_nodes") if isinstance(topology.get("fleet_nodes"), list) else []
        logs = snapshot.get("logs") if isinstance(snapshot.get("logs"), list) else []
        charts_path = html.escape(str(snapshot.get("project_charts_markdown_path") or "memory/PROJECT_ARCHITECTURE_CHARTS_LATEST.md"))

        policy_mode = html.escape(str(policy.get("mode") or "open"))
        policy_agents = policy.get("allowed_executor_agent_ids") if isinstance(policy.get("allowed_executor_agent_ids"), list) else []
        policy_memberships = (
            policy.get("allowed_executor_membership_ids")
            if isinstance(policy.get("allowed_executor_membership_ids"), list)
            else []
        )
        policy_agents_text = html.escape(", ".join([str(item) for item in policy_agents]) if policy_agents else "none")
        policy_memberships_text = html.escape(
            ", ".join([str(item) for item in policy_memberships]) if policy_memberships else "none"
        )

        lines = [
            f"<b>{html.escape(self._telegram_prompt_profile)} - /architecture</b>",
            f"<i>{html.escape(generated_at)}</i>",
            (
                "Runtime: "
                f"{html.escape(str(snapshot.get('runtime_mode') or 'unknown'))} | "
                f"service={html.escape(str(snapshot.get('service_name') or 'unknown'))} | "
                f"revision={html.escape(str(snapshot.get('service_revision') or 'unknown'))}"
            ),
            (
                "Stats: "
                f"agents_online={int(stats.get('agents_online', 0))}/{int(stats.get('agents_registered', 0))} | "
                f"queued={int(stats.get('tasks_queued', 0))} | leased={int(stats.get('tasks_leased', 0))} | "
                f"failed={int(stats.get('tasks_failed', 0))} | "
                f"pi_reachable={int(stats.get('pi_nodes_reachable', 0))}/{int(stats.get('pi_nodes_total', 0))}"
            ),
            f"Executor policy: mode={policy_mode}",
            f"- allowed_agents={policy_agents_text}",
            f"- allowed_memberships={policy_memberships_text}",
            "Pi nodes:",
        ]

        if fleet_nodes:
            for node in fleet_nodes[:4]:
                if not isinstance(node, dict):
                    continue
                alias = html.escape(str(node.get("node") or "pi"))
                role = html.escape(str(node.get("role") or "worker"))
                host = html.escape(str(node.get("connected_host") or node.get("host") or "unknown"))
                reachable = "reachable" if bool(node.get("reachable")) else "unreachable"
                lines.append(f"- {alias}: {reachable} | role={role} | host={host}")
        else:
            lines.append("- none reported")

        lines.append("Recent control events:")
        if logs:
            for row in logs[:4]:
                if not isinstance(row, dict):
                    continue
                event_type = html.escape(str(row.get("event_type") or "event"))
                task_id = html.escape(str(row.get("task_id") or ""))
                agent_id = html.escape(str(row.get("agent_id") or ""))
                summary = html.escape(str(row.get("summary") or "")[:90])
                detail = f"{event_type}"
                if task_id:
                    detail += f" task={task_id}"
                if agent_id:
                    detail += f" agent={agent_id}"
                if summary:
                    detail += f" | {summary}"
                lines.append(f"- {detail}")
        else:
            lines.append("- none")

        lines.append(f"Project charts: {charts_path}")
        if self._settings.public_base_url:
            lines.append(f"Dashboard: {html.escape(self._settings.public_base_url)}/architecture")
        return "\n".join(lines)[:3900]

    def _extract_membership_ids(self, capabilities: Sequence[Any]) -> list[str]:
        memberships: list[str] = []
        for raw in capabilities:
            text = str(raw or "").strip().lower()
            if not text.startswith("membership:"):
                continue
            membership = text.split(":", maxsplit=1)[1].strip()
            if membership and membership not in memberships:
                memberships.append(membership)
        return memberships

    def _agents_message(self, *, stale_after_seconds: int = 3600) -> str:
        try:
            agents = ControlPlaneStore().list_agents(heartbeat_ttl_seconds=180, include_disabled=True)
        except Exception as exc:
            return f"<b>{html.escape(self._telegram_prompt_profile)} - /agents</b>\nError loading agents: {html.escape(str(exc))}"[
                :3900
            ]

        allowed_agents = allowed_executor_agent_ids()
        allowed_memberships = allowed_executor_membership_ids()
        online_count = 0
        disabled_count = 0
        stale_candidates = 0
        rows: list[dict[str, Any]] = []
        for item in agents:
            if not isinstance(item, dict):
                continue
            status = str(item.get("status") or "").strip().lower()
            online = bool(item.get("online"))
            if online:
                online_count += 1
            if status == "disabled":
                disabled_count += 1

            capabilities = item.get("capabilities") if isinstance(item.get("capabilities"), list) else []
            memberships = self._extract_membership_ids(capabilities)
            age_seconds = int(item.get("heartbeat_age_seconds") or 0)
            agent_id = str(item.get("agent_id") or "").strip().lower()
            protected = bool(
                (agent_id and agent_id in allowed_agents)
                or any(membership in allowed_memberships for membership in memberships)
            )
            if status != "disabled" and age_seconds >= max(300, stale_after_seconds) and not protected:
                stale_candidates += 1
            rows.append(
                {
                    "agent_id": agent_id or "unknown",
                    "status": status or "unknown",
                    "online": online,
                    "age_seconds": age_seconds,
                    "memberships": memberships,
                }
            )

        rows.sort(key=lambda row: (0 if row.get("online") else 1, int(row.get("age_seconds", 0))))
        lines = [
            f"<b>{html.escape(self._telegram_prompt_profile)} - /agents</b>",
            (
                "Fleet: "
                f"online={online_count}/{len(rows)} | disabled={disabled_count} | "
                f"stale_candidates={stale_candidates} (>{max(300, stale_after_seconds)}s)"
            ),
            (
                "Protected by executor policy: "
                f"agents={html.escape(', '.join(sorted(allowed_agents)) if allowed_agents else 'none')} | "
                f"memberships={html.escape(', '.join(sorted(allowed_memberships)) if allowed_memberships else 'none')}"
            ),
            "Top agents:",
        ]
        if rows:
            for row in rows[:8]:
                memberships = row.get("memberships") if isinstance(row.get("memberships"), list) else []
                memberships_text = ", ".join([str(item) for item in memberships]) if memberships else "none"
                state = "online" if row.get("online") else row.get("status", "offline")
                lines.append(
                    f"- {html.escape(str(row.get('agent_id') or 'unknown'))}: "
                    f"{html.escape(str(state))} | age={int(row.get('age_seconds', 0))}s | "
                    f"memberships={html.escape(memberships_text)}"
                )
        else:
            lines.append("- none")

        lines.append("Tip: /cleanupagents dry (preview) or /cleanupagents apply")
        return "\n".join(lines)[:3900]

    def _cleanup_stale_agents(self, *, stale_after_seconds: int, dry_run: bool, actor: str) -> dict[str, Any]:
        keep_agents = sorted(allowed_executor_agent_ids())
        keep_memberships = sorted(allowed_executor_membership_ids())
        result = ControlPlaneStore().cleanup_stale_agents(
            stale_after_seconds=stale_after_seconds,
            keep_agent_ids=keep_agents,
            keep_membership_ids=keep_memberships,
            dry_run=dry_run,
            actor=actor,
        )
        result["keep_agent_ids"] = keep_agents
        result["keep_membership_ids"] = keep_memberships
        return result

    def _cleanup_agents_message(self, result: dict[str, Any]) -> str:
        dry_run = bool(result.get("dry_run"))
        lines = [
            f"<b>{html.escape(self._telegram_prompt_profile)} - /cleanupagents</b>",
            f"Mode: {'preview' if dry_run else 'applied'}",
            (
                f"registered={int(result.get('registered_count', 0))} | "
                f"candidates={int(result.get('candidate_count', 0))} | "
                f"disabled={int(result.get('disabled_count', 0))}"
            ),
            f"keep_agent_ids={html.escape(', '.join(result.get('keep_agent_ids') or []) or 'none')}",
            f"keep_memberships={html.escape(', '.join(result.get('keep_membership_ids') or []) or 'none')}",
        ]
        candidates = result.get("candidates") if isinstance(result.get("candidates"), list) else []
        if candidates:
            lines.append("Candidates:")
            for row in candidates[:6]:
                if not isinstance(row, dict):
                    continue
                memberships = row.get("memberships") if isinstance(row.get("memberships"), list) else []
                lines.append(
                    f"- {html.escape(str(row.get('agent_id') or 'unknown'))} | "
                    f"age={int(row.get('heartbeat_age_seconds', 0))}s | "
                    f"memberships={html.escape(', '.join([str(item) for item in memberships]) or 'none')}"
                )
        else:
            lines.append("Candidates: none")
        return "\n".join(lines)[:3900]

    def _enforce_rari_policy_message(self, *, actor: str) -> str:
        expected_mode = str(os.getenv("AGENTIC_EXPECTED_EXECUTOR_POLICY_MODE") or "").strip().lower()
        strict_lock = str(os.getenv("AGENTIC_ENFORCE_EXPECTED_EXECUTOR_POLICY") or "").strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
        }
        if strict_lock and expected_mode and expected_mode != "rari_pair":
            return (
                f"<b>{html.escape(self._telegram_prompt_profile)} - /rari enforce blocked</b>\n"
                "Executor policy lock is enabled and does not allow rari_pair.\n"
                f"expected_mode={html.escape(expected_mode)}\n"
                "Use the PM Hub set_executor_policy flow with an approved expected-policy change first."
            )[:3900]

        policy_payload = {
            "mode": "rari_pair",
            "description": "Simplified dual-Pi execution mode (rari1+rari2 only).",
            "allowed_executor_agent_ids": ["claude-main", "kimi-main"],
            "allowed_executor_membership_ids": ["claude_code", "kimi", "google_antigravity"],
        }
        saved = save_runtime_policy(policy_payload, updated_by=actor)
        cleanup_result = self._cleanup_stale_agents(
            stale_after_seconds=3600,
            dry_run=False,
            actor=actor,
        )
        return (
            f"<b>{html.escape(self._telegram_prompt_profile)} - /rari enforce</b>\n"
            f"Policy applied: mode={html.escape(str(saved.get('mode') or 'custom'))}\n"
            f"allowed_agents={html.escape(', '.join(saved.get('allowed_executor_agent_ids') or []))}\n"
            f"allowed_memberships={html.escape(', '.join(saved.get('allowed_executor_membership_ids') or []))}\n"
            f"Cleanup applied: candidates={int(cleanup_result.get('candidate_count', 0))} "
            f"| disabled={int(cleanup_result.get('disabled_count', 0))}\n"
            "Use /agents to verify fleet health."
        )[:3900]

    def _rari_status_message(self) -> str:
        return "\n".join(
            [
                self._agents_message(stale_after_seconds=3600),
                "",
                "Tip: /rari enforce applies dual-Pi policy and cleans stale registrations.",
            ]
        )[:3900]

    def _queue_deep_research_task(self, topic: str, actor: str) -> dict[str, Any]:
        root_dir = Path(__file__).resolve().parent.parent
        script_path = root_dir / "scripts" / "kimi_daily_research.sh"
        cleaned_topic = re.sub(r"\s+", " ", topic).strip()
        single_agent_mode = _single_agent_mode_enabled()
        single_agent_membership = _single_agent_membership_id()
        use_kimi_script = (not single_agent_mode) or (single_agent_membership in {"", "kimi"})

        cmd = "single-agent-research"
        if use_kimi_script:
            if not script_path.exists():
                return {"ok": False, "error": f"missing script: {script_path}"}
            cmd = "./scripts/kimi_daily_research.sh --force"
            if cleaned_topic:
                safe_topic = cleaned_topic.replace('"', "")
                cmd += f' --topic "{safe_topic}"'

        instructions = (
            "Run one deep-research cycle and persist outputs.\n"
            f"Command: cd '{root_dir}' && {cmd}\n"
            "Verify these files exist after run:\n"
            "- memory/kimi-deep-research/YYYY-MM-DD.prompt.md\n"
            "- memory/kimi-deep-research/YYYY-MM-DD.md\n"
            "- memory/kimi-deep-research/index.jsonl\n"
            "Return concise summary and file paths."
        )
        if single_agent_mode and not use_kimi_script:
            instructions = (
                "Single-agent mode is active. Do not depend on Kimi CLI.\n"
                "Use available local tooling to produce one deep-research brief and persist outputs.\n"
                "Verify these files exist after run:\n"
                "- memory/kimi-deep-research/YYYY-MM-DD.prompt.md\n"
                "- memory/kimi-deep-research/YYYY-MM-DD.md\n"
                "- memory/kimi-deep-research/index.jsonl\n"
                "Return concise summary and file paths."
            )

        task = ControlPlaneStore().create_task(
            title="Run deep research cycle" + (f": {cleaned_topic[:80]}" if cleaned_topic else ""),
            payload={
                "task_type": "research",
                "source": "telegram.deepresearch",
                "project": "ai-project-management-system",
                "workdir": str(root_dir),
                "instructions": instructions,
                "topic": cleaned_topic,
                "single_agent_mode": single_agent_mode,
                "single_agent_membership": single_agent_membership,
            },
            required_capabilities=_single_agent_capabilities(
                [
                    "membership:kimi",
                    "python",
                    "shell",
                    "web-access",
                    "tool:tavily-search",
                    "tool:summarize",
                ]
            ),
            priority=22,
            max_attempts=3,
            created_by=actor,
        )
        return {"ok": True, "task": task, "command": cmd}

    def _brief_message(self, chat: ChatConfig) -> str:
        generated_at = datetime.now(tz=UTC).strftime("%Y-%m-%d %H:%M UTC")
        focus_project = chat.focus_project.strip() or "none"
        directive = chat.operator_directive.strip() or "none"

        control_store: ControlPlaneStore | None = None
        control = {"agents_online": 0, "tasks": {"queued": 0, "leased": 0, "failed": 0}}
        queued_tasks: list[dict[str, Any]] = []
        leased_tasks: list[dict[str, Any]] = []
        try:
            control_store = ControlPlaneStore()
            control = control_store.overview(heartbeat_ttl_seconds=180)
            queued_tasks = control_store.list_tasks(status="queued", limit=3)
            leased_tasks = control_store.list_tasks(status="leased", limit=3)
        except Exception:
            pass

        tasks_overview = control.get("tasks") if isinstance(control.get("tasks"), dict) else {}
        proposals_snapshot = load_autonomy_proposals()
        proposals = proposals_snapshot.get("proposals") if isinstance(proposals_snapshot.get("proposals"), list) else []
        steering_questions = (
            proposals_snapshot.get("steering_questions")
            if isinstance(proposals_snapshot.get("steering_questions"), list)
            else []
        )

        lines = [
            f"<b>{html.escape(self._telegram_prompt_profile)} - /brief</b>",
            f"<i>{generated_at}</i>",
            (
                f"Mode={html.escape(chat.assistant_mode)} | Focus={html.escape(focus_project)} | "
                f"Directive={html.escape(directive)}"
            ),
            (
                "Prefs: "
                f"{html.escape(self._preferences_summary(chat))} | "
                f"checkin={'on' if chat.proactive_checkins_enabled else 'off'}:{int(chat.assistant_checkin_interval_minutes)}m | "
                f"sla={int(chat.decision_sla_minutes)}m"
            ),
            (
                "Control: "
                f"agents_online={int(control.get('agents_online', 0))} | "
                f"queued={int(tasks_overview.get('queued', 0))} | "
                f"leased={int(tasks_overview.get('leased', 0))} | "
                f"failed={int(tasks_overview.get('failed', 0))}"
            ),
            "Top queued:",
        ]
        if queued_tasks:
            for task in queued_tasks[:3]:
                lines.append(
                    f"- [{html.escape(str(task.get('task_id') or 'n/a'))}] "
                    f"{html.escape(str(task.get('title') or 'Untitled'))}"
                )
        else:
            lines.append("- none")

        lines.append("In progress:")
        if leased_tasks:
            for task in leased_tasks[:2]:
                lines.append(
                    f"- [{html.escape(str(task.get('task_id') or 'n/a'))}] "
                    f"{html.escape(str(task.get('title') or 'Untitled'))}"
                )
        else:
            lines.append("- none")

        lines.append("Decisions for you:")
        if proposals:
            for item in proposals[:2]:
                decision_id = html.escape(str(item.get("decision_id") or "decision"))
                title = html.escape(str(item.get("title") or "Decision needed"))
                lines.append(f"- {decision_id}: {title}")
                lines.append(f"  Reply: /decide {decision_id} 1")
        else:
            lines.append("- none")

        lines.append("Steering questions:")
        if steering_questions:
            for item in steering_questions[:2]:
                question_id = html.escape(str(item.get("question_id") or "question"))
                project_name = html.escape(str(item.get("project_name") or item.get("project_id") or "project"))
                lines.append(f"- {question_id} ({project_name})")
                lines.append(f"  Reply: /decide {question_id} 1")
        else:
            lines.append("- none")

        if chat.assistant_mode == "personal":
            lines.append("What I need from you now:")
            prompts: list[str] = []
            if proposals:
                item = proposals[0]
                decision_id = html.escape(str(item.get("decision_id") or "decision"))
                title = html.escape(str(item.get("title") or "Decision needed"))
                prompts.append(f"- Decision: {decision_id} ({title})")
                prompts.append(f"  Reply: /decide {decision_id} 1")
            if steering_questions:
                item = steering_questions[0]
                question_id = html.escape(str(item.get("question_id") or "question"))
                question_text = html.escape(str(item.get("question") or "Steering question"))
                prompts.append(f"- Question: {question_id} ({question_text[:120]})")
                prompts.append(f"  Reply: /decide {question_id} 1")
            if prompts:
                lines.extend(prompts)
            else:
                lines.append("- No decisions needed. I can keep executing.")

        lines.append(
            "Shortcuts: /inbox | /focus <project> | /autonomy | /deepresearch <topic> | /architecture | /agents"
        )
        return "\n".join(lines)[:3900]

    def _decision_inbox_message(self) -> str:
        snapshot = load_autonomy_proposals()
        proposals = snapshot.get("proposals") if isinstance(snapshot.get("proposals"), list) else []
        steering_questions = (
            snapshot.get("steering_questions")
            if isinstance(snapshot.get("steering_questions"), list)
            else []
        )
        generated_at = html.escape(str(snapshot.get("generated_at") or ""))

        lines = [
            f"<b>{html.escape(self._telegram_prompt_profile)} - /inbox</b>",
            f"<i>{generated_at}</i>",
            "Decision inbox:",
        ]

        if not proposals and not steering_questions:
            lines.append("- No open decisions or steering questions.")
            lines.append("Run /autonomy to generate the next set.")
            return "\n".join(lines)[:3900]

        for item in proposals[:4]:
            decision_id = str(item.get("decision_id") or "").strip()
            title = html.escape(str(item.get("title") or "Decision needed"))
            lines.append(f"- {html.escape(decision_id or 'decision')}: {title}")
            options = item.get("options") if isinstance(item.get("options"), list) else []
            for idx, option in enumerate(options[:3], start=1):
                lines.append(f"  {idx}. {html.escape(str(option))}")
            lines.append(f"  reply: /decide {html.escape(decision_id or 'decision')} 1")

        for item in steering_questions[:4]:
            question_id = str(item.get("question_id") or "").strip()
            project_name = html.escape(str(item.get("project_name") or item.get("project_id") or "project"))
            question_text = html.escape(str(item.get("question") or "Steering question"))
            lines.append(f"- {html.escape(question_id or 'question')} ({project_name}): {question_text}")
            options = item.get("options") if isinstance(item.get("options"), list) else []
            for idx, option in enumerate(options[:3], start=1):
                lines.append(f"  {idx}. {html.escape(str(option))}")
            lines.append(f"  reply: /decide {html.escape(question_id or 'question')} 1")

        return "\n".join(lines)[:3900]

    def _resolve_decision_choice(
        self,
        *,
        decision_id: str,
        choice_text: str,
    ) -> tuple[dict[str, Any] | None, str, str, str]:
        snapshot = load_autonomy_proposals()
        proposals = snapshot.get("proposals") if isinstance(snapshot.get("proposals"), list) else []
        steering_questions = (
            snapshot.get("steering_questions")
            if isinstance(snapshot.get("steering_questions"), list)
            else []
        )

        item: dict[str, Any] | None = None
        item_type = ""
        for candidate in proposals:
            if str(candidate.get("decision_id") or "").strip() == decision_id:
                item = candidate
                item_type = "decision"
                break
        if item is None:
            for candidate in steering_questions:
                if str(candidate.get("question_id") or "").strip() == decision_id:
                    item = candidate
                    item_type = "steering_question"
                    break
        if item is None:
            return None, "", "", "Decision/question ID not found in current inbox."

        options = item.get("options") if isinstance(item.get("options"), list) else []
        if not options:
            return None, "", "", "This decision has no selectable options."

        raw_choice = choice_text.strip()
        if raw_choice.isdigit():
            idx = int(raw_choice) - 1
            if 0 <= idx < len(options):
                selected = str(options[idx]).strip()
                return item, item_type, selected, ""
            return None, "", "", f"Option index out of range. Use 1..{len(options)}."

        lowered = raw_choice.lower()
        for option in options:
            option_text = str(option).strip()
            normalized = option_text.lower()
            if lowered == normalized or lowered in normalized:
                return item, item_type, option_text, ""

        return None, "", "", "Could not match that option. Use an index (1/2/3)."

    def _queue_decision_apply_task(
        self,
        *,
        chat_id: int,
        chat: ChatConfig,
        decision_id: str,
        item_type: str,
        selected_option: str,
        item: dict[str, Any],
    ) -> dict[str, Any]:
        project = chat.focus_project.strip() or "ai-project-management-system"
        title = str(item.get("title") or item.get("question") or decision_id).strip()
        instructions = (
            f"Apply approved {item_type} from Telegram.\n"
            f"Decision ID: {decision_id}\n"
            f"Selected option: {selected_option}\n"
            f"Context title/question: {title}\n"
            "Execute the approved path safely, update relevant tasks/cards, and post a concise completion note."
        )
        task = ControlPlaneStore().create_task(
            title=f"Apply approved decision: {decision_id}",
            payload={
                "task_type": "project_management",
                "source": "telegram.decision",
                "project": project,
                "instructions": instructions,
                "decision": {
                    "id": decision_id,
                    "type": item_type,
                    "selected_option": selected_option,
                    "title": title,
                },
            },
            required_capabilities=_single_agent_capabilities(["python", "git", "repo-write"]),
            priority=18,
            max_attempts=2,
            created_by=f"telegram:{chat_id}",
        )
        return task

    def _queue_quick_task_from_text(self, *, chat_id: int, chat: ChatConfig, task_text: str) -> dict[str, Any]:
        project = chat.focus_project.strip() or "ai-project-management-system"
        cleaned_task = re.sub(r"\s+", " ", task_text).strip()
        task = ControlPlaneStore().create_task(
            title=f"Telegram quick task: {cleaned_task[:90]}",
            payload={
                "task_type": "project_management",
                "source": "telegram.quick_task",
                "project": project,
                "instructions": cleaned_task,
                "requested_by_chat_id": chat_id,
                "assistant_mode": chat.assistant_mode,
            },
            required_capabilities=_single_agent_capabilities(["python", "git", "repo-write"]),
            priority=28,
            max_attempts=2,
            created_by=f"telegram:{chat_id}",
        )
        return task

    def _preferences_summary(self, chat: ChatConfig) -> str:
        return (
            f"tone={chat.preference_tone} | "
            f"risk={chat.preference_risk} | "
            f"coding={chat.preference_coding_style}"
        )

    def _decision_inbox_state(self, *, now: datetime | None = None) -> dict[str, Any]:
        ref_now = now or datetime.now(tz=UTC)
        snapshot = load_autonomy_proposals()
        proposals = snapshot.get("proposals") if isinstance(snapshot.get("proposals"), list) else []
        steering_questions = (
            snapshot.get("steering_questions")
            if isinstance(snapshot.get("steering_questions"), list)
            else []
        )
        generated_at_raw = str(snapshot.get("generated_at") or "")
        generated_at = _parse_utc_datetime(generated_at_raw)
        age_minutes = 0
        if generated_at is not None:
            age_minutes = max(0, int((ref_now - generated_at).total_seconds() // 60))
        return {
            "snapshot": snapshot,
            "proposals": proposals,
            "steering_questions": steering_questions,
            "open_count": len(proposals) + len(steering_questions),
            "generated_at": generated_at,
            "generated_at_raw": generated_at_raw,
            "age_minutes": age_minutes,
        }

    def _assistant_checkin_message(
        self,
        chat: ChatConfig,
        *,
        now: datetime | None = None,
        include_full_control: bool = False,
    ) -> tuple[str, bool]:
        ref_now = now or datetime.now(tz=UTC)
        focus_project = chat.focus_project.strip() or "none"
        directive = chat.operator_directive.strip() or "none"
        state = self._decision_inbox_state(now=ref_now)
        proposals = state["proposals"] if isinstance(state.get("proposals"), list) else []
        steering = state["steering_questions"] if isinstance(state.get("steering_questions"), list) else []
        open_count = int(state.get("open_count", 0))
        age_minutes = int(state.get("age_minutes", 0))
        sla_minutes = max(30, int(chat.decision_sla_minutes or 180))
        sla_breached = open_count > 0 and age_minutes >= sla_minutes

        control = {"agents_online": 0, "tasks": {"queued": 0, "leased": 0, "failed": 0}}
        next_actions: list[dict[str, Any]] = []
        try:
            control = ControlPlaneStore().overview(heartbeat_ttl_seconds=180)
        except Exception:
            pass
        try:
            projects = get_projects_overview(force_refresh=True)
            if isinstance(projects, dict) and isinstance(projects.get("next_actions"), list):
                next_actions = [row for row in projects["next_actions"] if isinstance(row, dict)]
        except Exception:
            next_actions = []

        tasks_overview = control.get("tasks") if isinstance(control.get("tasks"), dict) else {}
        lines = [
            f"<b>{html.escape(self._telegram_prompt_profile)} - /checkin</b>",
            f"<i>{ref_now.strftime('%Y-%m-%d %H:%M UTC')}</i>",
            (
                f"Mode={html.escape(chat.assistant_mode)} | "
                f"Focus={html.escape(focus_project)} | "
                f"Prefs={html.escape(self._preferences_summary(chat))}"
            ),
            f"Directive={html.escape(directive)}",
        ]

        if include_full_control:
            lines.append(
                "Control: "
                f"agents_online={int(control.get('agents_online', 0))} | "
                f"queued={int(tasks_overview.get('queued', 0))} | "
                f"leased={int(tasks_overview.get('leased', 0))} | "
                f"failed={int(tasks_overview.get('failed', 0))}"
            )

        lines.append(
            f"Decision inbox: open={open_count} | age={age_minutes}m | sla={sla_minutes}m"
        )
        if sla_breached:
            lines.append("SLA alert: decision backlog exceeded threshold; steer now to avoid stall.")

        lines.append("What I need from you:")
        if proposals:
            item = proposals[0]
            decision_id = html.escape(str(item.get("decision_id") or "decision"))
            title = html.escape(str(item.get("title") or "Decision needed"))
            lines.append(f"- Decision {decision_id}: {title}")
            lines.append(f"  reply: /decide {decision_id} 1")
        if steering:
            item = steering[0]
            question_id = html.escape(str(item.get("question_id") or "question"))
            question = html.escape(str(item.get("question") or "Steering question"))
            lines.append(f"- Question {question_id}: {question[:140]}")
            lines.append(f"  reply: /decide {question_id} 1")
        if not proposals and not steering:
            lines.append("- No pending decisions. I can keep executing autonomously.")

        lines.append("Next action:")
        if next_actions:
            action = next_actions[0]
            action_id = html.escape(str(action.get("id") or "n/a"))
            title = html.escape(str(action.get("title") or "Untitled action"))
            detail = html.escape(str(action.get("detail") or ""))
            if detail:
                lines.append(f"- [{action_id}] {title} | {detail[:120]}")
            else:
                lines.append(f"- [{action_id}] {title}")
        else:
            lines.append("- Run /autonomy or send task: <what to build/fix>")

        lines.append("Shortcuts: /inbox | /brief | /prefs | /setcheckin 120 | /setsla 180")
        return "\n".join(lines)[:3900], sla_breached

    def _set_preferences_from_pairs(self, chat: ChatConfig, pairs: dict[str, str]) -> bool:
        changed = False
        tone = pairs.get("tone")
        if tone is not None:
            normalized = _normalize_preference_tone(tone)
            if chat.preference_tone != normalized:
                chat.preference_tone = normalized
                changed = True
        risk = pairs.get("risk")
        if risk is not None:
            normalized = _normalize_preference_risk(risk)
            if chat.preference_risk != normalized:
                chat.preference_risk = normalized
                changed = True
        coding = pairs.get("coding")
        if coding is None:
            coding = pairs.get("coding_style")
        if coding is not None:
            normalized = _normalize_preference_coding_style(coding)
            if chat.preference_coding_style != normalized:
                chat.preference_coding_style = normalized
                changed = True
        return changed

    async def _persist_assistant_checkin_timestamps(
        self,
        chat: ChatConfig,
        *,
        ts: datetime,
        sla_reminder: bool = False,
    ) -> None:
        try:
            if hasattr(self._store, "set_last_assistant_checkin_at"):
                await asyncio.to_thread(  # type: ignore[attr-defined]
                    self._store.set_last_assistant_checkin_at,
                    chat_id=chat.chat_id,
                    ts=ts,
                )
            else:
                chat.last_assistant_checkin_at = ts
        except Exception as exc:
            logger.warning("failed setting last_assistant_checkin_at for chat=%s: %s", chat.chat_id, exc)

        if sla_reminder:
            try:
                if hasattr(self._store, "set_last_decision_sla_reminder_at"):
                    await asyncio.to_thread(  # type: ignore[attr-defined]
                        self._store.set_last_decision_sla_reminder_at,
                        chat_id=chat.chat_id,
                        ts=ts,
                    )
                else:
                    chat.last_decision_sla_reminder_at = ts
            except Exception as exc:
                logger.warning(
                    "failed setting last_decision_sla_reminder_at for chat=%s: %s",
                    chat.chat_id,
                    exc,
                )

        if not hasattr(self._store, "set_last_assistant_checkin_at"):
            await asyncio.to_thread(self._save_chat, chat)

    def _recent_telegram_chat_ids(self, *, limit: int = 400) -> list[int]:
        rows: list[dict[str, Any]] = []
        try:
            rows = recent_events(limit=limit, category="telegram")
        except TypeError:
            try:
                rows = recent_events(limit=limit)
            except Exception:
                rows = []
        except Exception:
            rows = []

        seen: set[int] = set()
        out: list[int] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            payload = row.get("payload") if isinstance(row.get("payload"), dict) else {}
            candidates = [
                payload.get("chat_id"),
                payload.get("telegram_chat_id"),
                row.get("chat_id"),
            ]
            for candidate in candidates:
                try:
                    chat_id = int(candidate)
                except Exception:
                    continue
                if chat_id in seen:
                    continue
                seen.add(chat_id)
                out.append(chat_id)
        return out

    def _state_message(self) -> str:
        generated_at = datetime.now(tz=UTC).strftime("%Y-%m-%d %H:%M UTC")
        projects = get_projects_overview(force_refresh=True)
        board = projects.get("board") if isinstance(projects.get("board"), dict) else {}
        counts = board.get("counts") if isinstance(board.get("counts"), dict) else {}
        next_actions = projects.get("next_actions") if isinstance(projects.get("next_actions"), list) else []

        control_store: ControlPlaneStore | None = None
        control = {"agents_online": 0, "tasks": {"queued": 0, "leased": 0, "failed": 0}}
        try:
            control_store = ControlPlaneStore()
            control = control_store.overview(heartbeat_ttl_seconds=180)
        except Exception:
            pass
        tasks_overview = control.get("tasks") if isinstance(control.get("tasks"), dict) else {}
        queued_tasks: list[dict[str, Any]] = []
        leased_tasks: list[dict[str, Any]] = []
        if control_store and hasattr(control_store, "list_tasks"):
            try:
                queued_tasks = control_store.list_tasks(status="queued", limit=3)
                leased_tasks = control_store.list_tasks(status="leased", limit=3)
            except Exception as exc:
                logger.warning("failed loading task IDs for /overview: %s", exc)

        try:
            router = get_router_overview(force_refresh=True)
        except Exception:
            router = {"summary": {}}
        router_summary = router.get("summary") if isinstance(router.get("summary"), dict) else {}

        try:
            proposals_snapshot = load_autonomy_proposals()
        except Exception:
            proposals_snapshot = {"proposals": []}
        proposals = proposals_snapshot.get("proposals") if isinstance(proposals_snapshot.get("proposals"), list) else []
        steering_questions = (
            proposals_snapshot.get("steering_questions")
            if isinstance(proposals_snapshot.get("steering_questions"), list)
            else []
        )

        agents_online = int(control.get("agents_online", 0))
        tasks_queued = int(tasks_overview.get("queued", 0))
        tasks_leased = int(tasks_overview.get("leased", 0))
        tasks_failed = int(tasks_overview.get("failed", 0))
        board_blocked = int(counts.get("blocked", 0))
        memberships_ready = int(router_summary.get("membership_ready_count", 0))
        status = self._runtime_status_label(
            agents_online=agents_online,
            tasks_queued=tasks_queued,
            tasks_failed=tasks_failed,
            board_blocked=board_blocked,
            memberships_ready=memberships_ready,
        )

        blockers: list[str] = []
        if tasks_queued > 0 and agents_online <= 0:
            blockers.append("Queued tasks are waiting because no agents are online.")
        if tasks_failed > 0:
            blockers.append(f"{tasks_failed} failed task(s) need root-cause triage and safe retry handling.")
        unavailable = int(router_summary.get("membership_unavailable_count", 0))
        if memberships_ready <= 0:
            blockers.append("Router reports zero ready memberships for task execution.")
        elif unavailable > 0:
            blockers.append(f"{unavailable} memberships are unavailable and reduce routing resilience.")
        if board_blocked > 0:
            blockers.append(f"Board has {board_blocked} blocked card(s) needing owner action.")
        if not blockers:
            blockers.append("No active blocker detected.")

        lines = [
            f"<b>{html.escape(self._telegram_prompt_profile)} - /overview (System State)</b>",
            f"<i>{generated_at}</i>",
            f"1) Status: {status}",
            (
                "2) Control Metrics: "
                f"agents_online={agents_online} | queued={tasks_queued} | leased={tasks_leased} "
                f"| failed={tasks_failed} | memberships_ready={memberships_ready}"
            ),
            "3) Task IDs:",
            f"- queued: {html.escape(self._task_id_list(queued_tasks))}",
            f"- leased: {html.escape(self._task_id_list(leased_tasks))}",
            "4) Blockers and Root Cause:",
        ]
        lines.extend([f"- {html.escape(item)}" for item in blockers])

        lines.append("5) Decisions Needed:")
        decision_lines = self._decision_blocks(proposals, limit=2)
        if decision_lines:
            lines.extend(decision_lines)
        else:
            lines.append("- None.")

        lines.append("6) Steering Questions:")
        steering_lines = self._steering_question_blocks(steering_questions, limit=2)
        if steering_lines:
            lines.extend(steering_lines)
        else:
            lines.append("- None.")

        lines.append("7) Next 2 Actions:")
        if next_actions:
            for action in next_actions[:2]:
                action_id = html.escape(str(action.get("id") or "n/a"))
                title = html.escape(str(action.get("title") or "Untitled action"))
                detail = html.escape(str(action.get("detail") or ""))
                if detail:
                    lines.append(f"- [{action_id}] {title} | {detail[:120]}")
                else:
                    lines.append(f"- [{action_id}] {title}")
        else:
            lines.append("- Run /autonomy to execute one debug and decision cycle.")
            lines.append("- Resolve the top queued task and recheck /overview.")

        return "\n".join(lines)[:3900]

    def _autonomy_cycle_message(self, report: dict[str, Any]) -> str:
        generated_at = str(report.get("generated_at") or "").replace("T", " ").replace("+00:00", " UTC")
        created = report.get("created_tasks") if isinstance(report.get("created_tasks"), list) else []
        proposals = report.get("proposals") if isinstance(report.get("proposals"), list) else []
        steering_questions = (
            report.get("steering_questions") if isinstance(report.get("steering_questions"), list) else []
        )
        observations = report.get("observations") if isinstance(report.get("observations"), list) else []
        metrics = report.get("metrics") if isinstance(report.get("metrics"), dict) else {}

        agents_online = int(metrics.get("agents_online", 0))
        tasks_queued = int(metrics.get("tasks_queued", 0))
        tasks_leased = int(metrics.get("tasks_leased", 0))
        tasks_failed = int(metrics.get("tasks_failed", 0))
        memberships_ready = int(metrics.get("memberships_ready", 0))
        board_blocked = int(metrics.get("board_blocked", 0))
        status = self._runtime_status_label(
            agents_online=agents_online,
            tasks_queued=tasks_queued,
            tasks_failed=tasks_failed,
            board_blocked=board_blocked,
            memberships_ready=memberships_ready,
        )

        lines = [
            f"<b>{html.escape(self._telegram_prompt_profile)} - /autonomy (Autonomy Cycle)</b>",
            f"<i>{html.escape(generated_at) if generated_at else ''}</i>",
            f"1) Status: {status}",
            (
                "2) Control Metrics: "
                f"agents_online={agents_online} | queued={tasks_queued} | leased={tasks_leased} "
                f"| failed={tasks_failed} | memberships_ready={memberships_ready}"
            ),
            "3) Autonomous Actions Completed (task IDs):",
        ]

        if created:
            for item in created[:5]:
                title = html.escape(str(item.get("title") or "Untitled task"))
                task_id = html.escape(str(item.get("task_id") or "n/a"))
                key = html.escape(str(item.get("key") or ""))
                if key:
                    lines.append(f"- [{task_id}] {title} | key={key}")
                else:
                    lines.append(f"- [{task_id}] {title}")
        else:
            lines.append("- None.")

        lines.append("4) Blockers and Root Cause:")
        if observations:
            for note in observations[:4]:
                lines.append(f"- {html.escape(str(note))}")
        else:
            lines.append("- No blocker detected in this cycle.")

        lines.append("5) Decisions Needed:")
        decision_lines = self._decision_blocks(proposals, limit=2)
        if decision_lines:
            lines.extend(decision_lines)
        else:
            lines.append("- None.")

        lines.append("6) Steering Questions:")
        steering_lines = self._steering_question_blocks(steering_questions, limit=3)
        if steering_lines:
            lines.extend(steering_lines)
        else:
            lines.append("- None.")

        lines.append("7) Next 2 Actions:")
        if created:
            for item in created[:2]:
                task_id = html.escape(str(item.get("task_id") or "n/a"))
                title = html.escape(str(item.get("title") or "autonomy task"))
                lines.append(f"- Execute [{task_id}] {title}.")
        else:
            lines.append("- Resolve open decision blocks and rerun /autonomy.")
            lines.append("- Keep heartbeat coverage active for the next cycle window.")

        lines.append("Use /setdirective to set policy decisions for the next cycle.")
        return "\n".join(lines)[:3900]

    def _run_autonomy_cycle_once(self, actor: str) -> dict[str, Any]:
        projects = get_projects_overview(force_refresh=True)
        router = get_router_overview(force_refresh=True)
        control_store = ControlPlaneStore()
        return run_autonomy_cycle(
            control_store=control_store,
            projects_overview=projects if isinstance(projects, dict) else {},
            router_overview=router if isinstance(router, dict) else {},
            actor=actor,
        )

    def _is_authorized_sender(self, message: dict[str, Any], chat_id: int) -> bool:
        if not self._allowed_user_ids and not self._allowed_chat_ids:
            return True
        if chat_id in self._allowed_chat_ids:
            return True
        sender = message.get("from") or {}
        sender_id = sender.get("id")
        try:
            return int(sender_id) in self._allowed_user_ids
        except Exception:
            return False

    def _remember_update_id(self, update_id: int) -> bool:
        """Return True if update is new; False if it's a duplicate."""
        if update_id in self._recent_update_id_set:
            return False
        self._recent_update_ids.append(update_id)
        self._recent_update_id_set.add(update_id)
        while len(self._recent_update_ids) > self._max_recent_updates:
            old = self._recent_update_ids.popleft()
            self._recent_update_id_set.discard(old)
        return True

    async def handle_update(self, update: dict[str, Any]) -> dict[str, Any]:
        update_id = update.get("update_id")
        if isinstance(update_id, int) and not self._remember_update_id(update_id):
            return {"status": "ignored", "reason": "duplicate-update"}

        message = _extract_message(update)
        if not message:
            return {"status": "ignored", "reason": "no-message"}

        try:
            chat_id = int(message["chat"]["id"])
        except Exception:
            return {"status": "ignored", "reason": "invalid-chat"}

        if not self._is_authorized_sender(message, chat_id):
            logger.warning("blocked telegram update from unauthorized sender chat_id=%s", chat_id)
            return {"status": "ignored", "reason": "unauthorized"}

        text = (message.get("text") or "").strip()
        if not text:
            return {"status": "ignored", "reason": "empty-text"}

        command, args = _parse_command(text)
        if not command.startswith("/"):
            return await self._handle_non_command_message(chat_id, text)

        sender = message.get("from") or {}
        sender_id = str(sender.get("id") or "")
        self._record_event(
            "telegram.command",
            source="telegram.webhook",
            actor=sender_id or "unknown",
            category="telegram",
            status="received",
            message=f"{command} command received",
            payload={"chat_id": chat_id, "command": command, "args": args[:240]},
        )

        await self._execute_command(chat_id, command, args)
        return {"status": "ok", "chat_id": chat_id, "command": command}

    async def _handle_non_command_message(self, chat_id: int, text: str) -> dict[str, Any]:
        cleaned = re.sub(r"\s+", " ", text).strip()
        if len(cleaned) < 8:
            return {"status": "ignored", "reason": "not-command"}

        chat = await asyncio.to_thread(self._load_chat, chat_id)
        lowered = cleaned.lower()

        # Telegram-first assistant shortcuts for plain text.
        if lowered.startswith("task:") or lowered.startswith("todo:"):
            body = cleaned.split(":", maxsplit=1)[1].strip()
            if not body:
                await self._send(chat_id, "Quick task format: task: <what to do>")
                return {"status": "ok", "chat_id": chat_id, "command": "quick-task-help"}
            task = await asyncio.to_thread(self._queue_quick_task_from_text, chat_id=chat_id, chat=chat, task_text=body)
            await self._send(
                chat_id,
                (
                    "<b>Quick task queued</b>\n"
                    f"- task_id={html.escape(str(task.get('task_id') or 'n/a'))}\n"
                    f"- title={html.escape(str(task.get('title') or 'n/a'))}\n"
                    f"- project={html.escape(chat.focus_project or 'ai-project-management-system')}"
                ),
            )
            return {"status": "ok", "chat_id": chat_id, "command": "quick-task"}

        if lowered.startswith("focus project:"):
            focus_value = cleaned.split(":", maxsplit=1)[1].strip()
            if not focus_value:
                await self._send(chat_id, "Focus format: focus project: <project-id-or-name>")
                return {"status": "ok", "chat_id": chat_id, "command": "focus-help"}
            chat.focus_project = focus_value[:120]
            await asyncio.to_thread(self._save_chat, chat)
            await self._send(chat_id, f"Focus project updated to: <b>{html.escape(chat.focus_project)}</b>")
            return {"status": "ok", "chat_id": chat_id, "command": "focus-text"}

        if lowered.startswith("prefs:") or lowered.startswith("preferences:"):
            raw_pairs = cleaned.split(":", maxsplit=1)[1].strip()
            matches = re.findall(r"(tone|risk|coding|coding_style)\s*=\s*([a-zA-Z_-]+)", raw_pairs, flags=re.IGNORECASE)
            if not matches:
                await self._send(chat_id, "Preferences format: prefs: tone=concise risk=balanced coding=pragmatic")
                return {"status": "ok", "chat_id": chat_id, "command": "prefs-help"}
            pairs = {str(k).strip().lower(): str(v).strip().lower() for k, v in matches}
            changed = self._set_preferences_from_pairs(chat, pairs)
            if changed:
                await asyncio.to_thread(self._save_chat, chat)
            await self._send(chat_id, f"Preferences updated: <b>{html.escape(self._preferences_summary(chat))}</b>")
            return {"status": "ok", "chat_id": chat_id, "command": "prefs-text"}

        inline_decision = _extract_inline_decision_choice(cleaned)
        if inline_decision:
            decision_id, choice_text = inline_decision
            item, item_type, selected_option, error = await asyncio.to_thread(
                self._resolve_decision_choice,
                decision_id=decision_id,
                choice_text=choice_text,
            )
            if error:
                await self._send(chat_id, html.escape(error))
                return {"status": "ok", "chat_id": chat_id, "command": "decide-text-error"}

            assert item is not None
            await self._save_directive(
                chat,
                f"{chat.operator_directive} | decision:{decision_id} => {selected_option}".strip(" |"),
            )
            apply_task = await asyncio.to_thread(
                self._queue_decision_apply_task,
                chat_id=chat_id,
                chat=chat,
                decision_id=decision_id,
                item_type=item_type,
                selected_option=selected_option,
                item=item,
            )
            await self._send(
                chat_id,
                (
                    "<b>Decision captured and queued</b>\n"
                    f"- id={html.escape(decision_id)}\n"
                    f"- selected={html.escape(selected_option)}\n"
                    f"- apply_task_id={html.escape(str(apply_task.get('task_id') or 'n/a'))}"
                ),
            )
            return {"status": "ok", "chat_id": chat_id, "command": "decide-text"}

        inferred_command, inferred_args = _infer_text_command(cleaned)
        if inferred_command:
            await self._execute_command(chat_id, inferred_command, inferred_args)
            return {"status": "ok", "chat_id": chat_id, "command": f"text-{inferred_command.lstrip('/')}"}

        saved = await self._record_operator_directive(chat_id, cleaned)
        if saved:
            return {"status": "ok", "chat_id": chat_id, "command": "directive-text"}
        return {"status": "ignored", "reason": "not-command"}

    def _load_chat(self, chat_id: int) -> ChatConfig:
        try:
            existing = self._store.get(chat_id)
        except Exception as exc:
            logger.warning("failed loading chat from store chat_id=%s: %s", chat_id, exc)
            existing = None
        if existing is not None:
            existing.assistant_mode = _normalize_assistant_mode(existing.assistant_mode)
            return existing
        created = default_chat_config(chat_id, self._settings)
        created.assistant_mode = _normalize_assistant_mode(created.assistant_mode)
        try:
            self._store.save(created)
        except Exception as exc:
            logger.warning("failed creating default chat config chat_id=%s: %s", chat_id, exc)
        return created

    def _save_chat(self, chat: ChatConfig) -> None:
        try:
            self._store.save(chat)
        except Exception as exc:
            logger.warning("failed saving chat config chat_id=%s: %s", chat.chat_id, exc)

    async def _send(self, chat_id: int, text: str) -> None:
        if not self._telegram.enabled:
            logger.info("telegram disabled; skipping send to chat_id=%s", chat_id)
            return
        try:
            await self._telegram.send_message(chat_id, text)
        except Exception as exc:
            logger.exception("failed sending message to %s: %s", chat_id, exc)

    async def _execute_command(self, chat_id: int, command: str, args: str) -> None:
        chat = await asyncio.to_thread(self._load_chat, chat_id)

        if command in {"/start", "/help"}:
            help_text = (
                f"<b>{html.escape(self._telegram_prompt_profile)}</b>\n"
                "Telegram-first AI project manager and personal assistant.\n\n"
                "Commands:\n"
                "/brief - compact personal briefing (best next actions)\n"
                "/next - alias for /brief\n"
                "/checkin - immediate personal assistant check-in + decisions\n"
                "/overview - full system state + tool inventory + research paths + policy\n"
                "/state - alias for /overview\n"
                "/architecture - live architecture and topology snapshot\n"
                "/agents - live fleet status and stale agent candidates\n"
                "/cleanupagents <dry|apply> - prune stale non-policy agents\n"
                "/rari <status|enforce> - manage dual-Pi executor policy\n"
                "/inbox - open decisions and steering questions with reply templates\n"
                "/questions - alias for /inbox\n"
                "/prefs - show/update assistant preferences (tone/risk/coding)\n"
                "/setcheckin <minutes|off> - proactive check-in cadence\n"
                "/setsla <minutes> - decision SLA reminder threshold\n"
                "/skills - enumerate Kimi tools/skills library snapshot\n"
                "/alphastream [top_k] - unified alpha stream (frontend + agent/trader routing tags)\n"
                "/digest - run immediate digest\n"
                "/heartbeat - run immediate heartbeat status\n"
                "/autonomy - run proactive debug + decision cycle\n"
                "/deepresearch [topic|status] - queue one deep-research run or view save status\n"
                "/decide <id> <1|2|3> - approve an inbox decision option\n"
                "/focus <project|clear> - set project focus for assistant context\n"
                "/mode <personal|operator> - switch Telegram response style\n"
                "/watchlist - show tracked assets/keywords\n"
                "/setaster BTC,ETH,SOL - set Aster asset list\n"
                "/setlighter BTC,ETH,ARB - set Lighter asset list\n"
                "/setkeywords fed,cpi,etf - set extra macro keywords\n"
                "/setdirective focus on regulation risk - set strategy directive\n"
                "/directive - show active strategy directive\n"
                "/setheartbeat 30 - set heartbeat interval (minutes)\n"
                "/pauseheartbeat - disable scheduled heartbeat updates\n"
                "/resumeheartbeat - enable scheduled heartbeat updates\n"
                "/subscribe - enable scheduled digests\n"
                "/unsubscribe - pause scheduled digests\n"
                "/reset - restore defaults\n\n"
                "Plain-text shortcuts:\n"
                "- task: <what to do> (queue quick task)\n"
                "- focus project: <project>\n\n"
                "Natural language shortcuts:\n"
                "- \"what next\" / \"next steps\" -> /brief\n"
                "- \"status\" / \"overview\" -> /overview\n"
                "- \"decisions\" / \"question inbox\" -> /inbox\n"
                "- \"assistant check-in\" -> /checkin\n"
                "- \"deep research: <topic>\" -> /deepresearch <topic>\n"
                "- \"decide <id> <1|2|3>\" -> decision + apply task\n\n"
                "Policy:\n"
                "- Daily research: memory/kimi-deep-research/YYYY-MM-DD.md\n"
                "- Tool catalog: app/data/kimi_tools_catalog.json\n"
                f"- Runtime prompt: {html.escape(self._telegram_runtime_prompt.get('path', 'app/data/crypton_telegram_agent_prompt.md'))}"
            )
            await self._send(chat_id, help_text)
            return

        if command == "/subscribe":
            chat.subscribed = True
            await asyncio.to_thread(self._save_chat, chat)
            await self._send(chat_id, "Subscribed. Scheduled digests are enabled.")
            return

        if command == "/unsubscribe":
            chat.subscribed = False
            await asyncio.to_thread(self._save_chat, chat)
            await self._send(chat_id, "Unsubscribed. Scheduled digests are paused.")
            return

        if command == "/reset":
            reset = default_chat_config(chat_id, self._settings)
            await asyncio.to_thread(self._save_chat, reset)
            await self._send(chat_id, "Watchlist and heartbeat settings reset to defaults.")
            await self._send(chat_id, format_watchlist_message(reset))
            return

        if command == "/watchlist":
            await self._send(chat_id, format_watchlist_message(chat))
            return

        if command == "/directive":
            if chat.operator_directive:
                safe = html.escape(chat.operator_directive)
                await self._send(chat_id, f"<b>Active directive</b>\n{safe}")
            else:
                await self._send(chat_id, "No directive set. Use /setdirective <instructions>.")
            return

        if command == "/prefs":
            cleaned_args = re.sub(r"\s+", " ", args).strip()
            if not cleaned_args or cleaned_args.lower() in {"show", "status"}:
                await self._send(
                    chat_id,
                    (
                        "<b>Assistant preferences</b>\n"
                        f"- {html.escape(self._preferences_summary(chat))}\n"
                        "Update with:\n"
                        "- /prefs tone <concise|balanced|detailed>\n"
                        "- /prefs risk <conservative|balanced|aggressive>\n"
                        "- /prefs coding <pragmatic|clean_architecture|exploratory>"
                    ),
                )
                return
            tokens = cleaned_args.split(maxsplit=1)
            if len(tokens) < 2:
                await self._send(chat_id, "Usage: /prefs tone concise")
                return
            key = tokens[0].strip().lower()
            value = tokens[1].strip()
            pairs: dict[str, str] = {}
            if key in {"tone", "risk", "coding", "coding_style"}:
                pairs[key] = value
            else:
                await self._send(chat_id, "Unknown preference key. Use tone, risk, or coding.")
                return
            changed = self._set_preferences_from_pairs(chat, pairs)
            if changed:
                await asyncio.to_thread(self._save_chat, chat)
            await self._send(chat_id, f"Preferences now: <b>{html.escape(self._preferences_summary(chat))}</b>")
            return

        if command == "/mode":
            requested = args.strip().lower()
            if requested not in {"personal", "operator"}:
                await self._send(
                    chat_id,
                    (
                        "<b>Assistant mode</b>\n"
                        f"- current={html.escape(chat.assistant_mode)}\n"
                        "- set with: /mode personal OR /mode operator"
                    ),
                )
                return
            chat.assistant_mode = _normalize_assistant_mode(requested)
            await asyncio.to_thread(self._save_chat, chat)
            await self._send(chat_id, f"Assistant mode updated to <b>{html.escape(chat.assistant_mode)}</b>.")
            return

        if command == "/focus":
            focus_value = re.sub(r"\s+", " ", args).strip()
            if not focus_value:
                current_focus = chat.focus_project.strip() or "none"
                await self._send(chat_id, f"Current focus project: <b>{html.escape(current_focus)}</b>")
                return
            if focus_value.lower() in {"clear", "none", "off"}:
                chat.focus_project = ""
                await asyncio.to_thread(self._save_chat, chat)
                await self._send(chat_id, "Focus project cleared.")
                return
            chat.focus_project = focus_value[:120]
            await asyncio.to_thread(self._save_chat, chat)
            await self._send(chat_id, f"Focus project set to <b>{html.escape(chat.focus_project)}</b>.")
            return

        if command == "/setaster":
            parsed = _parse_csv(args, upper=True)
            if not parsed:
                await self._send(chat_id, "Usage: /setaster BTC,ETH,SOL")
                return
            chat.aster_assets = parsed
            await asyncio.to_thread(self._save_chat, chat)
            await self._send(chat_id, f"Updated Aster assets: {', '.join(parsed)}")
            return

        if command == "/setlighter":
            parsed = _parse_csv(args, upper=True)
            if not parsed:
                await self._send(chat_id, "Usage: /setlighter BTC,ETH,ARB")
                return
            chat.lighter_assets = parsed
            await asyncio.to_thread(self._save_chat, chat)
            await self._send(chat_id, f"Updated Lighter assets: {', '.join(parsed)}")
            return

        if command == "/setkeywords":
            parsed = _parse_csv(args, upper=False)
            if not parsed:
                await self._send(chat_id, "Usage: /setkeywords fed,cpi,etf")
                return
            chat.extra_keywords = parsed
            await asyncio.to_thread(self._save_chat, chat)
            await self._send(chat_id, f"Updated keywords: {', '.join(parsed)}")
            return

        if command == "/setdirective":
            if not args.strip():
                await self._send(chat_id, "Usage: /setdirective focus on macro risk and BTC trend")
                return
            await self._save_directive(chat, args)
            await self._send(chat_id, "Directive saved and will be reflected in heartbeats and digests.")
            return

        if command == "/setheartbeat":
            parsed = args.strip()
            if not parsed.isdigit():
                await self._send(chat_id, "Usage: /setheartbeat 30 (minutes, range 5-1440)")
                return
            minutes = int(parsed)
            if minutes < 5 or minutes > 1440:
                await self._send(chat_id, "Heartbeat interval must be between 5 and 1440 minutes.")
                return
            chat.heartbeat_interval_minutes = minutes
            chat.heartbeat_enabled = True
            await asyncio.to_thread(self._save_chat, chat)
            await self._send(chat_id, f"Heartbeat interval set to {minutes} minutes.")
            return

        if command == "/pauseheartbeat":
            chat.heartbeat_enabled = False
            await asyncio.to_thread(self._save_chat, chat)
            await self._send(chat_id, "Scheduled heartbeats paused.")
            return

        if command == "/resumeheartbeat":
            chat.heartbeat_enabled = True
            if chat.heartbeat_interval_minutes < 5:
                chat.heartbeat_interval_minutes = self._default_heartbeat_interval_minutes
            await asyncio.to_thread(self._save_chat, chat)
            await self._send(chat_id, f"Scheduled heartbeats enabled every {chat.heartbeat_interval_minutes} minutes.")
            return

        if command == "/setcheckin":
            parsed = args.strip().lower()
            if not parsed:
                await self._send(
                    chat_id,
                    (
                        "<b>Assistant check-ins</b>\n"
                        f"- enabled={'yes' if chat.proactive_checkins_enabled else 'no'}\n"
                        f"- interval={int(chat.assistant_checkin_interval_minutes)} minutes\n"
                        "Set with /setcheckin 120 or /setcheckin off"
                    ),
                )
                return
            if parsed in {"off", "pause", "disable"}:
                chat.proactive_checkins_enabled = False
                await asyncio.to_thread(self._save_chat, chat)
                await self._send(chat_id, "Assistant check-ins disabled.")
                return
            if not parsed.isdigit():
                await self._send(chat_id, "Usage: /setcheckin 120 or /setcheckin off")
                return
            minutes = max(15, min(int(parsed), 1440))
            chat.proactive_checkins_enabled = True
            chat.assistant_checkin_interval_minutes = minutes
            await asyncio.to_thread(self._save_chat, chat)
            await self._send(chat_id, f"Assistant check-ins enabled every {minutes} minutes.")
            return

        if command == "/setsla":
            parsed = args.strip()
            if not parsed or not parsed.isdigit():
                await self._send(chat_id, "Usage: /setsla 180 (minutes, range 30-1440)")
                return
            minutes = max(30, min(int(parsed), 1440))
            chat.decision_sla_minutes = minutes
            await asyncio.to_thread(self._save_chat, chat)
            await self._send(chat_id, f"Decision SLA reminder threshold set to {minutes} minutes.")
            return

        if command == "/digest":
            await self._send(chat_id, "Running digest now...")
            await self.send_digest_to_chat(chat)
            return

        if command == "/alphastream":
            parsed = args.strip()
            top_k = None
            if parsed:
                if not parsed.isdigit():
                    await self._send(chat_id, "Usage: /alphastream OR /alphastream 8")
                    return
                top_k = max(1, min(int(parsed), 15))
            await self._send(chat_id, "Building unified alpha stream snapshot...")
            await self.send_alpha_stream_to_chat(chat, top_k=top_k)
            return

        if command in {"/heartbeat", "/status"}:
            await self._send(chat_id, "Running heartbeat now...")
            await self.send_heartbeat_to_chat(chat, suppress_if_too_soon=False)
            return

        if command in {"/state", "/overview"}:
            await self._send(chat_id, "Building full system state snapshot...")
            message = await asyncio.to_thread(self._state_message)
            await self._send(chat_id, message)
            return

        if command in {"/architecture", "/topology"}:
            refresh = args.strip().lower() in {"refresh", "force", "now"}
            await self._send(chat_id, "Building architecture and topology snapshot...")
            message = await asyncio.to_thread(self._architecture_message, refresh=refresh)
            await self._send(chat_id, message)
            return

        if command in {"/agents", "/fleet"}:
            await self._send(chat_id, "Loading live agent fleet state...")
            message = await asyncio.to_thread(self._agents_message, stale_after_seconds=3600)
            await self._send(chat_id, message)
            return

        if command in {"/cleanupagents", "/cleanup_agents"}:
            mode = args.strip().lower()
            if mode in {"", "help"}:
                await self._send(chat_id, "Usage: /cleanupagents dry OR /cleanupagents apply")
                return
            dry_run = mode not in {"apply", "run", "force", "yes"}
            action_text = "Previewing stale agent cleanup..." if dry_run else "Applying stale agent cleanup..."
            await self._send(chat_id, action_text)
            result = await asyncio.to_thread(
                self._cleanup_stale_agents,
                stale_after_seconds=3600,
                dry_run=dry_run,
                actor=f"telegram:{chat_id}",
            )
            await self._send(chat_id, self._cleanup_agents_message(result))
            return

        if command == "/rari":
            subcommand = args.strip().lower()
            if subcommand in {"", "status"}:
                await self._send(chat_id, "Checking dual-Pi policy and fleet...")
                message = await asyncio.to_thread(self._rari_status_message)
                await self._send(chat_id, message)
                return
            if subcommand in {"enforce", "apply", "on"}:
                await self._send(chat_id, "Enforcing dual-Pi executor policy...")
                message = await asyncio.to_thread(self._enforce_rari_policy_message, actor=f"telegram:{chat_id}")
                await self._send(chat_id, message)
                return
            await self._send(chat_id, "Usage: /rari status OR /rari enforce")
            return

        if command in {"/brief", "/next"}:
            await self._send(chat_id, "Building your personal briefing...")
            message = await asyncio.to_thread(self._brief_message, chat)
            await self._send(chat_id, message)
            return

        if command == "/checkin":
            await self._send(chat_id, "Running assistant check-in...")
            now = datetime.now(tz=UTC)
            message, sla_breached = await asyncio.to_thread(
                self._assistant_checkin_message,
                chat,
                now=now,
                include_full_control=True,
            )
            await self._send(chat_id, message)
            await self._persist_assistant_checkin_timestamps(chat, ts=now, sla_reminder=sla_breached)
            return

        if command in {"/inbox", "/questions"}:
            await self._send(chat_id, "Loading decisions and steering inbox...")
            message = await asyncio.to_thread(self._decision_inbox_message)
            await self._send(chat_id, message)
            return

        if command == "/skills":
            await self._send(chat_id, "Loading Kimi tools and skills catalog...")
            message = await asyncio.to_thread(self._skills_message)
            await self._send(chat_id, message)
            return

        if command == "/deepresearch":
            arg = args.strip()
            if not arg or arg.lower() == "status":
                message = await asyncio.to_thread(self._deep_research_status_message)
                await self._send(chat_id, message)
                return
            await self._send(chat_id, "Queueing deep-research run...")
            queued = await asyncio.to_thread(self._queue_deep_research_task, arg, f"telegram:{chat_id}")
            if not queued.get("ok"):
                await self._send(chat_id, f"Could not queue deep research: {html.escape(str(queued.get('error') or 'unknown error'))}")
                return
            task = queued.get("task") if isinstance(queued.get("task"), dict) else {}
            task_id = html.escape(str(task.get("task_id") or "n/a"))
            title = html.escape(str(task.get("title") or "Run deep research cycle"))
            command_text = html.escape(str(queued.get("command") or "./scripts/kimi_daily_research.sh"))
            await self._send(
                chat_id,
                (
                    "<b>Deep research queued</b>\n"
                    f"- task_id={task_id}\n"
                    f"- title={title}\n"
                    f"- command={command_text}\n"
                    "- Use /overview to monitor progress."
                ),
            )
            return

        if command == "/autonomy":
            await self._send(chat_id, "Running autonomy cycle (debug + proposals)...")
            report = await asyncio.to_thread(self._run_autonomy_cycle_once, f"telegram:{chat_id}")
            await self._send(chat_id, self._autonomy_cycle_message(report))
            return

        if command in {"/decide", "/decision"}:
            parsed = args.strip().split(maxsplit=1)
            if len(parsed) < 2:
                await self._send(chat_id, "Usage: /decide <decision_id> <1|2|3>")
                return
            decision_id = parsed[0].strip()
            choice_text = parsed[1].strip()
            item, item_type, selected_option, error = await asyncio.to_thread(
                self._resolve_decision_choice,
                decision_id=decision_id,
                choice_text=choice_text,
            )
            if error:
                await self._send(chat_id, html.escape(error))
                return

            assert item is not None
            await self._save_directive(
                chat,
                f"{chat.operator_directive} | decision:{decision_id} => {selected_option}".strip(" |"),
            )
            apply_task = await asyncio.to_thread(
                self._queue_decision_apply_task,
                chat_id=chat_id,
                chat=chat,
                decision_id=decision_id,
                item_type=item_type,
                selected_option=selected_option,
                item=item,
            )
            await self._send(
                chat_id,
                (
                    "<b>Decision captured and queued</b>\n"
                    f"- id={html.escape(decision_id)}\n"
                    f"- selected={html.escape(selected_option)}\n"
                    f"- apply_task_id={html.escape(str(apply_task.get('task_id') or 'n/a'))}"
                ),
            )
            return

        await self._send(chat_id, "Unknown command. Use /help.")

    async def _record_operator_directive(self, chat_id: int, text: str) -> bool:
        cleaned = re.sub(r"\s+", " ", text).strip()
        if len(cleaned) < 8:
            return False
        chat = await asyncio.to_thread(self._load_chat, chat_id)
        await self._save_directive(chat, cleaned)
        safe = html.escape(chat.operator_directive)
        await self._send(chat_id, f"Directive updated from message text.\n<b>Now focusing on:</b> {safe}")
        return True

    async def _save_directive(self, chat: ChatConfig, raw_text: str) -> None:
        cleaned = re.sub(r"\s+", " ", raw_text).strip()
        chat.operator_directive = cleaned[: self._heartbeat_directive_max_chars]
        await asyncio.to_thread(self._save_chat, chat)

    def _heartbeat_message(self, chat: ChatConfig, scored_top: Sequence, now: datetime, total_scored: int) -> str:
        watchlist = format_watchlist_message(chat).replace("<b>Current watchlist</b>\n", "")
        focus_project = chat.focus_project.strip() or "none"
        lines = [
            "<b>Sapphire Heartbeat</b>",
            f"<i>{now.strftime('%Y-%m-%d %H:%M UTC')}</i>",
            f"Assistant mode: {html.escape(chat.assistant_mode)} | Focus: {html.escape(focus_project)}",
            f"Subscribed: {'yes' if chat.subscribed else 'no'}",
            f"Heartbeat: {'enabled' if chat.heartbeat_enabled else 'paused'} every {chat.heartbeat_interval_minutes}m",
            watchlist,
        ]
        if chat.operator_directive:
            lines.append(f"Directive: {html.escape(chat.operator_directive)}")
        lines.append("")
        if scored_top:
            lines.append(f"Top signal count in window: {total_scored}")
            for idx, scored in enumerate(scored_top, start=1):
                title = html.escape(scored.item.title[:140])
                source = html.escape(scored.item.source.name)
                assets = ", ".join(scored.asset_hits[:4]) if scored.asset_hits else "none"
                lines.append(
                    f"{idx}. {title} | Alpha {scored.alpha_score}/100 | {source} | assets: {html.escape(assets)}"
                )
        else:
            lines.append("No high-confidence signals in the active window.")
        lines.append("")
        lines.append("Reply with plain text or /setdirective to steer the bot.")
        return "\n".join(lines)[:3900]

    def _score_for_chat(self, chat: ChatConfig, news: Sequence[NewsItem]):
        return score_alpha_stream_for_chat(
            items=news,
            chat_config=chat,
            macro_keywords=self._settings.default_macro_keywords,
            min_alpha_score=self._settings.min_alpha_score,
            max_news_age_hours=self._settings.max_news_age_hours,
            now=datetime.now(tz=UTC),
        )

    async def send_alpha_stream_to_chat(
        self,
        chat: ChatConfig,
        cached_news: Sequence[NewsItem] | None = None,
        *,
        top_k: int | None = None,
    ) -> int:
        now = datetime.now(tz=UTC)
        news = list(cached_news) if cached_news is not None else await self._news.fetch(REPUTABLE_NEWS_SOURCES)
        scored = self._score_for_chat(chat, news)
        safe_top_k = max(1, min(int(top_k if top_k is not None else self._settings.digest_top_k), 15))
        alpha_stream = build_alpha_stream_payload(
            scored_news=scored,
            chat_config=chat,
            generated_at=now,
            top_k=safe_top_k,
            consumer="telegram",
            max_news_age_hours=self._settings.max_news_age_hours,
            include_rationale=True,
            include_summary_text=False,
        )
        message = format_alpha_stream_message(chat, alpha_stream)
        await self._send(chat.chat_id, message)
        return int(len((alpha_stream or {}).get("items") or []))

    async def _fetch_snippet(self, client: httpx.AsyncClient, url: str) -> str:
        try:
            resp = await client.get(url)
            resp.raise_for_status()
        except Exception:
            return ""

        # Only attempt to parse HTML-ish bodies.
        content_type = (resp.headers.get("content-type") or "").lower()
        if "html" not in content_type and "text/" not in content_type:
            return ""

        page_html = resp.text or ""
        snippet = _extract_meta_description(page_html)
        if len(snippet) >= 120:
            return snippet

        # If meta description is short/empty, try a light-weight body extract.
        body = _extract_article_text(page_html)
        body_summary = _summarize_text(body, limit=240)
        return body_summary or snippet

    def _get_cached_snippet(self, url: str) -> str:
        key = _normalize_url(url)
        cached = self._snippet_cache.get(key)
        if not cached:
            return ""
        ts, snippet = cached
        if (time.time() - ts) > self._snippet_cache_ttl_seconds:
            self._snippet_cache.pop(key, None)
            return ""
        return snippet

    def _put_cached_snippet(self, url: str, snippet: str) -> None:
        key = _normalize_url(url)
        self._snippet_cache[key] = (time.time(), snippet)

    def _merge_sent_ids(self, existing: Sequence[str], new_ids: Sequence[str]) -> list[str]:
        combined = list(existing) + list(new_ids)
        seen: set[str] = set()
        # Keep last N unique ids (preserve recency).
        out_rev: list[str] = []
        for item_id in reversed(combined):
            if not item_id or item_id in seen:
                continue
            seen.add(item_id)
            out_rev.append(item_id)
            if len(out_rev) >= self._sent_item_id_buffer_size:
                break
        return list(reversed(out_rev))

    async def send_digest_to_chat(
        self,
        chat: ChatConfig,
        cached_news: Sequence[NewsItem] | None = None,
        *,
        suppress_if_no_new: bool = False,
    ) -> int:
        now = datetime.now(tz=UTC)
        if suppress_if_no_new and self._min_digest_interval_minutes > 0 and chat.last_digest_sent_at:
            last = chat.last_digest_sent_at
            if last.tzinfo is None:
                last = last.replace(tzinfo=UTC)
            if (now - last).total_seconds() < (self._min_digest_interval_minutes * 60):
                # Throttle scheduled digests to reduce spam/resource usage.
                return 0

        news = list(cached_news) if cached_news is not None else await self._news.fetch(REPUTABLE_NEWS_SOURCES)
        scored_all = self._score_for_chat(chat, news)

        # De-dupe: only send items that haven't been sent recently to this chat.
        sent_ids = set(chat.sent_item_ids or [])
        scored_new = []
        for item in scored_all:
            legacy = _legacy_item_id(item.item.source.key, item.item.url, item.item.title)
            url_id = _url_item_id(item.item.url)
            if item.item.id in sent_ids or legacy in sent_ids or url_id in sent_ids:
                continue
            scored_new.append(item)

        if not scored_new:
            if suppress_if_no_new:
                return 0
            if scored_all:
                await self._send(chat.chat_id, "No new high-alpha headlines since the last digest.")
                return 0

        top_k = self._settings.digest_top_k
        top_items = scored_new[:top_k] if scored_new else scored_all[:top_k]

        # Transactional reserve (Firestore only): claim these item ids before doing
        # extra work (snippet fetch) and before sending. This prevents duplicate
        # digests in multi-instance deployments.
        reserved_via_store = False
        if top_items and hasattr(self._store, "reserve_sent_item_ids"):
            candidate_ids: list[str] = []
            for scored in top_items:
                candidate_ids.append(scored.item.id)
                candidate_ids.append(_legacy_item_id(scored.item.source.key, scored.item.url, scored.item.title))
                candidate_ids.append(_url_item_id(scored.item.url))
            try:
                added, merged = await asyncio.to_thread(
                    self._store.reserve_sent_item_ids,  # type: ignore[attr-defined]
                    chat_id=chat.chat_id,
                    candidate_ids=candidate_ids,
                    limit=self._sent_item_id_buffer_size,
                )
                if added <= 0:
                    # Another instance beat us to it.
                    if suppress_if_no_new:
                        return 0
                    await self._send(chat.chat_id, "No new high-alpha headlines since the last digest.")
                    return 0
                reserved_via_store = True
                chat.sent_item_ids = merged
            except Exception as exc:
                logger.warning("failed reserving sent ids for chat=%s: %s", chat.chat_id, exc)

        # Best-effort snippet enrichment (only for top items; cached).
        summary_overrides: dict[str, str] = {}
        to_fetch: list[tuple[str, str]] = []  # (item_id, url)
        for scored in top_items:
            base_summary = (scored.item.summary or "").strip()
            if len(base_summary) >= 90:
                continue
            cached = self._get_cached_snippet(scored.item.url)
            if cached:
                summary_overrides[scored.item.id] = cached
                continue
            to_fetch.append((scored.item.id, scored.item.url))

        if to_fetch:
            sem = asyncio.Semaphore(self._snippet_fetch_max_concurrency)
            async with httpx.AsyncClient(
                timeout=self._snippet_fetch_timeout_seconds,
                follow_redirects=True,
                headers={"User-Agent": "Mozilla/5.0 (compatible; SapphireAlphaBot/1.0)"},
            ) as client:

                async def _worker(item_id: str, url: str) -> None:
                    async with sem:
                        snippet = await self._fetch_snippet(client, url)
                    if snippet:
                        summary_overrides[item_id] = snippet
                        self._put_cached_snippet(url, snippet)

                await asyncio.gather(*[_worker(item_id, url) for item_id, url in to_fetch], return_exceptions=True)

        message = format_digest_message(
            chat_config=chat,
            scored_news=top_items,
            top_k=top_k,
            generated_at=now,
            summary_overrides=summary_overrides,
        )
        await self._send(chat.chat_id, message)

        if reserved_via_store:
            # Persist last digest timestamp without clobbering transactional sent-id reservations.
            try:
                if hasattr(self._store, "set_last_digest_sent_at"):
                    await asyncio.to_thread(  # type: ignore[attr-defined]
                        self._store.set_last_digest_sent_at,
                        chat_id=chat.chat_id,
                        ts=now,
                    )
                else:
                    chat.last_digest_sent_at = now
                    await asyncio.to_thread(self._save_chat, chat)
            except Exception as exc:
                logger.warning("failed persisting last_digest_sent_at for chat=%s: %s", chat.chat_id, exc)

        # Persist sent ids (only items actually included in the message).
        if not reserved_via_store:
            try:
                new_ids: list[str] = []
                for s in top_items:
                    new_ids.append(s.item.id)
                    new_ids.append(_legacy_item_id(s.item.source.key, s.item.url, s.item.title))
                    new_ids.append(_url_item_id(s.item.url))
                chat.sent_item_ids = self._merge_sent_ids(chat.sent_item_ids or [], new_ids)
                chat.last_digest_sent_at = now
                await asyncio.to_thread(self._save_chat, chat)
            except Exception as exc:
                logger.warning("failed persisting sent_item_ids for chat=%s: %s", chat.chat_id, exc)

        return len(top_items)

    async def send_heartbeat_to_chat(
        self,
        chat: ChatConfig,
        cached_news: Sequence[NewsItem] | None = None,
        *,
        suppress_if_too_soon: bool = True,
    ) -> int:
        now = datetime.now(tz=UTC)
        interval = max(5, int(chat.heartbeat_interval_minutes or self._default_heartbeat_interval_minutes))
        if suppress_if_too_soon and chat.last_heartbeat_sent_at:
            last = chat.last_heartbeat_sent_at
            if last.tzinfo is None:
                last = last.replace(tzinfo=UTC)
            if (now - last).total_seconds() < (interval * 60):
                return 0

        news = list(cached_news) if cached_news is not None else await self._news.fetch(REPUTABLE_NEWS_SOURCES)
        scored = self._score_for_chat(chat, news)
        top = scored[:3]
        message = self._heartbeat_message(chat=chat, scored_top=top, now=now, total_scored=len(scored))
        await self._send(chat.chat_id, message)

        try:
            if hasattr(self._store, "set_last_heartbeat_sent_at"):
                await asyncio.to_thread(  # type: ignore[attr-defined]
                    self._store.set_last_heartbeat_sent_at,
                    chat_id=chat.chat_id,
                    ts=now,
                )
            else:
                chat.last_heartbeat_sent_at = now
                await asyncio.to_thread(self._save_chat, chat)
        except Exception as exc:
            logger.warning("failed persisting last_heartbeat_sent_at for chat=%s: %s", chat.chat_id, exc)

        return 1

    async def broadcast_scheduled_digests(self, limit: int | None = None) -> dict[str, int]:
        chats = await asyncio.to_thread(self._store.list_subscribed)
        if limit is not None and limit > 0:
            chats = chats[:limit]

        if not chats:
            return {"subscribed_chats": 0, "digests_sent": 0}

        news = await self._news.fetch(REPUTABLE_NEWS_SOURCES)

        sent = 0
        for chat in chats:
            try:
                count = await self.send_digest_to_chat(chat, cached_news=news, suppress_if_no_new=True)
                if count > 0:
                    sent += 1
            except Exception as exc:
                logger.exception("failed scheduled digest for chat=%s: %s", chat.chat_id, exc)

        return {
            "subscribed_chats": len(chats),
            "digests_sent": sent,
        }

    async def broadcast_scheduled_heartbeats(self, limit: int | None = None) -> dict[str, int]:
        chats = await asyncio.to_thread(self._store.list_subscribed)
        if limit is not None and limit > 0:
            chats = chats[:limit]

        if not chats:
            return {"subscribed_chats": 0, "heartbeat_enabled_chats": 0, "heartbeats_sent": 0}

        news = await self._news.fetch(REPUTABLE_NEWS_SOURCES)

        eligible = 0
        sent = 0
        for chat in chats:
            if not chat.heartbeat_enabled:
                continue
            eligible += 1
            try:
                count = await self.send_heartbeat_to_chat(chat, cached_news=news, suppress_if_too_soon=True)
                if count > 0:
                    sent += 1
            except Exception as exc:
                logger.exception("failed scheduled heartbeat for chat=%s: %s", chat.chat_id, exc)

        return {
            "subscribed_chats": len(chats),
            "heartbeat_enabled_chats": eligible,
            "heartbeats_sent": sent,
        }

    async def broadcast_assistant_checkins(
        self,
        limit: int | None = None,
        *,
        force: bool = False,
    ) -> dict[str, Any]:
        chat_map: dict[int, ChatConfig] = {}
        try:
            chats = await asyncio.to_thread(self._store.list_subscribed)
            for chat in chats:
                try:
                    chat_map[int(chat.chat_id)] = chat
                except Exception:
                    continue
        except Exception as exc:
            logger.warning("assistant check-in could not load subscribed chats: %s", exc)

        if self._settings.allowed_telegram_chat_ids:
            for chat_id in self._settings.allowed_telegram_chat_ids:
                try:
                    parsed = int(chat_id)
                except Exception:
                    continue
                if parsed in chat_map:
                    continue
                try:
                    existing = await asyncio.to_thread(self._store.get, parsed)
                except Exception as exc:
                    logger.warning("assistant check-in could not load chat_id=%s from store: %s", parsed, exc)
                    existing = None
                chat_map[parsed] = existing or default_chat_config(parsed, self._settings)

        # Fallback: infer recent Telegram chats from the event stream.
        # This keeps proactive delivery alive if subscription rows are missing.
        for parsed in self._recent_telegram_chat_ids(limit=400):
            if parsed in chat_map:
                continue
            if self._allowed_chat_ids and parsed not in self._allowed_chat_ids:
                continue
            try:
                existing = await asyncio.to_thread(self._store.get, parsed)
            except Exception as exc:
                logger.warning("assistant check-in fallback could not load chat_id=%s: %s", parsed, exc)
                existing = None
            chat_map[parsed] = existing or default_chat_config(parsed, self._settings)

        chat_ids = sorted(chat_map.keys())
        if limit is not None and limit > 0:
            chat_ids = chat_ids[:limit]
        if not chat_ids:
            return {
                "status": "ok",
                "subscribed_chats": 0,
                "proactive_enabled_chats": 0,
                "notifications_sent": 0,
                "sla_reminders_sent": 0,
            }

        now = datetime.now(tz=UTC)
        state = self._decision_inbox_state(now=now)
        open_count = int(state.get("open_count", 0))
        age_minutes = int(state.get("age_minutes", 0))

        proactive_enabled = 0
        eligible = 0
        sent = 0
        sla_sent = 0
        for chat_id in chat_ids:
            chat = chat_map[chat_id]
            if chat.proactive_checkins_enabled:
                proactive_enabled += 1
            if not force and not chat.proactive_checkins_enabled:
                continue

            interval_minutes = max(15, int(chat.assistant_checkin_interval_minutes or 120))
            sla_minutes = max(30, int(chat.decision_sla_minutes or 180))
            sla_breached = open_count > 0 and age_minutes >= sla_minutes

            last_checkin = chat.last_assistant_checkin_at
            if last_checkin and last_checkin.tzinfo is None:
                last_checkin = last_checkin.replace(tzinfo=UTC)
            interval_due = (last_checkin is None) or ((now - last_checkin).total_seconds() >= interval_minutes * 60)

            last_sla = chat.last_decision_sla_reminder_at
            if last_sla and last_sla.tzinfo is None:
                last_sla = last_sla.replace(tzinfo=UTC)
            sla_cooldown_minutes = max(30, min(sla_minutes, 180))
            sla_due = sla_breached and (
                last_sla is None or (now - last_sla).total_seconds() >= sla_cooldown_minutes * 60
            )

            should_send = force or interval_due or sla_due
            if not should_send:
                continue

            eligible += 1
            try:
                message, detected_sla_breach = self._assistant_checkin_message(chat, now=now, include_full_control=False)
                await self._send(chat.chat_id, message)
                await self._persist_assistant_checkin_timestamps(
                    chat,
                    ts=now,
                    sla_reminder=(detected_sla_breach and sla_due),
                )
                sent += 1
                if detected_sla_breach and sla_due:
                    sla_sent += 1
            except Exception as exc:
                logger.exception("failed assistant check-in for chat=%s: %s", chat.chat_id, exc)

        self._record_event(
            "assistant.checkin.broadcast",
            source="telegram.scheduler",
            actor="scheduler:assistant-checkin",
            category="assistant",
            status="ok",
            message=f"assistant check-ins sent={sent}",
            payload={
                "subscribed_chats": len(chat_ids),
                "proactive_enabled_chats": proactive_enabled,
                "eligible_chats": eligible,
                "notifications_sent": sent,
                "sla_reminders_sent": sla_sent,
                "open_decision_count": open_count,
                "decision_age_minutes": age_minutes,
                "force": force,
            },
        )

        return {
            "status": "ok",
            "subscribed_chats": len(chat_ids),
            "proactive_enabled_chats": proactive_enabled,
            "eligible_chats": eligible,
            "notifications_sent": sent,
            "sla_reminders_sent": sla_sent,
            "decision_open_count": open_count,
            "decision_age_minutes": age_minutes,
            "forced": force,
        }

    async def broadcast_autonomy_cycle(self, limit: int | None = None) -> dict[str, Any]:
        chat_ids: list[int] = []
        try:
            chats = await asyncio.to_thread(self._store.list_subscribed)
            for chat in chats:
                try:
                    chat_ids.append(int(chat.chat_id))
                except Exception:
                    continue
        except Exception as exc:
            logger.warning("autonomy broadcast could not load subscribed chats: %s", exc)
        if self._settings.allowed_telegram_chat_ids:
            known = set(chat_ids)
            for chat_id in self._settings.allowed_telegram_chat_ids:
                try:
                    parsed = int(chat_id)
                except Exception:
                    continue
                if parsed in known:
                    continue
                known.add(parsed)
                chat_ids.append(parsed)

        # Fallback: infer recent Telegram chats from event stream.
        known = set(chat_ids)
        for parsed in self._recent_telegram_chat_ids(limit=400):
            if parsed in known:
                continue
            if self._allowed_chat_ids and parsed not in self._allowed_chat_ids:
                continue
            known.add(parsed)
            chat_ids.append(parsed)

        if limit is not None and limit > 0:
            chat_ids = chat_ids[:limit]

        actor = "scheduler:autonomy"
        report = await asyncio.to_thread(self._run_autonomy_cycle_once, actor)
        message = self._autonomy_cycle_message(report)

        notified = 0
        for chat_id in chat_ids:
            try:
                await self._send(chat_id, message)
                notified += 1
            except Exception as exc:
                logger.exception("failed autonomy notification for chat=%s: %s", chat_id, exc)

        self._record_event(
            "autonomy.cycle.broadcast",
            source="telegram.scheduler",
            actor=actor,
            category="autonomy",
            status="ok",
            message=f"Autonomy cycle completed; notified_chats={notified}",
            payload={
                "notified_chats": notified,
                "created_tasks": len(report.get("created_tasks", []))
                if isinstance(report.get("created_tasks"), list)
                else 0,
                "proposal_count": len(report.get("proposals", []))
                if isinstance(report.get("proposals"), list)
                else 0,
            },
        )

        return {
            "status": "ok",
            "subscribed_chats": len(chat_ids),
            "notifications_sent": notified,
            "autonomy": report,
        }
