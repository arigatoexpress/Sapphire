"""
Episodic Trading Memory - Reflection Agent

LLM-powered reflection that generates lessons from trading outcomes.
Runs after trades close to analyze what worked and what didn't.

This is a novel contribution to the ACTS trading system.
"""

import asyncio
import json
import logging
from typing import Any, Dict, Optional

from .episode import Episode, TradeOutcome

logger = logging.getLogger(__name__)


class ReflectionAgent:
    """
    LLM-powered agent that reflects on trading outcomes.

    After a trade closes, the ReflectionAgent:
    1. Analyzes the decision in context of the outcome
    2. Identifies what worked well
    3. Identifies what could be improved
    4. Extracts a concise lesson for future reference

    The lessons become part of the episode memory and are surfaced
    when similar market conditions are encountered.
    """

    def __init__(self):
        self._reflection_count = 0

    async def reflect(self, episode: Episode) -> Dict[str, str]:
        """
        Generate reflection for a completed episode.

        Args:
            episode: The episode with outcome filled in

        Returns:
            Dict with 'what_worked', 'what_failed', 'lesson'
        """
        if not episode.outcome:
            logger.warning(f"Cannot reflect on episode {episode.episode_id} without outcome")
            return {"what_worked": "", "what_failed": "", "lesson": ""}

        # Try LLM reflection first
        try:
            reflection = await self._llm_reflect(episode)
            if reflection:
                self._reflection_count += 1
                return reflection
        except Exception as e:
            logger.warning(f"LLM reflection failed: {e}")

        # Fallback to rule-based reflection
        return self._rule_based_reflect(episode)

    async def _llm_reflect(self, episode: Episode) -> Optional[Dict[str, str]]:
        """Use LLM to generate reflection."""
        try:
            from ..vertex_ai_client import get_vertex_client

            client = get_vertex_client()
            if not client:
                return None

            context = episode.to_reflection_prompt_context()

            prompt = f"""You are analyzing a trading decision to learn from it.

{context}

Based on this trade, provide a brief reflection:

1. What Worked: What aspects of the decision or execution were good? (1 sentence)
2. What Failed: What could have been done better? (1 sentence)
3. Lesson: What's the key takeaway to apply in similar future situations? (1 sentence, actionable)

Respond in JSON format:
{{
    "what_worked": "...",
    "what_failed": "...",
    "lesson": "..."
}}

Keep each response to 1-2 sentences maximum. Be specific and actionable.
"""

            response = await client.generate_content(prompt)
            text = response.text.strip()

            # Extract JSON from response
            if "{" in text and "}" in text:
                json_start = text.find("{")
                json_end = text.rfind("}") + 1
                json_str = text[json_start:json_end]
                return json.loads(json_str)

            return None

        except Exception as e:
            logger.warning(f"LLM reflection failed: {e}")
            return None

    def _rule_based_reflect(self, episode: Episode) -> Dict[str, str]:
        """
        Generate reflection using rule-based analysis.

        Used as fallback when LLM is unavailable.
        """
        outcome = episode.outcome
        if not outcome:
            return {"what_worked": "", "what_failed": "", "lesson": "No outcome data"}

        what_worked = []
        what_failed = []

        # Analyze based on outcome
        if outcome.success:
            what_worked.append("Trade was profitable")

            if outcome.pnl_percent > 5:
                what_worked.append("strong move captured")

            if outcome.exit_reason == "take_profit":
                what_worked.append("TP hit as planned")
        else:
            what_failed.append("Trade was unprofitable")

            if outcome.exit_reason == "stop_loss":
                what_failed.append("SL triggered")

            if outcome.max_drawdown > abs(outcome.pnl) * 2:
                what_failed.append("position sized too large")

        # Analyze timing
        if outcome.hold_duration_seconds < 60:
            what_failed.append("exited too quickly")
        elif outcome.hold_duration_seconds > 3600 and not outcome.success:
            what_failed.append("held losing position too long")

        # Analyze max profit vs final pnl
        if outcome.max_profit > 0 and outcome.pnl < outcome.max_profit * 0.5:
            what_failed.append("gave back too much profit")

        # Generate lesson
        if outcome.success:
            if episode.signal_type == "LONG":
                lesson = f"Buying {episode.symbol} at support can work in this regime"
            else:
                lesson = f"Shorting {episode.symbol} at resistance can work in this regime"
        else:
            if outcome.exit_reason == "stop_loss":
                lesson = f"Be cautious with {episode.symbol} - stop was hit, consider wider stops or smaller size"
            else:
                lesson = f"Review entry timing for {episode.symbol} in similar conditions"

        return {
            "what_worked": "; ".join(what_worked) if what_worked else "N/A",
            "what_failed": "; ".join(what_failed) if what_failed else "N/A",
            "lesson": lesson,
        }

    async def batch_reflect(self, episodes: list) -> int:
        """
        Reflect on multiple episodes.

        Returns number of successful reflections.
        """
        count = 0
        for episode in episodes:
            if episode.is_complete():
                continue  # Already reflected

            if episode.outcome:
                reflection = await self.reflect(episode)
                episode.what_worked = reflection["what_worked"]
                episode.what_failed = reflection["what_failed"]
                episode.lesson = reflection["lesson"]
                count += 1

        return count

    def get_stats(self) -> Dict[str, Any]:
        """Get reflection statistics."""
        return {
            "total_reflections": self._reflection_count,
        }


# Global instance
_agent: Optional[ReflectionAgent] = None


def get_reflection_agent() -> ReflectionAgent:
    """Get global ReflectionAgent instance."""
    global _agent
    if _agent is None:
        _agent = ReflectionAgent()
    return _agent


async def reflect_on_episode(episode: Episode) -> Dict[str, str]:
    """Convenience function to reflect on an episode."""
    agent = get_reflection_agent()
    return await agent.reflect(episode)
