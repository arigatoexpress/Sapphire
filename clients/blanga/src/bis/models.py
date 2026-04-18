from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from enum import StrEnum
from uuid import uuid4


def utc_now() -> datetime:
    return datetime.now(tz=UTC)


def make_urn(prefix: str) -> str:
    return f"{prefix}:{uuid4().hex[:12]}"


class SignalType(StrEnum):
    NEW_PERMIT = "new_permit"
    ZONING_APPLICATION = "zoning_application"
    OWNERSHIP_CHANGE = "ownership_change"
    NEWS_MENTION = "news_mention"


class OutreachState(StrEnum):
    ACTIVE = "active"
    PAUSED = "paused"


class ListingStatus(StrEnum):
    DRAFT = "draft"
    LISTED = "listed"
    UNDER_CONTRACT = "under_contract"
    SOLD = "sold"
    OFF_MARKET = "off_market"


class MarketEventType(StrEnum):
    LISTED = "listed"
    SOLD = "sold"
    CLIENT_NEWS = "client_news"
    INDUSTRY_NEWS = "industry_news"
    NEW_COMPANY = "new_company"


class ReviewStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


@dataclass
class Person:
    person_urn: str
    full_name: str
    phones: list[str] = field(default_factory=list)
    emails: list[str] = field(default_factory=list)
    dnc: bool = False
    notes: str = ""
    created_at: datetime = field(default_factory=utc_now)
    updated_at: datetime = field(default_factory=utc_now)


@dataclass
class LlcEntity:
    llc_urn: str
    legal_name: str
    state: str = "TX"
    sos_file_number: str = ""
    officer_person_urns: list[str] = field(default_factory=list)
    created_at: datetime = field(default_factory=utc_now)
    updated_at: datetime = field(default_factory=utc_now)


@dataclass
class PropertyAsset:
    property_urn: str
    address_line1: str
    city: str
    county: str
    state: str = "TX"
    postal_code: str = ""
    submarket: str = ""
    corridor: str = ""
    asset_type: str = "stnl_retail"
    tenant_brand: str = ""
    occupancy_status: str = ""
    building_sqft: float | None = None
    land_acres: float | None = None
    year_built: int | None = None
    asking_price: float | None = None
    noi: float | None = None
    cap_rate: float | None = None
    current_rent_psf: float | None = None
    submarket_avg_rent_psf: float | None = None
    lease_expiration: date | None = None
    ownership_start: date | None = None
    owner_llc_urns: list[str] = field(default_factory=list)
    listing_status: ListingStatus = ListingStatus.DRAFT
    listed_at: date | None = None
    sold_at: date | None = None
    close_price: float | None = None
    listing_broker: str = ""
    redo: bool = False
    potential_listing: bool = False
    outreach_state: OutreachState = OutreachState.ACTIVE
    created_at: datetime = field(default_factory=utc_now)
    updated_at: datetime = field(default_factory=utc_now)


@dataclass
class NoteEntry:
    note_urn: str
    note_text: str
    owner_person_urn: str | None = None
    property_urn: str | None = None
    tags: list[str] = field(default_factory=list)
    created_by: str = "broker"
    created_at: datetime = field(default_factory=utc_now)


@dataclass
class ProgressSignal:
    signal_urn: str
    source: str
    signal_type: SignalType
    observed_at: datetime
    property_urn: str | None = None
    property_address_hint: str = ""
    value_delta: float | None = None
    attributes: dict[str, str] = field(default_factory=dict)


@dataclass
class OMExtractionRecord:
    extraction_urn: str
    source_name: str
    property_urn: str | None
    fields: dict[str, str]
    confidences: dict[str, float]
    extracted_at: datetime = field(default_factory=utc_now)


@dataclass
class PropensityScore:
    property_urn: str
    score: float
    components: dict[str, float]
    generated_at: datetime = field(default_factory=utc_now)


@dataclass
class GeneratedDocument:
    document_urn: str
    doc_type: str
    title: str
    content: str
    property_urn: str | None = None
    owner_person_urn: str | None = None
    source_event_urn: str | None = None
    created_at: datetime = field(default_factory=utc_now)


@dataclass
class MarketEvent:
    event_urn: str
    event_type: MarketEventType
    title: str
    observed_at: datetime
    property_urn: str | None = None
    property_address_hint: str = ""
    owner_person_urn: str | None = None
    company_name: str = ""
    source_url: str = ""
    summary: str = ""
    attributes: dict[str, str] = field(default_factory=dict)


@dataclass
class FieldObservation:
    observation_urn: str
    entity_type: str
    entity_urn: str
    field_name: str
    proposed_value: str
    confidence: float
    source_type: str
    source_ref: str
    rationale: str = ""
    extracted_by: str = "bis"
    observed_at: datetime = field(default_factory=utc_now)


@dataclass
class ReviewTask:
    review_urn: str
    observation_urn: str
    entity_type: str
    entity_urn: str
    field_name: str
    status: ReviewStatus = ReviewStatus.PENDING
    created_at: datetime = field(default_factory=utc_now)
    reviewed_at: datetime | None = None
    reviewed_by: str = ""
    review_note: str = ""
