from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict, List, Optional

import httpx

from bis.models import ProgressSignal
from bis.models import SignalType
from bis.models import make_urn
from bis.store import InMemoryMasterArena

AUSTIN_PERMIT_DATASET_URL = "https://data.austintexas.gov/resource/3syk-w9eu.json"


@dataclass(frozen=True)
class PermitSourceConfig:
    source_key: str
    source_name: str
    county: str
    mode: str
    public_url: str
    api_url: str = ""
    supports_live_pull: bool = True
    supports_valuation_filter: bool = False
    notes: str = ""


PERMIT_SOURCE_REGISTRY: List[PermitSourceConfig] = [
    PermitSourceConfig(
        source_key="coa_open_data",
        source_name="City of Austin Open Data (Permits)",
        county="Travis",
        mode="public_api",
        public_url="https://data.austintexas.gov/Building-and-Development/Issued-Construction-Permits/3syk-w9eu",
        api_url=AUSTIN_PERMIT_DATASET_URL,
        supports_live_pull=True,
        supports_valuation_filter=True,
        notes="Covers City of Austin permits; Travis County coverage is partial outside Austin city limits.",
    ),
    PermitSourceConfig(
        source_key="hays_county_public_permits",
        source_name="Hays County Public Permits Portal",
        county="Hays",
        mode="public_web_portal_public_api_endpoint",
        public_url="https://www.hayscountypermits.com/public/permits/list",
        api_url="https://www.hayscountypermits.com/api/v1/permits/datatables/list/public",
        supports_live_pull=True,
        supports_valuation_filter=False,
        notes="Public DataTables endpoint discovered from page source. No valuation field exposed in list endpoint.",
    ),
    PermitSourceConfig(
        source_key="williamson_county_public_permits",
        source_name="Williamson County Public Permits Portal",
        county="Williamson",
        mode="public_web_portal_public_api_endpoint",
        public_url="https://www.wilcopermits.com/public/permits/list",
        api_url="https://www.wilcopermits.com/api/v1/permits/datatables/list/public",
        supports_live_pull=True,
        supports_valuation_filter=False,
        notes="Public DataTables endpoint discovered from page source. No valuation field exposed in list endpoint.",
    ),
    PermitSourceConfig(
        source_key="caldwell_county_permits",
        source_name="Caldwell County Permits (Source URL Pending)",
        county="Caldwell",
        mode="public_source_pending",
        public_url="",
        supports_live_pull=False,
        supports_valuation_filter=False,
        notes="Client county included; awaiting preferred public permit source URL.",
    ),
    PermitSourceConfig(
        source_key="bastrop_county_permits",
        source_name="Bastrop County Permits (Source URL Pending)",
        county="Bastrop",
        mode="public_source_pending",
        public_url="",
        supports_live_pull=False,
        supports_valuation_filter=False,
        notes="Client county included; awaiting preferred public permit source URL.",
    ),
]


def permit_source_registry() -> List[Dict[str, object]]:
    return [
        {
            "source_key": src.source_key,
            "source_name": src.source_name,
            "county": src.county,
            "mode": src.mode,
            "public_url": src.public_url,
            "api_url": src.api_url,
            "supports_live_pull": src.supports_live_pull,
            "supports_valuation_filter": src.supports_valuation_filter,
            "notes": src.notes,
        }
        for src in PERMIT_SOURCE_REGISTRY
    ]


def _parse_dt(raw: str) -> datetime:
    if not raw:
        return datetime.now(tz=timezone.utc)
    candidate = raw.replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(candidate)
    except ValueError:
        return datetime.now(tz=timezone.utc)
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def _parse_date_slash(raw: str) -> datetime:
    if not raw:
        return datetime.now(tz=timezone.utc)
    for fmt in ("%m/%d/%Y", "%m/%d/%y"):
        try:
            return datetime.strptime(raw.strip(), fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return _parse_dt(raw)


def _parse_float(raw: object) -> Optional[float]:
    if raw is None:
        return None
    try:
        return float(str(raw).replace(",", ""))
    except ValueError:
        return None


def _address_from_row(row: Dict[str, object]) -> str:
    candidates = [
        row.get("original_address1"),
        row.get("street_number") and row.get("street_name"),
        row.get("full_address"),
        row.get("address"),
    ]
    for candidate in candidates:
        if not candidate:
            continue
        if isinstance(candidate, str):
            text = candidate.strip()
        else:
            text = str(candidate).strip()
        if text:
            return text
    return ""


def permit_row_to_signal(row: Dict[str, object]) -> ProgressSignal:
    valuation = _parse_float(row.get("total_valuation") or row.get("valuation"))
    address = _address_from_row(row)
    permit_class = str(row.get("permit_class_mapped") or row.get("work_class") or "").strip()

    return ProgressSignal(
        signal_urn=make_urn("signal"),
        source="coa_open_data",
        signal_type=SignalType.NEW_PERMIT,
        observed_at=_parse_dt(str(row.get("issue_date") or row.get("issued_date") or "")),
        property_address_hint=address,
        value_delta=valuation,
        attributes={
            "permit_number": str(row.get("permit_number") or row.get("permitnum") or ""),
            "permit_class": permit_class,
            "description": str(row.get("description") or ""),
        },
    )


def _county_portal_datatables_payload(*, start: int, length: int) -> Dict[str, str]:
    payload: Dict[str, str] = {
        "draw": "1",
        "start": str(max(0, start)),
        "length": str(max(1, min(100, length))),
        "search[value]": "",
        "search[regex]": "false",
        "order[0][column]": "6",
        "order[0][dir]": "desc",
    }
    columns = [
        ("propertyType", False),
        ("name", False),
        ("address", False),
        ("permitNumber", True),
        ("permitType", False),
        ("status", False),
        ("statusDate", True),
    ]
    for idx, (name, orderable) in enumerate(columns):
        payload[f"columns[{idx}][data]"] = name
        payload[f"columns[{idx}][name]"] = name
        payload[f"columns[{idx}][searchable]"] = "true"
        payload[f"columns[{idx}][orderable]"] = "true" if orderable else "false"
        payload[f"columns[{idx}][search][value]"] = ""
        payload[f"columns[{idx}][search][regex]"] = "false"
    return payload


def _county_portal_row_to_signal(row: Dict[str, object], *, source_key: str, county: str) -> ProgressSignal:
    return ProgressSignal(
        signal_urn=make_urn("signal"),
        source=source_key,
        signal_type=SignalType.NEW_PERMIT,
        observed_at=_parse_date_slash(str(row.get("statusDate") or "")),
        property_address_hint=str(row.get("address") or "").strip(),
        value_delta=None,
        attributes={
            "county": county,
            "permit_id": str(row.get("id") or ""),
            "permit_number": str(row.get("permitNumber") or ""),
            "permit_type": str(row.get("permitType") or ""),
            "property_type": str(row.get("propertyType") or ""),
            "status": str(row.get("status") or ""),
            "project_name": str(row.get("name") or ""),
            "valuation_available": "false",
        },
    )


async def _fetch_county_portal_permit_signals(
    *,
    source_key: str,
    api_url: str,
    county: str,
    limit: int = 50,
    client: Optional[httpx.AsyncClient] = None,
) -> List[ProgressSignal]:
    own_client = client is None
    if own_client:
        client = httpx.AsyncClient(timeout=20)
    assert client is not None

    try:
        response = await client.post(
            api_url,
            data=_county_portal_datatables_payload(start=0, length=max(1, min(100, limit))),
        )
        response.raise_for_status()
        payload = response.json()
    finally:
        if own_client:
            await client.aclose()

    rows = payload.get("data", []) if isinstance(payload, dict) else []
    output: List[ProgressSignal] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        signal = _county_portal_row_to_signal(row, source_key=source_key, county=county)
        output.append(signal)
    return output


async def fetch_austin_permit_signals(
    *,
    limit: int = 50,
    min_valuation: float = 50000.0,
    client: Optional[httpx.AsyncClient] = None,
) -> List[ProgressSignal]:
    own_client = client is None
    if own_client:
        client = httpx.AsyncClient(timeout=15)

    assert client is not None

    params = {
        "$order": "issue_date DESC",
        "$limit": str(max(1, min(1000, limit))),
    }

    try:
        response = await client.get(AUSTIN_PERMIT_DATASET_URL, params=params)
        response.raise_for_status()
        rows = response.json()
    finally:
        if own_client:
            await client.aclose()

    output: List[ProgressSignal] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        signal = permit_row_to_signal(row)
        if signal.value_delta is not None and signal.value_delta < min_valuation:
            continue
        output.append(signal)
    return output


def _norm_county(value: str) -> str:
    normalized = " ".join((value or "").strip().lower().split())
    if normalized == "hayes":
        return "hays"
    return normalized


async def fetch_county_permit_signals(
    *,
    counties: Optional[List[str]] = None,
    limit_per_source: int = 50,
    min_valuation: float = 50000.0,
    client: Optional[httpx.AsyncClient] = None,
) -> List[ProgressSignal]:
    requested = {_norm_county(c) for c in (counties or []) if _norm_county(c)}
    if not requested:
        requested = {"travis", "williamson", "hays"}

    own_client = client is None
    if own_client:
        client = httpx.AsyncClient(timeout=20)
    assert client is not None

    collected: List[ProgressSignal] = []
    try:
        if "travis" in requested:
            collected.extend(
                await fetch_austin_permit_signals(
                    limit=limit_per_source,
                    min_valuation=min_valuation,
                    client=client,
                )
            )
        if "hays" in requested:
            collected.extend(
                await _fetch_county_portal_permit_signals(
                    source_key="hays_county_public_permits",
                    api_url="https://www.hayscountypermits.com/api/v1/permits/datatables/list/public",
                    county="Hays",
                    limit=limit_per_source,
                    client=client,
                )
            )
        if "williamson" in requested:
            collected.extend(
                await _fetch_county_portal_permit_signals(
                    source_key="williamson_county_public_permits",
                    api_url="https://www.wilcopermits.com/api/v1/permits/datatables/list/public",
                    county="Williamson",
                    limit=limit_per_source,
                    client=client,
                )
            )
    finally:
        if own_client:
            await client.aclose()
    return collected


def attach_signals_to_properties(store: InMemoryMasterArena, signals: List[ProgressSignal]) -> List[ProgressSignal]:
    attached: List[ProgressSignal] = []
    for signal in signals:
        if signal.property_address_hint:
            property_asset = store.find_property_by_address(signal.property_address_hint)
            if property_asset:
                signal.property_urn = property_asset.property_urn
        store.add_signal(signal)
        attached.append(signal)
    return attached
