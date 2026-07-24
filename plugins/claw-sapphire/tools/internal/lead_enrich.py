#!/usr/bin/env python3
"""Lead enrichment — augments raw leads from lead_engine with scored fields.

Input: list of raw leads (from lead_engine discover or a saved JSON file).
Output: same leads with added fields:
    score         — 0-100 composite priority
    tier          — "hot" / "warm" / "cold" / "cool"
    intent_signals — list of matched signals ("permit_recent", "hiring_growth", ...)
    enrichment   — {domain, maybe_email, categories, normalized_name}

Never calls external APIs that cost money. Uses:
    - Regional Intel permits/news for recency-based intent
    - Simple heuristics for domain + email guessing
    - Optional Ollama (via local proxy) for industry classification

Actions:
    score   — enrich a list of leads
    pipeline — pull from lead_engine discover + enrich in one shot
    stats   — summarize enrichment run

Usage:
    echo '{"action":"score","leads":[{"name":"Acme","category":"plumbing"}]}' \\
        | python3 lead_enrich.py
    echo '{"action":"pipeline","industry":"roofing","region":"houston_tx"}' \\
        | python3 lead_enrich.py
"""

from __future__ import annotations

import contextlib
import json
import re
import sys
import urllib.parse
import urllib.request
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

SAPPHIRE_DIR = Path.home() / "Code" / "Sapphire"
LEADS_DIR = SAPPHIRE_DIR / "data" / "leads"
ENRICHED_DIR = LEADS_DIR / "enriched"
REGIONAL_INTEL_API = "http://127.0.0.1:8787"

# Intent-signal keyword buckets. Tuning is deliberate: high-intent buckets
# score much higher than generic category matches.
INTENT_SIGNALS: dict[str, tuple[str, ...]] = {
    "hiring_growth": ("hiring", "now hiring", "recruiting", "expanding team"),
    "recent_permit": ("permit", "construction", "remodel", "renovation", "new build"),
    "new_location": ("new location", "grand opening", "opening soon"),
    "funding_event": ("raised", "series a", "series b", "seed round", "funded"),
    "award_recognition": ("award", "top rated", "best of", "featured"),
    "compliance_gap": ("violation", "citation", "non-compliance", "fine"),
    "ai_adoption": ("ai", "automation", "chatbot", "machine learning"),
}

TIER_THRESHOLDS = {"hot": 75, "warm": 55, "cool": 35}

EMAIL_PATTERNS = (
    "{first}@{domain}",
    "{first}.{last}@{domain}",
    "{f}{last}@{domain}",
    "info@{domain}",
    "hello@{domain}",
)


def _slugify(s: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9\s-]", "", s).strip().lower()
    s = re.sub(r"\s+", "-", s)
    return s[:60]


def _guess_domain(name: str) -> str | None:
    """Heuristic — turns 'Acme Plumbing LLC' into 'acmeplumbing.com'.

    Not a lookup; a guess. Downstream verification (e.g. MX check) would
    confirm, but that's out of scope for this offline enricher.
    """
    if not name:
        return None
    # Strip common business suffixes
    cleaned = re.sub(r"\b(llc|inc|corp|co|ltd|company|group|the)\b", "", name, flags=re.I)
    cleaned = re.sub(r"[^a-zA-Z0-9\s]", "", cleaned).strip().lower()
    if not cleaned:
        return None
    domain = cleaned.replace(" ", "")[:40]
    return f"{domain}.com" if domain else None


def _guess_emails(name: str, domain: str | None) -> list[str]:
    if not domain:
        return []
    parts = [p.lower() for p in re.findall(r"[A-Za-z]+", name) if len(p) > 1]
    if not parts:
        return [f"info@{domain}", f"hello@{domain}"]
    first = parts[0]
    last = parts[-1] if len(parts) > 1 else first
    f_initial = first[0]
    out = set()
    for pat in EMAIL_PATTERNS:
        with contextlib.suppress(KeyError, IndexError):
            out.add(pat.format(first=first, last=last, f=f_initial, domain=domain))
    return sorted(out)[:4]


def _match_intents(text: str) -> list[str]:
    """Match intent keywords using word-boundary regexes to avoid substring
    false positives (e.g. 'ai' matching 'raised'). Each pattern is anchored
    at word boundaries so multi-word phrases still work."""
    low = text.lower()
    matched = []
    for label, patterns in INTENT_SIGNALS.items():
        for p in patterns:
            if re.search(rf"\b{re.escape(p)}\b", low):
                matched.append(label)
                break
    return matched


def _fetch_json(url: str) -> dict | None:
    try:
        with urllib.request.urlopen(url, timeout=10) as r:
            return json.loads(r.read())
    except Exception:
        return None


def _recent_permit_boost(name: str, region: str) -> int:
    """Check Regional Intel for a matching permit in the last 30 days.

    Returns 0 if Regional Intel is unavailable — we don't penalize offline mode.
    """
    if not name:
        return 0
    data = _fetch_json(f"{REGIONAL_INTEL_API}/api/intel/snapshot?region={region}")
    if not data:
        return 0
    cutoff = datetime.now(UTC) - timedelta(days=30)
    needle = name.lower()[:30]
    for p in data.get("permits", []):
        text = " ".join(str(v) for v in p.values()).lower()
        if needle and needle in text:
            date_str = p.get("issued_date") or p.get("date")
            if date_str:
                try:
                    d = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
                    if d.tzinfo is None:
                        d = d.replace(tzinfo=UTC)
                    if d >= cutoff:
                        return 15
                except ValueError:
                    pass
            return 8
    return 0


def _tier(score: float) -> str:
    if score >= TIER_THRESHOLDS["hot"]:
        return "hot"
    if score >= TIER_THRESHOLDS["warm"]:
        return "warm"
    if score >= TIER_THRESHOLDS["cool"]:
        return "cool"
    return "cold"


def enrich_one(lead: dict, region: str = "") -> dict:
    """Enrich a single lead. Pure function — no side effects."""
    name = str(lead.get("name", "")).strip()
    category = str(lead.get("category", ""))
    description = str(lead.get("description", ""))
    lead_type = str(lead.get("type", "business"))
    region = region or lead.get("region", "")

    searchable = " ".join([name, category, description])
    intents = _match_intents(searchable)

    # Base score components
    score = 0.0
    reasons: list[str] = []

    # Name completeness (15 pts)
    if name and name.lower() not in {"unknown", ""}:
        score += 15
        reasons.append("has_name")

    # Category specificity (10 pts)
    if category and len(category) > 3:
        score += 10
        reasons.append("has_category")

    # Intent signals (20 pts each, capped at 45)
    intent_pts = min(45, len(intents) * 20)
    score += intent_pts
    for i in intents:
        reasons.append(f"intent:{i}")

    # Lead type quality — contacts with titles beat raw business listings
    if lead_type == "contact":
        score += 10
        reasons.append("contact_record")
    elif lead_type == "permit":
        score += 10
        reasons.append("permit_fresh")
    elif lead_type == "organization":
        score += 5

    # Freshness from Regional Intel permits
    if region:
        boost = _recent_permit_boost(name, region)
        if boost:
            score += boost
            reasons.append(f"recent_permit+{boost}")

    # Clamp + round
    score = max(0.0, min(100.0, round(score, 1)))

    domain = _guess_domain(name)
    emails = _guess_emails(name, domain)

    enriched = dict(lead)
    enriched.update(
        {
            "score": score,
            "tier": _tier(score),
            "intent_signals": intents,
            "score_reasons": reasons,
            "enrichment": {
                "normalized_name": name.strip(),
                "slug": _slugify(name),
                "domain": domain,
                "maybe_emails": emails,
                "enriched_at": datetime.now(UTC).isoformat(),
            },
        }
    )
    return enriched


def action_score(leads: list[dict], region: str = "") -> dict:
    """Enrich a list of leads. Returns enriched list + distribution stats."""
    enriched = [enrich_one(lead, region=region) for lead in leads]
    enriched.sort(key=lambda x: x["score"], reverse=True)
    tiers = {"hot": 0, "warm": 0, "cool": 0, "cold": 0}
    for e in enriched:
        tiers[e["tier"]] += 1
    return {
        "count": len(enriched),
        "tiers": tiers,
        "leads": enriched,
    }


def action_pipeline(
    industry: str = "",
    region: str = "houston_tx",
    keywords: list[str] | None = None,
    limit: int = 20,
) -> dict:
    """Pull leads from lead_engine discover, then enrich. Persists to disk."""
    # Call lead_engine via subprocess (no import — avoids coupling)
    discovery_input = {
        "action": "discover",
        "industry": industry,
        "region": region,
        "keywords": keywords or [],
        "limit": limit,
    }
    try:
        import subprocess

        tool = Path(__file__).parent / "lead_engine.py"
        proc = subprocess.run(
            ["python3", str(tool)],
            input=json.dumps(discovery_input),
            capture_output=True,
            text=True,
            timeout=30,
        )
        if proc.returncode != 0:
            return {"error": "lead_engine failed", "stderr": proc.stderr[:500]}
        discovered = json.loads(proc.stdout)
    except Exception as e:
        return {"error": f"lead_engine call failed: {e}"}

    raw_leads = discovered.get("leads", [])
    result = action_score(raw_leads, region=region)

    ENRICHED_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    out_path = ENRICHED_DIR / f"{region}-{ts}.json"
    out_path.write_text(
        json.dumps(
            {
                "generated_at": datetime.now(UTC).isoformat(),
                "industry": industry,
                "region": region,
                "keywords": keywords or [],
                **result,
            },
            indent=2,
            default=str,
        )
    )
    result["path"] = str(out_path)
    return result


def action_stats() -> dict:
    """Summarize recent enrichment runs."""
    if not ENRICHED_DIR.exists():
        return {"runs": 0, "total_leads": 0, "files": []}
    files = sorted(ENRICHED_DIR.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    total = 0
    tiers_agg = {"hot": 0, "warm": 0, "cool": 0, "cold": 0}
    recent = []
    for f in files[:20]:
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            total += data.get("count", 0)
            for t, n in (data.get("tiers") or {}).items():
                tiers_agg[t] = tiers_agg.get(t, 0) + n
            recent.append(
                {
                    "file": f.name,
                    "count": data.get("count"),
                    "region": data.get("region"),
                    "generated_at": data.get("generated_at"),
                }
            )
        except Exception:
            pass
    return {
        "runs": len(files),
        "total_leads": total,
        "tiers": tiers_agg,
        "recent": recent,
    }


def main() -> None:
    raw = sys.stdin.read().strip()
    params: dict[str, Any] = json.loads(raw) if raw else {"action": "stats"}
    action = params.get("action", "stats")

    if action == "score":
        result = action_score(
            params.get("leads", []),
            region=params.get("region", ""),
        )
    elif action == "pipeline":
        result = action_pipeline(
            industry=params.get("industry", ""),
            region=params.get("region", "houston_tx"),
            keywords=params.get("keywords"),
            limit=int(params.get("limit", 20)),
        )
    elif action == "stats":
        result = action_stats()
    else:
        result = {"error": f"unknown action {action}"}

    print(json.dumps(result, indent=2, default=str))


if __name__ == "__main__":
    main()
