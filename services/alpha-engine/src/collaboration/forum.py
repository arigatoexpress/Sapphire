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

from src.security.prompt_sanitizer import detect_injection, log_injection_attempt


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

    # ── Phase 3: Categories, Scoring, Agent Profiles ───────────────
    VALID_CATEGORIES = {
        "trade_idea",       # Actionable trade setups
        "strategy",         # Strategy design & backtesting
        "market_analysis",  # Market structure, sentiment, macro
        "platform",         # Infrastructure, venues, deployment
        "general",          # Default catch-all
    }

    AGENT_PROFILES = {
        "SAPPHIRE": {
            "emoji": "💎",
            "name": "Sapphire",
            "role": "Chief Execution Officer",
            "expertise": ["trade execution", "venue management", "order routing", "fill analysis"],
            "voice": "Direct, tactical, execution-focused. Speaks in short decisive sentences.",
            "perspective": "Always evaluating: can we execute this? What's the fill risk?",
        },
        "OBSIDIAN": {
            "emoji": "🖤",
            "name": "Obsidian",
            "role": "Chief Infrastructure Officer",
            "expertise": ["cloud deployment", "system reliability", "monitoring", "security"],
            "voice": "Methodical, cautious, systems-thinking. Asks about edge cases.",
            "perspective": "Will this break production? What's the failure mode?",
        },
        "EMERALD": {
            "emoji": "💚",
            "name": "Emerald",
            "role": "Chief Strategy Officer",
            "expertise": ["strategy design", "performance analysis", "risk modeling", "cognition"],
            "voice": "Analytical, thoughtful, data-driven. Cites evidence and patterns.",
            "perspective": "What does the data say? How does this compare to historical performance?",
        },
        "SCOUT": {
            "emoji": "🔭",
            "name": "Scout",
            "role": "External Collaboration Agent",
            "expertise": ["community outreach", "idea gathering", "public communication"],
            "voice": "Friendly, curious, community-oriented. Bridges internal and external.",
            "perspective": "What are other agents saying? What ideas can we bring in?",
        },
    }

    _SENSITIVE_INLINE_RE = re.compile(
        r"(?i)\b(api[_-]?key|token|secret|password|private[_-]?key|access[_-]?key|refresh[_-]?token|authorization|cookie|session)\b\s*[:=]\s*([^\s,;]+)"
    )
    _SENSITIVE_QUERY_RE = re.compile(
        r"(?i)([?&](?:token|access_token|api_key|key|secret)=)([^&\s]+)"
    )
    _GOOGLE_KEY_RE = re.compile(r"AIza[0-9A-Za-z\-_]{20,}")
    _MOLTBOOK_KEY_RE = re.compile(r"\bmoltbook_[A-Za-z0-9\-_]{8,}\b", flags=re.IGNORECASE)
    _JWT_RE = re.compile(r"\beyJ[a-zA-Z0-9_\-]{8,}\.[a-zA-Z0-9_\-]{8,}\.[a-zA-Z0-9_\-]{8,}\b")
    _MOLTBOOK_NUMERIC_CHALLENGE_RE = re.compile(
        r"(-?\d+(?:\.\d+)?)\s*(\+|-|\*|x|×|/|÷)\s*(-?\d+(?:\.\d+)?)",
        flags=re.IGNORECASE,
    )

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

    @classmethod
    def _normalize_category(cls, category: Any) -> str:
        candidate = str(category or "").strip().lower().replace(" ", "_").replace("-", "_")
        aliases = {
            "trade": "trade_idea",
            "trade_ideas": "trade_idea",
            "idea": "trade_idea",
            "setup": "trade_idea",
            "signal": "trade_idea",
            "strat": "strategy",
            "backtest": "strategy",
            "market": "market_analysis",
            "analysis": "market_analysis",
            "macro": "market_analysis",
            "sentiment": "market_analysis",
            "infra": "platform",
            "deploy": "platform",
            "venue": "platform",
            "ops": "platform",
        }
        value = aliases.get(candidate, candidate)
        if value in cls.VALID_CATEGORIES:
            return value
        return "general"

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

        # Prompt injection detection on forum content
        injection = detect_injection(text)
        injection_blocked = False
        if injection.is_suspicious:
            log_injection_attempt("forum_content", injection, agent_id="forum")
            logger.warning(
                f"⚠️ Injection detected in forum content (risk={injection.risk_score}): "
                f"{[f['category'] for f in injection.findings]}"
            )
            if injection.risk_score >= 0.6:
                text = "[CONTENT BLOCKED — prompt injection detected]"
                injection_blocked = True

        return {
            "text": text,
            "redactions": redactions,
            "blocked": injection_blocked,
            "injection_risk": injection.risk_score if injection.is_suspicious else 0.0,
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
            "category": str(topic.get("category", "general")),
            "state": str(topic.get("state", "open")),
            "priority": str(topic.get("priority", "medium")),
            "author": str(topic.get("author", "SAPPHIRE")),
            "source": str(topic.get("source", "internal")),
            "tags": list(topic.get("tags", [])),
            "score": float(topic.get("score", 0.0)),
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
        # Phase 3 fields
        detail["category"] = str(topic.get("category", "general"))
        detail["upvotes"] = int(topic.get("upvotes", 0))
        detail["downvotes"] = int(topic.get("downvotes", 0))
        detail["score"] = float(topic.get("score", 0.0))
        detail["voters"] = list(topic.get("voters", []))
        if "approval" in topic:
            detail["approval"] = dict(topic["approval"])
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

        category = self._normalize_category(payload.get("category", "general"))

        now = self._now()
        topic = {
            "topic_id": self._new_topic_id_locked(),
            "title": title,
            "body": body,
            "lane": lane,
            "category": category,
            "state": state,
            "priority": priority,
            "author": author,
            "source": source,
            "tags": tags,
            "created_at": now,
            "updated_at": now,
            "redactions": int(title_safe["redactions"] + body_safe["redactions"]),
            # Phase 3: scoring
            "upvotes": 0,
            "downvotes": 0,
            "score": 0.0,
            "voters": [],  # List of agent_ids that have voted
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

        parent_reply_id = str(payload.get("parent_reply_id", "") or "").strip()

        reply = {
            "reply_id": self._new_reply_id_locked(),
            "topic_id": topic_id,
            "parent_reply_id": parent_reply_id,  # Phase 3: threading
            "author": author,
            "body": body,
            "kind": reply_kind,
            "source": source,
            "created_at": self._now(),
            "redactions": int(body_safe["redactions"]),
            # Phase 3: scoring & quality
            "upvotes": 0,
            "downvotes": 0,
            "quality": {
                "helpfulness": 0.0,
                "accuracy": 0.0,
                "ratings_count": 0,
            },
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

    # ── Phase 3: Voting, Quality, Agent Profiles ───────────────────

    def vote_topic(self, topic_id: str, voter_id: str, direction: str) -> Dict[str, Any]:
        """Upvote or downvote a topic. Each agent can vote once."""
        with self._lock:
            topic = next((t for t in self._topics if t.get("topic_id") == topic_id), None)
            if not topic:
                return {"ok": False, "error": "topic_not_found"}
            voter = str(voter_id or "").strip().upper()
            if voter in topic.get("voters", []):
                return {"ok": False, "error": "already_voted"}
            if direction == "up":
                topic["upvotes"] = topic.get("upvotes", 0) + 1
            elif direction == "down":
                topic["downvotes"] = topic.get("downvotes", 0) + 1
            else:
                return {"ok": False, "error": "invalid_direction"}
            topic.setdefault("voters", []).append(voter)
            topic["score"] = float(topic.get("upvotes", 0)) - float(topic.get("downvotes", 0))
            self._save_locked()
            return {"ok": True, "score": topic["score"], "upvotes": topic["upvotes"], "downvotes": topic["downvotes"]}

    def vote_reply(self, reply_id: str, voter_id: str, direction: str) -> Dict[str, Any]:
        """Upvote or downvote a reply."""
        with self._lock:
            for bucket in self._replies.values():
                for reply in bucket:
                    if reply.get("reply_id") == reply_id:
                        if direction == "up":
                            reply["upvotes"] = reply.get("upvotes", 0) + 1
                        elif direction == "down":
                            reply["downvotes"] = reply.get("downvotes", 0) + 1
                        else:
                            return {"ok": False, "error": "invalid_direction"}
                        self._save_locked()
                        return {"ok": True, "upvotes": reply.get("upvotes", 0), "downvotes": reply.get("downvotes", 0)}
            return {"ok": False, "error": "reply_not_found"}

    def rate_reply_quality(self, reply_id: str, rater_id: str, helpfulness: float, accuracy: float) -> Dict[str, Any]:
        """Rate a reply's quality (0.0–1.0 scale). Rolling average."""
        with self._lock:
            for bucket in self._replies.values():
                for reply in bucket:
                    if reply.get("reply_id") == reply_id:
                        q = reply.setdefault("quality", {"helpfulness": 0.0, "accuracy": 0.0, "ratings_count": 0})
                        n = q.get("ratings_count", 0)
                        h = max(0.0, min(1.0, float(helpfulness)))
                        a = max(0.0, min(1.0, float(accuracy)))
                        # Rolling average
                        q["helpfulness"] = (q["helpfulness"] * n + h) / (n + 1)
                        q["accuracy"] = (q["accuracy"] * n + a) / (n + 1)
                        q["ratings_count"] = n + 1
                        self._save_locked()
                        return {"ok": True, "quality": q}
            return {"ok": False, "error": "reply_not_found"}

    def get_agent_profile(self, agent_id: str) -> Optional[Dict[str, Any]]:
        """Return the personality profile for an agent."""
        key = str(agent_id or "").strip().upper()
        return self.AGENT_PROFILES.get(key)

    def list_agent_profiles(self) -> Dict[str, Dict[str, Any]]:
        """Return all agent personality profiles."""
        return dict(self.AGENT_PROFILES)

    def get_thread(self, topic_id: str, parent_reply_id: str = "") -> List[Dict[str, Any]]:
        """Return threaded replies for a topic, optionally under a parent reply."""
        with self._lock:
            all_replies = self._replies.get(topic_id, [])
            if parent_reply_id:
                return [r for r in all_replies if r.get("parent_reply_id") == parent_reply_id]
            # Top-level replies (no parent)
            return [r for r in all_replies if not r.get("parent_reply_id")]

    def get_top_topics(self, limit: int = 10, category: str = "") -> List[Dict[str, Any]]:
        """Return topics sorted by score, optionally filtered by category."""
        with self._lock:
            filtered = list(self._topics)
            if category:
                norm_cat = self._normalize_category(category)
                filtered = [t for t in filtered if t.get("category") == norm_cat]
            sorted_topics = sorted(filtered, key=lambda t: float(t.get("score", 0)), reverse=True)
            return [self._topic_summary_locked(t) for t in sorted_topics[:limit]]

    # ── Phase 3: Forum-based Approval Workflows ─────────────────

    APPROVAL_THRESHOLD = 2  # Minimum upvotes needed for auto-approval
    REJECTION_THRESHOLD = 2  # Minimum downvotes needed for auto-rejection

    def create_approval_topic(
        self,
        title: str,
        body: str,
        session_key: str,
        author: str = "SAPPHIRE",
        category: str = "platform",
    ) -> Dict[str, Any]:
        """Create a forum topic for an approval workflow.

        The topic is tagged with 'approval' and stores the session_key in metadata.
        Agents can vote (up=approve, down=reject) and add reply comments.
        """
        payload = {
            "title": title,
            "body": body,
            "lane": "governance",
            "category": category,
            "state": "open",
            "priority": "high",
            "author": author,
            "tags": ["approval", "governance"],
            "source": "system",
        }
        with self._lock:
            topic = self._create_topic_locked(payload, persist=True)
            # Store approval metadata directly on the topic
            for t in self._topics:
                if t.get("topic_id") == topic.get("topic_id"):
                    t["approval"] = {
                        "session_key": str(session_key),
                        "status": "pending",  # pending | approved | rejected | expired
                        "created_at": self._now(),
                        "resolved_at": "",
                        "resolution_reason": "",
                    }
                    break
            self._save_locked()
        return topic

    def resolve_approval(self, topic_id: str) -> Dict[str, Any]:
        """Check if an approval topic has reached a decision threshold.

        Returns the current state: pending, approved, rejected, or the vote tally.
        Auto-resolves if votes meet threshold.
        """
        with self._lock:
            topic = next((t for t in self._topics if t.get("topic_id") == topic_id), None)
            if not topic:
                return {"ok": False, "error": "topic_not_found"}
            approval = topic.get("approval")
            if not approval:
                return {"ok": False, "error": "not_an_approval_topic"}
            if approval["status"] != "pending":
                return {
                    "ok": True,
                    "status": approval["status"],
                    "session_key": approval.get("session_key", ""),
                    "resolved_at": approval.get("resolved_at", ""),
                    "reason": approval.get("resolution_reason", ""),
                    "score": float(topic.get("score", 0)),
                    "upvotes": int(topic.get("upvotes", 0)),
                    "downvotes": int(topic.get("downvotes", 0)),
                }

            upvotes = int(topic.get("upvotes", 0))
            downvotes = int(topic.get("downvotes", 0))
            score = float(topic.get("score", 0))

            status = "pending"
            reason = ""
            if upvotes >= self.APPROVAL_THRESHOLD and score > 0:
                status = "approved"
                reason = f"Consensus reached: {upvotes} upvotes, {downvotes} downvotes"
            elif downvotes >= self.REJECTION_THRESHOLD and score < 0:
                status = "rejected"
                reason = f"Rejected by consensus: {downvotes} downvotes, {upvotes} upvotes"

            if status != "pending":
                approval["status"] = status
                approval["resolved_at"] = self._now()
                approval["resolution_reason"] = reason
                topic["state"] = "closed"
                self._save_locked()

            return {
                "ok": True,
                "status": status,
                "session_key": approval.get("session_key", ""),
                "resolved_at": approval.get("resolved_at", ""),
                "reason": reason,
                "score": score,
                "upvotes": upvotes,
                "downvotes": downvotes,
            }

    def list_pending_approvals(self) -> List[Dict[str, Any]]:
        """Return all pending approval topics."""
        with self._lock:
            results = []
            for t in self._topics:
                approval = t.get("approval")
                if approval and approval.get("status") == "pending":
                    results.append({
                        "topic_id": t.get("topic_id", ""),
                        "title": t.get("title", ""),
                        "session_key": approval.get("session_key", ""),
                        "score": float(t.get("score", 0)),
                        "upvotes": int(t.get("upvotes", 0)),
                        "downvotes": int(t.get("downvotes", 0)),
                        "voters": t.get("voters", []),
                        "created_at": approval.get("created_at", ""),
                    })
            return results

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
        is_moltbook_api = self._is_moltbook_api_url(url)

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
                            if isinstance(parsed.get("hint"), str):
                                metadata["hint"] = str(parsed.get("hint", ""))[:220]
                            if "retry_after_minutes" in parsed:
                                try:
                                    metadata["retry_after_minutes"] = max(
                                        0, int(float(parsed.get("retry_after_minutes", 0)))
                                    )
                                except (TypeError, ValueError):
                                    pass
                            if "retry_after_seconds" in parsed:
                                try:
                                    metadata["retry_after_seconds"] = max(
                                        0, int(float(parsed.get("retry_after_seconds", 0)))
                                    )
                                except (TypeError, ValueError):
                                    pass
                            if "is_new_agent" in parsed:
                                metadata["is_new_agent"] = bool(parsed.get("is_new_agent"))
                            if "new_agent_hours_remaining" in parsed:
                                try:
                                    metadata["new_agent_hours_remaining"] = max(
                                        0, int(float(parsed.get("new_agent_hours_remaining", 0)))
                                    )
                                except (TypeError, ValueError):
                                    pass
                            if bool(parsed.get("verification_required")):
                                metadata["verification_required"] = True
                            if isinstance(parsed.get("verification"), dict):
                                verification_obj = parsed.get("verification", {})
                                if verification_obj:
                                    metadata["verification_required"] = True
                                    metadata["verification_code"] = (
                                        str(verification_obj.get("code", "")).strip()[:80]
                                    )
                                    metadata["verification_challenge"] = (
                                        str(verification_obj.get("challenge", "")).strip()[:220]
                                    )
                                    metadata["verification_code_present"] = bool(
                                        metadata.get("verification_code", "")
                                    )
                                    metadata["verification_challenge_present"] = bool(
                                        metadata.get("verification_challenge", "")
                                    )
                            if isinstance(parsed.get("post"), dict):
                                post_obj = parsed.get("post", {})
                                metadata["post_id"] = str(post_obj.get("id", "")).strip()[:100]
                                metadata["post_url"] = str(post_obj.get("url", "")).strip()[:180]
                                metadata["post_verification_status"] = (
                                    str(post_obj.get("verification_status", "")).strip()[:40]
                                )

                        reason = "ok" if ok else ("api_error" if parsed else "http_error")
                        api_error_lower = str(metadata.get("api_error", "")).lower()
                        if ok and metadata.get("verification_required"):
                            reason = "ok_pending_verification"
                            auto_verify_enabled = (
                                str(os.getenv("SAPPHIRE_SCOUT_AUTO_VERIFY_ENABLED", "true")).strip().lower()
                                in {"1", "true", "yes", "on"}
                            )
                            metadata["verification_auto_enabled"] = auto_verify_enabled
                            if is_moltbook_api and auto_verify_enabled:
                                verification_code = str(metadata.get("verification_code", "")).strip()
                                verification_challenge = str(metadata.get("verification_challenge", "")).strip()
                                if verification_code and verification_challenge:
                                    verify_url = (
                                        str(os.getenv("SAPPHIRE_SCOUT_EXTERNAL_VERIFY_URL", "")).strip()
                                        or self._derive_moltbook_verify_url(url)
                                    )
                                    verify_result = await self._verify_moltbook_challenge(
                                        verify_url=verify_url,
                                        verification_code=verification_code,
                                        challenge=verification_challenge,
                                        token=token,
                                        timeout_seconds=timeout_value,
                                    )
                                    metadata["verification_attempted"] = True
                                    metadata["verification_reason"] = str(
                                        verify_result.get("reason", "unknown")
                                    ).strip()[:80]
                                    if verify_result.get("answer"):
                                        metadata["verification_answer"] = str(
                                            verify_result.get("answer", "")
                                        ).strip()[:40]
                                    if isinstance(verify_result.get("status"), int):
                                        metadata["verification_http_status"] = int(verify_result.get("status", 0))
                                    if verify_result.get("response_excerpt"):
                                        metadata["verification_response_excerpt"] = str(
                                            verify_result.get("response_excerpt", "")
                                        ).strip()[:240]
                                    if verify_result.get("verified"):
                                        reason = "ok_verified"
                                        metadata["verification_status"] = "verified"
                                    else:
                                        metadata["verification_status"] = "pending"
                                else:
                                    metadata["verification_attempted"] = False
                                    metadata["verification_reason"] = "challenge_missing"
                                    metadata["verification_status"] = "pending"
                        elif not ok and is_moltbook_api and api_error_lower:
                            if (
                                int(response.status) == 429
                                or "only post once every" in api_error_lower
                                or "slow down" in api_error_lower
                                or "comment again in" in api_error_lower
                            ):
                                reason = "moltbook_rate_limited"
                            elif "pending_claim" in api_error_lower or "pending claim" in api_error_lower:
                                reason = "moltbook_pending_claim"
                            elif (
                                "already registered" in api_error_lower
                                or "already exists" in api_error_lower
                                or "already taken" in api_error_lower
                            ):
                                reason = "moltbook_already_registered"

                        result = {
                            "dispatched": ok,
                            "status": int(response.status),
                            "reason": reason,
                            "response_excerpt": safe_excerpt,
                            "metadata": metadata,
                            "attempt": attempt,
                        }
                        if ok:
                            return result

                        last_result = result
                        retryable_http = (
                            int(response.status) >= 500 or int(response.status) in {408, 429}
                        ) and reason != "moltbook_rate_limited"
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

    @staticmethod
    def _derive_moltbook_verify_url(url: str) -> str:
        parsed = urlparse(str(url or "").strip())
        if not parsed.scheme or not parsed.netloc:
            return ""
        return f"{parsed.scheme}://{parsed.netloc}/api/v1/verify"

    @staticmethod
    def _compute_challenge_result(left: float, operator: str, right: float) -> Optional[float]:
        op = str(operator or "").strip().lower()
        if op in {"x", "×"}:
            op = "*"
        if op in {"÷"}:
            op = "/"
        if op == "+":
            return left + right
        if op == "-":
            return left - right
        if op == "*":
            return left * right
        if op == "/":
            if right == 0:
                return None
            return left / right
        return None

    _ALL_NUMBER_WORDS = {
        "zero", "one", "two", "three", "four", "five", "six", "seven",
        "eight", "nine", "ten", "eleven", "twelve", "thirteen", "fourteen",
        "fifteen", "sixteen", "seventeen", "eighteen", "nineteen",
        "twenty", "thirty", "forty", "fifty", "sixty", "seventy", "eighty",
        "ninety", "hundred", "thousand", "point", "and",
    }
    _ALL_OPERATOR_WORDS = {
        "plus", "minus", "times", "add", "subtract", "over", "divide",
        "divided", "multiplied", "another", "nother", "x",
    }
    _ALL_KNOWN_WORDS = _ALL_NUMBER_WORDS | _ALL_OPERATOR_WORDS

    @staticmethod
    def _normalize_word_token(token: str) -> str:
        value = str(token or "").strip().lower()
        if not value:
            return ""
        value = re.sub(r"(.)\1+", r"\1", value)
        return value

    @classmethod
    def _normalize_word_token_safe(cls, token: str) -> str:
        """Normalize an obfuscated word token while preserving naturally valid words."""
        value = str(token or "").strip().lower()
        if not value:
            return ""
        # If the token is already a known word, keep it as-is
        if value in cls._ALL_KNOWN_WORDS:
            return value
        # Otherwise, collapse repeated chars to handle obfuscation (e.g. "eiigghht" -> "eight")
        deduped = re.sub(r"(.)\1+", r"\1", value)
        if deduped in cls._ALL_KNOWN_WORDS:
            return deduped
        return value

    @classmethod
    def _words_to_number(cls, tokens: List[str]) -> Optional[float]:
        units = {
            "zero": 0,
            "one": 1,
            "two": 2,
            "three": 3,
            "four": 4,
            "five": 5,
            "six": 6,
            "seven": 7,
            "eight": 8,
            "nine": 9,
            "ten": 10,
            "eleven": 11,
            "twelve": 12,
            "thirteen": 13,
            "fourteen": 14,
            "fifteen": 15,
            "sixteen": 16,
            "seventeen": 17,
            "eighteen": 18,
            "nineteen": 19,
        }
        tens = {
            "twenty": 20,
            "thirty": 30,
            "forty": 40,
            "fifty": 50,
            "sixty": 60,
            "seventy": 70,
            "eighty": 80,
            "ninety": 90,
        }
        scales = {"hundred": 100, "thousand": 1000}
        clean = [
            cls._normalize_word_token_safe(str(token or "").strip().lower())
            for token in tokens
            if str(token or "").strip()
        ]
        if not clean:
            return None

        total = 0
        current = 0
        decimal_mode = False
        decimal_digits = ""
        consumed = False
        for token in clean:
            if token == "and":
                continue
            if token == "point":
                decimal_mode = True
                continue
            if decimal_mode:
                if token.isdigit():
                    decimal_digits += token
                    consumed = True
                    continue
                if token in units:
                    decimal_digits += str(units[token])
                    consumed = True
                    continue
                return None

            if token.isdigit():
                current += int(token)
                consumed = True
            elif token in units:
                current += units[token]
                consumed = True
            elif token in tens:
                current += tens[token]
                consumed = True
            elif token in scales:
                factor = scales[token]
                if factor == 100:
                    current = max(1, current) * factor
                else:
                    total += max(1, current) * factor
                    current = 0
                consumed = True
            else:
                return None

        if not consumed:
            return None

        value = float(total + current)
        if decimal_digits:
            value = float(f"{int(total + current)}.{decimal_digits}")
        return value

    @classmethod
    def _solve_moltbook_challenge(cls, challenge: str) -> Optional[str]:
        raw = str(challenge or "").strip().lower()
        if not raw:
            return None

        direct = cls._MOLTBOOK_NUMERIC_CHALLENGE_RE.search(raw)
        if direct:
            left = float(direct.group(1))
            operator = str(direct.group(2))
            right = float(direct.group(3))
            result = cls._compute_challenge_result(left, operator, right)
            if result is None:
                return None
            return f"{result:.2f}"

        # Strip noise characters (brackets, carets, tildes, pipes, braces, slashes, angle brackets, etc.)
        # Keep only alphanumeric, whitespace, basic math operators (+, -, *, ×, ÷), and common punctuation
        cleaned = re.sub(r"[^\w\s+\-*×÷.,?!:;']", " ", raw)
        # Normalize hyphens to spaces for compound words like "thirty-two"
        cleaned = cleaned.replace("-", " ")
        # Leetspeak substitutions (only between alpha chars to avoid mangling real digits)
        cleaned = re.sub(r"(?<=[a-z])0(?=[a-z])", "o", cleaned)
        cleaned = re.sub(r"(?<=[a-z])1(?=[a-z])", "i", cleaned)
        cleaned = re.sub(r"(?<=[a-z])3(?=[a-z])", "e", cleaned)
        cleaned = re.sub(r"(?<=[a-z])4(?=[a-z])", "a", cleaned)
        cleaned = re.sub(r"(?<=[a-z])5(?=[a-z])", "s", cleaned)
        cleaned = re.sub(r"(?<=[a-z])7(?=[a-z])", "t", cleaned)
        # Collapse whitespace
        cleaned = re.sub(r"\s+", " ", cleaned).strip()

        # Normalize unicode math operators to ASCII
        cleaned = cleaned.replace("×", " * ").replace("÷", " / ")

        # Operator phrase replacements (before tokenizing)
        replacements = [
            ("multiplied by", " * "),
            ("times", " * "),
            ("divided by", " / "),
            ("plus", " + "),
            ("minus", " - "),
            ("subtract", " - "),
            ("over", " / "),
        ]
        for source, target in replacements:
            cleaned = cleaned.replace(source, target)

        raw_tokens = re.findall(r"[a-z]+|\d+(?:\.\d+)?|[+\-*/]", cleaned)
        # Normalize tokens: try as-is first, only dedup repeated chars as fallback
        tokens = [cls._normalize_word_token_safe(token) if token.isalpha() else token for token in raw_tokens]
        if not tokens:
            return None

        parsed_tokens: List[Any] = []
        number_words = {
            "zero",
            "one",
            "two",
            "three",
            "four",
            "five",
            "six",
            "seven",
            "eight",
            "nine",
            "ten",
            "eleven",
            "twelve",
            "thirteen",
            "fourteen",
            "fifteen",
            "sixteen",
            "seventeen",
            "eighteen",
            "nineteen",
            "twenty",
            "thirty",
            "forty",
            "fifty",
            "sixty",
            "seventy",
            "eighty",
            "ninety",
            "hundred",
            "thousand",
            "point",
            "and",
        }

        idx = 0
        while idx < len(tokens):
            token = tokens[idx]
            if token in {"x", "times"}:
                parsed_tokens.append("*")
                idx += 1
                continue
            if token in {"another", "nother"}:
                # "another N" means "+ N"; skip if previous token is already an operator
                if not parsed_tokens or isinstance(parsed_tokens[-1], str):
                    idx += 1
                    continue
                parsed_tokens.append("+")
                idx += 1
                continue
            if token in {"plus", "add"}:
                parsed_tokens.append("+")
                idx += 1
                continue
            if token in {"minus", "subtract"}:
                parsed_tokens.append("-")
                idx += 1
                continue
            if token in {"over", "divide", "divided"}:
                parsed_tokens.append("/")
                idx += 1
                continue
            if token in {"+", "-", "*", "/"}:
                parsed_tokens.append(token)
                idx += 1
                continue

            if re.fullmatch(r"-?\d+(?:\.\d+)?", token):
                parsed_tokens.append(float(token))
                idx += 1
                continue

            if token in number_words:
                end = idx
                while end < len(tokens) and tokens[end] in number_words:
                    end += 1
                number_value = cls._words_to_number(tokens[idx:end])
                if number_value is not None:
                    parsed_tokens.append(number_value)
                    idx = end
                    continue
            idx += 1

        for offset in range(0, len(parsed_tokens) - 2):
            left = parsed_tokens[offset]
            operator = parsed_tokens[offset + 1]
            right = parsed_tokens[offset + 2]
            if isinstance(left, (int, float)) and isinstance(operator, str) and isinstance(right, (int, float)):
                result = cls._compute_challenge_result(float(left), operator, float(right))
                if result is not None:
                    return f"{result:.2f}"

        numeric_terms = [float(item) for item in parsed_tokens if isinstance(item, (int, float))]
        operators = [item for item in parsed_tokens if isinstance(item, str) and item in {"+", "-", "*", "/"}]
        if len(numeric_terms) >= 2 and not operators:
            return f"{sum(numeric_terms):.2f}"

        return None

    async def _verify_moltbook_challenge(
        self,
        *,
        verify_url: str,
        verification_code: str,
        challenge: str,
        token: str = "",
        timeout_seconds: int = 15,
    ) -> Dict[str, Any]:
        url = str(verify_url or "").strip()
        code = str(verification_code or "").strip()
        if not url or not code:
            return {"verified": False, "reason": "verify_url_or_code_missing"}

        answer = self._solve_moltbook_challenge(challenge)
        if not answer:
            return {"verified": False, "reason": "challenge_unsolved"}

        headers = {"Content-Type": "application/json"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        payload = {"verification_code": code, "answer": answer}

        timeout = aiohttp.ClientTimeout(total=max(5, min(int(timeout_seconds or 15), 60)))
        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(url, json=payload, headers=headers) as response:
                    response_text = await response.text()
                    safe_excerpt = self._sanitize_text(response_text, max_len=300)["text"]

                    parsed: Dict[str, Any] = {}
                    try:
                        maybe = json.loads(response_text)
                        if isinstance(maybe, dict):
                            parsed = maybe
                    except Exception:
                        parsed = {}

                    api_success = parsed.get("success")
                    verified = bool(parsed.get("verified"))
                    if not verified and isinstance(parsed.get("verification"), dict):
                        verification_obj = parsed.get("verification", {})
                        verified = (
                            str(verification_obj.get("status", "")).strip().lower() in {"verified", "complete"}
                        )
                    if (
                        not verified
                        and 200 <= int(response.status) < 300
                        and (not isinstance(api_success, bool) or bool(api_success))
                    ):
                        verified = True

                    reason = "verified" if verified else "verify_failed"
                    if not verified and int(response.status) == 429:
                        reason = "verify_rate_limited"
                    elif not verified and isinstance(parsed.get("error"), str):
                        error_text = str(parsed.get("error", "")).lower()
                        if "rate limit" in error_text:
                            reason = "verify_rate_limited"
                        elif "invalid" in error_text or "expired" in error_text:
                            reason = "verify_rejected"

                    return {
                        "verified": verified,
                        "reason": reason,
                        "status": int(response.status),
                        "answer": answer,
                        "response_excerpt": safe_excerpt,
                    }
        except Exception as exc:
            return {
                "verified": False,
                "reason": f"verify_request_failed:{exc}",
                "answer": answer,
            }

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

    @staticmethod
    def _scout_sandbox_config() -> Dict[str, Any]:
        sandbox_url = str(os.getenv("SAPPHIRE_SCOUT_SANDBOX_URL", "")).strip()
        sandbox_token = str(os.getenv("SAPPHIRE_SCOUT_SANDBOX_TOKEN", "")).strip()
        sandbox_enforce = (
            str(os.getenv("SAPPHIRE_SCOUT_SANDBOX_ENFORCE", "false")).strip().lower()
            in {"1", "true", "yes", "on"}
        )
        return {
            "url": sandbox_url,
            "token": sandbox_token,
            "enforce": sandbox_enforce,
            "ready": bool(sandbox_url and sandbox_token),
        }

    async def _dispatch_scout_sandbox(
        self,
        *,
        action: str,
        outbound_payload: Dict[str, Any],
        external_url: str,
        note: str,
    ) -> Dict[str, Any]:
        config = self._scout_sandbox_config()
        sandbox_url = str(config.get("url", "")).strip()
        sandbox_token = str(config.get("token", "")).strip()
        if not sandbox_url:
            return {"dispatched": False, "reason": "sandbox_url_missing", "mode": "scout_sandbox"}
        if not sandbox_token:
            return {"dispatched": False, "reason": "sandbox_token_missing", "mode": "scout_sandbox"}

        endpoint = f"{sandbox_url.rstrip('/')}/v1/scout/dispatch"
        payload = {
            "action": action,
            "outbound_payload": outbound_payload,
            "external_url_hint": str(external_url or "").strip(),
            "note": note,
            "source": "alpha-engine",
            "request_id": f"scout-{action}-{int(time.time() * 1000)}",
        }
        headers = {
            "Content-Type": "application/json",
            "X-Scout-Sandbox-Token": sandbox_token,
        }

        timeout = aiohttp.ClientTimeout(total=25)
        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(endpoint, json=payload, headers=headers) as response:
                    body = await response.text()
                    parsed: Dict[str, Any] = {}
                    try:
                        maybe = json.loads(body)
                        if isinstance(maybe, dict):
                            parsed = maybe
                    except Exception:
                        parsed = {}

                    if response.status >= 400:
                        return {
                            "dispatched": False,
                            "reason": f"sandbox_http_{response.status}",
                            "mode": "scout_sandbox",
                            "response_excerpt": self._sanitize_text(body, max_len=320)["text"],
                        }

                    dispatch = parsed.get("dispatch", {}) if isinstance(parsed.get("dispatch"), dict) else {}
                    result = {
                        "dispatched": bool(dispatch.get("dispatched", parsed.get("ok", False))),
                        "reason": str(dispatch.get("reason", "sandbox_dispatch_unknown")).strip()[:120],
                        "status": dispatch.get("status"),
                        "mode": "scout_sandbox",
                    }
                    if dispatch:
                        result["metadata"] = dispatch.get("metadata", {})
                        if dispatch.get("response_excerpt"):
                            result["response_excerpt"] = str(dispatch.get("response_excerpt", ""))[:320]
                    return result
        except Exception as exc:
            return {
                "dispatched": False,
                "reason": f"sandbox_request_failed:{exc}",
                "mode": "scout_sandbox",
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

        sandbox = self._scout_sandbox_config()
        sandbox_url = str(sandbox.get("url", "")).strip()
        sandbox_enforce = bool(sandbox.get("enforce"))
        if sandbox_url:
            sandbox_result = await self._dispatch_scout_sandbox(
                action=action,
                outbound_payload=outbound_payload,
                external_url=url,
                note=note,
            )
            sandbox_result["sandbox_enforce"] = sandbox_enforce
            if sandbox_result.get("dispatched"):
                return sandbox_result
            if sandbox_enforce:
                return sandbox_result
            logger.warning(
                "Scout sandbox dispatch failed (non-enforced mode), falling back to legacy bridge: "
                f"{sandbox_result.get('reason', 'unknown')}"
            )
        elif sandbox_enforce:
            return {
                "dispatched": False,
                "reason": "sandbox_required_not_configured",
                "mode": "scout_sandbox",
            }

        if url:
            external_result = await self._dispatch_external(url, outbound_payload, token=token)
            external_result["mode"] = "external_http"
            if external_result.get("dispatched"):
                return external_result
            if external_result.get("reason") in {
                "moltbook_rate_limited",
                "moltbook_pending_claim",
                "moltbook_already_registered",
            }:
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
        sandbox = self._scout_sandbox_config()
        sandbox_ready = bool(sandbox.get("ready"))
        sandbox_enforce = bool(sandbox.get("enforce"))
        fallback = self._openclaw_fallback_config()
        fallback_ready = bool(
            fallback.get("hook_url") and fallback.get("hook_token") and fallback.get("chat_id")
        )
        external_ready = bool(external_register_url and external_post_url and external_token_set)
        dispatch_mode = "scout_sandbox" if sandbox.get("url") else ("external_http" if external_register_url or external_post_url else "openclaw_hook")
        if sandbox_enforce and not sandbox_ready:
            dispatch_mode = "none"
        elif dispatch_mode == "openclaw_hook" and not fallback_ready:
            dispatch_mode = "none"
        provider = (
            "moltbook"
            if self._is_moltbook_api_url(external_register_url)
            or self._is_moltbook_api_url(external_post_url)
            else "generic"
        )

        with self._lock:
            registration = dict(self._scout_registration)
            runtime_registered = bool(registration.get("registered"))
            assumed_registered = bool(
                not runtime_registered and provider == "moltbook" and external_token_set
            )
            effective_registered = bool(runtime_registered or assumed_registered)
            if assumed_registered:
                registration["registered"] = True
                registration["registered_source"] = "api_token"
                if not str(registration.get("username", "")).strip():
                    registration["username"] = (
                        str(os.getenv("SAPPHIRE_SCOUT_USERNAME", "")).strip() or "sapphire_scout"
                    )
                if not str(registration.get("display_name", "")).strip():
                    registration["display_name"] = (
                        str(os.getenv("SAPPHIRE_SCOUT_DISPLAY_NAME", "")).strip() or "Sapphire Scout"
                    )
            else:
                registration["registered_source"] = "runtime_state"
            registration["registered_runtime"] = runtime_registered
            registration["assumed_registered"] = assumed_registered

            if sandbox_enforce and not sandbox_ready:
                provider_state = "sandbox_enforced_not_ready"
                operator_hint = "Configure SAPPHIRE_SCOUT_SANDBOX_URL + SAPPHIRE_SCOUT_SANDBOX_TOKEN before scout dispatch."
            elif dispatch_mode == "none":
                provider_state = "bridge_unconfigured"
                operator_hint = "Configure external bridge URLs or OpenClaw fallback hook settings."
            elif dispatch_mode == "scout_sandbox":
                provider_state = "sandbox_active" if sandbox_ready else "sandbox_configured_partial"
                operator_hint = (
                    "Scout sandbox is active; all external scout dispatch should route through sandbox controls."
                    if sandbox_ready
                    else "Complete sandbox token configuration to activate sandbox dispatch."
                )
            elif dispatch_mode == "openclaw_hook":
                provider_state = "fallback_only_ready" if fallback_ready else "fallback_not_ready"
                operator_hint = (
                    "OpenClaw fallback can deliver scout work; wire external Moltbook URLs to publish directly."
                    if fallback_ready
                    else "Configure fallback hook URL/token/chat to keep scout collaboration available."
                )
            elif provider == "moltbook" and not external_token_set:
                provider_state = "missing_api_token"
                operator_hint = "Add SAPPHIRE_SCOUT_EXTERNAL_API_TOKEN so external publish can execute."
            elif effective_registered:
                provider_state = "registered_active"
                operator_hint = (
                    "Scout bridge is active. Use /scout publish to send sanitized external summaries."
                )
            else:
                provider_state = "registration_required"
                operator_hint = "Run /scout register <username> to activate least-privilege scout identity."

            return {
                "profile": self._scout_profile(),
                "registration": registration,
                "external_bridge": {
                    "sandbox_url_configured": bool(sandbox.get("url")),
                    "sandbox_token_configured": bool(sandbox.get("token")),
                    "sandbox_ready": sandbox_ready,
                    "sandbox_enforce": sandbox_enforce,
                    "register_url_configured": bool(external_register_url),
                    "post_url_configured": bool(external_post_url),
                    "api_token_configured": external_token_set,
                    "fallback_hook_url_configured": bool(fallback.get("hook_url")),
                    "fallback_hook_token_configured": bool(fallback.get("hook_token")),
                    "fallback_chat_id_configured": bool(fallback.get("chat_id")),
                    "external_ready": external_ready,
                    "fallback_ready": fallback_ready,
                    "dispatch_mode": dispatch_mode,
                    "provider": provider,
                    "provider_state": provider_state,
                    "operator_hint": operator_hint,
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
        dispatch_result: Dict[str, Any]
        if self._is_moltbook_api_url(register_url):
            outbound_payload = {
                "name": display_name[:60] or username,
                "description": bio_safe["text"][:280] or "Sapphire external collaboration scout",
            }
            token_for_dispatch = ""
            if token:
                dispatch_result = {
                    "dispatched": True,
                    "reason": "moltbook_token_present",
                    "mode": "external_http",
                    "metadata": {
                        "already_registered": True,
                        "token_present": True,
                    },
                }
            else:
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
        else:
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
        if not dispatch_result.get("dispatched") and dispatch_result.get("reason") == "moltbook_already_registered":
            dispatch_result = dict(dispatch_result)
            dispatch_result["dispatched"] = True
            metadata = dispatch_result.get("metadata", {})
            metadata = dict(metadata) if isinstance(metadata, dict) else {}
            metadata["already_registered"] = True
            dispatch_result["metadata"] = metadata

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
        external_post_id = str(
            payload.get("post_id", payload.get("external_post_id", payload.get("moltbook_post_id", "")))
        ).strip()
        external_post_id = re.sub(r"[^A-Za-z0-9_\-]", "", external_post_id)[:80]
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
        dispatch_action = "publish"
        dispatch_url = post_url
        if self._is_moltbook_api_url(post_url):
            if external_post_id:
                configured_comment_url = str(os.getenv("SAPPHIRE_SCOUT_EXTERNAL_COMMENT_URL", "")).strip()
                if configured_comment_url:
                    if "{post_id}" in configured_comment_url:
                        dispatch_url = configured_comment_url.replace("{post_id}", external_post_id)
                    else:
                        dispatch_url = configured_comment_url
                else:
                    parsed_post_url = urlparse(post_url)
                    dispatch_url = (
                        f"{parsed_post_url.scheme}://{parsed_post_url.netloc}"
                        f"/api/v1/posts/{external_post_id}/comments"
                    )
                outbound_payload = {
                    "content": body_safe["text"],
                }
                dispatch_action = "comment"
            else:
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
            f"Topic: {topic_id}. Author: {outbound_payload.get('author', 'SAPPHIRE_SCOUT')}. "
            + (
                f"External action: comment on post {external_post_id}."
                if dispatch_action == "comment"
                else "External action: create post."
            )
        )
        dispatch_result = await self._dispatch_scout_bridge(
            action=dispatch_action,
            outbound_payload=outbound_payload,
            external_url=dispatch_url,
            external_token=token,
            note=note,
        )

        return {
            "ok": True,
            "topic_id": topic_id,
            "created_topic_id": created_topic_id,
            "created_reply_id": created_reply_id,
            "redactions": int(title_safe["redactions"] + body_safe["redactions"]),
            "dispatch_action": dispatch_action,
            "external_post_id": external_post_id,
            "dispatch": dispatch_result,
            "timestamp": self._now(),
        }
