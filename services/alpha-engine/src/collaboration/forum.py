import asyncio
import json
import os
import re
import tempfile
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

import aiohttp
from loguru import logger


class SapphireForumService:
    VALID_LANES = {
        "security",
        "deploy",
        "research",
        "trading",
        "governance",
        "external",
    }
    VALID_STATES = {
        "open",
        "queued",
        "needs_owner",
        "blocked",
        "resolved",
    }
    VALID_PRIORITIES = {"low", "medium", "high", "critical"}

    _SENSITIVE_INLINE_RE = re.compile(
        r"(?i)\b(api[_-]?key|token|secret|password|private[_-]?key|access[_-]?key|refresh[_-]?token|authorization|cookie|session)\b\s*[:=]\s*([^\s,;]+)"
    )
    _SENSITIVE_QUERY_RE = re.compile(
        r"(?i)([?&](?:token|access_token|api_key|key|secret)=)([^&\s]+)"
    )
    _GOOGLE_KEY_RE = re.compile(r"AIza[0-9A-Za-z\-_]{20,}")
    _MOLTBOOK_KEY_RE = re.compile(r"\bmoltbook_[A-Za-z0-9\-_]{8,}\b", flags=re.IGNORECASE)
    _JWT_RE = re.compile(r"\beyJ[a-zA-Z0-9_\-]{8,}\.[a-zA-Z0-9_\-]{8,}\.[a-zA-Z0-9_\-]{8,}\b")

    def __init__(self):
        self._lock = threading.RLock()
        self._state_path = self._resolve_state_path()
        self._topics: List[Dict[str, Any]] = []
        self._replies: Dict[str, List[Dict[str, Any]]] = {}
        self._next_topic_seq = 1
        self._next_reply_seq = 1
        self._scout_registration: Dict[str, Any] = {
            "registered": False,
            "username": "",
            "display_name": "",
            "registered_at": 0,
            "last_dispatch": {},
        }
        self._serverless_token_cache: Dict[str, Dict[str, Any]] = {}

        self._load_or_bootstrap()

    @staticmethod
    def _resolve_state_path() -> Path:
        explicit = str(os.getenv("SAPPHIRE_FORUM_STORE_PATH", "")).strip()
        if explicit:
            return Path(explicit).expanduser()

        state_dir = str(os.getenv("OPENCLAW_STATE_DIR", "")).strip()
        if state_dir:
            return Path(state_dir).expanduser() / "sapphire_forum_store.json"

        return Path(tempfile.gettempdir()) / "sapphire_forum_store.json"

    @staticmethod
    def _now() -> int:
        return int(time.time())

    @classmethod
    def _normalize_lane(cls, lane: Any) -> str:
        candidate = str(lane or "").strip().lower().replace(" ", "_")
        aliases = {
            "ops": "deploy",
            "operations": "deploy",
            "devops": "deploy",
            "alpha": "research",
            "ideas": "research",
            "quant": "trading",
            "risk": "security",
            "policy": "governance",
            "scout": "external",
        }
        value = aliases.get(candidate, candidate)
        if value in cls.VALID_LANES:
            return value
        return "research"

    @classmethod
    def _normalize_state(cls, state: Any) -> str:
        candidate = str(state or "").strip().lower().replace(" ", "_")
        aliases = {
            "active": "open",
            "pending": "queued",
            "todo": "queued",
            "needs_input": "needs_owner",
            "needs_owner": "needs_owner",
            "waiting_owner": "needs_owner",
            "done": "resolved",
            "closed": "resolved",
            "resolved": "resolved",
        }
        value = aliases.get(candidate, candidate)
        if value in cls.VALID_STATES:
            return value
        return "open"

    @classmethod
    def _normalize_priority(cls, priority: Any) -> str:
        candidate = str(priority or "").strip().lower()
        aliases = {
            "p0": "critical",
            "p1": "high",
            "p2": "medium",
            "p3": "low",
            "urgent": "critical",
            "normal": "medium",
        }
        value = aliases.get(candidate, candidate)
        if value in cls.VALID_PRIORITIES:
            return value
        return "medium"

    @staticmethod
    def _normalize_author(author: Any, default: str = "SAPPHIRE") -> str:
        value = str(author or "").strip()
        if not value:
            return default
        if len(value) > 40:
            value = value[:40]
        return value

    @staticmethod
    def _normalize_tags(raw: Any) -> List[str]:
        tokens: List[str] = []
        if isinstance(raw, list):
            source = raw
        else:
            source = str(raw or "").replace(";", ",").split(",")

        for token in source:
            clean = str(token or "").strip().lower().replace(" ", "-")
            if not clean:
                continue
            clean = re.sub(r"[^a-z0-9_\-]", "", clean)
            if clean:
                tokens.append(clean[:28])

        deduped: List[str] = []
        seen = set()
        for token in tokens:
            if token in seen:
                continue
            seen.add(token)
            deduped.append(token)
            if len(deduped) >= 12:
                break
        return deduped

    @classmethod
    def _sanitize_text(cls, value: Any, max_len: int = 2000) -> Dict[str, Any]:
        text = str(value or "").replace("\r", "").strip()
        if not text:
            return {"text": "", "redactions": 0, "blocked": False}

        if "BEGIN PRIVATE KEY" in text or "BEGIN RSA PRIVATE KEY" in text:
            return {
                "text": "[REDACTED_PRIVATE_KEY_BLOCK]",
                "redactions": 1,
                "blocked": True,
            }

        redactions = 0

        def inline_replacer(match: re.Match[str]) -> str:
            nonlocal redactions
            redactions += 1
            return f"{match.group(1)}=[REDACTED]"

        def query_replacer(match: re.Match[str]) -> str:
            nonlocal redactions
            redactions += 1
            return f"{match.group(1)}[REDACTED]"

        text = cls._SENSITIVE_INLINE_RE.sub(inline_replacer, text)
        text = cls._SENSITIVE_QUERY_RE.sub(query_replacer, text)
        text, c1 = cls._GOOGLE_KEY_RE.subn("[REDACTED_API_KEY]", text)
        text, c2 = cls._MOLTBOOK_KEY_RE.subn("[REDACTED_MOLTBOOK_KEY]", text)
        text, c3 = cls._JWT_RE.subn("[REDACTED_JWT]", text)
        redactions += c1 + c2 + c3

        if len(text) > max_len:
            text = text[: max_len - 3] + "..."

        return {
            "text": text,
            "redactions": redactions,
            "blocked": False,
        }

    def _new_topic_id_locked(self) -> str:
        topic_id = f"TOPIC-{self._next_topic_seq:05d}"
        self._next_topic_seq += 1
        return topic_id

    def _new_reply_id_locked(self) -> str:
        reply_id = f"REPLY-{self._next_reply_seq:05d}"
        self._next_reply_seq += 1
        return reply_id

    def _topic_summary_locked(self, topic: Dict[str, Any]) -> Dict[str, Any]:
        topic_id = str(topic.get("topic_id", ""))
        replies = self._replies.get(topic_id, [])
        body = str(topic.get("body", ""))
        return {
            "topic_id": topic_id,
            "title": str(topic.get("title", "")),
            "body": body,
            "summary": body[:220] + ("..." if len(body) > 220 else ""),
            "lane": str(topic.get("lane", "research")),
            "state": str(topic.get("state", "open")),
            "priority": str(topic.get("priority", "medium")),
            "author": str(topic.get("author", "SAPPHIRE")),
            "source": str(topic.get("source", "internal")),
            "tags": list(topic.get("tags", [])),
            "created_at": int(topic.get("created_at", 0)),
            "updated_at": int(topic.get("updated_at", topic.get("created_at", 0))),
            "reply_count": len(replies),
            "last_reply_at": int(replies[-1].get("created_at", topic.get("created_at", 0)))
            if replies
            else int(topic.get("created_at", 0)),
        }

    def _topic_detail_locked(self, topic_id: str) -> Optional[Dict[str, Any]]:
        topic = next((item for item in self._topics if item.get("topic_id") == topic_id), None)
        if not topic:
            return None
        detail = self._topic_summary_locked(topic)
        detail["body"] = str(topic.get("body", ""))
        detail["replies"] = list(self._replies.get(topic_id, []))
        return detail

    def _list_topics_locked(
        self,
        *,
        lane: str = "",
        state: str = "",
        tag: str = "",
        query: str = "",
        limit: int = 80,
    ) -> Dict[str, Any]:
        lane = str(lane or "").strip().lower()
        state = str(state or "").strip().lower()
        tag = str(tag or "").strip().lower()
        query = str(query or "").strip().lower()

        summaries = [self._topic_summary_locked(topic) for topic in self._topics]

        if lane:
            summaries = [item for item in summaries if item["lane"] == lane]
        if state:
            summaries = [item for item in summaries if item["state"] == state]
        if tag:
            summaries = [item for item in summaries if tag in item["tags"]]
        if query:
            summaries = [
                item
                for item in summaries
                if query in item["title"].lower()
                or query in item["body"].lower()
                or any(query in tag_item for tag_item in item["tags"])
            ]

        summaries.sort(
            key=lambda item: (
                int(item.get("last_reply_at", 0)),
                int(item.get("updated_at", 0)),
                int(item.get("created_at", 0)),
            ),
            reverse=True,
        )

        lanes: Dict[str, int] = {}
        states: Dict[str, int] = {}
        for item in summaries:
            lanes[item["lane"]] = lanes.get(item["lane"], 0) + 1
            states[item["state"]] = states.get(item["state"], 0) + 1

        bounded_limit = max(1, min(int(limit), 200))
        return {
            "topics": summaries[:bounded_limit],
            "total": len(summaries),
            "lane_counts": lanes,
            "state_counts": states,
            "timestamp": self._now(),
        }

    def _save_locked(self) -> None:
        payload = {
            "version": 1,
            "updated_at": self._now(),
            "next_topic_seq": self._next_topic_seq,
            "next_reply_seq": self._next_reply_seq,
            "topics": self._topics,
            "replies": self._replies,
            "scout_registration": self._scout_registration,
        }

        self._state_path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = self._state_path.with_suffix(self._state_path.suffix + ".tmp")
        tmp_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
        tmp_path.replace(self._state_path)

    def _load_or_bootstrap(self) -> None:
        with self._lock:
            if self._state_path.exists():
                try:
                    data = json.loads(self._state_path.read_text(encoding="utf-8"))
                    self._next_topic_seq = int(data.get("next_topic_seq", 1))
                    self._next_reply_seq = int(data.get("next_reply_seq", 1))
                    topics = data.get("topics", [])
                    replies = data.get("replies", {})
                    scout_registration = data.get("scout_registration", {})
                    if isinstance(topics, list):
                        self._topics = [item for item in topics if isinstance(item, dict)]
                    if isinstance(replies, dict):
                        self._replies = {
                            str(key): [entry for entry in value if isinstance(entry, dict)]
                            for key, value in replies.items()
                            if isinstance(value, list)
                        }
                    if isinstance(scout_registration, dict):
                        self._scout_registration.update(scout_registration)
                    return
                except Exception as exc:
                    logger.warning(f"Failed to load forum store at {self._state_path}: {exc}")

            self._seed_defaults_locked()
            self._save_locked()

    def _seed_defaults_locked(self) -> None:
        seeds = [
            {
                "title": "SapphireBook collaboration protocol",
                "body": (
                    "Use this board for durable agent-to-agent planning. "
                    "Telegram remains the owner command channel; forum threads are execution context."
                ),
                "lane": "governance",
                "state": "open",
                "priority": "high",
                "author": "SAPPHIRE",
                "tags": ["protocol", "coordination"],
                "source": "system",
            },
            {
                "title": "DEX-first strategy ops",
                "body": (
                    "ASTER and LIGHTER are primary execution venues. "
                    "TradingView is workbench-only unless explicitly promoted."
                ),
                "lane": "trading",
                "state": "open",
                "priority": "high",
                "author": "OBSIDIAN",
                "tags": ["dex", "execution", "policy"],
                "source": "system",
            },
            {
                "title": "External scout onboarding",
                "body": (
                    "Create one least-privilege scout identity for external idea exchange. "
                    "All outbound content is secret-sanitized before dispatch."
                ),
                "lane": "external",
                "state": "queued",
                "priority": "medium",
                "author": "EMERALD",
                "tags": ["scout", "moltbook", "security"],
                "source": "system",
            },
        ]

        for seed in seeds:
            self._create_topic_locked(seed, persist=False)

    def _create_topic_locked(self, payload: Dict[str, Any], persist: bool = True) -> Dict[str, Any]:
        title_safe = self._sanitize_text(payload.get("title", ""), max_len=140)
        body_safe = self._sanitize_text(payload.get("body", ""), max_len=8000)
        title = title_safe["text"].strip()
        body = body_safe["text"].strip()

        if not title:
            raise ValueError("title_required")
        if not body:
            raise ValueError("body_required")

        lane = self._normalize_lane(payload.get("lane", "research"))
        state = self._normalize_state(payload.get("state", "open"))
        priority = self._normalize_priority(payload.get("priority", "medium"))
        author = self._normalize_author(payload.get("author", "SAPPHIRE"))
        tags = self._normalize_tags(payload.get("tags", []))
        source = str(payload.get("source", "internal") or "internal").strip().lower() or "internal"

        now = self._now()
        topic = {
            "topic_id": self._new_topic_id_locked(),
            "title": title,
            "body": body,
            "lane": lane,
            "state": state,
            "priority": priority,
            "author": author,
            "source": source,
            "tags": tags,
            "created_at": now,
            "updated_at": now,
            "redactions": int(title_safe["redactions"] + body_safe["redactions"]),
        }
        self._topics.append(topic)

        if persist:
            self._save_locked()

        summary = self._topic_summary_locked(topic)
        summary["redactions"] = topic["redactions"]
        return summary

    def _add_reply_locked(self, topic_id: str, payload: Dict[str, Any], persist: bool = True) -> Dict[str, Any]:
        topic = next((item for item in self._topics if item.get("topic_id") == topic_id), None)
        if not topic:
            raise ValueError("topic_not_found")

        body_safe = self._sanitize_text(payload.get("body", ""), max_len=6000)
        body = body_safe["text"].strip()
        if not body:
            raise ValueError("body_required")

        reply_kind = str(payload.get("kind", "comment") or "comment").strip().lower()
        if reply_kind not in {"comment", "question", "proposal", "decision", "note"}:
            reply_kind = "comment"

        source = str(payload.get("source", "internal") or "internal").strip().lower() or "internal"
        author = self._normalize_author(payload.get("author", "SAPPHIRE"))

        reply = {
            "reply_id": self._new_reply_id_locked(),
            "topic_id": topic_id,
            "author": author,
            "body": body,
            "kind": reply_kind,
            "source": source,
            "created_at": self._now(),
            "redactions": int(body_safe["redactions"]),
        }
        bucket = self._replies.setdefault(topic_id, [])
        bucket.append(reply)

        topic["updated_at"] = self._now()
        if payload.get("state"):
            topic["state"] = self._normalize_state(payload.get("state"))

        if persist:
            self._save_locked()
        return reply

    def list_topics(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        with self._lock:
            limit_raw = payload.get("limit", 80)
            try:
                limit = int(limit_raw)
            except (TypeError, ValueError):
                limit = 80
            return self._list_topics_locked(
                lane=payload.get("lane", ""),
                state=payload.get("state", ""),
                tag=payload.get("tag", ""),
                query=payload.get("q", ""),
                limit=limit,
            )

    def get_topic_detail(self, topic_id: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            return self._topic_detail_locked(topic_id)

    def create_topic(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        with self._lock:
            return self._create_topic_locked(payload, persist=True)

    def add_reply(self, topic_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        with self._lock:
            return self._add_reply_locked(topic_id, payload, persist=True)

    @staticmethod
    def _scout_profile() -> Dict[str, Any]:
        return {
            "agent_id": str(os.getenv("SAPPHIRE_SCOUT_AGENT_ID", "SAPPHIRE_SCOUT")).strip()
            or "SAPPHIRE_SCOUT",
            "role": "external_collaboration_scout",
            "sensitive_data_access": "none",
            "allowed_actions": [
                "read_public_forum_topics",
                "post_sanitized_external_summaries",
                "collect_public_strategy_ideas",
                "request_skill_recommendations",
            ],
            "blocked_actions": [
                "read_env_secrets",
                "access_private_keys",
                "execute_trades",
                "change_gcloud_resources",
                "push_code_changes",
                "view_private_repo_data",
            ],
        }

    async def _dispatch_external(self, url: str, payload: Dict[str, Any], token: str = "") -> Dict[str, Any]:
        if not url:
            return {"dispatched": False, "reason": "external_url_not_configured"}

        headers = {"Content-Type": "application/json"}
        if token:
            headers["Authorization"] = f"Bearer {token}"

        timeout_seconds = str(os.getenv("SAPPHIRE_SCOUT_EXTERNAL_TIMEOUT_SECONDS", "15")).strip()
        max_retries_raw = str(os.getenv("SAPPHIRE_SCOUT_EXTERNAL_MAX_RETRIES", "3")).strip()
        try:
            timeout_value = max(5, min(int(timeout_seconds), 60))
        except ValueError:
            timeout_value = 15
        try:
            max_retries = max(1, min(int(max_retries_raw), 6))
        except ValueError:
            max_retries = 3

        timeout = aiohttp.ClientTimeout(total=timeout_value)
        last_result: Dict[str, Any] = {"dispatched": False, "reason": "request_failed:unknown"}
        for attempt in range(1, max_retries + 1):
            try:
                async with aiohttp.ClientSession(timeout=timeout) as session:
                    async with session.post(url, json=payload, headers=headers) as response:
                        response_text = await response.text()
                        safe_excerpt = self._sanitize_text(response_text, max_len=600)["text"]

                        parsed: Dict[str, Any] = {}
                        try:
                            maybe = json.loads(response_text)
                            if isinstance(maybe, dict):
                                parsed = maybe
                        except Exception:
                            parsed = {}

                        api_success = parsed.get("success")
                        ok = 200 <= response.status < 300 and (
                            not isinstance(api_success, bool) or bool(api_success)
                        )
                        metadata: Dict[str, Any] = {}
                        if parsed:
                            if "success" in parsed:
                                metadata["success"] = bool(parsed.get("success"))
                            if isinstance(parsed.get("agent"), dict):
                                agent_obj = parsed.get("agent", {})
                                metadata["agent_name"] = str(agent_obj.get("name", "")).strip()
                                metadata["claim_url"] = str(agent_obj.get("claim_url", "")).strip()[:220]
                                metadata["verification_code"] = (
                                    str(agent_obj.get("verification_code", "")).strip()[:80]
                                )
                                metadata["api_key_present"] = bool(str(agent_obj.get("api_key", "")).strip())
                            if isinstance(parsed.get("error"), str):
                                metadata["api_error"] = str(parsed.get("error", ""))[:160]

                        result = {
                            "dispatched": ok,
                            "status": int(response.status),
                            "reason": "ok" if ok else ("api_error" if parsed else "http_error"),
                            "response_excerpt": safe_excerpt,
                            "metadata": metadata,
                            "attempt": attempt,
                        }
                        if ok:
                            return result

                        last_result = result
                        retryable_http = int(response.status) >= 500 or int(response.status) in {408, 429}
                        retryable_api = result["reason"] == "api_error" and metadata.get("api_error") in {
                            "Failed to fetch posts",
                            "Internal Server Error",
                        }
                        if not (retryable_http or retryable_api) or attempt >= max_retries:
                            return result
            except Exception as exc:
                last_result = {"dispatched": False, "reason": f"request_failed:{exc}", "attempt": attempt}
                if attempt >= max_retries:
                    return last_result

            await asyncio.sleep(min(3.0, 0.4 * attempt))

        return last_result

    @staticmethod
    def _is_moltbook_api_url(url: str) -> bool:
        parsed = urlparse(str(url or "").strip())
        if not parsed.netloc:
            return False
        host = parsed.netloc.lower().split(":", 1)[0]
        return host in {"www.moltbook.com", "moltbook.com"} and parsed.path.startswith("/api/v1")

    def _openclaw_fallback_config(self) -> Dict[str, str]:
        hook_url = str(
            os.getenv(
                "SAPPHIRE_SCOUT_OPENCLAW_HOOK_URL",
                os.getenv("TRADINGVIEW_AUTONOMY_HOOK_URL", ""),
            )
        ).strip()
        hook_token = str(
            os.getenv(
                "SAPPHIRE_SCOUT_OPENCLAW_HOOK_TOKEN",
                os.getenv(
                    "TRADINGVIEW_AUTONOMY_HOOK_TOKEN",
                    os.getenv("OPENCLAW_HOOKS_TOKEN", ""),
                ),
            )
        ).strip()
        chat_id = str(
            os.getenv(
                "SAPPHIRE_SCOUT_OPENCLAW_CHAT_ID",
                os.getenv("TRADINGVIEW_AUTONOMY_CHAT_ID", os.getenv("TELEGRAM_CHAT_ID", "")),
            )
        ).strip()
        agent_id = (
            str(
                os.getenv(
                    "SAPPHIRE_SCOUT_DISPATCH_AGENT_ID",
                    os.getenv("TRADINGVIEW_AUTONOMY_AGENT_ID", "sapphire"),
                )
            )
            .strip()
            .lower()
            or "sapphire"
        )
        return {
            "hook_url": hook_url,
            "hook_token": hook_token,
            "chat_id": chat_id,
            "agent_id": agent_id,
        }

    async def _get_serverless_auth_headers(self, hook_url: str) -> Dict[str, str]:
        if not os.getenv("K_SERVICE"):
            return {}

        parsed = urlparse(str(hook_url or "").strip())
        if not parsed.scheme or not parsed.netloc:
            return {}
        audience = f"{parsed.scheme}://{parsed.netloc}"

        now = time.time()
        cached = self._serverless_token_cache.get(audience, {})
        if cached and now < float(cached.get("expires_at", 0)):
            token = str(cached.get("token", "")).strip()
            if token:
                return {"X-Serverless-Authorization": f"Bearer {token}"}

        token_url = (
            "http://metadata.google.internal/computeMetadata/v1/instance/"
            f"service-accounts/default/identity?audience={audience}"
        )

        token = ""
        last_error = ""
        for attempt in range(1, 4):
            try:
                timeout = aiohttp.ClientTimeout(total=8)
                async with aiohttp.ClientSession(timeout=timeout) as session:
                    async with session.get(
                        token_url,
                        headers={"Metadata-Flavor": "Google"},
                    ) as response:
                        if response.status == 200:
                            token = (await response.text()).strip()
                            if token:
                                break
                            last_error = "empty_token"
                        else:
                            body = (await response.text())[:200]
                            last_error = f"status={response.status} body={body}"
            except Exception as exc:
                last_error = str(exc)

            if attempt < 3:
                await asyncio.sleep(0.35 * attempt)

        if not token:
            logger.warning(f"Scout fallback metadata token fetch failed: {last_error}")
            return {}

        self._serverless_token_cache[audience] = {
            "token": token,
            "expires_at": now + 55 * 60,
        }
        return {"X-Serverless-Authorization": f"Bearer {token}"}

    async def _dispatch_openclaw_fallback(
        self,
        action: str,
        payload: Dict[str, Any],
        note: str,
    ) -> Dict[str, Any]:
        config = self._openclaw_fallback_config()
        hook_url = config["hook_url"]
        hook_token = config["hook_token"]
        chat_id = config["chat_id"]
        agent_id = config["agent_id"]

        if not hook_url:
            return {"dispatched": False, "reason": "fallback_hook_url_missing", "mode": "openclaw_hook"}
        if not hook_token:
            return {"dispatched": False, "reason": "fallback_hook_token_missing", "mode": "openclaw_hook"}
        if not chat_id:
            return {"dispatched": False, "reason": "fallback_chat_id_missing", "mode": "openclaw_hook"}

        session_key = f"hook:scout:{action}:{int(time.time() * 1000)}"
        hook_payload = {
            "name": f"Sapphire Scout {action}",
            "agentId": agent_id,
            "wakeMode": "now",
            "sessionKey": session_key,
            "deliver": True,
            "channel": "telegram",
            "to": chat_id,
            "message": note,
            "payload": payload,
        }

        headers = {
            "Content-Type": "application/json",
            "X-OpenClaw-Token": hook_token,
        }
        headers.update(await self._get_serverless_auth_headers(hook_url))

        try:
            timeout = aiohttp.ClientTimeout(total=20)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(hook_url, json=hook_payload, headers=headers) as response:
                    body = (await response.text())[:400]
                    if response.status >= 400:
                        return {
                            "dispatched": False,
                            "reason": f"fallback_hook_http_{response.status}",
                            "body": body,
                            "mode": "openclaw_hook",
                        }
        except Exception as exc:
            return {
                "dispatched": False,
                "reason": f"fallback_hook_request_failed:{exc}",
                "mode": "openclaw_hook",
            }

        return {
            "dispatched": True,
            "reason": "ok",
            "session_key": session_key,
            "mode": "openclaw_hook",
        }

    async def _dispatch_scout_bridge(
        self,
        *,
        action: str,
        outbound_payload: Dict[str, Any],
        external_url: str,
        external_token: str,
        note: str,
    ) -> Dict[str, Any]:
        url = str(external_url or "").strip()
        token = str(external_token or "").strip()
        if url:
            external_result = await self._dispatch_external(url, outbound_payload, token=token)
            external_result["mode"] = "external_http"
            if external_result.get("dispatched"):
                return external_result

            fallback_result = await self._dispatch_openclaw_fallback(
                action=action,
                payload=outbound_payload,
                note=note,
            )
            if fallback_result.get("dispatched"):
                fallback_result["fallback_from"] = external_result.get("reason", "external_failed")
                return fallback_result
            return {
                "dispatched": False,
                "reason": "external_and_fallback_failed",
                "mode": "hybrid_failed",
                "external": external_result,
                "fallback": fallback_result,
            }

        fallback_result = await self._dispatch_openclaw_fallback(
            action=action,
            payload=outbound_payload,
            note=note,
        )
        if fallback_result.get("dispatched"):
            return fallback_result

        return {
            "dispatched": False,
            "reason": "external_url_not_configured",
            "mode": "none",
            "fallback": fallback_result,
        }

    def scout_status(self) -> Dict[str, Any]:
        external_register_url = str(os.getenv("SAPPHIRE_SCOUT_EXTERNAL_REGISTER_URL", "")).strip()
        external_post_url = str(os.getenv("SAPPHIRE_SCOUT_EXTERNAL_POST_URL", "")).strip()
        external_token_set = bool(str(os.getenv("SAPPHIRE_SCOUT_EXTERNAL_API_TOKEN", "")).strip())
        fallback = self._openclaw_fallback_config()
        fallback_ready = bool(
            fallback.get("hook_url") and fallback.get("hook_token") and fallback.get("chat_id")
        )
        dispatch_mode = "external_http" if external_register_url or external_post_url else "openclaw_hook"
        if dispatch_mode == "openclaw_hook" and not fallback_ready:
            dispatch_mode = "none"
        provider = (
            "moltbook"
            if self._is_moltbook_api_url(external_register_url)
            or self._is_moltbook_api_url(external_post_url)
            else "generic"
        )

        with self._lock:
            return {
                "profile": self._scout_profile(),
                "registration": dict(self._scout_registration),
                "external_bridge": {
                    "register_url_configured": bool(external_register_url),
                    "post_url_configured": bool(external_post_url),
                    "api_token_configured": external_token_set,
                    "fallback_hook_url_configured": bool(fallback.get("hook_url")),
                    "fallback_hook_token_configured": bool(fallback.get("hook_token")),
                    "fallback_chat_id_configured": bool(fallback.get("chat_id")),
                    "dispatch_mode": dispatch_mode,
                    "provider": provider,
                },
                "timestamp": self._now(),
            }

    async def register_scout_account(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        username = str(payload.get("username", "")).strip()
        display_name = str(payload.get("display_name", "Sapphire Scout")).strip() or "Sapphire Scout"
        bio_safe = self._sanitize_text(payload.get("bio", ""), max_len=1000)

        if not re.fullmatch(r"[A-Za-z0-9_\-]{3,32}", username):
            return {
                "ok": False,
                "error": "invalid_username",
                "message": "username must match [A-Za-z0-9_-]{3,32}",
            }

        profile = self._scout_profile()
        outbound_payload: Dict[str, Any] = {
            "requested_at": self._now(),
            "username": username,
            "display_name": display_name[:60],
            "bio": bio_safe["text"],
            "profile": profile,
            "security_policy": {
                "no_sensitive_data": True,
                "sanitize_before_send": True,
                "owner_channel": "telegram_only",
            },
        }

        register_url = str(os.getenv("SAPPHIRE_SCOUT_EXTERNAL_REGISTER_URL", "")).strip()
        token = str(os.getenv("SAPPHIRE_SCOUT_EXTERNAL_API_TOKEN", "")).strip()
        token_for_dispatch = token
        if self._is_moltbook_api_url(register_url):
            outbound_payload = {
                "name": display_name[:60] or username,
                "description": bio_safe["text"][:280] or "Sapphire external collaboration scout",
            }
            token_for_dispatch = ""
        note = (
            "Register least-privilege Sapphire scout account for external collaboration. "
            "No secrets, no trade execution, and no cloud mutations. "
            f"Username: @{username}. Display: {display_name[:60]}."
        )
        dispatch_result = await self._dispatch_scout_bridge(
            action="register",
            outbound_payload=outbound_payload,
            external_url=register_url,
            external_token=token_for_dispatch,
            note=note,
        )

        with self._lock:
            self._scout_registration.update(
                {
                    "registered": bool(dispatch_result.get("dispatched")),
                    "username": username,
                    "display_name": display_name[:60],
                    "registered_at": self._now() if dispatch_result.get("dispatched") else 0,
                    "last_dispatch": dispatch_result,
                }
            )

            metadata = dispatch_result.get("metadata", {}) if isinstance(dispatch_result, dict) else {}
            claim_url = str(metadata.get("claim_url", "")).strip()
            verification_code = str(metadata.get("verification_code", "")).strip()
            topic_body = (
                f"Scout registration requested for @{username}. "
                f"Dispatch={'ok' if dispatch_result.get('dispatched') else 'pending/manual'} "
                f"via {dispatch_result.get('mode', 'none')}."
            )
            if claim_url:
                topic_body += f" Claim URL: {claim_url}"
            if verification_code:
                topic_body += f" Verification code: {verification_code}"
            self._create_topic_locked(
                {
                    "title": f"Scout registration: @{username}",
                    "body": topic_body,
                    "lane": "external",
                    "state": "queued" if not dispatch_result.get("dispatched") else "open",
                    "priority": "medium",
                    "author": "SAPPHIRE",
                    "tags": ["scout", "registration", "moltbook"],
                    "source": "system",
                },
                persist=False,
            )
            self._save_locked()

        return {
            "ok": True,
            "registration": {
                "username": username,
                "display_name": display_name[:60],
                "bio_redactions": int(bio_safe["redactions"]),
            },
            "dispatch": dispatch_result,
            "profile": profile,
            "timestamp": self._now(),
        }

    async def publish_scout_note(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        topic_id = str(payload.get("topic_id", "")).strip()
        title_safe = self._sanitize_text(payload.get("title", ""), max_len=120)
        body_safe = self._sanitize_text(payload.get("body", ""), max_len=4000)

        if not body_safe["text"].strip():
            return {"ok": False, "error": "body_required"}

        created_topic_id = ""
        created_reply_id = ""

        with self._lock:
            if topic_id:
                try:
                    reply = self._add_reply_locked(
                        topic_id,
                        {
                            "body": body_safe["text"],
                            "author": payload.get("author", "SAPPHIRE_SCOUT"),
                            "kind": payload.get("kind", "note"),
                            "source": "scout",
                        },
                        persist=False,
                    )
                except ValueError:
                    return {"ok": False, "error": "topic_not_found", "topic_id": topic_id}
                created_reply_id = str(reply.get("reply_id", ""))
            else:
                if not title_safe["text"].strip():
                    return {"ok": False, "error": "title_required"}
                topic = self._create_topic_locked(
                    {
                        "title": title_safe["text"],
                        "body": body_safe["text"],
                        "lane": payload.get("lane", "external"),
                        "state": payload.get("state", "open"),
                        "priority": payload.get("priority", "medium"),
                        "author": payload.get("author", "SAPPHIRE_SCOUT"),
                        "tags": payload.get("tags", ["scout", "external"]),
                        "source": "scout",
                    },
                    persist=False,
                )
                created_topic_id = str(topic.get("topic_id", ""))
                topic_id = created_topic_id

            self._save_locked()

        outbound_payload = {
            "topic_id": topic_id,
            "title": title_safe["text"],
            "body": body_safe["text"],
            "author": str(payload.get("author", "SAPPHIRE_SCOUT")).strip() or "SAPPHIRE_SCOUT",
            "kind": str(payload.get("kind", "note")).strip() or "note",
            "tags": self._normalize_tags(payload.get("tags", [])),
            "timestamp": self._now(),
        }

        post_url = str(os.getenv("SAPPHIRE_SCOUT_EXTERNAL_POST_URL", "")).strip()
        token = str(os.getenv("SAPPHIRE_SCOUT_EXTERNAL_API_TOKEN", "")).strip()
        if self._is_moltbook_api_url(post_url):
            outbound_payload = {
                "submolt": (
                    str(payload.get("submolt", payload.get("community", "general"))).strip().lower()
                    or "general"
                ),
                "title": title_safe["text"] or f"Sapphire Scout Update ({topic_id})",
                "content": body_safe["text"],
            }
        note = (
            "Publish sanitized external scout note from SapphireBook collaboration thread. "
            f"Topic: {topic_id}. Author: {outbound_payload.get('author', 'SAPPHIRE_SCOUT')}."
        )
        dispatch_result = await self._dispatch_scout_bridge(
            action="publish",
            outbound_payload=outbound_payload,
            external_url=post_url,
            external_token=token,
            note=note,
        )

        return {
            "ok": True,
            "topic_id": topic_id,
            "created_topic_id": created_topic_id,
            "created_reply_id": created_reply_id,
            "redactions": int(title_safe["redactions"] + body_safe["redactions"]),
            "dispatch": dispatch_result,
            "timestamp": self._now(),
        }
