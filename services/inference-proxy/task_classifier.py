"""
Task classifier for inference proxy auto-routing.

Keyword + pattern matching to select the best model tier when model="auto".
No LLM call — must complete in <1ms. Called per-request before routing.

Routing map (benchmark-calibrated 2026-04-14, RTX 5070 Ti):
  FACTUAL   → fast      (nemotron-mini:4b)  232 tok/s — quick factual lookups, yes/no
  CODE      → code      (gemma4:latest)     154 tok/s — code gen, review, debugging (via Ollama)
  REASONING → reason    (deepseek-r1:14b)    80 tok/s — structured R1 chain-of-thought
  RESEARCH  → kimi-cloud                          —   — synthesis, market analysis, reports
  CREATIVE  → balanced  (hermes3:8b)        118 tok/s — writing, brainstorming
  CHAT      → balanced  (hermes3:8b)        118 tok/s — conversation, general Q&A (default)
"""

from __future__ import annotations

import logging
import re
from enum import StrEnum
from typing import NamedTuple

log = logging.getLogger(__name__)

__all__ = ["TaskCategory", "ClassifierResult", "classify_messages", "classify_text"]


class TaskCategory(StrEnum):
    FACTUAL = "factual"
    CODE = "code"
    REASONING = "reasoning"
    RESEARCH = "research"
    CREATIVE = "creative"
    CHAT = "chat"


class ClassifierResult(NamedTuple):
    category: TaskCategory
    model: str  # model alias to pass through MODEL_TIERS
    confidence: float  # 0.0–1.0


# ─── Pattern Banks ────────────────────────────────────────────────────────────

_CODE_PATTERNS = re.compile(
    r"""
    \b(?:
        write\s+(?:a\s+)?(?:function|class|script|code|program|test|module|method)|
        implement|refactor|debug|fix\s+(?:the\s+)?(?:bug|error|code)|
        code\s+review|review\s+(?:this\s+)?code|
        add\s+(?:a\s+)?(?:function|method|endpoint|route|test)|
        create\s+(?:a\s+)?(?:class|function|module|api|endpoint|component)|
        python|typescript|javascript|rust|golang|java\b|
        def\s+\w+\s*\(|class\s+\w+|import\s+\w+|from\s+\w+\s+import|
        #!/|npm\s+\w+|pip\s+install|cargo\s+\w+|
        sql\s+query|database\s+schema|migration|orm\b|
        regex|regular\s+expression|grep\s+pattern|
        dockerfile|yaml\s+config|json\s+schema
    )\b
    """,
    re.VERBOSE | re.IGNORECASE,
)

_CODE_SIGNALS = re.compile(
    r"```|`[^`]+`|\bfunction\s*\(|\bdef\s+\w+|\bclass\s+\w+\b|\bimport\s+\w|\bconst\s+\w|\blet\s+\w|\bvar\s+\w",
    re.IGNORECASE,
)

_REASONING_PATTERNS = re.compile(
    r"""
    \b(?:
        (?:step[- ]by[- ]step|explain\s+(?:how|why|the\s+reasoning))|
        analyze|analyse|evaluate|assess|compare\s+(?:and\s+)?contrast|
        pros\s+and\s+cons|trade[- ]offs?|decision\s+(?:matrix|framework)|
        (?:solve|work\s+through)\s+(?:this\s+)?(?:problem|equation|puzzle)|
        prove\s+that|disprove|logical\s+(?:argument|fallacy)|
        calculate\s+(?:the\s+)?(?:probability|expected|optimal)|
        optimize\s+(?:for|the)|gradient|derivative|integral\b|
        (?:should|would)\s+i\s+(?:invest|trade|buy|sell|choose|pick)\b|
        risk[-\s]reward|sharpe\b|sortino\b|calmar\b|drawdown\b|
        market\s+(?:structure|regime|cycle)|
        hypothesis|theorem|proof\b|mathematical
    )\b
    """,
    re.VERBOSE | re.IGNORECASE,
)

_RESEARCH_PATTERNS = re.compile(
    r"""
    \b(?:
        research|deep\s+dive|comprehensive\s+(?:analysis|overview|report)|
        summarize\s+(?:the\s+)?(?:key|main|latest|recent)|
        market\s+(?:report|analysis|trends?|overview|landscape)|
        competitive\s+(?:analysis|landscape|intelligence)|
        industry\s+(?:overview|trends?|analysis|report)|
        compare\s+(?:all|different|multiple|various)\s+\w+\s+(?:tools?|frameworks?|options?|alternatives?)|
        what\s+(?:are|is)\s+(?:the\s+)?(?:latest|current|recent|best|top|major)\s+\w+\s+(?:trends?|news|developments?|advances?)|
        brief(?:ing)?(?:\s+on|\s+about|\s+for)|
        intelligence\s+on|
        write\s+(?:a\s+)?(?:report|analysis|summary|overview|briefing)
    )\b
    """,
    re.VERBOSE | re.IGNORECASE,
)

_FACTUAL_PATTERNS = re.compile(
    r"""
    \b(?:
        what\s+(?:is|are|was|were)\s+(?:the\s+)?(?:capital|population|year|date|name|number|version|current\s+price)\b|
        who\s+(?:is|was|are|were)\s|
        when\s+(?:was|did|is)\s|
        where\s+is\s|
        how\s+(?:many|much|long|far|old|tall|big|deep|wide)\s|
        (?:yes|no)\s+or\s+(?:no|yes)\b|
        (?:true|false)\s*\?|
        definition\s+of|define\s+\w+|
        convert\s+\d|what\s+time\s+is|current\s+date|today(?:'s)?\s+date|
        \btldr\b|\bsummarize\s+in\s+(?:one|1|two|2|three|3)\s+(?:sentence|word|line)|
        (?:quick|brief|short)\s+(?:answer|summary|overview|explanation)\s+of\b|
        is\s+\w+\s+(?:a|an|the)\s+\w+\b
    )\b
    """,
    re.VERBOSE | re.IGNORECASE,
)

_CREATIVE_PATTERNS = re.compile(
    r"""
    \b(?:
        write\s+(?:a\s+)?(?:poem|story|essay|blog\s+post|email|letter|draft|creative|narrative|ad|copy|pitch)|
        brainstorm|generate\s+(?:ideas?|options?|alternatives?|names?|titles?)|
        creative\s+(?:writing|ideas?)|
        suggest\s+(?:some|a\s+few|ideas?\s+for)|
        come\s+up\s+with|think\s+of\s+(?:some|a\s+few|ways|ideas)|
        role[- ]play|act\s+as|pretend|imagine\s+(?:you\s+are|that)|
        marketing\s+copy|ad\s+campaign|outreach\s+(?:email|message|template)|
        catchy\s+(?:headline|title|tagline|slogan)
    )\b
    """,
    re.VERBOSE | re.IGNORECASE,
)


# ─── Scorer ───────────────────────────────────────────────────────────────────


def _score_text(text: str) -> dict[TaskCategory, float]:
    """Return unnormalized match scores for each category."""
    scores: dict[TaskCategory, float] = {cat: 0.0 for cat in TaskCategory}

    # Code: weight by signal count (code snippets are strong evidence)
    code_matches = len(_CODE_PATTERNS.findall(text))
    code_signals = len(_CODE_SIGNALS.findall(text))
    scores[TaskCategory.CODE] = code_matches * 2.0 + code_signals * 1.5

    # Reasoning: multi-step or analytical language
    scores[TaskCategory.REASONING] = len(_REASONING_PATTERNS.findall(text)) * 2.0

    # Research: synthesis / report language
    scores[TaskCategory.RESEARCH] = len(_RESEARCH_PATTERNS.findall(text)) * 2.5

    # Factual: short direct questions
    fact_score = len(_FACTUAL_PATTERNS.findall(text)) * 1.5
    # Penalize if text is long (long queries are rarely factual)
    if len(text) > 200:
        fact_score *= 0.5
    scores[TaskCategory.FACTUAL] = fact_score

    # Creative: writing / brainstorming language
    scores[TaskCategory.CREATIVE] = len(_CREATIVE_PATTERNS.findall(text)) * 2.0

    return scores


def classify_text(text: str) -> ClassifierResult:
    """Classify a text string (single message content) into a TaskCategory."""
    scores = _score_text(text)
    best_cat = max(scores, key=lambda c: scores[c])
    best_score = scores[best_cat]

    if best_score < 1.0:
        # No strong signal — default to chat
        return ClassifierResult(
            category=TaskCategory.CHAT,
            model="balanced",
            confidence=1.0,
        )

    # Confidence: ratio of best score to second-best
    sorted_scores = sorted(scores.values(), reverse=True)
    second = sorted_scores[1] if len(sorted_scores) > 1 else 0.0
    confidence = min(1.0, (best_score - second) / max(best_score, 1.0) + 0.5)

    model = _CATEGORY_TO_MODEL[best_cat]
    return ClassifierResult(category=best_cat, model=model, confidence=confidence)


def classify_messages(messages: list[dict]) -> ClassifierResult:
    """
    Classify a list of OpenAI-format messages.
    Uses the last user message; falls back to full concatenation.
    """
    if not messages:
        log.debug("classify_messages: empty message list — defaulting to balanced")
        return ClassifierResult(TaskCategory.CHAT, "balanced", 1.0)

    # Prefer the last user message for intent detection
    user_msgs = [m for m in messages if m.get("role") == "user"]
    primary = user_msgs[-1].get("content", "") if user_msgs else messages[-1].get("content", "")

    if not primary or not primary.strip():
        log.warning("classify_messages: empty/whitespace message content — defaulting to balanced")
        return ClassifierResult(TaskCategory.CHAT, "balanced", 1.0)

    # If primary message is very short, also look at system message for context
    if len(primary) < 50 and len(messages) > 1:
        system_msgs = [m for m in messages if m.get("role") == "system"]
        if system_msgs:
            context = system_msgs[0].get("content", "")
            primary = context + " " + primary

    return classify_text(primary)


# ─── Category → Model Mapping ─────────────────────────────────────────────────
# Maps to MODEL_TIERS aliases (not raw model names).

_CATEGORY_TO_MODEL: dict[TaskCategory, str] = {
    TaskCategory.FACTUAL: "fast",  # nemotron-mini:4b — instant
    TaskCategory.CODE: "code",  # gemma4:latest (supersedes qwen2.5-coder:14b)
    TaskCategory.REASONING: "reason",  # deepseek-r1:14b
    TaskCategory.RESEARCH: "kimi-cloud",  # Kimi Cloud (sensitivity-gated by proxy)
    TaskCategory.CREATIVE: "balanced",  # hermes3:8b
    TaskCategory.CHAT: "balanced",  # hermes3:8b (default)
}


# ─── CLI ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python3 task_classifier.py '<text>'")
        print()
        print("Examples:")
        test_cases = [
            "What is the capital of Texas?",
            "Write a Python function to sort a list of dicts by key",
            "Analyze whether the Bitcoin price will continue its uptrend given the current RSI and MACD divergence",
            "Research the residential WiFi installation market in Houston",
            "Write an outreach email for a luxury home networking company",
            "How are you today?",
        ]
        for t in test_cases:
            r = classify_text(t)
            print(
                f"  [{r.category.value:10s}] model={r.model:15s} conf={r.confidence:.2f}  {t[:60]}"
            )
        sys.exit(0)

    query = " ".join(sys.argv[1:])
    result = classify_text(query)
    print(f"Category:   {result.category.value}")
    print(f"Model:      {result.model}")
    print(f"Confidence: {result.confidence:.2f}")
