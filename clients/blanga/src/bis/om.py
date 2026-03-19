from __future__ import annotations

import re
from typing import Dict, Optional

from bis.models import OMExtractionRecord
from bis.models import make_urn


def _search(pattern: str, text: str) -> Optional[str]:
    match = re.search(pattern, text, flags=re.IGNORECASE | re.MULTILINE)
    if not match:
        return None
    return match.group(1).strip()


def _to_clean_number(raw: str) -> Optional[float]:
    cleaned = raw.replace(",", "").replace("$", "").replace("%", "").strip()
    try:
        return float(cleaned)
    except ValueError:
        return None


def _confidence(raw: Optional[str], numeric: bool = False) -> float:
    if raw is None:
        return 0.0
    if numeric:
        value = _to_clean_number(raw)
        return 0.96 if value is not None else 0.0
    if len(raw) >= 3:
        return 0.91
    return 0.0


def extract_om_fields(*, source_name: str, document_text: str, property_urn: Optional[str] = None) -> OMExtractionRecord:
    text = document_text or ""

    extracted: Dict[str, str] = {}
    confidences: Dict[str, float] = {}

    noi_raw = _search(r"\bNOI\b[^\d$]*([$\d,]+(?:\.\d+)?)", text)
    cap_rate_raw = _search(r"\bCap(?:italization)?\s*Rate\b[^\d]*([\d.]+%?)", text)
    ask_raw = _search(r"\b(?:Asking\s*Price|List\s*Price)\b[^\d$]*([$\d,]+(?:\.\d+)?)", text)
    tenant_raw = _search(r"\bTenant\b\s*[:\-]?\s*([A-Za-z0-9& .,'-]{2,})", text)
    lease_term_raw = _search(r"\b(?:Lease\s*(?:Term|Expiration|Expires?)|Remaining\s*Term)\b[^\d]*(\d+(?:\.\d+)?)\s*(?:years?|yrs?)", text)
    rsf_raw = _search(r"\b(?:RSF|Rentable\s*SF|Building\s*Area)\b[^\d]*([\d,]+(?:\.\d+)?)", text)
    land_acres_raw = _search(r"\b(?:Land\s*Acreage|Acreage|Land\s*Area)\b[^\d]*([\d.]+)", text)
    year_built_raw = _search(r"\b(?:Year\s*Built|Built\s*in)\b[^\d]*(19\d{2}|20\d{2})", text)

    for key, value, numeric in [
        ("noi", noi_raw, True),
        ("cap_rate", cap_rate_raw, True),
        ("asking_price", ask_raw, True),
        ("tenant_brand", tenant_raw, False),
        ("remaining_lease_term_years", lease_term_raw, True),
        ("rentable_sqft", rsf_raw, True),
        ("land_acres", land_acres_raw, True),
        ("year_built", year_built_raw, True),
    ]:
        if value is None:
            continue
        extracted[key] = value
        confidences[key] = round(_confidence(value, numeric=numeric), 2)

    return OMExtractionRecord(
        extraction_urn=make_urn("om"),
        source_name=source_name,
        property_urn=property_urn,
        fields=extracted,
        confidences=confidences,
    )
