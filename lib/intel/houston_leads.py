"""Houston home lead ingestion.

Three sources, one canonical schema (data/leads/houston_leads.jsonl):

1. Houston 311 service requests (CRIS public extract — pipe-delimited TXT,
   refreshed monthly-to-date). Filter for nuisance / water leak / unsafe-
   structure / property-maintenance / flooding / structural / roof / foundation.

2. Houston Permitting Center weekly XLSX activity reports. Filter for
   renovation-relevant work (remodel / repair / hvac / electrical / plumbing /
   roof / foundation / kitchen / bathroom / addition).

3. Regional Intel Workbench (localhost:8787) — already deduplicates against
   permits/businesses/contacts. Adds homeowner-relevant leads from the
   ``permits`` and ``businesses`` collections.

Each source returns ``LeadRecord`` dicts with this schema::

    {
        "id":           str,    # sr_id | permit_no | regional_intel:<hash>
        "source":       "311" | "permit" | "regional_intel",
        "address":      str,
        "zip":          str,
        "type":         str,    # service-request type / permit type / category
        "description":  str,
        "raw_data":     dict,   # original record (for audit)
        "score":        float | None,
        "score_reason": str | None,
        "urgency":      "high" | "medium" | "low" | None,
        "lat":          float | None,
        "lng":          float | None,
        "created_at":   str,    # ISO8601 of source-record creation
        "ingested_at":  str,    # ISO8601 of ingestion
    }

The XLSX dependency is optional — when ``openpyxl`` isn't installed we skip
permit ingestion gracefully. The 311 path uses only stdlib.

Public API:
    fetch_311_complaints()  -> list[dict]
    fetch_permit_activity() -> list[dict]
    fetch_regional_intel()  -> list[dict]
    ingest()                -> {"311": int, "permit": int, "regional_intel": int}
    load_leads()            -> list[dict]   (read full JSONL)
    save_leads(records)     -> int          (append-or-merge by id)
"""

from __future__ import annotations

import io
import json
import logging
import urllib.error
import urllib.request
from collections.abc import Iterable
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parents[2]
LEADS_DIR = ROOT / "data" / "leads"
LEADS_FILE = LEADS_DIR / "houston_leads.jsonl"

CRIS_311_URL = (
    "https://hfdapp.houstontx.gov/311/311-CRIS-Public-Data-Extract-D365-MTD-compressed.txt"
)
REGIONAL_INTEL_API = "http://127.0.0.1:8787"

# Service-request types relevant to home-improvement outreach.
HOME_RELEVANT_311 = (
    "nuisance on property",
    "water leak",
    "sewer wastewater",
    "unsafe structure",
    "property maintenance",
    "flooding",
    "structural",
    "roof",
    "foundation",
)

# Renovation-relevant permit keywords (matches Jessie's list).
RENOVATION_KEYWORDS = (
    "remodel",
    "renovation",
    "addition",
    "repair",
    "replace",
    "hvac",
    "electrical",
    "plumbing",
    "roof",
    "foundation",
    "window",
    "door",
    "kitchen",
    "bathroom",
    "deck",
    "fence",
)


@dataclass
class LeadRecord:
    id: str
    source: str
    address: str
    zip: str = ""
    type: str = ""
    description: str = ""
    raw_data: dict[str, Any] = field(default_factory=dict)
    score: float | None = None
    score_reason: str | None = None
    urgency: str | None = None
    lat: float | None = None
    lng: float | None = None
    created_at: str = ""
    ingested_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# ---------------------------------------------------------------------------
# JSONL store
# ---------------------------------------------------------------------------


def load_leads() -> list[dict[str, Any]]:
    """Read all leads from the JSONL store. Returns [] if missing."""
    if not LEADS_FILE.exists():
        return []
    out: list[dict[str, Any]] = []
    for line in LEADS_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out


def save_leads(records: Iterable[dict[str, Any]]) -> int:
    """Merge records into the JSONL store, deduplicating by ``id``.

    Existing records are preserved when a new record has the same id; the
    new record's non-empty fields win. Returns the count of *new* records
    added (not updates).
    """
    LEADS_DIR.mkdir(parents=True, exist_ok=True)
    existing = {r["id"]: r for r in load_leads() if r.get("id")}
    added = 0
    for rec in records:
        rid = rec.get("id")
        if not rid:
            continue
        if rid in existing:
            # Merge: only update fields that the new record actually fills.
            cur = existing[rid]
            for k, v in rec.items():
                if v not in (None, "", {}, []):
                    cur[k] = v
        else:
            existing[rid] = rec
            added += 1

    # Atomic-ish rewrite: write to temp, swap.
    tmp = LEADS_FILE.with_suffix(".jsonl.tmp")
    with tmp.open("w") as fh:
        for rec in existing.values():
            fh.write(json.dumps(rec, default=str) + "\n")
    tmp.replace(LEADS_FILE)
    return added


# ---------------------------------------------------------------------------
# 311 ingestion
# ---------------------------------------------------------------------------


def _is_home_relevant_311(service_type: str) -> bool:
    s = service_type.lower()
    return any(c in s for c in HOME_RELEVANT_311)


def _parse_311_row(line: str) -> dict[str, str] | None:
    fields = line.split("|")
    if len(fields) < 6:
        return None
    return {
        "sr_id": fields[0].strip(),
        "status": fields[1].strip(),
        "created_date": fields[2].strip(),
        "sr_type": fields[3].strip(),
        "dept": fields[4].strip() if len(fields) > 4 else "",
        "address": fields[5].strip() if len(fields) > 5 else "",
        "city": fields[6].strip() if len(fields) > 6 else "",
        "zip": fields[7].strip() if len(fields) > 7 else "",
    }


def _fetch_url_bytes(url: str, timeout: int = 30) -> bytes | None:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Sapphire-Lead-Pipeline/1.0"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read()
    except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
        log.warning("fetch failed: %s — %s", url, e)
        return None


def fetch_311_complaints(text: str | None = None) -> list[dict[str, Any]]:
    """Fetch + parse 311 home-relevant complaints.

    ``text`` is a test seam — pass a pre-fetched extract to skip the network.
    """
    if text is None:
        body = _fetch_url_bytes(CRIS_311_URL)
        if body is None:
            return []
        text = body.decode("utf-8", errors="ignore")

    leads: list[dict[str, Any]] = []
    now = datetime.now(UTC).isoformat()
    lines = text.split("\n")
    # First line is headers — skip.
    for line in lines[1:]:
        if not line.strip():
            continue
        row = _parse_311_row(line)
        if not row:
            continue
        if not row["address"] or not row["sr_type"]:
            continue
        if not _is_home_relevant_311(row["sr_type"]):
            continue

        addr = f"{row['address']}, Houston, TX {row['zip']}".strip().rstrip(",")
        rec = LeadRecord(
            id=f"311:{row['sr_id']}",
            source="311",
            address=addr,
            zip=row["zip"],
            type=row["sr_type"],
            description=f"{row['sr_type']} ({row['dept']})".strip(),
            raw_data=row,
            created_at=row["created_date"] or now,
            ingested_at=now,
        )
        leads.append(rec.to_dict())
    log.info("[311] parsed %d home-relevant complaints", len(leads))
    return leads


# ---------------------------------------------------------------------------
# Permit ingestion (XLSX)
# ---------------------------------------------------------------------------


def _is_renovation_permit(permit_type: str, description: str) -> bool:
    text = f"{permit_type} {description}".lower()
    return any(kw in text for kw in RENOVATION_KEYWORDS)


def _most_recent_permit_url(now: datetime | None = None) -> str:
    """Mirror Jessie's URL builder — Houston Permitting publishes weekly XLSX
    on Sundays under ``/sites/g/files/nwywnm431/files/YYYY-MM/Month%20DD_DD.xlsx``.
    """
    now = now or datetime.now(UTC)
    weekday = now.weekday()  # Monday = 0, Sunday = 6
    # Find most recent Sunday: if today *is* Sunday we want the previous Sunday's
    # report (this Sunday's hasn't been generated yet).
    days_back = 7 if weekday == 6 else weekday + 1
    last_sunday = now.replace(hour=0, minute=0, second=0, microsecond=0)
    last_sunday = last_sunday.fromordinal(now.toordinal() - days_back)
    next_saturday_day = last_sunday.day + 6  # may overflow into next month — Houston tolerates this
    months = [
        "January",
        "February",
        "March",
        "April",
        "May",
        "June",
        "July",
        "August",
        "September",
        "October",
        "November",
        "December",
    ]
    month_name = months[last_sunday.month - 1]
    file_part = f"{month_name}%20{last_sunday.day:02d}_{next_saturday_day}.xlsx"
    return (
        "https://www.houstonpermittingcenter.org/sites/g/files/nwywnm431/files/"
        f"{last_sunday.year}-{last_sunday.month:02d}/{file_part}"
    )


def fetch_permit_activity(buffer: bytes | None = None) -> list[dict[str, Any]]:
    """Fetch + parse weekly Houston permit XLSX.

    ``buffer`` is a test seam — pass raw XLSX bytes to skip the network.
    Returns [] if openpyxl is missing or the report can't be parsed.
    """
    try:
        import openpyxl
    except ImportError:
        log.warning("openpyxl not installed — skipping permit ingestion")
        return []

    if buffer is None:
        url = _most_recent_permit_url()
        log.info("[permits] fetching %s", url)
        buffer = _fetch_url_bytes(url, timeout=60)
        if buffer is None:
            return []

    try:
        wb = openpyxl.load_workbook(io.BytesIO(buffer), data_only=True, read_only=True)
    except Exception as e:
        log.warning("failed to parse permit XLSX: %s", e)
        return []

    sheet = wb.worksheets[0] if wb.worksheets else None
    if sheet is None:
        return []

    leads: list[dict[str, Any]] = []
    now = datetime.now(UTC).isoformat()
    for idx, row in enumerate(sheet.iter_rows(values_only=True)):
        if idx == 0:
            continue  # header
        if not row:
            continue
        # Permit XLSX columns (best-effort): permit_no, address, type, description,
        # owner, issue_date, value
        permit_no = str(row[0] or "").strip() if len(row) > 0 else ""
        address = str(row[1] or "").strip() if len(row) > 1 else ""
        permit_type = str(row[2] or "").strip() if len(row) > 2 else ""
        description = str(row[3] or "").strip() if len(row) > 3 else ""
        owner = str(row[4] or "").strip() if len(row) > 4 else ""
        issue_date = str(row[5] or "").strip() if len(row) > 5 else ""
        value = row[6] if len(row) > 6 else None

        if not permit_no or not address:
            continue
        if not _is_renovation_permit(permit_type, description):
            continue

        rec = LeadRecord(
            id=f"permit:{permit_no}",
            source="permit",
            address=f"{address}, Houston, TX",
            type=permit_type,
            description=description or permit_type,
            raw_data={
                "permit_no": permit_no,
                "permit_type": permit_type,
                "description": description,
                "owner": owner,
                "issue_date": issue_date,
                "declared_value": value,
            },
            created_at=issue_date or now,
            ingested_at=now,
        )
        leads.append(rec.to_dict())
    log.info("[permits] parsed %d renovation permits", len(leads))
    return leads


# ---------------------------------------------------------------------------
# Regional Intel ingestion
# ---------------------------------------------------------------------------


def _fetch_json(url: str, timeout: int = 10) -> dict | None:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Sapphire-Lead-Pipeline/1.0"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read())
    except Exception as e:
        log.debug("regional-intel fetch failed: %s", e)
        return None


def fetch_regional_intel(
    region: str = "houston_tx", api_url: str = REGIONAL_INTEL_API
) -> list[dict[str, Any]]:
    """Pull homeowner-relevant entries from Regional Intel Workbench."""
    snap = _fetch_json(f"{api_url}/api/intel/snapshot?region={region}")
    if not snap:
        log.info("[regional-intel] snapshot unavailable")
        return []

    now = datetime.now(UTC).isoformat()
    leads: list[dict[str, Any]] = []

    # Permits from regional intel
    for permit in snap.get("permits", []):
        permit_no = (
            permit.get("permit_no")
            or permit.get("permit_number")
            or permit.get("id")
            or permit.get("number")
        )
        address = permit.get("address") or permit.get("location") or ""
        ptype = permit.get("permit_type") or permit.get("work_type") or permit.get("category", "")
        desc = permit.get("description") or permit.get("work_description") or ""
        if not permit_no or not address:
            continue
        if not _is_renovation_permit(str(ptype), str(desc)):
            continue
        rec = LeadRecord(
            id=f"regional_intel:permit:{permit_no}",
            source="regional_intel",
            address=str(address),
            type=str(ptype),
            description=str(desc) or str(ptype),
            raw_data=dict(permit),
            created_at=str(permit.get("issued_date") or permit.get("date") or now),
            ingested_at=now,
        )
        leads.append(rec.to_dict())

    log.info("[regional-intel] parsed %d permits", len(leads))
    return leads


# ---------------------------------------------------------------------------
# Top-level ingest
# ---------------------------------------------------------------------------


def ingest(
    sources: tuple[str, ...] = ("311", "permit", "regional_intel"),
    region: str = "houston_tx",
) -> dict[str, int]:
    """Run all configured sources and merge into JSONL store.

    Returns a per-source count of *newly added* records.
    """
    counts: dict[str, int] = {}
    if "311" in sources:
        recs = fetch_311_complaints()
        counts["311"] = save_leads(recs)
    if "permit" in sources:
        recs = fetch_permit_activity()
        counts["permit"] = save_leads(recs)
    if "regional_intel" in sources:
        recs = fetch_regional_intel(region=region)
        counts["regional_intel"] = save_leads(recs)

    # Publish event so dashboards see the refresh.
    try:
        from lib.core.event_bus import get_bus

        get_bus().publish(
            "lead.ingested",
            {"counts": counts, "region": region},
            source="houston_leads",
        )
    except Exception:
        pass

    return counts


if __name__ == "__main__":
    import argparse

    logging.basicConfig(level=logging.INFO, format="%(message)s")
    p = argparse.ArgumentParser()
    p.add_argument("--source", action="append", default=None, help="311, permit, regional_intel")
    p.add_argument("--region", default="houston_tx")
    args = p.parse_args()

    sources = tuple(args.source) if args.source else ("311", "permit", "regional_intel")
    out = ingest(sources=sources, region=args.region)
    print(json.dumps({"ingested": out, "store": str(LEADS_FILE)}, indent=2))
