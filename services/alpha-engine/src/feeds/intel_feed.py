"""
Sapphire Intel Feed Aggregator

Provides a Glint-style intelligence feed from stable, public sources:
  - Google News RSS (crypto + AI)
  - Hacker News (crypto + AI)
  - GitHub repository momentum (AI-focused)

Optional Glint page scraping is sandbox-gated and disabled by default.
"""

from __future__ import annotations

import asyncio
import hashlib
import os
import re
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from typing import Any, Dict, List, Optional
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
    return datetime.now(timezone.utc)


def _to_iso(dt: datetime | None) -> str:
    if dt is None:
        return _now_utc().isoformat()
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat()


def _parse_ts(value: Any) -> Optional[datetime]:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).astimezone(timezone.utc)
    except ValueError:
        pass
    try:
        return parsedate_to_datetime(text).astimezone(timezone.utc)
    except Exception:
        return None


def _clean_text(value: Any, limit: int = 320) -> str:
    text = _HTML_TAG_RE.sub(" ", str(value or ""))
    text = _WS_RE.sub(" ", text).strip()
    if len(text) > limit:
        return text[: limit - 1].rstrip() + "…"
    return text


def _item_id(source: str, title: str, url: str) -> str:
    digest = hashlib.sha1(f"{source}|{title}|{url}".encode("utf-8")).hexdigest()
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
        self._glint_sandbox_only = _env_flag(
            "SAPPHIRE_GLINT_SCRAPE_SANDBOX_ONLY", default=True
        )
        self._runtime_env = str(
            os.getenv("SAPPHIRE_ENV", os.getenv("ENVIRONMENT", "production"))
        ).strip().lower()

        self._session: Optional[aiohttp.ClientSession] = None
        self._loop_task: Optional[asyncio.Task[Any]] = None
        self._running = False
        self._last_refresh_ts = 0.0
        self._items: List[Dict[str, Any]] = []
        self._source_status: Dict[str, Dict[str, Any]] = {
            "google_news_crypto": self._blank_source_status("google_news_crypto"),
            "google_news_ai": self._blank_source_status("google_news_ai"),
            "hn_crypto": self._blank_source_status("hn_crypto"),
            "hn_ai": self._blank_source_status("hn_ai"),
            "github_ai_repos": self._blank_source_status("github_ai_repos"),
            "glint_feed_scrape": self._blank_source_status("glint_feed_scrape"),
        }
        self._lock = asyncio.Lock()

    @property
    def enabled(self) -> bool:
        return self._enabled

    def _blank_source_status(self, name: str) -> Dict[str, Any]:
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

    async def refresh_once(self, force: bool = False) -> Dict[str, Any]:
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
        ]

        merged: List[Dict[str, Any]] = []
        for source_name, job_factory in jobs:
            source_items = await self._execute_source_job(source_name, job_factory)
            if source_items:
                merged.extend(source_items)

        async with self._lock:
            deduped: Dict[str, Dict[str, Any]] = {}
            for item in merged:
                deduped[item["id"]] = item
            ordered = sorted(
                deduped.values(),
                key=lambda row: (_parse_ts(row.get("published_at")) or datetime.min.replace(tzinfo=timezone.utc), float(row.get("score", 0))),
                reverse=True,
            )
            self._items = ordered[: self._max_items]

        self._last_refresh_ts = time.time()
        return self.get_status()

    async def _execute_source_job(
        self, source_name: str, job_factory: Any
    ) -> List[Dict[str, Any]]:
        started = time.time()
        status = self._source_status.setdefault(
            source_name, self._blank_source_status(source_name)
        )
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

    async def _fetch_json(self, url: str, timeout: float = 12.0) -> Dict[str, Any]:
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
        tags: List[str],
        confidence: str,
        score: float,
    ) -> Dict[str, Any]:
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

    async def _pull_google_news(self, query: str, category: str) -> List[Dict[str, Any]]:
        q = quote_plus(query)
        url = f"https://news.google.com/rss/search?q={q}&hl=en-US&gl=US&ceid=US:en"
        xml_text = await self._fetch_text(url)
        root = ET.fromstring(xml_text)
        items: List[Dict[str, Any]] = []
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

    async def _pull_hn(self, query: str, category: str) -> List[Dict[str, Any]]:
        q = quote_plus(query)
        url = (
            "https://hn.algolia.com/api/v1/search_by_date"
            f"?query={q}&tags=story&hitsPerPage=20"
        )
        payload = await self._fetch_json(url)
        hits = payload.get("hits", []) if isinstance(payload.get("hits"), list) else []
        items: List[Dict[str, Any]] = []
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

    async def _pull_github_ai_repos(self) -> List[Dict[str, Any]]:
        since = (_now_utc() - timedelta(days=14)).date().isoformat()
        query = quote_plus(f"topic:artificial-intelligence pushed:>{since}")
        url = (
            "https://api.github.com/search/repositories"
            f"?q={query}&sort=stars&order=desc&per_page=20"
        )
        payload = await self._fetch_json(url)
        repos = payload.get("items", []) if isinstance(payload.get("items"), list) else []
        items: List[Dict[str, Any]] = []
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

    async def _pull_glint_feed_optional(self) -> List[Dict[str, Any]]:
        status = self._source_status["glint_feed_scrape"]
        if not self._glint_scrape_enabled:
            status["healthy"] = True
            status["status"] = "disabled_by_policy"
            status["items"] = 0
            status["last_refresh"] = _now_utc().isoformat()
            status["last_error"] = None
            status["consecutive_errors"] = 0
            return []

        if self._glint_sandbox_only and self._runtime_env not in {"sandbox", "dev", "development", "staging"}:
            status["healthy"] = True
            status["status"] = "blocked_outside_sandbox"
            status["items"] = 0
            status["last_refresh"] = _now_utc().isoformat()
            status["last_error"] = None
            status["consecutive_errors"] = 0
            return []

        html = await self._fetch_text("https://glint.trade/feed", timeout=10.0)
        candidates = [match.strip() for match in _GLINT_TITLE_RE.findall(html)]
        unique_titles: List[str] = []
        for title in candidates:
            cleaned = _clean_text(title, limit=200)
            if len(cleaned) < 24:
                continue
            if cleaned in unique_titles:
                continue
            unique_titles.append(cleaned)
            if len(unique_titles) >= 12:
                break

        items: List[Dict[str, Any]] = []
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

    def get_feed(
        self,
        *,
        limit: int = 60,
        category: str = "",
        query: str = "",
    ) -> List[Dict[str, Any]]:
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

    def get_status(self) -> Dict[str, Any]:
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
                datetime.fromtimestamp(self._last_refresh_ts, tz=timezone.utc).isoformat()
                if self._last_refresh_ts
                else None
            ),
            "sources_total": len(self._source_status),
            "sources_healthy": healthy_sources,
            "sources": self._source_status,
            "glint_scrape_enabled": self._glint_scrape_enabled,
            "glint_scrape_sandbox_only": self._glint_sandbox_only,
            "runtime_env": self._runtime_env,
        }
