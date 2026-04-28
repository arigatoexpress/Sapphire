#!/usr/bin/env python3
"""Sapphire Vertex/Gemini eval harness — bounded benchmark of the Vertex lane.

A Sapphire plugin tool that runs a battery of OODA prompts through the
deterministic dry-run baseline and (optionally) a real Gemini call,
then scores the outputs against a reproducible rubric. The point is to
let the operator audit "is the Google AI Plus / Vertex spend actually
buying us better reasoning than the local 4-tier mesh?".

Modes
-----
- dry-run (default) — every action that would otherwise contact Google
  is short-circuited to the deterministic mock. Safe in CI and in any
  context that has not opted into live spend.
- live (``SAPPHIRE_GEMINI_LIVE=1``) — calls Gemini via
  ``google.generativeai`` with the same hard caps as the gemini_ooda
  tool plus a per-run prompt cap, and refuses to run if the input fails
  the Sapphire sensitivity gate.

Actions
-------
- ``eval``       — run a prompt set against the dry-run baseline.
                   Returns rubric scores per prompt + aggregate.
                   Live mode runs the same prompts through Gemini and
                   reports the live aggregate alongside.
- ``compare``    — run the same prompt set against (i) Gemini live (if
                   the env flag is set), (ii) the local mesh
                   ``balanced`` tier, and (iii) the deterministic mock.
                   Returns aggregate deltas per generator.
- ``prompt-set`` — list canonical eval prompt sets bundled in the tool.
- ``status``     — show counters, cache state, last eval timestamp.
                   Never contacts Google.

Output (stdout JSON)
--------------------
A dict whose top-level fields depend on the action. For ``eval`` and
``compare`` the result includes a ``provenance`` envelope from
``lib/core/provenance.py``; on ``eval`` runs the JSON output is also
written to ``~/.cache/sapphire/vertex_eval/runs/<id>.json`` with a
sidecar envelope file.

Safety
------
- No secrets are echoed back; the Gemini API key is loaded from
  ``~/.sapphire/secrets.env`` only when ``SAPPHIRE_GEMINI_LIVE=1``.
- Inputs are screened by :mod:`sensitivity_classifier`; sensitive
  prompts fall back to the dry-run mock with the matching
  ``mode_actual`` tag.
- Caches and counters live under ``~/.cache/sapphire/vertex_eval/``;
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
import urllib.error
import urllib.request
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


def _load_module_from_path(name: str, path: Path) -> Any:
    """Load a Python module by absolute path, registering it in sys.modules.

    Used in preference to ``from lib.X import Y`` so this tool works under
    every Sapphire test harness, including pytest invocations that don't
    load the top-level ``tests/conftest.py`` (which is what puts ``REPO_ROOT``
    on ``sys.path``).
    """
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load module {name!r} from {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules.setdefault(name, module)
    spec.loader.exec_module(module)
    return module


_provenance = _load_module_from_path(
    "sapphire_core_provenance_vertex_eval", REPO_ROOT / "lib" / "core" / "provenance.py"
)
stamp = _provenance.stamp
write_envelope_sidecar = _provenance.write_envelope_sidecar

_vertex_harness = _load_module_from_path(
    "sapphire_lib_eval_vertex_harness", REPO_ROOT / "lib" / "eval" / "vertex_harness.py"
)
EVAL_PROMPT_SETS = _vertex_harness.EVAL_PROMPT_SETS
EVAL_PROMPTS_PER_RUN_HARD = _vertex_harness.EVAL_PROMPTS_PER_RUN_HARD
MAX_CALLS_PER_HOUR = _vertex_harness.MAX_CALLS_PER_HOUR
MAX_INPUT_CHARS_HARD = _vertex_harness.MAX_INPUT_CHARS_HARD
MAX_OUTPUT_TOKENS_HARD = _vertex_harness.MAX_OUTPUT_TOKENS_HARD
MAX_TOKENS_PER_MONTH = _vertex_harness.MAX_TOKENS_PER_MONTH
PROMPT_SET_NAMES = _vertex_harness.PROMPT_SET_NAMES
AggregateScores = _vertex_harness.AggregateScores
PromptCase = _vertex_harness.PromptCase
RubricScores = _vertex_harness.RubricScores
aggregate_scores = _vertex_harness.aggregate_scores
deterministic_mock_response = _vertex_harness.deterministic_mock_response
enforce_caps = _vertex_harness.enforce_caps
score_response = _vertex_harness.score_response


CACHE_DIR = Path.home() / ".cache" / "sapphire" / "vertex_eval"
COUNTER_PATH = CACHE_DIR / "counters.json"
RUNS_DIR = CACHE_DIR / "runs"
LAST_RUN_PATH = CACHE_DIR / "last_run.json"
SECRETS_FILE = Path.home() / ".sapphire" / "secrets.env"

DEFAULT_MODEL = "gemini-2.5-flash"
KNOWN_MODELS = {
    "gemini-2.5-flash": {
        "context_window": 1_000_000,
        "tier": "flash",
        "notes": "Default. Cheap, fast, good for OODA-style synthesis.",
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

DEFAULT_LOCAL_PROXY_URL = "http://127.0.0.1:11435/v1/chat/completions"
DEFAULT_LOCAL_MODEL_ALIAS = "balanced"

# Deterministic re-export of the harness caps so plugin tests and
# downstream tooling can import them from this module too.
__all__ = [
    "CACHE_DIR",
    "COUNTER_PATH",
    "DEFAULT_LOCAL_MODEL_ALIAS",
    "DEFAULT_LOCAL_PROXY_URL",
    "DEFAULT_MODEL",
    "EVAL_PROMPTS_PER_RUN_HARD",
    "KNOWN_MODELS",
    "LAST_RUN_PATH",
    "MAX_CALLS_PER_HOUR",
    "MAX_INPUT_CHARS_HARD",
    "MAX_OUTPUT_TOKENS_HARD",
    "MAX_TOKENS_PER_MONTH",
    "PROMPT_SET_NAMES",
    "RUNS_DIR",
    "SECRETS_FILE",
    "compare",
    "evaluate",
    "handle",
    "main",
    "prompt_set_listing",
    "status",
]


def _now_utc() -> datetime:
    return datetime.now(UTC)


def _load_secrets() -> dict[str, str]:
    """Read the secrets file if present. Never echoes values."""
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


def _load_counters() -> dict[str, Any]:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    if not COUNTER_PATH.exists():
        return {
            "calls": [],
            "month_tokens": 0,
            "month_key": _now_utc().strftime("%Y-%m"),
            "runs": 0,
        }
    try:
        return json.loads(COUNTER_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {
            "calls": [],
            "month_tokens": 0,
            "month_key": _now_utc().strftime("%Y-%m"),
            "runs": 0,
        }


def _save_counters(counters: dict[str, Any]) -> None:
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


def _check_rate_limits(counters: dict[str, Any], expected_tokens: int) -> tuple[bool, str]:
    if len(counters.get("calls", [])) >= MAX_CALLS_PER_HOUR:
        return False, f"rate_limit: {MAX_CALLS_PER_HOUR}/hour exceeded"
    projected = counters.get("month_tokens", 0) + expected_tokens
    if projected > MAX_TOKENS_PER_MONTH:
        return False, f"cost_cap: month would hit {projected}/{MAX_TOKENS_PER_MONTH} tokens"
    return True, "ok"


def _build_prompt(case: PromptCase) -> str:
    return (
        "You are Sapphire's OODA synthesizer. Reply with strict JSON only, no "
        "prose, no code fences, matching exactly this schema:\n"
        '{"observe": "...", "orient": "...", "decide": "...", "act": ["...", "..."]}\n'
        "Keep each value under 320 characters. The act array must contain at least "
        "two concrete next actions a Sapphire operator could take in dry-run mode "
        "without spending money or sending live messages.\n\n"
        f"Topic: {case.topic}\n\nContext:\n{case.context}"
    )


def _parse_model_json(text: str) -> dict[str, Any] | None:
    if not text:
        return None
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\n", "", cleaned)
        cleaned = re.sub(r"\n```$", "", cleaned)
    match = re.search(r"\{.*\}", cleaned, re.DOTALL)
    if not match:
        return None
    try:
        return json.loads(match.group(0))
    except json.JSONDecodeError:
        return None


def _request_hash(payload: dict[str, Any]) -> str:
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:32]


def _safe_topic(case: PromptCase) -> tuple[bool, str]:
    """Return (is_safe, reason) by running the case through the gate."""
    blob = f"{case.topic}\n{case.context}"
    sensitivity = is_sensitive(blob)
    if sensitivity.sensitive:
        return False, sensitivity.reason or "sensitive_input"
    return True, ""


def _live_gemini_call(
    case: PromptCase,
    *,
    model: str,
    max_output_tokens: int,
    api_key: str,
    sdk_call: Any | None,
) -> dict[str, Any]:
    """Invoke Gemini via the SDK seam; never reached without the env gate."""
    prompt = _build_prompt(case)
    if sdk_call is not None:
        return sdk_call(prompt, model=model, max_output_tokens=max_output_tokens, api_key=api_key)
    import google.generativeai as genai  # pragma: no cover - real path

    genai.configure(api_key=api_key)
    gen_model = genai.GenerativeModel(model)
    result = gen_model.generate_content(
        prompt,
        generation_config={"max_output_tokens": max_output_tokens, "temperature": 0.2},
    )
    usage = getattr(result, "usage_metadata", None)
    return {
        "text": getattr(result, "text", "") or "",
        "prompt_tokens": getattr(usage, "prompt_token_count", 0) if usage else 0,
        "output_tokens": getattr(usage, "candidates_token_count", 0) if usage else 0,
        "total_tokens": getattr(usage, "total_token_count", 0) if usage else 0,
    }


def _local_mesh_call(
    case: PromptCase,
    *,
    model_alias: str,
    proxy_url: str,
    max_output_tokens: int,
    local_call: Any | None,
) -> dict[str, Any]:
    """Invoke the local mesh via the inference proxy or a test seam."""
    prompt = _build_prompt(case)
    if local_call is not None:
        return local_call(prompt, model=model_alias, max_output_tokens=max_output_tokens)
    body = {
        "model": model_alias,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": max_output_tokens,
        "temperature": 0.2,
    }
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(  # noqa: S310 - proxy URL is configured by env
        proxy_url, data=data, headers={"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:  # noqa: S310
            payload = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError) as exc:
        return {"text": "", "error": type(exc).__name__, "total_tokens": 0}
    text = ""
    try:
        text = payload["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError):
        text = ""
    usage = payload.get("usage") or {}
    return {
        "text": text,
        "prompt_tokens": usage.get("prompt_tokens", 0) or 0,
        "output_tokens": usage.get("completion_tokens", 0) or 0,
        "total_tokens": usage.get("total_tokens", 0) or 0,
    }


def _resolve_cases(
    *,
    set_name: str | None,
    prompt_ids: list[str] | None,
) -> tuple[list[PromptCase], str | None]:
    if set_name and set_name in EVAL_PROMPT_SETS:
        cases = list(EVAL_PROMPT_SETS[set_name])
        if prompt_ids:
            cases = [c for c in cases if c.prompt_id in set(prompt_ids)]
        return cases, None
    if not set_name and not prompt_ids:
        cases: list[PromptCase] = []
        for name in PROMPT_SET_NAMES:
            cases.extend(EVAL_PROMPT_SETS[name])
        return cases, None
    if prompt_ids:
        cases = []
        for name in PROMPT_SET_NAMES:
            cases.extend(c for c in EVAL_PROMPT_SETS[name] if c.prompt_id in set(prompt_ids))
        if not cases:
            return [], "no_matching_prompt_ids"
        return cases, None
    return [], f"unknown_prompt_set:{set_name!r}"


def _resolve_mode(
    *,
    requested_mode: str,
    has_sensitive_case: bool,
    live_env: bool,
    api_key_present: bool,
) -> str:
    if requested_mode != "live":
        return "dry-run"
    if not live_env:
        return "dry-run-blocked-by-env"
    if has_sensitive_case:
        return "dry-run-safety"
    if not api_key_present:
        return "dry-run-no-key"
    return "live"


def _score_case(
    case: PromptCase,
    response: Any,
    *,
    latency_ms: int,
    tokens_used: int,
    max_output_tokens: int,
) -> RubricScores:
    return score_response(
        response,
        case=case,
        latency_ms=latency_ms,
        tokens_used=tokens_used,
        max_output_tokens=max_output_tokens,
    )


def _per_prompt_record(
    case: PromptCase,
    response: Any,
    rubric: RubricScores,
    *,
    generator: str,
    error: str | None = None,
) -> dict[str, Any]:
    return {
        "prompt_id": case.prompt_id,
        "set_name": case.set_name,
        "topic": case.topic,
        "generator": generator,
        "rubric": rubric.to_dict(),
        "error": error,
        "response_keys": sorted(response.keys()) if isinstance(response, dict) else [],
    }


def _generator_section(
    *,
    name: str,
    cases: list[PromptCase],
    responses: list[dict[str, Any]],
    rubrics: list[RubricScores],
    errors: list[str | None],
) -> dict[str, Any]:
    per_prompt = [
        _per_prompt_record(case, response, rubric, generator=name, error=error)
        for case, response, rubric, error in zip(cases, responses, rubrics, errors, strict=False)
    ]
    return {
        "generator": name,
        "aggregate": aggregate_scores(rubrics).to_dict(),
        "per_prompt": per_prompt,
    }


def _delta(
    a: AggregateScores | dict[str, Any], b: AggregateScores | dict[str, Any]
) -> dict[str, float]:
    if isinstance(a, AggregateScores):
        a = a.to_dict()
    if isinstance(b, AggregateScores):
        b = b.to_dict()
    keys = (
        "structural_validity_mean",
        "actionability_mean",
        "citation_density_mean",
        "latency_ms_mean",
    )
    return {k: round(float(a.get(k, 0.0)) - float(b.get(k, 0.0)), 4) for k in keys}


def _generate_dry_run(cases: list[PromptCase]) -> tuple[
    list[dict[str, Any]], list[RubricScores], list[str | None]
]:
    responses: list[dict[str, Any]] = []
    rubrics: list[RubricScores] = []
    errors: list[str | None] = []
    for case in cases:
        response = deterministic_mock_response(case)
        responses.append(response)
        rubrics.append(
            _score_case(
                case,
                response,
                latency_ms=0,
                tokens_used=0,
                max_output_tokens=0,
            )
        )
        errors.append(None)
    return responses, rubrics, errors


def _generate_live(
    cases: list[PromptCase],
    *,
    model: str,
    max_output_tokens: int,
    api_key: str,
    sdk_call: Any | None,
    counters: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[RubricScores], list[str | None], dict[str, Any]]:
    """Run the live Gemini path, falling back to mocks per-case on errors."""
    responses: list[dict[str, Any]] = []
    rubrics: list[RubricScores] = []
    errors: list[str | None] = []
    rate_state: dict[str, Any] = {
        "calls_last_hour": len(counters.get("calls", [])),
        "month_tokens": counters.get("month_tokens", 0),
    }
    for case in cases:
        expected_tokens = max_output_tokens + min(
            len(case.topic) + len(case.context), MAX_INPUT_CHARS_HARD
        )
        allowed, reason = _check_rate_limits(counters, expected_tokens)
        if not allowed:
            mock = deterministic_mock_response(case)
            responses.append(mock)
            rubrics.append(
                _score_case(
                    case,
                    mock,
                    latency_ms=0,
                    tokens_used=0,
                    max_output_tokens=max_output_tokens,
                )
            )
            errors.append(reason)
            continue
        start = time.perf_counter()
        try:
            sdk_response = _live_gemini_call(
                case,
                model=model,
                max_output_tokens=max_output_tokens,
                api_key=api_key,
                sdk_call=sdk_call,
            )
        except Exception as exc:  # noqa: BLE001 - surface SDK errors as soft fallback
            mock = deterministic_mock_response(case)
            responses.append(mock)
            rubrics.append(
                _score_case(
                    case,
                    mock,
                    latency_ms=0,
                    tokens_used=0,
                    max_output_tokens=max_output_tokens,
                )
            )
            errors.append(f"live_error:{type(exc).__name__}")
            continue
        latency_ms = int((time.perf_counter() - start) * 1000)
        text = sdk_response.get("text", "") or ""
        parsed = _parse_model_json(text) or {"_raw_text": text[:200]}
        tokens_total = int(sdk_response.get("total_tokens") or 0)
        counters.setdefault("calls", []).append(time.time())
        counters["month_tokens"] = counters.get("month_tokens", 0) + tokens_total
        responses.append(parsed)
        rubrics.append(
            _score_case(
                case,
                parsed,
                latency_ms=latency_ms,
                tokens_used=tokens_total,
                max_output_tokens=max_output_tokens,
            )
        )
        errors.append(None)
        rate_state["calls_last_hour"] = len(counters["calls"])
        rate_state["month_tokens"] = counters["month_tokens"]
    return responses, rubrics, errors, rate_state


def _generate_local_mesh(
    cases: list[PromptCase],
    *,
    model_alias: str,
    proxy_url: str,
    max_output_tokens: int,
    local_call: Any | None,
) -> tuple[list[dict[str, Any]], list[RubricScores], list[str | None]]:
    responses: list[dict[str, Any]] = []
    rubrics: list[RubricScores] = []
    errors: list[str | None] = []
    for case in cases:
        start = time.perf_counter()
        sdk_response = _local_mesh_call(
            case,
            model_alias=model_alias,
            proxy_url=proxy_url,
            max_output_tokens=max_output_tokens,
            local_call=local_call,
        )
        latency_ms = int((time.perf_counter() - start) * 1000)
        if sdk_response.get("error"):
            mock = deterministic_mock_response(case)
            responses.append(mock)
            rubrics.append(
                _score_case(
                    case,
                    mock,
                    latency_ms=latency_ms,
                    tokens_used=0,
                    max_output_tokens=max_output_tokens,
                )
            )
            errors.append(f"local_error:{sdk_response['error']}")
            continue
        parsed = _parse_model_json(sdk_response.get("text", "") or "")
        if parsed is None:
            parsed = {"_raw_text": (sdk_response.get("text") or "")[:200]}
        tokens_total = int(sdk_response.get("total_tokens") or 0)
        responses.append(parsed)
        rubrics.append(
            _score_case(
                case,
                parsed,
                latency_ms=latency_ms,
                tokens_used=tokens_total,
                max_output_tokens=max_output_tokens,
            )
        )
        errors.append(None)
    return responses, rubrics, errors


def _persist_run(
    *,
    run_id: str,
    payload: dict[str, Any],
    prompt: str,
) -> dict[str, Any]:
    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    stamped = stamp(
        payload,
        generator="plugins.claw_sapphire.vertex_eval",
        model=payload.get("metadata", {}).get("model"),
        prompt=prompt,
        ttl_seconds=7 * 86400,
        metadata={"run_id": run_id, "kind": payload.get("action")},
    )
    artifact = RUNS_DIR / f"{run_id}.json"
    try:
        artifact.write_text(
            json.dumps(stamped, indent=2, sort_keys=True), encoding="utf-8"
        )
    except OSError:
        return stamped
    try:
        write_envelope_sidecar(
            artifact,
            generator="plugins.claw_sapphire.vertex_eval",
            model=payload.get("metadata", {}).get("model"),
            prompt=prompt,
            ttl_seconds=7 * 86400,
            metadata={"run_id": run_id, "kind": payload.get("action")},
        )
    except OSError:
        pass
    try:
        LAST_RUN_PATH.write_text(
            json.dumps(
                {
                    "run_id": run_id,
                    "artifact": str(artifact),
                    "completed_at": _now_utc().isoformat(),
                    "action": payload.get("action"),
                    "mode_actual": payload.get("metadata", {}).get("mode_actual"),
                },
                indent=2,
                sort_keys=True,
            ),
            encoding="utf-8",
        )
    except OSError:
        pass
    return stamped


def evaluate(
    *,
    set_name: str | None = None,
    prompt_ids: list[str] | None = None,
    mode: str = "dry-run",
    model: str = DEFAULT_MODEL,
    max_output_tokens: int = 512,
    sdk_call: Any | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    if model not in KNOWN_MODELS:
        return {"error": f"unknown model '{model}'", "known_models": sorted(KNOWN_MODELS)}
    cases, error = _resolve_cases(set_name=set_name, prompt_ids=prompt_ids)
    if error:
        return {"error": error}
    if not cases:
        return {"error": "no_prompts_resolved"}
    max_output_tokens = max(64, min(int(max_output_tokens), MAX_OUTPUT_TOKENS_HARD))
    max_input_chars = max((len(c.topic) + len(c.context)) for c in cases)
    within_caps, caps_reason = enforce_caps(
        prompt_count=len(cases),
        max_output_tokens=max_output_tokens,
        input_chars=max_input_chars,
    )
    if not within_caps:
        return {"error": f"caps_breach:{caps_reason}"}

    sensitive_cases: list[dict[str, str]] = []
    safe_cases: list[PromptCase] = []
    for case in cases:
        ok, reason = _safe_topic(case)
        if not ok:
            sensitive_cases.append({"prompt_id": case.prompt_id, "reason": reason})
        else:
            safe_cases.append(case)

    requested_mode = (mode or "dry-run").lower()
    live_env = os.environ.get("SAPPHIRE_GEMINI_LIVE", "").strip() == "1"
    secrets = _load_secrets()
    api_key = (
        secrets.get("GEMINI_API_KEY")
        or secrets.get("GOOGLE_API_KEY")
        or os.environ.get("GEMINI_API_KEY")
        or os.environ.get("GOOGLE_API_KEY")
    )
    actual_mode = _resolve_mode(
        requested_mode=requested_mode,
        has_sensitive_case=bool(sensitive_cases),
        live_env=live_env,
        api_key_present=bool(api_key),
    )

    issued = (now or _now_utc()).isoformat()
    run_id_seed = {
        "set_name": set_name,
        "prompt_ids": prompt_ids,
        "mode": actual_mode,
        "model": model,
        "max_output_tokens": max_output_tokens,
        "issued": issued,
    }
    run_id = _request_hash(run_id_seed)

    metadata: dict[str, Any] = {
        "mode_requested": requested_mode,
        "mode_actual": actual_mode,
        "model": model,
        "issued_at": issued,
        "set_name": set_name,
        "prompt_count": len(cases),
        "sensitive_cases": sensitive_cases,
        "max_output_tokens": max_output_tokens,
        "run_id": run_id,
    }

    counters = _prune_calls(_load_counters())

    sections: list[dict[str, Any]] = []
    dry_responses, dry_rubrics, dry_errors = _generate_dry_run(cases)
    sections.append(
        _generator_section(
            name="dry-run",
            cases=cases,
            responses=dry_responses,
            rubrics=dry_rubrics,
            errors=dry_errors,
        )
    )

    if actual_mode == "live" and safe_cases:
        live_responses, live_rubrics, live_errors, rate_state = _generate_live(
            safe_cases,
            model=model,
            max_output_tokens=max_output_tokens,
            api_key=api_key or "",
            sdk_call=sdk_call,
            counters=counters,
        )
        metadata["rate_limit_state"] = rate_state
        sections.append(
            _generator_section(
                name="gemini-live",
                cases=safe_cases,
                responses=live_responses,
                rubrics=live_rubrics,
                errors=live_errors,
            )
        )

    counters["runs"] = counters.get("runs", 0) + 1
    _save_counters(counters)

    payload: dict[str, Any] = {
        "action": "eval",
        "metadata": metadata,
        "generators": sections,
    }
    stamped = _persist_run(
        run_id=run_id,
        payload=payload,
        prompt=json.dumps(run_id_seed, sort_keys=True),
    )
    return stamped


def compare(
    *,
    set_name: str | None = None,
    prompt_ids: list[str] | None = None,
    mode: str = "dry-run",
    model: str = DEFAULT_MODEL,
    local_model_alias: str = DEFAULT_LOCAL_MODEL_ALIAS,
    proxy_url: str = DEFAULT_LOCAL_PROXY_URL,
    max_output_tokens: int = 512,
    sdk_call: Any | None = None,
    local_call: Any | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    if model not in KNOWN_MODELS:
        return {"error": f"unknown model '{model}'", "known_models": sorted(KNOWN_MODELS)}
    cases, error = _resolve_cases(set_name=set_name, prompt_ids=prompt_ids)
    if error:
        return {"error": error}
    if not cases:
        return {"error": "no_prompts_resolved"}
    max_output_tokens = max(64, min(int(max_output_tokens), MAX_OUTPUT_TOKENS_HARD))
    max_input_chars = max((len(c.topic) + len(c.context)) for c in cases)
    within_caps, caps_reason = enforce_caps(
        prompt_count=len(cases),
        max_output_tokens=max_output_tokens,
        input_chars=max_input_chars,
    )
    if not within_caps:
        return {"error": f"caps_breach:{caps_reason}"}

    sensitive_cases: list[dict[str, str]] = []
    safe_cases: list[PromptCase] = []
    for case in cases:
        ok, reason = _safe_topic(case)
        if not ok:
            sensitive_cases.append({"prompt_id": case.prompt_id, "reason": reason})
        else:
            safe_cases.append(case)

    requested_mode = (mode or "dry-run").lower()
    live_env = os.environ.get("SAPPHIRE_GEMINI_LIVE", "").strip() == "1"
    secrets = _load_secrets()
    api_key = (
        secrets.get("GEMINI_API_KEY")
        or secrets.get("GOOGLE_API_KEY")
        or os.environ.get("GEMINI_API_KEY")
        or os.environ.get("GOOGLE_API_KEY")
    )
    actual_mode = _resolve_mode(
        requested_mode=requested_mode,
        has_sensitive_case=bool(sensitive_cases),
        live_env=live_env,
        api_key_present=bool(api_key),
    )

    issued = (now or _now_utc()).isoformat()
    run_id_seed = {
        "set_name": set_name,
        "prompt_ids": prompt_ids,
        "mode": actual_mode,
        "model": model,
        "local_model_alias": local_model_alias,
        "max_output_tokens": max_output_tokens,
        "issued": issued,
    }
    run_id = _request_hash(run_id_seed)

    metadata: dict[str, Any] = {
        "mode_requested": requested_mode,
        "mode_actual": actual_mode,
        "model": model,
        "local_model_alias": local_model_alias,
        "issued_at": issued,
        "set_name": set_name,
        "prompt_count": len(cases),
        "sensitive_cases": sensitive_cases,
        "max_output_tokens": max_output_tokens,
        "run_id": run_id,
    }

    counters = _prune_calls(_load_counters())

    sections: list[dict[str, Any]] = []
    dry_responses, dry_rubrics, dry_errors = _generate_dry_run(cases)
    sections.append(
        _generator_section(
            name="dry-run",
            cases=cases,
            responses=dry_responses,
            rubrics=dry_rubrics,
            errors=dry_errors,
        )
    )

    local_responses, local_rubrics, local_errors = _generate_local_mesh(
        cases,
        model_alias=local_model_alias,
        proxy_url=proxy_url,
        max_output_tokens=max_output_tokens,
        local_call=local_call,
    )
    sections.append(
        _generator_section(
            name="local-mesh",
            cases=cases,
            responses=local_responses,
            rubrics=local_rubrics,
            errors=local_errors,
        )
    )

    if actual_mode == "live" and safe_cases:
        live_responses, live_rubrics, live_errors, rate_state = _generate_live(
            safe_cases,
            model=model,
            max_output_tokens=max_output_tokens,
            api_key=api_key or "",
            sdk_call=sdk_call,
            counters=counters,
        )
        metadata["rate_limit_state"] = rate_state
        sections.append(
            _generator_section(
                name="gemini-live",
                cases=safe_cases,
                responses=live_responses,
                rubrics=live_rubrics,
                errors=live_errors,
            )
        )

    aggregates = {sec["generator"]: sec["aggregate"] for sec in sections}
    deltas: dict[str, dict[str, float]] = {}
    if "gemini-live" in aggregates and "local-mesh" in aggregates:
        deltas["live_minus_local"] = _delta(
            aggregates["gemini-live"], aggregates["local-mesh"]
        )
    if "gemini-live" in aggregates and "dry-run" in aggregates:
        deltas["live_minus_dry"] = _delta(
            aggregates["gemini-live"], aggregates["dry-run"]
        )
    if "local-mesh" in aggregates and "dry-run" in aggregates:
        deltas["local_minus_dry"] = _delta(
            aggregates["local-mesh"], aggregates["dry-run"]
        )

    counters["runs"] = counters.get("runs", 0) + 1
    _save_counters(counters)

    payload: dict[str, Any] = {
        "action": "compare",
        "metadata": metadata,
        "generators": sections,
        "deltas": deltas,
    }
    stamped = _persist_run(
        run_id=run_id,
        payload=payload,
        prompt=json.dumps(run_id_seed, sort_keys=True),
    )
    return stamped


def prompt_set_listing() -> dict[str, Any]:
    return {
        "sets": [
            {
                "name": name,
                "size": len(EVAL_PROMPT_SETS[name]),
                "prompt_ids": [c.prompt_id for c in EVAL_PROMPT_SETS[name]],
            }
            for name in PROMPT_SET_NAMES
        ],
        "total_prompts": sum(len(EVAL_PROMPT_SETS[name]) for name in PROMPT_SET_NAMES),
        "prompts_per_run_hard": EVAL_PROMPTS_PER_RUN_HARD,
    }


def status() -> dict[str, Any]:
    counters = _prune_calls(_load_counters())
    runs_dir = RUNS_DIR
    run_files = list(runs_dir.glob("*.json")) if runs_dir.exists() else []
    last_run: dict[str, Any] | None = None
    if LAST_RUN_PATH.exists():
        try:
            last_run = json.loads(LAST_RUN_PATH.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            last_run = None
    return {
        "cache_dir": str(CACHE_DIR),
        "runs_dir": str(runs_dir),
        "run_artifacts": len(run_files),
        "calls_last_hour": len(counters.get("calls", [])),
        "max_calls_per_hour": MAX_CALLS_PER_HOUR,
        "month_tokens": counters.get("month_tokens", 0),
        "max_tokens_per_month": MAX_TOKENS_PER_MONTH,
        "month_key": counters.get("month_key"),
        "runs_total": counters.get("runs", 0),
        "live_env": os.environ.get("SAPPHIRE_GEMINI_LIVE") == "1",
        "secrets_file_present": SECRETS_FILE.exists(),
        "prompts_per_run_hard": EVAL_PROMPTS_PER_RUN_HARD,
        "last_run": last_run,
    }


def handle(payload: dict[str, Any]) -> dict[str, Any]:
    action = (payload.get("action") or "eval").strip().lower()
    if action == "status":
        return status()
    if action in {"prompt-set", "prompt_sets", "prompt-sets"}:
        return prompt_set_listing()
    if action == "eval":
        return evaluate(
            set_name=payload.get("set_name"),
            prompt_ids=payload.get("prompt_ids"),
            mode=payload.get("mode") or "dry-run",
            model=payload.get("model") or DEFAULT_MODEL,
            max_output_tokens=int(payload.get("max_output_tokens") or 512),
        )
    if action == "compare":
        return compare(
            set_name=payload.get("set_name"),
            prompt_ids=payload.get("prompt_ids"),
            mode=payload.get("mode") or "dry-run",
            model=payload.get("model") or DEFAULT_MODEL,
            local_model_alias=payload.get("local_model_alias")
            or DEFAULT_LOCAL_MODEL_ALIAS,
            proxy_url=payload.get("proxy_url") or DEFAULT_LOCAL_PROXY_URL,
            max_output_tokens=int(payload.get("max_output_tokens") or 512),
        )
    return {
        "error": f"unknown action '{action}'",
        "valid_actions": ["eval", "compare", "prompt-set", "status"],
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
