"""Pure scoring harness for Vertex/Gemini OODA outputs.

This module is deliberately free of I/O, environment access, and network
calls. It exposes:

* The canonical eval prompt sets used by ``vertex_eval`` (immutable).
* A deterministic OODA mock generator (used as a no-spend baseline).
* A small reproducible rubric (``score_response``) that returns
  per-prompt scores in [0, 1] for ``structural_validity``,
  ``actionability``, and ``citation_density``, plus passthrough
  ``latency_ms`` and ``tokens_used`` integers and a ``caps_breach``
  boolean.
* An aggregator (``aggregate_scores``) that computes mean/min/max for
  the rubric metrics across a prompt set.

The rubric is intentionally NOT an LLM judge. Reproducibility is the
whole point — two operators running the same harness on the same
outputs must get identical scores. That keeps the auditor honest when
they ask "is the Google AI / Vertex spend buying us better reasoning?".

The caps in ``enforce_caps`` mirror those in
``plugins/claw-sapphire/tools/internal/gemini_ooda.py``; the eval
harness never exceeds the live tool's hard limits.
"""

from __future__ import annotations

import json
import re
import statistics
from dataclasses import asdict, dataclass, field
from typing import Any

# Caps mirror plugins/claw-sapphire/tools/internal/gemini_ooda.py.
MAX_OUTPUT_TOKENS_HARD = 4096
MAX_INPUT_CHARS_HARD = 12_000
MAX_CALLS_PER_HOUR = 8
MAX_TOKENS_PER_MONTH = 500_000
EVAL_PROMPTS_PER_RUN_HARD = 12

OODA_KEYS: tuple[str, ...] = ("observe", "orient", "decide", "act")

# Markdown link regex used by citation_density.
_MD_LINK = re.compile(r"\[[^\]]+\]\([^)]+\)")
# Numeric "facts" — bare numbers, percentages, currency, durations.
_NUMERIC_FACT = re.compile(
    r"\b\d{1,4}(?:\.\d+)?\s?(?:%|bps|usd|eth|btc|sol|tps|x|h|d|m|w)?\b",
    re.IGNORECASE,
)
# Heuristic sentence splitter used to count claims.
_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+|\n+")
_VERB_LEADERS = (
    # Action verbs an OODA "act" step is expected to start with.
    "add",
    "alert",
    "audit",
    "block",
    "build",
    "check",
    "confirm",
    "deploy",
    "disable",
    "draft",
    "enable",
    "escalate",
    "evaluate",
    "execute",
    "expand",
    "fetch",
    "file",
    "flag",
    "generate",
    "halt",
    "hold",
    "increase",
    "inspect",
    "investigate",
    "issue",
    "kick",
    "land",
    "launch",
    "lower",
    "merge",
    "monitor",
    "notify",
    "open",
    "pause",
    "ping",
    "post",
    "publish",
    "queue",
    "raise",
    "reduce",
    "replay",
    "request",
    "resume",
    "review",
    "revoke",
    "roll",
    "route",
    "run",
    "scan",
    "schedule",
    "send",
    "set",
    "ship",
    "snapshot",
    "stage",
    "start",
    "stop",
    "submit",
    "sync",
    "tag",
    "test",
    "trigger",
    "unblock",
    "update",
    "verify",
    "watch",
    "write",
)


@dataclass(frozen=True)
class PromptCase:
    """One eval prompt — immutable, JSON-serialisable."""

    set_name: str
    prompt_id: str
    topic: str
    context: str
    expected_focus: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "set_name": self.set_name,
            "prompt_id": self.prompt_id,
            "topic": self.topic,
            "context": self.context,
            "expected_focus": list(self.expected_focus),
        }


@dataclass(frozen=True)
class RubricScores:
    """Per-prompt rubric output."""

    structural_validity: float
    actionability: float
    citation_density: float
    latency_ms: int
    tokens_used: int
    caps_breach: bool
    notes: tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, Any]:
        out = asdict(self)
        out["notes"] = list(self.notes)
        return out


@dataclass(frozen=True)
class AggregateScores:
    """Aggregate rubric output across a prompt set."""

    n: int
    structural_validity_mean: float
    actionability_mean: float
    citation_density_mean: float
    latency_ms_mean: float
    tokens_used_total: int
    caps_breach_count: int
    structural_validity_min: float
    actionability_min: float
    citation_density_min: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# ---------------------------------------------------------------------------
# Bundled prompt sets (immutable constants).
# ---------------------------------------------------------------------------


def _case(set_name: str, idx: int, topic: str, context: str, focus: tuple[str, ...]) -> PromptCase:
    return PromptCase(
        set_name=set_name,
        prompt_id=f"{set_name}-{idx:02d}",
        topic=topic,
        context=context,
        expected_focus=focus,
    )


_CRYPTO = "crypto-regime-shift"
_VOTE = "vote-monitor-context"
_THREAT = "threat-intel-summary"
_SOVEREIGN = "sovereign-thesis-synthesis"


EVAL_PROMPT_SETS: dict[str, tuple[PromptCase, ...]] = {
    _CRYPTO: (
        _case(
            _CRYPTO,
            1,
            "BTC funding skew + OI building into a 4h breakout",
            (
                "BTC spot up 3.2% over 24h. Open interest up 4.1% on perpetuals. "
                "Funding rate flat near 0.005% on Binance, slightly positive elsewhere. "
                "Spot volume normal, perp volume +18%. No major macro print today."
            ),
            ("regime", "funding", "open_interest"),
        ),
        _case(
            _CRYPTO,
            2,
            "ETH lagging BTC into a sector rotation",
            (
                "ETH/BTC trending down for 12 days. Stablecoin supply rising 0.8% "
                "weekly. Solana memecoin volume sustained. Ethereum L2 activity "
                "flat. Funding on ETH perps mildly negative."
            ),
            ("rotation", "ethbtc", "stablecoin"),
        ),
        _case(
            _CRYPTO,
            3,
            "SOL liquidation cascade risk read",
            (
                "SOL liquidations totalled forty-two million USD in the last 6h, "
                "mostly longs. OI down 7%. Spot funding flipped negative. Whale "
                "wallets accumulating into the dip. No exchange outage."
            ),
            ("liquidation", "whale_flow", "regime"),
        ),
    ),
    _VOTE: (
        _case(
            _VOTE,
            1,
            "Blackhole ve(3,3) bribe efficiency drift",
            (
                "Blackhole epoch closed with thirty-one thousand USD bribes paid "
                "versus forty-eight thousand USD voter value last week. Top pool "
                "shifted from USDC/AVAX to AVAX/sAVAX. veBLACK supply unchanged."
            ),
            ("bribe_efficiency", "pool_rotation"),
        ),
        _case(
            _VOTE,
            2,
            "Supernova versus Full Sail vote concentration",
            (
                "Top 3 pools on Supernova hold 71% of votes. Full Sail's top 3 "
                "hold 54%. Supernova bribes +12% week-over-week, Full Sail flat."
            ),
            ("concentration", "competition"),
        ),
    ),
    _THREAT: (
        _case(
            _THREAT,
            1,
            "CISA KEV additions matching Sapphire dependency surface",
            (
                "Three new CISA KEV adds: a Cisco IOS XE auth-bypass, a Microsoft "
                "Exchange RCE, a libxslt UAF. Sapphire deps include a libxml2 "
                "tree but not libxslt. No Cisco / Exchange in stack."
            ),
            ("kev", "dependency_surface"),
        ),
        _case(
            _THREAT,
            2,
            "Repeated CVE pattern in northbound services",
            (
                "Past 30d: 4 CVEs in our HTTP framework's body parser, 2 in our "
                "static-file handler, 1 in our reverse-proxy module. All medium "
                "severity. No exploitation evidence."
            ),
            ("pattern", "exposure_window"),
        ),
    ),
    _SOVEREIGN: (
        _case(
            _SOVEREIGN,
            1,
            "US/Asia capital reallocation read on a soft-landing surprise",
            (
                "DXY -1.3% on the week. US 10y at 3.97%. Hang Seng +5.1%. "
                "Nikkei +2.4%. Stablecoin issuance +$1.2B week. ETH/BTC down."
            ),
            ("dollar", "asia_equities", "stablecoins"),
        ),
        _case(
            _SOVEREIGN,
            2,
            "Macro allocation reference into the print",
            (
                "A reference 60/40 stock-bond mix outperforms a flat-equities "
                "alternative under soft-landing scenarios in the latest IMF WEO. "
                "Sortino-style risk-adjusted returns favor the equity tilt."
            ),
            ("allocation", "macro_reference"),
        ),
    ),
}

PROMPT_SET_NAMES: tuple[str, ...] = tuple(EVAL_PROMPT_SETS.keys())


def get_prompt_set(name: str) -> tuple[PromptCase, ...]:
    """Return the canonical prompt cases for ``name`` or empty tuple."""
    return EVAL_PROMPT_SETS.get(name, ())


# ---------------------------------------------------------------------------
# Caps and mock baseline.
# ---------------------------------------------------------------------------


def enforce_caps(
    *,
    prompt_count: int,
    max_output_tokens: int,
    input_chars: int,
) -> tuple[bool, str]:
    """Return (within_caps, reason). Reason is empty if within caps."""
    if prompt_count > EVAL_PROMPTS_PER_RUN_HARD:
        return False, (f"prompts_per_run_breach: {prompt_count} > {EVAL_PROMPTS_PER_RUN_HARD}")
    if max_output_tokens > MAX_OUTPUT_TOKENS_HARD:
        return False, (f"output_tokens_breach: {max_output_tokens} > {MAX_OUTPUT_TOKENS_HARD}")
    if input_chars > MAX_INPUT_CHARS_HARD:
        return False, f"input_chars_breach: {input_chars} > {MAX_INPUT_CHARS_HARD}"
    return True, ""


def deterministic_mock_response(case: PromptCase) -> dict[str, Any]:
    """Deterministic OODA packet generated from a prompt — no model required.

    The mock is intentionally simple: it satisfies the OODA shape and gives
    the rubric a non-trivial baseline to score against. It does NOT pretend
    to be high-quality reasoning; the scoring delta versus a live response
    is what the operator inspects.
    """
    topic = case.topic.strip()
    context = case.context.strip()
    focus = ", ".join(case.expected_focus) if case.expected_focus else "none"
    return {
        "observe": (
            f"Mock observation for '{topic}'. Context length: {len(context)} chars. "
            f"Expected focus areas: {focus}. No live model contacted; this output "
            f"serves only as the deterministic baseline for the eval rubric."
        ),
        "orient": (
            "Sapphire posture: 4-tier local mesh + capped Vertex lane. "
            f"Prompt set: {case.set_name}. Cite no fewer than two facts when "
            "live; this baseline cites zero on purpose so the delta is visible."
        ),
        "decide": (
            f"Defer external spend on '{case.prompt_id}'. Use the local mesh "
            "until a live Vertex run is auditable and the rubric agrees the "
            "delta is worth the cost."
        ),
        "act": [
            "Run the same prompt against the local mesh `balanced` tier.",
            "Check the rubric delta for structural_validity and citation_density.",
        ],
    }


# ---------------------------------------------------------------------------
# Rubric.
# ---------------------------------------------------------------------------


def _coerce_ooda(response: Any) -> dict[str, Any] | None:
    """Best-effort coerce a response into an OODA dict."""
    if isinstance(response, dict):
        return response
    if isinstance(response, str):
        cleaned = response.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.strip("`")
            cleaned = re.sub(r"^json\s*\n", "", cleaned, flags=re.IGNORECASE)
        try:
            parsed = json.loads(cleaned)
        except (TypeError, json.JSONDecodeError):
            return None
        if isinstance(parsed, dict):
            return parsed
    return None


def _structural_validity(ooda: dict[str, Any] | None) -> tuple[float, list[str]]:
    notes: list[str] = []
    if not ooda:
        return 0.0, ["non_dict_response"]
    score = 0.0
    for key in OODA_KEYS:
        if key in ooda:
            value = ooda[key]
            if key == "act":
                if isinstance(value, list) and value:
                    score += 0.25
                else:
                    notes.append("act_not_nonempty_list")
            else:
                if isinstance(value, str) and value.strip():
                    score += 0.25
                else:
                    notes.append(f"{key}_not_nonempty_string")
        else:
            notes.append(f"missing_{key}")
    return score, notes


def _split_act_steps(act: Any) -> list[str]:
    if isinstance(act, list):
        return [str(item).strip() for item in act if str(item).strip()]
    if isinstance(act, str):
        return [chunk.strip() for chunk in re.split(r"\n+|;|•", act) if chunk.strip()]
    return []


def _is_concrete_step(step: str) -> bool:
    if not step:
        return False
    parts = step.split()
    if not parts:
        return False
    head = parts[0].lower().strip(":,.-")
    if head not in _VERB_LEADERS:
        return False
    return len(parts) >= 3


def _actionability(ooda: dict[str, Any] | None) -> tuple[float, list[str]]:
    if not ooda:
        return 0.0, ["non_dict_response"]
    steps = _split_act_steps(ooda.get("act"))
    if len(steps) < 2:
        return 0.0, [f"only_{len(steps)}_steps"]
    concrete = [s for s in steps if _is_concrete_step(s)]
    if not concrete:
        return 0.0, ["no_concrete_verb_leaders"]
    # 2 concrete steps -> 0.5; 4+ -> 1.0; partial scaling between.
    raw = min(1.0, len(concrete) / 4.0)
    if raw < 0.5 and len(concrete) >= 2:
        raw = 0.5
    return raw, []


def _count_claims(text: str) -> int:
    if not text:
        return 0
    sentences = [s.strip() for s in _SENTENCE_SPLIT.split(text) if s.strip()]
    return len(sentences)


def _count_citations(text: str) -> int:
    if not text:
        return 0
    md_links = len(_MD_LINK.findall(text))
    facts = len(_NUMERIC_FACT.findall(text))
    return md_links + facts


def _citation_density(ooda: dict[str, Any] | None) -> tuple[float, list[str]]:
    if not ooda:
        return 0.0, ["non_dict_response"]
    blob_parts: list[str] = []
    for key in ("observe", "orient", "decide"):
        value = ooda.get(key)
        if isinstance(value, str):
            blob_parts.append(value)
    act = ooda.get("act")
    if isinstance(act, list):
        blob_parts.extend(str(item) for item in act)
    elif isinstance(act, str):
        blob_parts.append(act)
    blob = "\n".join(blob_parts)
    claims = _count_claims(blob)
    if claims == 0:
        return 0.0, ["no_claims_detected"]
    citations = _count_citations(blob)
    raw = min(1.0, citations / max(1, claims))
    return raw, []


def score_response(
    response: Any,
    *,
    case: PromptCase,
    latency_ms: int = 0,
    tokens_used: int = 0,
    max_output_tokens: int = 0,
    input_chars: int | None = None,
) -> RubricScores:
    """Score a single response against the deterministic rubric.

    Args:
        response: The OODA dict (or a JSON string we'll coerce) from the
            generator. Anything else scores zero on structural_validity.
        case: The prompt case the response is for. Used to compute the
            input character count for caps-breach detection.
        latency_ms: Raw observed latency, passed through unchanged.
        tokens_used: Raw observed token count, passed through unchanged.
        max_output_tokens: The configured per-call max output tokens.
        input_chars: Override for the input character count. Defaults to
            ``len(case.topic) + len(case.context)``.

    Returns:
        RubricScores with three [0, 1] floats plus passthrough integers
        and a ``caps_breach`` boolean.
    """
    ooda = _coerce_ooda(response)
    structural, struct_notes = _structural_validity(ooda)
    actionability, action_notes = _actionability(ooda)
    citation, cite_notes = _citation_density(ooda)
    chars = input_chars if input_chars is not None else len(case.topic) + len(case.context)
    within, _reason = enforce_caps(
        prompt_count=1,
        max_output_tokens=max_output_tokens or 0,
        input_chars=chars,
    )
    breach = not within
    notes = tuple(struct_notes + action_notes + cite_notes)
    return RubricScores(
        structural_validity=round(structural, 4),
        actionability=round(actionability, 4),
        citation_density=round(citation, 4),
        latency_ms=int(max(0, latency_ms)),
        tokens_used=int(max(0, tokens_used)),
        caps_breach=bool(breach),
        notes=notes,
    )


def aggregate_scores(scores: list[RubricScores]) -> AggregateScores:
    """Aggregate per-prompt scores into the harness summary."""
    if not scores:
        return AggregateScores(
            n=0,
            structural_validity_mean=0.0,
            actionability_mean=0.0,
            citation_density_mean=0.0,
            latency_ms_mean=0.0,
            tokens_used_total=0,
            caps_breach_count=0,
            structural_validity_min=0.0,
            actionability_min=0.0,
            citation_density_min=0.0,
        )
    structurals = [s.structural_validity for s in scores]
    actionables = [s.actionability for s in scores]
    citations = [s.citation_density for s in scores]
    latencies = [s.latency_ms for s in scores]
    return AggregateScores(
        n=len(scores),
        structural_validity_mean=round(statistics.fmean(structurals), 4),
        actionability_mean=round(statistics.fmean(actionables), 4),
        citation_density_mean=round(statistics.fmean(citations), 4),
        latency_ms_mean=round(statistics.fmean(latencies), 2),
        tokens_used_total=sum(s.tokens_used for s in scores),
        caps_breach_count=sum(1 for s in scores if s.caps_breach),
        structural_validity_min=round(min(structurals), 4),
        actionability_min=round(min(actionables), 4),
        citation_density_min=round(min(citations), 4),
    )


__all__ = [
    "EVAL_PROMPTS_PER_RUN_HARD",
    "EVAL_PROMPT_SETS",
    "MAX_CALLS_PER_HOUR",
    "MAX_INPUT_CHARS_HARD",
    "MAX_OUTPUT_TOKENS_HARD",
    "MAX_TOKENS_PER_MONTH",
    "OODA_KEYS",
    "PROMPT_SET_NAMES",
    "AggregateScores",
    "PromptCase",
    "RubricScores",
    "aggregate_scores",
    "deterministic_mock_response",
    "enforce_caps",
    "get_prompt_set",
    "score_response",
]
