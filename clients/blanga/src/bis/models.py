from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from enum import Enum
from typing import Dict, List, Optional
from uuid import uuid4


def utc_now() -> datetime:
    return datetime.now(tz=timezone.utc)


def make_urn(prefix: str) -> str:
    return f"{prefix}:{uuid4().hex[:12]}"


class SignalType(str, Enum):
    NEW_PERMIT = "new_permit"
    ZONING_APPLICATION = "zoning_application"
    OWNERSHIP_CHANGE = "ownership_change"
    NEWS_MENTION = "news_mention"


class OutreachState(str, Enum):
    ACTIVE = "active"
    PAUSED = "paused"


class ListingStatus(str, Enum):
    DRAFT = "draft"
    LISTED = "listed"
    UNDER_CONTRACT = "under_contract"
    SOLD = "sold"
    OFF_MARKET = "off_market"


class MarketEventType(str, Enum):
    LISTED = "listed"
    SOLD = "sold"
    CLIENT_NEWS = "client_news"
    INDUSTRY_NEWS = "industry_news"
    NEW_COMPANY = "new_company"


class ReviewStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


@dataclass
class Person:
    person_urn: str
    full_name: str
    phones: List[str] = field(default_factory=list)
    emails: List[str] = field(default_factory=list)
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
    officer_person_urns: List[str] = field(default_factory=list)
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
    building_sqft: Optional[float] = None
    land_acres: Optional[float] = None
    year_built: Optional[int] = None
    asking_price: Optional[float] = None
    noi: Optional[float] = None
    cap_rate: Optional[float] = None
    current_rent_psf: Optional[float] = None
    submarket_avg_rent_psf: Optional[float] = None
    lease_expiration: Optional[date] = None
    ownership_start: Optional[date] = None
    owner_llc_urns: List[str] = field(default_factory=list)
    listing_status: ListingStatus = ListingStatus.DRAFT
    listed_at: Optional[date] = None
    sold_at: Optional[date] = None
    close_price: Optional[float] = None
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
    owner_person_urn: Optional[str] = None
    property_urn: Optional[str] = None
    tags: List[str] = field(default_factory=list)
    created_by: str = "broker"
    created_at: datetime = field(default_factory=utc_now)


@dataclass
class ProgressSignal:
    signal_urn: str
    source: str
    signal_type: SignalType
    observed_at: datetime
    property_urn: Optional[str] = None
    property_address_hint: str = ""
    value_delta: Optional[float] = None
    attributes: Dict[str, str] = field(default_factory=dict)


@dataclass
class OMExtractionRecord:
    extraction_urn: str
    source_name: str
    property_urn: Optional[str]
    fields: Dict[str, str]
    confidences: Dict[str, float]
    extracted_at: datetime = field(default_factory=utc_now)


@dataclass
class PropensityScore:
    property_urn: str
    score: float
    components: Dict[str, float]
    generated_at: datetime = field(default_factory=utc_now)


@dataclass
class GeneratedDocument:
    document_urn: str
    doc_type: str
    title: str
    content: str
    property_urn: Optional[str] = None
    owner_person_urn: Optional[str] = None
    source_event_urn: Optional[str] = None
    created_at: datetime = field(default_factory=utc_now)


@dataclass
class MarketEvent:
    event_urn: str
    event_type: MarketEventType
    title: str
    observed_at: datetime
    property_urn: Optional[str] = None
    property_address_hint: str = ""
    owner_person_urn: Optional[str] = None
    company_name: str = ""
    source_url: str = ""
    summary: str = ""
    attributes: Dict[str, str] = field(default_factory=dict)


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
    reviewed_at: Optional[datetime] = None
    reviewed_by: str = ""
    review_note: str = ""
