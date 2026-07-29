"""
Sapphire Intel Feed Aggregator

Provides a Glint-style intelligence feed from stable, public sources:
  - Google News RSS (crypto + AI)
  - Hacker News (crypto + AI)
  - GitHub repository momentum (AI-focused)

Optional Glint collection is routed through the SCOUT sandbox by default.
"""

from __future__ import annotations

import asyncio
import hashlib
import os
import re
import time
import xml.etree.ElementTree as ET
from datetime import UTC, datetime, timedelta
from email.utils import parsedate_to_datetime
from typing import Any
from urllib.parse import quote_plus

import aiohttp
from loguru import logger

_HTML_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")
_GLINT_TITLE_RE = re.compile(r'"(?:headline|title)"\s*:\s*"([^"]{18,220})"')


def _env_flag(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _now_utc() -> datetime:
    return datetime.now(UTC)


def _to_iso(dt: datetime | None) -> str:
    if dt is None:
        return _now_utc().isoformat()
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC).isoformat()


def _parse_ts(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).astimezone(UTC)
    except ValueError:
        pass
    try:
        return parsedate_to_datetime(text).astimezone(UTC)
    except Exception:
        return None


def _clean_text(value: Any, limit: int = 320) -> str:
    text = _HTML_TAG_RE.sub(" ", str(value or ""))
    text = _WS_RE.sub(" ", text).strip()
    if len(text) > limit:
        return text[: limit - 1].rstrip() + "…"
    return text


def _item_id(source: str, title: str, url: str) -> str:
    digest = hashlib.sha1(f"{source}|{title}|{url}".encode()).hexdigest()
    return f"{source}:{digest[:14]}"


class IntelFeedAggregator:
    """Aggregates public intelligence sources into a normalized feed."""

    def __init__(self):
        self._enabled = _env_flag("SAPPHIRE_INTEL_FEED_ENABLED", default=True)
        self._poll_interval_seconds = max(
            60, int(os.getenv("SAPPHIRE_INTEL_FEED_INTERVAL_SECONDS", "300"))
        )
        self._max_items = max(40, int(os.getenv("SAPPHIRE_INTEL_FEED_MAX_ITEMS", "240")))
        self._glint_scrape_enabled = _env_flag("SAPPHIRE_GLINT_SCRAPE_ENABLED", default=False)
        self._glint_sandbox_only = _env_flag("SAPPHIRE_GLINT_SCRAPE_SANDBOX_ONLY", default=True)
        self._glint_use_scout_sandbox = _env_flag("SAPPHIRE_GLINT_USE_SCOUT_SANDBOX", default=True)
        self._scout_sandbox_url = (
            str(os.getenv("SAPPHIRE_SCOUT_SANDBOX_URL", "")).strip().rstrip("/")
        )
        self._scout_sandbox_token = str(os.getenv("SAPPHIRE_SCOUT_SANDBOX_TOKEN", "")).strip()
        self._glint_source_url = str(
            os.getenv("SAPPHIRE_GLINT_SOURCE_URL", "https://glint.trade/feed")
        ).strip()
        self._glint_sandbox_limit = max(
            1, min(int(os.getenv("SAPPHIRE_GLINT_SANDBOX_LIMIT", "24")), 100)
        )
        self._glint_sandbox_query = str(os.getenv("SAPPHIRE_GLINT_SANDBOX_QUERY", "")).strip()
        self._glint_sandbox_timeout_seconds = max(
            5, min(int(os.getenv("SAPPHIRE_GLINT_SANDBOX_TIMEOUT_SECONDS", "14")), 30)
        )
        self._scrapling_intel_enabled = _env_flag("SAPPHIRE_SCRAPLING_INTEL_ENABLED", default=False)
        self._scrapling_source_url = str(
            os.getenv("SAPPHIRE_SCRAPLING_INTEL_SOURCE_URL", "https://news.ycombinator.com/")
        ).strip()
        raw_selectors = str(
            os.getenv("SAPPHIRE_SCRAPLING_INTEL_SELECTORS", "title;h1;h2;a")
        ).strip()
        self._scrapling_selectors = [
            selector.strip() for selector in raw_selectors.split(";") if selector.strip()
        ] or ["title", "h1", "h2", "a"]
        self._scrapling_limit_per_selector = max(
            1, min(int(os.getenv("SAPPHIRE_SCRAPLING_INTEL_LIMIT_PER_SELECTOR", "4")), 20)
        )
        self._scrapling_include_links = _env_flag(
            "SAPPHIRE_SCRAPLING_INTEL_INCLUDE_LINKS", default=True
        )
        self._scrapling_max_links = max(
            1, min(int(os.getenv("SAPPHIRE_SCRAPLING_INTEL_MAX_LINKS", "20")), 50)
        )
        self._scrapling_query = str(os.getenv("SAPPHIRE_SCRAPLING_INTEL_QUERY", "")).strip()
        self._scrapling_timeout_seconds = max(
            5, min(int(os.getenv("SAPPHIRE_SCRAPLING_INTEL_TIMEOUT_SECONDS", "20")), 30)
        )
        self._coingecko_trending_enabled = _env_flag(
            "SAPPHIRE_INTEL_COINGECKO_TRENDING_ENABLED", default=True
        )
        self._coingecko_trending_limit = max(
            3, min(int(os.getenv("SAPPHIRE_INTEL_COINGECKO_TRENDING_LIMIT", "10")), 20)
        )
        self._coingecko_api_base = (
            str(os.getenv("SAPPHIRE_INTEL_COINGECKO_API_BASE", "https://api.coingecko.com/api/v3"))
            .strip()
            .rstrip("/")
        )
        self._fear_greed_enabled = _env_flag("SAPPHIRE_INTEL_FEAR_GREED_ENABLED", default=True)
        self._fear_greed_api = str(
            os.getenv("SAPPHIRE_INTEL_FEAR_GREED_API", "https://api.alternative.me/fng/")
        ).strip()
        self._fear_greed_items = max(
            1, min(int(os.getenv("SAPPHIRE_INTEL_FEAR_GREED_ITEMS", "3")), 10)
        )
        self._runtime_env = (
            str(os.getenv("SAPPHIRE_ENV", os.getenv("ENVIRONMENT", "production"))).strip().lower()
        )

        self._session: aiohttp.ClientSession | None = None
        self._loop_task: asyncio.Task[Any] | None = None
        self._running = False
        self._last_refresh_ts = 0.0
        self._items: list[dict[str, Any]] = []
        self._source_status: dict[str, dict[str, Any]] = {
            "google_news_crypto": self._blank_source_status("google_news_crypto"),
            "google_news_ai": self._blank_source_status("google_news_ai"),
            "hn_crypto": self._blank_source_status("hn_crypto"),
            "hn_ai": self._blank_source_status("hn_ai"),
            "github_ai_repos": self._blank_source_status("github_ai_repos"),
            "glint_feed_scrape": self._blank_source_status("glint_feed_scrape"),
            "scrapling_web_intel": self._blank_source_status("scrapling_web_intel"),
            "coingecko_trending": self._blank_source_status("coingecko_trending"),
            "fear_greed_index": self._blank_source_status("fear_greed_index"),
        }
        self._lock = asyncio.Lock()

    @property
    def enabled(self) -> bool:
        return self._enabled

    def _blank_source_status(self, name: str) -> dict[str, Any]:
        return {
            "name": name,
            "healthy": False,
            "running": False,
            "items": 0,
            "last_refresh": None,
            "last_error": None,
            "consecutive_errors": 0,
            "status": "idle",
        }

    async def start(self) -> None:
        if not self._enabled:
            logger.info("🧠 Intel feed disabled (SAPPHIRE_INTEL_FEED_ENABLED=false)")
            return

        if self._running:
            return

        self._session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=20, connect=5, sock_read=12),
            headers={"User-Agent": "SapphireIntel/1.0 (+https://sapphirealpha.xyz)"},
        )
        self._running = True
        self._loop_task = asyncio.create_task(self._run_loop(), name="intel_feed_loop")
        logger.info("🧠 Intel feed started")

    async def stop(self) -> None:
        self._running = False
        if self._loop_task:
            self._loop_task.cancel()
            self._loop_task = None
        if self._session:
            await self._session.close()
            self._session = None
        logger.info("🧠 Intel feed stopped")

    async def _run_loop(self) -> None:
        while self._running:
            try:
                await self.refresh_once(force=True)
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.warning(f"Intel feed refresh failed: {type(exc).__name__}: {exc}")
            await asyncio.sleep(self._poll_interval_seconds)

    async def refresh_once(self, force: bool = False) -> dict[str, Any]:
        if not self._enabled:
            return self.get_status()
        if not self._session:
            return self.get_status()
        if not force and (time.time() - self._last_refresh_ts) < max(
            20, self._poll_interval_seconds // 3
        ):
            return self.get_status()

        jobs = [
            (
                "google_news_crypto",
                lambda: self._pull_google_news("crypto market OR bitcoin OR ethereum", "market"),
            ),
            (
                "google_news_ai",
                lambda: self._pull_google_news(
                    "artificial intelligence OR llm OR model release", "ai"
                ),
            ),
            ("hn_crypto", lambda: self._pull_hn("bitcoin OR ethereum OR crypto", "market")),
            ("hn_ai", lambda: self._pull_hn("llm OR ai model OR open source ai", "ai")),
            ("github_ai_repos", self._pull_github_ai_repos),
            ("glint_feed_scrape", self._pull_glint_feed_optional),
            ("scrapling_web_intel", self._pull_scrapling_intel_optional),
            ("coingecko_trending", self._pull_coingecko_trending_optional),
            ("fear_greed_index", self._pull_fear_greed_optional),
        ]

        merged: list[dict[str, Any]] = []
        for source_name, job_factory in jobs:
            source_items = await self._execute_source_job(source_name, job_factory)
            if source_items:
                merged.extend(source_items)

        async with self._lock:
            deduped: dict[str, dict[str, Any]] = {}
            for item in merged:
                deduped[item["id"]] = item
            ordered = sorted(
                deduped.values(),
                key=lambda row: (
                    _parse_ts(row.get("published_at")) or datetime.min.replace(tzinfo=UTC),
                    float(row.get("score", 0)),
                ),
                reverse=True,
            )
            self._items = ordered[: self._max_items]

        self._last_refresh_ts = time.time()
        return self.get_status()

    async def _execute_source_job(self, source_name: str, job_factory: Any) -> list[dict[str, Any]]:
        started = time.time()
        status = self._source_status.setdefault(source_name, self._blank_source_status(source_name))
        status["running"] = True
        try:
            items = await job_factory()
            status["healthy"] = True
            status["status"] = "healthy"
            status["items"] = len(items)
            status["last_refresh"] = _now_utc().isoformat()
            status["latency_ms"] = round((time.time() - started) * 1000, 2)
            status["last_error"] = None
            status["consecutive_errors"] = 0
            return items
        except Exception as exc:
            status["healthy"] = False
            status["status"] = "error"
            status["items"] = 0
            status["last_refresh"] = _now_utc().isoformat()
            status["latency_ms"] = round((time.time() - started) * 1000, 2)
            status["last_error"] = (str(exc).strip() or type(exc).__name__)[:220]
            status["consecutive_errors"] = int(status.get("consecutive_errors", 0)) + 1
            logger.warning(f"Intel source {source_name} failed: {exc}")
            return []
        finally:
            status["running"] = False

    async def _fetch_text(self, url: str, timeout: float = 12.0) -> str:
        assert self._session is not None
        async with self._session.get(url, timeout=timeout) as resp:
            if resp.status != 200:
                raise RuntimeError(f"http_{resp.status}")
            return await resp.text()

    async def _fetch_json(self, url: str, timeout: float = 12.0) -> dict[str, Any]:
        assert self._session is not None
        async with self._session.get(url, timeout=timeout) as resp:
            if resp.status != 200:
                raise RuntimeError(f"http_{resp.status}")
            data = await resp.json(content_type=None)
            return data if isinstance(data, dict) else {}

    def _build_item(
        self,
        *,
        source: str,
        category: str,
        title: str,
        summary: str,
        url: str,
        published_at: datetime | None,
        tags: list[str],
        confidence: str,
        score: float,
    ) -> dict[str, Any]:
        clean_title = _clean_text(title, limit=220)
        clean_summary = _clean_text(summary, limit=360)
        safe_url = str(url or "").strip()
        return {
            "id": _item_id(source, clean_title, safe_url),
            "source": source,
            "category": category,
            "title": clean_title,
            "summary": clean_summary,
            "url": safe_url,
            "published_at": _to_iso(published_at),
            "tags": [str(t).strip().lower() for t in tags if str(t).strip()],
            "confidence": confidence,
            "score": round(float(score), 3),
        }

    async def _pull_google_news(self, query: str, category: str) -> list[dict[str, Any]]:
        q = quote_plus(query)
        url = f"https://news.google.com/rss/search?q={q}&hl=en-US&gl=US&ceid=US:en"
        xml_text = await self._fetch_text(url)
        root = ET.fromstring(xml_text)
        items: list[dict[str, Any]] = []
        for node in root.findall("./channel/item")[:20]:
            title = node.findtext("title", default="")
            link = node.findtext("link", default="")
            pub_date = _parse_ts(node.findtext("pubDate", default=""))
            summary = node.findtext("description", default="")
            score = 0.78 if category == "market" else 0.74
            items.append(
                self._build_item(
                    source=f"google_news_{category}",
                    category=category,
                    title=title,
                    summary=summary,
                    url=link,
                    published_at=pub_date,
                    tags=[category, "news", "public_source"],
                    confidence="medium",
                    score=score,
                )
            )
        return items

    async def _pull_hn(self, query: str, category: str) -> list[dict[str, Any]]:
        q = quote_plus(query)
        url = f"https://hn.algolia.com/api/v1/search_by_date?query={q}&tags=story&hitsPerPage=20"
        payload = await self._fetch_json(url)
        hits = payload.get("hits", []) if isinstance(payload.get("hits"), list) else []
        items: list[dict[str, Any]] = []
        for row in hits:
            if not isinstance(row, dict):
                continue
            title = row.get("title") or row.get("story_title") or ""
            if not title:
                continue
            post_url = row.get("url") or (
                f"https://news.ycombinator.com/item?id={row.get('objectID')}"
            )
            points = float(row.get("points") or 0)
            comments = float(row.get("num_comments") or 0)
            score = min(1.0, 0.55 + (points / 600.0) + (comments / 900.0))
            items.append(
                self._build_item(
                    source=f"hackernews_{category}",
                    category=category,
                    title=title,
                    summary=f"HN score={int(points)} · comments={int(comments)} · by {row.get('author', 'unknown')}",
                    url=post_url,
                    published_at=_parse_ts(row.get("created_at")),
                    tags=[category, "hn", "discussion"],
                    confidence="medium",
                    score=score,
                )
            )
        return items

    async def _pull_github_ai_repos(self) -> list[dict[str, Any]]:
        since = (_now_utc() - timedelta(days=14)).date().isoformat()
        query = quote_plus(f"topic:artificial-intelligence pushed:>{since}")
        url = (
            "https://api.github.com/search/repositories"
            f"?q={query}&sort=stars&order=desc&per_page=20"
        )
        payload = await self._fetch_json(url)
        repos = payload.get("items", []) if isinstance(payload.get("items"), list) else []
        items: list[dict[str, Any]] = []
        for repo in repos:
            if not isinstance(repo, dict):
                continue
            name = str(repo.get("full_name", "")).strip()
            if not name:
                continue
            stars = float(repo.get("stargazers_count") or 0)
            forks = float(repo.get("forks_count") or 0)
            watchers = float(repo.get("watchers_count") or 0)
            score = min(1.0, 0.58 + (stars / 20000.0) + (watchers / 25000.0) + (forks / 35000.0))
            description = repo.get("description") or "AI repository update"
            lang = repo.get("language") or "unknown"
            items.append(
                self._build_item(
                    source="github_research",
                    category="research",
                    title=f"{name} gaining momentum",
                    summary=f"{description} · ★{int(stars):,} · forks {int(forks):,} · language {lang}",
                    url=repo.get("html_url", ""),
                    published_at=_parse_ts(repo.get("pushed_at")),
                    tags=["ai", "github", "research", str(lang).lower()],
                    confidence="high" if stars >= 1000 else "medium",
                    score=score,
                )
            )
        return items

    async def _pull_glint_feed_optional(self) -> list[dict[str, Any]]:
        status = self._source_status["glint_feed_scrape"]
        if not self._glint_scrape_enabled:
            status["healthy"] = True
            status["status"] = "disabled_by_policy"
            status["items"] = 0
            status["last_refresh"] = _now_utc().isoformat()
            status["last_error"] = None
            status["consecutive_errors"] = 0
            return []

        if self._glint_use_scout_sandbox:
            return await self._pull_glint_feed_from_scout_sandbox()

        if self._glint_sandbox_only and self._runtime_env not in {
            "sandbox",
            "dev",
            "development",
            "staging",
        }:
            status["healthy"] = True
            status["status"] = "blocked_outside_sandbox"
            status["items"] = 0
            status["last_refresh"] = _now_utc().isoformat()
            status["last_error"] = None
            status["consecutive_errors"] = 0
            return []

        return await self._pull_glint_feed_direct()

    async def _pull_glint_feed_from_scout_sandbox(self) -> list[dict[str, Any]]:
        if not self._session:
            raise RuntimeError("session_unavailable")
        if not self._scout_sandbox_url:
            raise RuntimeError("sandbox_url_missing")
        if not self._scout_sandbox_token:
            raise RuntimeError("sandbox_token_missing")

        endpoint = f"{self._scout_sandbox_url}/v1/intel/glint_collect"
        payload = {
            "limit": self._glint_sandbox_limit,
            "query": self._glint_sandbox_query,
            "source_url": self._glint_source_url,
        }
        headers = {
            "Content-Type": "application/json",
            "X-Scout-Sandbox-Token": self._scout_sandbox_token,
        }
        timeout = aiohttp.ClientTimeout(total=self._glint_sandbox_timeout_seconds)
        async with self._session.post(
            endpoint,
            json=payload,
            headers=headers,
            timeout=timeout,
        ) as resp:
            if resp.status >= 400:
                raise RuntimeError(f"sandbox_http_{resp.status}")
            data = await resp.json(content_type=None)

        if not isinstance(data, dict):
            raise RuntimeError("sandbox_response_invalid")
        if not bool(data.get("ok", False)):
            reason = str(data.get("reason", "collect_failed")).strip()[:120]
            raise RuntimeError(f"sandbox_collect_failed:{reason}")

        rows = data.get("items", [])
        if not isinstance(rows, list):
            return []

        items: list[dict[str, Any]] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            title = _clean_text(row.get("title", ""), limit=220)
            if not title:
                continue
            summary = row.get("summary") or "Collected by SCOUT sandbox collector."
            try:
                score = float(row.get("score", 0.58))
            except (TypeError, ValueError):
                score = 0.58
            tags = row.get("tags", [])
            if not isinstance(tags, list):
                tags = []
            items.append(
                self._build_item(
                    source=str(row.get("source") or "glint_feed_scrape"),
                    category=str(row.get("category") or "market"),
                    title=title,
                    summary=summary,
                    url=str(row.get("url") or self._glint_source_url),
                    published_at=_parse_ts(row.get("published_at")) or _now_utc(),
                    tags=[*tags, "scout_sandbox"],
                    confidence=str(row.get("confidence") or "low"),
                    score=score,
                )
            )
            if len(items) >= self._glint_sandbox_limit:
                break
        return items

    async def _pull_glint_feed_direct(self) -> list[dict[str, Any]]:
        html = await self._fetch_text(self._glint_source_url, timeout=10.0)
        candidates = [match.strip() for match in _GLINT_TITLE_RE.findall(html)]
        unique_titles: list[str] = []
        for title in candidates:
            cleaned = _clean_text(title, limit=200)
            if len(cleaned) < 24:
                continue
            if cleaned in unique_titles:
                continue
            unique_titles.append(cleaned)
            if len(unique_titles) >= 12:
                break

        items: list[dict[str, Any]] = []
        now = _now_utc()
        for idx, title in enumerate(unique_titles):
            items.append(
                self._build_item(
                    source="glint_feed_scrape",
                    category="market",
                    title=title,
                    summary="Captured from glint.trade/feed HTML in sandbox mode.",
                    url="https://glint.trade/feed",
                    published_at=now - timedelta(minutes=idx),
                    tags=["sandbox", "glint", "scrape"],
                    confidence="low",
                    score=max(0.42, 0.62 - (idx * 0.02)),
                )
            )
        return items

    async def _pull_scrapling_intel_optional(self) -> list[dict[str, Any]]:
        status = self._source_status["scrapling_web_intel"]
        if not self._scrapling_intel_enabled:
            status["healthy"] = True
            status["status"] = "disabled_by_policy"
            status["items"] = 0
            status["last_refresh"] = _now_utc().isoformat()
            status["last_error"] = None
            status["consecutive_errors"] = 0
            return []

        if not self._session:
            raise RuntimeError("session_unavailable")
        if not self._scout_sandbox_url:
            raise RuntimeError("sandbox_url_missing")
        if not self._scout_sandbox_token:
            raise RuntimeError("sandbox_token_missing")

        endpoint = f"{self._scout_sandbox_url}/v1/intel/scrapling_collect"
        payload = {
            "source_url": self._scrapling_source_url,
            "selectors": self._scrapling_selectors,
            "limit_per_selector": self._scrapling_limit_per_selector,
            "include_links": self._scrapling_include_links,
            "max_links": self._scrapling_max_links,
            "query": self._scrapling_query,
        }
        headers = {
            "Content-Type": "application/json",
            "X-Scout-Sandbox-Token": self._scout_sandbox_token,
        }
        timeout = aiohttp.ClientTimeout(total=self._scrapling_timeout_seconds)
        async with self._session.post(
            endpoint,
            json=payload,
            headers=headers,
            timeout=timeout,
        ) as resp:
            if resp.status >= 400:
                raise RuntimeError(f"sandbox_http_{resp.status}")
            data = await resp.json(content_type=None)

        if not isinstance(data, dict):
            raise RuntimeError("sandbox_response_invalid")
        if not bool(data.get("ok", False)):
            reason = str(data.get("reason", "collect_failed")).strip()[:120]
            raise RuntimeError(f"sandbox_collect_failed:{reason}")

        rows = data.get("items", [])
        if not isinstance(rows, list):
            return []

        limit = max(1, min(self._scrapling_limit_per_selector * len(self._scrapling_selectors), 80))
        items: list[dict[str, Any]] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            title = _clean_text(row.get("title", ""), limit=220)
            if not title:
                continue
            summary = row.get("summary") or "Collected by SCOUT sandbox Scrapling collector."
            try:
                score = float(row.get("score", 0.56))
            except (TypeError, ValueError):
                score = 0.56
            tags = row.get("tags", [])
            if not isinstance(tags, list):
                tags = []
            items.append(
                self._build_item(
                    source=str(row.get("source") or "scrapling_fetch"),
                    category=str(row.get("category") or "research"),
                    title=title,
                    summary=summary,
                    url=str(row.get("url") or self._scrapling_source_url),
                    published_at=_parse_ts(row.get("published_at")) or _now_utc(),
                    tags=[*tags, "scout_sandbox", "scrapling"],
                    confidence=str(row.get("confidence") or "low"),
                    score=score,
                )
            )
            if len(items) >= limit:
                break
        return items

    async def _pull_coingecko_trending_optional(self) -> list[dict[str, Any]]:
        status = self._source_status["coingecko_trending"]
        if not self._coingecko_trending_enabled:
            status["healthy"] = True
            status["status"] = "disabled_by_policy"
            status["items"] = 0
            status["last_refresh"] = _now_utc().isoformat()
            status["last_error"] = None
            status["consecutive_errors"] = 0
            return []

        url = f"{self._coingecko_api_base}/search/trending"
        payload = await self._fetch_json(url, timeout=12.0)
        rows = payload.get("coins", []) if isinstance(payload, dict) else []
        if not isinstance(rows, list):
            return []

        out: list[dict[str, Any]] = []
        for idx, row in enumerate(rows):
            item = row.get("item", row) if isinstance(row, dict) else {}
            if not isinstance(item, dict):
                continue
            name = _clean_text(item.get("name", ""), limit=96)
            symbol = _clean_text(item.get("symbol", ""), limit=24).upper()
            coin_id = _clean_text(item.get("id", ""), limit=80)
            rank = item.get("market_cap_rank")
            score_index = item.get("score")
            if not name or not symbol:
                continue
            try:
                score_hint = float(score_index) if score_index is not None else float(idx)
            except (TypeError, ValueError):
                score_hint = float(idx)
            confidence = "high" if idx < 3 else "medium"
            source_score = max(0.45, 0.85 - min(0.35, score_hint * 0.05))
            rank_text = f" · rank #{rank}" if rank not in (None, "", "None") else ""
            out.append(
                self._build_item(
                    source="coingecko_trending",
                    category="market",
                    title=f"{symbol} trending on CoinGecko",
                    summary=f"{name}{rank_text} · trending index {idx + 1}",
                    url=f"https://www.coingecko.com/en/coins/{coin_id}"
                    if coin_id
                    else "https://www.coingecko.com/",
                    published_at=_now_utc(),
                    tags=["market", "trending", "coingecko", symbol.lower()],
                    confidence=confidence,
                    score=source_score,
                )
            )
            if len(out) >= self._coingecko_trending_limit:
                break
        return out

    async def _pull_fear_greed_optional(self) -> list[dict[str, Any]]:
        status = self._source_status["fear_greed_index"]
        if not self._fear_greed_enabled:
            status["healthy"] = True
            status["status"] = "disabled_by_policy"
            status["items"] = 0
            status["last_refresh"] = _now_utc().isoformat()
            status["last_error"] = None
            status["consecutive_errors"] = 0
            return []

        url = f"{self._fear_greed_api}?limit={self._fear_greed_items}&format=json"
        payload = await self._fetch_json(url, timeout=10.0)
        rows = payload.get("data", []) if isinstance(payload, dict) else []
        if not isinstance(rows, list):
            return []

        out: list[dict[str, Any]] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            raw_value = row.get("value", "")
            try:
                value = float(raw_value)
            except (TypeError, ValueError):
                continue
            mood = _clean_text(row.get("value_classification", "Unknown"), limit=40)
            ts_value = row.get("timestamp")
            published_at = _parse_ts(ts_value) if ts_value is not None else _now_utc()
            if isinstance(ts_value, str) and ts_value.isdigit():
                try:
                    published_at = datetime.fromtimestamp(float(ts_value), tz=UTC)
                except Exception:
                    published_at = _now_utc()
            if isinstance(ts_value, int | float):
                try:
                    published_at = datetime.fromtimestamp(float(ts_value), tz=UTC)
                except Exception:
                    published_at = _now_utc()

            if value <= 25:
                mood_tag = "extreme_fear"
            elif value <= 45:
                mood_tag = "fear"
            elif value <= 55:
                mood_tag = "neutral"
            elif value <= 75:
                mood_tag = "greed"
            else:
                mood_tag = "extreme_greed"

            score = max(0.45, min(0.92, 0.55 + (abs(value - 50.0) / 120.0)))
            out.append(
                self._build_item(
                    source="fear_greed_index",
                    category="market",
                    title=f"Crypto sentiment: {mood}",
                    summary=f"Fear & Greed index at {value:.0f}/100 ({mood}).",
                    url="https://alternative.me/crypto/fear-and-greed-index/",
                    published_at=published_at,
                    tags=["market", "sentiment", "fear-greed", mood_tag],
                    confidence="medium",
                    score=score,
                )
            )
        return out

    def get_feed(
        self,
        *,
        limit: int = 60,
        category: str = "",
        query: str = "",
    ) -> list[dict[str, Any]]:
        capped = max(1, min(int(limit or 60), 200))
        category_lower = str(category or "").strip().lower()
        query_lower = str(query or "").strip().lower()
        rows = list(self._items)
        if category_lower:
            rows = [row for row in rows if str(row.get("category", "")).lower() == category_lower]
        if query_lower:
            rows = [
                row
                for row in rows
                if query_lower in str(row.get("title", "")).lower()
                or query_lower in str(row.get("summary", "")).lower()
                or query_lower in " ".join(row.get("tags", []))
            ]
        return rows[:capped]

    def get_cognition_context(self, symbol: str) -> str:
        if not self._enabled:
            return ""
        symbol_upper = str(symbol or "").strip().upper()
        if not symbol_upper:
            return ""

        symbol_terms = {
            "BTC": {"btc", "bitcoin", "etf"},
            "ETH": {"eth", "ethereum", "ether"},
            "SOL": {"sol", "solana"},
        }
        terms = symbol_terms.get(symbol_upper, {symbol_upper.lower()})

        relevant = []
        for row in self._items:
            haystack = " ".join(
                [
                    str(row.get("title", "")).lower(),
                    str(row.get("summary", "")).lower(),
                    " ".join([str(tag).lower() for tag in row.get("tags", [])]),
                ]
            )
            if any(term in haystack for term in terms):
                relevant.append(row)
            if len(relevant) >= 6:
                break

        if not relevant:
            return ""

        lines = [f"Intel Feed ({len(relevant)} updates relevant to {symbol_upper}):"]
        for row in relevant:
            lines.append(
                f"  [{row.get('source')}] {row.get('title')} "
                f"(confidence={row.get('confidence')}, score={row.get('score')})"
            )
        return "\n".join(lines)

    def get_status(self) -> dict[str, Any]:
        healthy_sources = sum(
            1 for source in self._source_status.values() if source.get("healthy", False)
        )
        return {
            "enabled": self._enabled,
            "running": self._running,
            "item_count": len(self._items),
            "poll_interval_seconds": self._poll_interval_seconds,
            "last_refresh_ts": self._last_refresh_ts,
            "last_refresh_iso": (
                datetime.fromtimestamp(self._last_refresh_ts, tz=UTC).isoformat()
                if self._last_refresh_ts
                else None
            ),
            "sources_total": len(self._source_status),
            "sources_healthy": healthy_sources,
            "sources": self._source_status,
            "glint_scrape_enabled": self._glint_scrape_enabled,
            "glint_scrape_sandbox_only": self._glint_sandbox_only,
            "glint_use_scout_sandbox": self._glint_use_scout_sandbox,
            "glint_scout_configured": bool(self._scout_sandbox_url and self._scout_sandbox_token),
            "glint_source_url": self._glint_source_url,
            "scrapling_intel_enabled": self._scrapling_intel_enabled,
            "scrapling_scout_configured": bool(
                self._scout_sandbox_url and self._scout_sandbox_token
            ),
            "scrapling_source_url": self._scrapling_source_url,
            "coingecko_trending_enabled": self._coingecko_trending_enabled,
            "coingecko_trending_limit": self._coingecko_trending_limit,
            "fear_greed_enabled": self._fear_greed_enabled,
            "fear_greed_items": self._fear_greed_items,
            "runtime_env": self._runtime_env,
        }
