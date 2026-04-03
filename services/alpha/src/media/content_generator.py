"""
AI-powered content generation for Sapphire social media.

Uses Gemini to transform system data (forum topics, trade metrics, system logs,
episodic memory) into polished social media content for X, Substack, and LinkedIn.

Quality controls:
- Gemini quality scoring (0.0-1.0) with configurable threshold
- Anti-slop detection (generic filler, excessive emojis, AI-sounding phrases)
- Min interval enforcement between posts per channel
- Content length validation per platform
"""

import os
import re
import time
from typing import Any

from loguru import logger

# ── Platform constraints ────────────────────────────────────────────

PLATFORM_LIMITS = {
    "twitter": {"max_chars": 280, "max_thread": 8},
    "substack": {"max_chars": 50_000, "min_chars": 500},
    "linkedin": {"max_chars": 3000},
}

# Phrases that signal low-quality AI-generated content
_SLOP_PATTERNS: list[re.Pattern] = [
    re.compile(r"(?i)\bin this article\b"),
    re.compile(r"(?i)\blet'?s dive in\b"),
    re.compile(r"(?i)\bin conclusion\b"),
    re.compile(r"(?i)\bbuckle up\b"),
    re.compile(r"(?i)\bgame.?changer\b"),
    re.compile(r"(?i)\bexciting times?\b"),
    re.compile(r"(?i)\bstay tuned\b"),
    re.compile(r"(?i)\bwithout further ado\b"),
    re.compile(r"(?i)\bthe future (is|looks) (bright|promising)\b"),
    re.compile(r"(?i)\bunlock(ing)? the (power|potential)\b"),
    re.compile(r"(?i)\brevolutioniz(e|ing)\b"),
    re.compile(r"(?i)\btransform(ative|ing)?\b.*\blandscape\b"),
]

# Maximum emoji density (emojis per 100 chars)
_MAX_EMOJI_DENSITY = 5.0


class ContentGenerator:
    """
    Generates social media content from system data using Gemini.

    Provides per-platform content generation with quality scoring,
    slop detection, and format validation.
    """

    def __init__(self, gemini_guard: Any = None):
        self.gemini = gemini_guard
        self.quality_threshold = float(
            os.getenv("SAPPHIRE_MEDIA_QUALITY_THRESHOLD", "0.6")
        )
        self.min_post_interval = int(
            os.getenv("SAPPHIRE_MEDIA_MIN_INTERVAL_SECONDS", "3600")
        )
        self.last_generation: dict[str, float] = {}
        self._generation_count = 0

    # ── Public API ──────────────────────────────────────────────

    async def generate_tweet(
        self,
        context: dict[str, Any],
        topic: str = "",
    ) -> dict[str, Any]:
        """Generate a tweet or thread from system context."""
        if not self._check_interval("twitter"):
            return {"ok": False, "reason": "min_interval_not_met"}

        prompt = self._build_tweet_prompt(context, topic)
        raw = await self._call_gemini(prompt)
        if not raw:
            return {"ok": False, "reason": "gemini_unavailable"}

        quality = self._score_quality(raw, "twitter")
        if quality["score"] < self.quality_threshold:
            return {
                "ok": False,
                "reason": "below_quality_threshold",
                "score": quality["score"],
                "issues": quality["issues"],
                "draft": raw,
            }

        self.last_generation["twitter"] = time.time()
        self._generation_count += 1
        return {
            "ok": True,
            "content": raw,
            "platform": "twitter",
            "quality": quality,
            "topic": topic,
        }

    async def generate_substack(
        self,
        context: dict[str, Any],
        topic: str = "",
    ) -> dict[str, Any]:
        """Generate a Substack article from system context."""
        if not self._check_interval("substack"):
            return {"ok": False, "reason": "min_interval_not_met"}

        prompt = self._build_substack_prompt(context, topic)
        raw = await self._call_gemini(prompt)
        if not raw:
            return {"ok": False, "reason": "gemini_unavailable"}

        quality = self._score_quality(raw, "substack")
        if quality["score"] < self.quality_threshold:
            return {
                "ok": False,
                "reason": "below_quality_threshold",
                "score": quality["score"],
                "issues": quality["issues"],
                "draft": raw,
            }

        self.last_generation["substack"] = time.time()
        self._generation_count += 1
        return {
            "ok": True,
            "content": raw,
            "platform": "substack",
            "quality": quality,
            "topic": topic,
        }

    async def generate_linkedin(
        self,
        context: dict[str, Any],
        topic: str = "",
    ) -> dict[str, Any]:
        """Generate a LinkedIn post from system context."""
        if not self._check_interval("linkedin"):
            return {"ok": False, "reason": "min_interval_not_met"}

        prompt = self._build_linkedin_prompt(context, topic)
        raw = await self._call_gemini(prompt)
        if not raw:
            return {"ok": False, "reason": "gemini_unavailable"}

        quality = self._score_quality(raw, "linkedin")
        if quality["score"] < self.quality_threshold:
            return {
                "ok": False,
                "reason": "below_quality_threshold",
                "score": quality["score"],
                "issues": quality["issues"],
                "draft": raw,
            }

        self.last_generation["linkedin"] = time.time()
        self._generation_count += 1
        return {
            "ok": True,
            "content": raw,
            "platform": "linkedin",
            "quality": quality,
            "topic": topic,
        }

    async def generate_for_platform(
        self,
        platform: str,
        context: dict[str, Any],
        topic: str = "",
    ) -> dict[str, Any]:
        """Route to the correct platform generator."""
        platform = platform.lower().strip()
        if platform in ("twitter", "x"):
            return await self.generate_tweet(context, topic)
        elif platform == "substack":
            return await self.generate_substack(context, topic)
        elif platform in ("linkedin", "li"):
            return await self.generate_linkedin(context, topic)
        return {"ok": False, "reason": f"unknown_platform:{platform}"}

    def stats(self) -> dict[str, Any]:
        """Return generation statistics."""
        return {
            "generation_count": self._generation_count,
            "quality_threshold": self.quality_threshold,
            "min_post_interval_seconds": self.min_post_interval,
            "last_generation": {
                k: int(v) for k, v in self.last_generation.items()
            },
        }

    # ── Quality scoring ─────────────────────────────────────────

    def _score_quality(self, text: str, platform: str) -> dict[str, Any]:
        """Score content quality. Returns {score: float, issues: list}."""
        issues: list[str] = []
        score = 1.0

        # 1. Slop detection
        slop_count = sum(1 for p in _SLOP_PATTERNS if p.search(text))
        if slop_count > 0:
            penalty = min(0.4, slop_count * 0.1)
            score -= penalty
            issues.append(f"slop_phrases:{slop_count}")

        # 2. Emoji density
        emoji_count = len(re.findall(
            r"[\U0001f300-\U0001f9ff\u2600-\u26ff\u2700-\u27bf]", text
        ))
        text_len = max(1, len(text))
        density = (emoji_count / text_len) * 100
        if density > _MAX_EMOJI_DENSITY:
            score -= 0.2
            issues.append(f"emoji_density:{density:.1f}")

        # 3. Platform length check
        limits = PLATFORM_LIMITS.get(platform, {})
        max_chars = limits.get("max_chars", 50_000)
        min_chars = limits.get("min_chars", 0)
        if len(text) > max_chars:
            score -= 0.15
            issues.append(f"over_length:{len(text)}/{max_chars}")
        if min_chars and len(text) < min_chars:
            score -= 0.15
            issues.append(f"under_length:{len(text)}/{min_chars}")

        # 4. Empty or trivially short
        if len(text.strip()) < 20:
            score -= 0.5
            issues.append("too_short")

        # 5. Repetition detection (same sentence appears twice)
        sentences = [s.strip() for s in re.split(r"[.!?\n]", text) if s.strip()]
        if len(sentences) != len(set(sentences)):
            score -= 0.15
            issues.append("repetition")

        score = max(0.0, min(1.0, score))
        return {"score": round(score, 2), "issues": issues}

    # ── Interval enforcement ────────────────────────────────────

    def _check_interval(self, platform: str) -> bool:
        """Return True if enough time has passed since last generation."""
        last = self.last_generation.get(platform, 0)
        return (time.time() - last) >= self.min_post_interval

    # ── Prompt builders ─────────────────────────────────────────

    def _build_tweet_prompt(self, ctx: dict[str, Any], topic: str) -> str:
        data_block = self._format_context_block(ctx)
        topic_line = f"Topic focus: {topic}\n" if topic else ""
        return (
            "You are the public voice of Sapphire, an autonomous crypto trading research lab.\n"
            "Write a single tweet (max 280 chars) that is:\n"
            "- Technically specific (cite a metric, insight, or decision)\n"
            "- Not generic hype or filler\n"
            "- No hashtags unless organic\n"
            "- No 'exciting times', 'stay tuned', or AI-slop phrases\n"
            "- Tone: confident engineer sharing real findings\n\n"
            f"{topic_line}"
            f"System data:\n{data_block}\n\n"
            "Respond ONLY with the tweet text. Nothing else."
        )

    def _build_substack_prompt(self, ctx: dict[str, Any], topic: str) -> str:
        data_block = self._format_context_block(ctx)
        topic_line = f"Topic focus: {topic}\n" if topic else ""
        return (
            "You are the editorial voice of Sapphire, an autonomous crypto trading research lab.\n"
            "Write a weekly Substack lab note (800-1500 words, markdown) covering:\n"
            "1. What was built or changed this period (be specific)\n"
            "2. Key metrics and their trends\n"
            "3. Incidents and what was learned\n"
            "4. What's being tested next and why\n\n"
            "Rules:\n"
            "- Write like an engineering blog, not marketing copy\n"
            "- Include real numbers from the data\n"
            "- No AI-slop phrases ('dive in', 'exciting times', 'game-changer')\n"
            "- Use code formatting for technical terms\n"
            "- Be honest about failures and uncertainties\n\n"
            f"{topic_line}"
            f"System data:\n{data_block}\n\n"
            "Respond ONLY with the article in markdown. Start with the title as a # heading."
        )

    def _build_linkedin_prompt(self, ctx: dict[str, Any], topic: str) -> str:
        data_block = self._format_context_block(ctx)
        topic_line = f"Topic focus: {topic}\n" if topic else ""
        return (
            "You are the professional voice of Sapphire, an autonomous crypto trading research lab.\n"
            "Write a LinkedIn post (500-2000 chars) that:\n"
            "- Leads with a specific technical insight or result\n"
            "- Is professional but not corporate-speak\n"
            "- Includes 1-2 concrete metrics or decisions\n"
            "- Ends with a thoughtful observation, not a CTA\n"
            "- No AI-slop phrases or excessive emojis\n\n"
            f"{topic_line}"
            f"System data:\n{data_block}\n\n"
            "Respond ONLY with the post text. Nothing else."
        )

    def _format_context_block(self, ctx: dict[str, Any]) -> str:
        """Format system context into a structured data block for the prompt."""
        lines: list[str] = []

        # Trade metrics
        metrics = ctx.get("metrics", {})
        if metrics:
            lines.append("Trade metrics:")
            for k, v in metrics.items():
                lines.append(f"  {k}: {v}")

        # Recent forum topics
        forum = ctx.get("forum_topics", [])
        if forum:
            lines.append("Recent forum topics:")
            for t in forum[:5]:
                title = t.get("title", "untitled")
                lane = t.get("lane", "general")
                lines.append(f"  [{lane}] {title}")

        # Execution state
        execution = ctx.get("execution", {})
        if execution:
            lines.append("Execution state:")
            for k, v in execution.items():
                lines.append(f"  {k}: {v}")

        # Recent system events
        events = ctx.get("events", [])
        if events:
            lines.append("Recent events:")
            for e in events[:8]:
                lines.append(f"  - {e}")

        # Memory insights
        memory = ctx.get("memory_insights", [])
        if memory:
            lines.append("Memory insights:")
            for m in memory[:5]:
                lines.append(f"  - {m}")

        # Swarm intelligence
        swarm = ctx.get("swarm", {})
        if swarm:
            lines.append("Swarm intelligence:")
            for k, v in swarm.items():
                lines.append(f"  {k}: {v}")

        return "\n".join(lines) if lines else "(no data available)"

    # ── Gemini call ─────────────────────────────────────────────

    async def _call_gemini(self, prompt: str) -> str | None:
        """Call Gemini via the guard's chat method."""
        if not self.gemini:
            logger.warning("ContentGenerator: no Gemini guard available")
            return None
        try:
            result = await self.gemini.chat_with_owner(
                message=prompt,
                system_context="You are a content generation assistant for Sapphire's social media.",
            )
            return result
        except Exception as e:
            logger.error(f"ContentGenerator Gemini call failed: {e}")
            return None
