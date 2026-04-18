
import json
import logging
import re
from enum import StrEnum
from typing import Any

# We will use the existing GeminiGuard or a lightweight client
from src.ai.gemini_guard import GeminiGuard

logger = logging.getLogger(__name__)


class IntentType(StrEnum):
    STATUS_REPORT = "status_report"
    CONTROL_TRADING = "control_trading"
    MEDIA_PUBLISH = "media_publish"
    MEDIA_STATUS = "media_status"
    OPERATIONS = "operations"
    AGENT_QUESTION = "agent_question"
    GENERAL_CHAT = "general_chat"
    UNKNOWN = "unknown"


# ── Fast local patterns for common conversational phrases ──────────────
# These bypass the LLM entirely for ultra-low latency (<1ms).
_STATUS_PATTERNS = re.compile(
    r"^(how('?s| is| are)?\s*(it|we|things|everything|the (system|engine|bot))?\s*(going|doing|looking)?|"
    r"sitrep|status|report|give me (a |an |the )?update|what'?s (the )?(status|situation|vibe)|"
    r"how'?s (the )?(p[&n]l|portfolio|trading|book)|are we (making|losing) money|"
    r"quick (update|check|status)|morning (update|report|check)|evening (update|report)|"
    r"daily (brief|briefing|update|summary)|where do we stand|catch me up)[\s?!.]*$",
    re.IGNORECASE,
)
_KILL_PATTERNS = re.compile(
    r"^(kill|halt|stop (everything|all|trading)|emergency stop|shut (it )?down|panic)[\s!.]*$",
    re.IGNORECASE,
)
_RESUME_PATTERNS = re.compile(
    r"^(resume|restart|start (trading|back)|bring (it )?back|go live|turn (it )?on)[\s!.]*$",
    re.IGNORECASE,
)
_HEALTH_PATTERNS = re.compile(
    r"^(health( check)?|check health|run (a )?(health|diagnostic)|diagnostics|"
    r"is everything (ok|okay|working|healthy)|anything broken|any (issues|errors|problems))[\s?!.]*$",
    re.IGNORECASE,
)
_PROPOSALS_PATTERNS = re.compile(
    r"^(show (me )?(the )?(proposals?|pending (code|changes|diffs?))|"
    r"pending (proposals?|code|changes)|any (proposals?|pending|changes)|what needs (my )?(approval|review)|"
    r"what'?s (pending|waiting)|anything (to|for me to) (approve|review))[\s?!.]*$",
    re.IGNORECASE,
)
_AGENTS_PATTERNS = re.compile(
    r"^(agent(s| status| stats)?|who'?s (working|running|active)|dispatch (status|stats)|"
    r"how are (the )?(agents?|bots?)|what are (the )?(agents?|bots?) (doing|up to))[\s?!.]*$",
    re.IGNORECASE,
)


class ChatIntentEngine:
    """Conversational intent classifier for Sapphire.

    Uses a two-tier approach:
    1. **Local regex patterns** for common phrases (instant, no LLM cost).
    2. **Gemini Flash LLM call** for ambiguous or complex messages.

    The engine powers the personal assistant experience — the owner
    talks naturally on Telegram and the system figures out what to do.
    """

    def __init__(self, ai_guard: GeminiGuard):
        self.ai = ai_guard
        self._system_prompt = _SYSTEM_PROMPT

    async def analyze(self, text: str) -> dict[str, Any]:
        """Classify a natural language message into a structured intent.

        Returns a dict with 'intent' and 'parameters' keys.
        """
        # Tier 1: Fast local pattern matching (< 1ms, no LLM call)
        local = self._fast_classify(text)
        if local:
            return local

        # Tier 2: LLM classification via Gemini Flash
        try:
            prompt = f"{self._system_prompt}\n\nUser: {text}\nOutput:"
            raw_content = await self.ai.classify_intent(prompt)
            if not raw_content:
                raise ValueError("Empty response from AI")

            # Clean markdown code blocks if present
            cleaned = raw_content.strip()
            if cleaned.startswith("```json"):
                cleaned = cleaned[7:]
            if cleaned.startswith("```"):
                cleaned = cleaned[3:]
            if cleaned.endswith("```"):
                cleaned = cleaned[:-3]

            result = json.loads(cleaned.strip())
            # Validate intent field
            intent = result.get("intent", "")
            valid_intents = {e.value for e in IntentType}
            if intent not in valid_intents:
                result["intent"] = "general_chat"
            return result

        except Exception as e:
            logger.error(f"Intent classification failed: {e}")
            return {
                "intent": "general_chat",
                "parameters": {
                    "reply": "I'm not sure I caught that — could you say that differently?"
                },
            }

    # ── Fast local classifier ─────────────────────────────────────────

    def _fast_classify(self, text: str) -> dict[str, Any] | None:
        """Match common conversational phrases without hitting the LLM."""
        cleaned = text.strip()
        if not cleaned:
            return None

        if _STATUS_PATTERNS.match(cleaned):
            return {"intent": "status_report", "parameters": {"type": "full"}}

        if _KILL_PATTERNS.match(cleaned):
            return {
                "intent": "control_trading",
                "parameters": {"action": "PAUSE", "target": "ALL"},
            }

        if _RESUME_PATTERNS.match(cleaned):
            return {
                "intent": "control_trading",
                "parameters": {"action": "RESUME", "target": "ALL"},
            }

        if _HEALTH_PATTERNS.match(cleaned):
            return {
                "intent": "operations",
                "parameters": {"action": "HEALTH"},
            }

        if _PROPOSALS_PATTERNS.match(cleaned):
            return {
                "intent": "operations",
                "parameters": {"action": "PROPOSALS"},
            }

        if _AGENTS_PATTERNS.match(cleaned):
            return {
                "intent": "operations",
                "parameters": {"action": "AGENT_STATUS"},
            }

        # Pause/resume with venue name
        pause_match = re.match(
            r"^pause\s+(aster|lighter|all)\s*$", cleaned, re.IGNORECASE
        )
        if pause_match:
            return {
                "intent": "control_trading",
                "parameters": {
                    "action": "PAUSE",
                    "target": pause_match.group(1).upper(),
                },
            }

        resume_match = re.match(
            r"^resume\s+(aster|lighter|all)\s*$", cleaned, re.IGNORECASE
        )
        if resume_match:
            return {
                "intent": "control_trading",
                "parameters": {
                    "action": "RESUME",
                    "target": resume_match.group(1).upper(),
                },
            }

        return None


# ── LLM System Prompt ──────────────────────────────────────────────────

_SYSTEM_PROMPT = """You are Sapphire's intent classifier. The owner talks to you on Telegram like a personal assistant — casual, short, sometimes just a few words. Map their message to structured JSON.

### INTENTS
Output JSON: {"intent": "<type>", "parameters": {…}}

**status_report** — Owner wants to know how things are going.
  Examples: "how are we doing?", "give me an update", "morning report", "P&L?", "quick check"
  Params: {"type": "full" | "short"}

**control_trading** — Owner wants to pause, resume, or adjust trading.
  Examples: "pause aster", "stop everything", "resume trading", "set allocation to 30%"
  Params: {"action": "PAUSE"|"RESUME"|"SET_ALLOCATION", "target": "ASTER"|"LIGHTER"|"ALL", "value": float?}

**media_publish** — Owner wants content drafted or posted.
  Examples: "write a tweet about BTC", "post to substack about our strategy"
  Params: {"topic": str, "channels": ["twitter","substack","linkedin"]}

**media_status** — Owner asks about media/content queue.
  Examples: "any posts pending?", "media status", "check the queue"
  Params: {}

**operations** — Owner wants system operations performed.
  Examples: "health check", "show proposals", "sync roadmap", "ci status", "agent status", "openclaw status"
  Params: {"action": "PROPOSALS"|"DIFF"|"APPROVE_PROPOSAL"|"REJECT_PROPOSAL"|"HEALTH"|"ROADMAP_SYNC"|"CI_STATUS"|"OPENCLAW_STATUS"|"OPENCLAW_SMOKE"|"AGENT_STATUS", "target": str?}

**agent_question** — Owner asks a question the agents should think about and answer.
  Examples: "what do you think about adding SOL?", "should we increase exposure?", "analyze the BTC trend", "what's your take on the market?", "any trading opportunities?", "what would you improve next?"
  Params: {"question": str, "agent": "SAPPHIRE"|"OBSIDIAN"|"EMERALD"|"auto"}
  Use "auto" when no specific agent is implied. Route infrastructure questions to OBSIDIAN, strategy/improvement to EMERALD, trading/market to SAPPHIRE.

**general_chat** — Greetings, praise, small talk, or anything that doesn't fit above.
  Examples: "good morning", "nice work", "thanks", "who are you?"
  Params: {"reply": str}
  Draft a short, warm, in-character reply as Sapphire (the trading agent). Be personable — Sapphire is a competent colleague, not a robot. One or two sentences max.

### CLASSIFICATION RULES
- Prefer the MOST SPECIFIC intent. "how's trading?" → status_report, not general_chat.
- If the message is a question about markets, strategy, or system improvements → agent_question.
- If it's a greeting followed by a request, classify by the request part.
- When ambiguous between agent_question and general_chat, prefer agent_question — the owner wants substantive answers.

### EXAMPLES
User: "hey how are we doing"
Output: {"intent": "status_report", "parameters": {"type": "full"}}

User: "kill"
Output: {"intent": "control_trading", "parameters": {"action": "PAUSE", "target": "ALL"}}

User: "any proposals I need to look at?"
Output: {"intent": "operations", "parameters": {"action": "PROPOSALS"}}

User: "what do you think about the ETH setup right now?"
Output: {"intent": "agent_question", "parameters": {"question": "what do you think about the ETH setup right now?", "agent": "SAPPHIRE"}}

User: "obsidian, how's the infrastructure looking?"
Output: {"intent": "agent_question", "parameters": {"question": "how's the infrastructure looking?", "agent": "OBSIDIAN"}}

User: "nice work team"
Output: {"intent": "general_chat", "parameters": {"reply": "Appreciate that! The team's been running smooth — I'll keep you posted if anything comes up."}}

User: "approve proposal abc123"
Output: {"intent": "operations", "parameters": {"action": "APPROVE_PROPOSAL", "target": "abc123"}}

User: "what should we work on next?"
Output: {"intent": "agent_question", "parameters": {"question": "what should we work on next?", "agent": "EMERALD"}}
"""
