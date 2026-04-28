#!/usr/bin/env python3
"""Sapphire Gemini OODA Synthesizer — bounded Vertex/Gemini reasoning lane.

A Sapphire plugin tool that turns a paste-safe topic plus optional context
into a structured OODA packet (Observe / Orient / Decide / Act). It is
designed to *complement* the local 4-tier inference mesh, not replace it,
and follows Sapphire's no-spend posture by defaulting to dry-run mode.

Modes
-----
- dry-run (default) — produces a deterministic mock OODA packet from the
  prompt; never reads ``GEMINI_API_KEY`` or contacts Google. Safe in CI and
  for any operator who has not opted into live spend.
- live (``SAPPHIRE_GEMINI_LIVE=1``) — calls Gemini via ``google.generativeai``
  with strict per-call token caps, a per-hour call cap, and a monthly token
  budget. Refuses to run if the input fails the Sapphire sensitivity gate.

Actions
-------
- ``synthesize``   — return an OODA packet for ``topic`` + ``context``.
- ``status``       — show cache hits, live-call counters, and rate-limit
                     state without contacting Google.
- ``models``       — list the Gemini model aliases the tool understands.

Input (stdin JSON)
------------------
::

    {
      "action": "synthesize",
      "topic": "Crypto regime shift signals",
      "context": "BTC bullish, funding flat, OI rising 3%",
      "mode": "dry-run",            # or "live" — only honoured if env flag set
      "model": "gemini-2.5-flash",
      "max_output_tokens": 512,
      "ttl_seconds": 86400
    }

Output (stdout JSON)
--------------------
A dict with ``ooda`` (observe/orient/decide/act), ``metadata`` (mode,
cached, tokens, source), and (in live mode) ``citations`` if the model
returned them.

Safety
------
- No secrets are echoed back; the API key is loaded from
  ``~/.sapphire/secrets.env`` only when ``SAPPHIRE_GEMINI_LIVE=1``.
- Inputs are screened by :mod:`sensitivity_classifier`; sensitive prompts
  fall back to the dry-run mock with ``mode_actual="dry-run-safety"``.
- Caches and counters live under ``~/.cache/sapphire/gemini_ooda/``;
  nothing leaves the machine unless live mode is explicitly enabled.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import re
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[4]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
PLUGIN_LIB = str(Path(__file__).parent.parent.parent / "lib")
if PLUGIN_LIB not in sys.path:
    sys.path.insert(1, PLUGIN_LIB)
from sensitivity_classifier import is_sensitive  # noqa: E402


def _load_provenance_stamp():
    spec = importlib.util.spec_from_file_location(
        "sapphire_core_provenance",
        REPO_ROOT / "lib" / "core" / "provenance.py",
    )
    if spec is None or spec.loader is None:
        raise ImportError("cannot load Sapphire provenance helper")
    module = importlib.util.module_from_spec(spec)
    sys.modules.setdefault("sapphire_core_provenance", module)
    spec.loader.exec_module(module)
    return module.stamp


stamp = _load_provenance_stamp()

CACHE_DIR = Path.home() / ".cache" / "sapphire" / "gemini_ooda"
COUNTER_PATH = CACHE_DIR / "counters.json"
SECRETS_FILE = Path.home() / ".sapphire" / "secrets.env"

DEFAULT_MODEL = "gemini-2.5-flash"
KNOWN_MODELS = {
    "gemini-2.5-flash": {
        "context_window": 1_000_000,
        "tier": "flash",
        "notes": "Default. Cheap, fast, good for OODA synthesis.",
    },
    "gemini-2.5-pro": {
        "context_window": 2_000_000,
        "tier": "pro",
        "notes": "Reserve for hard reasoning; cost is materially higher.",
    },
    "gemini-2.0-flash": {
        "context_window": 1_000_000,
        "tier": "flash",
        "notes": "Older flash model; kept for fallback.",
    },
}

# Hard caps — designed to fail closed.
MAX_OUTPUT_TOKENS_HARD = 4096
MAX_INPUT_CHARS_HARD = 12_000  # ~3000 tokens
MAX_CALLS_PER_HOUR = 8
MAX_TOKENS_PER_MONTH = 500_000


def _load_secrets() -> dict[str, str]:
    """Read secrets file if present. Never echoes values."""
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


def _now_utc() -> datetime:
    return datetime.now(UTC)


def _request_hash(payload: dict[str, Any]) -> str:
    """SHA-256 of the request payload — used as cache key."""
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:32]


def _cache_path(req_hash: str) -> Path:
    return CACHE_DIR / f"{req_hash}.json"


def _load_counters() -> dict[str, Any]:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    if not COUNTER_PATH.exists():
        return {"calls": [], "month_tokens": 0, "month_key": _now_utc().strftime("%Y-%m")}
    try:
        return json.loads(COUNTER_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"calls": [], "month_tokens": 0, "month_key": _now_utc().strftime("%Y-%m")}


def _save_counters(counters: dict[str, Any]) -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    COUNTER_PATH.write_text(json.dumps(counters, indent=2, sort_keys=True), encoding="utf-8")


def _prune_calls(counters: dict[str, Any]) -> dict[str, Any]:
    """Keep only call timestamps from the last 60 minutes."""
    cutoff = time.time() - 3600
    counters["calls"] = [t for t in counters.get("calls", []) if t >= cutoff]
    month_key = _now_utc().strftime("%Y-%m")
    if counters.get("month_key") != month_key:
        counters["month_key"] = month_key
        counters["month_tokens"] = 0
    return counters


def _check_rate_limits(counters: dict[str, Any], expected_tokens: int) -> tuple[bool, str]:
    """Return (allowed, reason)."""
    if len(counters.get("calls", [])) >= MAX_CALLS_PER_HOUR:
        return False, f"rate_limit: {MAX_CALLS_PER_HOUR}/hour exceeded"
    projected = counters.get("month_tokens", 0) + expected_tokens
    if projected > MAX_TOKENS_PER_MONTH:
        return False, f"cost_cap: month would hit {projected}/{MAX_TOKENS_PER_MONTH} tokens"
    return True, "ok"


def _build_prompt(topic: str, context: str | None) -> str:
    ctx = (context or "").strip()
    ctx_block = f"\n\nContext:\n{ctx}" if ctx else ""
    return (
        "You are Sapphire's OODA synthesizer. The operator has given you a topic "
        "and optional paste-safe context. Reply with strict JSON only, no prose, "
        "no code fences, matching exactly this schema:\n"
        '{"observe": "...", "orient": "...", "decide": "...", "act": ["...", "..."]}\n'
        "Keep each value under 320 characters. The act array must contain 1-4 "
        "concrete next actions a Sapphire operator could take in dry-run mode "
        "without spending money or sending live messages.\n\n"
        f"Topic: {topic}{ctx_block}"
    )


def _mock_synthesize(topic: str, context: str | None, reason: str = "dry-run") -> dict[str, Any]:
    """Deterministic mock OODA packet. Never calls a model."""
    base = topic.strip() or "untitled-topic"
    ctx = (context or "").strip()
    return {
        "observe": (
            f"Mock observation for '{base}'. Context length: {len(ctx)} chars. "
            "No live model was contacted."
        ),
        "orient": (
            "Sapphire is in production-for-testing posture: 4-tier local mesh + "
            "self-hosted CI + dry-run media factory. This OODA packet is offline."
        ),
        "decide": (
            "Defer external Gemini spend until SAPPHIRE_GEMINI_LIVE=1 is set and the "
            "monthly token cap is reviewed. Use the local Hermes/Kimi tiers in the meantime."
        ),
        "act": [
            "Run `python3 plugins/claw-sapphire/tools/gemini_ooda.py` with `mode=live` "
            "only after reviewing the per-call cap.",
            "If you only need synthesis, route via `sapphire_dispatch` to the local mesh.",
            "Re-run with the same topic later — cached results are reused for 24h by default.",
        ],
        "_mock_reason": reason,
    }


def _parse_model_json(text: str) -> dict[str, Any] | None:
    """Best-effort JSON extraction from a Gemini response.

    Models occasionally wrap JSON in code fences or add stray prose; this
    strips the most common variants before parsing.
    """
    if not text:
        return None
    cleaned = text.strip()
    if cleaned.startswith("```"):
        # Strip ``` and optional language tag.
        cleaned = re.sub(r"^```(?:json)?\n", "", cleaned)
        cleaned = re.sub(r"\n```$", "", cleaned)
    # Find the first {...} block.
    match = re.search(r"\{.*\}", cleaned, re.DOTALL)
    if not match:
        return None
    try:
        return json.loads(match.group(0))
    except json.JSONDecodeError:
        return None


def _live_synthesize(
    topic: str,
    context: str | None,
    *,
    model: str,
    max_output_tokens: int,
    api_key: str,
    sdk_call: Any | None = None,
) -> dict[str, Any]:
    """Call Gemini via google.generativeai. ``sdk_call`` is a test seam."""
    prompt = _build_prompt(topic, context)
    if sdk_call is not None:
        response = sdk_call(
            prompt, model=model, max_output_tokens=max_output_tokens, api_key=api_key
        )
    else:  # pragma: no cover - exercised only in real environments.
        import google.generativeai as genai

        genai.configure(api_key=api_key)
        gen_model = genai.GenerativeModel(model)
        result = gen_model.generate_content(
            prompt,
            generation_config={"max_output_tokens": max_output_tokens, "temperature": 0.2},
        )
        usage = getattr(result, "usage_metadata", None)
        response = {
            "text": getattr(result, "text", "") or "",
            "prompt_tokens": getattr(usage, "prompt_token_count", 0) if usage else 0,
            "output_tokens": getattr(usage, "candidates_token_count", 0) if usage else 0,
            "total_tokens": getattr(usage, "total_token_count", 0) if usage else 0,
        }
    parsed = _parse_model_json(response.get("text", ""))
    if not isinstance(parsed, dict):
        return {
            "_mock_reason": "live_response_unparseable",
            "raw_text": response.get("text", "")[:400],
            **_mock_synthesize(topic, context, reason="live_response_unparseable"),
            "_live_tokens": response,
        }
    parsed["_live_tokens"] = response
    return parsed


def _truncate(value: str, limit: int) -> str:
    return value if len(value) <= limit else value[: limit - 1] + "…"


def synthesize(
    *,
    topic: str,
    context: str | None,
    mode: str,
    model: str,
    max_output_tokens: int,
    ttl_seconds: int,
    sdk_call: Any | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    if not topic or not topic.strip():
        return {"error": "topic is required"}
    if model not in KNOWN_MODELS:
        return {"error": f"unknown model '{model}'", "known_models": sorted(KNOWN_MODELS)}
    max_output_tokens = max(64, min(max_output_tokens, MAX_OUTPUT_TOKENS_HARD))
    ttl_seconds = max(60, min(ttl_seconds, 7 * 86400))
    request_for_hash = {
        "topic": topic.strip(),
        "context": (context or "").strip(),
        "model": model,
        "max_output_tokens": max_output_tokens,
    }
    truncated_topic = _truncate(topic.strip(), 280)
    truncated_context = _truncate((context or "").strip(), MAX_INPUT_CHARS_HARD)

    sensitivity = is_sensitive(f"{truncated_topic}\n{truncated_context}")
    safety_blocked = bool(sensitivity.sensitive)
    requested_mode = (mode or "dry-run").lower()
    live_env = os.environ.get("SAPPHIRE_GEMINI_LIVE", "").strip() == "1"
    if requested_mode == "live" and not live_env:
        actual_mode = "dry-run-blocked-by-env"
    elif safety_blocked:
        actual_mode = "dry-run-safety"
    else:
        actual_mode = requested_mode

    issued = (now or _now_utc()).isoformat()
    metadata: dict[str, Any] = {
        "mode_requested": requested_mode,
        "mode_actual": actual_mode,
        "model": model,
        "topic_hash": _request_hash(request_for_hash),
        "issued_at": issued,
        "cached": False,
        "tokens": None,
        "rate_limit_state": None,
        "sensitivity": {"sensitive": safety_blocked, "reason": sensitivity.reason or ""},
    }

    if actual_mode != "live":
        ooda = _mock_synthesize(truncated_topic, truncated_context, reason=actual_mode)
        return {"ooda": ooda, "metadata": metadata}

    cache_path = _cache_path(metadata["topic_hash"])
    if cache_path.exists():
        try:
            cached = json.loads(cache_path.read_text(encoding="utf-8"))
            cached_age = time.time() - cached.get("_cached_at", 0)
            if cached_age <= ttl_seconds:
                metadata["cached"] = True
                metadata["tokens"] = cached.get("tokens")
                return {"ooda": cached.get("ooda", {}), "metadata": metadata}
        except (OSError, json.JSONDecodeError):
            pass

    counters = _prune_calls(_load_counters())
    expected_tokens = max_output_tokens + min(
        len(truncated_topic) + len(truncated_context), MAX_INPUT_CHARS_HARD
    )
    allowed, reason = _check_rate_limits(counters, expected_tokens)
    metadata["rate_limit_state"] = {
        "calls_last_hour": len(counters.get("calls", [])),
        "month_tokens": counters.get("month_tokens", 0),
        "max_calls_per_hour": MAX_CALLS_PER_HOUR,
        "max_tokens_per_month": MAX_TOKENS_PER_MONTH,
    }
    if not allowed:
        metadata["mode_actual"] = "dry-run-rate-limited"
        metadata["rate_limit_reason"] = reason
        ooda = _mock_synthesize(truncated_topic, truncated_context, reason=metadata["mode_actual"])
        return {"ooda": ooda, "metadata": metadata}

    secrets = _load_secrets()
    api_key = (
        secrets.get("GEMINI_API_KEY")
        or secrets.get("GOOGLE_API_KEY")
        or os.environ.get("GEMINI_API_KEY")
        or os.environ.get("GOOGLE_API_KEY")
    )
    if not api_key:
        metadata["mode_actual"] = "dry-run-no-key"
        ooda = _mock_synthesize(truncated_topic, truncated_context, reason=metadata["mode_actual"])
        return {"ooda": ooda, "metadata": metadata}

    try:
        live = _live_synthesize(
            truncated_topic,
            truncated_context,
            model=model,
            max_output_tokens=max_output_tokens,
            api_key=api_key,
            sdk_call=sdk_call,
        )
    except Exception as exc:  # noqa: BLE001 - surface any SDK error as a soft fallback
        metadata["mode_actual"] = "dry-run-live-error"
        metadata["error"] = type(exc).__name__
        ooda = _mock_synthesize(truncated_topic, truncated_context, reason=metadata["mode_actual"])
        return {"ooda": ooda, "metadata": metadata}

    tokens = live.pop("_live_tokens", {}) or {}
    counters.setdefault("calls", []).append(time.time())
    counters["month_tokens"] = counters.get("month_tokens", 0) + int(
        tokens.get("total_tokens") or 0
    )
    _save_counters(counters)

    cache_payload = stamp(
        {"ooda": live, "tokens": tokens, "_cached_at": time.time()},
        generator="plugins.claw_sapphire.gemini_ooda",
        model=model,
        prompt=_build_prompt(truncated_topic, truncated_context),
        ttl_seconds=ttl_seconds,
        metadata={"cache": True, "mode": "live"},
    )
    try:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(json.dumps(cache_payload, indent=2, sort_keys=True), encoding="utf-8")
    except OSError:
        pass

    metadata["tokens"] = tokens
    metadata["rate_limit_state"]["calls_last_hour"] = len(counters["calls"])
    metadata["rate_limit_state"]["month_tokens"] = counters["month_tokens"]
    return {"ooda": live, "metadata": metadata}


def status() -> dict[str, Any]:
    counters = _prune_calls(_load_counters())
    cache_files = list(CACHE_DIR.glob("*.json")) if CACHE_DIR.exists() else []
    cache_files = [p for p in cache_files if p.name != COUNTER_PATH.name]
    return {
        "cache_dir": str(CACHE_DIR),
        "cache_entries": len(cache_files),
        "calls_last_hour": len(counters.get("calls", [])),
        "max_calls_per_hour": MAX_CALLS_PER_HOUR,
        "month_tokens": counters.get("month_tokens", 0),
        "max_tokens_per_month": MAX_TOKENS_PER_MONTH,
        "month_key": counters.get("month_key"),
        "live_env": os.environ.get("SAPPHIRE_GEMINI_LIVE") == "1",
        "secrets_file_present": SECRETS_FILE.exists(),
    }


def models() -> dict[str, Any]:
    return {
        "default": DEFAULT_MODEL,
        "models": KNOWN_MODELS,
    }


def handle(payload: dict[str, Any]) -> dict[str, Any]:
    action = (payload.get("action") or "synthesize").strip().lower()
    if action == "status":
        return status()
    if action == "models":
        return models()
    if action == "synthesize":
        return synthesize(
            topic=payload.get("topic") or "",
            context=payload.get("context"),
            mode=payload.get("mode") or "dry-run",
            model=payload.get("model") or DEFAULT_MODEL,
            max_output_tokens=int(payload.get("max_output_tokens") or 512),
            ttl_seconds=int(payload.get("ttl_seconds") or 86400),
        )
    return {
        "error": f"unknown action '{action}'",
        "valid_actions": ["synthesize", "status", "models"],
    }


def main(stream_in: Any = sys.stdin, stream_out: Any = sys.stdout) -> int:
    raw = stream_in.read() or "{}"
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        json.dump({"error": f"invalid JSON: {exc}"}, stream_out)
        return 2
    if not isinstance(payload, dict):
        json.dump({"error": "stdin payload must be a JSON object"}, stream_out)
        return 2
    response = handle(payload)
    json.dump(response, stream_out, indent=2, sort_keys=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
