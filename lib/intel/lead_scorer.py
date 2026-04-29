"""Local-AI lead scorer for Houston home leads.

Uses the Sapphire inference proxy (``127.0.0.1:11435``, hermes3:8b by default)
to score each lead 0-100 with a one-line reason and an urgency tag. When the
proxy is unavailable, falls back to the existing heuristic in
``plugins/claw-sapphire/tools/internal/lead_enrich.py`` so scoring never
blocks the pipeline.

Cost: hermes3:8b at ~154 tok/s on the GPU node ≈ free per lead.

Public API:
    score_lead(lead)  -> {"score": int, "reason": str, "urgency": str}
    score_unscored()  -> int   (count of leads scored)
"""

from __future__ import annotations

import json
import logging
import re
import urllib.request
from typing import Any

from lib.intel.houston_leads import LEADS_FILE, load_leads, save_leads

log = logging.getLogger(__name__)

INFERENCE_PROXY_URL = "http://127.0.0.1:11435/v1/chat/completions"
DEFAULT_MODEL = "hermes3:8b"

SCORING_SYSTEM_PROMPT = """You are a lead scoring agent for a home renovation services company in Houston, TX.
Score this homeowner lead 0-100 based on their likelihood to need and pay for home improvement services.

Scoring guidance:
- Foundation repair → 90-100 (urgent structural need, high spend)
- Residential remodel (kitchen, bathroom, addition) → 75-90 (active renovation budget)
- Roof repair or replacement → 75-85 (weather-driven urgency)
- HVAC, electrical, plumbing repair → 65-80 (system failure, motivated buyer)
- Solar panel installation → 50-65 (investing in home, budget available)
- Minor residential repairs → 40-55 (some willingness to spend)
- Commercial permits (office, retail, restaurant remodel) → 10-25 (not a homeowner lead)
- New construction → 5-15 (not yet a renovation prospect)
- Demolition only → 5-10 (low value)

Urgency: "high" for active failures (water leak, foundation, roof), "medium" for
planned renovations (remodel, addition, HVAC replacement), "low" for cosmetic /
amenity work.

Return strict JSON only: {"score": <int 0-100>, "reason": "<one short sentence>", "urgency": "high|medium|low"}"""


# ---------------------------------------------------------------------------
# Heuristic fallback (mirrors the spec rubric so behavior is consistent
# whether AI or fallback ran the scoring).
# ---------------------------------------------------------------------------

# Each tuple is (substring_match, score_floor, score_ceiling, urgency, reason).
HEURISTIC_RULES: list[tuple[tuple[str, ...], int, int, str, str]] = [
    (("foundation",), 90, 100, "high", "Foundation repair — urgent structural"),
    (("water leak", "flooding", "sewer"), 85, 95, "high", "Active water/flood damage"),
    (("unsafe structure", "structural"), 80, 92, "high", "Unsafe / structural condition"),
    (("roof",), 75, 85, "high", "Roof repair / replacement"),
    (("kitchen", "bathroom", "addition", "remodel", "renovation"), 75, 90, "medium",
     "Active residential remodel"),
    (("hvac", "electrical", "plumbing", "ac repair", "heater"), 65, 80, "medium",
     "Mechanical-system repair"),
    (("solar",), 50, 65, "medium", "Solar / energy upgrade"),
    (("repair", "replace"), 40, 55, "medium", "Minor residential repair"),
    (("commercial", "office", "retail", "restaurant"), 10, 25, "low",
     "Commercial permit — not a homeowner"),
    (("new construction", "new build"), 5, 15, "low", "New build — not yet a prospect"),
    (("demolition", "demo only"), 5, 10, "low", "Demolition only"),
]


def heuristic_score(lead: dict[str, Any]) -> dict[str, Any]:
    """Heuristic-only scoring — guaranteed to return."""
    text = " ".join(
        str(lead.get(k, "")) for k in ("type", "description", "raw_data")
    ).lower()
    for keywords, lo, hi, urgency, reason in HEURISTIC_RULES:
        if any(kw in text for kw in keywords):
            score = (lo + hi) // 2
            return {"score": score, "reason": reason, "urgency": urgency}
    return {"score": 30, "reason": "No high-signal keywords matched", "urgency": "low"}


# ---------------------------------------------------------------------------
# AI scoring via the inference proxy
# ---------------------------------------------------------------------------


def _infer(prompt: str, model: str, timeout: int = 30) -> str | None:
    payload = json.dumps(
        {
            "model": model,
            "messages": [
                {"role": "system", "content": SCORING_SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            "stream": False,
            "temperature": 0.1,
            "max_tokens": 200,
        }
    ).encode()
    req = urllib.request.Request(
        INFERENCE_PROXY_URL,
        data=payload,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            data = json.loads(r.read())
            return data.get("choices", [{}])[0].get("message", {}).get("content")
    except Exception as e:
        log.debug("inference proxy unavailable: %s", e)
        return None


def _parse_response(text: str) -> dict[str, Any] | None:
    """Extract the first valid scoring JSON from an LLM response."""
    if not text:
        return None
    match = re.search(r"\{[^{}]*\}", text, flags=re.DOTALL)
    candidate = match.group(0) if match else text.strip()
    try:
        parsed = json.loads(candidate)
    except json.JSONDecodeError:
        return None
    score = parsed.get("score")
    reason = parsed.get("reason")
    urgency = parsed.get("urgency")
    if not isinstance(score, (int, float)):
        return None
    if not isinstance(reason, str) or not reason:
        return None
    if urgency not in {"high", "medium", "low"}:
        return None
    return {"score": int(max(0, min(100, score))), "reason": reason, "urgency": urgency}


def score_lead(lead: dict[str, Any], model: str = DEFAULT_MODEL) -> dict[str, Any]:
    """Score one lead. AI first, heuristic fallback. Always returns a dict."""
    user_payload = json.dumps(
        {
            "type": lead.get("type"),
            "description": lead.get("description"),
            "address": lead.get("address"),
            "source": lead.get("source"),
            "raw_data": lead.get("raw_data") or {},
        },
        default=str,
    )
    text = _infer(user_payload, model=model)
    if text:
        parsed = _parse_response(text)
        if parsed:
            parsed["score_engine"] = f"ai:{model}"
            return parsed
    fallback = heuristic_score(lead)
    fallback["score_engine"] = "heuristic"
    return fallback


def score_unscored(model: str = DEFAULT_MODEL, limit: int | None = None) -> int:
    """Score every lead in the JSONL store missing a score. Returns count."""
    leads = load_leads()
    if not leads:
        return 0
    scored = 0
    for lead in leads:
        if lead.get("score") is not None:
            continue
        result = score_lead(lead, model=model)
        lead["score"] = result["score"]
        lead["score_reason"] = result["reason"]
        lead["urgency"] = result["urgency"]
        lead["score_engine"] = result.get("score_engine")
        scored += 1
        if limit and scored >= limit:
            break
    if scored:
        # save_leads merges by id — pass everything so updates persist.
        save_leads(leads)
    return scored


if __name__ == "__main__":
    import argparse

    logging.basicConfig(level=logging.INFO, format="%(message)s")
    p = argparse.ArgumentParser()
    p.add_argument("--limit", type=int, default=None)
    p.add_argument("--model", default=DEFAULT_MODEL)
    args = p.parse_args()
    n = score_unscored(model=args.model, limit=args.limit)
    print(json.dumps({"scored": n, "store": str(LEADS_FILE)}, indent=2))
