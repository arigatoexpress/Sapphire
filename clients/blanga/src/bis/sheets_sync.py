from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any

from bis.models import ListingStatus
from bis.store import InMemoryMasterArena

SHEETS_TAB_CONTRACT: dict[str, dict[str, Any]] = {
    "properties_new_input": {
        "description": "Append-only broker tab for brand new properties. BIS rejects accidental duplicates and writes canonical data to master/writeback tabs.",
        "required_columns": ["address_line1", "owner_name"],
        "optional_columns": [
            "city",
            "county",
            "llc_name",
            "tenant_brand",
            "occupancy_status",
            "submarket",
            "corridor",
            "building_sqft",
            "land_acres",
            "asking_price",
            "listing_status",
            "listed_at",
            "note_text",
            "source_label",
        ],
    },
    "property_updates_input": {
        "description": "Append-only patch requests for existing properties. Empty values do not overwrite fields unless clear_field=true.",
        "required_columns": ["field_name", "new_value"],
        "optional_columns": [
            "property_urn",
            "address_line1",
            "address",
            "reason",
            "requested_by",
            "clear_field",
            "source_label",
        ],
    },
    "notes_input": {
        "description": "Append-only broker notes tab. BIS links notes to property/owner, extracts follow-up dates into Today’s Tasks, and creates suggested structured updates.",
        "required_columns": ["note_text"],
        "optional_columns": [
            "property_urn",
            "address_line1",
            "address",
            "owner_name",
            "created_at",
            "entered_by",
            "source_label",
            "tags",
        ],
    },
    "properties_input": {
        "description": "Broker-operated input tab. BIS imports rows from here.",
        "required_columns": ["address_line1", "owner_name"],
        "optional_columns": [
            "city",
            "county",
            "llc_name",
            "tenant_brand",
            "occupancy_status",
            "submarket",
            "corridor",
            "building_sqft",
            "land_acres",
            "asking_price",
            "close_price",
            "listing_status",
            "listed_at",
            "sold_at",
            "note_text",
            "dnc",
            "redo",
            "source_label",
        ],
    },
    "properties_computed": {
        "description": "BIS writeback preview for DOM, pricing metrics, outreach state, and review-safe structured fields.",
        "writeback_columns": [
            "property_urn",
            "address_line1",
            "city",
            "county",
            "listing_status",
            "listed_at",
            "sold_at",
            "days_on_market",
            "tenant_brand",
            "occupancy_status",
            "asking_price",
            "close_price",
            "sale_price_per_building_sf",
            "sale_price_per_land_sf",
            "outreach_state",
            "redo",
            "potential_listing",
            "updated_at",
        ],
    },
    "properties_master_view": {
        "description": "BIS writeback mirror of canonical property records (read-only/protected in Sheets).",
        "writeback_columns": [
            "property_urn",
            "address_line1",
            "city",
            "county",
            "owner_names",
            "listing_status",
            "tenant_brand",
            "occupancy_status",
            "building_sqft",
            "land_acres",
            "asking_price",
            "close_price",
            "cap_rate",
            "lease_expiration",
            "days_on_market",
            "sale_price_per_building_sf",
            "sale_price_per_land_sf",
            "updated_at",
        ],
    },
    "reviews_pending": {
        "description": "Pending AI suggestions from notes/OMs before column writeback.",
        "writeback_columns": [
            "review_urn",
            "field_name",
            "proposed_value",
            "confidence",
            "entity_urn",
            "source_type",
            "source_ref",
            "created_at",
            "status",
        ],
    },
    "change_log_view": {
        "description": "BIS writeback of audit/change activity for trust and recovery.",
        "writeback_columns": [
            "created_at",
            "action",
            "actor",
            "summary",
            "entity_type",
            "entity_urn",
            "details_json",
        ],
    },
    "today_tasks_view": {
        "description": "BIS writeback preview of next best actions / follow-up tasks.",
        "writeback_columns": [
            "action_urn",
            "category",
            "priority_score",
            "title",
            "reason",
            "recommended_action",
            "property_address",
            "entity_urn",
            "created_at",
        ],
    },
}


@dataclass(frozen=True)
class NormalizedPropertiesRow:
    address_line1: str
    owner_name: str
    city: str = "Austin"
    county: str = "Travis"
    llc_name: str = ""
    tenant_brand: str = ""
    occupancy_status: str = ""
    submarket: str = ""
    corridor: str = ""
    building_sqft: float | None = None
    land_acres: float | None = None
    asking_price: float | None = None
    close_price: float | None = None
    listing_status: ListingStatus | None = None
    listed_at: date | None = None
    sold_at: date | None = None
    note_text: str = ""
    dnc: bool | None = None
    redo: bool | None = None
    source_label: str = "google-sheets"


@dataclass(frozen=True)
class NormalizedNotesRow:
    note_text: str
    property_urn: str = ""
    address_line1: str = ""
    owner_name: str = ""
    entered_by: str = "broker"
    source_label: str = "google-sheets"
    created_at: date | None = None
    tags: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class NormalizedPropertyUpdateRow:
    property_urn: str = ""
    address_line1: str = ""
    field_name: str = ""
    new_value: str = ""
    reason: str = ""
    requested_by: str = "broker"
    clear_field: bool = False
    source_label: str = "google-sheets"


def sheet_contract() -> dict[str, Any]:
    return {"tabs": SHEETS_TAB_CONTRACT}


def _norm_key(key: str) -> str:
    return str(key or "").strip().lower().replace(" ", "_")


def _as_str(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _as_float(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    raw = str(value).strip().replace(",", "").replace("$", "")
    if not raw:
        return None
    try:
        return float(raw)
    except ValueError:
        return None


def _as_bool(value: Any) -> bool | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    raw = str(value).strip().lower()
    if raw in {"1", "true", "yes", "y"}:
        return True
    if raw in {"0", "false", "no", "n"}:
        return False
    return None


def _as_date(value: Any) -> date | None:
    if value is None:
        return None
    if isinstance(value, date):
        return value
    raw = str(value).strip()
    if not raw:
        return None
    try:
        return date.fromisoformat(raw)
    except ValueError:
        return None


def _as_listing_status(value: Any) -> ListingStatus | None:
    raw = _as_str(value).lower()
    if not raw:
        return None
    raw = raw.replace(" ", "_").replace("-", "_")
    try:
        return ListingStatus(raw)
    except ValueError:
        return None


def normalize_properties_row(row: dict[str, Any]) -> NormalizedPropertiesRow:
    normalized = {_norm_key(k): v for k, v in row.items()}
    address_line1 = _as_str(normalized.get("address_line1") or normalized.get("address"))
    owner_name = _as_str(normalized.get("owner_name") or normalized.get("owner"))
    if not address_line1 or not owner_name:
        raise ValueError("properties_input row requires address_line1 and owner_name")

    return NormalizedPropertiesRow(
        address_line1=address_line1,
        owner_name=owner_name,
        city=_as_str(normalized.get("city")) or "Austin",
        county=_as_str(normalized.get("county")) or "Travis",
        llc_name=_as_str(normalized.get("llc_name")),
        tenant_brand=_as_str(normalized.get("tenant_brand")),
        occupancy_status=_as_str(normalized.get("occupancy_status")).lower(),
        submarket=_as_str(normalized.get("submarket")),
        corridor=_as_str(normalized.get("corridor")),
        building_sqft=_as_float(normalized.get("building_sqft")),
        land_acres=_as_float(normalized.get("land_acres")),
        asking_price=_as_float(normalized.get("asking_price")),
        close_price=_as_float(normalized.get("close_price")),
        listing_status=_as_listing_status(normalized.get("listing_status")),
        listed_at=_as_date(normalized.get("listed_at")),
        sold_at=_as_date(normalized.get("sold_at")),
        note_text=_as_str(normalized.get("note_text")),
        dnc=_as_bool(normalized.get("dnc")),
        redo=_as_bool(normalized.get("redo")),
        source_label=_as_str(normalized.get("source_label")) or "google-sheets",
    )


def _parse_tags(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(v).strip() for v in value if str(v).strip()]
    raw = str(value).strip()
    if not raw:
        return []
    separators = [",", ";", "|"]
    for sep in separators:
        if sep in raw:
            return [part.strip() for part in raw.split(sep) if part.strip()]
    return [raw]


def normalize_notes_row(row: dict[str, Any]) -> NormalizedNotesRow:
    normalized = {_norm_key(k): v for k, v in row.items()}
    note_text = _as_str(normalized.get("note_text") or normalized.get("note"))
    if not note_text:
        raise ValueError("notes_input row requires note_text")
    tags = _parse_tags(normalized.get("tags"))
    return NormalizedNotesRow(
        note_text=note_text,
        property_urn=_as_str(normalized.get("property_urn")),
        address_line1=_as_str(normalized.get("address_line1") or normalized.get("address")),
        owner_name=_as_str(normalized.get("owner_name") or normalized.get("owner")),
        entered_by=_as_str(normalized.get("entered_by") or normalized.get("created_by")) or "broker",
        source_label=_as_str(normalized.get("source_label")) or "google-sheets",
        created_at=_as_date(normalized.get("created_at")),
        tags=tags,
    )


def normalize_property_update_row(row: dict[str, Any]) -> NormalizedPropertyUpdateRow:
    normalized = {_norm_key(k): v for k, v in row.items()}
    field_name = _as_str(normalized.get("field_name"))
    if not field_name:
        raise ValueError("property_updates_input row requires field_name")
    if normalized.get("new_value") is None and normalized.get("value") is not None:
        normalized["new_value"] = normalized.get("value")
    new_value = _as_str(normalized.get("new_value"))
    property_urn = _as_str(normalized.get("property_urn"))
    address_line1 = _as_str(normalized.get("address_line1") or normalized.get("address"))
    if not property_urn and not address_line1:
        raise ValueError("property_updates_input row requires property_urn or address_line1")
    return NormalizedPropertyUpdateRow(
        property_urn=property_urn,
        address_line1=address_line1,
        field_name=field_name,
        new_value=new_value,
        reason=_as_str(normalized.get("reason")),
        requested_by=_as_str(normalized.get("requested_by") or normalized.get("entered_by")) or "broker",
        clear_field=bool(_as_bool(normalized.get("clear_field")) or False),
        source_label=_as_str(normalized.get("source_label")) or "google-sheets",
    )


def writeback_preview_rows(arena: InMemoryMasterArena, *, tab: str) -> list[dict[str, Any]]:
    if tab == "properties_computed":
        rows: list[dict[str, Any]] = []
        for prop in sorted(arena.list_properties(), key=lambda p: (p.city.lower(), p.address_line1.lower())):
            rows.append(
                {
                    "property_urn": prop.property_urn,
                    "address_line1": prop.address_line1,
                    "city": prop.city,
                    "county": prop.county,
                    "listing_status": prop.listing_status.value,
                    "listed_at": prop.listed_at.isoformat() if prop.listed_at else "",
                    "sold_at": prop.sold_at.isoformat() if prop.sold_at else "",
                    "days_on_market": arena.days_on_market(prop.property_urn),
                    "tenant_brand": prop.tenant_brand,
                    "occupancy_status": prop.occupancy_status,
                    "asking_price": prop.asking_price,
                    "close_price": prop.close_price,
                    "sale_price_per_building_sf": arena.sale_price_per_building_sf(prop),
                    "sale_price_per_land_sf": arena.sale_price_per_land_sf(prop),
                    "outreach_state": prop.outreach_state.value,
                    "redo": prop.redo,
                    "potential_listing": prop.potential_listing,
                    "updated_at": prop.updated_at.isoformat(),
                }
            )
        return rows

    if tab == "properties_master_view":
        rows: list[dict[str, Any]] = []
        for prop in sorted(arena.list_properties(), key=lambda p: (p.city.lower(), p.address_line1.lower())):
            owners = [owner.full_name for owner in arena.owners_for_property(prop.property_urn)]
            rows.append(
                {
                    "property_urn": prop.property_urn,
                    "address_line1": prop.address_line1,
                    "city": prop.city,
                    "county": prop.county,
                    "owner_names": " | ".join(sorted(owners)),
                    "listing_status": prop.listing_status.value,
                    "tenant_brand": prop.tenant_brand,
                    "occupancy_status": prop.occupancy_status,
                    "building_sqft": prop.building_sqft,
                    "land_acres": prop.land_acres,
                    "asking_price": prop.asking_price,
                    "close_price": prop.close_price,
                    "cap_rate": prop.cap_rate,
                    "lease_expiration": prop.lease_expiration.isoformat() if prop.lease_expiration else "",
                    "days_on_market": arena.days_on_market(prop.property_urn),
                    "sale_price_per_building_sf": arena.sale_price_per_building_sf(prop),
                    "sale_price_per_land_sf": arena.sale_price_per_land_sf(prop),
                    "updated_at": prop.updated_at.isoformat(),
                }
            )
        return rows

    if tab == "reviews_pending":
        rows = []
        for review in arena.list_review_tasks(status="pending"):
            obs = arena.get_field_observation(review.observation_urn)
            rows.append(
                {
                    "review_urn": review.review_urn,
                    "field_name": review.field_name,
                    "proposed_value": obs.proposed_value if obs else "",
                    "confidence": obs.confidence if obs else None,
                    "entity_urn": review.entity_urn,
                    "source_type": obs.source_type if obs else "",
                    "source_ref": obs.source_ref if obs else "",
                    "created_at": review.created_at.isoformat(),
                    "status": review.status.value,
                }
            )
        return rows

    raise ValueError(f"unsupported writeback tab: {tab}")
