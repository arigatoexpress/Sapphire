from __future__ import annotations

from collections.abc import Sequence
from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime, timedelta
from enum import Enum
from typing import Any

from bis.models import (
    FieldObservation,
    GeneratedDocument,
    ListingStatus,
    LlcEntity,
    MarketEvent,
    MarketEventType,
    NoteEntry,
    OMExtractionRecord,
    OutreachState,
    Person,
    ProgressSignal,
    PropertyAsset,
    ReviewStatus,
    ReviewTask,
    SignalType,
)


def _norm(text: str) -> str:
    return " ".join((text or "").strip().lower().split())


def _now() -> datetime:
    return datetime.now(tz=UTC)


def _encode_snapshot_value(value: Any) -> Any:
    if isinstance(value, datetime):
        return {"__type__": "datetime", "value": value.isoformat()}
    if isinstance(value, date):
        return {"__type__": "date", "value": value.isoformat()}
    if isinstance(value, Enum):
        return {"__type__": "enum", "value": value.value}
    if isinstance(value, dict):
        return {str(k): _encode_snapshot_value(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_encode_snapshot_value(v) for v in value]
    return value


def _decode_snapshot_datetime(value: Any) -> datetime | None:
    if value in (None, ""):
        return None
    if isinstance(value, dict) and value.get("__type__") == "datetime":
        value = value.get("value")
    if not isinstance(value, str):
        return None
    return datetime.fromisoformat(value)


def _decode_snapshot_date(value: Any) -> date | None:
    if value in (None, ""):
        return None
    if isinstance(value, dict) and value.get("__type__") == "date":
        value = value.get("value")
    if not isinstance(value, str):
        return None
    return date.fromisoformat(value)


def _decode_snapshot_enum(value: Any, enum_cls: type[Enum]) -> Enum:
    if isinstance(value, dict) and value.get("__type__") == "enum":
        value = value.get("value")
    return enum_cls(value)


@dataclass
class PropertyQuery:
    tenant_brand: str = ""
    city: str = ""
    county: str = ""
    corridor: str = ""
    submarket: str = ""
    max_land_psf: float | None = None
    max_building_psf: float | None = None
    max_building_sqft: float | None = None
    min_cap_rate: float | None = None
    max_cap_rate: float | None = None
    occupancy_status: str = ""
    lease_expiring_within_years: int | None = None
    only_active_outreach: bool = False


class InMemoryMasterArena:
    """
    Master Arena v0 store.

    This is intentionally in-memory so the API can run without infrastructure.
    The same interfaces can be backed by BigQuery + Vertex pipelines in production.
    """

    def __init__(self) -> None:
        self.people: dict[str, Person] = {}
        self.llcs: dict[str, LlcEntity] = {}
        self.properties: dict[str, PropertyAsset] = {}
        self.notes: dict[str, NoteEntry] = {}
        self.signals: dict[str, ProgressSignal] = {}
        self.om_extractions: dict[str, OMExtractionRecord] = {}
        self.documents: dict[str, GeneratedDocument] = {}
        self.market_events: dict[str, MarketEvent] = {}
        self.field_observations: dict[str, FieldObservation] = {}
        self.review_tasks: dict[str, ReviewTask] = {}
        self.canonical_field_values: dict[tuple[str, str, str], str] = {}

        self._address_to_property_urn: dict[str, str] = {}
        self._notes_by_property: dict[str, list[str]] = {}
        self._notes_by_owner: dict[str, list[str]] = {}

    def reset(self) -> None:
        self.people.clear()
        self.llcs.clear()
        self.properties.clear()
        self.notes.clear()
        self.signals.clear()
        self.om_extractions.clear()
        self.documents.clear()
        self.market_events.clear()
        self.field_observations.clear()
        self.review_tasks.clear()
        self.canonical_field_values.clear()
        self._address_to_property_urn.clear()
        self._notes_by_property.clear()
        self._notes_by_owner.clear()

    def snapshot(self) -> dict[str, Any]:
        def encode_items(items: Sequence[Any]) -> list[dict[str, Any]]:
            return [_encode_snapshot_value(asdict(item)) for item in items]

        return {
            "version": 1,
            "generated_at": _now().isoformat(),
            "counts": {
                "people": len(self.people),
                "llcs": len(self.llcs),
                "properties": len(self.properties),
                "notes": len(self.notes),
                "signals": len(self.signals),
                "om_extractions": len(self.om_extractions),
                "documents": len(self.documents),
                "market_events": len(self.market_events),
                "field_observations": len(self.field_observations),
                "review_tasks": len(self.review_tasks),
            },
            "people": encode_items(list(self.people.values())),
            "llcs": encode_items(list(self.llcs.values())),
            "properties": encode_items(list(self.properties.values())),
            "notes": encode_items(list(self.notes.values())),
            "signals": encode_items(list(self.signals.values())),
            "om_extractions": encode_items(list(self.om_extractions.values())),
            "documents": encode_items(list(self.documents.values())),
            "market_events": encode_items(list(self.market_events.values())),
            "field_observations": encode_items(list(self.field_observations.values())),
            "review_tasks": encode_items(list(self.review_tasks.values())),
            "canonical_field_values": [
                {
                    "entity_type": entity_type,
                    "entity_urn": entity_urn,
                    "field_name": field_name,
                    "value": value,
                }
                for (entity_type, entity_urn, field_name), value in self.canonical_field_values.items()
            ],
        }

    def restore_snapshot(self, payload: dict[str, Any]) -> dict[str, int]:
        self.reset()

        for row in payload.get("people", []):
            person = Person(
                person_urn=str(row["person_urn"]),
                full_name=str(row["full_name"]),
                phones=[str(v) for v in row.get("phones", [])],
                emails=[str(v) for v in row.get("emails", [])],
                dnc=bool(row.get("dnc", False)),
                notes=str(row.get("notes", "")),
                created_at=_decode_snapshot_datetime(row.get("created_at")) or _now(),
                updated_at=_decode_snapshot_datetime(row.get("updated_at")) or _now(),
            )
            self.people[person.person_urn] = person

        for row in payload.get("llcs", []):
            llc = LlcEntity(
                llc_urn=str(row["llc_urn"]),
                legal_name=str(row["legal_name"]),
                state=str(row.get("state", "TX")),
                sos_file_number=str(row.get("sos_file_number", "")),
                officer_person_urns=[str(v) for v in row.get("officer_person_urns", [])],
                created_at=_decode_snapshot_datetime(row.get("created_at")) or _now(),
                updated_at=_decode_snapshot_datetime(row.get("updated_at")) or _now(),
            )
            self.llcs[llc.llc_urn] = llc

        for row in payload.get("properties", []):
            prop = PropertyAsset(
                property_urn=str(row["property_urn"]),
                address_line1=str(row["address_line1"]),
                city=str(row["city"]),
                county=str(row["county"]),
                state=str(row.get("state", "TX")),
                postal_code=str(row.get("postal_code", "")),
                submarket=str(row.get("submarket", "")),
                corridor=str(row.get("corridor", "")),
                asset_type=str(row.get("asset_type", "stnl_retail")),
                tenant_brand=str(row.get("tenant_brand", "")),
                occupancy_status=str(row.get("occupancy_status", "")),
                building_sqft=float(row["building_sqft"]) if row.get("building_sqft") is not None else None,
                land_acres=float(row["land_acres"]) if row.get("land_acres") is not None else None,
                year_built=int(row["year_built"]) if row.get("year_built") is not None else None,
                asking_price=float(row["asking_price"]) if row.get("asking_price") is not None else None,
                noi=float(row["noi"]) if row.get("noi") is not None else None,
                cap_rate=float(row["cap_rate"]) if row.get("cap_rate") is not None else None,
                current_rent_psf=float(row["current_rent_psf"]) if row.get("current_rent_psf") is not None else None,
                submarket_avg_rent_psf=(
                    float(row["submarket_avg_rent_psf"]) if row.get("submarket_avg_rent_psf") is not None else None
                ),
                lease_expiration=_decode_snapshot_date(row.get("lease_expiration")),
                ownership_start=_decode_snapshot_date(row.get("ownership_start")),
                owner_llc_urns=[str(v) for v in row.get("owner_llc_urns", [])],
                listing_status=_decode_snapshot_enum(row.get("listing_status", ListingStatus.DRAFT.value), ListingStatus),
                listed_at=_decode_snapshot_date(row.get("listed_at")),
                sold_at=_decode_snapshot_date(row.get("sold_at")),
                close_price=float(row["close_price"]) if row.get("close_price") is not None else None,
                listing_broker=str(row.get("listing_broker", "")),
                redo=bool(row.get("redo", False)),
                potential_listing=bool(row.get("potential_listing", False)),
                outreach_state=_decode_snapshot_enum(
                    row.get("outreach_state", OutreachState.ACTIVE.value),
                    OutreachState,
                ),
                created_at=_decode_snapshot_datetime(row.get("created_at")) or _now(),
                updated_at=_decode_snapshot_datetime(row.get("updated_at")) or _now(),
            )
            self.properties[prop.property_urn] = prop

        for row in payload.get("notes", []):
            note = NoteEntry(
                note_urn=str(row["note_urn"]),
                note_text=str(row["note_text"]),
                owner_person_urn=str(row["owner_person_urn"]) if row.get("owner_person_urn") else None,
                property_urn=str(row["property_urn"]) if row.get("property_urn") else None,
                tags=[str(v) for v in row.get("tags", [])],
                created_by=str(row.get("created_by", "broker")),
                created_at=_decode_snapshot_datetime(row.get("created_at")) or _now(),
            )
            self.notes[note.note_urn] = note

        for row in payload.get("signals", []):
            signal = ProgressSignal(
                signal_urn=str(row["signal_urn"]),
                source=str(row.get("source", "")),
                signal_type=_decode_snapshot_enum(row.get("signal_type", SignalType.NEW_PERMIT.value), SignalType),
                observed_at=_decode_snapshot_datetime(row.get("observed_at")) or _now(),
                property_urn=str(row["property_urn"]) if row.get("property_urn") else None,
                property_address_hint=str(row.get("property_address_hint", "")),
                value_delta=float(row["value_delta"]) if row.get("value_delta") is not None else None,
                attributes={str(k): str(v) for k, v in row.get("attributes", {}).items()},
            )
            self.signals[signal.signal_urn] = signal

        for row in payload.get("om_extractions", []):
            extraction = OMExtractionRecord(
                extraction_urn=str(row["extraction_urn"]),
                source_name=str(row.get("source_name", "")),
                property_urn=str(row["property_urn"]) if row.get("property_urn") else None,
                fields={str(k): str(v) for k, v in row.get("fields", {}).items()},
                confidences={str(k): float(v) for k, v in row.get("confidences", {}).items()},
                extracted_at=_decode_snapshot_datetime(row.get("extracted_at")) or _now(),
            )
            self.om_extractions[extraction.extraction_urn] = extraction

        for row in payload.get("documents", []):
            document = GeneratedDocument(
                document_urn=str(row["document_urn"]),
                doc_type=str(row.get("doc_type", "")),
                title=str(row.get("title", "")),
                content=str(row.get("content", "")),
                property_urn=str(row["property_urn"]) if row.get("property_urn") else None,
                owner_person_urn=str(row["owner_person_urn"]) if row.get("owner_person_urn") else None,
                source_event_urn=str(row["source_event_urn"]) if row.get("source_event_urn") else None,
                created_at=_decode_snapshot_datetime(row.get("created_at")) or _now(),
            )
            self.documents[document.document_urn] = document

        for row in payload.get("market_events", []):
            event = MarketEvent(
                event_urn=str(row["event_urn"]),
                event_type=_decode_snapshot_enum(row.get("event_type"), MarketEventType),
                title=str(row.get("title", "")),
                observed_at=_decode_snapshot_datetime(row.get("observed_at")) or _now(),
                property_urn=str(row["property_urn"]) if row.get("property_urn") else None,
                property_address_hint=str(row.get("property_address_hint", "")),
                owner_person_urn=str(row["owner_person_urn"]) if row.get("owner_person_urn") else None,
                company_name=str(row.get("company_name", "")),
                source_url=str(row.get("source_url", "")),
                summary=str(row.get("summary", "")),
                attributes={str(k): str(v) for k, v in row.get("attributes", {}).items()},
            )
            self.market_events[event.event_urn] = event

        for row in payload.get("field_observations", []):
            observation = FieldObservation(
                observation_urn=str(row["observation_urn"]),
                entity_type=str(row.get("entity_type", "")),
                entity_urn=str(row.get("entity_urn", "")),
                field_name=str(row.get("field_name", "")),
                proposed_value=str(row.get("proposed_value", "")),
                confidence=float(row.get("confidence", 0.0)),
                source_type=str(row.get("source_type", "")),
                source_ref=str(row.get("source_ref", "")),
                rationale=str(row.get("rationale", "")),
                extracted_by=str(row.get("extracted_by", "bis")),
                observed_at=_decode_snapshot_datetime(row.get("observed_at")) or _now(),
            )
            self.field_observations[observation.observation_urn] = observation

        for row in payload.get("review_tasks", []):
            task = ReviewTask(
                review_urn=str(row["review_urn"]),
                observation_urn=str(row.get("observation_urn", "")),
                entity_type=str(row.get("entity_type", "")),
                entity_urn=str(row.get("entity_urn", "")),
                field_name=str(row.get("field_name", "")),
                status=_decode_snapshot_enum(row.get("status", ReviewStatus.PENDING.value), ReviewStatus),
                created_at=_decode_snapshot_datetime(row.get("created_at")) or _now(),
                reviewed_at=_decode_snapshot_datetime(row.get("reviewed_at")),
                reviewed_by=str(row.get("reviewed_by", "")),
                review_note=str(row.get("review_note", "")),
            )
            self.review_tasks[task.review_urn] = task

        for row in payload.get("canonical_field_values", []):
            key = (str(row.get("entity_type", "")), str(row.get("entity_urn", "")), str(row.get("field_name", "")))
            self.canonical_field_values[key] = str(row.get("value", ""))

        self._rebuild_indexes()
        return {
            "people": len(self.people),
            "llcs": len(self.llcs),
            "properties": len(self.properties),
            "notes": len(self.notes),
            "review_tasks": len(self.review_tasks),
        }

    def upsert_person(self, person: Person) -> Person:
        existing = self.people.get(person.person_urn)
        if existing:
            person.created_at = existing.created_at
        person.updated_at = _now()
        self.people[person.person_urn] = person
        self._sync_property_compliance_for_person(person.person_urn)
        return person

    def upsert_llc(self, llc: LlcEntity) -> LlcEntity:
        existing = self.llcs.get(llc.llc_urn)
        if existing:
            llc.created_at = existing.created_at
        llc.updated_at = _now()
        llc.officer_person_urns = list(dict.fromkeys(llc.officer_person_urns))
        self.llcs[llc.llc_urn] = llc
        self._sync_properties_for_llc(llc.llc_urn)
        return llc

    def attach_officer_to_llc(self, *, person_urn: str, llc_urn: str) -> None:
        llc = self.llcs.get(llc_urn)
        if not llc:
            raise KeyError(f"llc not found: {llc_urn}")
        if person_urn not in llc.officer_person_urns:
            llc.officer_person_urns.append(person_urn)
            llc.updated_at = _now()
        self._sync_properties_for_llc(llc_urn)

    def upsert_property(self, property_asset: PropertyAsset) -> PropertyAsset:
        existing = self.properties.get(property_asset.property_urn)
        if existing:
            property_asset.created_at = existing.created_at
        property_asset.updated_at = _now()
        property_asset.owner_llc_urns = list(dict.fromkeys(property_asset.owner_llc_urns))
        self.properties[property_asset.property_urn] = property_asset
        self._address_to_property_urn[_norm(property_asset.address_line1)] = property_asset.property_urn
        self._sync_property_compliance(property_asset.property_urn)
        return property_asset

    def find_property_by_address(self, address_line1: str) -> PropertyAsset | None:
        urn = self._address_to_property_urn.get(_norm(address_line1))
        if not urn:
            return None
        return self.properties.get(urn)

    def add_note(self, note: NoteEntry) -> NoteEntry:
        self.notes[note.note_urn] = note
        if note.property_urn:
            self._notes_by_property.setdefault(note.property_urn, []).append(note.note_urn)
        if note.owner_person_urn:
            self._notes_by_owner.setdefault(note.owner_person_urn, []).append(note.note_urn)
        return note

    def add_signal(self, signal: ProgressSignal) -> ProgressSignal:
        self.signals[signal.signal_urn] = signal
        return signal

    def add_om_extraction(self, extraction: OMExtractionRecord) -> OMExtractionRecord:
        self.om_extractions[extraction.extraction_urn] = extraction
        return extraction

    def add_document(self, document: GeneratedDocument) -> GeneratedDocument:
        self.documents[document.document_urn] = document
        return document

    def list_documents(
        self,
        *,
        property_urn: str | None = None,
        owner_person_urn: str | None = None,
        doc_type: str = "",
    ) -> list[GeneratedDocument]:
        docs = list(self.documents.values())
        if property_urn:
            docs = [doc for doc in docs if doc.property_urn == property_urn]
        if owner_person_urn:
            docs = [doc for doc in docs if doc.owner_person_urn == owner_person_urn]
        if doc_type:
            docs = [doc for doc in docs if _norm(doc.doc_type) == _norm(doc_type)]
        docs.sort(key=lambda doc: doc.created_at, reverse=True)
        return docs

    def latest_document_for_property(self, *, property_urn: str, doc_type: str = "") -> GeneratedDocument | None:
        docs = self.list_documents(property_urn=property_urn, doc_type=doc_type)
        return docs[0] if docs else None

    def add_market_event(self, event: MarketEvent) -> MarketEvent:
        self.market_events[event.event_urn] = event
        self._apply_market_event(event)
        return event

    def add_field_observation(self, observation: FieldObservation) -> FieldObservation:
        self.field_observations[observation.observation_urn] = observation
        return observation

    def create_review_task(self, task: ReviewTask) -> ReviewTask:
        self.review_tasks[task.review_urn] = task
        return task

    def list_review_tasks(
        self,
        *,
        status: str = "",
        entity_urn: str | None = None,
        field_name: str = "",
    ) -> list[ReviewTask]:
        tasks = list(self.review_tasks.values())
        if status:
            normalized = _norm(status)
            tasks = [task for task in tasks if _norm(task.status.value) == normalized]
        if entity_urn:
            tasks = [task for task in tasks if task.entity_urn == entity_urn]
        if field_name:
            normalized_field = _norm(field_name)
            tasks = [task for task in tasks if _norm(task.field_name) == normalized_field]
        tasks.sort(key=lambda task: task.created_at, reverse=True)
        return tasks

    def get_review_task(self, review_urn: str) -> ReviewTask | None:
        return self.review_tasks.get(review_urn)

    def get_field_observation(self, observation_urn: str) -> FieldObservation | None:
        return self.field_observations.get(observation_urn)

    def approve_review_task(self, *, review_urn: str, reviewed_by: str, review_note: str = "") -> ReviewTask:
        task = self.review_tasks.get(review_urn)
        if not task:
            raise KeyError(f"review task not found: {review_urn}")
        observation = self.field_observations.get(task.observation_urn)
        if not observation:
            raise KeyError(f"observation not found: {task.observation_urn}")

        task.status = ReviewStatus.APPROVED
        task.reviewed_at = _now()
        task.reviewed_by = reviewed_by
        task.review_note = review_note
        self._apply_observation(observation)
        return task

    def reject_review_task(self, *, review_urn: str, reviewed_by: str, review_note: str = "") -> ReviewTask:
        task = self.review_tasks.get(review_urn)
        if not task:
            raise KeyError(f"review task not found: {review_urn}")
        task.status = ReviewStatus.REJECTED
        task.reviewed_at = _now()
        task.reviewed_by = reviewed_by
        task.review_note = review_note
        return task

    def list_market_events(
        self,
        *,
        property_urn: str | None = None,
        owner_person_urn: str | None = None,
        event_type: str = "",
        since_days: int | None = None,
    ) -> list[MarketEvent]:
        events = list(self.market_events.values())
        if property_urn:
            events = [event for event in events if event.property_urn == property_urn]
        if owner_person_urn:
            events = [event for event in events if event.owner_person_urn == owner_person_urn]
        if event_type:
            normalized = _norm(event_type)
            events = [event for event in events if _norm(event.event_type.value) == normalized]
        if since_days is not None and since_days >= 0:
            cutoff = _now() - timedelta(days=since_days)
            events = [event for event in events if event.observed_at >= cutoff]
        events.sort(key=lambda event: event.observed_at, reverse=True)
        return events

    def get_person(self, person_urn: str) -> Person | None:
        return self.people.get(person_urn)

    def get_llc(self, llc_urn: str) -> LlcEntity | None:
        return self.llcs.get(llc_urn)

    def get_property(self, property_urn: str) -> PropertyAsset | None:
        return self.properties.get(property_urn)

    def get_note(self, note_urn: str) -> NoteEntry | None:
        return self.notes.get(note_urn)

    def list_properties(self) -> list[PropertyAsset]:
        return list(self.properties.values())

    def list_signals(self, *, property_urn: str | None = None, since_days: int | None = None) -> list[ProgressSignal]:
        items = list(self.signals.values())
        if property_urn:
            items = [item for item in items if item.property_urn == property_urn]
        if since_days is not None and since_days >= 0:
            cutoff = _now() - timedelta(days=since_days)
            items = [item for item in items if item.observed_at >= cutoff]
        items.sort(key=lambda item: item.observed_at, reverse=True)
        return items

    def owners_for_property(self, property_urn: str) -> list[Person]:
        prop = self.properties.get(property_urn)
        if not prop:
            return []
        owner_urns: list[str] = []
        for llc_urn in prop.owner_llc_urns:
            llc = self.llcs.get(llc_urn)
            if not llc:
                continue
            owner_urns.extend(llc.officer_person_urns)
        owners: list[Person] = []
        seen = set()
        for owner_urn in owner_urns:
            if owner_urn in seen:
                continue
            person = self.people.get(owner_urn)
            if person:
                owners.append(person)
                seen.add(owner_urn)
        return owners

    def notes_rollup_for_property(self, property_urn: str) -> list[NoteEntry]:
        prop = self.properties.get(property_urn)
        if not prop:
            return []

        collected_ids: list[str] = []
        collected_ids.extend(self._notes_by_property.get(property_urn, []))
        for owner in self.owners_for_property(property_urn):
            collected_ids.extend(self._notes_by_owner.get(owner.person_urn, []))

        unique_ids: list[str] = []
        seen = set()
        for note_id in collected_ids:
            if note_id in seen:
                continue
            seen.add(note_id)
            unique_ids.append(note_id)

        notes = [self.notes[nid] for nid in unique_ids if nid in self.notes]
        notes.sort(key=lambda note: note.created_at, reverse=True)
        return notes

    def apply_redo(self, property_urn: str, redo: bool = True) -> None:
        prop = self.properties.get(property_urn)
        if not prop:
            raise KeyError(f"property not found: {property_urn}")
        prop.redo = redo
        prop.potential_listing = True if redo else prop.potential_listing
        prop.updated_at = _now()
        self._sync_property_compliance(property_urn)

    def set_potential_listing(self, property_urn: str, value: bool) -> None:
        prop = self.properties.get(property_urn)
        if not prop:
            raise KeyError(f"property not found: {property_urn}")
        prop.potential_listing = value
        prop.updated_at = _now()

    def set_person_dnc(self, person_urn: str, value: bool) -> None:
        person = self.people.get(person_urn)
        if not person:
            raise KeyError(f"person not found: {person_urn}")
        person.dnc = value
        person.updated_at = _now()
        self._sync_property_compliance_for_person(person_urn)

    def mark_listed(self, *, property_urn: str, listed_at: date | None = None, list_price: float | None = None) -> None:
        prop = self.properties.get(property_urn)
        if not prop:
            raise KeyError(f"property not found: {property_urn}")
        prop.listing_status = ListingStatus.LISTED
        prop.listed_at = listed_at or date.today()
        prop.potential_listing = True
        if list_price is not None:
            prop.asking_price = list_price
        prop.updated_at = _now()

    def mark_under_contract(self, *, property_urn: str) -> None:
        prop = self.properties.get(property_urn)
        if not prop:
            raise KeyError(f"property not found: {property_urn}")
        prop.listing_status = ListingStatus.UNDER_CONTRACT
        prop.updated_at = _now()

    def mark_sold(self, *, property_urn: str, sold_at: date | None = None, close_price: float | None = None) -> None:
        prop = self.properties.get(property_urn)
        if not prop:
            raise KeyError(f"property not found: {property_urn}")
        prop.listing_status = ListingStatus.SOLD
        prop.sold_at = sold_at or date.today()
        if prop.listed_at is None:
            prop.listed_at = prop.sold_at
        if close_price is not None:
            prop.close_price = close_price
        prop.potential_listing = False
        prop.outreach_state = OutreachState.PAUSED
        prop.updated_at = _now()

    def days_on_market(self, property_urn: str, *, as_of: date | None = None) -> int | None:
        prop = self.properties.get(property_urn)
        if not prop or not prop.listed_at:
            return None
        endpoint = prop.sold_at or as_of or date.today()
        days = (endpoint - prop.listed_at).days
        return max(0, days)

    def query_properties(self, query: PropertyQuery) -> list[PropertyAsset]:
        now_date = date.today()
        tenant_brand = _norm(query.tenant_brand)
        city = _norm(query.city)
        county = _norm(query.county)
        corridor = _norm(query.corridor)
        submarket = _norm(query.submarket)
        occupancy_status = _norm(query.occupancy_status)

        matches: list[PropertyAsset] = []
        for item in self.properties.values():
            if tenant_brand and tenant_brand not in _norm(item.tenant_brand):
                continue
            if city and city != _norm(item.city):
                continue
            if county and county != _norm(item.county):
                continue
            if corridor and corridor not in _norm(item.corridor):
                continue
            if submarket and submarket not in _norm(item.submarket):
                continue

            if query.max_land_psf is not None:
                land_psf = self.sale_price_per_land_sf(item)
                if land_psf is None or land_psf > query.max_land_psf:
                    continue

            if query.max_building_psf is not None:
                bldg_psf = self.sale_price_per_building_sf(item)
                if bldg_psf is None or bldg_psf > query.max_building_psf:
                    continue

            if query.max_building_sqft is not None:
                if item.building_sqft is None or item.building_sqft > query.max_building_sqft:
                    continue

            if query.min_cap_rate is not None:
                if item.cap_rate is None or item.cap_rate < query.min_cap_rate:
                    continue

            if query.max_cap_rate is not None:
                if item.cap_rate is None or item.cap_rate > query.max_cap_rate:
                    continue

            if occupancy_status:
                prop_occ = _norm(item.occupancy_status)
                if occupancy_status == "vacant":
                    if "vacant" not in prop_occ:
                        continue
                elif occupancy_status == "leased":
                    inferred_leased = prop_occ in {"leased", "occupied"} or (not prop_occ and bool(item.tenant_brand))
                    if not inferred_leased:
                        continue
                elif occupancy_status not in prop_occ:
                    continue

            if query.lease_expiring_within_years is not None:
                if not item.lease_expiration:
                    continue
                expiry_limit = now_date + timedelta(days=365 * query.lease_expiring_within_years)
                if item.lease_expiration > expiry_limit:
                    continue

            if query.only_active_outreach and item.outreach_state != OutreachState.ACTIVE:
                continue

            matches.append(item)

        matches.sort(key=lambda prop: (_norm(prop.city), _norm(prop.address_line1)))
        return matches

    @staticmethod
    def rent_psf(item: PropertyAsset) -> float | None:
        if item.current_rent_psf is None:
            return None
        return round(item.current_rent_psf, 2)

    @staticmethod
    def sale_price_per_building_sf(item: PropertyAsset) -> float | None:
        if item.asking_price is None or not item.building_sqft:
            return None
        if item.building_sqft <= 0:
            return None
        return round(item.asking_price / item.building_sqft, 2)

    @staticmethod
    def sale_price_per_land_sf(item: PropertyAsset) -> float | None:
        if item.asking_price is None or not item.land_acres:
            return None
        if item.land_acres <= 0:
            return None
        land_sf = item.land_acres * 43560.0
        return round(item.asking_price / land_sf, 2)

    @staticmethod
    def list_to_close_delta(*, list_price: float | None, close_price: float | None) -> float | None:
        if list_price is None or close_price is None or list_price <= 0:
            return None
        return round(((close_price - list_price) / list_price) * 100.0, 2)

    @staticmethod
    def cap_rate(*, noi: float | None, price: float | None) -> float | None:
        if noi is None or price is None or price <= 0:
            return None
        return round((noi / price) * 100.0, 2)

    def _sync_properties_for_llc(self, llc_urn: str) -> None:
        for prop in self.properties.values():
            if llc_urn in prop.owner_llc_urns:
                self._sync_property_compliance(prop.property_urn)

    def _sync_property_compliance_for_person(self, person_urn: str) -> None:
        for prop in self.properties.values():
            for llc_urn in prop.owner_llc_urns:
                llc = self.llcs.get(llc_urn)
                if llc and person_urn in llc.officer_person_urns:
                    self._sync_property_compliance(prop.property_urn)
                    break

    def _sync_property_compliance(self, property_urn: str) -> None:
        prop = self.properties.get(property_urn)
        if not prop:
            return

        owners = self.owners_for_property(property_urn)
        dnc_on_owner = any(owner.dnc for owner in owners)
        if prop.redo or dnc_on_owner:
            prop.outreach_state = OutreachState.PAUSED
        else:
            prop.outreach_state = OutreachState.ACTIVE
        prop.updated_at = _now()

    def _apply_market_event(self, event: MarketEvent) -> None:
        if not event.property_urn and event.property_address_hint:
            matched = self.find_property_by_address(event.property_address_hint)
            if matched:
                event.property_urn = matched.property_urn

        if not event.property_urn:
            return

        if event.event_type == MarketEventType.LISTED:
            listed_date = event.observed_at.date()
            list_price = None
            raw = event.attributes.get("list_price", "")
            try:
                list_price = float(raw) if raw else None
            except ValueError:
                list_price = None
            self.mark_listed(property_urn=event.property_urn, listed_at=listed_date, list_price=list_price)
            return

        if event.event_type == MarketEventType.SOLD:
            sold_date = event.observed_at.date()
            close_price = None
            raw = event.attributes.get("close_price", "")
            try:
                close_price = float(raw) if raw else None
            except ValueError:
                close_price = None
            self.mark_sold(property_urn=event.property_urn, sold_at=sold_date, close_price=close_price)

    def _apply_observation(self, observation: FieldObservation) -> None:
        key = (observation.entity_type, observation.entity_urn, observation.field_name)
        self.canonical_field_values[key] = observation.proposed_value

        if observation.entity_type != "property":
            return
        prop = self.properties.get(observation.entity_urn)
        if not prop:
            return

        field_name = observation.field_name
        raw = observation.proposed_value

        if field_name == "lease_expiration":
            try:
                prop.lease_expiration = date.fromisoformat(raw)
            except ValueError:
                return
            prop.updated_at = _now()
            return

        if field_name == "tenant_brand":
            prop.tenant_brand = raw
            prop.updated_at = _now()
            return

        if field_name == "occupancy_status":
            prop.occupancy_status = raw.strip().lower()
            prop.updated_at = _now()
            if prop.occupancy_status == "vacant":
                prop.potential_listing = True
            return

    def _rebuild_indexes(self) -> None:
        self._address_to_property_urn.clear()
        self._notes_by_property.clear()
        self._notes_by_owner.clear()

        for prop in self.properties.values():
            self._address_to_property_urn[_norm(prop.address_line1)] = prop.property_urn

        for note in self.notes.values():
            if note.property_urn:
                self._notes_by_property.setdefault(note.property_urn, []).append(note.note_urn)
            if note.owner_person_urn:
                self._notes_by_owner.setdefault(note.owner_person_urn, []).append(note.note_urn)

        for prop in self.properties.values():
            self._sync_property_compliance(prop.property_urn)
