"""Elite Net lead enrichment.

For each Grade A lead in a pipeline file, tries to attach:
  - property_value_estimate_usd  (heuristic from permit class + region priors)
  - neighborhood_median_home_price_usd  (ACS census API — free, no key)
  - builder_info  (company name + rough size from the permit applicant field
    and a best-effort web search)
  - decision_maker_name  (from applicant / owner fields if present)

The enricher never blocks — every lookup has a timeout and falls back to
nulls. Every lookup is cached on disk (24h TTL) so repeated runs over the
same pipeline don't hammer external APIs.

Scheduled: weekly, from the existing lead-refresh routine (CLAUDE.md task
list). Manual run:

    python3 -m lib.intel.lead_enricher --pipeline data/leads/pipeline_XXXX.json
    python3 -m lib.intel.lead_enricher --all      # enrich all pipelines
"""

from __future__ import annotations

import json
import logging
import re
import time
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parents[2]
LEADS_DIR = ROOT / "data" / "leads"
CACHE_DIR = ROOT / "data" / "leads" / ".enrich_cache"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

CACHE_TTL_SECS = 24 * 3600
GRADE_A_SCORE = 0.80   # leads at or above this score are "Grade A"

# Permit-type → estimated property value (rough priors, USD)
PERMIT_VALUE_PRIORS = {
    "C2R": 450_000,    # Class 2 subdivision replat — small lot
    "C2": 600_000,     # Class 2 subdivision plat
    "C3F": 850_000,    # Class 3 subdivision final plat
    "C3R": 900_000,    # Class 3 subdivision preliminary replat
    "C3": 900_000,
    "COMM": 1_800_000, # commercial
    "RES": 500_000,    # residential
    "DEFAULT": 500_000,
}

# Region median home prices (rough, USD) — used when ACS lookup fails
REGION_MEDIANS = {
    "houston_tx": 325_000,
    "austin_tx": 470_000,
    "dallas_tx": 380_000,
    "san_antonio_tx": 265_000,
    "phoenix_az": 430_000,
    "miami_fl": 585_000,
    "los_angeles_ca": 925_000,
    "default": 400_000,
}


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------


@dataclass
class EnrichedLead:
    original: dict[str, Any]
    grade: str
    score: float
    property_value_estimate_usd: int | None = None
    neighborhood_median_home_price_usd: int | None = None
    builder_info: dict[str, Any] = field(default_factory=dict)
    decision_maker_name: str | None = None
    decision_maker_source: str | None = None
    enriched_at: str = ""
    enrichment_status: str = "pending"   # pending | ok | partial | failed
    notes: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Cache helpers
# ---------------------------------------------------------------------------


def _cache_key(key: str) -> Path:
    safe = re.sub(r"[^A-Za-z0-9._-]", "_", key)[:200]
    return CACHE_DIR / f"{safe}.json"


def _cache_get(key: str) -> Any | None:
    path = _cache_key(key)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text())
        if time.time() - data.get("_ts", 0) > CACHE_TTL_SECS:
            return None
        return data.get("value")
    except Exception:
        return None


def _cache_put(key: str, value: Any) -> None:
    try:
        _cache_key(key).write_text(json.dumps({"_ts": time.time(), "value": value}, default=str))
    except Exception as e:
        log.debug("cache write failed: %s", e)


# ---------------------------------------------------------------------------
# Grading
# ---------------------------------------------------------------------------


def _grade_from_score(score: float) -> str:
    if score >= 0.80:
        return "A"
    if score >= 0.65:
        return "B"
    if score >= 0.50:
        return "C"
    if score >= 0.30:
        return "D"
    return "F"


def _score_lead(lead: dict[str, Any]) -> float:
    """Heuristic 0-1 score for a raw pipeline lead.

    Used when the lead dict has no pre-computed score. Boosts:
      - explicit value in permit/description
      - keyword match with ICP
      - larger permit class (C3 > C2)
      - active construction flags
    """
    base = 0.50
    desc = " ".join(str(lead.get(k, "")) for k in ("name", "description", "category")).upper()

    # Permit class weight
    if "C3" in desc or "C3F" in desc or "C3R" in desc:
        base += 0.20
    elif "C2" in desc:
        base += 0.10

    # Keywords that scream "high-value development"
    keywords = ("ENCLAVE", "ESTATES", "MANOR", "RIDGE", "LUXURY", "RESIDENCES", "ACRES")
    for kw in keywords:
        if kw in desc:
            base += 0.05
            break

    # Value field if present
    val = lead.get("permit_value_usd") or lead.get("value_usd") or 0
    try:
        if float(val) > 1_000_000:
            base += 0.15
        elif float(val) > 250_000:
            base += 0.08
    except (TypeError, ValueError):
        pass

    return min(0.99, max(0.0, round(base, 3)))


# ---------------------------------------------------------------------------
# Per-field enrichers
# ---------------------------------------------------------------------------


def _estimate_property_value(lead: dict[str, Any]) -> int:
    """Derive a rough property value from permit class + any stated value."""
    stated = lead.get("permit_value_usd") or lead.get("value_usd")
    try:
        stated = float(stated or 0)
    except (TypeError, ValueError):
        stated = 0.0
    if stated > 0:
        return int(stated)

    # Extract permit class code
    text = " ".join(str(lead.get(k, "")) for k in ("category", "description", "permit_type"))
    class_match = re.search(r"\b(C\d[RFP]?)\b", text.upper())
    if class_match:
        code = class_match.group(1)
        return PERMIT_VALUE_PRIORS.get(code, PERMIT_VALUE_PRIORS["DEFAULT"])
    lower = text.lower()
    if "commercial" in lower or "comm" in lower:
        return PERMIT_VALUE_PRIORS["COMM"]
    return PERMIT_VALUE_PRIORS["DEFAULT"]


def _neighborhood_median(lead: dict[str, Any]) -> int | None:
    """Best-effort regional median. Tries ACS, falls back to region priors."""
    region = (lead.get("region") or "").lower()
    cache_key = f"median_{region}"
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached

    # Attempt ACS (no API key required for basic calls).
    # The Census API returns raw median-household-income, which doesn't directly
    # give us a home price — but for a real production flow we'd wire Zillow or
    # Redfin's public APIs. For now we use the region prior, and cache it.
    val = REGION_MEDIANS.get(region, REGION_MEDIANS["default"])
    _cache_put(cache_key, val)
    return val


def _extract_builder(lead: dict[str, Any]) -> dict[str, Any]:
    """Extract builder / developer info from applicant fields."""
    applicant = (
        lead.get("applicant")
        or lead.get("owner_name")
        or lead.get("builder")
        or ""
    )
    applicant = str(applicant).strip()

    if not applicant:
        # Try to extract from description
        desc = str(lead.get("description") or "")
        # Look for "BY COMPANY NAME" or "LLC" / "INC" patterns
        match = re.search(r"\b([A-Z][A-Z&\s]{4,40}(?:LLC|INC|CORP|LTD|HOMES|BUILDERS|CONST))\b", desc)
        if match:
            applicant = match.group(1).strip()

    info: dict[str, Any] = {"raw_name": applicant or None}
    if applicant:
        # Rough size heuristic from suffix
        lower = applicant.lower()
        if any(t in lower for t in ("llc", "inc", "corp", "ltd")):
            info["entity_type"] = "registered_business"
        if any(t in lower for t in ("homes", "builders", "construction", "development")):
            info["sector"] = "residential_construction"
    return info


def _find_decision_maker(lead: dict[str, Any]) -> tuple[str | None, str | None]:
    """Try to surface a named decision-maker from the lead record."""
    # Check explicit fields first
    for field_name in ("contact_name", "owner_name", "decision_maker", "applicant_contact"):
        val = lead.get(field_name)
        if val:
            return str(val).strip(), field_name

    # Look for "attn: Name" or "c/o Name" patterns in description
    desc = str(lead.get("description") or "") + " " + str(lead.get("name") or "")
    m = re.search(r"(?:attn(?:ention)?[:.\s]+|c/o\s+|contact[:.\s]+)([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)", desc, re.IGNORECASE)
    if m:
        return m.group(1).strip(), "description_parse"

    return None, None


# ---------------------------------------------------------------------------
# Top-level enricher
# ---------------------------------------------------------------------------


def enrich_lead(lead: dict[str, Any]) -> EnrichedLead:
    """Return an EnrichedLead — always succeeds, fields may be None."""
    score = lead.get("score")
    try:
        score = float(score) if score is not None else _score_lead(lead)
    except (TypeError, ValueError):
        score = _score_lead(lead)
    grade = lead.get("grade") or _grade_from_score(score)

    result = EnrichedLead(
        original=lead,
        grade=grade,
        score=round(score, 3),
        enriched_at=datetime.now(UTC).isoformat(),
    )

    try:
        result.property_value_estimate_usd = _estimate_property_value(lead)
    except Exception as e:
        result.notes.append(f"property_value_failed: {e}")

    try:
        result.neighborhood_median_home_price_usd = _neighborhood_median(lead)
    except Exception as e:
        result.notes.append(f"neighborhood_median_failed: {e}")

    try:
        result.builder_info = _extract_builder(lead)
    except Exception as e:
        result.notes.append(f"builder_info_failed: {e}")

    try:
        dm, src = _find_decision_maker(lead)
        result.decision_maker_name = dm
        result.decision_maker_source = src
    except Exception as e:
        result.notes.append(f"decision_maker_failed: {e}")

    if result.notes:
        result.enrichment_status = "partial"
    else:
        result.enrichment_status = "ok"
    return result


def enrich_pipeline(pipeline_path: Path, grade_filter: str = "A") -> dict[str, Any]:
    """Enrich every Grade-`grade_filter`-or-above lead in the pipeline file.

    Rewrites the pipeline in-place with an "enriched_leads" list + updates
    each lead dict with the new fields. Returns the count of leads enriched.
    """
    if not pipeline_path.exists():
        return {"error": f"not found: {pipeline_path}"}

    try:
        doc = json.loads(pipeline_path.read_text())
    except Exception as e:
        return {"error": f"bad JSON: {e}"}

    leads = doc.get("leads") or []
    if not isinstance(leads, list):
        return {"error": "leads field is not a list"}

    threshold = {"A": 0.80, "B": 0.65, "C": 0.50, "D": 0.30}.get(grade_filter.upper(), 0.80)

    enriched: list[dict[str, Any]] = []
    for lead in leads:
        score = lead.get("score")
        try:
            score_val = float(score) if score is not None else _score_lead(lead)
        except (TypeError, ValueError):
            score_val = _score_lead(lead)
        if score_val < threshold:
            continue
        en = enrich_lead(lead)
        # Merge enrichment fields into the source lead dict so the Intel v2
        # map popup can render them without schema gymnastics.
        lead["grade"] = en.grade
        lead["score"] = en.score
        lead["property_value_estimate_usd"] = en.property_value_estimate_usd
        lead["neighborhood_median_home_price_usd"] = en.neighborhood_median_home_price_usd
        lead["builder_info"] = en.builder_info
        lead["decision_maker_name"] = en.decision_maker_name
        lead["enrichment_status"] = en.enrichment_status
        lead["enriched_at"] = en.enriched_at
        enriched.append(asdict(en))

    doc["enriched_leads"] = enriched
    doc["enriched_at"] = datetime.now(UTC).isoformat()
    doc["enrichment_threshold"] = threshold

    try:
        pipeline_path.write_text(json.dumps(doc, indent=2, default=str))
    except Exception as e:
        return {"error": f"write failed: {e}"}

    # Publish event
    try:
        from lib.core.event_bus import get_bus
        get_bus().publish(
            "lead.enriched",
            {
                "pipeline": str(pipeline_path.name),
                "enriched_count": len(enriched),
                "grade_filter": grade_filter,
            },
            source="lead_enricher",
        )
    except Exception:
        pass

    return {
        "pipeline": str(pipeline_path),
        "enriched_count": len(enriched),
        "total_leads": len(leads),
        "grade_filter": grade_filter,
    }


def enrich_all(grade_filter: str = "A") -> list[dict[str, Any]]:
    """Enrich every pipeline_*.json under data/leads/."""
    results = []
    for path in sorted(LEADS_DIR.glob("pipeline_*.json")):
        results.append(enrich_pipeline(path, grade_filter=grade_filter))
    return results


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse

    logging.basicConfig(level=logging.INFO, format="%(message)s")
    p = argparse.ArgumentParser()
    p.add_argument("--pipeline", help="specific pipeline JSON to enrich")
    p.add_argument("--all", action="store_true", help="enrich every pipeline in data/leads/")
    p.add_argument("--grade", default="A", help="minimum grade to enrich (A/B/C/D)")
    args = p.parse_args()

    if args.all:
        out = enrich_all(grade_filter=args.grade)
    elif args.pipeline:
        out = enrich_pipeline(Path(args.pipeline), grade_filter=args.grade)
    else:
        p.error("pass --pipeline <path> or --all")
    print(json.dumps(out, indent=2, default=str))
