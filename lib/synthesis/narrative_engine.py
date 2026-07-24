"""Narrative thesis generation on top of Sapphire correlated signals.

The engine is deterministic and offline by default. Live Gemini synthesis is a
bounded complement, not the normal path: it requires an explicit env gate, a key
loaded without logging, a sensitivity pass, a cache/rate-limit pass, and the
same rubric used by the daemon before anything is publishable.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import sys
import time
from collections.abc import Mapping
from dataclasses import asdict, dataclass, is_dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from lib.core.provenance import sha256_canonical, stamp
from lib.synthesis.prompts import PROMPT_VERSION, build_user_prompt
from lib.synthesis.rubric import (
    IMPLIED_POSITIONS,
    MIN_RUBRIC_SCORE_TO_PUBLISH,
    score_narrative,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
PLUGIN_LIB = REPO_ROOT / "plugins" / "claw-sapphire" / "lib"
if PLUGIN_LIB.exists() and str(PLUGIN_LIB) not in sys.path:
    sys.path.insert(1, str(PLUGIN_LIB))

try:  # pragma: no cover - fallback only matters if plugin lib is unavailable.
    from sensitivity_classifier import is_sensitive
except Exception:  # noqa: BLE001
    is_sensitive = None  # type: ignore[assignment]

VERSION = "0.1.0"
GENERATOR = "lib.synthesis.narrative_engine"
DEFAULT_MODEL = "gemini-2.5-flash"
KNOWN_MODELS: dict[str, dict[str, Any]] = {
    "gemini-2.5-flash": {
        "context_window": 1_000_000,
        "tier": "flash",
        "notes": "Default for bounded narrative thesis synthesis.",
    },
    "gemini-2.5-pro": {
        "context_window": 2_000_000,
        "tier": "pro",
        "notes": "Reserve for long-form hard reasoning; cost is materially higher.",
    },
    "gemini-2.0-flash": {
        "context_window": 1_000_000,
        "tier": "flash",
        "notes": "Fallback flash model.",
    },
}

MAX_OUTPUT_TOKENS_HARD = 6144
MAX_INPUT_CHARS_HARD = 18_000
MAX_CALLS_PER_HOUR = 6
MAX_TOKENS_PER_MONTH = 750_000

CACHE_DIR = Path.home() / ".cache" / "sapphire" / "narrative_synthesis"
COUNTER_PATH = CACHE_DIR / "counters.json"
SECRETS_FILE = Path.home() / ".sapphire" / "secrets.env"

ImpliedPosition = Literal[
    "long_strong",
    "long_mild",
    "neutral",
    "short_mild",
    "short_strong",
    "no_position",
]

_SENSITIVE_FALLBACK = re.compile(
    r"(api[_-]?key|secret|password|private[_-]?key|authorization:|bearer\s+[a-z0-9._-]+|"
    r"\b\d{3}-\d{2}-\d{4}\b)",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class NarrativeThesis:
    """Structured narrative output for one correlated signal."""

    thesis_one_paragraph: str
    evidence_bullets: list[str]
    counter_thesis_one_paragraph: str
    invalidators: list[str]
    next_signal_to_watch: str
    implied_position: ImpliedPosition
    confidence: float
    caveat_block: str
    provenance_envelope: dict[str, Any]
    symbol: str = ""
    timeframe: str = ""
    generated_at: str = ""
    mode_actual: str = "dry-run"
    model: str = DEFAULT_MODEL
    prompt_version: str = PROMPT_VERSION
    version: str = VERSION

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _now_utc() -> datetime:
    return datetime.now(UTC)


def _iso(now: datetime | None = None) -> str:
    return (now or _now_utc()).replace(microsecond=0).isoformat()


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, float(value)))


def _signal_dict(signal: Any) -> dict[str, Any]:
    if is_dataclass(signal):
        return asdict(signal)
    if isinstance(signal, Mapping):
        return dict(signal)
    if hasattr(signal, "to_dict"):
        return dict(signal.to_dict())
    raise TypeError("signal must be a CorrelatedSignal-like mapping")


def _as_str_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [chunk.strip() for chunk in re.split(r"\n+|;|•", value) if chunk.strip()]
    if isinstance(value, (list, tuple)):
        return [str(item).strip() for item in value if str(item).strip()]
    return [str(value).strip()] if str(value).strip() else []


def _float(signal: Mapping[str, Any], key: str, default: float = 0.0) -> float:
    try:
        return float(signal.get(key, default) or default)
    except (TypeError, ValueError):
        return default


def _int(signal: Mapping[str, Any], key: str, default: int = 0) -> int:
    try:
        return int(float(signal.get(key, default) or default))
    except (TypeError, ValueError):
        return default


def implied_position_for_edge(
    signal_or_edge: Any, *, consensus: str | None = None
) -> ImpliedPosition:
    """Map ``edge_score`` into the six narrative position buckets."""
    if isinstance(signal_or_edge, Mapping):
        signal = signal_or_edge
        edge = _float(signal, "edge_score")
        consensus = str(signal.get("consensus") or consensus or "")
        contributing = _int(signal, "contributing")
        if contributing <= 0 or consensus == "INSUFFICIENT_DATA":
            return "no_position"
    else:
        edge = float(signal_or_edge)
    if edge >= 0.65:
        return "long_strong"
    if edge > 0.2:
        return "long_mild"
    if edge <= -0.65:
        return "short_strong"
    if edge < -0.2:
        return "short_mild"
    return "neutral"


def _direction_phrase(position: str) -> str:
    return {
        "long_strong": "strong bullish",
        "long_mild": "mild bullish",
        "neutral": "balanced",
        "short_mild": "mild bearish",
        "short_strong": "strong bearish",
        "no_position": "no-position",
    }[position]


def _dominant_sources(signal: Mapping[str, Any], position: str) -> list[str]:
    if position.startswith("long"):
        sources = _as_str_list(signal.get("bull_sources")) or _as_str_list(
            signal.get("corroborated_by")
        )
    elif position.startswith("short"):
        sources = _as_str_list(signal.get("bear_sources")) or _as_str_list(
            signal.get("corroborated_by")
        )
    else:
        sources = _as_str_list(signal.get("corroborated_by"))
    return sources


def _confidence(signal: Mapping[str, Any], position: str) -> float:
    edge = abs(_float(signal, "edge_score"))
    contributing = min(1.0, _int(signal, "contributing") / 4.0)
    contradiction_penalty = 0.12 if str(signal.get("consensus") or "") == "CONTRADICT" else 0.0
    no_position_penalty = 0.18 if position == "no_position" else 0.0
    confidence = (
        0.2 + edge * 0.52 + contributing * 0.22 - contradiction_penalty - no_position_penalty
    )
    return round(_clamp(confidence), 4)


def _provenance(
    signal: Mapping[str, Any], *, mode_actual: str, model: str, now: str
) -> dict[str, Any]:
    sources = _as_str_list(signal.get("corroborated_by"))
    return {
        "generator": GENERATOR,
        "version": VERSION,
        "prompt_version": PROMPT_VERSION,
        "mode_actual": mode_actual,
        "model": model,
        "generated_at": now,
        "source_signal_hash": sha256_canonical(signal),
        "source_signal_generated_at": signal.get("generated_at"),
        "source_provenance": signal.get("provenance_envelope") or {},
        "corroborated_by": sources,
        "caps": {
            "max_output_tokens": MAX_OUTPUT_TOKENS_HARD,
            "max_input_chars": MAX_INPUT_CHARS_HARD,
            "max_calls_per_hour": MAX_CALLS_PER_HOUR,
            "max_tokens_per_month": MAX_TOKENS_PER_MONTH,
            "min_rubric_score_to_publish": MIN_RUBRIC_SCORE_TO_PUBLISH,
        },
    }


def _mock_thesis(
    signal: Mapping[str, Any],
    *,
    mode_actual: str,
    model: str,
    now: datetime | None = None,
) -> NarrativeThesis:
    generated_at = _iso(now)
    symbol = str(signal.get("symbol") or "UNKNOWN").upper()
    timeframe = str(signal.get("timeframe") or "unknown")
    edge = _float(signal, "edge_score")
    consensus = str(signal.get("consensus") or "UNKNOWN")
    position = implied_position_for_edge(signal)
    posture = _direction_phrase(position)
    contributing = _int(signal, "contributing")
    freshness = _float(signal, "freshness_seconds")
    corroborated = _as_str_list(signal.get("corroborated_by"))
    divergent = _as_str_list(signal.get("divergent_sources"))
    bull_sources = _as_str_list(signal.get("bull_sources"))
    bear_sources = _as_str_list(signal.get("bear_sources"))
    neutral_sources = _as_str_list(signal.get("neutral_sources"))
    dominant = _dominant_sources(signal, position)
    dominant_text = ", ".join(dominant[:4]) if dominant else "no dominant source cluster"
    divergent_text = ", ".join(divergent[:4]) if divergent else "no named divergent source"

    thesis = (
        f"{symbol} {timeframe} carries a {posture} research thesis because the correlated "
        f"edge_score is {edge:+.3f} with consensus {consensus} across {contributing} fresh "
        f"sources. The strongest explanation is the source cluster around {dominant_text}; "
        f"freshness is {freshness:.0f}s, so the read is recent enough for monitoring but not "
        "a live execution instruction. The implied posture is "
        f"{position.replace('_', ' ')} until a new correlated signal changes the edge by at "
        "least 0.10 or a named invalidator trips."
    )
    if position == "no_position":
        thesis = (
            f"{symbol} {timeframe} is a no-position research thesis because the correlator "
            f"reported {consensus} with edge_score {edge:+.3f} and only {contributing} "
            "contributing sources. The narrative engine can explain the absence of edge, "
            "but it should not promote a directional thesis until the source base improves."
        )

    evidence = [
        (
            f"edge_score {edge:+.3f} and raw_score {_float(signal, 'raw_score'):+.3f} "
            f"map to implied_position={position}."
        ),
        (
            f"consensus={consensus}; corroborated_by={corroborated or []}; "
            f"divergent_sources={divergent or []}."
        ),
        (
            f"bull_sources={bull_sources or []}; bear_sources={bear_sources or []}; "
            f"neutral_sources={neutral_sources or []}."
        ),
        (
            f"agreement_multiplier={_float(signal, 'agreement_multiplier', 1.0):.3f}, "
            f"contradict_factor={_float(signal, 'contradict_factor', 1.0):.3f}, "
            f"total_weight={_float(signal, 'total_weight'):.3f}."
        ),
        (
            f"freshness_seconds={freshness:.0f}; source_signal_generated_at="
            f"{signal.get('generated_at') or 'unknown'}."
        ),
    ]
    counter = (
        f"The counter-thesis is that {divergent_text} may be early, stale, or observing a "
        "different timeframe than the dominant cluster. If liquidity or macro context shifts "
        "before the next correlator tick, the numeric edge could compress without warning."
    )
    invalidators = [
        "Monitor whether the next correlator tick moves edge_score by more than 0.10 against the thesis.",
        "Watch for divergent_sources expanding to two or more independently weighted feeds.",
        "Compare freshness_seconds; invalidate if the dominant source cluster ages beyond the 24h hard limit.",
        "Confirm whether agreement_multiplier falls below 1.00 or contradict_factor tightens materially.",
    ]
    next_signal = (
        f"Watch the next {symbol} {timeframe} signal.correlated row for an edge_score delta "
        "greater than 0.10 plus any new divergent_sources."
    )
    caveat = (
        "Research-only dry-run narrative. This thesis does not place trades, size positions, "
        "send Telegram messages, or override Sapphire's paper-only safety posture."
    )
    return NarrativeThesis(
        thesis_one_paragraph=thesis,
        evidence_bullets=evidence,
        counter_thesis_one_paragraph=counter,
        invalidators=invalidators,
        next_signal_to_watch=next_signal,
        implied_position=position,
        confidence=_confidence(signal, position),
        caveat_block=caveat,
        provenance_envelope=_provenance(
            signal, mode_actual=mode_actual, model=model, now=generated_at
        ),
        symbol=symbol,
        timeframe=timeframe,
        generated_at=generated_at,
        mode_actual=mode_actual,
        model=model,
    )


def _request_hash(signal: Mapping[str, Any], *, model: str, max_output_tokens: int) -> str:
    payload = {
        "signal": signal,
        "model": model,
        "max_output_tokens": max_output_tokens,
        "prompt_version": PROMPT_VERSION,
        "engine_version": VERSION,
    }
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:32]


def _cache_path(req_hash: str) -> Path:
    return CACHE_DIR / f"{req_hash}.json"


def _load_counters() -> dict[str, Any]:
    if not COUNTER_PATH.exists():
        return {"calls": [], "month_tokens": 0, "month_key": _now_utc().strftime("%Y-%m")}
    try:
        return json.loads(COUNTER_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"calls": [], "month_tokens": 0, "month_key": _now_utc().strftime("%Y-%m")}


def _save_counters(counters: Mapping[str, Any]) -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    COUNTER_PATH.write_text(json.dumps(counters, indent=2, sort_keys=True), encoding="utf-8")


def _prune_calls(counters: dict[str, Any]) -> dict[str, Any]:
    cutoff = time.time() - 3600
    counters["calls"] = [t for t in counters.get("calls", []) if t >= cutoff]
    month_key = _now_utc().strftime("%Y-%m")
    if counters.get("month_key") != month_key:
        counters["month_key"] = month_key
        counters["month_tokens"] = 0
    return counters


def _check_rate_limits(counters: Mapping[str, Any], expected_tokens: int) -> tuple[bool, str]:
    if len(counters.get("calls", [])) >= MAX_CALLS_PER_HOUR:
        return False, f"rate_limit: {MAX_CALLS_PER_HOUR}/hour exceeded"
    projected = int(counters.get("month_tokens", 0)) + int(expected_tokens)
    if projected > MAX_TOKENS_PER_MONTH:
        return False, f"cost_cap: month would hit {projected}/{MAX_TOKENS_PER_MONTH} tokens"
    return True, "ok"


def _load_secrets() -> dict[str, str]:
    env: dict[str, str] = {}
    if not SECRETS_FILE.exists():
        return env
    try:
        for raw in SECRETS_FILE.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            env[key.strip()] = value.strip().strip("'\"")
    except OSError:
        return env
    return env


def _sensitivity(prompt: str) -> tuple[bool, str]:
    if is_sensitive is not None:
        result = is_sensitive(prompt)
        return bool(result.sensitive), result.reason or ""
    match = _SENSITIVE_FALLBACK.search(prompt)
    return bool(match), match.group(1) if match else ""


def _parse_model_json(text: str) -> dict[str, Any] | None:
    if not text:
        return None
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\n", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\n```$", "", cleaned)
    match = re.search(r"\{.*\}", cleaned, re.DOTALL)
    if not match:
        return None
    try:
        parsed = json.loads(match.group(0))
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def _coerce_live_thesis(
    payload: Mapping[str, Any],
    *,
    signal: Mapping[str, Any],
    mode_actual: str,
    model: str,
    now: datetime | None,
) -> NarrativeThesis:
    base = _mock_thesis(signal, mode_actual=mode_actual, model=model, now=now)
    generated_at = base.generated_at
    position = str(payload.get("implied_position") or base.implied_position)
    if position not in IMPLIED_POSITIONS:
        position = base.implied_position
    try:
        confidence = _clamp(float(payload.get("confidence", base.confidence)))
    except (TypeError, ValueError):
        confidence = base.confidence
    return NarrativeThesis(
        thesis_one_paragraph=str(payload.get("thesis_one_paragraph") or base.thesis_one_paragraph),
        evidence_bullets=_as_str_list(payload.get("evidence_bullets")) or base.evidence_bullets,
        counter_thesis_one_paragraph=str(
            payload.get("counter_thesis_one_paragraph") or base.counter_thesis_one_paragraph
        ),
        invalidators=_as_str_list(payload.get("invalidators")) or base.invalidators,
        next_signal_to_watch=str(payload.get("next_signal_to_watch") or base.next_signal_to_watch),
        implied_position=position,  # type: ignore[arg-type]
        confidence=round(confidence, 4),
        caveat_block=str(payload.get("caveat_block") or base.caveat_block),
        provenance_envelope=_provenance(
            signal, mode_actual=mode_actual, model=model, now=generated_at
        ),
        symbol=base.symbol,
        timeframe=base.timeframe,
        generated_at=generated_at,
        mode_actual=mode_actual,
        model=model,
    )


def _live_generate(
    prompt: str,
    *,
    model: str,
    max_output_tokens: int,
    api_key: str,
    sdk_call: Any | None,
) -> dict[str, Any]:
    if sdk_call is not None:
        return sdk_call(prompt, model=model, max_output_tokens=max_output_tokens, api_key=api_key)
    import google.generativeai as genai  # pragma: no cover - real path only

    genai.configure(api_key=api_key)
    gen_model = genai.GenerativeModel(model)
    result = gen_model.generate_content(
        prompt,
        generation_config={"max_output_tokens": max_output_tokens, "temperature": 0.15},
    )
    usage = getattr(result, "usage_metadata", None)
    return {
        "text": getattr(result, "text", "") or "",
        "prompt_tokens": getattr(usage, "prompt_token_count", 0) if usage else 0,
        "output_tokens": getattr(usage, "candidates_token_count", 0) if usage else 0,
        "total_tokens": getattr(usage, "total_token_count", 0) if usage else 0,
    }


def synthesize_thesis(
    signal: Any,
    *,
    mode: str = "dry-run",
    model: str = DEFAULT_MODEL,
    max_output_tokens: int = 2048,
    ttl_seconds: int = 86_400,
    use_cache: bool = True,
    sdk_call: Any | None = None,
    now: datetime | None = None,
) -> NarrativeThesis:
    """Return one :class:`NarrativeThesis` for a correlated signal."""
    signal_payload = _signal_dict(signal)
    model = model or DEFAULT_MODEL
    if model not in KNOWN_MODELS:
        raise ValueError(f"unknown model '{model}'")
    max_output_tokens = max(256, min(int(max_output_tokens), MAX_OUTPUT_TOKENS_HARD))
    ttl_seconds = max(60, min(int(ttl_seconds), 7 * 86_400))
    requested_mode = (mode or "dry-run").strip().lower()
    if requested_mode != "live":
        return _mock_thesis(signal_payload, mode_actual="dry-run", model=model, now=now)

    prompt = build_user_prompt(
        signal_payload, max_input_chars=MAX_INPUT_CHARS_HARD, mode=requested_mode
    )
    req_hash = _request_hash(signal_payload, model=model, max_output_tokens=max_output_tokens)
    cache_path = _cache_path(req_hash)
    if use_cache and cache_path.exists():
        try:
            cached = json.loads(cache_path.read_text(encoding="utf-8"))
            if time.time() - float(cached.get("_cached_at", 0.0)) <= ttl_seconds:
                thesis_payload = cached.get("thesis")
                if isinstance(thesis_payload, Mapping):
                    return _coerce_live_thesis(
                        thesis_payload,
                        signal=signal_payload,
                        mode_actual="live-cache",
                        model=model,
                        now=now,
                    )
        except (OSError, ValueError, json.JSONDecodeError):
            pass

    if os.environ.get("SAPPHIRE_NARRATIVE_LIVE", "").strip() != "1":
        return _mock_thesis(
            signal_payload, mode_actual="dry-run-blocked-by-env", model=model, now=now
        )
    # Gate the *injected* data, not the assembled prompt. build_user_prompt()
    # wraps the signal in a static in-repo template whose rules line reads "Do
    # not include secrets, credentials, raw private payloads" — scanning that
    # constant makes the guardrail's own wording trip the guardrail, blocking
    # every live call. The signal payload is the only untrusted input here.
    sensitive, reason = _sensitivity(json.dumps(signal_payload, default=str, sort_keys=True))
    if sensitive:
        thesis = _mock_thesis(signal_payload, mode_actual="dry-run-safety", model=model, now=now)
        thesis.provenance_envelope["sensitivity"] = {"sensitive": True, "reason": reason}
        return thesis

    counters = _prune_calls(_load_counters())
    expected_tokens = max_output_tokens + min(len(prompt), MAX_INPUT_CHARS_HARD)
    allowed, rate_reason = _check_rate_limits(counters, expected_tokens)
    if not allowed:
        thesis = _mock_thesis(
            signal_payload, mode_actual="dry-run-rate-limited", model=model, now=now
        )
        thesis.provenance_envelope["rate_limit_reason"] = rate_reason
        return thesis

    secrets = _load_secrets()
    api_key = (
        secrets.get("GEMINI_API_KEY")
        or secrets.get("GOOGLE_API_KEY")
        or os.environ.get("GEMINI_API_KEY")
        or os.environ.get("GOOGLE_API_KEY")
    )
    if not api_key:
        return _mock_thesis(signal_payload, mode_actual="dry-run-no-key", model=model, now=now)

    try:
        response = _live_generate(
            prompt,
            model=model,
            max_output_tokens=max_output_tokens,
            api_key=api_key,
            sdk_call=sdk_call,
        )
    except Exception as exc:  # noqa: BLE001 - live failures are soft fallbacks.
        thesis = _mock_thesis(
            signal_payload, mode_actual="dry-run-live-error", model=model, now=now
        )
        thesis.provenance_envelope["live_error"] = type(exc).__name__
        return thesis

    parsed = _parse_model_json(str(response.get("text") or ""))
    if parsed is None:
        thesis = _mock_thesis(
            signal_payload, mode_actual="dry-run-live-unparseable", model=model, now=now
        )
        thesis.provenance_envelope["live_response_preview_hash"] = hashlib.sha256(
            str(response.get("text") or "")[:400].encode("utf-8")
        ).hexdigest()
        return thesis

    thesis = _coerce_live_thesis(
        parsed, signal=signal_payload, mode_actual="live", model=model, now=now
    )
    tokens = int(response.get("total_tokens") or 0)
    counters.setdefault("calls", []).append(time.time())
    counters["month_tokens"] = int(counters.get("month_tokens", 0)) + tokens
    _save_counters(counters)

    cache_payload = stamp(
        {
            "thesis": thesis.to_dict(),
            "tokens": {
                "prompt_tokens": int(response.get("prompt_tokens") or 0),
                "output_tokens": int(response.get("output_tokens") or 0),
                "total_tokens": tokens,
            },
            "_cached_at": time.time(),
        },
        generator=GENERATOR,
        model=model,
        prompt=prompt,
        ttl_seconds=ttl_seconds,
        metadata={"cache": True, "mode": "live"},
    )
    try:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(json.dumps(cache_payload, indent=2, sort_keys=True), encoding="utf-8")
    except OSError:
        pass
    return thesis


def synthesize(
    signal: Any,
    *,
    mode: str = "dry-run",
    model: str = DEFAULT_MODEL,
    max_output_tokens: int = 2048,
    ttl_seconds: int = 86_400,
    use_cache: bool = True,
    sdk_call: Any | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    signal_payload = _signal_dict(signal)
    try:
        thesis = synthesize_thesis(
            signal_payload,
            mode=mode,
            model=model,
            max_output_tokens=max_output_tokens,
            ttl_seconds=ttl_seconds,
            use_cache=use_cache,
            sdk_call=sdk_call,
            now=now,
        )
    except (TypeError, ValueError) as exc:
        return {"ok": False, "error": str(exc)}
    rubric = score_narrative(thesis, signal=signal_payload)
    return {
        "ok": True,
        "thesis": thesis.to_dict(),
        "rubric": rubric.to_dict(),
        "metadata": {
            "generator": GENERATOR,
            "version": VERSION,
            "prompt_version": PROMPT_VERSION,
            "mode_requested": mode,
            "mode_actual": thesis.mode_actual,
            "model": thesis.model,
            "publishable": rubric.publishable,
            "min_rubric_score_to_publish": MIN_RUBRIC_SCORE_TO_PUBLISH,
        },
    }


def status() -> dict[str, Any]:
    counters = _prune_calls(_load_counters())
    cache_files = list(CACHE_DIR.glob("*.json")) if CACHE_DIR.exists() else []
    cache_files = [path for path in cache_files if path.name != COUNTER_PATH.name]
    return {
        "cache_dir": str(CACHE_DIR),
        "cache_entries": len(cache_files),
        "calls_last_hour": len(counters.get("calls", [])),
        "max_calls_per_hour": MAX_CALLS_PER_HOUR,
        "month_tokens": int(counters.get("month_tokens", 0)),
        "max_tokens_per_month": MAX_TOKENS_PER_MONTH,
        "month_key": counters.get("month_key"),
        "live_env": os.environ.get("SAPPHIRE_NARRATIVE_LIVE") == "1",
        "secrets_file_present": SECRETS_FILE.exists(),
        "default_model": DEFAULT_MODEL,
        "known_models": sorted(KNOWN_MODELS),
        "min_rubric_score_to_publish": MIN_RUBRIC_SCORE_TO_PUBLISH,
        "version": VERSION,
        "generator": GENERATOR,
    }


__all__ = [
    "CACHE_DIR",
    "COUNTER_PATH",
    "DEFAULT_MODEL",
    "GENERATOR",
    "KNOWN_MODELS",
    "MAX_CALLS_PER_HOUR",
    "MAX_INPUT_CHARS_HARD",
    "MAX_OUTPUT_TOKENS_HARD",
    "MAX_TOKENS_PER_MONTH",
    "MIN_RUBRIC_SCORE_TO_PUBLISH",
    "SECRETS_FILE",
    "VERSION",
    "NarrativeThesis",
    "implied_position_for_edge",
    "status",
    "synthesize",
    "synthesize_thesis",
]
